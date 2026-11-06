# phone-no-search

Offline phone number lookup that returns numverify-style JSON, with no API
key, quota or network calls. It also builds a Google search string for a
number.

## Setup

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

Run the tests (standard library only; they use libphonenumber's example
numbers, never real ones):

    .venv/bin/python -m unittest discover -s tests

## Usage

Numbers must include the country code (`91…` for India, `1…` for US).
Without it, `9738XXXXXX` is read as `+973…` (Bahrain).

    .venv/bin/python phonelookup.py 919738XXXXXX
    .venv/bin/python phonelookup.py --pretty 919738XXXXXX 1650XXXXXXX
    .venv/bin/python phonelookup.py --file numbers.txt
    echo 9180XXXXXXXX | .venv/bin/python phonelookup.py
    .venv/bin/python phonelookup.py --dork 919738XXXXXX

Example output:

    {"valid": true, "number": "919738XXXXXX", "local_format": "09738XXXXXX",
     "international_format": "+919738XXXXXX", "country_prefix": "+91",
     "country_code": "IN", "country_name": "India", "location": "Karnataka",
     "carrier": "Vodafone Idea (Vi)", "line_type": "mobile",
     "series_source": "in-mob-prefix", "updated": "2026-11-06"}

`updated` is the date behind the answer: the DoT letter date for
`dot.gov.in`, the check date for `numverify`, the fetch date for the
4-digit tables. When more than one source covers the number, `history`
lists every entry (oldest letter first, the one used last), each with its
own `source` and `updated`; DoT entries also give `kind` (allocation,
corrigendum, withdrawal) and the `letter` URL. Example, a block DoT has
reused twice:

    "history": [
      {"carrier": "Reliance Jio", "location": "Odisha", "source": "wikipedia", ...},
      {"carrier": "Reliance Communications (closed 2017)", "location": "Bihar & Jharkhand",
       "source": "dot.gov.in", "updated": "2012-05-16", ...},
      {"carrier": "Reliance Jio", "location": "Odisha", "source": "dot.gov.in", "updated": "2017-08-23", ...},
      {"carrier": "Bharti Airtel", "location": "Assam", "source": "dot.gov.in", "updated": "2026-09-28", ...}
    ]

`--numverify` also calls the numverify API (1 request per number) and
prints `{"offline": …, "numverify": …, "agree": {…}}`. The `agree` block
shows which of `valid`, `line_type`, `location` and `carrier` match. Put the
key in `.env` (copy `.env.example`) or export `NUMVERIFY_KEY`. The free
plan is HTTP-only, so the key is sent unencrypted; set `NUMVERIFY_URL` to
the https endpoint if you are on a paid plan.

    cp .env.example .env    # then fill in NUMVERIFY_KEY
    .venv/bin/python phonelookup.py --numverify --pretty 919738XXXXXX

`--dork` prints a Google query covering the common written forms of the
number (with or without +91, spaces, a leading 0) plus a search URL.

## How it works

| Field | Where it comes from |
|---|---|
| valid, formats, country, line type | Google libphonenumber (`phonenumbers`), which bundles each country's ITU numbering plan |
| landline location (e.g. Bangalore) | libphonenumber geocoder, from the area (STD) code |
| Indian mobile state and carrier | DoT MSC allocation letters per 5-digit block (`data/in_mobile_msc.csv`), hand-checked rows (`data/in_mobile_blocks.csv`), libphonenumber's carrier data through its git history 2013-2026 (`data/in_libphonenumber_history.csv`, no circle), and the 4-digit series table (`data/in_mobile_series.csv`); newest dated entry wins (see `data/README.md`) |
| other carriers | libphonenumber carrier data |

For Indian 10-digit numbers starting 6–9 that are in the series table, the
tool sets `line_type` to `mobile` and uses the table's state and carrier.
Mobiles not in the table show location `India` rather than a wrong STD-code
city.

## Accuracy (checked 2026-11-06 against numverify)

| Number | This tool | numverify |
|---|---|---|
| 917904XXXXXX | Tamil Nadu, Jio | Tamil Nadu, Jio |
| 918250XXXXXX | West Bengal, Jio | West Bengal, Jio |
| 919164XXXXXX | Karnataka, Vi | Karnataka, Vi |
| 916362XXXXXX | Karnataka, Jio | Karnataka, Jio |
| 916363XXXXXX | Karnataka, Jio | Karnataka, Jio |
| 919886XXXXXX | Karnataka, Vi | Karnataka, Vi |
| 918317XXXXXX | UP West, Vi (now Karnataka, Jio via block 83174) | Karnataka, Jio |
| 918306XXXXXX | India, Airtel | Rajasthan, Airtel (prefix not in our data) |
| 9180XXXXXXXX | Bangalore, Karnataka, landline | Bengaluru, landline |
| 1650XXXXXXX | California, no carrier | Palo Alto, T-Mobile |

Limits, which numverify shares:
- **"Valid" means the number fits the numbering plan, not that it is in
  use.** 6362… and 6363… both pass.
