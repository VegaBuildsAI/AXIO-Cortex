import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.memory import MemoryManager


def _session(mode, content="Acme Corp ASC 606 SaaS deal"):
    return {
        "name":     f"{mode}_test",
        "mode":     mode,
        "model":    "qwen3:14b",
        "created":  "",
        "updated":  "",
        "messages": [{"role": "user", "content": content}],
    }


def _local_manager(mode):
    mem = MemoryManager(mode)
    mem._postgres_backend = None
    mem._chroma = None
    mem._chroma_client = None
    return mem


class RevRecIsolationTests(unittest.TestCase):
    def test_revrec_store_session_does_not_touch_console(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.memory.MEMORY_DIR", Path(tmp)), \
                    patch("core.memory_durability.JOURNAL_DIR", Path(tmp) / "journals"):
                mem = _local_manager("revrec")
                with patch.object(mem, "_update_console_master") as upd, \
                        patch.object(mem, "_summarize_session", return_value="summary"):
                    mem.store_session(_session("revrec"))
                    upd.assert_not_called()

    def test_non_isolated_mode_still_updates_console(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("core.memory.MEMORY_DIR", Path(tmp)), \
                    patch("core.memory_durability.JOURNAL_DIR", Path(tmp) / "journals"):
                mem = _local_manager("chat")
                with patch.object(mem, "_update_console_master") as upd, \
                        patch.object(mem, "_summarize_session", return_value="summary"):
                    mem.store_session(_session("chat", "hello there"))
                    upd.assert_called_once()


if __name__ == "__main__":
    unittest.main()
