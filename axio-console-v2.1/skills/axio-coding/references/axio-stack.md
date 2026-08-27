# AXIO engineering stack and patterns

This reference is a curated technical snapshot distilled on 2026-08-24 from the canonical Second Brain and verified against the AXIO Console repository. Re-check the active repository before using version, path, model, or deployment claims.

## Recurring architecture

- Windows and PowerShell are the primary execution environment; Python services and automation are the dominant backend layer.
- AXIO systems are local-first and multi-model. Local Ollama handles privacy-sensitive or economical paths; a stronger cloud model is an explicitly controlled agentic tier.
- Memory uses volatile/session state plus durable retrieval. Current AXIO Console uses crash-safe journals, Postgres/pgvector as healthy primary, a local Chroma mirror, a durable outbox, and atomic JSON fact mirrors.
- Consequential operations require a human gate. The model prepares, checks, cites, and logs; a human authorizes publication, posting, clinical action, financial action, deletion, deployment, or other irreversible effects.
- Services are configuration-driven, auditable, and honest about unavailable layers. A stub is labelled as a stub rather than simulated as working.

## Current AXIO Console family

- Backend: Python 3.12, FastAPI, Uvicorn, Pydantic v2, Requests/HTTPX, Anthropic SDK, Ollama HTTP APIs.
- Data and memory: PostgreSQL, Psycopg 3, pgvector, ChromaDB, local Ollama embeddings, JSON/JSONL persistence.
- UI: Next.js/React/TypeScript with a headless FastAPI service and SSE for execution updates.
- Runtime: bind local services to `127.0.0.1` by default; keep writable state under `AXIO_DATA_ROOT`; use temporary-file plus replace for atomic JSON writes.
- Code mode: an agentic client-tool loop. Tool schemas are sent to Claude or Ollama; AXIO executes client-side tools and returns structured results for the next turn.

## Patterns across AXIO work

- GoodMed/AXIO Clinical: FastAPI engines, typed schemas, strict privacy boundaries, deterministic crisis/approval gates, and no fabricated clinical state.
- Govimo: financial ingestion plus pgvector/k-nearest-neighbor forecasting; the system informs decisions and does not autonomously move money.
- VrT/FreeCAD: MCP bridges around external tools; validate SDK signatures and real application/runtime availability before claiming success.
- JPS/analytics: Python statistics and Monte Carlo are treated as analysis or null/risk models, not evidence of predictive edge. Runtime JSON/SQLite paths are contractual until callers are migrated.
- Websites/AEO: React/Astro/Vite and Cloudflare are recurring. Resolve canonical routing, HTTP status behavior, and deployment authority before public claims.

## Decision rules

1. Inspect first: `AGENTS.md`, dependency manifests, tests, runtime configuration, nested repository roots, and `git status`.
2. Prefer existing libraries and patterns when verified compatible; do not import a package just because it appears in a historical snapshot.
3. Keep secrets in environment variables or secret stores, never source files, prompts, logs, or command arguments.
4. For APIs and database writes, use typed validation, timeouts, explicit error handling, idempotency where retries are possible, and audit metadata.
5. For public or regulated output, omit unsupported facts instead of inventing metrics, readiness, customers, certifications, or results.
