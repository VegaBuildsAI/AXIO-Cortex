"""Bounded local-first web search, fetch, cache, and HTML extraction tools."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

from core.config import (
    AXIO_SEARXNG_URL,
    AXIO_WEB_CACHE_DB,
    AXIO_WEB_MAX_BYTES,
    AXIO_WEB_MAX_CHARS,
    AXIO_WEB_TIMEOUT,
)

from .network_policy import UnsafeUrlError, validate_public_url
from .registry import CodeTool, ToolResult


_REDIRECTS = {301, 302, 303, 307, 308}
_TEXT_TYPES = ("text/", "application/json", "application/xml", "application/xhtml+xml")


def _connection(path: Path | None = None) -> sqlite3.Connection:
    path = path or AXIO_WEB_CACHE_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS responses (
            cache_id TEXT PRIMARY KEY, url TEXT NOT NULL, final_url TEXT NOT NULL,
            status INTEGER NOT NULL, content_type TEXT, body TEXT NOT NULL,
            fetched_at REAL NOT NULL
        )"""
    )
    return conn


def _fetch_data(
    url: str,
    *,
    timeout_seconds: int = AXIO_WEB_TIMEOUT,
    max_bytes: int = AXIO_WEB_MAX_BYTES,
) -> dict:
    current = validate_public_url(url)
    timeout = max(1, min(int(timeout_seconds), 60))
    byte_limit = max(1_024, min(int(max_bytes), AXIO_WEB_MAX_BYTES))
    headers = {"User-Agent": "AXIO-Code/2.1 (+local-first bounded fetch)"}

    response = None
    for _ in range(6):
        response = requests.get(
            current,
            headers=headers,
            timeout=(min(timeout, 10), timeout),
            stream=True,
            allow_redirects=False,
        )
        if response.status_code not in _REDIRECTS:
            break
        location = response.headers.get("location")
        response.close()
        if not location:
            raise ValueError("Redirect response omitted Location header")
        current = validate_public_url(urljoin(current, location))
    else:
        raise ValueError("Too many redirects (maximum 5)")

    if response is None:
        raise ValueError("No response received")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type and not any(content_type.startswith(kind) for kind in _TEXT_TYPES):
        response.close()
        raise ValueError(f"Non-text content type is blocked: {content_type}")

    raw = bytearray()
    for chunk in response.iter_content(chunk_size=65_536):
        if not chunk:
            continue
        raw.extend(chunk)
        if len(raw) > byte_limit:
            response.close()
            raise ValueError(f"Response exceeds {byte_limit:,} byte limit")
    encoding = response.encoding or "utf-8"
    body = bytes(raw).decode(encoding, errors="replace")
    response.close()
    final_url = validate_public_url(current)
    cache_id = hashlib.sha256(f"{final_url}\0{time.time_ns()}".encode()).hexdigest()[:20]
    return {
        "cache_id": cache_id,
        "url": url,
        "final_url": final_url,
        "status": int(response.status_code),
        "content_type": content_type or "unknown",
        "body": body,
        "bytes": len(raw),
    }


def _cache(data: dict, path: Path | None = None) -> None:
    with closing(_connection(path)) as conn:
        conn.execute(
            "INSERT INTO responses VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                data["cache_id"], data["url"], data["final_url"], data["status"],
                data["content_type"], data["body"], time.time(),
            ),
        )
        conn.commit()


