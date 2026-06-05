# Docker Live Database Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local-first Docker Postgres + pgvector live database backend for AXIO Cortex memory, sessions, facts, embeddings, logs, and benchmark history.

**Architecture:** Keep `MemoryManager` as the public API used by existing modes. Add a Postgres backend selected by `AXIO_MEMORY_BACKEND=postgres`, while preserving the current JSON/Chroma path when `AXIO_MEMORY_BACKEND=json`. Docker starts localhost-only by default and remains LAN-ready through configuration.

**Tech Stack:** Python standard library, optional `psycopg[binary]`, Docker Compose, Postgres with pgvector, existing Ollama embedding flow.

---

## File Structure

- Create `docker-compose.yml`: local Postgres + pgvector service, localhost binding, persistent volume.
- Create `docker/postgres/init/001_schema.sql`: database extension and tables.
- Create `docker/postgres/init/002_indexes.sql`: indexes for mode/session/facts/vector search.
- Create `axio-console-v2.1/requirements.txt`: documented runtime dependencies, including `psycopg[binary]`.
- Modify `axio-console-v2.1/.env.example`: database variables and backend selector.
- Modify `axio-console-v2.1/core/config.py`: parse database env vars and backend selector.
- Create `axio-console-v2.1/core/db.py`: database connection config and explicit dependency errors.
- Create `axio-console-v2.1/core/memory_backends/__init__.py`: backend exports.
- Create `axio-console-v2.1/core/memory_backends/postgres_backend.py`: Postgres storage implementation.
- Modify `axio-console-v2.1/core/memory.py`: delegate selected methods to Postgres backend when configured.
- Create `axio-console-v2.1/scripts/migrate_memory_to_postgres.py`: idempotent migration from current local files.
- Create `axio-console-v2.1/tests/test_db_config.py`: config and connection string tests.
- Create `axio-console-v2.1/tests/test_postgres_backend_unit.py`: unit tests for SQL-facing backend with fake connection.
- Create `axio-console-v2.1/tests/test_memory_backend_selection.py`: `MemoryManager` backend selection tests.

---

### Task 1: Add Test Harness and Database Config Tests

**Files:**
- Create: `axio-console-v2.1/tests/__init__.py`
- Create: `axio-console-v2.1/tests/test_db_config.py`
- Modify: `axio-console-v2.1/core/config.py`
- Create: `axio-console-v2.1/core/db.py`

- [ ] **Step 1: Write failing config tests**

Create `axio-console-v2.1/tests/__init__.py` as an empty file.

Create `axio-console-v2.1/tests/test_db_config.py`:

```python
import importlib
import os
import unittest
from unittest.mock import patch


class DatabaseConfigTests(unittest.TestCase):
    def reload_config(self, env):
        with patch.dict(os.environ, env, clear=False):
            import core.config as config
            return importlib.reload(config)

    def test_defaults_to_json_memory_backend(self):
        config = self.reload_config({"AXIO_MEMORY_BACKEND": ""})
        self.assertEqual(config.AXIO_MEMORY_BACKEND, "json")

    def test_reads_postgres_database_settings(self):
        config = self.reload_config({
            "AXIO_MEMORY_BACKEND": "postgres",
            "AXIO_DB_HOST": "127.0.0.1",
            "AXIO_DB_PORT": "5544",
            "AXIO_DB_NAME": "axio_test",
            "AXIO_DB_USER": "axio_user",
            "AXIO_DB_PASSWORD": "secret",
        })

        self.assertEqual(config.AXIO_MEMORY_BACKEND, "postgres")
        self.assertEqual(config.AXIO_DB_HOST, "127.0.0.1")
        self.assertEqual(config.AXIO_DB_PORT, 5544)
        self.assertEqual(config.AXIO_DB_NAME, "axio_test")
        self.assertEqual(config.AXIO_DB_USER, "axio_user")
        self.assertEqual(config.AXIO_DB_PASSWORD, "secret")

    def test_builds_psycopg_connection_string(self):
        with patch.dict(os.environ, {
            "AXIO_DB_HOST": "127.0.0.1",
            "AXIO_DB_PORT": "5432",
            "AXIO_DB_NAME": "axio_cortex",
            "AXIO_DB_USER": "axio",
            "AXIO_DB_PASSWORD": "pw",
        }, clear=False):
            import core.config as config
            importlib.reload(config)
            import core.db as db
            importlib.reload(db)

            dsn = db.get_database_dsn()

        self.assertIn("host=127.0.0.1", dsn)
        self.assertIn("port=5432", dsn)
        self.assertIn("dbname=axio_cortex", dsn)
        self.assertIn("user=axio", dsn)
        self.assertIn("password=pw", dsn)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
cd axio-console-v2.1
py -m unittest tests.test_db_config -v
```

