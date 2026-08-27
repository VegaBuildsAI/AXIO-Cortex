"""AXIO web-intent detection and evidence helpers.

Pure, dependency-light logic that decides whether a request needs live web
evidence, and whether a task's recorded tool calls satisfy that need. The
detection functions are I/O-free and unit-testable. ``augment_with_web`` does
perform retrieval and imports the web tools lazily, so importing this module
stays cheap and free of import cycles (``registry`` imports ``detect_web_intent``
lazily inside ``start_task``).
"""

from __future__ import annotations

import json
import re
from typing import Iterable

# Successful use of any of these tools counts as web evidence for a task.
WEB_EVIDENCE_TOOLS: frozenset[str] = frozenset(
    {"web_search", "web_fetch", "web_extract", "browser_open", "browser_snapshot"}
)

# Explicit opt-out: when the user says any of these, never require web evidence.
_OVERRIDE = re.compile(
    r"\b(no web|without (the )?web|offline|don'?t search|do not search|"
    r"from memory|no internet|sin web|sin internet|no busques|no buscar)\b",
    re.IGNORECASE,
)

# Intent signals. A request needs live evidence only when one of these matches
# AND the override does not. Two-signal / verb-anchored so incidental tokens
# (a bare year, the word "api", "code") never trigger it.
_INTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(search|look ?up|google|browse to|fetch|check online|find out|"
        r"busca|buscar|investiga|investigar)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwhat('?s| is| are)\b.{0,40}\b(latest|current|newest|price|release|"
        r"version|status|score|standings)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(latest|current|newest|up[-\s]?to[-\s]?date|recent|"
        r"[uú]ltim[ao]s?|reciente)\b.{0,40}\b(version|release|price|news|rate|"
        r"weather|standings|noticias|precio|versi[oó]n)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(who won|as of (today|now)|right now|today'?s|breaking|live score)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(stock price|exchange rate|weather forecast|news headlines|headlines)\b",
        re.IGNORECASE,
    ),
)


def detect_web_intent(task: str) -> bool:
    """Return True when the request needs live web evidence."""
    text = task or ""
    if _OVERRIDE.search(text):
        return False
    return any(pattern.search(text) for pattern in _INTENT_PATTERNS)


def has_web_evidence(records: Iterable) -> bool:
    """True if any recorded tool call is a successful web-evidence tool."""
    for record in records or ():
        if getattr(record, "name", None) in WEB_EVIDENCE_TOOLS and getattr(record, "ok", False):
            return True
    return False


def web_gate_message() -> str:
    """Nudge shown when a web-intent task tries to complete without evidence."""
    return (
        "Web evidence required: this request needs current information. Call "
        "web_search first, then web_fetch/web_extract on a result, and cite the "
        "source URL(s). Do not answer from memory. (Add 'no web' to answer "
        "offline and label it unverified.)"
    )


def augment_with_web(query: str, *, max_pages: int = 1, max_chars: int = 4000) -> str:
    """Retrieve bounded web evidence for a query, or "" when no web intent.

    Runs the standalone ``web_search -> web_fetch -> web_extract`` chain and
    returns a labeled, citation-ready evidence block for injection into a chat
    prompt. Never raises: on any failure it returns a short unavailable note
    (or "" when there was no web intent in the first place).
    """
    if not detect_web_intent(query):
        return ""
    try:
        from core.code_tools.web_tools import web_search, web_fetch, web_extract
    except Exception:  # pragma: no cover - web layer unavailable
        return ""

    try:
        search_res = web_search(query)
        if not getattr(search_res, "ok", False):
            return "## Web evidence\n(web search unavailable: SearXNG may be down)\n"
        results = (json.loads(search_res.content) or {}).get("results") or []
        if not results:
            return "## Web evidence\n(no web results found)\n"

        lines = ["## Web evidence (live retrieval — cite these URLs)"]
        for item in results[:5]:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            snippet = (item.get("snippet") or "").strip()
            lines.append(f"- {title} — {url}\n  {snippet}")

        for item in results[:max_pages]:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            fetched = web_fetch(url)
            if not getattr(fetched, "ok", False):
                continue
            try:
                cache_id = (json.loads(fetched.content) or {}).get("cache_id")
            except (ValueError, TypeError):
                cache_id = None
            if not cache_id:
                continue
            extracted = web_extract(cache_id)
            if not getattr(extracted, "ok", False):
                continue
            try:
                body = (json.loads(extracted.content) or {}).get("content") or ""
            except (ValueError, TypeError):
                body = ""
            if body:
                lines.append(f"\n### Extracted from {url}\n{body[:max_chars]}")

        return "\n".join(lines) + "\n"
    except Exception as exc:  # pragma: no cover - defensive; never fail a turn
        return f"## Web evidence\n(web retrieval error: {exc})\n"
