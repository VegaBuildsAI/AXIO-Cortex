"""run_npm_script must not block the console on long-running dev/watch scripts."""

from __future__ import annotations

import json
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from core.code_tools import node_tools
from core.code_tools.node_tools import _is_long_running, run_npm_script


class LongRunningDetectionTests(unittest.TestCase):
    def test_server_names_are_long_running(self):
        for name in ("dev", "start", "serve", "watch", "preview", "storybook"):
            self.assertTrue(_is_long_running(name, ""), name)

    def test_watch_marker_in_body(self):
        self.assertTrue(_is_long_running("css", "tailwind -i in.css -o out.css --watch"))
        self.assertTrue(_is_long_running("api", "nodemon server.js"))

    def test_one_shot_scripts_are_not_long_running(self):
        self.assertFalse(_is_long_running("build", "vite build"))     # 'vite' alone must not trip it
        self.assertFalse(_is_long_running("test", "jest"))
        self.assertFalse(_is_long_running("lint", "eslint ."))


class RunNpmScriptRoutingTests(unittest.TestCase):
    def _pkg(self, tmp: Path):
        (tmp / "package.json").write_text(json.dumps({"scripts": {
            "dev": "vite", "build": "vite build",
        }}), encoding="utf-8")

    def test_dev_script_is_launched_detached_not_blocking(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            self._pkg(tmp)
            with mock.patch.object(node_tools.shutil, "which", return_value="npm"), \
                 mock.patch.object(node_tools, "_launch_detached",
                                   return_value=node_tools.ToolResult("DETACHED-OK", ok=True)) as det, \
                 mock.patch.object(node_tools.subprocess, "run",
                                   side_effect=AssertionError("must not block on dev")):
                out = run_npm_script(str(tmp), "dev")
            self.assertIn("DETACHED-OK", out.content)
            det.assert_called_once()

    def test_build_script_runs_synchronously(self):
        with TemporaryDirectory() as d:
            tmp = Path(d)
            self._pkg(tmp)
            fake_proc = types.SimpleNamespace(returncode=0, stdout="built", stderr="")
            with mock.patch.object(node_tools.shutil, "which", return_value="npm"), \
                 mock.patch.object(node_tools, "_launch_detached",
                                   side_effect=AssertionError("build must not detach")), \
                 mock.patch.object(node_tools.subprocess, "run", return_value=fake_proc):
                out = run_npm_script(str(tmp), "build")
            self.assertIn("EXIT CODE: 0", out.content)
            self.assertTrue(out.ok)


if __name__ == "__main__":
    unittest.main()