Expected: FAIL because `AXIO_MEMORY_BACKEND`, `AXIO_DB_*`, and `core.db` do not exist.

- [ ] **Step 3: Add config values**

In `axio-console-v2.1/core/config.py`, add after the memory settings:

```python
AXIO_MEMORY_BACKEND = os.getenv("AXIO_MEMORY_BACKEND", "json").strip().lower() or "json"

AXIO_DB_HOST     = os.getenv("AXIO_DB_HOST", "127.0.0.1")
AXIO_DB_PORT     = int(os.getenv("AXIO_DB_PORT", "5432"))
AXIO_DB_NAME     = os.getenv("AXIO_DB_NAME", "axio_cortex")
AXIO_DB_USER     = os.getenv("AXIO_DB_USER", "axio")
AXIO_DB_PASSWORD = os.getenv("AXIO_DB_PASSWORD", "local-dev-password")
```

Create `axio-console-v2.1/core/db.py`:

```python
"""
AXIO database helpers for the optional Postgres memory backend.
"""

from __future__ import annotations

from contextlib import contextmanager

from .config import (
    AXIO_DB_HOST,
    AXIO_DB_NAME,
    AXIO_DB_PASSWORD,
    AXIO_DB_PORT,
    AXIO_DB_USER,
)


class DatabaseDependencyError(RuntimeError):
    """Raised when the optional Postgres dependency is not installed."""


def get_database_dsn() -> str:
    return (
        f"host={AXIO_DB_HOST} "
        f"port={AXIO_DB_PORT} "
        f"dbname={AXIO_DB_NAME} "
        f"user={AXIO_DB_USER} "
        f"password={AXIO_DB_PASSWORD}"
    )


def _load_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
        return psycopg, dict_row
    except ImportError as exc:
        raise DatabaseDependencyError(
            "Postgres backend requires psycopg. Install with: "
            "py -m pip install psycopg[binary]"
        ) from exc


@contextmanager
def connect():
    psycopg, dict_row = _load_psycopg()
    with psycopg.connect(get_database_dsn(), row_factory=dict_row) as conn:
        yield conn
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
cd axio-console-v2.1
py -m unittest tests.test_db_config -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add axio-console-v2.1/core/config.py axio-console-v2.1/core/db.py axio-console-v2.1/tests/__init__.py axio-console-v2.1/tests/test_db_config.py
git commit -m "Add Postgres memory configuration"
```

---

### Task 2: Add Docker Compose and Postgres Schema

**Files:**
- Create: `docker-compose.yml`
- Create: `docker/postgres/init/001_schema.sql`
- Create: `docker/postgres/init/002_indexes.sql`
- Create: `axio-console-v2.1/requirements.txt`
- Modify: `axio-console-v2.1/.env.example`

- [ ] **Step 1: Create Docker compose file**

Create `docker-compose.yml`:

```yaml
services:
  axio-postgres:
    image: pgvector/pgvector:pg16
    container_name: axio-cortex-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${AXIO_DB_NAME:-axio_cortex}
      POSTGRES_USER: ${AXIO_DB_USER:-axio}
      POSTGRES_PASSWORD: ${AXIO_DB_PASSWORD:-local-dev-password}
    ports:
      - "${AXIO_DB_BIND:-127.0.0.1}:${AXIO_DB_PORT:-5432}:5432"
    volumes:
      - axio_postgres_data:/var/lib/postgresql/data
      - ./docker/postgres/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${AXIO_DB_USER:-axio} -d ${AXIO_DB_NAME:-axio_cortex}"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  axio_postgres_data:
```

