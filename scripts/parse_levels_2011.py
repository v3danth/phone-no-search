#!/usr/bin/env python3
"""Parse DoT's c.2011 all-India "MSC levels" list into data/in_mobile_levels_2011.csv.

Usage: parse_levels_2011.py LIST.pdf   (needs pdftotext on PATH)

The source is a Scribd scan of DoT's "LIST OF MSC & SP CODES ALLOTTED TO
ALL" (e.g. scribd.com/doc/74759473), a consolidated table with columns
Sl.No / Service Area / Operator / Level. Its text layer is clean (not
font-scrambled), so pdftotext -layout recovers it; the layout's
indentation is inconsistent, so areas and operators are identified by
known vocabularies, not column positions.

Every operator on the list has since merged or closed (Etisalat DB,
Unitech/Uninor, S Tel, Loop, Datacom/Videocon, Reliance Communications,
Idea, Vodafone Essar), which dates it to 2010-2011. It is wired into
phonelookup.py as the stalest, least-trusted undated baseline. 3-digit
levels and levels that resolve to more than one circle are dropped as
unreliable; page-break duplicates are removed.

Output columns: level (4- or 5-digit), operator (code), circle (code).
"""
import csv
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "in_mobile_levels_2011.csv"

# Area first word -> circle code (phonelookup.IN_CIRCLES).
AREAS = [
    ("andhra", "AP"), ("assam", "AS"), ("bihar", "BR"), ("chennai", "CH"),
    ("delhi", "DL"), ("gujarat", "GJ"), ("haryana", "HR"), ("himachal", "HP"),
    ("jammu", "JK"), ("j&k", "JK"), ("karnataka", "KA"), ("kerala", "KL"),
    ("kolkata", "KO"), ("madhya", "MP"), ("maharashtra", "MH"), ("mumbai", "MU"),
    ("north east", "NE"), ("orissa", "OR"), ("punjab", "PB"), ("rajasthan", "RJ"),
    ("tamil", "TN"), ("west bengal", "WB"),
    ("u.p.(w", "UW"), ("u.p(w", "UW"), ("up(w", "UW"), ("u.p. (w", "UW"),
    ("uttar pradesh(w", "UW"),
    ("u.p.(e", "UE"), ("u.p(e", "UE"), ("up(e", "UE"), ("u.p. (e", "UE"),
    ("uttar pradesh(e", "UE"),
]

# Operator-start keyword -> operator code (phonelookup.IN_OPERATORS /
# IN_FORMER_OPERATORS). More specific first.
OPERATORS = [
    ("idea", "VI"), ("spice", "VI"),
    ("bharti airtel", "AT"), ("bharti mobile", "AT"), ("bharti tele", "AT"),
    ("bharti", "AT"), ("bsnl", "CG"), ("mtnl", "CG"),
    ("vodafone essar", "VI"), ("hutchison", "VI"),
    ("reliance infocomm", "RCom"), ("reliance communication", "RCom"),
    ("reliance telecom", "RCom"), ("reliance", "RCom"),
    ("tata", "Tata"), ("aircell", "Aircel"), ("aircel", "Aircel"),
    ("dishnet", "Dishnet"), ("loop", "Loop"),
    ("sistema shyam", "MTS"), ("shyam", "MTS"), ("s tel", "S Tel"), ("stel", "S Tel"),
    ("etisalat", "Etisalat"), ("swan", "Etisalat"), ("unitech", "Uninor"),
    ("datacom", "Videocon"), ("videocon", "Videocon"), ("bpl", "BPL"),
    ("quadrant", "HFCL"), ("hfcl", "HFCL"),
]

DROP = re.compile(
    r"^\s*(list of msc|sl\.|no\.?$|\.$|service area|name of the operator|"
    r"level to be opened|page \d|\d{1,2}\s*$|\*|-\s|wherever|the msc codes|"
    r"all the above|note\b)", re.I)
LEVEL = re.compile(r"(\d{3,5})\s*(?:ask\s*\d+)?\s*$", re.I)
ASK = re.compile(r"\s*ask\s*\d+\s*$", re.I)
SLNO = re.compile(r"^\s*\d{1,2}[.)]?\s+")


def first_match(text, pairs):
    low = text.lstrip(" (").lower()
    for key, code in pairs:
        if low.startswith(key):
            return code, key
    return None, None


def area_start(text):
    """If text begins with an area word (after an optional Sl.No), return
    (circle code, remaining text).

    Only a genuine header counts: the area word must be at the very start
    (spaces stripped, but not an opening paren), so an operator's
    "(Maharashtra) Ltd." continuation line is not mistaken for an area.
    """
    body = SLNO.sub("", text)
    low = body.lower().lstrip()
    for key, code in sorted(AREAS, key=lambda kv: -len(kv[0])):
        if low.startswith(key):
            return code, body.lstrip()[len(key):].lstrip(" .)")
    return None


def op_start(text):
    code, _ = first_match(text, OPERATORS)
    return code


def parse(lines):
    groups, area, cur = [], None, None
    for raw in lines:
        if not raw.strip() or DROP.match(raw):
            continue
        line = ASK.sub("", raw).rstrip()
        m = LEVEL.search(line)
        level = m.group(1) if m else None
        text = (line[:m.start()] if m else line).strip()
        found = area_start(text)
        if found:
            area, text = found
        code = op_start(text) if text else None
        if code:
            cur = {"area": area, "op": code, "levels": []}
            groups.append(cur)
        if level is not None and cur is not None and level not in cur["levels"]:
            cur["levels"].append(level)
    return groups


def clean(groups):
    """One (level, operator, circle) row each; drop 3-digit and ambiguous."""
    rows, seen = [], set()
    for g in groups:
        for lvl in g["levels"]:
            if len(lvl) == 3:
                continue
            key = (lvl, g["area"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({"level": lvl, "operator": g["op"], "circle": g["area"]})
    bad = {lvl for lvl, n in Counter(r["level"] for r in rows).items() if n > 1}
    rows = [r for r in rows if r["level"] not in bad]
    rows.sort(key=lambda r: (r["level"], r["circle"]))
    return rows, sorted(bad)


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    text = subprocess.run(["pdftotext", "-layout", sys.argv[1], "-"],
                          check=True, capture_output=True, text=True).stdout
    rows, bad = clean(parse(text.splitlines()))
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, ["level", "operator", "circle"],
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT.name}; dropped ambiguous {bad}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
