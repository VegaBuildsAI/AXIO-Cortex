"""Brain tools: read the shared AXIO Cortex brain from Postgres.

The Postgres Cortex is the one brain. It holds the imported Second Brain vault
notes (source_type ``second_brain``) beside what AXIO learned on its own
(``self_learned``, ``memory_seed``, ``exemplar``, session summaries). These
tools query Postgres only: they never read vault files and never write.

revrec's isolated namespace is never searched (see ``BRAIN_TOOL_MODES``).
"""

from __future__ import annotations

import json
import re

import requests

from core.config import (
    BRAIN_READ_MAX_CHARS,
    BRAIN_TOOL_MODES,
    MEMORY_EMBED_MODEL,
    MEMORY_IVFFLAT_PROBES,
    OLLAMA_HOST,
    SECOND_BRAIN_NAMESPACE,
    SECOND_BRAIN_SOURCE_TYPE,
)
from core.db import connect

from .registry import CodeTool, ToolResult


# Patched by tests; production uses the shared psycopg factory.
_connect = connect

_SOURCE_RE = re.compile(r"^[a-z_]{1,40}$")
_TOKEN_RE = re.compile(r"[\w][\w.-]{2,}", re.UNICODE)
_STOPWORDS = {
    "the", "and", "for", "what", "who", "how", "why", "with", "about", "does",
    "que", "con", "para", "por", "los", "las", "del", "una", "como", "sobre",
}


def _modes() -> list[str]:
    return [mode for mode in BRAIN_TOOL_MODES if mode != "revrec"]


def _embed_query(text: str) -> list[float] | None:
    """Embed with the same endpoint/model the stored vectors were built with."""
    try:
        response = requests.post(
            f"{OLLAMA_HOST.rstrip('/')}/api/embeddings",
            json={"model": MEMORY_EMBED_MODEL, "prompt": text},
            timeout=30,
        )
        if response.ok:
            vector = response.json().get("embedding")
            if vector and len(vector) == 768:
                return vector
    except requests.RequestException:
        pass
    return None


