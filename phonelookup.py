#!/usr/bin/env python3
"""Offline phone number lookup, numverify-style output.

Usage:
  phonelookup.py 917904XXXXXX +1650XXXXXXX ...
  phonelookup.py --file numbers.txt      (one number per line)
  echo 9180XXXXXXXX | phonelookup.py     (reads stdin when no args)
  phonelookup.py --dork 919886XXXXXX     (print a Google search string)
  phonelookup.py --numverify 919886XXXXXX  (also call numverify; needs
                                            NUMVERIFY_KEY in env or .env)
  phonelookup.py --live 919886XXXXXX       (also call Twilio Lookup for live
                                            HLR carrier; needs TWILIO_ACCOUNT_SID
                                            and TWILIO_AUTH_TOKEN in env or .env)
  phonelookup.py --live --line-status 919886XXXXXX  (add live reachability)
  phonelookup.py --probe-block 83170 ...   (sample a few numbers per block via
                                            Twilio to infer its current operator)

Numbers without a leading + are treated as including the country code.
"""

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType, carrier, geocoder

ROOT = Path(__file__).resolve().parent
SERIES_CSV = ROOT / "data" / "in_mobile_series.csv"
BLOCKS_CSV = ROOT / "data" / "in_mobile_blocks.csv"
MSC_CSV = ROOT / "data" / "in_mobile_msc.csv"
LIBPN_CSV = ROOT / "data" / "in_libphonenumber_history.csv"
COAI_CSV = ROOT / "data" / "coai_msc.csv"
LEVELS2011_CSV = ROOT / "data" / "in_mobile_levels_2011.csv"
# Dated histories of the two 4-digit sources (scripts/series_history.py).
SERIES_HISTORY_CSV = {
    "wikipedia": ROOT / "data" / "wiki_series_history.csv",
    "in-mob-prefix": ROOT / "data" / "in_mob_prefix_history.csv",
}
# The numverify free plan only supports plain HTTP; paid plans can set
# NUMVERIFY_URL=https://apilayer.net/api/validate
NUMVERIFY_URL = "http://apilayer.net/api/validate"

# Twilio Lookup v2. --live appends the phone number as a path segment.
# line_type_intelligence is the HLR-backed field: current carrier name,
# line type, and the serving MCC/MNC (which exposes real MNP porting).
TWILIO_LOOKUP_URL = "https://lookups.twilio.com/v2/PhoneNumbers"

# --live results are cached here to avoid paying for repeat lookups.
# This file holds specific real numbers people queried, so it is NOT data
# to publish: it stays git-ignored, the same as .env.
LIVE_CACHE = ROOT / "live_cache.json"

# Raw per-number log of --probe-block samples (synthetic block numbers, not
# real subscribers), mirroring data/numverify_checks.csv. Safe to commit.
TWILIO_CHECKS_CSV = ROOT / "data" / "twilio_checks.csv"
# Derived block rows a probe/sweep suggests, in in_mobile_blocks.csv schema.
SUGGESTED_CSV = ROOT / "data" / "twilio_suggested.csv"

LINE_TYPES = {
    PhoneNumberType.MOBILE: "mobile",
    PhoneNumberType.FIXED_LINE: "landline",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "landline_or_mobile",
    PhoneNumberType.TOLL_FREE: "toll_free",
    PhoneNumberType.PREMIUM_RATE: "premium_rate",
    PhoneNumberType.SHARED_COST: "shared_cost",
    PhoneNumberType.VOIP: "voip",
    PhoneNumberType.PERSONAL_NUMBER: "personal_number",
    PhoneNumberType.PAGER: "pager",
    PhoneNumberType.UAN: "uan",
    PhoneNumberType.VOICEMAIL: "voicemail",
}

IN_OPERATORS = {
    "AT": "Bharti Airtel",
    "RJ": "Reliance Jio",
    "VI": "Vodafone Idea (Vi)",
    "CG": "BSNL/MTNL",
}

# Licensees in old DoT letters that no longer run a mobile network. Their
# numbers were ported out or taken over, so they are never the final answer
# while a current-operator source has the prefix.
IN_FORMER_OPERATORS = {
    "Aircel": "Aircel (closed 2018)",
    "Dishnet": "Aircel/Dishnet (closed 2018)",
    "RCom": "Reliance Communications (closed 2017)",
    "MTS": "MTS/Sistema (merged into RCom 2017)",
    "Tata": "Tata Teleservices (merged into Airtel 2019)",
    "Uninor": "Uninor/Telenor (merged into Airtel 2018)",
    "Videocon": "Videocon (closed 2016)",
    "Loop": "Loop Mobile (closed 2014)",
    "BPL": "BPL Mobile (merged ~2008)",
    "S Tel": "S Tel (closed 2012)",
    "Etisalat": "Etisalat DB (closed 2012)",
    "Allianze": "Allianz Infratech (licence cancelled 2012)",
    "HFCL": "HFCL/Quadrant (closed 2016)",
    "BTA Cellcom": "BTA Cellcom",
    "RingCentral": "RingCentral (internet telephony)",
}

IN_CIRCLES = {
    "AP": "Andhra Pradesh & Telangana",
    "AS": "Assam",
    "BR": "Bihar & Jharkhand",
    "DL": "Delhi",
    "GJ": "Gujarat",
    "HP": "Himachal Pradesh",
    "HR": "Haryana",
    "JK": "Jammu & Kashmir",
    "KA": "Karnataka",
    "KL": "Kerala",
    "MH": "Maharashtra & Goa",
    "MP": "Madhya Pradesh & Chhattisgarh",
    "NE": "North East",
    "OR": "Odisha",
    "PB": "Punjab",
    "RJ": "Rajasthan",
    "TN": "Tamil Nadu",
    "UE": "Uttar Pradesh (East)",
    "UW": "Uttar Pradesh (West)",
    "UP": "Uttar Pradesh",
    "WB": "West Bengal",
    "MU": "Mumbai",
    "KO": "Kolkata",
    "CH": "Chennai",
}


