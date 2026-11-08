"""numverify validate endpoint, for cross-checking the offline answer."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .. import constants as c
from ..config import env_setting
from ..records import Live


def numverify(number: str, key: str) -> Live:
    """Validate one number via numverify.

    Failures come back as {"error": ...} so one bad request does not stop a
    batch of lookups.
    """
    url = env_setting("NUMVERIFY_URL") or c.NUMVERIFY_URL
    query = urlencode({"access_key": key, "number": number})
    try:
        with urlopen(f"{url}?{query}", timeout=10) as resp:
            body = json.load(resp)
    except HTTPError as err:  # apilayer puts the reason in the JSON body
        try:
            body = json.load(err)
        except ValueError:
            return {"error": f"request failed: {err}"}
    except (URLError, TimeoutError, ValueError) as err:
        return {"error": f"request failed: {err}"}
    if body.get("success") is False:
        error = body.get("error", {})
        return {"error": error.get("info") or error.get("type") or "unknown error"}
    return body