- [ ] **Step 2: Create schema SQL**

Create `docker/postgres/init/001_schema.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sessions (
    id uuid PRIMARY KEY,
    mode text NOT NULL,
    title text,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    summary text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS messages (
    id uuid PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role text NOT NULL,
    content text NOT NULL,
    created_at timestamptz NOT NULL,
    token_count integer,
    model text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS memory_facts (
    id uuid PRIMARY KEY,
    mode text NOT NULL,
    key text NOT NULL,
    value jsonb NOT NULL,
    source_session_id uuid REFERENCES sessions(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE (mode, key)
);

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id uuid PRIMARY KEY,
    mode text NOT NULL,
    session_id uuid REFERENCES sessions(id) ON DELETE SET NULL,
    source_type text NOT NULL,
    source_id uuid,
    content text NOT NULL,
    embedding vector(768) NOT NULL,
    created_at timestamptz NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id uuid PRIMARY KEY,
    mode text,
    event_type text NOT NULL,
    event jsonb NOT NULL,
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id uuid PRIMARY KEY,
    name text,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS model_scores (
    id uuid PRIMARY KEY,
    benchmark_run_id uuid REFERENCES benchmark_runs(id) ON DELETE CASCADE,
    model text NOT NULL,
    task_id text NOT NULL,
    score numeric,
    verdict text,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL
);
```

Create `docker/postgres/init/002_indexes.sql`:

```sql
CREATE INDEX IF NOT EXISTS idx_sessions_mode_started
    ON sessions (mode, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_messages_session_created
    ON messages (session_id, created_at);

CREATE INDEX IF NOT EXISTS idx_memory_facts_mode_key
    ON memory_facts (mode, key);

CREATE INDEX IF NOT EXISTS idx_memory_embeddings_mode_created
    ON memory_embeddings (mode, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_embeddings_vector
    ON memory_embeddings USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_audit_logs_mode_created
    ON audit_logs (mode, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_model_scores_run_model
    ON model_scores (benchmark_run_id, model);
```

- [ ] **Step 3: Add dependency docs**

Create `axio-console-v2.1/requirements.txt`:

```text
anthropic
chromadb
psycopg[binary]
python-dotenv
requests
rich
```

Append these database settings to `axio-console-v2.1/.env.example`:

```env
# Docker Postgres live memory backend
AXIO_MEMORY_BACKEND=json
AXIO_DB_BIND=127.0.0.1
AXIO_DB_HOST=127.0.0.1
AXIO_DB_PORT=5432
AXIO_DB_NAME=axio_cortex
AXIO_DB_USER=axio
AXIO_DB_PASSWORD=local-dev-password
```

- [ ] **Step 4: Validate compose file syntax**

Run:

```powershell
docker compose config
```

Expected: command exits 0 and prints resolved compose config.

- [ ] **Step 5: Commit**

```powershell
git add docker-compose.yml docker/postgres/init/001_schema.sql docker/postgres/init/002_indexes.sql axio-console-v2.1/requirements.txt axio-console-v2.1/.env.example
git commit -m "Add Docker Postgres schema"
```

---

### Task 3: Add Postgres Backend Unit Tests and Implementation

**Files:**
- Create: `axio-console-v2.1/tests/test_postgres_backend_unit.py`
- Create: `axio-console-v2.1/core/memory_backends/__init__.py`
- Create: `axio-console-v2.1/core/memory_backends/postgres_backend.py`

- [ ] **Step 1: Write failing backend unit tests**

Create `axio-console-v2.1/tests/test_postgres_backend_unit.py`:

