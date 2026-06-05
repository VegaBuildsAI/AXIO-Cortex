import importlib
import os
import unittest
from unittest.mock import patch


class MemoryBackendSelectionTests(unittest.TestCase):
    def test_json_backend_is_default(self):
        with patch.dict(os.environ, {"AXIO_MEMORY_BACKEND": ""}, clear=False):
            import core.config as config
            importlib.reload(config)
            import core.memory as memory
            importlib.reload(memory)
            mem = memory.MemoryManager("chat")

        self.assertEqual(mem.backend_name, "json")

    def test_postgres_backend_selected_by_env(self):
        with patch.dict(os.environ, {"AXIO_MEMORY_BACKEND": "postgres"}, clear=False):
            import core.config as config
            importlib.reload(config)
            import core.memory as memory
            importlib.reload(memory)
            mem = memory.MemoryManager("chat")

        self.assertEqual(mem.backend_name, "postgres")
        self.assertIsNotNone(mem._postgres_backend)


if __name__ == "__main__":
    unittest.main()
