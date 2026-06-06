import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.memory import MemoryManager


class CrossModeKeywordRecallTests(unittest.TestCase):
    """Cross-mode recall must work on the default (non-Postgres) backend too."""

    def _make_manager(self, mode, tmp_path):
        mem = MemoryManager(mode)
        mem._postgres_backend = None
        mem._chroma = None
        mem._chroma_client = None
        return mem

    def test_recall_surfaces_facts_from_allowed_sibling_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch("core.memory.MEMORY_DIR", tmp_path):
                (tmp_path / "cowork_memory.json").write_text(
                    json.dumps({"active_projects": ["AXIO Cortex migration"]}),
                    encoding="utf-8",
                )
                mem = self._make_manager("code", tmp_path)
                hits = mem.recall(
                    "Cortex migration",
                    allowed_modes=["code", "cowork", "console"],
                )
        texts = " ".join(h["text"] for h in hits)
        self.assertIn("AXIO Cortex migration", texts)

    def test_recall_without_allowed_modes_stays_single_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch("core.memory.MEMORY_DIR", tmp_path):
                (tmp_path / "cowork_memory.json").write_text(
                    json.dumps({"active_projects": ["AXIO Cortex migration"]}),
                    encoding="utf-8",
                )
                mem = self._make_manager("code", tmp_path)
                hits = mem.recall("Cortex migration")
        texts = " ".join(h["text"] for h in hits)
        self.assertNotIn("AXIO Cortex migration", texts)


if __name__ == "__main__":
    unittest.main()
