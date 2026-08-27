"""Local hybrid workspace retrieval and official-documentation cache tools."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from array import array
from contextlib import closing
from pathlib import Path

import requests

from core.config import (
    AXIO_DOCS_INDEX_DB,
    AXIO_RETRIEVAL_MAX_CHUNKS,
    AXIO_RETRIEVAL_MAX_FILES,
    AXIO_WEB_MAX_CHARS,
    AXIO_WORKSPACE_INDEX_DB,
    MAX_FILE_BYTES,
    MEMORY_EMBED_MODEL,
    OLLAMA_HOST,
    TEXT_EXTENSIONS,
)

from .registry import CodeTool, ToolResult
from .web_tools import _extract_html, _fetch_data, _search_web_data


_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".next"}
_DOC_DOMAINS = {
    "python": ["docs.python.org"],
    "fastapi": ["fastapi.tiangolo.com"],
    "pydantic": ["docs.pydantic.dev"],
    "react": ["react.dev"],
    "nextjs": ["nextjs.org"],
    "cloudflare": ["developers.cloudflare.com"],
    "supabase": ["supabase.com"],
    "playwright": ["playwright.dev"],
    "docker": ["docs.docker.com"],
    "github": ["docs.github.com"],
}


def _absolute_directory(path: str) -> Path:
    root = Path(path).expanduser()
    if not root.is_absolute():
        raise ValueError(f"Path must be absolute: {path}")
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"Directory not found: {root}")
    return root


def _workspace_connection(path: Path | None = None) -> sqlite3.Connection:
    path = path or AXIO_WORKSPACE_INDEX_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY, workspace_root TEXT NOT NULL, path TEXT NOT NULL,
            start_line INTEGER NOT NULL, end_line INTEGER NOT NULL, content TEXT NOT NULL,
            mtime_ns INTEGER NOT NULL, embedding BLOB
        )"""
    )
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content, path, workspace_root UNINDEXED)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_root ON chunks(workspace_root)")
    return conn


def _matches_text_file(path: Path) -> bool:
    name = path.name.casefold()
    return any(name.endswith(ext.casefold()) for ext in TEXT_EXTENSIONS)


def _chunk_file(path: Path, root: Path) -> list[dict]:
    if path.stat().st_size > MAX_FILE_BYTES:
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    chunks = []
    window, overlap = 80, 10
    start = 0
    while start < len(lines):
        end = min(len(lines), start + window)
        content = "\n".join(lines[start:end]).strip()
        if content:
            chunks.append({
                "path": str(path),
                "relative_path": str(path.relative_to(root)),
                "start_line": start + 1,
                "end_line": end,
                "content": content[:6_000],
                "mtime_ns": path.stat().st_mtime_ns,
            })
        if end >= len(lines):
            break
        start = end - overlap
    return chunks


def _embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = requests.post(
        f"{OLLAMA_HOST.rstrip('/')}/api/embed",
        json={"model": MEMORY_EMBED_MODEL, "input": texts, "truncate": False},
        timeout=60,
    )
    response.raise_for_status()
    vectors = response.json().get("embeddings", [])
    if len(vectors) != len(texts):
        raise ValueError("Embedding endpoint returned an unexpected vector count")
    return vectors


def _pack(vector: list[float] | None) -> bytes | None:
    return array("f", vector).tobytes() if vector else None


def _unpack(blob: bytes | None) -> array:
    values = array("f")
    if blob:
        values.frombytes(blob)
    return values