```python
import unittest

from core.memory_backends.postgres_backend import PostgresMemoryBackend


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.rows = []
        self.row = None

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.cursor_obj.execute(sql, params)
        return self.cursor_obj

    def commit(self):
        self.commits += 1


class PostgresMemoryBackendUnitTests(unittest.TestCase):
    def test_update_facts_upserts_each_key(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)

        backend.update_facts({"user_name": "Michael", "notes": ["AXIO"]})

        executed_sql = "\n".join(call[0] for call in conn.cursor_obj.calls)
        self.assertIn("INSERT INTO memory_facts", executed_sql)
        self.assertIn("ON CONFLICT (mode, key)", executed_sql)
        self.assertEqual(conn.commits, 1)

    def test_get_facts_returns_key_value_dict(self):
        conn = FakeConnection()
        conn.cursor_obj.rows = [
            {"key": "user_name", "value": "Michael"},
            {"key": "notes", "value": ["AXIO"]},
        ]
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)

        facts = backend.get_facts()

        self.assertEqual(facts["user_name"], "Michael")
        self.assertEqual(facts["notes"], ["AXIO"])

    def test_store_chunk_rejects_wrong_embedding_dimension(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)

        with self.assertRaises(ValueError):
            backend.store_chunk("summary", [0.1, 0.2], {"mode": "chat"})

    def test_recall_orders_by_vector_distance(self):
        conn = FakeConnection()
        conn.cursor_obj.rows = [
            {"content": "Past AXIO session", "metadata": {"mode": "chat"}, "distance": 0.2}
        ]
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)

        rows = backend.recall([0.0] * 768, n_results=3)

        self.assertEqual(rows[0]["text"], "Past AXIO session")
        self.assertEqual(rows[0]["distance"], 0.2)
        executed_sql = "\n".join(call[0] for call in conn.cursor_obj.calls)
        self.assertIn("embedding <=>", executed_sql)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
cd axio-console-v2.1
py -m unittest tests.test_postgres_backend_unit -v
```

Expected: FAIL because `core.memory_backends.postgres_backend` does not exist.

- [ ] **Step 3: Implement Postgres backend**

Create `axio-console-v2.1/core/memory_backends/__init__.py`:

```python
"""Memory backend implementations for AXIO Cortex."""
```

Create `axio-console-v2.1/core/memory_backends/postgres_backend.py`:

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Callable

from core.db import connect


