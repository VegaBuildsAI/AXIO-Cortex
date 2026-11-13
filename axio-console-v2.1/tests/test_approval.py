import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core import approval
from core.code_tools.tool_loop import interactive_approver


def tool(risk, name="t"):
    return SimpleNamespace(risk=risk, name=name)


class ApprovalPolicyTests(unittest.TestCase):
    def setUp(self):
        self._saved = approval.get_level()

    def tearDown(self):
        approval.set_level(self._saved)

    def test_levels_decide_by_risk(self):
        approval.set_level("off")
        self.assertFalse(any(approval.auto_approves(tool(r)) for r in ("execute", "write", "destructive", "external")))
        approval.set_level("on")
        self.assertTrue(approval.auto_approves(tool("execute")))
        self.assertTrue(approval.auto_approves(tool("write")))
        self.assertFalse(approval.auto_approves(tool("destructive")))
        self.assertFalse(approval.auto_approves(tool("external")))
        approval.set_level("all")
        self.assertTrue(all(approval.auto_approves(tool(r)) for r in ("execute", "write", "destructive", "external")))

    def test_command_parsing(self):
        self.assertIn("AUTO -", approval.handle_auto_command("auto on"))
        self.assertEqual(approval.get_level(), "on")
        self.assertIn("AUTO ALL", approval.handle_auto_command("/auto all"))
        self.assertIn("OFF", approval.handle_auto_command("auto off"))
        self.assertEqual(approval.get_level(), "off")
        self.assertIn("auto on", approval.handle_auto_command("auto"))  # shows usage
        # Ordinary messages are not swallowed as commands.
        self.assertIsNone(approval.handle_auto_command("auto complete"))
        self.assertIsNone(approval.handle_auto_command("auto fix the failing test"))
        self.assertIsNone(approval.handle_auto_command("automatic"))
        self.assertEqual(approval.get_level(), "off")

    def test_invalid_level_rejected(self):
        with self.assertRaises(ValueError):
            approval.set_level("maybe")

    def test_tool_loop_approver_skips_prompt_when_auto(self):
        approval.set_level("on")
        with patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertTrue(interactive_approver(tool("execute", "run_command"), {"command": "py -V"}))
        # Destructive still asks under "on".
        with patch("builtins.input", return_value="no") as asked:
            self.assertFalse(interactive_approver(tool("destructive", "delete_file"), {"path": "x"}))
            asked.assert_called_once()

    def test_tool_loop_approver_asks_when_off(self):
        approval.set_level("off")
        with patch("builtins.input", return_value="y") as asked:
            self.assertTrue(interactive_approver(tool("execute", "run_command"), {}))
            asked.assert_called_once()

    def test_code_mode_approver_follows_policy(self):
        from modes import code

        approval.set_level("all")
        with patch("builtins.input", side_effect=AssertionError("prompted")):
            self.assertTrue(code._approve_tool(tool("external", "github_push"), {}))
        approval.set_level("off")
        with patch("builtins.input", return_value="n"):
            self.assertFalse(code._approve_tool(tool("execute", "run_command"), {}))

    def test_registry_runs_gated_tool_without_prompt_when_auto(self):
        from core.code_tools import build_default_registry

        registry = build_default_registry()
        calls = []
        approval.set_level("on")
        with patch("builtins.input", side_effect=AssertionError("prompted")):
            registry.execute(
                "run_command", {"command": "echo hi"},
                approve=lambda t, a: calls.append(t.name) or interactive_approver(t, a),
            )
        self.assertEqual(calls, ["run_command"])
        self.assertNotIn("CANCELLED", registry.records[-1].result)


if __name__ == "__main__":
    unittest.main()
