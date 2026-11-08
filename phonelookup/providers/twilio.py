"""Twilio Lookup v2 (HLR-backed) plus the block-probing built on top of it.

Twilio gives the current, possibly-ported carrier for one number; sampling a few
numbers per block turns that into evidence for who holds the block now. Results
are cached so a repeat run, or a resumed sweep, costs nothing.
"""

from __future__ import annotations

import base64
import contextlib
import csv
import json
import time
from collections import Counter
from collections.abc import Callable
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from .. import constants as c
from ..config import env_setting
from ..core import lookup
from ..naming import (
    circle_code,
    operator_name,
    twilio_circle_code,
    twilio_operator_code,
)
from ..records import Credentials, Live, Row
from ..registry import network_registry

Budget = dict[str, Any]  # {"calls": int, "max": int | None}
Sample = dict[str, Any]  # one per-number probe record (values may be None)


class BudgetExceeded(Exception):
    """Raised to stop a sweep cleanly once the billed-call cap is reached."""


def _today() -> str:
    """Today as YYYY-MM-DD, for cache stamps and probe logs."""
    return date.today().isoformat()


def twilio_lookup(e164: str, sid: str, token: str,
                  fields: str = c.LTI_FIELD) -> Live:
    """Call Twilio Lookup v2 for one E.164 number (HLR-backed carrier data).

    `fields` is Twilio's comma-separated package list; the result is flattened to
    the number facts we use. Returns {"error": ...} on failure; the credentials
    are HTTP Basic auth and are never logged.
    """
    url = env_setting("TWILIO_LOOKUP_URL") or c.TWILIO_LOOKUP_URL
    query = urlencode({"Fields": fields})
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    request = Request(
        f"{url}/{quote_plus(e164)}?{query}",
        headers={"Authorization": f"Basic {auth}"},
    )
    # A long sweep gets rate-limited (429) and transient 5xx/timeouts; back off
    # and retry so throttling slows the run instead of blanking it.
    body: dict[str, Any] = {}
    for attempt in range(c.TWILIO_RETRIES):
        try:
            with urlopen(request, timeout=10) as resp:
                body = json.load(resp)
            break
        except HTTPError as err:
            if err.code in (429, 500, 502, 503, 504) and attempt < c.TWILIO_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            try:
                detail = json.load(err)
            except ValueError:
                return {"error": f"request failed: {err}"}
            return {"error": detail.get("message") or f"request failed: {err}"}
        except (URLError, TimeoutError, ValueError) as err:
            if attempt < c.TWILIO_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            return {"error": f"request failed: {err}"}

    lti = body.get("line_type_intelligence") or {}
    result: Live = {
        "valid": body.get("valid"),
        "number": body.get("phone_number"),
        "national_format": body.get("national_format"),
        "country_code": body.get("country_code"),
        "carrier": lti.get("carrier_name"),
        "line_type": lti.get("type"),
        "mobile_country_code": lti.get("mobile_country_code"),
        "mobile_network_code": lti.get("mobile_network_code"),
        "fields": fields,
    }
    registry = network_registry(result["mobile_country_code"],
                                result["mobile_network_code"])
    if registry:
        result["network_registry"] = registry
    if c.LINE_STATUS_FIELD in fields:
        result["line_status"] = twilio_line_status(body)
    if c.SIM_SWAP_FIELD in fields:
        result[c.SIM_SWAP_FIELD] = body.get(c.SIM_SWAP_FIELD)
    if c.CALL_FORWARDING_FIELD in fields:
        result[c.CALL_FORWARDING_FIELD] = body.get(c.CALL_FORWARDING_FIELD)
    return result


def twilio_line_status(body: dict[str, Any]) -> Live:
    """Flatten a Lookup v2 line_status block, or an error note if absent.

    The field is gated, so Twilio may return it null or with an error_code even
    on a 200; record that instead of silently dropping it.
    """
    status = body.get("line_status")
    if not status:
        return {"error": "line_status not returned (not licensed/available)"}
    if status.get("error_code"):
        return {"error": f"line_status error_code {status['error_code']}"}
    return {"status": status.get("status")}


