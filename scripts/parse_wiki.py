#!/usr/bin/env python3
"""Extract Indian mobile series from Wikipedia wikitext as CSV.

Usage: parse_wiki.py wiki.txt > wiki_series.csv

Reads the raw source of "Mobile telephone numbering in India" and prints
series,operator,circle for every 4-digit prefix in its "Call No Series"
tables. See data/README.md for the full refresh steps.
"""

import csv
import re
import sys

SECTION_START = "==Call No Series=="
SECTION_END = "== See also =="
SERIES = re.compile(r"[6-9]\d{3}")
# Table markup rows: new row, end of table, caption.
MARKUP_PREFIXES = ("|-", "|}", "|+")


def series_section(text: str) -> str:
    """Return the wikitext between the series heading and "See also"."""
    return text.split(SECTION_START)[1].split(SECTION_END)[0]


def table_cells(section: str) -> list:
    """Flatten every table data row into one list of stripped cell values.

    Rows may hold several cells joined by "||", and a row's cells can spill
    onto the next line, so cells are read as one stream rather than per row.
    """
    cells = []
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith(MARKUP_PREFIXES):
            continue
        cells.extend(cell.strip() for cell in line[1:].split("||"))
    return cells


def is_series(cell: str) -> bool:
    return SERIES.fullmatch(cell) is not None


def series_entries(cells: list) -> dict:
    """Group the cell stream into {series: (operator, circle)}.

    A series is normally followed by its operator and circle, but either
    may be missing. A cell that is itself a series starts the next entry
    instead of being read as a value.
    """
    entries = {}
    i = 0
    while i < len(cells):
        if not is_series(cells[i]):
            i += 1
            continue
        values = []
        for cell in cells[i + 1:i + 3]:
            if is_series(cell):
                break
            values.append(cell)
        operator, circle = (values + ["", ""])[:2]
        entries[cells[i]] = (operator, circle)
        i += 1 + len(values)
    return entries


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        entries = series_entries(table_cells(series_section(fh.read())))
    writer = csv.writer(sys.stdout)
    writer.writerow(["series", "operator", "circle"])
    for series in sorted(entries):
        writer.writerow([series, *entries[series]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