def expand_codes(codes: str, names: dict) -> str:
    """Spell out short codes such as 'BR/WB'.

    The series table stores operator and circle as 2-letter codes, with a
    slash where DoT split a 4-digit block between circles.
    """
    return " / ".join(names[c] for c in codes.split("/") if c in names)


def read_table(path: Path, key: str) -> dict:
    """Map each row's `key` column to the whole row.

    A missing file yields an empty table so the tool still works on
    libphonenumber data alone.
    """
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            return {row[key]: row for row in csv.DictReader(fh)}
    except FileNotFoundError:
        return {}


@lru_cache(maxsize=1)
def series_table() -> dict:
    """4-digit prefix -> DoT allocation row. Cached: the CSV never changes
    while the process runs."""
    return read_table(SERIES_CSV, "series")


@lru_cache(maxsize=1)
def block_table() -> dict:
    """4- or 5-digit prefix -> newer row (a DoT letter or a live check) that
    supersedes the series table."""
    return read_table(BLOCKS_CSV, "prefix")


@lru_cache(maxsize=1)
def msc_table() -> dict:
    """5-digit block -> every DoT letter row for it, oldest first.

    Unlike the other tables a block can have many rows: DoT reuses blocks,
    and corrigenda move them between operators and circles.
    """
    table = {}
    try:
        with MSC_CSV.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                table.setdefault(row["block"], []).append(row)
    except FileNotFoundError:
        return {}
    for rows in table.values():
        rows.sort(key=lambda row: row["date"])
    return table


def series_entry(row: dict) -> dict:
    """Spell out one series or blocks-file row as a history entry."""
    return {
        "carrier": expand_codes(row["operator"], IN_OPERATORS),
        "location": expand_codes(row["circle"], IN_CIRCLES),
        "source": row["source"],
        "updated": row.get("updated", ""),
    }


def msc_entry(row: dict) -> dict:
    """Spell out one DoT letter row as a history entry."""
    code = row["operator"]
    return {
        "carrier": IN_OPERATORS.get(code) or IN_FORMER_OPERATORS.get(code, code),
        "location": expand_codes(row["circle"], IN_CIRCLES),
        "source": "dot.gov.in",
        "updated": row["date"],
        "kind": row["kind"],
        "letter": row["letter"],
    }


@lru_cache(maxsize=1)
def twilio_table() -> dict:
    """5-digit block -> Twilio HLR row (data/twilio_suggested.csv).

    These are live current-carrier observations, treated as ground truth for
    who holds a block now; the allocation sources stay in history.
    """
    return read_table(SUGGESTED_CSV, "prefix")


def twilio_entry(row: dict) -> dict:
    """Spell out a Twilio suggested-block row as a history entry.

    Dated today and marked "current" so it sorts last and becomes the live
    answer, above every allocation source.
    """
    return {
        "carrier": operator_name(row["operator"]),
        "location": IN_CIRCLES.get(row["circle"], ""),
        "source": "twilio",
        "updated": row.get("updated", ""),
        "kind": "current",
        "note": row.get("note", ""),
    }


def is_current(entry: dict) -> bool:
    """True when an entry names an operator that still runs a network."""
    return (entry.get("kind") not in ("withdrawal", "removed", "superseded")
            and entry["carrier"] in IN_OPERATORS.values())


# Every spelling libphonenumber has used for an Indian carrier since 2013,
# mapped to the operator codes used elsewhere.
LIBPN_OPERATORS = {
    "Airtel": "AT", "AirTel": "AT", "AIRTEL": "AT", "Hexacom": "AT",
    "Bharti Hexacom": "AT",
    "Reliance Jio": "RJ",
    "Idea": "VI", "IDEA": "VI", "Idea Cellular Ltd": "VI", "Vodafone": "VI",
    "Vodafone IN": "VI", "VODAFONE": "VI",
    "CellOne": "CG", "Cellone": "CG", "BSNL MOBILE": "CG", "BSNL": "CG",
    "BSNL Mobile": "CG", "MTNL": "CG", "DOLPHIN": "CG",
    "Reliance": "RCom", "RELIANCE": "RCom",
    "Aircel": "Aircel", "AIRCEL": "Aircel",
    "Dishnet": "Dishnet", "Dishnet Wireless": "Dishnet",
    "Tata Docomo": "Tata", "TATA DOCOMO": "Tata", "TATA": "Tata", "Tata": "Tata",
    "Telewings": "Uninor", "Telenor": "Uninor", "Uninor": "Uninor", "UNITECH": "Uninor",
    "Sistema": "MTS", "SISTEMA": "MTS",
    "Videocon": "Videocon", "VIDEOCON": "Videocon", "Videocon Datacom": "Videocon",
    "Loop Mobile": "Loop",
    "ETISALAT": "Etisalat", "Etisalat DB(cheers)": "Etisalat",
    "S TEL": "S Tel", "S Tel": "S Tel",
}


def operator_name(code: str) -> str:
    """Spell out an operator code, current or closed."""
    return IN_OPERATORS.get(code) or IN_FORMER_OPERATORS.get(code, code)


# Twilio Lookup returns freeform carrier strings such as "Airtel India -
# Tamil Nadu (94) (Bharti Airtel)" or "Reliance (JIO) - West Bengal", so
# these are matched as case-insensitive substrings, not exact keys.
TWILIO_OPERATORS = (
    ("jio", "RJ"),
    ("airtel", "AT"),
    ("bharti", "AT"),
    ("vodafone", "VI"),
    ("idea", "VI"),
    ("bsnl", "CG"),
    ("mtnl", "CG"),
)


