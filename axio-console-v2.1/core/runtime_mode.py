"""In-process runtime toggle for the local-only vs. local+Claude backend mode.

`core.config.LOCAL_ONLY` is read once at import time from the environment. The web
UI needs to switch between "Gemma local only" and "local + Claude API" without
restarting the uvicorn process, so this module holds a mutable override that
defaults from the env-time constant. It mirrors the pattern of
`core.claude_runtime` (mutable session state for the Claude model/effort).

Callers on the web path should consult `get_local_only()` instead of importing the
`LOCAL_ONLY` constant directly. The terminal CLI keeps using the env constant.
"""
from __future__ import annotations

import threading

from core import config

_lock = threading.Lock()
_state = {"local_only": bool(config.LOCAL_ONLY)}


def get_local_only() -> bool:
    """Return the effective local-only flag (runtime override, env default)."""
    with _lock:
        return _state["local_only"]


def set_local_only(value: bool) -> bool:
    """Set the runtime local-only flag. Returns the new value."""
    with _lock:
        _state["local_only"] = bool(value)
        return _state["local_only"]


def describe() -> dict:
    """Small dict for status endpoints."""
    return {
        "local_only": get_local_only(),
        "claude_configured": bool(config.CLAUDE_API_KEY),
    }
