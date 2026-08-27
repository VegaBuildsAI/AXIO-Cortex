import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.memory import MemoryManager
from core.memory_durability import pending_count


class RaisingBackend:
    def get_facts(self):
        raise RuntimeError("pg down")

    def recall(self, *args, **kwargs):
        raise RuntimeError("pg down")

    def store_chunk(self, *args, **kwargs):
        raise RuntimeError("pg down")


class FakeChroma:
    def __init__(self):
        self.upserts = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def count(self):
        return 1

    def query(self, **kwargs):
        return {
            "documents": [["local semantic fallback"]],
            "metadatas": [[{"mode": "cowork", "source_type": "test"}]],
            "distances": [[0.1]],
        }


class MemoryResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            patch("core.memory.MEMORY_DIR", self.root / "memory"),
            patch("core.memory.CHROMA_DIR", self.root / "chroma"),
            patch("core.memory._CHROMA_OK", False),
            patch("core.memory_durability.JOURNAL_DIR", self.root / "journals"),
            patch("core.memory_durability.PENDING_DIR", self.root / "outbox" / "pending"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def _local_manager(self, mode="cowork"):
        mem = MemoryManager(mode)
        mem._postgres_backend = None
        mem._chroma = None
        mem._chroma_client = None
        return mem

    def test_console_global_profile_is_always_in_cowork_prefix(self):
        memory_dir = self.root / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "console_memory.json").write_text(
            json.dumps({
                "global_profile": {
                    "user_name": "Michael",
                    "preferred_language": "Spanish",
                    "key_projects": ["AXIO Cortex"],
                }
            }),
            encoding="utf-8",
        )
        mem = self._local_manager("cowork")

        prefix = mem.build_memory_prefix("")

        self.assertIn("User name: Michael", prefix)
        self.assertIn("Preferred language: Spanish", prefix)
        self.assertIn("Key projects: AXIO Cortex", prefix)

    def test_promoted_principles_are_always_loaded_in_cowork_prefix(self):
        memory_dir = self.root / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        (memory_dir / "console_memory.json").write_text(
            json.dumps({"learned_principles": ["Validar evidencia antes de afirmar"]}),
            encoding="utf-8",
        )
        mem = self._local_manager("cowork")

        prefix = mem.build_memory_prefix("")

        self.assertIn("Learned principles", prefix)
        self.assertIn("Validar evidencia antes de afirmar", prefix)

    def test_postgres_failure_writes_chroma_and_durable_outbox(self):
        mem = self._local_manager("cowork")
        mem._postgres_backend = RaisingBackend()
        mem._chroma = FakeChroma()
        mem._chroma_client = object()
        with patch.object(mem, "_embed_via_ollama", return_value=[0.0] * 768):
            mem.store_chunk("durable memory", {"source_type": "test"})

        self.assertEqual(len(mem._chroma.upserts), 1)
        self.assertEqual(pending_count(), 1)

        with patch.object(mem, "reconcile_pending", return_value=0), \
                patch.object(mem, "_chroma_collection", return_value=mem._chroma), \
                patch.object(mem, "_embed_via_ollama", return_value=[0.0] * 768):
            hits = mem.recall("durable", allowed_modes=["cowork"])
        self.assertEqual(hits[0]["text"], "local semantic fallback")

    def test_required_primary_write_raises_but_keeps_local_and_outbox(self):
        mem = self._local_manager("console")
        mem._postgres_backend = RaisingBackend()
        mem._chroma = FakeChroma()
        mem._chroma_client = object()

        with patch.object(mem, "_embed_via_ollama", return_value=[0.0] * 768):
            with self.assertRaises(RuntimeError):
                mem.store_chunk(
                    "must reach primary",
                    {"source_type": "self_learned"},
                    require_primary=True,
                )

        self.assertEqual(len(mem._chroma.upserts), 1)
        self.assertEqual(pending_count(), 1)

    def test_cross_mode_metadata_replay_refreshes_correct_chroma_collection(self):
        from core.memory_durability import enqueue

        mirror = FakeChroma()

        class Backend:
            def __init__(self, mode):
                self.mode = mode

            def update_chunk_metadata(self, chunk_id, metadata):
                return {
                    "id": chunk_id,
                    "content": "updated console lesson",
                    "embedding": [0.0] * 768,
                    "metadata": metadata,
                }

        mem = self._local_manager("chat")
        mem._postgres_backend = object()
        enqueue(
            "chunk_metadata",
            "console",
            {"chunk_id": "chunk-1", "metadata": {
                "source_type": "self_learned", "reinforced_count": 2,
            }},
            event_id="metadata-event",
        )

        with patch(
            "core.memory_backends.postgres_backend.PostgresMemoryBackend", Backend
        ), patch.object(mem, "_chroma_collection", return_value=mirror):
            replayed = mem.reconcile_pending()

        self.assertEqual(replayed, 1)
        self.assertEqual(len(mirror.upserts), 1)
        self.assertEqual(mirror.upserts[0]["documents"], ["updated console lesson"])

    def test_prefix_uses_all_configured_recall_results(self):
        mem = self._local_manager("chat")
        rows = [
            {"text": f"memory-{index}", "metadata": {}, "distance": index / 10}
            for index in range(5)
        ]
        with patch.object(mem, "recall", return_value=rows):
            prefix = mem.build_memory_prefix("AXIO")
        self.assertIn("memory-4", prefix)

    def test_poison_event_does_not_wedge_queue_and_dead_letters(self):
        """A permanent-failure event must not block healthy events (head-of-line)
        and must be quarantined into outbox/dead after repeated attempts."""
        from core import memory_durability as dur
        from core.memory_durability import enqueue, pending_events

        dead_dir = self.root / "outbox" / "dead"
        good_calls = []

        class FakeBackend:
            def __init__(self, mode):
                self.mode = mode

            def store_chunk(self, *args, **kwargs):
                # Permanent poison: wrong-dimension embedding -> ValueError.
                raise ValueError("Expected embedding dimension 768, got 512")

            def persist_live_session(self, session):
                good_calls.append(session.get("id"))

        mem = self._local_manager("cowork")
        mem._postgres_backend = object()  # truthy so reconcile_pending runs

        # Poison chunk enqueued BEFORE the good event (head-of-line position).
        enqueue("chunk", "cowork",
                {"chunk_id": "poison", "text": "bad",
                 "embedding": [0.0] * 768, "metadata": {}},
                event_id="poison")
        enqueue("live_session", "cowork", {"session": {"id": "good"}}, event_id="good")

        with patch("core.memory_backends.postgres_backend.PostgresMemoryBackend", FakeBackend), \
                patch("core.memory_durability.DEAD_DIR", dead_dir):
            mem.reconcile_pending()
            # Good event drained despite the poison sitting ahead of it.
            self.assertEqual(good_calls, ["good"])
            remaining = {event["event_id"] for event in pending_events()}
            self.assertIn("poison", remaining)
            self.assertNotIn("good", remaining)

            # Keep reconciling; poison quarantines after MAX_REPLAY_ATTEMPTS.
            for _ in range(dur.MAX_REPLAY_ATTEMPTS):
                mem.reconcile_pending()

        self.assertEqual(pending_count(), 0)                       # queue fully drained
        self.assertEqual(len(list(dead_dir.glob("*.json"))), 1)    # poison quarantined, not lost


if __name__ == "__main__":
    unittest.main()
