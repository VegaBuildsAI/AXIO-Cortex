"""
AXIO Core -- Model Router (standalone module)
Keyword-based routing that maps a user prompt to the best (route, model) pair.
Kept in its own file so it has no stale bytecode cache issues.

Force Claude Sonnet for every prompt:
  - Set FORCE_CLAUDE=1 in your .env file  (permanent)
  - Or: py axio.py --claude chat          (one session)
"""

import os as _os
import re as _re
from .config import ROUTE_KEYWORDS, MODELS, CLAUDE_MODEL, LOCAL_ONLY

# Arithmetic expression detector: matches patterns like 2+2, 10*5, x^2, 3.14/7
_ARITH_RE = _re.compile(r"\d[\s]*[+\-*/^][\s]*[\d(]|\b\d+\.?\d*\s*[+\-*/^]")

# If FORCE_CLAUDE=1 is set, every prompt routes to the premium (Claude) tier.
FORCE_CLAUDE: bool = _os.getenv("FORCE_CLAUDE", "").strip() in ("1", "true", "yes")


def detect(prompt: str) -> tuple[str, str]:
    """
    Inspect a prompt and return (route_name, model_name).

    Routes (checked in order):
      [override]  FORCE_CLAUDE=1  -> premium (Claude), UNLESS LOCAL_ONLY=1
      math        -> local model (gemma4:12b) / python tool  [arithmetic regex]
      premium     -> Claude tier (or local model when LOCAL_ONLY)
      coding      -> Claude tier (or local model when LOCAL_ONLY)
      revenue     -> Claude tier (or local model when LOCAL_ONLY)
      chat        -> local chat model (gemma4:12b)

    Uses word-boundary matching for short single-word keywords to prevent
    false positives like 'api' matching inside 'capital'.
    """
    # Hybrid: the agentic routes (coding / revenue / premium) boost to the active
    # Claude tier; under LOCAL_ONLY they fall back to the local model so the whole
    # platform stays on-device and never hands a claude-* tag to Ollama.
    if LOCAL_ONLY:
        _agentic = MODELS["reasoning"]
    else:
        from . import claude_runtime
        _agentic = claude_runtime.get_model()
    ROUTE_TO_MODEL = {
        "coding":  _agentic,
        "revenue": _agentic,
        "math":    MODELS["reasoning"],   # exact math uses the local model / python tool
        "premium": _agentic,
        "chat":    MODELS["chat"],
    }

    # ── global override: FORCE_CLAUDE=1 (ignored under LOCAL_ONLY) ────────
    if FORCE_CLAUDE and not LOCAL_ONLY:
        return "premium", CLAUDE_MODEL

    p = prompt.lower()

    # ── fast path: arithmetic expression regex ────────────────────────────
    if _ARITH_RE.search(p):
        return "math", ROUTE_TO_MODEL["math"]

    # ── keyword scan (dict order = priority order) ────────────────────────
    for route, keywords in ROUTE_KEYWORDS.items():
        for kw in keywords:
            no_space = " " not in kw
            short    = len(kw) <= 6

            if no_space and short:
                # Word-boundary check: avoids 'api' in 'capital', 'sql' in 'casual'
                if _re.search(r"\b" + _re.escape(kw) + r"\b", p):
                    return route, ROUTE_TO_MODEL[route]
            else:
                if kw in p:
                    return route, ROUTE_TO_MODEL[route]

    return "chat", ROUTE_TO_MODEL["chat"]


def needs_claude(prompt: str) -> bool:
    """Return True if the prompt should be sent to the Claude API."""
    route, _ = detect(prompt)
    return route == "premium"