def index_workspace(path: str, max_files: int = AXIO_RETRIEVAL_MAX_FILES) -> ToolResult:
    try:
        root = _absolute_directory(path)
        file_limit = max(1, min(int(max_files), AXIO_RETRIEVAL_MAX_FILES))
        files = [
            item for item in sorted(root.rglob("*"))
            if item.is_file()
            and not any(part in _SKIP_DIRS for part in item.parts)
            and _matches_text_file(item)
        ][:file_limit]
        chunks: list[dict] = []
        for source in files:
            try:
                chunks.extend(_chunk_file(source, root))
            except OSError:
                continue
            if len(chunks) >= AXIO_RETRIEVAL_MAX_CHUNKS:
                chunks = chunks[:AXIO_RETRIEVAL_MAX_CHUNKS]
                break
        if not chunks:
            return ToolResult(f"ERROR: No supported text/code files found under {root}", ok=False)

        embedding_error = ""
        for offset in range(0, len(chunks), 32):
            batch = chunks[offset:offset + 32]
            if embedding_error:
                vectors = [None] * len(batch)
            else:
                try:
                    vectors = _embed([item["content"] for item in batch])
                except (requests.RequestException, ValueError) as exc:
                    embedding_error = str(exc)
                    vectors = [None] * len(batch)
            for item, vector in zip(batch, vectors):
                item["embedding"] = _pack(vector)

        root_key = str(root)
        with closing(_workspace_connection()) as conn:
            old_ids = [row[0] for row in conn.execute("SELECT id FROM chunks WHERE workspace_root = ?", (root_key,))]
            if old_ids:
                conn.executemany("DELETE FROM chunks_fts WHERE rowid = ?", ((item,) for item in old_ids))
            conn.execute("DELETE FROM chunks WHERE workspace_root = ?", (root_key,))
            for item in chunks:
                cursor = conn.execute(
                    "INSERT INTO chunks(workspace_root,path,start_line,end_line,content,mtime_ns,embedding) VALUES(?,?,?,?,?,?,?)",
                    (root_key, item["path"], item["start_line"], item["end_line"], item["content"], item["mtime_ns"], item["embedding"]),
                )
                conn.execute(
                    "INSERT INTO chunks_fts(rowid,content,path,workspace_root) VALUES(?,?,?,?)",
                    (cursor.lastrowid, item["content"], item["relative_path"], root_key),
                )
            conn.commit()
        mode = "hybrid semantic+FTS5" if not embedding_error else f"FTS5 only (embedding unavailable: {embedding_error})"
        return ToolResult(json.dumps({"workspace": root_key, "files": len(files), "chunks": len(chunks), "mode": mode, "index": str(AXIO_WORKSPACE_INDEX_DB)}, indent=2))
    except (OSError, sqlite3.Error, ValueError) as exc:
        return ToolResult(f"ERROR: index_workspace failed: {exc}", ok=False)


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9_]{2,}", query)[:20]
    return " OR ".join(f'"{token}"' for token in tokens)


def _cosine(left: array, right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    norm_left = math.sqrt(sum(float(a) * float(a) for a in left))
    norm_right = math.sqrt(sum(float(b) * float(b) for b in right))
    return dot / (norm_left * norm_right) if norm_left and norm_right else 0.0


def semantic_search(query: str, path: str, top_k: int = 8) -> ToolResult:
    try:
        root = str(_absolute_directory(path))
        limit = max(1, min(int(top_k), 20))
        with closing(_workspace_connection()) as conn:
            rows = conn.execute(
                "SELECT id,path,start_line,end_line,content,embedding FROM chunks WHERE workspace_root = ?",
                (root,),
            ).fetchall()
            if not rows:
                return ToolResult("ERROR: Workspace is not indexed. Call index_workspace first.", ok=False)
            lexical: dict[int, float] = {}
            expression = _fts_query(query)
            if expression:
                for row_id, rank in conn.execute(
                    "SELECT rowid,bm25(chunks_fts) FROM chunks_fts WHERE chunks_fts MATCH ? AND workspace_root = ? LIMIT 100",
                    (expression, root),
                ):
                    lexical[int(row_id)] = 1.0 / (1.0 + abs(float(rank)))

        try:
            query_vector = _embed([query])[0]
        except (requests.RequestException, ValueError, IndexError):
            query_vector = []
        query_terms = {item.casefold() for item in re.findall(r"[A-Za-z0-9_]{2,}", query)}
        ranked = []
        for row_id, source, start, end, content, blob in rows:
            semantic = _cosine(_unpack(blob), query_vector) if query_vector else 0.0
            filename_terms = {item.casefold() for item in re.findall(r"[A-Za-z0-9_]{2,}", Path(source).name)}
            filename = len(query_terms & filename_terms) / max(len(query_terms), 1)
            score = 0.55 * max(semantic, 0.0) + 0.35 * lexical.get(int(row_id), 0.0) + 0.10 * filename
            ranked.append((score, source, start, end, content, semantic, lexical.get(int(row_id), 0.0)))
        ranked.sort(key=lambda item: item[0], reverse=True)
        results = [
            {"path": source, "start_line": start, "end_line": end, "score": round(score, 4), "semantic": round(semantic, 4), "lexical": round(lexical, 4), "content": content[:3_000]}
            for score, source, start, end, content, semantic, lexical in ranked[:limit]
        ]
        return ToolResult(json.dumps({"query": query, "workspace": root, "results": results}, ensure_ascii=False, indent=2))
    except (OSError, sqlite3.Error, ValueError) as exc:
        return ToolResult(f"ERROR: semantic_search failed: {exc}", ok=False)


def _docs_connection(path: Path | None = None) -> sqlite3.Connection:
    path = path or AXIO_DOCS_INDEX_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, library TEXT, title TEXT, url TEXT UNIQUE, content TEXT, updated_at REAL)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(title,content,url,library UNINDEXED)")
    return conn


