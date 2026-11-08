"""Combine every offline source into one dated history for an Indian mobile.

The sources disagree and span years, so each is turned into dated entries and
ordered so the entry to trust ends up last. Kept apart from the data loaders
because this is the ranking logic, not the storage.
"""

from __future__ import annotations

from . import constants as c
from . import tables
from .naming import expand_codes, operator_name, operator_names
from .records import Entry, Row


def is_current(entry: Entry) -> bool:
    """True when an entry names an operator that still runs a network."""
    return (entry.get("kind") not in ("withdrawal", "removed", "superseded")
            and entry["carrier"] in c.IN_OPERATORS.values())


def libphonenumber_entries(national: str) -> list[Entry]:
    """Dated entries for each change in libphonenumber's carrier for a number.

    libphonenumber uses the longest prefix it lists, and its prefixes grew from
    4 to 5 digits over the years, so the carrier on each date is the longest
    period active then. An entry is added only when the operator changes; a
    dropped prefix gives a "removed" entry, never the answer. No circle.
    """
    table = tables.libpn_table()
    periods = [row for n in range(1, len(national) + 1)
               for row in table.get(national[:n], [])]
    days = sorted({row["since"] for row in periods}
                  | {row["until"] for row in periods} - {""})
    entries: list[Entry] = []
    previous: str | None = None
    for day in days:
        active = [row for row in periods
                  if row["since"] <= day and (not row["until"] or day < row["until"])]
        row = max(active, key=lambda r: len(r["prefix"])) if active else None
        code = c.LIBPN_OPERATORS.get(row["carrier"], row["carrier"]) if row else None
        if code == previous:
            continue
        if row and code is not None:
            entries.append({"carrier": operator_name(code), "location": "",
                            "source": "libphonenumber", "updated": day,
                            "kind": "listed", "prefix": row["prefix"],
                            "commit": row["since_commit"] if row["since"] == day
                            else row["until_commit"]})
        elif previous:
            entries.append({"carrier": operator_name(previous), "location": "",
                            "source": "libphonenumber", "updated": day,
                            "kind": "removed", "prefix": "", "commit": ""})
        previous = code
    return entries


def series_entries(series: Row) -> list[Entry]:
    """The 4-digit row as history: its source's earlier values, then the current
    one dated from when that value first appeared.

    Earlier values are "superseded" and never the answer. Without a history file
    the row keeps its fetch date.
    """
    current = tables.series_entry(series)
    earlier: list[Entry] = []
    for period in tables.series_history(series["source"]).get(series["series"], []):
        if not period["until"]:
            current["updated"] = period["since"]
            continue
        earlier.append({"carrier": operator_names(period["operator"]),
                        "location": expand_codes(period["circle"], c.IN_CIRCLES),
                        "source": series["source"], "updated": period["since"],
                        "kind": "superseded", "until": period["until"]})
    return earlier + [current]


def extra_series_history(prefix: str, chosen: str) -> list[Entry]:
    """Dated periods for a 4-digit prefix from every series-history source but
    the one the merged series row already uses.

    The merged series table keeps one source per prefix, so the other source's
    history would never show. These entries are informational; the chosen source
    stays the baseline answer.
    """
    entries: list[Entry] = []
    for source in c.SERIES_HISTORY_CSV:
        if source == chosen:
            continue
        for period in tables.series_history(source).get(prefix, []):
            entries.append({
                "carrier": operator_names(period["operator"]),
                "location": expand_codes(period["circle"], c.IN_CIRCLES),
                "source": source, "updated": period["since"],
                "kind": "superseded" if period["until"] else "listed",
                "until": period["until"],
            })
    entries.sort(key=lambda e: e["updated"])
    return entries


def india_mobile_history(national: str) -> list[Entry]:
    """What the sources know about a 10-digit Indian mobile, trust last.

    Dated entries (DoT letters, libphonenumber git history, blocks-file rows)
    sort by date, so a reused or corrected block ends on its newest owner.
    Undated or coarse entries lead as the baseline: the c.2011 Scribd list
    (stalest), both 4-digit git sources, then COAI's 5-digit metro listing; or
    last when the newest dated entry is a closed operator and the series row
    names a current one, because that names who serves the numbers now.

    Returns [] when the number is not a mobile or no source has it.
    """
    if len(national) != 10 or national[0] not in "6789":
        return []
    blocks = tables.block_table()
    dated = [tables.msc_entry(row) for row in tables.msc_table().get(national[:5], [])]
    dated += libphonenumber_entries(national)
    dated += [tables.series_entry(row)
              for row in (blocks.get(national[:4]), blocks.get(national[:5])) if row]
    twilio = tables.twilio_table().get(national[:5])
    if twilio:  # live ground truth, dated today: sorts last as the answer
        dated.append(tables.twilio_entry(twilio))
    dated.sort(key=lambda entry: entry["updated"])
    series = tables.series_table().get(national[:4])
    undated: list[Entry] = []
    if series:
        undated += extra_series_history(national[:4], series["source"])
        undated += series_entries(series)
    levels = tables.levels2011_table()
    old = levels.get(national[:5]) or levels.get(national[:4])
    if old:  # oldest and stalest, so the least-trusted baseline
        undated.insert(0, tables.levels2011_entry(old))
    coai = tables.coai_table().get(national[:5])
    if coai:  # 5-digit, so it outranks the 4-digit row
        undated.append(tables.coai_entry(coai))
    if dated and not is_current(dated[-1]) and any(map(is_current, undated)):
        # Keep the order, but end on a current operator: a closed one in an
        # undated source must not become the answer over a current one.
        return (dated + [e for e in undated if not is_current(e)]
                + [e for e in undated if is_current(e)])
    return undated + dated


def latest_location(history: list[Entry]) -> str:
    """The newest circle given for the answer's operator, or "".

    libphonenumber names a carrier but no circle; another source naming the same
    operator supplies it. A circle from a different operator is not used.
    """
    answer = history[-1]
    for entry in reversed(history):
        if entry["carrier"] == answer["carrier"] and entry["location"] \
                and entry.get("kind") not in ("withdrawal", "removed", "superseded"):
            return entry["location"]
    return ""
