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


@lru_cache(maxsize=1)
def series_table() -> dict:
    """Map each 4-digit Indian mobile prefix to (operator, circle, source).

    Cached because every Indian lookup needs it and the CSV never changes
    while the process runs. A missing file yields an empty table so the
    tool still works on libphonenumber data alone.
    """
    try:
        with SERIES_CSV.open(encoding="utf-8") as fh:
            return {
                row["series"]: (row["operator"], row["circle"], row["source"])
                for row in csv.DictReader(fh)
            }
    except FileNotFoundError:
        return {}


def india_mobile_series(national: str) -> dict:
    """Return carrier, location and source for a 10-digit Indian mobile.

    libphonenumber has no state data for Indian mobiles, so this fills the
    gap from the series table. Returns {} when the number is not a mobile
    or its prefix is not in the table.
    """
    if len(national) != 10 or national[0] not in "6789":
        return {}
    match = series_table().get(national[:4])
    if not match:
        return {}
    operator, circle, source = match
    return {
        "carrier": expand_codes(operator, IN_OPERATORS),
        "location": expand_codes(circle, IN_CIRCLES),
        "series_source": source,
    }


def india_overrides(result: dict, national: str) -> dict:
    """Return the fields that replace libphonenumber's answer for India.

    The series table is more specific than libphonenumber for Indian
    mobiles, and stops 7x/8x mobiles being geocoded as STD landlines.
    """
    series = india_mobile_series(national)
    if series:
        return {
            "line_type": "mobile",
            "location": series["location"] or result["location"],
            "carrier": series["carrier"] or result["carrier"],
            "series_source": series["series_source"],
        }
    if result["line_type"] == "landline_or_mobile":
        return {"location": result["country_name"]}
    return {}


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
    """Lower-cased text, with None and "" treated alike."""
    return str(value or "").lower()


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