def _infer_library(query: str, library: str) -> str:
    chosen = library.strip().casefold()
    if chosen:
        if chosen not in _DOC_DOMAINS:
            raise ValueError("Unsupported library. Choose: " + ", ".join(sorted(_DOC_DOMAINS)))
        return chosen
    lowered = query.casefold()
    for name in _DOC_DOMAINS:
        if name in lowered:
            return name
    raise ValueError("library is required when it cannot be inferred from the query")


def _local_docs(query: str, library: str, limit: int) -> list[dict]:
    expression = _fts_query(query)
    if not expression:
        return []
    with closing(_docs_connection()) as conn:
        rows = conn.execute(
            "SELECT title,url,content,bm25(docs_fts) FROM docs_fts WHERE docs_fts MATCH ? AND library = ? ORDER BY bm25(docs_fts) LIMIT ?",
            (expression, library, limit),
        ).fetchall()
    return [{"title": title, "url": url, "content": content[:4_000], "score": round(1 / (1 + abs(float(rank))), 4), "source": "local-docs-cache"} for title, url, content, rank in rows]


def search_docs(query: str, library: str = "", max_results: int = 5, refresh: bool = False) -> ToolResult:
    try:
        chosen = _infer_library(query, library)
        limit = max(1, min(int(max_results), 8))
        results = [] if refresh else _local_docs(query, chosen, limit)
        warning = ""
        if len(results) < limit:
            try:
                found = _search_web_data(f"{query} official documentation", min(3, limit), domains=_DOC_DOMAINS[chosen])
                with closing(_docs_connection()) as conn:
                    for item in found["results"][:3]:
                        fetched = _fetch_data(item["url"])
                        title, content, _ = _extract_html(fetched["body"], AXIO_WEB_MAX_CHARS)
                        if not content:
                            continue
                        cursor = conn.execute(
                            "INSERT INTO documents(library,title,url,content,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET title=excluded.title,content=excluded.content,updated_at=excluded.updated_at RETURNING id",
                            (chosen, title or item["title"], item["url"], content, time.time()),
                        )
                        doc_id = cursor.fetchone()[0]
                        conn.execute("DELETE FROM docs_fts WHERE rowid = ?", (doc_id,))
                        conn.execute("INSERT INTO docs_fts(rowid,title,content,url,library) VALUES(?,?,?,?,?)", (doc_id, title or item["title"], content, item["url"], chosen))
                    conn.commit()
                results = _local_docs(query, chosen, limit)
            except Exception as exc:
                warning = f"Online refresh unavailable: {exc}"
        if not results:
            return ToolResult(f"ERROR: No cached official docs found for {chosen}. {warning}".strip(), ok=False)
        return ToolResult(json.dumps({"query": query, "library": chosen, "warning": warning, "results": results}, ensure_ascii=False, indent=2))
    except (OSError, sqlite3.Error, ValueError) as exc:
        return ToolResult(f"ERROR: search_docs failed: {exc}", ok=False)


TOOLS = [
    CodeTool("index_workspace", "Build or refresh a bounded local hybrid FTS5 + Ollama-embedding index for one workspace. Writes only derived AXIO index data.", {"type": "object", "properties": {"path": {"type": "string"}, "max_files": {"type": "integer", "minimum": 1}}, "required": ["path"]}, index_workspace, "index"),
    CodeTool("semantic_search", "Search an indexed workspace with hybrid semantic, FTS5, and filename ranking; returns bounded line-addressable chunks.", {"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}, "top_k": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": ["query", "path"]}, semantic_search, "read"),
    CodeTool("search_docs", "Search a local cache of official library documentation and refresh it through SearXNG when needed.", {"type": "object", "properties": {"query": {"type": "string"}, "library": {"type": "string", "enum": ["", "python", "fastapi", "pydantic", "react", "nextjs", "cloudflare", "supabase", "playwright", "docker", "github"]}, "max_results": {"type": "integer", "minimum": 1, "maximum": 8}, "refresh": {"type": "boolean"}}, "required": ["query"]}, search_docs, "read"),
]
