# phone-no-search

Phone number lookup that returns numverify-style JSON using offline numbering
data, and also builds a Google search string for a number. Each normal lookup
also POSTs the valid number to a local JSON service at `http://localhost:8080/flow`.

## Setup

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

Run the tests (standard library only; they use libphonenumber's example
numbers, never real ones):

    .venv/bin/python -m unittest discover -s tests

## Usage

Numbers must include the country code (`91…` for India, `1…` for US).
Without it, `9738XXXXXX` is read as `+973…` (Bahrain).

    .venv/bin/python -m phonelookup 919738XXXXXX
    .venv/bin/python -m phonelookup --pretty 919738XXXXXX 1650XXXXXXX
    .venv/bin/python -m phonelookup --file numbers.txt
    echo 9180XXXXXXXX | .venv/bin/python -m phonelookup
    .venv/bin/python -m phonelookup --dork 919738XXXXXX

Normal lookups include the local service's parsed JSON response in a `flow`
field. The service must be running at `localhost:8080`; if it is unavailable,
returns an HTTP error, or sends invalid JSON, the lookup still prints its
offline result and includes the failure in `flow.error`. This local request
uses the number in E.164 format (for example, `+919003488880`). No external
provider is contacted unless `--numverify` or `--live` is used.

Example output:

    {"valid": true, "number": "919738XXXXXX", "local_format": "09738XXXXXX",
     "international_format": "+919738XXXXXX", "country_prefix": "+91",
     "country_code": "IN", "country_name": "India", "location": "Karnataka",
     "carrier": "Vodafone Idea (Vi)", "line_type": "mobile",
     "current_carrier": null, "series_source": "in-mob-prefix",
     "updated": "2026-11-06"}

For Indian mobiles `carrier` is the **original DoT allocation**. A
subscriber can keep the number and move to another operator (MNP), so the
live operator may differ; `current_carrier` is `null` because that is only
knowable from an HLR / number-portability lookup, which this offline tool
does not do. A `carrier_note` field says the same in the output.

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
    .venv/bin/python -m phonelookup --numverify --pretty 919738XXXXXX

`--live` calls Twilio Lookup (1 billed request per number) for live HLR
carrier data and prints `{"offline": …, "live": …}`. Unlike the offline
tables, which only know the *allocated* operator, the live `carrier` plus
`mobile_country_code`/`mobile_network_code` show the *current* operator,
so a ported number (MNP) shows up as a mismatch. Needs `TWILIO_ACCOUNT_SID`
and `TWILIO_AUTH_TOKEN` in `.env` or the environment. Results are cached to
`live_cache.json` (git-ignored, since it holds specific real numbers);
`--refresh` re-queries and overwrites the cache.

    .venv/bin/python -m phonelookup --live --pretty 919738XXXXXX

`--line-status` (with `--live`) also requests Twilio's `line_status` package,
adding a `line_status` block (`reachable`/`unreachable`/`unknown`: whether the
handset is currently on and in coverage). It is a gated field billed on top of
the base lookup; asking for it re-queries a number already cached without it.

When a live result reports a serving `mobile_country_code`/`mobile_network_code`,
the output also gains a `network_registry` block resolved **offline** from a
bundled community MCC/MNC list (`data/mcc_mnc.csv`, from musalbas/mcc-mnc-table).
It names the operator that registered that network code — a separate axis from
the DoT numbering plan. Treat it as a hint, not ground truth: the list lags
porting and operator mergers, so Twilio's `carrier` remains authoritative. Its
India (MCC 404/405) rows are all pre-2010 operators, so India hits are tagged
`"historical": true` with a note saying so; because the list predates Jio and
the Vi/Airtel consolidations, a *current* Indian number's serving MNC often is
not listed and the field is simply omitted. The field is also omitted when the
code is unknown or the file is absent.

`--sim-swap` and `--call-forwarding` (with `--live`) add Twilio's `sim_swap`
and `call_forwarding` fields to the live result. Their Twilio response objects
are included as `sim_swap` and `call_forwarding`; requesting these fields also
re-queries cached numbers that do not already include them. These are additional
paid Lookup fields. Call Forwarding is in private beta, requires carrier
registration/approval, and is currently limited to major UK carriers; Twilio
returns `null` for unsupported numbers.

    .venv/bin/python -m phonelookup --live --sim-swap --call-forwarding --pretty 919738XXXXXX

To request **all Twilio fields currently supported by this app** in one Lookup
request per number, combine all three optional-field flags:

    .venv/bin/python -m phonelookup --live --line-status --sim-swap --call-forwarding --pretty 919738XXXXXX

This includes the default `line_type_intelligence` data plus `line_status`,
`sim_swap`, and `call_forwarding`. “All” means all packages this app currently
requests; it does not guarantee every package returns data. Availability depends
on the number, country/carrier coverage, and Twilio account permissions, and
optional packages may add charges. `--numverify` is a separate provider call,
not part of this single Twilio request.

`--probe-block` treats its arguments as block prefixes instead of numbers.
It samples a few numbers per block (`--samples N`, default 3) over Twilio,
takes the majority carrier, and prints a suggested `in_mobile_blocks.csv`
row when the sample agrees (a lone ported number is outvoted; a split
sample is flagged inconclusive). This is current-holder evidence, not a DoT
allocation. Every sampled number is appended to `data/twilio_checks.csv`.

    .venv/bin/python -m phonelookup --probe-block --samples 3 83170 83171

