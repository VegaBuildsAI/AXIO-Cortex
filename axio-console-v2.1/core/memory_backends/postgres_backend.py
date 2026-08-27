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


def _uuid_str(value=None, seed: str = "") -> str:
    """Return a Postgres-safe UUID, deterministically when a legacy id is used."""
    if value:
        try:
            return str(uuid.UUID(str(value)))
        except ValueError:
            return str(uuid.uuid5(uuid.NAMESPACE_URL, f"axio:{seed}:{value}"))
    return str(uuid.uuid4())


class PostgresMemoryBackend:
    def __init__(self, mode: str, connection_factory: Callable = None):
        self.mode = mode
        self.connection_factory = connection_factory or connect

    def _connection(self):
        return self.connection_factory()

    def healthcheck(self) -> bool:
        with self._connection() as conn:
            row = conn.execute("SELECT 1 AS ok").fetchone()
        return bool(row and row["ok"] == 1)

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

    def store_chunk(
        self,
        text: str,
        embedding: list[float],
        metadata: dict = None,
        chunk_id: str = None,
    ):
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
                ON CONFLICT (id)
                DO UPDATE SET
                    mode = EXCLUDED.mode,
                    source_type = EXCLUDED.source_type,
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata
                """,
                (
                    _uuid_str(chunk_id, "chunk"),
                    self.mode,
                    meta.get("source_type", "session_summary"),
                    text,
                    embedding,
                    now,
                    json.dumps(meta),
                ),
            )
            conn.commit()

    def find_similar(
        self,
        embedding: list[float],
        source_type: str,
        threshold: float = 0.0,
    ) -> dict | None:
        """Return the nearest same-mode/source chunk when it clears threshold."""
        if len(embedding) != 768:
            raise ValueError(
                f"Expected embedding dimension 768, got {len(embedding)}"
            )
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT id, content, embedding, metadata, created_at,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM memory_embeddings
                WHERE mode = %s AND source_type = %s
                  AND NOT (metadata ? 'superseded_by')
                ORDER BY embedding <=> %s::vector
                LIMIT 1
                """,
                (embedding, self.mode, source_type, embedding),
            ).fetchone()
        if not row or float(row["similarity"]) < float(threshold):
            return None
        return dict(row)

    def list_chunks(self, source_type: str, limit: int = 1000) -> list[dict]:
        """List derived chunks for maintenance/reporting; never raw messages."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, content, embedding, metadata, created_at
                FROM memory_embeddings
                WHERE mode = %s AND source_type = %s
                ORDER BY created_at, id
                LIMIT %s
                """,
                (self.mode, source_type, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_chunks(self, source_type: str) -> int:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT count(*) AS count FROM memory_embeddings "
                "WHERE mode = %s AND source_type = %s",
                (self.mode, source_type),
            ).fetchone()
        return int(row["count"] if row else 0)

    def update_chunk_metadata(self, chunk_id: str, metadata: dict) -> dict | None:
        """Replace metadata for one derived chunk and return its mirror payload."""
        with self._connection() as conn:
            row = conn.execute(
                """
                UPDATE memory_embeddings
                SET metadata = %s
                WHERE id = %s AND mode = %s
                RETURNING id, content, embedding, metadata, created_at
                """,
                (json.dumps(metadata), _uuid_str(chunk_id, "chunk"), self.mode),
            ).fetchone()
            conn.commit()
        return dict(row) if row else None

    def recent_messages(self, since_iso=None, limit: int = 500) -> list[dict]:
        """Read incremental message material for local self-memory mining."""
        if since_iso:
            where = "WHERE m.created_at > %s"
            params = (_ts(since_iso), limit)
        else:
            where = ""
            params = (limit,)
        with self._connection() as conn:
            rows = conn.execute(
                f"""
                SELECT m.id, m.session_id, s.mode, m.role, m.content,
                       m.created_at, m.model, m.metadata
                FROM messages AS m
                JOIN sessions AS s ON s.id = m.session_id
                {where}
                ORDER BY m.created_at, m.id
                LIMIT %s
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def persist_live_session(self, session: dict) -> str:
        """Upsert the raw session and messages without waiting for clean exit."""
        session_id = _uuid_str(session.get("id"), "session")
        session["id"] = session_id
        mode = session.get("mode", self.mode)
        model = session.get("model", "")
        messages = session.get("messages", [])
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, mode, title, started_at, ended_at, summary, metadata)
                VALUES (%s, %s, %s, %s, NULL, '', %s)
                ON CONFLICT (id)
                DO UPDATE SET
                    mode = EXCLUDED.mode,
                    title = EXCLUDED.title,
                    metadata = EXCLUDED.metadata
                """,
                (
                    session_id,
                    mode,
                    session.get("name", ""),
                    _ts(session.get("created")),
                    json.dumps({"model": model, "live": True}),
                ),
            )
            for index, message in enumerate(messages):
                message_id = _uuid_str(
                    message.get("id"),
                    f"message:{session_id}:{index}",
                )
                message["id"] = message_id
                conn.execute(
                    """
                    INSERT INTO messages
                        (id, session_id, role, content, created_at, token_count, model, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        role = EXCLUDED.role,
                        content = EXCLUDED.content,
                        model = EXCLUDED.model,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        message_id,
                        session_id,
                        message.get("role", ""),
                        message.get("content", ""),
                        _ts(message.get("created_at")),
                        None,
                        model,
                        json.dumps(message.get("metadata", {})),
                    ),
                )
            conn.commit()
        return session_id

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
        session_id = _uuid_str(session.get("id"), "session")
        session["id"] = session_id
        now = datetime.now()
        mode = session.get("mode", self.mode)
        model = session.get("model", "")
        messages = session.get("messages", [])
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, mode, title, started_at, ended_at, summary, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id)
                DO UPDATE SET
                    mode = EXCLUDED.mode,
                    title = EXCLUDED.title,
                    ended_at = EXCLUDED.ended_at,
                    summary = EXCLUDED.summary,
                    metadata = EXCLUDED.metadata
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
            for index, m in enumerate(messages):
                message_id = _uuid_str(
                    m.get("id"),
                    f"message:{session_id}:{index}",
                )
                m["id"] = message_id
                conn.execute(
                    """
                    INSERT INTO messages
                        (id, session_id, role, content, created_at, token_count, model, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        role = EXCLUDED.role,
                        content = EXCLUDED.content,
                        model = EXCLUDED.model,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        message_id,
                        session_id,
                        m.get("role", ""),
                        m.get("content", ""),
                        _ts(m.get("created_at")),
                        None,
                        model,
                        json.dumps(m.get("metadata", {})),
                    ),
                )
            if embedding is not None:
                conn.execute(
                    """
                    INSERT INTO memory_embeddings
                        (id, mode, session_id, source_type, source_id, content, embedding, created_at, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id)
                    DO UPDATE SET
                        mode = EXCLUDED.mode,
                        session_id = EXCLUDED.session_id,
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        str(uuid.uuid5(uuid.UUID(session_id), "summary")),
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

    def delete_chunks(self, source_type: str, key: str, value: str) -> None:
        if key not in {"doc", "path"}:
            raise ValueError(f"Unsupported metadata key: {key}")
        with self._connection() as conn:
            conn.execute(
                f"DELETE FROM memory_embeddings "
                f"WHERE mode=%s AND source_type=%s AND metadata->>%s = %s",
                (self.mode, source_type, key, value),
            )
            conn.commit()

    def source_counts(self) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT mode, source_type, count(*) AS count
                FROM memory_embeddings
                GROUP BY mode, source_type
                ORDER BY mode, source_type
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def all_embeddings(self) -> list[dict]:
        """Export the current canonical vectors for local Chroma bootstrap."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, mode, content, embedding, metadata
                FROM memory_embeddings
                ORDER BY created_at, id
                """
            ).fetchall()
        return [dict(row) for row in rows]

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
                  AND NOT (metadata ? 'superseded_by')
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """
            params = (embedding, modes, embedding, n_results)
        else:
            sql = """
                SELECT content, metadata, embedding <=> %s::vector AS distance
                FROM memory_embeddings
                WHERE mode = %s
                  AND NOT (metadata ? 'superseded_by')
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
