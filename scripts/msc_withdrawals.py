#!/usr/bin/env python3
"""Add withdrawal rows for blocks that a DoT corrigendum replaced.

Usage: msc_withdrawals.py   (rewrites data/in_mobile_msc.csv in place)

A corrigendum row's note says "replaces 85468,85469" or "replaces
90600-90609". Without a matching withdrawal the replaced block keeps its
old allocation as the newest entry, so the lookup would still answer with
it. This adds one withdrawal row per replaced block, dated and linked like
the corrigendum. Running it again adds nothing.
"""

import csv
import re
import sys
from pathlib import Path

MSC_CSV = Path(__file__).resolve().parent.parent / "data" / "in_mobile_msc.csv"
REPLACES = re.compile(r"replaces (?:withdrawn )?([\d,\s-]+)")


def replaced_blocks(note: str) -> list:
    """Return the 5-digit blocks named after "replaces" in a note."""
    match = REPLACES.search(note)
    if not match:
        return []
    blocks = []
    for part in match.group(1).split(","):
        part = part.strip()
        if re.fullmatch(r"\d{5}-\d{5}", part):
            start, end = map(int, part.split("-"))
            blocks += [str(n) for n in range(start, end + 1)]
        elif re.fullmatch(r"\d{5}", part):
            blocks.append(part)
    return blocks


def withdrawals(rows: list) -> list:
    """Return the withdrawal rows the replacements imply, minus existing ones."""
    have = {(r["block"], r["date"]) for r in rows if r["kind"] == "withdrawal"}
    new = {}
    for row in rows:
        for block in replaced_blocks(row["note"]):
            key = (block, row["date"])
            if key in have or key in new:
                continue
            new[key] = {
                "block": block, "operator": row["operator"], "circle": row["circle"],
                "date": row["date"], "kind": "withdrawal", "letter": row["letter"],
                "note": f"replaced by {row['block']} ({row['kind']})",
            }
    return list(new.values())


def main() -> int:
    if len(sys.argv) != 1:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    with MSC_CSV.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fields, rows = reader.fieldnames, list(reader)
    added = withdrawals(rows)
    rows += added
    rows.sort(key=lambda r: (r["block"], r["date"], r["kind"]))
    with MSC_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"added {len(added)} withdrawal rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
