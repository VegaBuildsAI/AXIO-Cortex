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
from .config import ROUTE_KEYWORDS, MODELS, CLAUDE_MODEL

# Arithmetic expression detector: matches patterns like 2+2, 10*5, x^2, 3.14/7
_ARITH_RE = _re.compile(r"\d[\s]*[+\-*/^][\s]*[\d(]|\b\d+\.?\d*\s*[+\-*/^]")

# If FORCE_CLAUDE=1 is set, every prompt routes to the premium (Claude) tier.
FORCE_CLAUDE: bool = _os.getenv("FORCE_CLAUDE", "").strip() in ("1", "true", "yes")


def detect(prompt: str) -> tuple[str, str]:
    """
    Inspect a prompt and return (route_name, model_name).

    Routes (checked in order):
      [override]  FORCE_CLAUDE=1  -> always premium (Claude Sonnet)
      math        -> local reasoning model  [arithmetic regex]
      premium     -> Claude API (PDF / legal / audit / complex tasks)
      coding      -> local coding model (qwen3-coder)
      revenue     -> local reasoning model (qwen3:14b)
      chat        -> default chat model (mistral)

    Uses word-boundary matching for short single-word keywords to prevent
    false positives like 'api' matching inside 'capital'.
    """
    ROUTE_TO_MODEL = {
        "coding":  MODELS["coding"],
        "revenue": MODELS["reasoning"],
        "math":    MODELS["reasoning"],
        "premium": CLAUDE_MODEL,
        "chat":    MODELS["chat"],
    }

    # ── global override: FORCE_CLAUDE=1 ──────────────────────────────────
    if FORCE_CLAUDE:
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
