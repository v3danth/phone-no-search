"""Build an OSINT search query and per-engine URLs for one number.

The same number is written many ways online, so an exact-phrase search for one
form misses most pages; the "a" OR "b" syntax covers the common forms at once.
"""

from __future__ import annotations

from urllib.parse import quote_plus

import phonenumbers
from phonenumbers import PhoneNumberFormat

from .constants import SEARCH_ENGINES
from .core import parse_number


def dork(raw: str) -> str:
    """A search query matching the common written forms of one number."""
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
    # Sort on the text too: sets have no order, and equal-length forms would
    # otherwise print differently on each run.
    return " OR ".join(f'"{f}"' for f in sorted(forms, key=lambda f: (len(f), f)))


def dork_urls(query: str) -> dict[str, str]:
    """Map each search engine to its URL for the dork query."""
    return {name: base + quote_plus(query) for name, base in SEARCH_ENGINES.items()}