def twilio_operator_code(carrier_name: str) -> str:
    """Map a Twilio carrier string to our operator code, or "" if unknown."""
    text = (carrier_name or "").lower()
    for needle, code in TWILIO_OPERATORS:
        if needle in text:
            return code
    return ""


@lru_cache(maxsize=1)
def circle_by_name() -> dict:
    """Reverse of IN_CIRCLES: full circle name (lower-case) -> code."""
    return {name.lower(): code for code, name in IN_CIRCLES.items()}


def circle_code(location: str) -> str:
    """Map an offline location name to a circle code, or "" if unknown."""
    return circle_by_name().get((location or "").lower(), "")


@lru_cache(maxsize=1)
def circle_by_normalized() -> dict:
    """IN_CIRCLES keyed by normalized name, so "Uttar Pradesh (West)" and
    Twilio's "Uttar Pradesh West" both resolve to UW."""
    return {normalized(name): code for code, name in IN_CIRCLES.items()}


def twilio_circle_code(carrier_name: str) -> str:
    """Pull a circle code out of a Twilio carrier string, or "" if none.

    Twilio writes the circle after " - ", e.g. "Reliance (JIO) - Uttar Pradesh
    West" or "Airtel India - Tamil Nadu (94) (Bharti Airtel)"; the trailing
    parenthetical (network code or legal name) is dropped before matching.
    """
    text = carrier_name or ""
    if " - " not in text:
        return ""
    region = text.split(" - ", 1)[1].split(" (")[0]
    return circle_by_normalized().get(normalized(region), "")


@lru_cache(maxsize=1)
def libpn_table() -> dict:
    """Prefix -> libphonenumber carrier periods (since/until dates), built
    from its git history by scripts/libphonenumber_history.py."""
    table = {}
    try:
        with LIBPN_CSV.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                table.setdefault(row["prefix"], []).append(row)
    except FileNotFoundError:
        return {}
    return table


def libphonenumber_entries(national: str) -> list:
    """Return dated entries for each change in libphonenumber's carrier for
    this number.

    libphonenumber uses the longest prefix it lists, and its prefixes went
    from 4 to 5 digits over the years, so the carrier on each date is the
    longest period active then. An entry is added only when the operator
    changes (spelling changes are ignored). A prefix dropped from the data
    gives a "removed" entry, which is never the answer. No circle.
    """
    table = libpn_table()
    periods = [row for n in range(1, len(national) + 1)
               for row in table.get(national[:n], [])]
    days = sorted({row["since"] for row in periods} | {row["until"] for row in periods} - {""})
    entries, previous = [], None
    for day in days:
        active = [row for row in periods
                  if row["since"] <= day and (not row["until"] or day < row["until"])]
        row = max(active, key=lambda r: len(r["prefix"])) if active else None
        code = LIBPN_OPERATORS.get(row["carrier"], row["carrier"]) if row else None
        if code == previous:
            continue
        if row:
            entries.append({"carrier": operator_name(code), "location": "",
                            "source": "libphonenumber", "updated": day,
                            "kind": "listed", "prefix": row["prefix"],
                            "commit": row["since_commit"] if row["since"] == day
                            else row["until_commit"]})
        elif previous:
            entries.append({"carrier": operator_name(previous), "location": "",
                            "source": "libphonenumber", "updated": day,
                            "kind": "removed", "prefix": "", "commit": ""})
        previous = code
    return entries


@lru_cache(maxsize=None)
def series_history(source: str) -> dict:
    """Prefix -> dated (operator, circle) periods for a 4-digit source."""
    path = SERIES_HISTORY_CSV.get(source)
    table = {}
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                table.setdefault(row["prefix"], []).append(row)
    except (AttributeError, FileNotFoundError):
        return {}
    return table


def operator_names(codes: str) -> str:
    """Spell out "AT/Aircel"-style operator codes, current or closed."""
    return " / ".join(operator_name(code) for code in codes.split("/") if code)


def series_entries(series: dict) -> list:
    """The 4-digit row as history: its source's earlier values, then the
    current one dated from when that value first appeared.

    Earlier values are "superseded" and never the answer. Without a
    history file the row keeps its fetch date.
    """
    current = series_entry(series)
    earlier = []
    for period in series_history(series["source"]).get(series["series"], []):
        if not period["until"]:
            current["updated"] = period["since"]
            continue
        earlier.append({"carrier": operator_names(period["operator"]),
                        "location": expand_codes(period["circle"], IN_CIRCLES),
                        "source": series["source"], "updated": period["since"],
                        "kind": "superseded", "until": period["until"]})
    return earlier + [current]


def extra_series_history(prefix: str, chosen: str) -> list:
    """Dated periods for a 4-digit prefix from every series-history source
    except the one the merged series row already uses.

    Both Wikipedia and in-mob-prefix are tracked by commit, but the merged
    series table keeps one source per prefix, so the other source's history
    would never show. These entries are informational (an ended period is
    "superseded", a still-current one "listed"); the chosen source stays
    the baseline answer.
    """
    entries = []
    for source in SERIES_HISTORY_CSV:
        if source == chosen:
            continue
        for period in series_history(source).get(prefix, []):
            entries.append({
                "carrier": operator_names(period["operator"]),
                "location": expand_codes(period["circle"], IN_CIRCLES),
                "source": source, "updated": period["since"],
                "kind": "superseded" if period["until"] else "listed",
                "until": period["until"],
            })
    entries.sort(key=lambda e: e["updated"])
    return entries


@lru_cache(maxsize=1)
def coai_table() -> dict:
    """5-digit block -> COAI's metro-circle MSC listing (undated, ~2016-17)."""
    return read_table(COAI_CSV, "block")


def coai_entry(row: dict) -> dict:
    """Spell out a COAI row as an undated history entry."""
    return {"carrier": operator_name(row["operator"]),
            "location": expand_codes(row["circle"], IN_CIRCLES),
            "source": "coai.com", "updated": "", "kind": "listed"}


