"""
AXIO Core -- Runtime-switchable Claude model + effort (per session).

Modes let the user switch the active Claude model and effort with in-app
commands (e.g. `model opus max`, `model sonnet high`, `effort xhigh`).
ClaudeClient reads these values on every call, so a switch takes effect on the
next Claude request without reconstructing the client.
"""

from .config import CLAUDE_MODEL, CLAUDE_MODELS, CLAUDE_EFFORT, CLAUDE_EFFORTS

_state = {
    "model":  CLAUDE_MODEL,
    "effort": CLAUDE_EFFORT if CLAUDE_EFFORT in CLAUDE_EFFORTS else "max",
}


def get_model() -> str:
    return _state["model"]


def get_effort() -> str:
    return _state["effort"]


def resolve_model(name: str):
    """Resolve a short alias (sonnet/opus), a full claude-* id, or None."""
    key = (name or "").strip().lower()
    if key in CLAUDE_MODELS:
        return CLAUDE_MODELS[key]
    if key.startswith("claude-"):
        return key
    return None


def set_model(name: str):
    """Switch the active Claude model. Returns the resolved id, or None if invalid."""
    resolved = resolve_model(name)
    if resolved:
        _state["model"] = resolved
    return resolved


def set_effort(level: str):
    """Switch the active effort. Returns the level, or None if invalid."""
    key = (level or "").strip().lower()
    if key in CLAUDE_EFFORTS:
        _state["effort"] = key
        return key
    return None


def apply(name: str = None, effort: str = None):
    """Apply an optional model and/or effort in one call. Returns (model, effort, ok)."""
    ok = True
    if name:
        ok = set_model(name) is not None and ok
    if effort:
        ok = set_effort(effort) is not None and ok
    return _state["model"], _state["effort"], ok


def describe() -> str:
    return f"{_state['model']}  |  effort={_state['effort']}"


def options() -> str:
    models = ", ".join(f"{alias}={mid}" for alias, mid in CLAUDE_MODELS.items())
    return f"models: {models}   efforts: {', '.join(CLAUDE_EFFORTS)}"
