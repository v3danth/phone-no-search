"""Resolve a serving MCC/MNC to the operator that registered it, offline.

A separate axis from the numbering plan: Twilio returns the serving MCC/MNC, and
this names who owns that network code. Labelled apart from carrier because the
community list lags porting and mergers (its India rows are pre-2010 operators).
"""

from __future__ import annotations

from . import tables
from .records import Result

# The community list's India rows are all pre-2010 operators, so flag them.
_HISTORICAL_MCC = frozenset({"404", "405"})


def _mnc_candidates(mnc: str) -> tuple[str, ...]:
    """The MNC forms to try, since the serving value's padding varies."""
    stripped = mnc.lstrip("0") or "0"
    return (mnc, stripped, stripped.zfill(2), stripped.zfill(3))


def network_registry(mcc: str, mnc: str) -> Result:
    """Registered owner of a serving MCC/MNC, or {} when unknown.

    India (404/405) hits are tagged historical rather than shown like a current
    carrier, because the source predates Jio and the Vi/Airtel consolidations.
    """
    mcc, mnc = str(mcc or "").strip(), str(mnc or "").strip()
    if not (mcc and mnc):
        return {}
    table = tables.mcc_mnc_table()
    for candidate in _mnc_candidates(mnc):
        hit = table.get((mcc, candidate))
        if not hit:
            continue
        networks = hit["networks"]
        row = hit["row"]
        assert isinstance(networks, list) and isinstance(row, dict)
        historical = mcc in _HISTORICAL_MCC
        source = ("mcc-mnc-table (community list; India rows are historical, "
                  "pre-2010 operators)" if historical
                  else "mcc-mnc-table (community list; may lag porting/mergers)")
        entry: Result = {
            "mcc": mcc,
            "mnc": mnc,
            "registered_operator": " / ".join(networks),
            "country": row.get("country", ""),
            "source": source,
        }
        if historical:
            entry["historical"] = True
        return entry
    return {}