`--dork` prints a query covering the common written forms of the number
(with or without +91, spaces, a leading 0) plus a ready-made search URL
for each engine: Google, Bing, DuckDuckGo, Yandex, Brave, Startpage and
Mojeek.

### Spam / caller category

A valid number may also get a `spam` block, built offline (no API, no
personal data):

- `category` — set when the number is in a TRAI-designated caller series:
  `140`-series (registered telemarketing / promotional callers) or
  `1600`-series (transactional / service callers, from 2024). These classify
  the *kind of caller*, straight from the numbering plan.
- `reported_spam` — set when the number appears in an optional local list at
  `data/spam_numbers.csv`. This is a file you supply, not a lookup service; if
  it is absent the flag is simply never set. Columns: `number` (full, e.g.
  `919886012345`), `source`, `updated`.

The block is omitted entirely when nothing applies, so ordinary lookups are
unchanged.

## How it works

| Field | Where it comes from |
|---|---|
| valid, formats, country, line type | Google libphonenumber (`phonenumbers`), which bundles each country's ITU numbering plan |
| landline location (e.g. Bangalore) | libphonenumber geocoder, from the area (STD) code |
| Indian mobile state and carrier | DoT MSC allocation letters per 5-digit block (`data/in_mobile_msc.csv`), hand-checked rows (`data/in_mobile_blocks.csv`), libphonenumber's carrier data through its git history 2013-2026 (`data/in_libphonenumber_history.csv`, no circle), the 4-digit series table (`data/in_mobile_series.csv`), and DoT's c.2011 consolidated "MSC levels" list (`data/in_mobile_levels_2011.csv`, the stalest baseline); newest dated entry wins (see `data/README.md`) |
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
- DoT's c.2011 all-India "LIST OF MSC & SP CODES ALLOTTED TO ALL" is
  added (`data/in_mobile_levels_2011.csv`, from Scribd doc 74759473 via
  `scripts/parse_levels_2011.py`). Its text layer is clean, so a
  downloaded PDF parses directly. It is undated and every operator on it
  has since merged or closed, so it is the stalest baseline: it overlaps
  the existing sources on every block (0 new blocks) and only adds a
  c.2011 data point to `history`.
- TODO: the two other consolidated Scribd lists still differ in date:
  as on 30.06.2014 (87 pages,
  https://www.scribd.com/document/340595713/Msc-Code-All-Operator) and
  as on 31.12.2010
  (https://www.scribd.com/doc/53690984/MSC-and-SP-Codes-as-on-31-12-10).
  Their viewers scramble the text (font substitution), so do not scrape
  them: download while signed in (Google SSO failed), or use screenshots
  of the pages, then parse like the 2011 list with the list's date.
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

    phonelookup/              package (constants, tables, history, india, core,
                              dork, providers/, cli)
    pyproject.toml            packaging, dependency pins, ruff + mypy config
    requirements.txt          phonenumbers==9.0.42
    data/in_mobile_series.csv Indian 4-digit series table
    data/in_mobile_msc.csv    DoT MSC letters, every 5-digit block with date
    data/in_mobile_blocks.csv hand-checked rows no DoT letter covers
    data/in_libphonenumber_history.csv  libphonenumber carriers by date
    data/wiki_series_history.csv        Wikipedia 4-digit table by month, 2009-
    data/in_mob_prefix_history.csv      in-mob-prefix by commit
    data/coai_msc.csv         COAI metro-circle MSC listing (undated)
    data/in_mobile_levels_2011.csv  DoT c.2011 all-India MSC levels (Scribd)
    data/numverify_checks.csv numverify answers for checked blocks
    data/twilio_checks.csv    Twilio HLR answers for --probe-block samples
    data/spam_numbers.csv     optional local spam-report list (you supply it)
    data/dot_msc/             the DoT letters (PDF) and their index
    data/README.md            data sources, licence, refresh steps
    scripts/parse_wiki.py     parse the Wikipedia tables into CSV
    scripts/merge.py          merge sources (Wikipedia first)
    scripts/msc_withdrawals.py add withdrawals implied by DoT corrigenda
    scripts/libphonenumber_history.py  rebuild libphonenumber history
    scripts/series_history.py rebuild Wikipedia / in-mob-prefix history
    scripts/coai_msc.py       extract COAI's MSC table
    scripts/parse_levels_2011.py  parse DoT's c.2011 MSC levels PDF
    scripts/check_blocks.py   check blocks against numverify/Veriphone

## Sources

- https://en.wikipedia.org/wiki/Mobile_telephone_numbering_in_India
- https://github.com/hstsethi/in-mob-prefix
- https://github.com/google/libphonenumber
- https://telecomtalk.info/reliance-jio-msc-code-circles/357322
- https://telecomtalk.info/dot-allocated-msc-codes-to-reliance-jio/496355/
- https://telecomtalk.info/idea9133-airtel8942-series-new-msc-codes/132898/
- https://www.scribd.com/doc/74759473/All-India-Mobile-Levels (DoT c.2011 MSC levels)
- https://ipqs.com/free-hlr-lookup
- https://seven.io/en/products/number-validation/hlr-lookup/
- https://www.loqate.com/en-us/phone-validation/product-detail/
