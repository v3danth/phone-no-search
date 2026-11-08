"""The offline lookup: libphonenumber facts, refined by the India sources.

This is the one function the whole tool is built around; the command line and
every provider call start from its result.
"""

from __future__ import annotations

import phonenumbers
from phonenumbers import PhoneNumberFormat, carrier, geocoder

from .constants import LINE_TYPES
from .india import india_overrides
from .records import Result
from .spam import spam_signal


def parse_number(raw: str) -> phonenumbers.PhoneNumber:
    """Parse a number that already includes its country code.

    Users paste numbers like 91XXXXXXXXXX without the '+'; adding it stops
    libphonenumber guessing a region from the leading digits.
    """
    text = raw.strip()
    return phonenumbers.parse(text if text.startswith("+") else "+" + text, None)


def lookup(raw: str) -> Result:
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
    result: Result = {
        "valid": True,
        "number": f"{num.country_code}{national}",
        "local_format": "".join(
            ch for ch in phonenumbers.format_number(num, PhoneNumberFormat.NATIONAL)
            if ch.isdigit()
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
        result = {**result, **india_overrides(result, national)}
    spam = spam_signal(result["number"], national, region or "")
    if spam:
        result["spam"] = spam
    return result