class PostgresMemoryBackend:
    def __init__(self, mode: str, connection_factory: Callable = None):
        self.mode = mode
        self.connection_factory = connection_factory or connect

    def _connection(self):
        return self.connection_factory()

    def get_facts(self) -> dict:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT key, value FROM memory_facts WHERE mode = %s",
                (self.mode,),
            ).fetchall()
        return {row["key"]: row["value"] for row in rows}

    def update_facts(self, patch: dict):
        now = datetime.now()
        with self._connection() as conn:
            for key, value in patch.items():
                conn.execute(
                    """
                    INSERT INTO memory_facts (id, mode, key, value, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (mode, key)
                    DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
                    """,
                    (
                        str(uuid.uuid4()),
                        self.mode,
                        key,
                        json.dumps(value),
                        now,
                    ),
                )
            conn.commit()

    def store_chunk(self, text: str, embedding: list[float], metadata: dict = None):
        if len(embedding) != 768:
            raise ValueError(
                f"Expected embedding dimension 768, got {len(embedding)}"
            )
        meta = dict(metadata or {})
        now = datetime.now()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO memory_embeddings
                    (id, mode, source_type, content, embedding, created_at, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    self.mode,
                    meta.get("source_type", "session_summary"),
                    text,
                    embedding,
                    now,
                    json.dumps(meta),
                ),
            )
            conn.commit()

    def recall(self, embedding: list[float], n_results: int):
        if len(embedding) != 768:
            raise ValueError(
                f"Expected embedding dimension 768, got {len(embedding)}"
            )
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT content, metadata, embedding <=> %s::vector AS distance
                FROM memory_embeddings
                WHERE mode = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (embedding, self.mode, embedding, n_results),
            ).fetchall()
        return [
            {"text": row["content"], "metadata": row["metadata"], "distance": row["distance"]}
            for row in rows
        ]

    def stats(self) -> dict:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    (SELECT count(*) FROM memory_facts WHERE mode = %s) AS facts_count,
                    (SELECT count(*) FROM memory_embeddings WHERE mode = %s) AS embedding_count
                """,
                (self.mode, self.mode),
            ).fetchone()
        return {
            "backend": "postgres",
            "facts_count": row["facts_count"],
            "embedding_count": row["embedding_count"],
        }
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
cd axio-console-v2.1
py -m unittest tests.test_postgres_backend_unit -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add axio-console-v2.1/core/memory_backends axio-console-v2.1/tests/test_postgres_backend_unit.py
git commit -m "Add Postgres memory backend"
```

---

### Task 4: Integrate Backend Selection into MemoryManager

**Files:**
- Create: `axio-console-v2.1/tests/test_memory_backend_selection.py`
- Modify: `axio-console-v2.1/core/memory.py`

- [ ] **Step 1: Write failing MemoryManager tests**

Create `axio-console-v2.1/tests/test_memory_backend_selection.py`:

```python
import importlib
import os
import unittest
from unittest.mock import patch


class MemoryBackendSelectionTests(unittest.TestCase):
    def test_json_backend_is_default(self):
        with patch.dict(os.environ, {"AXIO_MEMORY_BACKEND": ""}, clear=False):
            import core.config as config
            importlib.reload(config)
            import core.memory as memory
            importlib.reload(memory)
            mem = memory.MemoryManager("chat")

        self.assertEqual(mem.backend_name, "json")

    def test_postgres_backend_selected_by_env(self):
        with patch.dict(os.environ, {"AXIO_MEMORY_BACKEND": "postgres"}, clear=False):
            import core.config as config
            importlib.reload(config)
            import core.memory as memory
            importlib.reload(memory)
            mem = memory.MemoryManager("chat")

        self.assertEqual(mem.backend_name, "postgres")
        self.assertIsNotNone(mem._postgres_backend)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
cd axio-console-v2.1
py -m unittest tests.test_memory_backend_selection -v
```

Expected: FAIL because `backend_name` and `_postgres_backend` do not exist.

- [ ] **Step 3: Modify MemoryManager**

In `axio-console-v2.1/core/memory.py`, import the backend selector config:

```python
from .config import AXIO_MEMORY_BACKEND
```

In the existing config import block, include `AXIO_MEMORY_BACKEND`; in the fallback block set:

```python
AXIO_MEMORY_BACKEND = "json"
```

In `MemoryManager.__init__`, add:

```python
self.backend_name = AXIO_MEMORY_BACKEND
self._postgres_backend = None
if self.backend_name == "postgres":
    from core.memory_backends.postgres_backend import PostgresMemoryBackend
    self._postgres_backend = PostgresMemoryBackend(self.mode)
```

At the top of `get_facts`, add:

```python
if self._postgres_backend:
    base = dict(_DEFAULT_FACTS.get(self.mode, {}))
    base.update(self._postgres_backend.get_facts())
    return base
```

At the top of `update_facts`, add:

```python
if self._postgres_backend:
    facts = self.get_facts()
    for key, value in patch.items():
        if isinstance(value, list) and isinstance(facts.get(key), list):
            existing = facts[key]
            for item in value:
                if item not in existing:
                    existing.append(item)
            facts[key] = existing
        elif isinstance(value, dict) and isinstance(facts.get(key), dict):
            facts[key].update(value)
        else:
            facts[key] = value
    facts["last_session"] = datetime.now().isoformat()
    self._postgres_backend.update_facts(facts)
    return
```

At the top of `store_chunk`, add:

```python
if self._postgres_backend:
    meta = {"mode": self.mode, "ts": datetime.now().isoformat()}
    if metadata:
        meta.update({k: str(v) for k, v in metadata.items()})
    embedding = self._embed_via_ollama(text)
    if not embedding:
        return
    self._postgres_backend.store_chunk(text, embedding, meta)
    return
```

At the top of `recall`, add after `n = ...`:

```python
if self._postgres_backend:
    embedding = self._embed_via_ollama(query)
    if embedding:
        return self._postgres_backend.recall(embedding, n)
    return self._keyword_fallback(query)
```

In `stats`, when `_postgres_backend` is active, merge backend stats into the returned dict and report `chroma_ok=False`.

- [ ] **Step 4: Run selection and existing memory tests**

Run:

```powershell
cd axio-console-v2.1
py -m unittest tests.test_memory_backend_selection tests.test_db_config tests.test_postgres_backend_unit -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add axio-console-v2.1/core/memory.py axio-console-v2.1/tests/test_memory_backend_selection.py
git commit -m "Select Postgres memory backend"
```

---

### Task 5: Add Migration Script

**Files:**
- Create: `axio-console-v2.1/scripts/migrate_memory_to_postgres.py`

- [ ] **Step 1: Write migration script**

Create `axio-console-v2.1/scripts/migrate_memory_to_postgres.py`:

```python
#!/usr/bin/env python3
"""
Import existing AXIO JSON memory files into the Postgres backend.

