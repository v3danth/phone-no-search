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


def expand(codes: str, names: dict) -> str:
    """'BR/WB' -> 'Bihar & Jharkhand / West Bengal' (split blocks)."""
    return " / ".join(names[c] for c in codes.split("/") if c in names)


@lru_cache(maxsize=1)
def in_series() -> dict:
    """4-digit Indian mobile prefix -> (operator, circle, source)."""
    try:
        with SERIES_CSV.open(encoding="utf-8") as fh:
            return {
                r["series"]: (r["operator"], r["circle"], r["source"])
                for r in csv.DictReader(fh)
            }
    except FileNotFoundError:
        return {}


def india_mobile_info(national: str) -> dict:
    """Operator and circle for a 10-digit Indian mobile, or {} if unknown."""
    if len(national) != 10 or national[0] not in "6789":
        return {}
    match = in_series().get(national[:4])
    if not match:
        return {}
    op, circle, source = match
    return {
        "carrier": expand(op, IN_OPERATORS),
        "location": expand(circle, IN_CIRCLES),
        "series_source": source,
    }


def parse(raw: str):
    text = raw.strip()
    return phonenumbers.parse(text if text.startswith("+") else "+" + text, None)


def lookup(raw: str) -> dict:
    digits = raw.strip()
    try:
        num = parse(digits)
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
        info = india_mobile_info(national)
        if info:
            # The series table is more specific than libphonenumber for Indian
            # mobiles, and stops 7x/8x mobiles being geocoded as STD landlines.
            result["line_type"] = "mobile"
            result["location"] = info["location"] or result["location"]
            result["carrier"] = info["carrier"] or result["carrier"]
            result["series_source"] = info["series_source"]
        elif result["line_type"] == "landline_or_mobile":
            result["location"] = result["country_name"]
    return result


def env_setting(name: str) -> str:
    """Read a setting from the environment, falling back to ./.env."""
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
    """Call numverify's validate endpoint; errors come back as a dict."""
    url = env_setting("NUMVERIFY_URL") or NUMVERIFY_URL
    query = urlencode({"access_key": key, "number": number})
    try:
        with urlopen(f"{url}?{query}", timeout=10) as resp:
            data = json.load(resp)
    except HTTPError as err:  # apilayer puts the reason in the JSON body
        try:
            data = json.load(err)
        except ValueError:
            return {"error": f"request failed: {err}"}
    except (URLError, TimeoutError, ValueError) as err:
        return {"error": f"request failed: {err}"}
    if data.get("success") is False:
        info = data.get("error", {})
        return {"error": info.get("info") or info.get("type") or "unknown error"}
    return data


def compare(ours: dict, theirs: dict) -> dict:
    """Which shared fields agree between the offline and numverify results."""
    def norm(v):
        return str(v or "").lower()
    return {
        "valid": ours.get("valid") == theirs.get("valid"),
        "line_type": norm(ours.get("line_type")) == norm(theirs.get("line_type")),
        "location": bool(theirs.get("location"))
        and norm(theirs["location"]) in norm(ours.get("location")),
        "carrier": bool(theirs.get("carrier"))
        and norm(ours.get("carrier")).split()[:1] == norm(theirs["carrier"]).split()[:1],
    }


def dork(raw: str) -> str:
    """Google query matching the common written forms of one number."""
    num = parse(raw)
    cc, nat = str(num.country_code), str(num.national_number)
    forms = {
        nat,
        f"+{cc}{nat}",
        f"{cc}{nat}",
        phonenumbers.format_number(num, PhoneNumberFormat.INTERNATIONAL),
        phonenumbers.format_number(num, PhoneNumberFormat.NATIONAL),
    }
    forms |= {f"+{cc}-{nat}", f"+{cc} {nat}"}
    if cc == "91" and len(nat) == 10:
        forms.add(f"{nat[:5]} {nat[5:]}")
    elif cc == "1" and len(nat) == 10:
        forms.add(f"{nat[:3]}-{nat[3:6]}-{nat[6:]}")
    return " OR ".join(f'"{f}"' for f in sorted(forms, key=len))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("numbers", nargs="*")
    parser.add_argument("--file", help="file with one number per line")
    parser.add_argument("--pretty", action="store_true", help="indent JSON")
    parser.add_argument("--dork", action="store_true",
                        help="print a Google search string and URL instead")
    parser.add_argument("--numverify", action="store_true",
                        help="also query numverify (uses 1 API request per number)")
    args = parser.parse_args()

    key = ""
    if args.numverify:
        key = env_setting("NUMVERIFY_KEY")
        if not key:
            print("--numverify needs NUMVERIFY_KEY in the environment or .env",
                  file=sys.stderr)
            return 2

    numbers = list(args.numbers)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            numbers += fh.read().split()
    if not numbers and not sys.stdin.isatty():
        numbers = sys.stdin.read().split()
    if not numbers:
        parser.print_help()
        return 2

    if args.dork:
        for raw in numbers:
            try:
                query = dork(raw)
            except phonenumbers.NumberParseException as err:
                print(f"{raw}: {err}", file=sys.stderr)
                continue
            print(query)
            print("https://www.google.com/search?q=" + quote_plus(query))
        return 0

    indent = 2 if args.pretty else None
    for raw in numbers:
        result = lookup(raw)
        if args.numverify and result["valid"]:
            remote = numverify(result["number"], key)
            result = {"offline": result, "numverify": remote}
            if "error" not in remote:
                result["agree"] = compare(result["offline"], remote)
        print(json.dumps(result, indent=indent, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
