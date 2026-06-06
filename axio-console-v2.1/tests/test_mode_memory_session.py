import unittest
from unittest.mock import patch

from core.mode_memory import ModeMemorySession, shared_recall_modes


class FakeMemoryManager:
    instances = []

    def __init__(self, mode):
        self.mode = mode
        self.prefix_calls = []
        self.facts_updates = []
        self.chunks = []
        self.stored = []
        self.commands = []
        FakeMemoryManager.instances.append(self)

    def build_memory_prefix(self, query="", allowed_modes=None):
        self.prefix_calls.append((query, allowed_modes))
        return f"[memory:{self.mode}:{query}]"

    def update_facts(self, patch):
        self.facts_updates.append(patch)

    def auto_update_facts(self, prompt, response):
        self.facts_updates.append({"auto": [prompt, response]})

    def store_chunk(self, text, metadata=None):
        self.chunks.append((text, metadata or {}))

    def store_session(self, session, ollama_client=None):
        self.stored.append((session, ollama_client))

    def get_facts(self):
        return {"notes": ["stored note"]}

    def stats(self):
        return {"mode": self.mode, "backend": "fake", "chroma_docs": 0, "last_session": "never"}


class ModeMemorySessionTests(unittest.TestCase):
    def setUp(self):
        FakeMemoryManager.instances = []

    def test_shared_recall_modes_excludes_revrec(self):
        self.assertEqual(
            shared_recall_modes("code"),
            ["code", "console", "chat", "cowork"],
        )
        self.assertEqual(shared_recall_modes("revrec"), ["revrec"])

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_prefix_uses_allowed_recall_modes(self):
        session = ModeMemorySession("cowork")

        prefix = session.prefix("AXIO Docker Memory")

        self.assertEqual(prefix, "[memory:cowork:AXIO Docker Memory]")
        self.assertEqual(
            session.memory.prefix_calls[0][1],
            ["cowork", "console", "chat", "code"],
        )

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_record_turn_builds_session_messages(self):
        session = ModeMemorySession("code")

        session.record_turn("fix bug", "fixed", model="qwen3-coder", metadata={"route": "local"})

        self.assertEqual(len(session.session["messages"]), 2)
        self.assertEqual(session.session["messages"][0]["role"], "user")
        self.assertEqual(session.session["messages"][1]["role"], "assistant")
        self.assertEqual(session.session["model"], "qwen3-coder")
        self.assertEqual(session.turn_metadata[0]["route"], "local")

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_record_private_writes_current_mode_chunk(self):
        session = ModeMemorySession("chat")

        session.record_private("Private project fact")

        self.assertEqual(session.memory.chunks[0][0], "Private project fact")
        self.assertEqual(session.memory.chunks[0][1]["source_type"], "manual_private")

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_record_global_writes_console_chunk(self):
        session = ModeMemorySession("chat")

        session.record_global("Global project fact")

        console = FakeMemoryManager.instances[-1]
        self.assertEqual(console.mode, "console")
        self.assertEqual(console.chunks[0][0], "Global project fact")
        self.assertEqual(console.chunks[0][1]["source_type"], "manual_global")

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_store_delegates_non_empty_session(self):
        session = ModeMemorySession("code")
        ollama = object()
        session.record_turn("task", "result")

        session.store(ollama_client=ollama)

        self.assertEqual(session.memory.stored[0][0]["mode"], "code")
        self.assertIs(session.memory.stored[0][1], ollama)

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_handle_command_private_and_share(self):
        session = ModeMemorySession("cowork")

        self.assertTrue(session.handle_command("memory private keep this in cowork"))
        self.assertTrue(session.handle_command("memory share keep this global"))

        self.assertEqual(session.memory.chunks[0][0], "keep this in cowork")
        console = FakeMemoryManager.instances[-1]
        self.assertEqual(console.mode, "console")
        self.assertEqual(console.chunks[0][0], "keep this global")


if __name__ == "__main__":
    unittest.main()
