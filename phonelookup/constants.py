"""Static tables, file paths, and field names shared across the package.

Kept in one place so a new data file or operator code is a one-line change and
every module reads the same source of truth.
"""

from __future__ import annotations

from pathlib import Path

from phonenumbers import PhoneNumberType

# Repository root (the package lives one level below it, the data beside it).
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

SERIES_CSV = DATA / "in_mobile_series.csv"
BLOCKS_CSV = DATA / "in_mobile_blocks.csv"
MSC_CSV = DATA / "in_mobile_msc.csv"
LIBPN_CSV = DATA / "in_libphonenumber_history.csv"
COAI_CSV = DATA / "coai_msc.csv"
LEVELS2011_CSV = DATA / "in_mobile_levels_2011.csv"
# Optional offline list of numbers reported as spam. A local file, not an API:
# if it is absent the spam-report flag is simply never set.
SPAM_CSV = DATA / "spam_numbers.csv"
# Community MCC/MNC -> operator list (musalbas/mcc-mnc-table). The
# network-identity axis, not the numbering plan: it names who registered a
# serving MCC/MNC, which lags porting and mergers. Surfaced as its own field.
MCC_MNC_CSV = DATA / "mcc_mnc.csv"
# Dated histories of the two 4-digit sources (scripts/series_history.py).
SERIES_HISTORY_CSV = {
    "wikipedia": DATA / "wiki_series_history.csv",
    "in-mob-prefix": DATA / "in_mob_prefix_history.csv",
}
# Raw per-number log of probe samples (synthetic block numbers). Safe to commit.
TWILIO_CHECKS_CSV = DATA / "twilio_checks.csv"
# Derived block rows a probe/sweep suggests, in in_mobile_blocks.csv schema.
SUGGESTED_CSV = DATA / "twilio_suggested.csv"

# --live results are cached here; holds real numbers people queried, so it is
# git-ignored like .env and never published.
LIVE_CACHE = ROOT / "live_cache.json"
ENV_FILE = ROOT / ".env"

# The numverify free plan only supports plain HTTP; paid plans set NUMVERIFY_URL.
NUMVERIFY_URL = "http://apilayer.net/api/validate"
# Twilio Lookup v2; --live appends the number as a path segment.
TWILIO_LOOKUP_URL = "https://lookups.twilio.com/v2/PhoneNumbers"
# Local service queried for every valid number in the normal lookup flow.
FLOW_URL = "http://localhost:8080/flow"
FLIPKART_URL = "https://2.rome.api.flipkart.com/api/6/user/signup/status"

# Twilio Lookup field packages and retry budget.
LTI_FIELD = "line_type_intelligence"
LINE_STATUS_FIELD = "line_status"
SIM_SWAP_FIELD = "sim_swap"
CALL_FORWARDING_FIELD = "call_forwarding"
TWILIO_RETRIES = 4  # attempts per lookup before giving up (429/5xx backoff)

TWILIO_CHECKS_FIELDS = ("checked", "number", "live_carrier", "live_code",
                        "mcc", "mnc", "line_type", "offline_carrier",
                        "location", "error")
SUGGESTED_FIELDS = ("prefix", "operator", "circle", "source", "updated", "note")

LINE_TYPES = {
    PhoneNumberType.MOBILE: "mobile",
    PhoneNumberType.FIXED_LINE: "landline",
    PhoneNumberType.FIXED_LINE_OR_MOBILE: "landline_or_mobile",
    PhoneNumberType.TOLL_FREE: "toll_free",
    PhoneNumberType.PREMIUM_RATE: "premium_rate",
    PhoneNumberType.SHARED_COST: "shared_cost",
    PhoneNumberType.VOIP: "voip",
    PhoneNumberType.PERSONAL_NUMBER: "personal_number",
    PhoneNumberType.PAGER: "pager",
    PhoneNumberType.UAN: "uan",
    PhoneNumberType.VOICEMAIL: "voicemail",
}

IN_OPERATORS = {
    "AT": "Bharti Airtel",
    "RJ": "Reliance Jio",
    "VI": "Vodafone Idea (Vi)",
    "CG": "BSNL/MTNL",
}

