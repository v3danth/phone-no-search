"""Fact-only spam signal for a number, from the numbering plan and a local list.

India has no public mobile directory, so this never calls a reputation API: it
reports a TRAI caller category and whether a user-supplied list names the number.
"""

from __future__ import annotations

from . import tables
from .india import caller_category
from .records import Result


def spam_signal(number: str, national: str, region: str) -> Result:
    """TRAI caller category (India) plus any local spam report for a number.

    Empty dict when nothing applies, so the normal output stays clean.
    """
    signal: Result = {}
    category = caller_category(national) if region == "IN" else ""
    if category:
        signal["category"] = category
    reported = tables.spam_table().get(number)
    if reported:
        signal["reported_spam"] = True
        if reported.get("source"):
            signal["spam_source"] = reported["source"]
        if reported.get("updated"):
            signal["spam_updated"] = reported["updated"]
    return signal
