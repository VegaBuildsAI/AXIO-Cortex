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

    def test_find_similar_is_scoped_and_applies_threshold(self):
        conn = FakeConnection()
        conn.cursor_obj.row = {
            "id": "00000000-0000-0000-0000-000000000001",
            "content": "canonical lesson",
            "embedding": [0.0] * 768,
            "metadata": {"source_type": "self_learned"},
            "created_at": "2026-08-24T00:00:00",
            "similarity": 0.95,
        }
        backend = PostgresMemoryBackend("console", connection_factory=lambda: conn)

        result = backend.find_similar([0.0] * 768, "self_learned", threshold=0.92)

        sql, params = conn.cursor_obj.calls[-1]
        self.assertIn("WHERE mode = %s AND source_type = %s", sql)
        self.assertEqual(params[1:3], ("console", "self_learned"))
        self.assertEqual(result["content"], "canonical lesson")
        self.assertIsNone(backend.find_similar([0.0] * 768, "self_learned", threshold=0.99))

    def test_update_chunk_metadata_returns_mirror_payload(self):
        conn = FakeConnection()
        conn.cursor_obj.row = {
            "id": "00000000-0000-0000-0000-000000000001",
            "content": "lesson",
            "embedding": [0.0] * 768,
            "metadata": {"reinforced_count": 2},
            "created_at": "2026-08-24T00:00:00",
        }
        backend = PostgresMemoryBackend("console", connection_factory=lambda: conn)

        result = backend.update_chunk_metadata(
            "00000000-0000-0000-0000-000000000001",
            {"reinforced_count": 2},
        )

        sql, params = conn.cursor_obj.calls[-1]
        self.assertIn("UPDATE memory_embeddings", sql)
        self.assertEqual(params[2], "console")
        self.assertEqual(result["content"], "lesson")
        self.assertEqual(conn.commits, 1)

    def test_recent_messages_joins_session_mode_and_uses_watermark(self):
        conn = FakeConnection()
        conn.cursor_obj.rows = [{"id": "m1", "mode": "code", "role": "assistant"}]
        backend = PostgresMemoryBackend("console", connection_factory=lambda: conn)

        rows = backend.recent_messages("2026-08-24T00:00:00+00:00", limit=50)

        sql, params = conn.cursor_obj.calls[-1]
        self.assertIn("JOIN sessions", sql)
        self.assertIn("m.created_at > %s", sql)
        self.assertEqual(params[-1], 50)
        self.assertEqual(rows[0]["mode"], "code")

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
        self.assertIn("metadata ? 'superseded_by'", executed_sql)

    def test_recall_without_modes_filters_to_backend_mode(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)
        conn.cursor_obj.rows = []

        backend.recall([0.0] * 768, n_results=2)

        sql, params = conn.cursor_obj.calls[-1]
        self.assertIn("WHERE mode = %s", sql)
        self.assertEqual(params[1], "chat")

    def test_recall_with_allowed_modes_filters_to_those_modes(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("code", connection_factory=lambda: conn)
        conn.cursor_obj.rows = [
            {"content": "Cowork remembered AXIO", "metadata": {"mode": "cowork"}, "distance": 0.1}
        ]

        rows = backend.recall(
            [0.0] * 768,
            n_results=3,
            modes=["code", "cowork", "chat", "console"],
        )

        sql, params = conn.cursor_obj.calls[-1]
        self.assertIn("WHERE mode = ANY(%s)", sql)
        self.assertEqual(params[1], ["code", "cowork", "chat", "console"])
        self.assertEqual(rows[0]["metadata"]["mode"], "cowork")

    def test_persist_session_writes_session_messages_and_embedding(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)
        session = {
            "name": "chat_1", "mode": "chat", "model": "mistral",
            "created": "2026-06-06T10:00:00", "updated": "2026-06-06T10:05:00",
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        }

        sid = backend.persist_session(session, "a summary", [0.0] * 768)

        joined = "\n".join(call[0] for call in conn.cursor_obj.calls)
        self.assertIn("INSERT INTO sessions", joined)
        self.assertEqual(joined.count("INSERT INTO messages"), 2)
        self.assertIn("INSERT INTO memory_embeddings", joined)
        self.assertIsInstance(sid, str)
        self.assertEqual(conn.commits, 1)

    def test_persist_live_session_upserts_before_clean_exit(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("cowork", connection_factory=lambda: conn)
        session = {
            "id": "c4d7c02e-f4c2-4c4f-b85e-a8d879271c83",
            "name": "cowork_live",
            "mode": "cowork",
            "model": "gemma4:12b",
            "created": "2026-08-24T19:00:00",
            "messages": [
                {
                    "id": "669471ae-e0ad-48e2-b406-107941492c61",
                    "role": "user",
                    "content": "persist before model completes",
                    "created_at": "2026-08-24T19:00:01",
                }
            ],
        }

        sid = backend.persist_live_session(session)

        joined = "\n".join(call[0] for call in conn.cursor_obj.calls)
        self.assertIn("ON CONFLICT (id)", joined)
        self.assertIn("INSERT INTO sessions", joined)
        self.assertIn("INSERT INTO messages", joined)
        self.assertEqual(sid, session["id"])
        self.assertEqual(conn.commits, 1)

    def test_persist_session_without_embedding_skips_embeddings_table(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)
        session = {
            "name": "c", "mode": "chat", "model": "m",
            "created": "", "updated": "",
            "messages": [{"role": "user", "content": "hi"}],
        }

        backend.persist_session(session, "summary", None)

        joined = "\n".join(call[0] for call in conn.cursor_obj.calls)
        self.assertIn("INSERT INTO sessions", joined)
        self.assertNotIn("INSERT INTO memory_embeddings", joined)

    def test_persist_session_rejects_wrong_embedding_dimension(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)
        session = {"messages": [{"role": "user", "content": "hi"}]}

        with self.assertRaises(ValueError):
            backend.persist_session(session, "summary", [0.1, 0.2])

    def test_update_facts_records_source_session_id(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)

        backend.update_facts({"user_name": "Michael"}, source_session_id="sess-123")

        sql, params = conn.cursor_obj.calls[-1]
        self.assertIn("source_session_id", sql)
        self.assertIn("sess-123", params)


if __name__ == "__main__":
    unittest.main()
