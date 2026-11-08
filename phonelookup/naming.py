"""Spell out the terse codes in the data tables into human names.

The CSVs store 2-letter operator and circle codes; these turn them into the
text the output shows, and map Twilio's freeform carrier strings back to codes.
"""

from __future__ import annotations

import re
from functools import lru_cache

from .constants import (
    IN_CIRCLES,
    IN_FORMER_OPERATORS,
    IN_OPERATORS,
    TWILIO_OPERATORS,
)

_WORD = re.compile(r"[a-z0-9]+")


def normalized(value: object) -> str:
    """Lower-cased words without punctuation; None and "" compare alike.

    numverify writes "Uttar Pradesh East" where we write "Uttar Pradesh
    (East)"; both should compare equal.
    """
    return " ".join(_WORD.findall(str(value or "").lower()))


def expand_codes(codes: str, names: dict[str, str]) -> str:
    """Spell out slash-joined short codes such as 'BR/WB' using `names`."""
    return " / ".join(names[c] for c in codes.split("/") if c in names)


def operator_name(code: str) -> str:
    """Spell out an operator code, current or closed."""
    return IN_OPERATORS.get(code) or IN_FORMER_OPERATORS.get(code, code)


def operator_names(codes: str) -> str:
    """Spell out "AT/Aircel"-style operator codes, current or closed."""
    return " / ".join(operator_name(code) for code in codes.split("/") if code)


def twilio_operator_code(carrier_name: str) -> str:
    """Map a Twilio carrier string to our operator code, or "" if unknown."""
    text = (carrier_name or "").lower()
    for needle, code in TWILIO_OPERATORS:
        if needle in text:
            return code
    return ""


@lru_cache(maxsize=1)
def _circle_by_name() -> dict[str, str]:
    """Reverse of IN_CIRCLES: full circle name (lower-case) -> code."""
    return {name.lower(): code for code, name in IN_CIRCLES.items()}


def circle_code(location: str) -> str:
    """Map an offline location name to a circle code, or "" if unknown."""
    return _circle_by_name().get((location or "").lower(), "")


@lru_cache(maxsize=1)
def _circle_by_normalized() -> dict[str, str]:
    """IN_CIRCLES keyed by normalized name, so "Uttar Pradesh (West)" and
    Twilio's "Uttar Pradesh West" both resolve to UW."""
    return {normalized(name): code for code, name in IN_CIRCLES.items()}


def twilio_circle_code(carrier_name: str) -> str:
    """Pull a circle code out of a Twilio carrier string, or "" if none.

    Twilio writes the circle after " - ", e.g. "Reliance (JIO) - Uttar Pradesh
    West"; the trailing parenthetical (network code or legal name) is dropped.
    """
    text = carrier_name or ""
    if " - " not in text:
        return ""
    region = text.split(" - ", 1)[1].split(" (")[0]
    return _circle_by_normalized().get(normalized(region), "")
