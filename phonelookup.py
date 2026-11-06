#!/usr/bin/env python3
"""Offline phone number lookup, numverify-style output.

Usage:
  phonelookup.py 917904XXXXXX +1650XXXXXXX ...
  phonelookup.py --file numbers.txt      (one number per line)
  echo 9180XXXXXXXX | phonelookup.py     (reads stdin when no args)
  phonelookup.py --dork 919886XXXXXX     (print a Google search string)
  phonelookup.py --numverify 919886XXXXXX  (also call numverify; needs
                                            NUMVERIFY_KEY in env or .env)

Numbers without a leading + are treated as including the country code.
"""

import argparse
import csv
import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import urlopen

import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType, carrier, geocoder

ROOT = Path(__file__).resolve().parent
SERIES_CSV = ROOT / "data" / "in_mobile_series.csv"
BLOCKS_CSV = ROOT / "data" / "in_mobile_blocks.csv"
MSC_CSV = ROOT / "data" / "in_mobile_msc.csv"
LIBPN_CSV = ROOT / "data" / "in_libphonenumber_history.csv"
COAI_CSV = ROOT / "data" / "coai_msc.csv"
# Dated histories of the two 4-digit sources (scripts/series_history.py).
SERIES_HISTORY_CSV = {
    "wikipedia": ROOT / "data" / "wiki_series_history.csv",
    "in-mob-prefix": ROOT / "data" / "in_mob_prefix_history.csv",
}
# The numverify free plan only supports plain HTTP; paid plans can set
# NUMVERIFY_URL=https://apilayer.net/api/validate
NUMVERIFY_URL = "http://apilayer.net/api/validate"

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


@lru_cache(maxsize=1)
def coai_table() -> dict:
    """5-digit block -> COAI's metro-circle MSC listing (undated, ~2016-17)."""
    return read_table(COAI_CSV, "block")


def coai_entry(row: dict) -> dict:
    """Spell out a COAI row as an undated history entry."""
    return {"carrier": operator_name(row["operator"]),
            "location": expand_codes(row["circle"], IN_CIRCLES),
            "source": "coai.com", "updated": "", "kind": "listed"}


def india_mobile_history(national: str) -> list:
    """Return what the sources know about a 10-digit Indian mobile, with
    the entry to trust last.

    Dated entries (DoT letters, libphonenumber's git history, blocks-file
    rows) are sorted by date, so a reused or corrected block ends on its
    newest owner. Undated or coarse entries go first as the baseline
    whatever their date: the 4-digit series row (with its source's earlier
    values, oldest first), then COAI's undated 5-digit metro listing, or last when the newest dated entry is a closed operator, a
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
    dated.sort(key=lambda entry: entry["updated"])
    series = series_table().get(national[:4])
    undated = series_entries(series) if series else []
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
    """
    history = india_mobile_history(national)
    if history:
        latest = history[-1]
        fields = {
            "line_type": "mobile",
            "location": latest_location(history) or result["country_name"],
            "carrier": latest["carrier"] or result["carrier"],
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


def dork(raw: str) -> str:
    """Build a Google query matching the common written forms of one number.

    The same number is written many ways online, so an exact-phrase search
    for one form misses most pages.
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


def build_parser() -> argparse.ArgumentParser:
    """Define the command-line flags."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("numbers", nargs="*")
    parser.add_argument("--file", help="file with one number per line")
    parser.add_argument("--pretty", action="store_true", help="indent JSON")
    parser.add_argument("--dork", action="store_true",
                        help="print a Google search string and URL instead")
    parser.add_argument("--numverify", action="store_true",
                        help="also query numverify (uses 1 API request per number)")
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
        print("https://www.google.com/search?q=" + quote_plus(query))


def print_lookups(numbers: list, key: str, indent) -> None:
    """Print one JSON result per number, adding numverify when key is set."""
    for raw in numbers:
        result = lookup(raw)
        if key and result["valid"]:
            remote = numverify(result["number"], key)
            result = {"offline": result, "numverify": remote}
            if "error" not in remote:
                result["agree"] = agreement(result["offline"], remote)
        print(json.dumps(result, indent=indent, ensure_ascii=False))


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

    try:
        numbers = input_numbers(args)
    except OSError as err:
        print(f"cannot read --file: {err}", file=sys.stderr)
        return 2
    if not numbers:
        parser.print_help()
        return 2

    if args.dork:
        print_dorks(numbers)
    else:
        print_lookups(numbers, key, indent=2 if args.pretty else None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
