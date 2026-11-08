"""Consent-based account-presence checks that take an E.164 number.

Each posts the number to a service and returns its JSON, shaped as {"error": ...}
on failure so one unreachable service never stops a batch.
"""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .. import constants as c
from ..records import Live
from .http import browser_headers

_FLIPKART_UA = ("Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 "
                "Firefox/140.0 FKUA/website/42/website/Desktop")


def flow_payload(raw: str) -> dict[str, str]:
    """The request body the local flow service expects for a number."""
    return {"phone": raw}


def flow_lookup(e164: str) -> Live:
    """POST the number to the local flow service and return its JSON response."""
    request = Request(
        c.FLOW_URL,
        data=json.dumps(flow_payload(e164)).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as resp:
            return json.load(resp)
    except HTTPError as err:
        return {"error": f"flow service returned HTTP {err.code}: {err.reason}"}
    except (URLError, TimeoutError, OSError) as err:
        return {"error": f"flow service unavailable: {err}"}
    except (ValueError, UnicodeError) as err:
        return {"error": f"flow service returned invalid JSON: {err}"}


def flipkart_lookup(e164: str) -> Live:
    """POST the number to Flipkart's signup-status endpoint and return its JSON."""
    headers = browser_headers("https://www.flipkart.com/")
    headers.update({
        "Content-Type": "application/json",
        "X-User-Agent": _FLIPKART_UA,
        "Origin": "https://www.flipkart.com",
    })
    request = Request(
        c.FLIPKART_URL,
        data=json.dumps({"loginId": [e164], "supportAllStates": True}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as resp:
            return json.load(resp)
    except HTTPError as err:
        return {"error": f"flipkart service returned HTTP {err.code}: {err.reason}"}
    except (URLError, TimeoutError, OSError) as err:
        return {"error": f"flipkart service unavailable: {err}"}
    except (ValueError, UnicodeError) as err:
        return {"error": f"flipkart service returned invalid JSON: {err}"}
