#!/usr/bin/env python3
"""Check Indian 5-digit mobile blocks against an online lookup API.

Usage: check_blocks.py [--provider numverify|veriphone] PREFIX_OR_BLOCK...
  e.g. check_blocks.py 8317                       (blocks 83170 ... 83179)
       check_blocks.py --provider veriphone 88280 77451

One request per block, 2 s apart; both free plans are small, so check a
single block per prefix first and only expand when it disagrees. Needs
NUMVERIFY_KEY or VERIPHONE_KEY in the environment or .env. Responses are
appended to data/<provider>_checks.csv next to the offline answer, so
disagreements can be reviewed and copied into data/in_mobile_blocks.csv by
hand. Blocks already checked with that provider are skipped, and failed
requests are not saved.

Only the 5-digit block matters to these sources, so the rest of the number
is a fixed made-up suffix, not anyone's real number.
"""

import argparse
import csv
import json
import sys
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import phonelookup  # noqa: E402

VERIPHONE_URL = "https://api.veriphone.io/v2/verify"
# Free plans reject bursts ("maximum rate limitation"); space requests.
PAUSE_SECONDS = 2
RETRIES = 3
# Made-up subscriber digits: only the block matters to these sources.
SUFFIX = "12345"
FIELDS = ["checked", "number", "block", "valid", "carrier", "location",
          "line_type", "offline_carrier", "offline_location", "offline_source",
          "agree_carrier", "agree_location", "response"]


def veriphone(number: str, key: str) -> dict:
    """Call Veriphone and rename its fields to numverify's.

    Returns {"error": ...} on failure, like phonelookup.numverify, and keeps
    the original response under "raw".
    """
    query = urlencode({"key": key, "phone": "+" + number})
    try:
        with urlopen(f"{VERIPHONE_URL}?{query}", timeout=10) as resp:
            body = json.load(resp)
    except HTTPError as err:  # the reason is in the JSON body
        try:
            body = json.load(err)
        except ValueError:
            return {"error": f"request failed: {err}"}
    except (URLError, TimeoutError, ValueError) as err:
        return {"error": f"request failed: {err}"}
    if body.get("status") != "success":
        return {"error": body.get("message") or body.get("type") or "unknown error"}
    return {
        "valid": body.get("phone_valid"),
        "carrier": body.get("carrier", ""),
        "location": body.get("phone_region", ""),
        "line_type": body.get("phone_type", ""),
        "raw": body,
    }


PROVIDERS = {
    "numverify": ("NUMVERIFY_KEY", phonelookup.numverify),
    "veriphone": ("VERIPHONE_KEY", veriphone),
}


def check(number: str, key: str, query) -> dict:
    """Query one provider for a number and pair it with the offline lookup."""
    ours = phonelookup.lookup(number)
    for attempt in range(RETRIES):
        time.sleep(PAUSE_SECONDS * (attempt + 1))
        theirs = query(number, key)
        if "rate limit" not in str(theirs.get("error", "")).lower():
            break
    agree = phonelookup.agreement(ours, theirs) if "error" not in theirs else {}
    return {
        "checked": date.today().isoformat(),
        "number": number,
        "block": number[2:7],
        "valid": theirs.get("valid", ""),
        "carrier": theirs.get("carrier", ""),
        "location": theirs.get("location", ""),
        "line_type": theirs.get("line_type", ""),
        "offline_carrier": ours.get("carrier", ""),
        "offline_location": ours.get("location", ""),
        "offline_source": ours.get("series_source", ""),
        "agree_carrier": agree.get("carrier", ""),
        "agree_location": agree.get("location", ""),
        "response": json.dumps(theirs.get("raw", theirs), ensure_ascii=False,
                               sort_keys=True),
    }


def failed(row: dict) -> bool:
    """True when the saved response is an error rather than an answer."""
    return '"error"' in row["response"]


def checked_blocks(path: Path) -> set:
    """Blocks that already have a successful check, so reruns skip them."""
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            return {row["block"] for row in csv.DictReader(fh) if not failed(row)}
    except FileNotFoundError:
        return set()


def append_rows(path: Path, rows: list) -> None:
    """Append rows to a checks CSV, writing the header for a new file."""
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, FIELDS, lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerows(rows)


def blocks_from_args(args: list) -> list:
    """Expand 4-digit prefixes to their ten blocks; keep 5-digit blocks.

    Returns [] if any argument is not a 4- or 5-digit mobile prefix.
    """
    blocks = []
    for arg in args:
        if not (arg.isdigit() and len(arg) in (4, 5) and arg[0] in "6789"):
            return []
        blocks += [arg + d for d in "0123456789"] if len(arg) == 4 else [arg]
    return list(dict.fromkeys(blocks))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=PROVIDERS, default="numverify")
    parser.add_argument("blocks", nargs="+", help="4-digit prefixes or 5-digit blocks")
    args = parser.parse_args()
    blocks = blocks_from_args(args.blocks)
    if not blocks:
        parser.error("blocks must be 4- or 5-digit Indian mobile prefixes")
    env_name, query = PROVIDERS[args.provider]
    key = phonelookup.env_setting(env_name)
    if not key:
        print(f"needs {env_name} in the environment or .env", file=sys.stderr)
        return 2

    path = ROOT / "data" / f"{args.provider}_checks.csv"
    done = checked_blocks(path)
    todo = [block for block in blocks if block not in done]
    rows = []
    for block in todo:
        rows.append(check(f"91{block}{SUFFIX}", key, query))
        if failed(rows[-1]) and "rate limit" not in rows[-1]["response"].lower():
            break  # a bad key or unverified account fails every request
    append_rows(path, [row for row in rows if not failed(row)])
    for row in rows:
        if failed(row):
            flag = "  <-- request failed, not saved"
        elif row["agree_carrier"] and row["agree_location"]:
            flag = ""
        else:
            flag = "  <-- differs"
        print(f"{row['block']}  {args.provider}: {row['carrier'] or row['response']} | "
              f"{row['location']}   offline: {row['offline_carrier']} | "
              f"{row['offline_location']} ({row['offline_source']}){flag}")
    saved = sum(not failed(row) for row in rows)
    print(f"skipped {len(blocks) - len(todo)} already checked; saved {saved} to "
          f"{path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