def _keyword_tokens(query: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(query.casefold()):
        if token in _STOPWORDS or token in tokens:
            continue
        tokens.append(token)
    return tokens[:8]


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _like_pattern(token: str) -> str:
    return f"%{_escape_like(token)}%"


def _strip_chunk_header(content: str) -> str:
    """Drop the '[Second Brain] path — heading:' line the importer prepends."""
    if content.startswith("[") and "\n" in content:
        first, rest = content.split("\n", 1)
        if "]" in first and first.rstrip().endswith(":"):
            return rest
    return content


def _validate_source(source: str) -> str:
    source = (source or "").strip()
    if source and not _SOURCE_RE.match(source):
        raise ValueError(f"Invalid source filter: {source!r}")
    return source


def _row_summary(row: dict, content_chars: int = 2000) -> dict:
    meta = row.get("metadata") or {}
    return {
        "source_type": row.get("source_type"),
        "mode": row.get("mode"),
        "path": meta.get("path") or meta.get("doc") or meta.get("session_name") or "",
        "title": meta.get("title", ""),
        "chunk_index": meta.get("chunk_index"),
        "content": _strip_chunk_header(str(row.get("content") or ""))[:content_chars],
    }


def brain_search(query: str, top_k: int = 8, source: str = "") -> ToolResult:
    """Exact vector + keyword search over the shared Cortex brain."""
    try:
        query = (query or "").strip()
        if not query:
            return ToolResult("ERROR: query is required", ok=False)
        limit = max(1, min(int(top_k), 20))
        source = _validate_source(source)
        modes = _modes()
        embedding = _embed_query(query)
        tokens = _keyword_tokens(query)
        source_sql = " AND source_type = %s" if source else ""
        source_params = (source,) if source else ()

        merged: dict[str, dict] = {}
        with _connect() as conn:
            if embedding:
                conn.execute(
                    "SELECT set_config('ivfflat.probes', %s, true)",
                    (str(MEMORY_IVFFLAT_PROBES),),
                )
                rows = conn.execute(
                    f"""
                    SELECT id, mode, source_type, content, metadata,
                           embedding <=> %s::vector AS distance
                    FROM memory_embeddings
                    WHERE mode = ANY(%s)
                      AND NOT (metadata ? 'superseded_by'){source_sql}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (embedding, modes, *source_params, embedding, limit * 2),
                ).fetchall()
                for row in rows:
                    item = _row_summary(dict(row))
                    item["semantic"] = round(1.0 - float(row["distance"]), 4)
                    item["keyword"] = 0.0
                    merged[str(row["id"])] = item
            if tokens:
                patterns = [_like_pattern(token) for token in tokens]
                score_sql = " + ".join(
                    "(CASE WHEN content ILIKE %s THEN 1 ELSE 0 END)" for _ in patterns
                )
                rows = conn.execute(
                    f"""
                    SELECT id, mode, source_type, content, metadata,
                           ({score_sql}) AS hits
                    FROM memory_embeddings
                    WHERE mode = ANY(%s)
                      AND NOT (metadata ? 'superseded_by'){source_sql}
                      AND content ILIKE ANY(%s)
                    ORDER BY hits DESC, created_at DESC
                    LIMIT %s
                    """,
                    (*patterns, modes, *source_params, patterns, limit * 2),
                ).fetchall()
                for row in rows:
                    key = str(row["id"])
                    item = merged.get(key) or {**_row_summary(dict(row)), "semantic": 0.0}
                    item["keyword"] = round(float(row["hits"]) / len(tokens), 4)
                    merged[key] = item

        for item in merged.values():
            if embedding:
                item["score"] = round(0.7 * max(item["semantic"], 0.0) + 0.3 * item["keyword"], 4)
            else:
                item["score"] = item["keyword"]
        results = sorted(merged.values(), key=lambda item: item["score"], reverse=True)[:limit]
        mode = "exact vector + keyword" if embedding else "keyword-only (Ollama embedding unavailable)"
        return ToolResult(json.dumps(
            {"query": query, "mode": mode, "source": source or "all", "results": results},
            ensure_ascii=False, indent=2, default=str,
        ))
    except ValueError as exc:
        return ToolResult(f"ERROR: brain_search: {exc}", ok=False)
    except Exception as exc:
        return ToolResult(f"ERROR: brain_search: Cortex Postgres unavailable ({exc})", ok=False)


def _note_rows(conn, path: str, source: str) -> list:
    return conn.execute(
        """
        SELECT content, metadata, created_at
        FROM memory_embeddings
        WHERE mode = ANY(%s) AND source_type = %s AND metadata->>'path' = %s
          AND NOT (metadata ? 'superseded_by')
        ORDER BY NULLIF(metadata->>'chunk_index', '')::int NULLS LAST, created_at, id
        """,
        (_modes(), source, path),
    ).fetchall()


def brain_read(path: str, source: str = SECOND_BRAIN_SOURCE_TYPE) -> ToolResult:
    """Rebuild one full imported note from its ordered chunks in Postgres."""
    try:
        path = (path or "").strip().replace("\\", "/").lstrip("/")
        if not path:
            return ToolResult("ERROR: path is required (e.g. 01-Projects/minios.md)", ok=False)
        source = _validate_source(source) or SECOND_BRAIN_SOURCE_TYPE
        with _connect() as conn:
            rows = _note_rows(conn, path, source)
            if not rows:
                candidates = [
                    row["path"] for row in conn.execute(
                        """
                        SELECT DISTINCT metadata->>'path' AS path
                        FROM memory_embeddings
                        WHERE mode = ANY(%s) AND source_type = %s
                          AND metadata->>'path' ILIKE %s
                        ORDER BY 1
                        LIMIT 10
                        """,
                        (_modes(), source, _like_pattern(path)),
                    ).fetchall()
                    if row["path"]
                ]
                if len(candidates) == 1:
                    path = candidates[0]
                    rows = _note_rows(conn, path, source)
                elif candidates:
                    return ToolResult(
                        "ERROR: brain_read: path is ambiguous; pick one of:\n- "
                        + "\n- ".join(candidates),
                        ok=False,
                    )
        if not rows:
            return ToolResult(
                f"ERROR: brain_read: no imported note at {path!r} (source {source}). "
                "Use brain_list or brain_search to find the exact path.",
                ok=False,
            )

        sections: list[str] = []
        last_title = None
        ordered = all((row["metadata"] or {}).get("chunk_index") is not None for row in rows)
        note_mtime = None
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        for row in rows:
            meta = row["metadata"] or {}
            note_mtime = meta.get("note_mtime", note_mtime)
            title = meta.get("title", "")
            body = _strip_chunk_header(str(row["content"] or ""))
            if sections and int(meta.get("section_part") or 0) > 0 and title == last_title:
                # Oversized sections are stored as contiguous slices: rejoin
                # them exactly, without inserting a break mid-sentence.
                sections[-1] += body
            elif title in ("(intro)", "") or (title == stem and not sections):
                sections.append(body.strip())
            else:
                sections.append(f"## {title}\n{body.strip()}")
            last_title = title
        text = "\n\n".join(sections)
        truncated = len(text) > BRAIN_READ_MAX_CHARS
        header = (
            f"# {path}\n(source: {source}; {len(rows)} chunk(s) from the Cortex"
            + ("" if ordered else "; imported before chunk_index, order approximate")
            + (f"; note_mtime {note_mtime}" if note_mtime else "")
            + ")\n\n"
        )
        return ToolResult(
            header + text[:BRAIN_READ_MAX_CHARS]
            + ("\n\n…[truncated]" if truncated else "")
        )
    except ValueError as exc:
        return ToolResult(f"ERROR: brain_read: {exc}", ok=False)
    except Exception as exc:
        return ToolResult(f"ERROR: brain_read: Cortex Postgres unavailable ({exc})", ok=False)


def brain_list(folder: str = "", source: str = SECOND_BRAIN_SOURCE_TYPE) -> ToolResult:
    """List imported note paths and headings, plus per-source chunk counts."""
    try:
        folder = (folder or "").strip().replace("\\", "/").lstrip("/")
        source = _validate_source(source) or SECOND_BRAIN_SOURCE_TYPE
        prefix = _escape_like(folder) + "%"
        with _connect() as conn:
            notes = conn.execute(
                """
                SELECT metadata->>'path' AS path, count(*) AS chunks,
                       array_agg(metadata->>'title'
                                 ORDER BY NULLIF(metadata->>'chunk_index', '')::int NULLS LAST, created_at)
                           AS titles
                FROM memory_embeddings
                WHERE mode = ANY(%s) AND source_type = %s
                  AND coalesce(metadata->>'path', '') LIKE %s
                GROUP BY 1
                ORDER BY 1
                """,
                (_modes(), source, prefix),
            ).fetchall()
            counts = conn.execute(
                """
                SELECT mode, source_type, count(*) AS count
                FROM memory_embeddings
                WHERE mode = ANY(%s)
                GROUP BY 1, 2
                ORDER BY 1, 2
                """,
                (_modes(),),
            ).fetchall()
        listed = []
        for row in notes:
            headings = []
            for title in row["titles"] or []:
                if title and title != "(intro)" and title not in headings:
                    headings.append(title)
            listed.append({"path": row["path"], "chunks": int(row["chunks"]), "headings": headings[:12]})
        return ToolResult(json.dumps({
            "source": source,
            "folder": folder or "(all)",
            "notes": len(listed),
            "items": listed,
            "source_counts": [
                {"mode": row["mode"], "source_type": row["source_type"], "count": int(row["count"])}
                for row in counts
            ],
        }, ensure_ascii=False, indent=2))
    except ValueError as exc:
        return ToolResult(f"ERROR: brain_list: {exc}", ok=False)
    except Exception as exc:
        return ToolResult(f"ERROR: brain_list: Cortex Postgres unavailable ({exc})", ok=False)


_SOURCE_SCHEMA = {
    "type": "string",
    "description": "Optional source_type filter: second_brain, self_learned, memory_seed, exemplar, session_summary.",
}

TOOLS = [
    CodeTool(
        "brain_search",
        "Search Michael's shared AXIO brain in the Postgres Cortex (imported Second Brain notes, "
        "seed docs, self-learned lessons, exemplars, session summaries) with exact vector + keyword "
        "ranking. Use for questions about his projects, people, decisions and history.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
                "source": _SOURCE_SCHEMA,
            },
            "required": ["query"],
        },
        brain_search, "read", "brain", ("RESEARCH", "PLANNING"),
    ),
    CodeTool(
        "brain_read",
        "Read one full imported note from the Postgres Cortex by its vault-relative path "
        "(e.g. 01-Projects/minios.md), rebuilt from its ordered chunks.",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}, "source": _SOURCE_SCHEMA},
            "required": ["path"],
        },
        brain_read, "read", "brain", ("RESEARCH", "PLANNING"),
    ),
    CodeTool(
        "brain_list",
        "List imported note paths (optionally under a folder) with their headings, plus "
        "per-source chunk counts for the shared Cortex brain.",
        {
            "type": "object",
            "properties": {"folder": {"type": "string"}, "source": _SOURCE_SCHEMA},
        },
        brain_list, "read", "brain", ("RESEARCH", "PLANNING"),
    ),
]