@lru_cache(maxsize=1)
def levels2011_table() -> dict:
    """4- or 5-digit level -> the c.2011 DoT "MSC levels" consolidated list.

    A Scribd scan of DoT's all-India "LIST OF MSC & SP CODES ALLOTTED TO
    ALL" (scripts/parse_levels_2011.py). Undated and stale: every operator
    on it has since merged or closed, so it is the least-trusted baseline,
    used mainly for a block's circle when no better source has it.
    """
    return read_table(LEVELS2011_CSV, "level")


def levels2011_entry(row: dict) -> dict:
    """Spell out a c.2011 levels-list row as an undated history entry."""
    return {"carrier": operator_name(row["operator"]),
            "location": expand_codes(row["circle"], IN_CIRCLES),
            "source": "scribd-2011", "updated": "", "kind": "listed"}


def india_mobile_history(national: str) -> list:
    """Return what the sources know about a 10-digit Indian mobile, with
    the entry to trust last.

    Dated entries (DoT letters, libphonenumber's git history, blocks-file
    rows) are sorted by date, so a reused or corrected block ends on its
    newest owner. Undated or coarse entries go first as the baseline
    whatever their date: the c.2011 Scribd levels list (stalest, least
    trusted), then both 4-digit git sources (Wikipedia and in-mob-prefix,
    with their earlier values, oldest first), then COAI's undated 5-digit
    metro listing, or last when the newest dated entry is a closed operator, a
    withdrawal or a removal and the series row names a current operator,
    because it names who serves those numbers now.

    Returns [] when the number is not a mobile or no source has it.
    """
    if len(national) != 10 or national[0] not in "6789":
        return []
    blocks = block_table()
    dated = [msc_entry(row) for row in msc_table().get(national[:5], [])]
    dated += libphonenumber_entries(national)
    dated += [series_entry(row)
              for row in (blocks.get(national[:4]), blocks.get(national[:5])) if row]
    twilio = twilio_table().get(national[:5])
    if twilio:  # live ground truth, dated today: sorts last as the answer
        dated.append(twilio_entry(twilio))
    dated.sort(key=lambda entry: entry["updated"])
    series = series_table().get(national[:4])
    undated = []
    if series:
        undated += extra_series_history(national[:4], series["source"])
        undated += series_entries(series)
    levels = levels2011_table()
    old = levels.get(national[:5]) or levels.get(national[:4])
    if old:  # oldest and stalest, so it is the least-trusted baseline
        undated.insert(0, levels2011_entry(old))
    coai = coai_table().get(national[:5])
    if coai:  # 5-digit, so it outranks the 4-digit row
        undated.append(coai_entry(coai))
    if dated and not is_current(dated[-1]) and any(map(is_current, undated)):
        # Keep the order, but end on a current operator: a closed one in an
        # undated source must not become the answer over a current one.
        return (dated + [e for e in undated if not is_current(e)]
                + [e for e in undated if is_current(e)])
    return undated + dated


def latest_location(history: list) -> str:
    """The newest circle given for the answer's operator, or "".

    libphonenumber names a carrier but no circle; another source that
    names the same operator supplies it. A circle from a different
    operator's allocation is not used.
    """
    answer = history[-1]
    for entry in reversed(history):
        if entry["carrier"] == answer["carrier"] and entry["location"] \
                and entry.get("kind") not in ("withdrawal", "removed", "superseded"):
            return entry["location"]
    return ""


def india_overrides(result: dict, national: str) -> dict:
    """Return the fields that replace libphonenumber's answer for India.

    The sources are more specific than libphonenumber's geocoder, which
    reads 7x/8x mobiles as STD landlines; so when the chosen entry has no
    circle the location is just the country. The newest entry wins; when
    sources differ, all of them are kept under "history".

    `carrier` is the original DoT allocation. After mobile number
    portability (MNP) the subscriber may have moved to another operator
    without changing the number, so `current_carrier` is returned as null:
    the live operator is only knowable from an HLR / number-portability
    lookup, which this offline tool does not do.
    """
    history = india_mobile_history(national)
    if history:
        latest = history[-1]
        from_twilio = latest.get("source") == "twilio"
        fields = {
            "line_type": "mobile",
            "location": latest_location(history) or result["country_name"],
            "carrier": latest["carrier"] or result["carrier"],
            "current_carrier": latest["carrier"] if from_twilio else None,
            "carrier_note": ("current carrier from a Twilio HLR sample (ground "
                             "truth); see history for the DoT allocation"
                             if from_twilio
                             else "allocation; current may differ (MNP)"),
            "series_source": latest["source"],
            "updated": latest["updated"],
        }
        if len(history) > 1:
            fields["history"] = history
        return fields
    if result["line_type"] == "mobile":
        return {"note": unallocated_note(national)}
    if result["line_type"] == "landline_or_mobile":
        return {"location": result["country_name"]}
    return {}


def unallocated_note(national: str) -> str:
    """Explain a valid mobile number that no source gives an operator.

    Likely unallocated: the 6x series (opened 2017) and 71xx (first
    letters 2026), and 4-digit prefixes where no block has any source.
    Many of those start with a city's STD code (8161 = 0816 Tumkur, 8321 =
    0832 Panaji); numverify reads them as landlines and Veriphone has no
    carrier (checked 2026-11-06/07).
    """
    whole_prefix_empty = not any(
        india_mobile_history(national[:4] + digit + national[5:])
        for digit in "0123456789")
    if national[0] == "6" or national[:2] == "71" or whole_prefix_empty:
        return ("no operator in DoT letters, libphonenumber or numverify; "
                "this block is probably not allocated yet")
    return "no operator known for this block"


def parse_number(raw: str) -> phonenumbers.PhoneNumber:
    """Parse a number that already includes its country code.

    Users paste numbers like 91XXXXXXXXXX without the '+'. Adding it stops
    libphonenumber guessing a region from the leading digits.
    """
    text = raw.strip()
    return phonenumbers.parse(text if text.startswith("+") else "+" + text, None)


