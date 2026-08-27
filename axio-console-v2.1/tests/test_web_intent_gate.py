"""Web-intent detection, the web-evidence gate, and the GitHub toolset."""

import unittest
from unittest.mock import patch

from core.web_intent import detect_web_intent, has_web_evidence
from core.code_tools.registry import CodeToolRegistry, ToolExecutionRecord
import core.code_tools as code_tools
import core.code_tools.github_tools as github_tools
import modes.code as codemod


class _Blk:
    def __init__(self, type, text=None, name=None, input=None, id=None):
        self.type = type
        self.text = text
        self.name = name
        self.input = input
        self.id = id


class _Resp:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class _FakeClaude:
    def __init__(self, scripted):
        self.scripted = scripted
        self.i = 0

    def tool_call(self, messages, tools, system=""):
        r = self.scripted[self.i]
        self.i += 1
        return r


class _FakeLogger:
    def log_tool(self, *a, **k):
        pass


class WebIntentDetectionTests(unittest.TestCase):
    def test_lookup_verb_triggers(self):
        self.assertTrue(detect_web_intent("what is the latest FastAPI version? search the web"))

    def test_incidental_year_and_code_do_not_trigger(self):
        self.assertFalse(detect_web_intent("refactor this function and fix the 2026 date bug"))

    def test_explicit_override_wins(self):
        self.assertFalse(detect_web_intent("latest FastAPI version, no web, from memory"))


class WebCompletionStatusTests(unittest.TestCase):
    def test_gate_blocks_without_evidence_then_passes_with_it(self):
        reg = CodeToolRegistry()
        reg.start_task("what is the current release? search online")
        self.assertTrue(reg.state.web_evidence_required)
        ok, _ = reg.web_completion_status()
        self.assertFalse(ok)

        reg.records.append(
            ToolExecutionRecord(name="web_search", risk="read", arguments={}, result="{}", ok=True)
        )
        ok, _ = reg.web_completion_status()
        self.assertTrue(ok)

    def test_no_intent_means_no_gate(self):
        reg = CodeToolRegistry()
        reg.start_task("refactor the parser and add a test")
        self.assertFalse(reg.state.web_evidence_required)
        self.assertTrue(reg.web_completion_status()[0])

    def test_has_web_evidence_ignores_failed_calls(self):
        failed = [ToolExecutionRecord("web_search", "read", {}, "ERROR", ok=False)]
        self.assertFalse(has_web_evidence(failed))


class WebGateIntegrationTests(unittest.TestCase):
    def test_completion_blocked_for_web_task_without_web_tool(self):
        # A current-information task that never calls a web tool must not complete.
        scripted = [_Resp([_Blk("text", text="TASK_COMPLETE the latest is X")], "end_turn")] * 4
        result = codemod._run_claude_agent(
            "what is the latest stable FastAPI version? search the web",
            _FakeClaude(scripted),
            _FakeLogger(),
        )
        self.assertIn("web evidence", result.lower())


class GitHubToolsetTests(unittest.TestCase):
    def test_registered_and_unique(self):
        names = [t.name for t in code_tools.CODE_TOOL_REGISTRY.tools]
        self.assertEqual(len(names), len(set(names)), "duplicate tool names")
        for expected in ("github_push", "github_pr_create", "git_commit", "github_status"):
            self.assertIn(expected, names)

    def test_outward_actions_are_external_risk(self):
        risk = {t.name: t.risk for t in github_tools.TOOLS}
        for outward in ("github_push", "github_fork", "github_pr_create", "github_pr_merge"):
            self.assertEqual(risk[outward], "external")
        # Local commit is a write so it trips the verification gate before push.
        self.assertEqual(risk["git_commit"], "write")

    def test_relative_working_dir_is_rejected(self):
        result = github_tools.github_push(working_dir="not/absolute", branch="feature")
        self.assertFalse(result.ok)
        self.assertIn("absolute", result.content.lower())


if __name__ == "__main__":
    unittest.main()