Run from axio-console-v2.1:
    py scripts/migrate_memory_to_postgres.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import MEMORY_DIR
from core.memory import VALID_MODES
from core.memory_backends.postgres_backend import PostgresMemoryBackend


def import_facts() -> int:
    imported = 0
    for mode in VALID_MODES:
        path = MEMORY_DIR / f"{mode}_memory.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        backend = PostgresMemoryBackend(mode)
        backend.update_facts(data)
        imported += 1
        print(f"Imported facts: {path}")
    return imported


def main() -> int:
    count = import_facts()
    print(f"Imported {count} memory fact file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Syntax-check migration script**

Run:

```powershell
cd axio-console-v2.1
py -m py_compile scripts/migrate_memory_to_postgres.py
```

Expected: exits 0.

- [ ] **Step 3: Commit**

```powershell
git add axio-console-v2.1/scripts/migrate_memory_to_postgres.py
git commit -m "Add Postgres memory migration script"
```

---

### Task 6: Docker Integration Verification

**Files:**
- No new source files unless verification finds defects.

- [ ] **Step 1: Install dependencies if missing**

Run:

```powershell
cd axio-console-v2.1
py -m pip install -r requirements.txt
```

Expected: exits 0.

- [ ] **Step 2: Start Postgres**

Run from repository root:

```powershell
docker compose up -d axio-postgres
```

Expected: container starts and healthcheck becomes healthy.

- [ ] **Step 3: Verify schema**

Run:

```powershell
docker compose exec axio-postgres psql -U axio -d axio_cortex -c "\dt"
```

Expected: output includes `sessions`, `messages`, `memory_facts`, `memory_embeddings`, `audit_logs`, `benchmark_runs`, and `model_scores`.

- [ ] **Step 4: Run unit tests**

Run:

```powershell
cd axio-console-v2.1
py -m unittest discover tests -v
```

Expected: PASS.

- [ ] **Step 5: Run migration**

Run:

```powershell
cd axio-console-v2.1
py scripts/migrate_memory_to_postgres.py
```

Expected: imports existing `~/.axio/memory/*_memory.json` files or reports `Imported 0 memory fact file(s).`

- [ ] **Step 6: Verify facts in database**

Run from repository root:

```powershell
docker compose exec axio-postgres psql -U axio -d axio_cortex -c "select mode, key from memory_facts order by mode, key limit 20;"
```

Expected: rows appear if local memory existed.

- [ ] **Step 7: Commit verification-only fixes if needed**

If verification reveals code defects, fix with TDD and commit each fix separately.

---

### Task 7: Documentation and Final Push

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document Docker DB usage**

Add a short section to `README.md` after "HOW TO USE":

````markdown
## Docker Live Database

AXIO Cortex can use a local Docker Postgres + pgvector database as its live
memory backend.

Start the database:

```powershell
docker compose up -d axio-postgres
```

Enable the backend in `axio-console-v2.1/.env`:

```env
AXIO_MEMORY_BACKEND=postgres
AXIO_DB_HOST=127.0.0.1
AXIO_DB_PORT=5432
AXIO_DB_NAME=axio_cortex
AXIO_DB_USER=axio
AXIO_DB_PASSWORD=local-dev-password
```

The default Docker binding is localhost-only. To enable future LAN access,
change `AXIO_DB_BIND` intentionally and restrict access with Windows Firewall.
````

- [ ] **Step 2: Run documentation/status check**

Run:

```powershell
git status -sb
```

Expected: only `README.md` modified.

- [ ] **Step 3: Commit docs**

```powershell
git add README.md
git commit -m "Document Docker live database usage"
```

- [ ] **Step 4: Push all commits**

```powershell
git push
```

- [ ] **Step 5: Final verification**

Run:

```powershell
git status -sb
git log --oneline -5
```

Expected: `main...origin/main` and recent commits show the Docker DB work.