def web_fetch(url: str, timeout_seconds: int = AXIO_WEB_TIMEOUT, max_bytes: int = AXIO_WEB_MAX_BYTES) -> ToolResult:
    try:
        data = _fetch_data(url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
        _cache(data)
    except (requests.RequestException, UnsafeUrlError, ValueError, OSError) as exc:
        return ToolResult(f"ERROR: web_fetch failed: {exc}", ok=False)
    preview = re.sub(r"\s+", " ", data["body"]).strip()[:500]
    return ToolResult(json.dumps({key: value for key, value in data.items() if key != "body"} | {"preview": preview}, ensure_ascii=False, indent=2))


class _ReadableHTML(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "aside", "noscript", "svg", "canvas"}
    BREAKS = {"p", "div", "section", "article", "main", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.casefold()
        if tag in self.SKIP:
            self.depth += 1
        if tag == "title":
            self._in_title = True
        if not self.depth and tag in self.BREAKS:
            self.parts.append("\n")
        if not self.depth and tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        if not self.depth and tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.depth:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
        self.parts.append(text + " ")

    def result(self) -> str:
        text = "".join(self.parts)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)


def _extract_html(body: str, max_chars: int = AXIO_WEB_MAX_CHARS) -> tuple[str, str, bool]:
    parser = _ReadableHTML()
    parser.feed(body)
    content = parser.result()
    limit = max(1_000, min(int(max_chars), AXIO_WEB_MAX_CHARS))
    truncated = len(content) > limit
    return parser.title, content[:limit], truncated


def web_extract(cache_id: str, max_chars: int = AXIO_WEB_MAX_CHARS) -> ToolResult:
    try:
        with closing(_connection()) as conn:
            row = conn.execute(
                "SELECT final_url, content_type, body FROM responses WHERE cache_id = ?",
                (cache_id,),
            ).fetchone()
        if row is None:
            return ToolResult(f"ERROR: Unknown web cache id: {cache_id}", ok=False)
        url, content_type, body = row
        if "html" in content_type or "<html" in body[:500].casefold():
            title, content, truncated = _extract_html(body, max_chars)
        else:
            title = ""
            limit = max(1_000, min(int(max_chars), AXIO_WEB_MAX_CHARS))
            content, truncated = body[:limit], len(body) > limit
        return ToolResult(json.dumps({"cache_id": cache_id, "url": url, "title": title, "truncated": truncated, "content": content}, ensure_ascii=False, indent=2))
    except (OSError, sqlite3.Error, ValueError) as exc:
        return ToolResult(f"ERROR: web_extract failed: {exc}", ok=False)


def _valid_domain(value: str) -> str | None:
    domain = value.strip().casefold().lstrip(".")
    return domain if re.fullmatch(r"[a-z0-9.-]+", domain) and "." in domain else None


def _search_web_data(
    query: str,
    max_results: int = 8,
    time_range: str = "",
    domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict:
    if not query.strip():
        raise ValueError("query cannot be empty")
    include = [item for raw in (domains or []) if (item := _valid_domain(raw))]
    exclude = [item for raw in (exclude_domains or []) if (item := _valid_domain(raw))]
    search_query = query.strip() + "".join(f" site:{domain}" for domain in include)
    params = {"q": search_query, "format": "json", "language": "all", "safesearch": 1}
    if time_range in {"day", "month", "year"}:
        params["time_range"] = time_range
    response = requests.get(f"{AXIO_SEARXNG_URL}/search", params=params, timeout=(5, AXIO_WEB_TIMEOUT))
    response.raise_for_status()
    payload = response.json()
    results = []
    for item in payload.get("results", []):
        url = str(item.get("url", ""))
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        if parsed.scheme not in {"http", "https"} or not host:
            continue
        if include and not any(host == domain or host.endswith("." + domain) for domain in include):
            continue
        if any(host == domain or host.endswith("." + domain) for domain in exclude):
            continue
        results.append({
            "title": str(item.get("title", ""))[:300],
            "url": url,
            "snippet": re.sub(r"\s+", " ", str(item.get("content", "")))[:700],
            "score": item.get("score"),
            "source": "searxng",
        })
        if len(results) >= max(1, min(int(max_results), 10)):
            break
    return {"query": query, "provider": AXIO_SEARXNG_URL, "results": results}


def web_search(query: str, max_results: int = 8, time_range: str = "", domains: list[str] | None = None, exclude_domains: list[str] | None = None) -> ToolResult:
    try:
        return ToolResult(json.dumps(_search_web_data(query, max_results, time_range, domains, exclude_domains), ensure_ascii=False, indent=2))
    except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
        return ToolResult(
            f"ERROR: web_search could not reach configured SearXNG at {AXIO_SEARXNG_URL}: {exc}. "
            "Start SearXNG or set AXIO_SEARXNG_URL.",
            ok=False,
        )


TOOLS = [
    CodeTool("web_search", "Search the public web through configured local-first SearXNG and return bounded structured results.", {"type": "object", "properties": {"query": {"type": "string"}, "max_results": {"type": "integer", "minimum": 1, "maximum": 10}, "time_range": {"type": "string", "enum": ["", "day", "month", "year"]}, "domains": {"type": "array", "items": {"type": "string"}}, "exclude_domains": {"type": "array", "items": {"type": "string"}}}, "required": ["query"]}, web_search, "read"),
    CodeTool("web_fetch", "Fetch one known public HTTP(S) URL with redirect, SSRF, content-type, byte, and timeout limits; caches the body locally.", {"type": "object", "properties": {"url": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60}, "max_bytes": {"type": "integer", "minimum": 1024}}, "required": ["url"]}, web_fetch, "read"),
    CodeTool("web_extract", "Extract bounded readable text from a cached web_fetch response; removes scripts, styles, navigation, and boilerplate.", {"type": "object", "properties": {"cache_id": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 1000}}, "required": ["cache_id"]}, web_extract, "read"),
]
