# Retrieval tools

Covers `index_workspace`, `semantic_search`, `search_docs`.

## Semantic code retrieval
- `index_workspace <path>` builds/refreshes a derived FTS5 + local-embedding index. It only writes index data, never source. Run it **once** before `semantic_search` in a session; re-index after the workspace changes significantly.
- `semantic_search "query"` returns bounded, line-addressable chunks. Use it for concept-level questions ("where is auth handled?").

## grep vs semantic
- `grep_files` — exact strings / known symbols / precise patterns.
- `semantic_search` — fuzzy, concept-level "where does X happen" when you do not know the exact term.

## Library docs
- `search_docs` finds official library documentation from a local cache, refreshing via SearXNG when needed. Prefer it over `web_fetch` for known libraries (FastAPI, SQLAlchemy, pytest, …). Cite the returned source URL; do not present cached content as current when a refresh failed.

## Error recovery
- `semantic_search` "index not found" → run `index_workspace` first.
- Empty results → widen the query, or fall back to `grep_files` for exact terms.