# Licensees in old DoT letters that no longer run a mobile network. Their
# numbers were ported out or taken over, so they are never the final answer
# while a current-operator source has the prefix.
IN_FORMER_OPERATORS = {
    "Aircel": "Aircel (closed 2018)",
    "Dishnet": "Aircel/Dishnet (closed 2018)",
    "RCom": "Reliance Communications (closed 2017)",
    "MTS": "MTS/Sistema (merged into RCom 2017)",
    "Tata": "Tata Teleservices (merged into Airtel 2019)",
    "Uninor": "Uninor/Telenor (merged into Airtel 2018)",
    "Videocon": "Videocon (closed 2016)",
    "Loop": "Loop Mobile (closed 2014)",
    "BPL": "BPL Mobile (merged ~2008)",
    "S Tel": "S Tel (closed 2012)",
    "Etisalat": "Etisalat DB (closed 2012)",
    "Allianze": "Allianz Infratech (licence cancelled 2012)",
    "HFCL": "HFCL/Quadrant (closed 2016)",
    "BTA Cellcom": "BTA Cellcom",
    "RingCentral": "RingCentral (internet telephony)",
}

IN_CIRCLES = {
    "AP": "Andhra Pradesh & Telangana",
    "AS": "Assam",
    "BR": "Bihar & Jharkhand",
    "DL": "Delhi",
    "GJ": "Gujarat",
    "HP": "Himachal Pradesh",
    "HR": "Haryana",
    "JK": "Jammu & Kashmir",
    "KA": "Karnataka",
    "KL": "Kerala",
    "MH": "Maharashtra & Goa",
    "MP": "Madhya Pradesh & Chhattisgarh",
    "NE": "North East",
    "OR": "Odisha",
    "PB": "Punjab",
    "RJ": "Rajasthan",
    "TN": "Tamil Nadu",
    "UE": "Uttar Pradesh (East)",
    "UW": "Uttar Pradesh (West)",
    "UP": "Uttar Pradesh",
    "WB": "West Bengal",
    "MU": "Mumbai",
    "KO": "Kolkata",
    "CH": "Chennai",
}

# Every spelling libphonenumber has used for an Indian carrier since 2013,
# mapped to the operator codes used elsewhere.
LIBPN_OPERATORS = {
    "Airtel": "AT", "AirTel": "AT", "AIRTEL": "AT", "Hexacom": "AT",
    "Bharti Hexacom": "AT",
    "Reliance Jio": "RJ",
    "Idea": "VI", "IDEA": "VI", "Idea Cellular Ltd": "VI", "Vodafone": "VI",
    "Vodafone IN": "VI", "VODAFONE": "VI",
    "CellOne": "CG", "Cellone": "CG", "BSNL MOBILE": "CG", "BSNL": "CG",
    "BSNL Mobile": "CG", "MTNL": "CG", "DOLPHIN": "CG",
    "Reliance": "RCom", "RELIANCE": "RCom",
    "Aircel": "Aircel", "AIRCEL": "Aircel",
    "Dishnet": "Dishnet", "Dishnet Wireless": "Dishnet",
    "Tata Docomo": "Tata", "TATA DOCOMO": "Tata", "TATA": "Tata",
    "Telewings": "Uninor", "Telenor": "Uninor", "Uninor": "Uninor",
    "UNITECH": "Uninor",
    "Sistema": "MTS", "SISTEMA": "MTS",
    "Videocon": "Videocon", "VIDEOCON": "Videocon",
    "Videocon Datacom": "Videocon",
    "Loop Mobile": "Loop",
    "ETISALAT": "Etisalat", "Etisalat DB(cheers)": "Etisalat",
    "S TEL": "S Tel", "S Tel": "S Tel",
}

# Twilio Lookup returns freeform carrier strings such as "Airtel India -
# Tamil Nadu (94) (Bharti Airtel)", matched as case-insensitive substrings.
TWILIO_OPERATORS = (
    ("jio", "RJ"),
    ("airtel", "AT"),
    ("bharti", "AT"),
    ("vodafone", "VI"),
    ("idea", "VI"),
    ("bsnl", "CG"),
    ("mtnl", "CG"),
)

# Search engines that accept an "a" OR "b" phrase query in a URL parameter.
SEARCH_ENGINES = {
    "Google": "https://www.google.com/search?q=",
    "Bing": "https://www.bing.com/search?q=",
    "DuckDuckGo": "https://duckduckgo.com/?q=",
    "Yandex": "https://yandex.com/search/?text=",
    "Brave": "https://search.brave.com/search?q=",
    "Startpage": "https://www.startpage.com/sp/search?query=",
    "Mojeek": "https://www.mojeek.com/search?q=",
}