def lookup(raw: str) -> dict:
    """Return numverify-style facts about one number, worked out offline."""
    digits = raw.strip()
    try:
        num = parse_number(digits)
    except phonenumbers.NumberParseException as err:
        return {"valid": False, "number": digits, "error": str(err)}

    if not phonenumbers.is_valid_number(num):
        return {"valid": False, "number": digits}

    region = phonenumbers.region_code_for_number(num)
    national = str(num.national_number)
    result = {
        "valid": True,
        "number": f"{num.country_code}{national}",
        "local_format": "".join(
            c for c in phonenumbers.format_number(num, PhoneNumberFormat.NATIONAL)
            if c.isdigit()
        ),
        "international_format": phonenumbers.format_number(num, PhoneNumberFormat.E164),
        "country_prefix": f"+{num.country_code}",
        "country_code": region,
        "country_name": geocoder.country_name_for_number(num, "en"),
        "location": geocoder.description_for_number(num, "en"),
        "carrier": carrier.name_for_number(num, "en"),
        "line_type": LINE_TYPES.get(phonenumbers.number_type(num), "unknown"),
    }
    if region == "IN":
        return {**result, **india_overrides(result, national)}
    return result


def env_setting(name: str) -> str:
    """Read a setting from the environment, falling back to ./.env.

    Lets users keep the API key in a git-ignored file instead of their
    shell history.
    """
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("'\"")
    except FileNotFoundError:
        pass
    return ""


def numverify(number: str, key: str) -> dict:
    """Call numverify's validate endpoint.

    Failures come back as {"error": ...} so one bad request does not stop
    a batch of lookups.
    """
    url = env_setting("NUMVERIFY_URL") or NUMVERIFY_URL
    query = urlencode({"access_key": key, "number": number})
    try:
        with urlopen(f"{url}?{query}", timeout=10) as resp:
            body = json.load(resp)
    except HTTPError as err:  # apilayer puts the reason in the JSON body
        try:
            body = json.load(err)
        except ValueError:
            return {"error": f"request failed: {err}"}
    except (URLError, TimeoutError, ValueError) as err:
        return {"error": f"request failed: {err}"}
    if body.get("success") is False:
        error = body.get("error", {})
        return {"error": error.get("info") or error.get("type") or "unknown error"}
    return body


LTI_FIELD = "line_type_intelligence"
LINE_STATUS_FIELD = "line_status"
TWILIO_RETRIES = 4  # attempts per lookup before giving up (429/5xx backoff)


