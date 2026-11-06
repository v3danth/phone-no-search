#!/usr/bin/env python3
"""Build the history of libphonenumber's Indian carrier data from git.

Usage: libphonenumber_history.py REPO_DIR > data/in_libphonenumber_history.csv

REPO_DIR is a clone of https://github.com/google/libphonenumber; a
partial clone is enough (git clone --filter=blob:none --no-checkout).
Every commit that touched resources/carrier/en/91.txt is a dated
snapshot. The output has one row per period a prefix kept the same
carrier: prefix (national digits), carrier, since and until (commit
dates; until is empty while current), and the commits that started and
ended the period.
"""

import csv
import subprocess
import sys

CARRIER_FILE = "resources/carrier/en/91.txt"


def git(repo: str, *args: str) -> str:
    """Run a git command in the repo and return its output."""
    return subprocess.run(["git", "-C", repo, *args], check=True,
                          capture_output=True, text=True).stdout


def snapshots(repo: str) -> list:
    """Return (commit, date) for every change to the carrier file, oldest first."""
    log = git(repo, "log", "--reverse", "--format=%H %ad", "--date=short",
              "--", CARRIER_FILE)
    return [tuple(line.split()) for line in log.splitlines()]


def carriers(text: str) -> dict:
    """Parse a carrier file ("918317|Reliance Jio") into {national prefix: name}."""
    table = {}
    for line in text.splitlines():
        prefix, sep, name = line.partition("|")
        if sep and prefix.startswith("91") and not prefix.startswith("#"):
            table[prefix[2:].strip()] = name.strip()
    return table


def periods(repo: str) -> list:
    """Walk the snapshots and return one row per (prefix, carrier) period."""
    open_rows, rows = {}, []
    for commit, day in snapshots(repo):
        table = carriers(git(repo, "show", f"{commit}:{CARRIER_FILE}"))
        for prefix, row in list(open_rows.items()):
            if table.get(prefix) != row["carrier"]:
                row.update(until=day, until_commit=commit)
                rows.append(open_rows.pop(prefix))
        for prefix, name in table.items():
            if prefix not in open_rows:
                open_rows[prefix] = {"prefix": prefix, "carrier": name, "since": day,
                                     "until": "", "since_commit": commit,
                                     "until_commit": ""}
    rows += open_rows.values()
    rows.sort(key=lambda row: (row["prefix"], row["since"]))
    return rows


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    writer = csv.DictWriter(sys.stdout, ["prefix", "carrier", "since", "until",
                                         "since_commit", "until_commit"],
                            lineterminator="\n")
    writer.writeheader()
    writer.writerows(periods(sys.argv[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
