#!/usr/bin/env python3
"""Merge two series CSVs into data/in_mobile_series.csv.

Usage: merge.py wiki_series.csv in_mob_prefix.csv [YYYY-MM-DD] > data/in_mobile_series.csv

The date (default: today) fills the "updated" column: the day the sources
were fetched, so users can tell how old an answer is.

Wikipedia is preferred because it matched numverify where the sources
disagreed; in-mob-prefix fills series Wikipedia lacks. See data/README.md.
"""

import csv
import re
import sys
from datetime import date

CODE = re.compile(r"[A-Z]{2}")
EMPTY = ("", "")


def load_series(path: str) -> dict:
    """Read a series,operator,circle CSV into {series: (operator, circle)}."""
    with open(path, encoding="utf-8", newline="") as fh:
        return {row["series"]: (row["operator"], row["circle"])
                for row in csv.DictReader(fh)}


def clean_codes(value: str) -> str:
    """Keep only 2-letter codes, de-duplicated, in their original order.

    Source tables mix in notes and repeat circles for split blocks
    ("BR/WB/BR"); the lookup tool only understands the codes.
    """
    codes = dict.fromkeys(value.split("/"))
    return "/".join(code for code in codes if CODE.fullmatch(code))


def merged_row(wiki: tuple, fallback: tuple):
    """Pick (operator, circle, source) for one series, or None if unknown.

    A complete Wikipedia entry wins, then a complete fallback entry, then
    whatever partial values either source has.
    """
    wiki_op, wiki_circle = map(clean_codes, wiki)
    fb_op, fb_circle = map(clean_codes, fallback)
    if wiki_op and wiki_circle:
        return wiki_op, wiki_circle, "wikipedia"
    if fb_op and fb_circle:
        return fb_op, fb_circle, "in-mob-prefix"
    if wiki_op or wiki_circle or fb_op or fb_circle:
        return wiki_op or fb_op, wiki_circle or fb_circle, "partial"
    return None


def main() -> int:
    if len(sys.argv) not in (3, 4):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    wiki, fallback = load_series(sys.argv[1]), load_series(sys.argv[2])
    updated = sys.argv[3] if len(sys.argv) == 4 else date.today().isoformat()
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["series", "operator", "circle", "source", "updated"])
    for series in sorted(wiki.keys() | fallback.keys()):
        row = merged_row(wiki.get(series, EMPTY), fallback.get(series, EMPTY))
        if row:
            writer.writerow([series, *row, updated])
    return 0


if __name__ == "__main__":
    sys.exit(main())
