import unittest

from modes.chat import _save_and_store_memory


class FakeSessionManager:
    def __init__(self):
        self.saved = []

    def save(self, session):
        self.saved.append(session)


class FakeMemoryManager:
    def __init__(self):
        self.stored = []

    def store_session(self, session, ollama_client=None):
        self.stored.append((session, ollama_client))


class ChatMemoryPersistenceTests(unittest.TestCase):
    def test_saves_session_and_stores_non_empty_session_in_memory(self):
        sm = FakeSessionManager()
        mem = FakeMemoryManager()
        ollama = object()
        session = {"messages": [{"role": "user", "content": "remember this"}]}

        _save_and_store_memory(sm, mem, session, ollama)

        self.assertEqual(sm.saved, [session])
        self.assertEqual(mem.stored, [(session, ollama)])

    def test_does_not_store_empty_session_in_memory(self):
        sm = FakeSessionManager()
        mem = FakeMemoryManager()
        session = {"messages": []}

        _save_and_store_memory(sm, mem, session, None)

        self.assertEqual(sm.saved, [session])
        self.assertEqual(mem.stored, [])


if __name__ == "__main__":
    unittest.main()