def live_cache_load() -> dict[str, Live]:
    """Read the git-ignored live-lookup cache, or {} if absent/unreadable."""
    try:
        return json.loads(c.LIVE_CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def live_cache_save(cache: dict[str, Live]) -> None:
    """Write the live-lookup cache back to disk (best effort)."""
    with contextlib.suppress(OSError):
        c.LIVE_CACHE.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def _covers(cached: Live, fields: str) -> bool:
    """True when a cached result already includes every requested field."""
    have = (cached.get("fields") or c.LTI_FIELD).split(",")
    return all(field in have for field in fields.split(","))


def cached_twilio_lookup(e164: str, twilio: Credentials, cache: dict[str, Live],
                         refresh: bool, fields: str = c.LTI_FIELD) -> Live:
    """A Twilio result for e164, from cache unless refresh or a new field forces
    a refetch. A fresh call is stored with a fetched_at date; errors are not
    cached.
    """
    cached = cache.get(e164)
    if not refresh and cached and _covers(cached, fields):
        return cached
    result = twilio_lookup(e164, twilio[0], twilio[1], fields)
    if "error" not in result:
        result = {**result, "fetched_at": _today()}
        cache[e164] = result
    return result


def block_sample_numbers(prefix: str, count: int) -> list[str]:
    """`count` E.164 numbers spread evenly across an Indian block.

    Suffixes sit at even offsets so the sample spans the range and is
    deterministic, so a re-run reuses the cache instead of paying again.
    """
    suffix_len = 10 - len(prefix)
    span = 10 ** suffix_len
    numbers = []
    for i in range(count):
        suffix = int((i + 0.5) / count * span)
        numbers.append(f"+91{prefix}{suffix:0{suffix_len}d}")
    return numbers


def block_note(prefix: str, counts: Counter[str], total: int) -> str:
    """Describe a block sample for the CSV note, spelling out any split."""
    parts = [f"{n}/{total} {operator_name(code) if code else 'unknown'}"
             for code, n in counts.most_common()]
    return (f"{total} numbers sampled via Twilio HLR ({'; '.join(parts)}); "
            "current-carrier evidence (MNP), not a DoT allocation")


def live_outcome(live: Live, ok: bool) -> str:
    """Classify one live result for the probe summary (error/absent/line type)."""
    if not ok:
        return "error"
    if not live.get("valid") or not live.get("carrier"):
        return "absent"
    return live.get("line_type") or "unknown"


def is_live_mobile(live: Live) -> bool:
    """True when a live result is a reachable mobile line worth counting."""
    return ("error" not in live and bool(live.get("valid"))
            and live.get("line_type") == "mobile")


def sample_row(number: str, live: Live) -> Sample:
    """One per-number record: live facts plus the offline carrier/location."""
    offline = lookup(number)
    return {
        "number": number,
        "live_carrier": live.get("carrier"),
        "live_code": twilio_operator_code(live.get("carrier", "")) if is_live_mobile(live) else "",
        "mcc": live.get("mobile_country_code"),
        "mnc": live.get("mobile_network_code"),
        "line_type": live.get("line_type"),
        "offline_carrier": offline.get("carrier"),
        "location": offline.get("location"),
        "error": live.get("error"),
    }


def aggregate_block(prefix: str, pairs: list[tuple[str, Live]]) -> dict[str, Any]:
    """Turn (number, live) pairs for one block into a probe result.

    Only live mobile lines vote; a majority (> half the mobile samples) yields a
    suggested row, otherwise it is inconclusive.
    """
    samples: list[Sample] = []
    counts: Counter[str] = Counter()
    circles: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    for number, live in pairs:
        row = sample_row(number, live)
        if is_live_mobile(live):
            counts[row["live_code"]] += 1
            # Prefer the circle Twilio names in the carrier string (present for
            # gap blocks too); fall back to the offline circle.
            circle = twilio_circle_code(live.get("carrier", "")) or \
                circle_code(row["location"] or "")
            circles[circle] += 1
        outcomes[live_outcome(live, "error" not in live)] += 1
        samples.append(row)

    mobile = sum(counts.values())
    top = counts.most_common(1)
    majority = top[0][0] if top and top[0][1] * 2 > mobile and top[0][0] else ""
    circle = circles.most_common(1)[0][0] if circles else ""
    result: dict[str, Any] = {
        "prefix": prefix,
        "samples": samples,
        "counts": dict(counts),
        "outcomes": dict(outcomes),
        "majority": majority,
        "circle": circle,
        "suggested_row": None,
    }
    if majority:
        result["suggested_row"] = {
            "prefix": prefix,
            "operator": majority,
            "circle": circle,
            "source": "twilio",
            "updated": _today(),
            "note": block_note(prefix, counts, mobile),
        }
    return result


def probe_block(prefix: str, count: int, twilio: Credentials,
                cache: dict[str, Live], refresh: bool) -> dict[str, Any]:
    """Sample a block over the live API and infer its current operator."""
    pairs = [(n, cached_twilio_lookup(n, twilio, cache, refresh))
             for n in block_sample_numbers(prefix, count)]
    return aggregate_block(prefix, pairs)


def blocks_to_refresh(low: int, high: int) -> list[str]:
    """5-digit mobile blocks in [low, high] a live probe can fill or correct.

    Keeps blocks with no operator (gaps) or a closed one (stale) and skips those
    already tied to a current operator or non-mobile ranges, so a sweep spends
    calls only where live data adds something.
    """
    dead = {v for k, v in c.IN_FORMER_OPERATORS.items() if k != "RingCentral"}
    stale, gaps = [], []
    for block in range(low, high + 1):
        result = lookup(f"91{block}50000")
        if not result.get("valid") or result.get("line_type") != "mobile":
            continue
        carrier = result.get("current_carrier") or result.get("carrier") or ""
        if carrier in dead:  # closed operator: reliably ported, high value
            stale.append(str(block))
        elif not carrier:  # gap: often unallocated, so probe these last
            gaps.append(str(block))
    return stale + gaps


def billed_lookup(e164: str, twilio: Credentials, cache: dict[str, Live],
                  refresh: bool, fields: str, budget: Budget) -> Live:
    """Cached lookup that counts billed calls and enforces budget['max'].

    A cache hit is free; a real call increments budget['calls'] and raises
    BudgetExceeded before exceeding the cap, so a sweep stops without overspending
    and resumes later from the cache.
    """
    cached = cache.get(e164)
    if not refresh and cached and _covers(cached, fields):
        return cached
    if budget["max"] is not None and budget["calls"] >= budget["max"]:
        raise BudgetExceeded
    result = twilio_lookup(e164, twilio[0], twilio[1], fields)
    budget["calls"] += 1
    if "error" not in result:
        cache[e164] = {**result, "fetched_at": _today()}
    return result


def sweep_blocks(prefixes: list[str], samples: int, twilio: Credentials,
                 cache: dict[str, Live], refresh: bool, fields: str,
                 max_calls: int | None,
                 save: Callable[[dict[str, Live]], None],
                 ) -> tuple[list[dict[str, Any]], int, bool]:
    """Triage-probe many blocks within a billed-call budget, saving as it goes.

    Each block is checked with one number first; only blocks whose first sample
    is a live mobile line get the remaining samples, so dead blocks cost one call
    instead of `samples`. The cache is saved every block, so an interrupted or
    capped run resumes without re-billing. Returns (results, billed, hit_cap).
    """
    budget: Budget = {"calls": 0, "max": max_calls}
    results: list[dict[str, Any]] = []
    hit_cap = False
    try:
        for prefix in prefixes:
            pairs: list[tuple[str, Live]] = []
            for i, number in enumerate(block_sample_numbers(prefix, samples)):
                live = billed_lookup(number, twilio, cache, refresh, fields, budget)
                pairs.append((number, live))
                if i == 0 and not is_live_mobile(live):
                    break  # triage: do not spend more on a dead/landline block
            results.append(aggregate_block(prefix, pairs))
            save(cache)
    except BudgetExceeded:
        hit_cap = True
        save(cache)
    return results, budget["calls"], hit_cap


def append_twilio_checks(samples: list[Sample]) -> None:
    """Record raw per-number probe rows in data/twilio_checks.csv, idempotently.

    Keyed by number so re-running a (cached, unbilled) probe refreshes the row
    instead of duplicating it. These are synthetic block numbers, safe to commit.
    """
    rows: dict[str, Sample] = {}
    try:
        with c.TWILIO_CHECKS_CSV.open(encoding="utf-8", newline="") as fh:
            rows = {r["number"]: r for r in csv.DictReader(fh)}
    except FileNotFoundError:
        pass
    for sample in samples:
        rows[sample["number"]] = {"checked": _today(),
                                  **{k: sample.get(k) for k in c.TWILIO_CHECKS_FIELDS
                                     if k != "checked"}}
    with c.TWILIO_CHECKS_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(c.TWILIO_CHECKS_FIELDS),
                                extrasaction="ignore")
        writer.writeheader()
        for number in sorted(rows):
            writer.writerow(rows[number])


def save_suggested_rows(rows: list[Row]) -> None:
    """Merge suggested block rows into data/twilio_suggested.csv, keyed by prefix.

    This file has the in_mobile_blocks.csv schema, so a sweep leaves a ready
    candidate set to review and merge; keyed by prefix so re-runs refresh rows.
    """
    merged: dict[str, Row] = {}
    try:
        with c.SUGGESTED_CSV.open(encoding="utf-8", newline="") as fh:
            merged = {r["prefix"]: r for r in csv.DictReader(fh)}
    except FileNotFoundError:
        pass
    for row in rows:
        merged[row["prefix"]] = row
    with c.SUGGESTED_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(c.SUGGESTED_FIELDS),
                                extrasaction="ignore")
        writer.writeheader()
        for prefix in sorted(merged):
            writer.writerow(merged[prefix])
