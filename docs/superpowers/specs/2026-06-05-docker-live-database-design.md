# AXIO Cortex Docker Live Database Design

Date: 2026-06-05
Status: Approved design, pending implementation plan

## Goal

Add a Docker-backed live database to AXIO Cortex so memory, sessions, facts,
embeddings, logs, and benchmark history can move from local JSON/Chroma files
to a durable database backend.

The database must be local-first on day one and prepared for future LAN access
from other devices on the user's network.

## Current State

AXIO Cortex currently stores memory in local files under the user's home
directory:

- Tier 1 session records: `~/.axio/sessions`
- Tier 2 semantic memory: `~/.axio/chroma`
- Tier 3 structured facts: `~/.axio/memory`
- Runtime logs: `axio-console-v2.1/logs`

The current `MemoryManager` in `axio-console-v2.1/core/memory.py` owns facts,
semantic recall, and session storage integration. It uses ChromaDB when
available and degrades gracefully when optional dependencies are missing.

## Recommended Architecture

Use **Postgres + pgvector in Docker** as the live memory backend.

Postgres becomes the main durable store for structured and relational data.
`pgvector` stores embeddings for semantic recall. This keeps AXIO's long-term
memory in one queryable database instead of splitting facts, sessions, logs,
and vectors across independent local stores.

AXIO keeps the existing JSON/Chroma path as a separately selectable backend
during the transition. It should be a deliberate configuration choice, not an
automatic silent fallback.

```text
AXIO Cortex
  |
  |-- MemoryManager
      |
      |-- backend=json       existing local fallback
      |-- backend=postgres   new live backend
              |
              |-- Docker Postgres + pgvector
                    |
                    |-- sessions
                    |-- messages
                    |-- memory_facts
                    |-- memory_embeddings
                    |-- audit_logs
                    |-- benchmark_runs
                    |-- model_scores
```

## Deployment Model

The first implementation binds Postgres to localhost:

```env
AXIO_DB_HOST=127.0.0.1
AXIO_DB_PORT=5432
AXIO_DB_NAME=axio_cortex
AXIO_DB_USER=axio
AXIO_DB_PASSWORD=local-dev-password
AXIO_MEMORY_BACKEND=postgres
```

The Docker compose file should expose Postgres only through the configured
local host port initially. It should not require LAN exposure to run.

Future LAN access should be possible by changing configuration, not by
rewriting the backend:

- bind the database to a LAN-reachable interface
- use a stronger password
- restrict firewall access to trusted local subnet devices
- update client machines to point `AXIO_DB_HOST` to the host machine's LAN IP

## Database Schema

The initial schema should include these tables:

### `sessions`

Stores one AXIO session per mode invocation.

Core fields:

- `id uuid primary key`
- `mode text not null`
- `title text`
- `started_at timestamptz not null`
- `ended_at timestamptz`
- `summary text`
- `metadata jsonb not null default '{}'`

### `messages`

Stores individual turns in a session.

Core fields:

- `id uuid primary key`
- `session_id uuid not null references sessions(id)`
- `role text not null`
- `content text not null`
- `created_at timestamptz not null`
- `token_count integer`
- `model text`
- `metadata jsonb not null default '{}'`

### `memory_facts`

Stores structured facts by mode.

Core fields:

- `id uuid primary key`
- `mode text not null`
- `key text not null`
- `value jsonb not null`
- `source_session_id uuid references sessions(id)`
- `updated_at timestamptz not null`

Add a unique constraint on `(mode, key)`.

### `memory_embeddings`

Stores semantic memory chunks and vector embeddings.

Core fields:

- `id uuid primary key`
- `mode text not null`
- `session_id uuid references sessions(id)`
- `source_type text not null`
- `source_id uuid`
- `content text not null`
- `embedding vector(768) not null`
- `created_at timestamptz not null`
- `metadata jsonb not null default '{}'`

The initial vector dimension is `768` because AXIO currently uses
`nomic-embed-text`. If a future embedding model changes dimension, add a second
embedding table or a dimension-aware migration instead of silently mixing
dimensions.

### `audit_logs`

Stores JSONL-style audit events in queryable form.

Core fields:

- `id uuid primary key`
- `mode text`
- `event_type text not null`
- `event jsonb not null`
- `created_at timestamptz not null`

### `benchmark_runs`

Stores benchmark run metadata.

Core fields:

- `id uuid primary key`
- `name text`
- `started_at timestamptz not null`
- `ended_at timestamptz`
- `metadata jsonb not null default '{}'`

### `model_scores`

Stores per-model benchmark scores.

Core fields:

- `id uuid primary key`
- `benchmark_run_id uuid references benchmark_runs(id)`
- `model text not null`
- `task_id text not null`
- `score numeric`
- `verdict text`
- `details jsonb not null default '{}'`
- `created_at timestamptz not null`

## Python Design

Add a backend abstraction under `core/` so `MemoryManager` can delegate storage
without leaking database details into each mode.

Suggested modules:

- `core/memory_backends/base.py`
- `core/memory_backends/json_backend.py`
- `core/memory_backends/postgres_backend.py`
- `core/db.py`

`MemoryManager` remains the public API used by modes:

- `build_memory_prefix(query)`
- `store_session(session, ollama_client)`
- `update_facts(patch)`
- `get_facts()`
- `recall(query, n)`
- `stats()`

The backend is selected with:

```env
AXIO_MEMORY_BACKEND=json
AXIO_MEMORY_BACKEND=postgres
```

If `AXIO_MEMORY_BACKEND=postgres` and the database is unreachable, AXIO should
fail clearly with a connection error. It should not silently write to JSON unless
the user explicitly sets fallback behavior, because silent fallback can split
memory across two stores.

## Docker Design

Add:

- `docker-compose.yml`
- `docker/postgres/init/001_schema.sql`
- `docker/postgres/init/002_indexes.sql`

The compose service should use a pgvector-enabled Postgres image and a named
volume:

- service: `axio-postgres`
- database: `axio_cortex`
- user: `axio`
- volume: `axio_postgres_data`

The compose file should read credentials from a local `.env` file and the
repository should only commit `.env.example` values.

## Migration Design

Add a migration script that imports existing local memory into Postgres:

- JSON session files from `~/.axio/sessions`
- structured facts from `~/.axio/memory`
- ChromaDB summaries where accessible
- runtime logs from `axio-console-v2.1/logs`

The migration should be idempotent where practical. It should record source
paths and source timestamps in `metadata` so imports can be audited.

## Error Handling

Required behavior:

- Missing `psycopg` or database dependency: explain install step.
- Docker not running: show a clear database connection error.
- pgvector extension missing: fail during schema setup with explicit message.
- Embedding dimension mismatch: reject insert and explain the configured model.
- Database unavailable in postgres mode: fail fast instead of silently splitting
  memory.

## Verification Plan

Implementation should verify:

- Docker starts Postgres with pgvector enabled.
- Schema initializes from a clean volume.
- `AXIO_MEMORY_BACKEND=postgres` can save facts and read them back.
- A test session can be stored and retrieved.
- Semantic recall returns expected rows from `memory_embeddings`.
- Data persists after `docker compose down` and `docker compose up`.
- JSON backend still works when selected.

## Non-Goals

This phase will not add:

- cloud hosting
- public database exposure
- multi-user auth
- web dashboard
- Supabase
- automatic LAN firewall configuration

Those can be added after the local Docker database path is stable.

## Open Decision

The implementation should default to localhost-only binding. LAN readiness is
included in configuration and documentation, but actual LAN exposure should
remain a separate, explicit operational step.
