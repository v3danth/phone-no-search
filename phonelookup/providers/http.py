"""Browser-like request headers shared by the web-facing providers."""

from __future__ import annotations

_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def browser_headers(referer: str = "") -> dict[str, str]:
    """Default headers a site expects from a browser, with an optional referer."""
    return {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Connection": "keep-alive",
        "Referer": referer,
    }
