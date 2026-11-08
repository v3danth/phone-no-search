"""Compare our offline answer with numverify's, field by field.

Kept separate because it is only used when --numverify runs; the two sources
spell brands and circles differently, so the match is deliberately loose.
"""

from __future__ import annotations

from .naming import normalized
from .records import Live, Result


def agreement(ours: Result, theirs: Live) -> dict[str, bool]:
    """Which shared fields match between offline and numverify.

    Location matches when numverify's (often shorter) name appears in ours;
    carrier matches on the first word, since the two spell brand names
    differently ("Reliance Jio" vs "Reliance Jio Infocomm").
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
