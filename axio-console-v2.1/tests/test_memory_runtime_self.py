import unittest
from unittest.mock import Mock, patch

from core import memory_runtime


class Backend:
    def healthcheck(self):
        return True


class Manager:
    def __init__(self):
        self._postgres_backend = Backend()
        self.reconcile_calls = 0

    def reconcile_pending(self):
        self.reconcile_calls += 1
        return 0

    def stats(self):
        return {"embedding_count": 0}


class Engine:
    def __init__(self, dry_run=True):
        self.dry_run = dry_run

    def consolidate_summaries(self, rows):
        return len(rows)


class MemoryRuntimeSelfTests(unittest.TestCase):
    def test_dry_run_does_not_save_state_or_reconcile_outbox(self):
        manager = Manager()
        state = {"files": {}, "mirror_version": memory_runtime.MIRROR_VERSION}
        with patch("core.memory_runtime.MemoryManager", return_value=manager), \
                patch("core.memory_runtime._load_state", return_value=state), \
                patch("core.memory_runtime._save_state") as save, \
                patch("core.memory_runtime.plan_sync", return_value={
                    "seed_changed": 0, "vault_changed": 0, "removed": 0,
                }):
            result = memory_runtime.run(
                once=True,
                do_sync=True,
                do_consolidate=False,
                do_reflect=False,
                dry_run=True,
                log=lambda *_: None,
            )

        self.assertEqual(result, 0)
        self.assertEqual(manager.reconcile_calls, 0)
        save.assert_not_called()

    def test_second_writer_yields_without_running_cycle(self):
        manager = Manager()
        lock = Mock()
        lock.acquire.return_value = False
        with patch("core.memory_runtime.MemoryManager", return_value=manager), \
                patch("core.memory_runtime.SingleInstanceLock", return_value=lock), \
                patch("core.memory_runtime._run_cycles") as cycles:
            result = memory_runtime.run(once=True, log=lambda *_: None)

        self.assertEqual(result, 0)
        cycles.assert_not_called()

    def test_dry_run_consolidation_does_not_advance_watermark(self):
        state = {"consolidate_watermark": "old"}
        rows = [{
            "id": "s1", "mode": "chat", "summary": "summary",
            "ended_at": "2026-08-24T00:00:00+00:00",
        }]
        with patch("core.memory_runtime._recent_summaries", return_value=rows), \
                patch("core.memory_runtime.OllamaClient.is_running", return_value=True):
            count = memory_runtime.consolidate(
                Mock(), state, lambda *_: None, engine=Engine(dry_run=True)
            )

        self.assertEqual(count, 1)
        self.assertEqual(state["consolidate_watermark"], "old")


if __name__ == "__main__":
    unittest.main()
