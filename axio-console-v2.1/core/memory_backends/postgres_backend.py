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
