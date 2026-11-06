#!/usr/bin/env python3
"""Extract the metro-circle MSC codes table published by COAI.

Usage: coai_msc.py msc-codes.html > data/coai_msc.csv
  (download: curl -o msc-codes.html https://coai.com/msc-codes)

COAI (the operators' association) lists DoT MSC allocations for the four
metro circles. The page has no date; its operators (Jio, Aircel, Unitech,
Loop) place it around 2016-17. Blocks the page lists under two different operators or cities are
left out as ambiguous. Output: one row per 5-digit block: block,
operator (our code), circle, listed_as (the operator as written).
"""

import csv
import html
import re
import sys

CIRCLES = {"Mumbai": "MU", "Kolkata": "KO", "Delhi": "DL", "Chennai": "CH"}
OPERATORS = {
    "Bharti Airtel": "AT", "Bharati Airtel": "AT",
    "Reliance Jio Infocomm": "RJ", "Reliance JIO Infocomm": "RJ",
    "IDEA": "VI", "Vodafone Essar": "VI", "Spice": "VI",
    "BSNL": "CG", "MTNL": "CG",
    "Aircel": "Aircel",
    "Reliance Communication": "RCom", "Reliance Telecom": "RCom",
    "Tata Teleservices": "Tata",
    "Unitech Wireless": "Uninor",
    "Shyam Telelink": "MTS",
    "Datacom Solution": "Videocon", "Datacom Solutions": "Videocon",
    "Etisalat": "Etisalat", "Etsalat": "Etisalat",
    "LOOP": "Loop", "BPL Mobile": "Loop",  # BPL Mobile Mumbai became Loop
}


def table_rows(page: str) -> list:
    """Return [city, operator, codes] for each table row with MSC codes."""
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", " ", cell)).strip()
                 for cell in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) >= 3 and re.search(r"\d{5}", cells[2]):
            rows.append(cells[:3])
    return rows


def blocks(codes: str) -> list:
    """Expand "98670-98679 84549" into 5-digit blocks."""
    out = []
    for start, end in re.findall(r"(\d{5})\s*-\s*(\d{5})", codes):
        out += [str(n) for n in range(int(start), int(end) + 1)]
    out += re.findall(r"(?<![\d-])(\d{5})(?![\d-])", codes)
    return [b for b in dict.fromkeys(out) if b[0] in "6789"]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    page = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    listings = {}
    for city, operator, codes in table_rows(page):
        for block in blocks(codes):
            listings.setdefault(block, set()).add(
                (OPERATORS.get(operator, operator), CIRCLES.get(city, city), operator))
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["block", "operator", "circle", "listed_as"])
    conflicts = 0
    for block, values in sorted(listings.items()):
        if len({value[:2] for value in values}) > 1:
            conflicts += 1  # listed under two operators or cities: ambiguous
            continue
        writer.writerow([block, *sorted(values)[0]])
    print(f"skipped {conflicts} blocks listed with conflicting values", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