- **Carrier and state are the original allocation.** People can keep their
  number when they switch carriers (MNP), so the current carrier may differ.

## Research notes

How commercial verifiers get their data:
- **Numbering plans** (free): ITU and national regulators. This is what
  libphonenumber packages.
- **Indian MSC / series codes** (free, scattered): DoT gives operators
  5-digit blocks per telecom circle. These are published in DoT notices and
  reported by TelecomTalk. There is no single official master list.
- **US number blocks**: NANPA (free); LERG routing data (paid).
- **Current carrier, active status, roaming**: HLR lookup, a live query to
  the carrier's subscriber database. Paid, roughly ≤1¢ per lookup, from
  vendors such as IPQS, Seven.io and Loqate. This is the only way to see
  ported numbers.

DoT's own site search (`https://www.dot.gov.in/search`, "allotment msc
codes") lists the allocation letters with PDFs, 2007 to Oct 2026; these
are in `data/dot_msc/`. With libphonenumber's 5-digit carrier data and
the 4-digit tables, 25,160 of the 40,000 5-digit mobile blocks resolve to
a current operator (22,856 before libphonenumber was added).

numverify and Veriphone (checked 2026-11-06) are both prefix tables, not
live lookups. Veriphone's Indian answers are exactly libphonenumber's
(carrier, "fixed_line_or_mobile", landline-style region), so it adds
nothing offline. On the 22 blocks numverify answered, this tool's carrier
matches all 22 without using the numverify rows (18 before
libphonenumber), and the circle matches 16; the rest show "India".

Possible next steps:
- Fill the remaining blocks with no data. Most empty ones are probably
  unallocated (6x, 71xx, prefixes that start with an STD code); about 250
  are real gaps. DoT letters listed without a PDF are the main source
  still missing (RTI to DoT Access Services Wing).
- TODO: add the consolidated DoT "MSC and SP codes" lists on Scribd:
  as on 30.06.2014 (87 pages,
  https://www.scribd.com/document/340595713/Msc-Code-All-Operator) and
  as on 31.12.2010
  (https://www.scribd.com/doc/53690984/MSC-and-SP-Codes-as-on-31-12-10).
  Scribd's viewer scrambles the text (font substitution), so do not
  scrape it: download while signed in with a password (Google SSO
  failed), or use screenshots of the pages, then extract like the DoT
  letters into data/in_mobile_msc.csv with the list's date.
- Add a `--country IN` default so bare 10-digit numbers work.
- Add an optional HLR provider for the current carrier and live status.
- Add a small web UI.

## Legal and data rules

- **Do not use leaked or breached data** (for example the 2021 Domino's
  India leak).
- **Data licences**: `data/in_mobile_series.csv` is CC BY-SA 4.0
  (Wikipedia and hstsethi/in-mob-prefix). Credit the sources if you share
  it.
- **numverify key**: the free tier only works over plain HTTP, so the key
  travels unencrypted. Keep it server-side, and rotate the one that was
  pasted into chat.

This is a general overview, not legal advice.

## Personal security playbook

`SECURITY_PLAYBOOK.md` is a tiered plan for phones, emails and identity
(vault / identity / social / public): threat model, setup checklist,
maintenance and incident steps.

## Files

    phonelookup.py            CLI
    requirements.txt          phonenumbers==9.0.42
    data/in_mobile_series.csv Indian 4-digit series table
    data/in_mobile_msc.csv    DoT MSC letters, every 5-digit block with date
    data/in_mobile_blocks.csv hand-checked rows no DoT letter covers
    data/in_libphonenumber_history.csv  libphonenumber carriers by date
    data/wiki_series_history.csv        Wikipedia 4-digit table by month, 2009-
    data/in_mob_prefix_history.csv      in-mob-prefix by commit
    data/coai_msc.csv         COAI metro-circle MSC listing (undated)
    data/numverify_checks.csv numverify answers for checked blocks
    data/dot_msc/             the DoT letters (PDF) and their index
    data/README.md            data sources, licence, refresh steps
    scripts/parse_wiki.py     parse the Wikipedia tables into CSV
    scripts/merge.py          merge sources (Wikipedia first)
    scripts/msc_withdrawals.py add withdrawals implied by DoT corrigenda
    scripts/libphonenumber_history.py  rebuild libphonenumber history
    scripts/series_history.py rebuild Wikipedia / in-mob-prefix history
    scripts/coai_msc.py       extract COAI's MSC table
    scripts/check_blocks.py   check blocks against numverify/Veriphone

## Sources

- https://en.wikipedia.org/wiki/Mobile_telephone_numbering_in_India
- https://github.com/hstsethi/in-mob-prefix
- https://github.com/google/libphonenumber
- https://telecomtalk.info/reliance-jio-msc-code-circles/357322
- https://telecomtalk.info/dot-allocated-msc-codes-to-reliance-jio/496355/
- https://telecomtalk.info/idea9133-airtel8942-series-new-msc-codes/132898/
- https://ipqs.com/free-hlr-lookup
- https://seven.io/en/products/number-validation/hlr-lookup/
- https://www.loqate.com/en-us/phone-validation/product-detail/
