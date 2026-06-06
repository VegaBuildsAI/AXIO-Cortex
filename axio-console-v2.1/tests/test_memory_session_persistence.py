import unittest
from unittest.mock import patch

from core.memory import MemoryManager


class FakePgBackend:
    def __init__(self):
        self.persisted = []
        self.fact_calls = []

    def get_facts(self):
        return {}

    def persist_session(self, session, summary, embedding):
        self.persisted.append((session, summary, embedding))
        return "sess-xyz"

    def update_facts(self, facts, source_session_id=None):
        self.fact_calls.append(source_session_id)


class MemorySessionPersistenceTests(unittest.TestCase):
    def _manager(self):
        mem = MemoryManager("chat")
        mem._postgres_backend = FakePgBackend()
        mem._chroma = None
        mem._chroma_client = None
        return mem

    def test_store_session_persists_session_and_links_facts(self):
        mem = self._manager()
        backend = mem._postgres_backend
        session = {
            "name": "s", "mode": "chat", "model": "m",
            "created": "", "updated": "",
            "messages": [{"role": "user", "content": "hi"}],
        }

        with patch.object(mem, "_summarize_session", return_value="summary"), \
                patch.object(mem, "_embed_via_ollama", return_value=[0.0] * 768), \
                patch.object(mem, "_update_console_master"):
            mem.store_session(session)

        self.assertEqual(len(backend.persisted), 1)
        self.assertEqual(backend.persisted[0][1], "summary")
        self.assertEqual(backend.persisted[0][2], [0.0] * 768)
        self.assertIn("sess-xyz", backend.fact_calls)


if __name__ == "__main__":
    unittest.main()
