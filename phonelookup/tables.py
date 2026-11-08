"""Load the offline data tables and spell each row out as a history entry.

Every loader is cached for the process lifetime because the CSVs never change
while it runs, and a missing file yields an empty table so the tool still works
on libphonenumber data alone.
"""

from __future__ import annotations

import csv
from functools import cache, lru_cache
from pathlib import Path

from . import constants as c
from .naming import expand_codes, operator_name
from .records import Entry, Row


def read_table(path: Path, key: str) -> dict[str, Row]:
    """Map each row's `key` column to the whole row, or {} if the file is gone."""
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            return {row[key]: row for row in csv.DictReader(fh)}
    except FileNotFoundError:
        return {}


def _grouped(path: Path, key: str) -> dict[str, list[Row]]:
    """Group rows by `key` (a block can have many rows), or {} if no file."""
    table: dict[str, list[Row]] = {}
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                table.setdefault(row[key], []).append(row)
    except FileNotFoundError:
        return {}
    return table


@lru_cache(maxsize=1)
def series_table() -> dict[str, Row]:
    """4-digit prefix -> DoT allocation row."""
    return read_table(c.SERIES_CSV, "series")


@lru_cache(maxsize=1)
def block_table() -> dict[str, Row]:
    """4- or 5-digit prefix -> newer row (a DoT letter or live check) that
    supersedes the series table."""
    return read_table(c.BLOCKS_CSV, "prefix")


@lru_cache(maxsize=1)
def msc_table() -> dict[str, list[Row]]:
    """5-digit block -> every DoT letter row for it, oldest first.

    A block can have many rows: DoT reuses blocks, and corrigenda move them
    between operators and circles.
    """
    table = _grouped(c.MSC_CSV, "block")
    for rows in table.values():
        rows.sort(key=lambda row: row["date"])
    return table


@lru_cache(maxsize=1)
def twilio_table() -> dict[str, Row]:
    """5-digit block -> Twilio HLR row; live current-carrier ground truth."""
    return read_table(c.SUGGESTED_CSV, "prefix")


@lru_cache(maxsize=1)
def libpn_table() -> dict[str, list[Row]]:
    """Prefix -> libphonenumber carrier periods (since/until), from its git
    history (scripts/libphonenumber_history.py)."""
    return _grouped(c.LIBPN_CSV, "prefix")


@cache
def series_history(source: str) -> dict[str, list[Row]]:
    """Prefix -> dated (operator, circle) periods for a 4-digit source."""
    path = c.SERIES_HISTORY_CSV.get(source)
    if path is None:
        return {}
    return _grouped(path, "prefix")


@lru_cache(maxsize=1)
def coai_table() -> dict[str, Row]:
    """5-digit block -> COAI's metro-circle MSC listing (undated, ~2016-17)."""
    return read_table(c.COAI_CSV, "block")


@lru_cache(maxsize=1)
def levels2011_table() -> dict[str, Row]:
    """4- or 5-digit level -> the c.2011 DoT "MSC levels" consolidated list.

    Undated and stale (every operator on it has since merged or closed), so it
    is the least-trusted baseline, used mainly for a block's circle.
    """
    return read_table(c.LEVELS2011_CSV, "level")


@lru_cache(maxsize=1)
def spam_table() -> dict[str, Row]:
    """Optional offline spam-report list (data/spam_numbers.csv) keyed by number.

    A local file the user supplies, never an API; absent file -> empty table.
    Expected columns: number, source, updated.
    """
    return read_table(c.SPAM_CSV, "number")


@lru_cache(maxsize=1)
def mcc_mnc_table() -> dict[tuple[str, str], dict[str, object]]:
    """(MCC, MNC) -> {networks, row}; distinct operators that registered a code.

    Networks is a list because the source has placeholder MNCs (299, 998, 999)
    shared by many MVNOs; keeping all names is more honest than dropping them.
    """
    table: dict[tuple[str, str], dict[str, object]] = {}
    try:
        with c.MCC_MNC_CSV.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                mcc, mnc = row["mcc"].strip(), row["mnc"].strip()
                net = row["network"].strip()
                if not (mcc and mnc and net):
                    continue
                hit = table.setdefault((mcc, mnc), {"networks": [], "row": row})
                networks = hit["networks"]
                assert isinstance(networks, list)
                if net not in networks:
                    networks.append(net)
    except FileNotFoundError:
        return {}
    return table


def series_entry(row: Row) -> Entry:
    """Spell out one series or blocks-file row as a history entry."""
    return {
        "carrier": expand_codes(row["operator"], c.IN_OPERATORS),
        "location": expand_codes(row["circle"], c.IN_CIRCLES),
        "source": row["source"],
        "updated": row.get("updated", ""),
    }


def msc_entry(row: Row) -> Entry:
    """Spell out one DoT letter row as a history entry."""
    code = row["operator"]
    return {
        "carrier": c.IN_OPERATORS.get(code) or c.IN_FORMER_OPERATORS.get(code, code),
        "location": expand_codes(row["circle"], c.IN_CIRCLES),
        "source": "dot.gov.in",
        "updated": row["date"],
        "kind": row["kind"],
        "letter": row["letter"],
    }


def twilio_entry(row: Row) -> Entry:
    """Spell out a Twilio suggested-block row as a history entry.

    Marked "current" so it sorts last and becomes the live answer, above every
    allocation source.
    """
    return {
        "carrier": operator_name(row["operator"]),
        "location": c.IN_CIRCLES.get(row["circle"], ""),
        "source": "twilio",
        "updated": row.get("updated", ""),
        "kind": "current",
        "note": row.get("note", ""),
    }


def coai_entry(row: Row) -> Entry:
    """Spell out a COAI row as an undated history entry."""
    return {"carrier": operator_name(row["operator"]),
            "location": expand_codes(row["circle"], c.IN_CIRCLES),
            "source": "coai.com", "updated": "", "kind": "listed"}


def levels2011_entry(row: Row) -> Entry:
    """Spell out a c.2011 levels-list row as an undated history entry."""
    return {"carrier": operator_name(row["operator"]),
            "location": expand_codes(row["circle"], c.IN_CIRCLES),
            "source": "scribd-2011", "updated": "", "kind": "listed"}
