"""phonelookup: offline, numverify-style phone number facts with optional live
HLR, block probing, and OSINT helpers.

Re-exports the public API so callers write `phonelookup.lookup(...)`; the real
code lives in the submodules grouped by responsibility.
"""

from __future__ import annotations

# Submodules kept importable so tests and callers can reach them by name.
from . import constants, history, providers, tables  # noqa: F401
from .agreement import agreement
from .cli import build_parser, main, parse_range
from .config import env_setting, twilio_creds
from .constants import (
    CALL_FORWARDING_FIELD,
    IN_CIRCLES,
    IN_OPERATORS,
    LINE_STATUS_FIELD,
    LTI_FIELD,
    SEARCH_ENGINES,
    SERIES_HISTORY_CSV,
    SIM_SWAP_FIELD,
)
from .core import lookup, parse_number
from .dork import dork, dork_urls
from .history import (
    extra_series_history,
    india_mobile_history,
    is_current,
    latest_location,
    libphonenumber_entries,
    series_entries,
)
from .india import caller_category, india_overrides, unallocated_note
from .naming import (
    expand_codes,
    normalized,
    operator_name,
    operator_names,
    twilio_circle_code,
    twilio_operator_code,
)
from .providers.flow import flipkart_lookup, flow_lookup, flow_payload
from .providers.numverify import numverify
from .providers.twilio import (
    BudgetExceeded,
    aggregate_block,
    append_twilio_checks,
    billed_lookup,
    block_sample_numbers,
    blocks_to_refresh,
    cached_twilio_lookup,
    live_cache_load,
    live_cache_save,
    probe_block,
    save_suggested_rows,
    sweep_blocks,
    twilio_line_status,
    twilio_lookup,
)
from .registry import network_registry
from .spam import spam_signal
from .tables import (
    block_table,
    coai_table,
    levels2011_table,
    libpn_table,
    mcc_mnc_table,
    msc_table,
    series_history,
    series_table,
    spam_table,
    twilio_table,
)

__all__ = [
    "BudgetExceeded",
    "CALL_FORWARDING_FIELD",
    "IN_CIRCLES",
    "IN_OPERATORS",
    "LINE_STATUS_FIELD",
    "LTI_FIELD",
    "SEARCH_ENGINES",
    "SERIES_HISTORY_CSV",
    "SIM_SWAP_FIELD",
    "aggregate_block",
    "agreement",
    "append_twilio_checks",
    "billed_lookup",
    "block_sample_numbers",
    "block_table",
    "blocks_to_refresh",
    "build_parser",
    "cached_twilio_lookup",
    "caller_category",
    "coai_table",
    "dork",
    "dork_urls",
    "env_setting",
    "expand_codes",
    "extra_series_history",
    "flipkart_lookup",
    "flow_lookup",
    "flow_payload",
    "india_mobile_history",
    "india_overrides",
    "is_current",
    "latest_location",
    "levels2011_table",
    "libphonenumber_entries",
    "libpn_table",
    "live_cache_load",
    "live_cache_save",
    "lookup",
    "main",
    "mcc_mnc_table",
    "msc_table",
    "network_registry",
    "normalized",
    "numverify",
    "operator_name",
    "operator_names",
    "parse_number",
    "parse_range",
    "probe_block",
    "save_suggested_rows",
    "series_entries",
    "series_history",
    "series_table",
    "spam_signal",
    "spam_table",
    "sweep_blocks",
    "twilio_circle_code",
    "twilio_creds",
    "twilio_line_status",
    "twilio_lookup",
    "twilio_operator_code",
    "twilio_table",
    "unallocated_note",
]
