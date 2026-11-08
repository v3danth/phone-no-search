"""Read credentials and settings from the environment, falling back to ./.env.

Lets users keep API keys in a git-ignored file instead of their shell history;
nothing here is ever logged.
"""

from __future__ import annotations

import os

from . import constants as c
from .records import Credentials


def env_setting(name: str) -> str:
    """One setting from the environment, else from ./.env, else ""."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        for line in c.ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("'\"")
    except FileNotFoundError:
        pass
    return ""


def twilio_creds() -> Credentials | None:
    """(sid, token) from env/.env, or None if either is missing."""
    sid = env_setting("TWILIO_ACCOUNT_SID")
    token = env_setting("TWILIO_AUTH_TOKEN")
    return (sid, token) if sid and token else None
