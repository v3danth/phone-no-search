#!/usr/bin/env python3
"""Build the dated history of the 4-digit series sources.

Usage:
  series_history.py wiki SNAPSHOTS.json > wiki_history.csv
  series_history.py git IN_MOB_PREFIX_REPO > in_mob_prefix_history.csv

`wiki` reads monthly snapshots of "Mobile telephone numbering in India"
fetched from the MediaWiki API ({revid: {timestamp, text}}); `git` walks
every commit of a clone of https://github.com/hstsethi/in-mob-prefix that
changed data/. Output: one row per period a prefix kept the same
operator and circle: prefix, operator, circle, since, until (empty while
current), since_ref, until_ref (Wikipedia revision id or commit hash).

Wikipedia snapshots before 2009-10 (one-letter operator codes) are not
used; old operator codes are mapped to the current ones. Snapshots whose
series table is missing or less than half the size of
the largest seen so far (old page layouts, blanking vandalism) are
skipped rather than read as every prefix being removed.
"""

import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import merge  # noqa: E402
import parse_wiki  # noqa: E402

FIELDS = ["prefix", "operator", "circle", "since", "until", "since_ref", "until_ref"]

# Wikipedia's table used one-letter or free-text operators before this
# month; from here on it is 2-letter codes, so earlier snapshots are skipped.
WIKI_START = "2009-10"
# Operator codes and names the page has used, mapped to ours (closed
# operators by name, as in phonelookup.IN_FORMER_OPERATORS). Codes whose
# meaning is unclear (SR, BG, MS, JT) are left out and read as unknown.
WIKI_OPERATORS = {
    "AT": "AT", "AIRTEL": "AT",
    "RJ": "RJ", "VI": "VI", "VF": "VI", "VODAFONE": "VI", "ID": "VI", "IDEA": "VI",
    "SP": "VI",
    "CG": "CG", "CC": "CG", "DP": "CG", "CELLONE CDMA": "CG",
    "RG": "RCom", "RC": "RCom", "RELIANCE GSM": "RCom",
    "AC": "Aircel", "AIRCEL": "Aircel",
    "TD": "Tata", "TI": "Tata", "DC": "Tata", "T24": "Tata", "TATA DOCOMO": "Tata",
    "UN": "Uninor", "UNINOR": "Uninor",
    "MT": "MTS", "LM": "Loop", "LOOP MOBILE": "Loop",
    "VD": "Videocon", "VG": "Videocon", "DATACOM": "Videocon",
    "ET": "Etisalat", "ETISALAT": "Etisalat", "ST": "S Tel", "PG": "HFCL",
}
CIRCLES = set("AP AS BR CH DL GJ HP HR JK KA KL KO MH MP MU NE OR PB RJ TN UE UW WB".split())
CIRCLE_ALIASES = {"UPE": "UE", "UPW": "UW", "DEL": "DL", "TC": "TN", "TN,CH": "TN"}


def wiki_value(operator: str, circle: str, day: str) -> tuple:
    """Normalise one Wikipedia row to (operator, circle) codes.

    Rows with two cells were "prefix, circle" in the old tables but are
    parsed as "prefix, operator"; a lone circle code is moved back. "RJ"
    is Rajasthan before Jio launched (2016), Jio after.
    """
    op = operator.strip().upper()
    ci = circle.strip().strip("|").strip().upper()
    ci = CIRCLE_ALIASES.get(ci, ci)
    if not ci and op in CIRCLES and (op != "RJ" or day < "2016"):
        op, ci = "", op
    codes = [WIKI_OPERATORS[part.strip()] for part in op.split("/")
             if part.strip() in WIKI_OPERATORS]
    circles = [part for part in ci.split("/") if part in CIRCLES]
    return "/".join(dict.fromkeys(codes)), "/".join(dict.fromkeys(circles))


def wiki_snapshots(path: str):
    """Yield (date, revid, {prefix: (operator, circle)}) oldest first."""
    snapshots = json.load(open(path, encoding="utf-8"))
    for revid, snap in sorted(snapshots.items(), key=lambda kv: kv[1]["timestamp"]):
        day = snap["timestamp"][:10]
        if day < WIKI_START:
            continue
        # The series tables moved between headings over the years; reading
        # every table cell finds them in all layouts.
        entries = parse_wiki.series_entries(parse_wiki.table_cells(snap["text"]))
        table = {prefix: wiki_value(*value, day) for prefix, value in entries.items()}
        yield day, revid, {k: v for k, v in table.items() if any(v)}


def git_snapshots(repo: str):
    """Yield (date, commit, {prefix: (operator, circle)}) oldest first."""
    def git(*args):
        return subprocess.run(["git", "-C", repo, *args], check=True,
                              capture_output=True, text=True).stdout
    for line in git("log", "--reverse", "--format=%H %ad", "--date=short",
                    "--", "data").splitlines():
        commit, day = line.split()
        table = {}
        for name in git("ls-tree", "-r", "--name-only", commit).split():
            if name.startswith("data/") and name.endswith("-in-mob-prefix.csv"):
                text = git("show", f"{commit}:{name}")
                header, _, body = text.partition("\n")
                # Early commits capitalised the header ("Series,Operator,Circle").
                reader = csv.DictReader([header.lower()] + body.splitlines())
                if not {"series", "operator", "circle"} <= set(reader.fieldnames or []):
                    continue  # the first commits' 6xxx/7xxx files used another layout
                for row in reader:
                    value = (merge.clean_codes(row["operator"] or ""),
                             merge.clean_codes(row["circle"] or ""))
                    if any(value):
                        table[row["series"]] = value
        yield day, commit, table


def periods(snapshots) -> list:
    """Turn snapshots into one row per unchanged (prefix, value) period."""
    open_rows, rows, largest = {}, [], 0
    for day, ref, table in snapshots:
        if len(table) < largest / 2:
            continue
        largest = max(largest, len(table))
        for prefix, row in list(open_rows.items()):
            if table.get(prefix) != (row["operator"], row["circle"]):
                row.update(until=day, until_ref=ref)
                rows.append(open_rows.pop(prefix))
        for prefix, (operator, circle) in table.items():
            if prefix not in open_rows:
                open_rows[prefix] = {"prefix": prefix, "operator": operator,
                                     "circle": circle, "since": day, "until": "",
                                     "since_ref": ref, "until_ref": ""}
    rows += open_rows.values()
    rows.sort(key=lambda row: (row["prefix"], row["since"]))
    return drop_short_reverts(rows)


def drop_short_reverts(rows: list, max_days: int = 92) -> list:
    """Merge A -> B -> A when B lasted under max_days.

    Monthly snapshots catch broken edits and vandalism that were reverted
    within weeks; those are noise, not changes. Longer swings (edit
    disputes lasting years) are kept.
    """
    def days(row):
        if not row["until"]:
            return max_days + 1
        return (date.fromisoformat(row["until"]) - date.fromisoformat(row["since"])).days
    out = []
    for row in rows:
        if (len(out) >= 2 and out[-2]["prefix"] == out[-1]["prefix"] == row["prefix"]
                and (out[-2]["operator"], out[-2]["circle"]) == (row["operator"], row["circle"])
                and days(out[-1]) < max_days):
            out.pop()
            out[-1].update(until=row["until"], until_ref=row["until_ref"])
        else:
            out.append(dict(row))
    return out


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("wiki", "git"):
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    source = wiki_snapshots if sys.argv[1] == "wiki" else git_snapshots
    writer = csv.DictWriter(sys.stdout, FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(periods(source(sys.argv[2])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
