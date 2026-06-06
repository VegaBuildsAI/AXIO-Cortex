import unittest
from unittest.mock import patch

from core.memory import MemoryManager


class FakePostgresBackend:
    def __init__(self):
        self.recall_calls = []

    def get_facts(self):
        return {}

    def recall(self, embedding, n_results, modes=None):
        self.recall_calls.append((embedding, n_results, modes))
        return [{"text": "cross-mode hit", "metadata": {"mode": "cowork"}, "distance": 0.1}]


class MemoryCrossModeTests(unittest.TestCase):
    def test_memory_manager_passes_allowed_modes_to_postgres_backend(self):
        mem = MemoryManager("code")
        backend = FakePostgresBackend()
        mem._postgres_backend = backend

        with patch.object(mem, "_embed_via_ollama", return_value=[0.0] * 768):
            rows = mem.recall(
                "AXIO Docker Memory",
                n_results=4,
                allowed_modes=["code", "cowork", "chat", "console"],
            )

        self.assertEqual(rows[0]["text"], "cross-mode hit")
        self.assertEqual(
            backend.recall_calls[0][2],
            ["code", "cowork", "chat", "console"],
        )


if __name__ == "__main__":
    unittest.main()
