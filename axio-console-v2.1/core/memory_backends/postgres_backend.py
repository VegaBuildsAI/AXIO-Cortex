from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Callable

from core.db import connect


def _ts(value) -> datetime:
    """Coerce an ISO string / datetime / None into a datetime for timestamptz."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now()


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

    def update_facts(self, patch: dict, source_session_id: str = None):
        now = datetime.now()
        with self._connection() as conn:
            for key, value in patch.items():
                conn.execute(
                    """
                    INSERT INTO memory_facts (id, mode, key, value, source_session_id, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (mode, key)
                    DO UPDATE SET
                        value = EXCLUDED.value,
                        source_session_id = COALESCE(EXCLUDED.source_session_id, memory_facts.source_session_id),
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        str(uuid.uuid4()),
                        self.mode,
                        key,
                        json.dumps(value),
                        source_session_id,
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

    def persist_session(self, session: dict, summary: str, embedding: list[float] = None) -> str:
        """Persist a full session (Tier 1) + its summary embedding (Tier 2).

        Writes one `sessions` row and one `messages` row per turn, then -- if an
        embedding is supplied -- one `memory_embeddings` row linked back to the
        session. Returns the new session id so facts can reference it.
        """
        if embedding is not None and len(embedding) != 768:
            raise ValueError(
                f"Expected embedding dimension 768, got {len(embedding)}"
            )
        session_id = str(uuid.uuid4())
        now = datetime.now()
        mode = session.get("mode", self.mode)
        model = session.get("model", "")
        messages = session.get("messages", [])
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, mode, title, started_at, ended_at, summary, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    mode,
                    session.get("name", ""),
                    _ts(session.get("created")),
                    _ts(session.get("updated")),
                    summary,
                    json.dumps({"model": model}),
                ),
            )
            for m in messages:
                conn.execute(
                    """
                    INSERT INTO messages
                        (id, session_id, role, content, created_at, token_count, model, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        session_id,
                        m.get("role", ""),
                        m.get("content", ""),
                        now,
                        None,
                        model,
                        json.dumps({}),
                    ),
                )
            if embedding is not None:
                conn.execute(
                    """
                    INSERT INTO memory_embeddings
                        (id, mode, session_id, source_type, source_id, content, embedding, created_at, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        mode,
                        session_id,
                        "session_summary",
                        session_id,
                        summary,
                        embedding,
                        now,
                        json.dumps({"mode": mode, "session_name": session.get("name", ""), "model": model}),
                    ),
                )
            conn.commit()
        return session_id

    def recall(self, embedding: list[float], n_results: int, modes: list[str] = None):
        if len(embedding) != 768:
            raise ValueError(
                f"Expected embedding dimension 768, got {len(embedding)}"
            )
        if modes:
            sql = """
                SELECT content, metadata, embedding <=> %s::vector AS distance
                FROM memory_embeddings
                WHERE mode = ANY(%s)
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """
            params = (embedding, modes, embedding, n_results)
        else:
            sql = """
                SELECT content, metadata, embedding <=> %s::vector AS distance
                FROM memory_embeddings
                WHERE mode = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """
            params = (embedding, self.mode, embedding, n_results)

        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
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
