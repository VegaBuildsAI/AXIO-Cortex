import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from core import memory_consolidation


class ExitConsolidationTests(unittest.TestCase):
    @patch("core.memory_consolidation.RUNTIME_SCRIPT", Path("C:/AXIO/runtime.py"))
    @patch("core.memory_consolidation._runtime_python", return_value=Path("C:/AXIO/python.exe"))
    @patch("core.memory_consolidation.subprocess.Popen")
    @patch("core.memory_consolidation.Path.exists", return_value=True)
    def test_trigger_starts_one_shot_consolidation(self, _exists, popen, _python):
        started = memory_consolidation.trigger_exit_consolidation()

        self.assertTrue(started)
        command = popen.call_args.args[0]
        self.assertEqual(
            command,
            [
                "C:\\AXIO\\python.exe",
                "C:\\AXIO\\runtime.py",
                "--once",
                "--consolidate-only",
            ],
        )
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs["env"]["AXIO_MEMORY_BACKEND"], "postgres")
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        if os.name == "nt":
            self.assertIn("creationflags", kwargs)
        else:
            self.assertTrue(kwargs["start_new_session"])

    @patch("core.memory_consolidation.RUNTIME_SCRIPT", Path("C:/missing/runtime.py"))
    def test_missing_runtime_is_non_fatal(self):
        self.assertFalse(memory_consolidation.trigger_exit_consolidation())

    @patch("core.memory_consolidation.RUNTIME_SCRIPT", Path("C:/AXIO/runtime.py"))
    @patch("core.memory_consolidation.subprocess.Popen", side_effect=OSError("blocked"))
    @patch("core.memory_consolidation.Path.exists", return_value=True)
    def test_spawn_failure_is_non_fatal(self, _exists, _popen):
        self.assertFalse(memory_consolidation.trigger_exit_consolidation())


if __name__ == "__main__":
    unittest.main()
