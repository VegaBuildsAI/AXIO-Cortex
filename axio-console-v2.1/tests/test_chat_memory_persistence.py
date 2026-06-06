import unittest

from modes.chat import _store_chat_memory
from core.mode_memory import ModeMemorySession


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


def _make_memory_session(messages):
    """Build a real ModeMemorySession without constructing a live MemoryManager."""
    ms = ModeMemorySession.__new__(ModeMemorySession)
    ms.mode = "chat"
    ms.memory = FakeMemoryManager()
    ms.allowed_recall_modes = ["chat"]
    ms.session = {"messages": messages}
    ms.turn_metadata = []
    return ms


class ChatMemoryPersistenceTests(unittest.TestCase):
    """Covers the production persistence path used by chat.run()."""

    def test_saves_session_and_stores_non_empty_session_in_memory(self):
        sm = FakeSessionManager()
        memory = _make_memory_session([{"role": "user", "content": "remember this"}])
        ollama = object()
        session = {"messages": [{"role": "user", "content": "remember this"}]}

        _store_chat_memory(sm, memory, session, ollama)

        self.assertEqual(sm.saved, [session])
        self.assertEqual(memory.memory.stored, [(memory.session, ollama)])

    def test_does_not_store_empty_session_in_memory(self):
        sm = FakeSessionManager()
        memory = _make_memory_session([])
        session = {"messages": []}

        _store_chat_memory(sm, memory, session, None)

        self.assertEqual(sm.saved, [session])
        self.assertEqual(memory.memory.stored, [])


if __name__ == "__main__":
    unittest.main()
