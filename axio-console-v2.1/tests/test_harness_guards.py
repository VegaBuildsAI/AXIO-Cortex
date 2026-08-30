"""Harness guards: verification credit for Python checks + run_python GUI guard."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.code_tools.python_tools import run_python
from core.code_tools.verification import verification_ids_from_command


class VerificationCreditTests(unittest.TestCase):
    def test_py_compile_counts(self):
        self.assertIn("compile", verification_ids_from_command('py -m py_compile "a b/tetris.py"'))

    def test_selftest_counts(self):
        self.assertIn("python:selftest",
                      verification_ids_from_command('python "C:\\x\\tetris.py" --selftest'))

    def test_pytest_and_unittest_count(self):
        self.assertIn("python:tests", verification_ids_from_command("pytest -q tests"))
        self.assertIn("python:tests", verification_ids_from_command("py -m unittest -v"))

    def test_plain_python_run_counts(self):
        self.assertIn("python:tetris.py", verification_ids_from_command('py "tetris.py"'))

    def test_npm_still_works(self):
        self.assertIn("npm:build", verification_ids_from_command("npm run build"))

    def test_non_verification_command_is_empty(self):
        self.assertEqual(verification_ids_from_command("echo hello"), ())


class RunPythonGuardTests(unittest.TestCase):
    GUI = (
        "import sys\n"
        "if '--selftest' in sys.argv:\n"
        "    print('SELFTEST OK'); sys.exit(0)\n"
        "import tkinter as tk\n"
        "tk.Tk().mainloop()\n"
    )

    def test_gui_script_without_flag_is_refused_not_run(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "game.py"
            p.write_text(self.GUI, encoding="utf-8")
            out = run_python(str(p))               # no args → would open a window
            self.assertFalse(out.ok)
            self.assertTrue(out.content.startswith("SKIPPED"))

    def test_gui_script_with_selftest_runs(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "game.py"
            p.write_text(self.GUI, encoding="utf-8")
            out = run_python(str(p), args=["--selftest"])
            self.assertTrue(out.ok, out.content)
            self.assertIn("EXIT CODE: 0", out.content)
            self.assertIn("python:game.py", out.verification_ids)

    def test_plain_script_runs_normally(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "hello.py"
            p.write_text("print('hi')\n", encoding="utf-8")
            out = run_python(str(p))
            self.assertTrue(out.ok, out.content)
            self.assertIn("hi", out.content)


if __name__ == "__main__":
    unittest.main()
