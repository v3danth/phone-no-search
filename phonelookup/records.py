"""Shared type aliases for the loosely-typed dicts that flow through the tool.

Named so signatures say what a dict means (a CSV row, a history entry, a lookup
result) without repeating `dict[str, ...]` everywhere.
"""

from __future__ import annotations

from typing import Any

Row = dict[str, str]          # one CSV row, column -> value
Entry = dict[str, Any]        # one dated history entry for a number
Result = dict[str, Any]       # a full offline lookup result
Live = dict[str, Any]         # a provider (Twilio/numverify/flow) response
Credentials = tuple[str, str]  # (account sid, auth token)
