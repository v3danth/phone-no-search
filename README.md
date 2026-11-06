# phone-no-search

Offline phone number lookup that returns numverify-style JSON, with no API
key, quota or network calls. It also builds a Google search string for a
number.

## Setup

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

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
     "series_source": "in-mob-prefix"}

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
| Indian mobile state and carrier | `data/in_mobile_series.csv`, the first 4 digits mapped to the DoT allocation (see `data/README.md`) |
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
| 918306XXXXXX | India, Airtel | Rajasthan, Airtel (prefix not in our data) |
| 9180XXXXXXXX | Bangalore, Karnataka, landline | Bengaluru, landline |
| 1650XXXXXXX | California, no carrier | Palo Alto, T-Mobile |

Limits, which numverify shares:
- **"Valid" means the number fits the numbering plan, not that it is in
  use.** 6362… and 6363… both pass.
- **Carrier and state are the original allocation.** People can keep their
  number when they switch carriers (MNP), so the current carrier may differ.
- **No owner details.** This tool reports facts about the number, not the
  person.

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

No public 2025–26 allocation list was found; the newest press coverage is
from 2022. Wikipedia's per-prefix tables (edited Oct 2025) were the best
current source.

Possible next steps:
- Fill the ~1,750 missing prefixes and move to 5-digit precision from DoT
  and TelecomTalk notices.
- Add a `--country IN` default so bare 10-digit numbers work.
- Add an optional HLR provider for the current carrier and live status.
- Add a small web UI.

## Legal and data rules

- **Do not use leaked or breached data** (for example the 2021 Domino's
  India leak), and do not scrape personal details such as names or
  addresses. Linking numbers to people without consent is a privacy harm
  and likely illegal in India.
- **DPDP Act 2023** (Digital Personal Data Protection Act): India's data
  protection law. It requires consent and purpose limitation for personal
  data, gives people rights to access, correct and erase their data, and
  is enforced by the Data Protection Board with fines up to ₹250 crore.
  The DPDP Rules were notified in Nov 2025 and phase in through about
  2027. Number-level facts (prefix, circle, carrier) are not personal data.
  If you store lookup history, you need a privacy notice and a deletion
  policy.
- **IT Act 2000**: covers unauthorised access and dealing in stolen data.
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
    data/README.md            data sources, licence, refresh steps
    scripts/parse_wiki.py     parse the Wikipedia tables into CSV
    scripts/merge.py          merge sources (Wikipedia first)

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
