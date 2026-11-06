# data/

## in_mobile_series.csv

Maps the first 4 digits of an Indian mobile number to its original operator
and telecom circle (DoT series allocations). Columns: series, operator,
circle, source, updated. A value like `BR/WB` means the 4-digit block is
split. `updated` is the day the sources were fetched.

Sources (fetched 2026-11-06), in priority order:
1. `wikipedia`: tables in "Mobile telephone numbering in India",
   https://en.wikipedia.org/wiki/Mobile_telephone_numbering_in_India
   (CC BY-SA 4.0). 2,209 rows.
2. `in-mob-prefix`: https://github.com/hstsethi/in-mob-prefix (CC BY 4.0),
   used only where Wikipedia has no complete entry. 41 rows.
3. `partial`: only an operator or only a circle was known. 43 rows.

Because it includes Wikipedia content, this file is CC BY-SA 4.0: credit the
sources above and keep the same licence if you redistribute it.

Where both sources had a value they disagreed about 10% of the time
(70 operator, 95 circle mismatches out of 1,661). Wikipedia matched
numverify on the one checked conflict (7904), so it wins.

Caveats: ~2,250 of 4,000 prefixes covered; DoT really allocates 5-digit
blocks; results show the original allocation, not the current carrier.

## in_mobile_msc.csv

Every 5-digit block in DoT's mobile MSC-code letters, one row per block
per letter (21,815 rows, 17,544 blocks). Columns: block, operator, circle,
date, kind, letter, note.
- `operator`: AT, RJ, VI, CG, or a closed licensee (Aircel, RCom, Tata,
  Uninor, Videocon, MTS, Loop, ...). Idea, Vodafone, Hutch and Spice are VI.
- `date`: the date printed on the letter (or the signature date).
- `kind`: allocation, corrigendum (the new block; `note` says which block
  it replaces) or withdrawal.
- `letter`: the PDF's URL on dot.gov.in. Copies are in `dot_msc/`.

The same block can appear several times: DoT reuses blocks after a
licence ends, and corrigenda move them. The lookup sorts a block's rows by
date and uses the newest. 16,174 rows come from DoT's consolidated "List
of MSC Codes as on 16-05-2012"; the rest are individual letters from
2007 to Oct 2026.

How it was made: the PDF list came from the dot.gov.in site search
(`/cms/wp-json/custom/api/search?s=allotment msc codes`, 136 files with
attachments). The letters are mostly scans, so each was read page by page
by Claude, with faint digits checked at high resolution. Blocks whose
digits could not be read were left out rather than guessed (about 25
cases, mostly faint 2012 scans). There is no script to regenerate it;
spot-check new rows against the linked letter. After adding rows, run
`python3 scripts/msc_withdrawals.py`: it adds a withdrawal row for every
block a corrigendum says it replaced (74 so far), so a cancelled
allocation is never the answer.

Not covered: allocation letters DoT lists without an attached PDF
(for example Airtel Delhi 92170-92179, 2025, kept in in_mobile_blocks.csv).

## dot_msc/

The 136 DoT PDFs (38 MB) and `index.csv` (date, file, title, url).
Government of India documents, kept so every row in in_mobile_msc.csv can
be checked offline.

## in_mobile_blocks.csv

Hand-added rows for things no letter on dot.gov.in covers: DoT letters
listed without a PDF, and live checks (`numverify`, `updated` = check
date). Columns: prefix (4 or 5 digits), operator, circle, source, updated,
note. They are sorted by date together with the DoT letter rows.

A live check of one number may just show a ported number (MNP), and a
5-digit row relabels all 10,000 numbers in the block, so say in `note` how
many numbers were checked.

## in_libphonenumber_history.csv

libphonenumber's Indian carrier data (`resources/carrier/en/91.txt` in
https://github.com/google/libphonenumber, Apache 2.0) through every commit
that changed it: 58 commits, 2013-09-30 to 2026-10-22 (release 9.0.42).
One row per period a prefix kept the same carrier name. Columns: prefix
(national, 2-5 digits), carrier (as spelled then), since, until (empty =
still listed), since_commit, until_commit. 6,937 periods; India updates
almost stopped after 2019.

Refresh:
    git clone --filter=blob:none --no-checkout https://github.com/google/libphonenumber.git
    python3 scripts/libphonenumber_history.py libphonenumber > data/in_libphonenumber_history.csv

## wiki_series_history.csv, in_mob_prefix_history.csv

Dated history of the two 4-digit sources, built by
`scripts/series_history.py`. Columns: prefix, operator, circle, since,
until (empty = current), since_ref, until_ref.
- Wikipedia: the last revision of each month of "Mobile telephone
  numbering in India" from 2009-10 (251 monthly snapshots fetched through
  the MediaWiki API; dates are accurate to the month). Old operator codes
  (VF, ID, RG, TD, AC, ...) are mapped to current ones; unclear codes are
  left blank. Reverts within 3 months (vandalism, broken edits) are
  merged away; longer swings are kept. 4,268 periods.
- in-mob-prefix: every commit that changed data/ (2024-10 to 2025-11).

The lookup dates the 4-digit answer from when its current value first
appeared and lists earlier values as "superseded".

Refresh: fetch monthly revisions (see the script docstring for the JSON
shape) and `git clone https://github.com/hstsethi/in-mob-prefix`, then
    python3 scripts/series_history.py wiki snapshots.json > data/wiki_series_history.csv
    python3 scripts/series_history.py git in-mob-prefix > data/in_mob_prefix_history.csv

## How the sources combine

For each number the lookup collects the dated entries — DoT letter rows,
libphonenumber's carrier on each date it changed (longest listed prefix,
spelling changes ignored, a dropped prefix as "removed"), and
blocks-file rows — sorts them by date, and uses the newest. The undated
4-digit series row is the baseline; it wins only when the newest dated
entry is a closed operator, a withdrawal or a removal. libphonenumber
gives no circle, so the location comes from the newest entry of any
source naming the same operator, or is "India" if there is none. Every entry is
returned under `history` with its own source and date.

## Refresh

    curl -sL -o wiki.txt 'https://en.wikipedia.org/w/index.php?title=Mobile_telephone_numbering_in_India&action=raw'
    python3 scripts/parse_wiki.py wiki.txt > wiki_series.csv
    python3 scripts/merge.py wiki_series.csv <in-mob-prefix merged csv> YYYY-MM-DD > data/in_mobile_series.csv
