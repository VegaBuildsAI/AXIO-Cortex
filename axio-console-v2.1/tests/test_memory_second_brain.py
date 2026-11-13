"""Second Brain: prefix section, recall filters, and the safe import path."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import memory_runtime
from core.memory import MemoryManager
from core.memory_backends.postgres_backend import PostgresMemoryBackend
from tests.test_postgres_backend_unit import FakeConnection


class FakeBrainBackend:
    """Backend fake that honours the optional source_types filter."""

    def __init__(self):
        self.recall_calls = []
        self.general = [
            {"text": "session summary hit", "metadata": {"mode": "chat"},
             "source_type": "session_summary", "distance": 0.1},
            {"text": "[Second Brain] a.md — A:\nshared", "metadata": {"source_type": "second_brain"},
             "source_type": "second_brain", "distance": 0.2},
        ]
        self.brain = [
            {"text": "[Second Brain] a.md — A:\nshared", "metadata": {"source_type": "second_brain"},
             "source_type": "second_brain", "distance": 0.2},
            {"text": "[Second Brain] b.md — B:\n" + "x" * 3000,
             "metadata": {"source_type": "second_brain"}, "source_type": "second_brain", "distance": 0.3},
            {"text": "[Second Brain] c.md — C:\nthird", "metadata": {"source_type": "second_brain"},
             "source_type": "second_brain", "distance": 0.4},
        ]

    def get_facts(self):
        return {}

    def recall(self, embedding, n_results, modes=None, source_types=None):
        self.recall_calls.append({"n": n_results, "modes": modes, "source_types": source_types})
        rows = self.brain if source_types else self.general
        return rows[:n_results]


class SecondBrainPrefixTests(unittest.TestCase):
    def _manager(self, mode="chat"):
        mem = MemoryManager(mode)
        mem._postgres_backend = FakeBrainBackend()
        mem._chroma = None
        return mem

    def test_prefix_adds_deduplicated_capped_second_brain_section(self):
        mem = self._manager()
        embed_calls = []

        def fake_embed(text):
            embed_calls.append(text)
            return [0.0] * 768

        with patch.object(mem, "_embed_via_ollama", side_effect=fake_embed), \
                patch.object(mem, "reconcile_pending", return_value=0):
            prefix = mem.build_memory_prefix(
                "what is a", allowed_modes=["chat", "console", "cowork", "code"]
            )

        self.assertIn("=== RELEVANT MEMORY ===", prefix)
        self.assertIn("=== SECOND BRAIN ===", prefix)
        brain = prefix.split("=== SECOND BRAIN ===", 1)[1]
        self.assertNotIn("shared", brain)            # already in RELEVANT MEMORY
        self.assertIn("b.md", brain)
        self.assertIn("third", brain)
        self.assertIn("brain_read", brain)           # truncated chunk points at the tool
        self.assertLess(len(brain), 1500 + 400)
        brain_call = mem._postgres_backend.recall_calls[1]
        self.assertEqual(brain_call["modes"], ["console"])
        self.assertEqual(brain_call["source_types"], ["second_brain"])
        self.assertEqual(len(embed_calls), 1)        # one embedding for both lookups

    def test_revrec_prefix_never_queries_the_brain(self):
        mem = self._manager("revrec")
        with patch.object(mem, "_embed_via_ollama", return_value=[0.0] * 768), \
                patch.object(mem, "reconcile_pending", return_value=0):
            prefix = mem.build_memory_prefix("anything", allowed_modes=["revrec"])
        self.assertNotIn("SECOND BRAIN", prefix)
        self.assertTrue(all(c["source_types"] is None for c in mem._postgres_backend.recall_calls))

    def test_brain_failure_leaves_prefix_unchanged(self):
        mem = self._manager()
        with patch.object(mem, "_embed_via_ollama", return_value=[0.0] * 768), \
                patch.object(mem, "reconcile_pending", return_value=0), \
                patch.object(mem, "_second_brain_section", side_effect=RuntimeError("boom")):
            prefix = mem.build_memory_prefix("q", allowed_modes=["chat", "console"])
        self.assertIn("session summary hit", prefix)
        self.assertNotIn("SECOND BRAIN", prefix)

    def test_filtered_recall_never_falls_back_to_fact_keywords(self):
        mem = MemoryManager("chat")
        mem._postgres_backend = None
        mem._chroma = None
        with patch.object(mem, "_facts_for_mode", return_value={"notes": ["anything goes"]}):
            self.assertEqual(mem.recall("anything", source_types=["second_brain"]), [])
            self.assertTrue(mem.recall("anything"))


class BackendRecallTests(unittest.TestCase):
    def test_recall_sets_exact_probes_in_same_transaction_before_select(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)
        backend.recall([0.0] * 768, n_results=5, modes=["chat", "console"])
        first_sql, first_params = conn.cursor_obj.calls[0]
        self.assertIn("set_config('ivfflat.probes'", first_sql)
        self.assertTrue(first_params[0].isdigit())
        self.assertIn("ORDER BY embedding <=>", conn.cursor_obj.calls[1][0])

    def test_source_types_filter_only_when_set(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)
        backend.recall([0.0] * 768, n_results=4, modes=["console"])
        self.assertNotIn("source_type = ANY", conn.cursor_obj.calls[-1][0])

        backend.recall([0.0] * 768, n_results=4, modes=["console"], source_types=["second_brain"])
        sql, params = conn.cursor_obj.calls[-1]
        self.assertIn("source_type = ANY(%s)", sql)
        self.assertEqual(params[1], ["console"])
        self.assertEqual(params[2], ["second_brain"])
        self.assertEqual(params[-1], 4)


class FakeImportManager:
    def __init__(self, fail_on=None):
        self.fail_on = fail_on
        self.deleted = []
        self.stored = []

    def embed_text(self, text):
        if self.fail_on and self.fail_on in text:
            return None
        return [0.0] * 768

    def delete_chunks(self, source_type, key, value):
        self.deleted.append((source_type, key, value))

    def store_chunk(self, text, metadata=None, embedding=None):
        self.stored.append((text, metadata, embedding))


class ImportPathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_iter_vault_notes_skips_obsidian_git_and_empty(self):
        (self.vault / ".obsidian").mkdir()
        (self.vault / ".obsidian" / "x.md").write_text("cfg", encoding="utf-8")
        (self.vault / ".git").mkdir()
        (self.vault / ".git" / "y.md").write_text("git", encoding="utf-8")
        (self.vault / "empty.md").write_text("", encoding="utf-8")
        (self.vault / "01-Projects").mkdir()
        (self.vault / "01-Projects" / "minios.md").write_text("# MiniOS", encoding="utf-8")
        rels = [rel for _p, rel in memory_runtime.iter_vault_notes(self.vault)]
        self.assertEqual(rels, ["01-Projects/minios.md"])

    def test_ingest_records_order_and_mtime_then_replaces(self):
        note = self.vault / "n.md"
        long_body = "y" * (memory_runtime.MAX_CHARS + 10)
        note.write_text(f"intro text\n## A\nalpha\n## B\n{long_body}", encoding="utf-8")
        mgr = FakeImportManager()
        n = memory_runtime._ingest(mgr, note, "second_brain", "path", "n.md", "n.md", "Second Brain")
        self.assertEqual(n, 4)
        self.assertEqual(mgr.deleted, [("second_brain", "path", "n.md")])
        metas = [meta for _t, meta, _e in mgr.stored]
        self.assertEqual([m["chunk_index"] for m in metas], [0, 1, 2, 3])
        self.assertEqual([m["section_part"] for m in metas], [0, 0, 0, 1])
        self.assertTrue(all(m["note_mtime"] == note.stat().st_mtime for m in metas))
        self.assertTrue(all(e for _t, _m, e in mgr.stored))

    def test_ingest_deletes_nothing_when_any_embedding_fails(self):
        note = self.vault / "n.md"
        note.write_text("## A\nalpha\n## B\nbeta", encoding="utf-8")
        mgr = FakeImportManager(fail_on="beta")
        with self.assertRaises(memory_runtime.EmbeddingUnavailable):
            memory_runtime._ingest(mgr, note, "second_brain", "path", "n.md", "n.md", "Second Brain")
        self.assertEqual(mgr.deleted, [])
        self.assertEqual(mgr.stored, [])

    def test_sync_logs_pending_count_when_ollama_offline(self):
        (self.vault / "a.md").write_text("alpha", encoding="utf-8")
        (self.vault / "b.md").write_text("beta", encoding="utf-8")
        logs = []
        state = {"files": {}}
        with patch.object(memory_runtime, "VAULT", self.vault), \
                patch.object(memory_runtime, "SEED_DOCS", []), \
                patch.object(memory_runtime.OllamaClient, "is_running", return_value=False):
            changed = memory_runtime.sync_files(FakeImportManager(), state, logs.append)
        self.assertEqual(changed, 0)
        self.assertEqual(state["files"], {})
        self.assertTrue(any("Ollama offline" in line and "2 Second Brain note(s)" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