def twilio_lookup(e164: str, sid: str, token: str,
                  fields: str = LTI_FIELD) -> dict:
    """Call Twilio Lookup v2 for one E.164 number (HLR-backed carrier data).

    `fields` is Twilio's comma-separated package list; the result is flattened
    to the number facts we use. line_status, when asked for and licensed on
    the account, adds whether the line is currently active/reachable.
    Returns {"error": ...} so one bad request does not stop a batch; the
    credentials are HTTP Basic auth and are never logged.
    """
    url = env_setting("TWILIO_LOOKUP_URL") or TWILIO_LOOKUP_URL
    query = urlencode({"Fields": fields})
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    request = Request(
        f"{url}/{quote_plus(e164)}?{query}",
        headers={"Authorization": f"Basic {auth}"},
    )
    # A long sweep gets rate-limited (429) and transient 5xx/timeouts; back off
    # and retry a few times so throttling slows the run instead of blanking it.
    for attempt in range(TWILIO_RETRIES):
        try:
            with urlopen(request, timeout=10) as resp:
                body = json.load(resp)
            break
        except HTTPError as err:
            if err.code in (429, 500, 502, 503, 504) and attempt < TWILIO_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            try:
                detail = json.load(err)
            except ValueError:
                return {"error": f"request failed: {err}"}
            return {"error": detail.get("message") or f"request failed: {err}"}
        except (URLError, TimeoutError, ValueError) as err:
            if attempt < TWILIO_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            return {"error": f"request failed: {err}"}

    lti = body.get("line_type_intelligence") or {}
    result = {
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
    if LINE_STATUS_FIELD in fields:
        result["line_status"] = twilio_line_status(body)
    return result


def twilio_line_status(body: dict) -> dict:
    """Flatten a Lookup v2 line_status block, or an error note if absent.

    The field is gated, so Twilio may return it as null or with an error_code
    even on a 200; record that instead of silently dropping it.
    """
    status = body.get("line_status")
    if not status:
        return {"error": "line_status not returned (not licensed/available)"}
    if status.get("error_code"):
        return {"error": f"line_status error_code {status['error_code']}"}
    return {"status": status.get("status")}


def live_cache_load() -> dict:
    """Read the git-ignored live-lookup cache, or {} if absent/unreadable."""
    try:
        return json.loads(LIVE_CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def live_cache_save(cache: dict) -> None:
    """Write the live-lookup cache back to disk (best effort)."""
    try:
        LIVE_CACHE.write_text(
            json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def cached_twilio_lookup(e164: str, twilio: tuple, cache: dict,
                         refresh: bool, fields: str = LTI_FIELD) -> dict:
    """Return a Twilio result for e164, from cache unless refresh is set.

    A fresh call is stored under the E.164 key with a fetched_at date, so a
    repeat run costs nothing. The cache is reused only when it already covers
    every requested field; asking for a new field (e.g. live_activity) forces
    a refetch. Errors are returned but not cached.
    """
    cached = cache.get(e164)
    if not refresh and cached and _covers(cached, fields):
        return cached
    result = twilio_lookup(e164, twilio[0], twilio[1], fields)
    if "error" not in result:
        result = {**result, "fetched_at": _today()}
        cache[e164] = result
    return result


def _covers(cached: dict, fields: str) -> bool:
    """True when a cached result already includes every requested field."""
    have = (cached.get("fields") or LTI_FIELD).split(",")
    return all(field in have for field in fields.split(","))


def _today() -> str:
    """Today's date as YYYY-MM-DD (for cache stamps and probe logs)."""
    return date.today().isoformat()


def block_sample_numbers(prefix: str, count: int) -> list:
    """Pick `count` E.164 numbers spread evenly across an Indian block.

    A block is the leading digits of the 10-digit national number; the rest
    is filled with suffixes at even offsets so the sample spans the range and
    is deterministic (a re-run reuses the cache instead of paying again).
    """
    suffix_len = 10 - len(prefix)
    span = 10 ** suffix_len
    numbers = []
    for i in range(count):
        suffix = int((i + 0.5) / count * span)
        numbers.append(f"+91{prefix}{suffix:0{suffix_len}d}")
    return numbers


def block_note(prefix: str, counts: Counter, total: int) -> str:
    """Describe a block sample for the CSV note, spelling out any split.

    HLR reports the current (possibly ported) carrier, so the note records
    this as current-holder evidence, not a DoT allocation.
    """
    parts = [f"{n}/{total} {operator_name(code) if code else 'unknown'}"
             for code, n in counts.most_common()]
    return (f"{total} numbers sampled via Twilio HLR ({'; '.join(parts)}); "
            "current-carrier evidence (MNP), not a DoT allocation")


def live_outcome(live: dict, ok: bool) -> str:
    """Classify one live result for the probe summary.

    Separates the reasons a sample does not count toward a mobile block:
    a failed request, an unallocated number, or a non-mobile line.
    """
    if not ok:
        return "error"
    if not live.get("valid") or not live.get("carrier"):
        return "absent"
    return live.get("line_type") or "unknown"


def is_live_mobile(live: dict) -> bool:
    """True when a live result is a reachable mobile line worth counting."""
    return ("error" not in live and bool(live.get("valid"))
            and live.get("line_type") == "mobile")


def sample_row(number: str, live: dict) -> dict:
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


def aggregate_block(prefix: str, pairs: list) -> dict:
    """Turn (number, live) pairs for one block into a probe result.

    Only live mobile lines vote for the operator; a majority (> half the
    mobile samples) yields a suggested row, otherwise it is inconclusive.
    """
    samples, counts, circles, outcomes = [], Counter(), Counter(), Counter()
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
    result = {
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


def probe_block(prefix: str, count: int, twilio: tuple, cache: dict,
                refresh: bool) -> dict:
    """Sample a block over the live API and infer its current operator."""
    pairs = [(n, cached_twilio_lookup(n, twilio, cache, refresh))
             for n in block_sample_numbers(prefix, count)]
    return aggregate_block(prefix, pairs)


class BudgetExceeded(Exception):
    """Raised to stop a sweep cleanly once the billed-call cap is reached."""


def blocks_to_refresh(low: int, high: int) -> list:
    """5-digit mobile blocks in [low, high] a live probe can fill or correct.

    Keeps blocks with no operator (gaps) or a closed operator (stale), and
    skips blocks already tied to a current operator and non-mobile ranges, so
    the sweep spends calls only where live data would add something.
    """
    dead = {v for k, v in IN_FORMER_OPERATORS.items() if k != "RingCentral"}
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


def billed_lookup(e164: str, twilio: tuple, cache: dict, refresh: bool,
                  fields: str, budget: dict) -> dict:
    """Cached lookup that counts billed calls and enforces budget['max'].

    A cache hit is free; a real API call increments budget['calls'] and
    raises BudgetExceeded before exceeding the cap, so a sweep stops without
    overspending and resumes later from the cache.
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


def sweep_blocks(prefixes: list, samples: int, twilio: tuple, cache: dict,
                 refresh: bool, fields: str, max_calls, save) -> tuple:
    """Triage-probe many blocks within a billed-call budget, saving as it goes.

    Each block is checked with one number first; only blocks whose first
    sample is a live mobile line get the remaining samples, so unallocated and
    landline blocks cost one call instead of `samples`. The cache is saved
    every block, so an interrupted or capped run resumes without re-billing.
    Returns (results, billed_calls, hit_cap).
    """
    budget = {"calls": 0, "max": max_calls}
    results = []
    hit_cap = False
    try:
        for prefix in prefixes:
            pairs = []
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


TWILIO_CHECKS_FIELDS = ["checked", "number", "live_carrier", "live_code",
                        "mcc", "mnc", "line_type", "offline_carrier",
                        "location", "error"]


def append_twilio_checks(samples: list) -> None:
    """Record raw per-number probe rows in data/twilio_checks.csv, idempotently.

    Keyed by number so re-running a (cached, unbilled) probe refreshes the row
    instead of duplicating it. These are synthetic block numbers, not real
    subscribers, so the log is safe to commit, mirroring numverify_checks.csv.
    """
    rows = {}
    try:
        with open(TWILIO_CHECKS_CSV, encoding="utf-8", newline="") as fh:
            rows = {r["number"]: r for r in csv.DictReader(fh)}
    except FileNotFoundError:
        pass
    for sample in samples:
        rows[sample["number"]] = {"checked": _today(),
                                  **{k: sample.get(k) for k in TWILIO_CHECKS_FIELDS
                                     if k != "checked"}}
    with open(TWILIO_CHECKS_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=TWILIO_CHECKS_FIELDS,
                                extrasaction="ignore")
        writer.writeheader()
        for number in sorted(rows):
            writer.writerow(rows[number])


SUGGESTED_FIELDS = ["prefix", "operator", "circle", "source", "updated", "note"]


def save_suggested_rows(rows: list) -> None:
    """Merge suggested block rows into data/twilio_suggested.csv, keyed by prefix.

    This file has the in_mobile_blocks.csv schema, so a sweep leaves a ready
    candidate set to review and merge. Keyed by prefix so resumes and re-runs
    refresh rows instead of duplicating them.
    """
    merged = {}
    try:
        with open(SUGGESTED_CSV, encoding="utf-8", newline="") as fh:
            merged = {r["prefix"]: r for r in csv.DictReader(fh)}
    except FileNotFoundError:
        pass
    for row in rows:
        merged[row["prefix"]] = row
    with open(SUGGESTED_CSV, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUGGESTED_FIELDS,
                                extrasaction="ignore")
        writer.writeheader()
        for prefix in sorted(merged):
            writer.writerow(merged[prefix])


def normalized(value) -> str:
    """Lower-cased words without punctuation, with None and "" alike.

    numverify writes "Uttar Pradesh East" where we write "Uttar Pradesh
    (East)"; both should compare equal.
    """
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))


def agreement(ours: dict, theirs: dict) -> dict:
    """Report which shared fields match between offline and numverify.

    Location matches when numverify's (often shorter) name appears in ours;
    carrier matches on the first word, since the two sources spell brand
    names differently ("Reliance Jio" vs "Reliance Jio Infocomm").
    """
    their_location = normalized(theirs.get("location"))
    their_carrier = normalized(theirs.get("carrier")).split()[:1]
    return {
        "valid": ours.get("valid") == theirs.get("valid"),
        "line_type": normalized(ours.get("line_type")) == normalized(theirs.get("line_type")),
        "location": bool(their_location)
        and their_location in normalized(ours.get("location")),
        "carrier": bool(their_carrier)
        and normalized(ours.get("carrier")).split()[:1] == their_carrier,
    }


# Search engines that accept a "a" OR "b" phrase query in a URL parameter.
SEARCH_ENGINES = {
    "Google": "https://www.google.com/search?q=",
    "Bing": "https://www.bing.com/search?q=",
    "DuckDuckGo": "https://duckduckgo.com/?q=",
    "Yandex": "https://yandex.com/search/?text=",
    "Brave": "https://search.brave.com/search?q=",
    "Startpage": "https://www.startpage.com/sp/search?query=",
    "Mojeek": "https://www.mojeek.com/search?q=",
}


def dork(raw: str) -> str:
    """Build a search query matching the common written forms of one number.

    The same number is written many ways online, so an exact-phrase search
    for one form misses most pages. The "a" OR "b" phrase syntax works on
    every engine in SEARCH_ENGINES.
    """
    num = parse_number(raw)
    cc, nat = str(num.country_code), str(num.national_number)
    forms = {
        nat,
        f"{cc}{nat}",
        f"+{cc}{nat}",
        f"+{cc}-{nat}",
        f"+{cc} {nat}",
        phonenumbers.format_number(num, PhoneNumberFormat.INTERNATIONAL),
        phonenumbers.format_number(num, PhoneNumberFormat.NATIONAL),
    }
    if cc == "91" and len(nat) == 10:
        forms.add(f"{nat[:5]} {nat[5:]}")
    elif cc == "1" and len(nat) == 10:
        forms.add(f"{nat[:3]}-{nat[3:6]}-{nat[6:]}")
    # Sort on the text too: sets have no order, and equal-length forms
    # would otherwise print in a different order on each run.
    return " OR ".join(f'"{f}"' for f in sorted(forms, key=lambda f: (len(f), f)))


def dork_urls(query: str) -> dict:
    """Map each search engine to its URL for the dork query."""
    return {name: base + quote_plus(query) for name, base in SEARCH_ENGINES.items()}


def build_parser() -> argparse.ArgumentParser:
    """Define the command-line flags."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("numbers", nargs="*")
    parser.add_argument("--file", help="file with one number per line")
    parser.add_argument("--pretty", action="store_true", help="indent JSON")
    parser.add_argument("--dork", action="store_true",
                        help="print a search string and a URL per search engine instead")
    parser.add_argument("--numverify", action="store_true",
                        help="also query numverify (uses 1 API request per number)")
    parser.add_argument("--live", action="store_true",
                        help="also query Twilio Lookup for live HLR carrier data "
                             "(needs TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN; "
                             "1 billed request per number; results cached locally)")
    parser.add_argument("--refresh", action="store_true",
                        help="with --live, ignore the cache and re-query Twilio")
    parser.add_argument("--line-status", action="store_true",
                        help="with --live, also request Twilio line_status "
                             "(whether the line is currently active/reachable; "
                             "gated field, may be unavailable for India)")
    parser.add_argument("--probe-block", action="store_true",
                        help="treat positional args as block prefixes: sample a few "
                             "numbers per block via Twilio to infer its operator "
                             "(needs Twilio credentials; logs data/twilio_checks.csv)")
    parser.add_argument("--samples", type=int, default=3, metavar="N",
                        help="numbers to sample per block with --probe-block (default 3)")
    parser.add_argument("--probe-range", metavar="LOW-HIGH",
                        help="sweep every 5-digit mobile block in the range that has "
                             "no operator or a closed one (e.g. 70000-79999); "
                             "triages with 1 sample, escalates to --samples on live "
                             "mobile blocks. Resumable via the cache")
    parser.add_argument("--max-calls", type=int, metavar="N",
                        help="hard cap on billed Twilio calls for --probe-range "
                             "(cache hits are free); stops cleanly and resumes later")
    return parser


def input_numbers(args: argparse.Namespace) -> list:
    """Collect numbers from arguments, then --file, then piped stdin.

    Raises OSError if --file cannot be read.
    """
    numbers = list(args.numbers)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            numbers += fh.read().split()
    if not numbers and not sys.stdin.isatty():
        numbers = sys.stdin.read().split()
    return numbers


def print_dorks(numbers: list) -> None:
    """Print a search query and URL per number; skip unparsable ones."""
    for raw in numbers:
        try:
            query = dork(raw)
        except phonenumbers.NumberParseException as err:
            print(f"{raw}: {err}", file=sys.stderr)
            continue
        print(query)
        for name, url in dork_urls(query).items():
            print(f"  {name}: {url}")


def print_lookups(numbers: list, key: str, indent, twilio=None,
                  refresh=False, fields=LTI_FIELD) -> None:
    """Print one JSON result per number.

    Adds a numverify block when key is set, and a live Twilio Lookup block
    when twilio=(sid, token) is given. The number stays offline unless a
    credentialed flag asks for a network call. Live results are cached to a
    git-ignored file so repeat runs cost nothing (bypass with refresh).
    """
    cache = live_cache_load() if twilio else {}
    dirty = False
    for raw in numbers:
        result = lookup(raw)
        offline = result
        if (key or twilio) and result["valid"]:
            result = {"offline": offline}
            if key:
                remote = numverify(offline["number"], key)
                result["numverify"] = remote
                if "error" not in remote:
                    result["agree"] = agreement(offline, remote)
            if twilio:
                e164 = offline["international_format"]
                before = cache.get(e164)
                result["live"] = cached_twilio_lookup(
                    e164, twilio, cache, refresh, fields)
                dirty = dirty or cache.get(e164) is not before
        print(json.dumps(result, indent=indent, ensure_ascii=False))
    if dirty:
        live_cache_save(cache)


def print_block_probes(prefixes: list, twilio: tuple, samples: int,
                       refresh: bool, indent) -> None:
    """Probe each block prefix and print its inferred operator as JSON.

    Caches live results and appends every sampled number to the checks log,
    so the paid lookups are recorded once and reused on later runs.
    """
    cache = live_cache_load()
    all_samples = []
    suggested = []
    for prefix in prefixes:
        result = probe_block(prefix, samples, twilio, cache, refresh)
        all_samples += result["samples"]
        if result["suggested_row"]:
            suggested.append(result["suggested_row"])
        print(json.dumps(result, indent=indent, ensure_ascii=False))
    live_cache_save(cache)
    if all_samples:
        append_twilio_checks(all_samples)
    if suggested:
        save_suggested_rows(suggested)


def parse_range(text: str) -> tuple:
    """Parse "LOW-HIGH" into (low, high) ints, or raise ValueError."""
    low, sep, high = text.partition("-")
    if not sep:
        raise ValueError("range must be LOW-HIGH, e.g. 70000-79999")
    return int(low), int(high)


def print_block_sweep(low: int, high: int, twilio: tuple, samples: int,
                      refresh: bool, fields: str, max_calls, indent) -> None:
    """Sweep a block range within a billed-call cap, printing suggested rows.

    Prints one JSON line per block that yields a suggested operator row, then
    a summary (blocks scanned, rows found, calls billed, whether the cap was
    hit) to stderr. Every sampled number is cached and logged for reuse.
    """
    prefixes = blocks_to_refresh(low, high)
    print(f"{len(prefixes)} blocks worth probing in {low}-{high}; "
          f"cap {max_calls if max_calls is not None else 'none'} calls",
          file=sys.stderr)
    cache = live_cache_load()
    results, billed, hit_cap = sweep_blocks(
        prefixes, samples, twilio, cache, refresh, fields, max_calls,
        live_cache_save)

    suggested = []
    all_samples = []
    for result in results:
        all_samples += result["samples"]
        if result["suggested_row"]:
            suggested.append(result["suggested_row"])
            print(json.dumps(result["suggested_row"], indent=indent,
                             ensure_ascii=False))
    if all_samples:
        append_twilio_checks(all_samples)
    if suggested:
        save_suggested_rows(suggested)
    print(f"done: scanned {len(results)}/{len(prefixes)} blocks, "
          f"{len(suggested)} rows suggested (saved to {SUGGESTED_CSV.name}), "
          f"{billed} calls billed"
          f"{' (CAP HIT, resume to continue)' if hit_cap else ''}",
          file=sys.stderr)


def twilio_creds() -> tuple:
    """Return (sid, token) from env/.env, or None if either is missing."""
    sid = env_setting("TWILIO_ACCOUNT_SID")
    token = env_setting("TWILIO_AUTH_TOKEN")
    return (sid, token) if sid and token else None


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    key = ""
    if args.numverify:
        key = env_setting("NUMVERIFY_KEY")
        if not key:
            print("--numverify needs NUMVERIFY_KEY in the environment or .env",
                  file=sys.stderr)
            return 2

    twilio = None
    if args.live or args.probe_block or args.probe_range:
        twilio = twilio_creds()
        if not twilio:
            flag = ("--probe-range" if args.probe_range else
                    "--probe-block" if args.probe_block else "--live")
            print(f"{flag} needs TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN "
                  "in the environment or .env", file=sys.stderr)
            return 2

    if (args.probe_block or args.probe_range) and args.samples < 1:
        print("--samples must be at least 1", file=sys.stderr)
        return 2

    fields = f"{LTI_FIELD},{LINE_STATUS_FIELD}" if args.line_status else LTI_FIELD
    indent = 2 if args.pretty else None

    if args.probe_range:
        try:
            low, high = parse_range(args.probe_range)
        except ValueError as err:
            print(f"--probe-range: {err}", file=sys.stderr)
            return 2
        print_block_sweep(low, high, twilio, args.samples, args.refresh,
                          fields, args.max_calls, indent)
        return 0

    try:
        numbers = input_numbers(args)
    except OSError as err:
        print(f"cannot read --file: {err}", file=sys.stderr)
        return 2
    if not numbers:
        parser.print_help()
        return 2

    if args.probe_block:
        print_block_probes(numbers, twilio, args.samples, args.refresh, indent)
    elif args.dork:
        print_dorks(numbers)
    else:
        print_lookups(numbers, key, indent=indent,
                      twilio=twilio, refresh=args.refresh, fields=fields)
    return 0


if __name__ == "__main__":
    sys.exit(main())
