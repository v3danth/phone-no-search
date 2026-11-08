"""India-specific overrides that replace libphonenumber's coarse answer.

libphonenumber reads 7x/8x mobiles as STD landlines and froze India carrier data
around 2019, so the DoT/COAI/Twilio sources here are more specific and current.
"""

from __future__ import annotations

from . import history
from .records import Result


def caller_category(national: str) -> str:
    """Name India's designated caller series, which identify the kind of entity
    placing a call rather than a subscriber.

    TRAI reserves 140-xxxxxxx for registered telemarketing callers and, from
    2024, 1600-xx for transactional/service calls. Both are numbering-plan facts.
    Returns "" when the number is in neither series.
    """
    if national.startswith("1600"):
        return "transactional / service caller (TRAI 1600 series)"
    if national.startswith("140"):
        return "registered telemarketing / promotional caller (TRAI 140 series)"
    return ""


def unallocated_note(national: str) -> str:
    """Explain a valid mobile number that no source gives an operator.

    Likely unallocated: the 6x series (opened 2017), 71xx (first letters 2026),
    and 4-digit prefixes where no block has any source.
    """
    whole_prefix_empty = not any(
        history.india_mobile_history(national[:4] + digit + national[5:])
        for digit in "0123456789")
    if national[0] == "6" or national[:2] == "71" or whole_prefix_empty:
        return ("no operator in DoT letters, libphonenumber or numverify; "
                "this block is probably not allocated yet")
    return "no operator known for this block"


def india_overrides(result: Result, national: str) -> Result:
    """The fields that replace libphonenumber's answer for an Indian number.

    The newest history entry wins; when sources differ, all are kept under
    "history". `carrier` is the DoT allocation, which MNP may have changed, so
    `current_carrier` is null unless a live Twilio sample set it.
    """
    entries = history.india_mobile_history(national)
    if entries:
        latest = entries[-1]
        from_twilio = latest.get("source") == "twilio"
        fields: Result = {
            "line_type": "mobile",
            "location": history.latest_location(entries) or result["country_name"],
            "carrier": latest["carrier"] or result["carrier"],
            "current_carrier": latest["carrier"] if from_twilio else None,
            "carrier_note": ("current carrier from a Twilio HLR sample (ground "
                             "truth); see history for the DoT allocation"
                             if from_twilio
                             else "allocation; current may differ (MNP)"),
            "series_source": latest["source"],
            "updated": latest["updated"],
        }
        if len(entries) > 1:
            fields["history"] = entries
        return fields
    if result["line_type"] == "mobile":
        return {"note": unallocated_note(national)}
    if result["line_type"] == "landline_or_mobile":
        return {"location": result["country_name"]}
    return {}


__all__ = ["caller_category", "india_overrides", "unallocated_note"]
