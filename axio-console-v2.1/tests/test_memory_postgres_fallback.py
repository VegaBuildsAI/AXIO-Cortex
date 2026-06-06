import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.memory import MemoryManager


class RaisingBackend:
    """Simulates a Postgres backend that is configured but unreachable."""

    def get_facts(self):
        raise RuntimeError("pg down")

    def update_facts(self, facts):
        raise RuntimeError("pg down")

    def recall(self, *args, **kwargs):
        raise RuntimeError("pg down")

    def store_chunk(self, *args, **kwargs):
        raise RuntimeError("pg down")

    def stats(self):
        raise RuntimeError("pg down")


class PostgresFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mem = MemoryManager("chat")
        self.mem._postgres_backend = RaisingBackend()
        self.mem._chroma = None
        self.mem._facts_path = Path(self.tmp.name) / "chat_memory.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_get_facts_falls_back_to_defaults(self):
        facts = self.mem.get_facts()
        self.assertIn("user_name", facts)

    def test_update_facts_falls_back_to_json(self):
        self.mem.update_facts({"user_name": "Michael"})
        self.assertTrue(self.mem._facts_path.exists())
        self.assertEqual(self.mem.get_facts()["user_name"], "Michael")

    def test_recall_falls_back_to_keyword_when_backend_raises(self):
        with patch.object(self.mem, "_embed_via_ollama", return_value=[0.0] * 768):
            result = self.mem.recall("anything")
        self.assertIsInstance(result, list)

    def test_store_chunk_does_not_raise_when_backend_raises(self):
        with patch.object(self.mem, "_embed_via_ollama", return_value=[0.0] * 768):
            self.mem.store_chunk("summary text", {"mode": "chat"})

    def test_stats_falls_back_when_backend_raises(self):
        stats = self.mem.stats()
        self.assertEqual(stats["mode"], "chat")


if __name__ == "__main__":
    unittest.main()
