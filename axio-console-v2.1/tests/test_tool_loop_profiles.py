"""Tests for the shared tool loop and per-mode tool profiles."""

from __future__ import annotations

import unittest

from core.code_tools import CODE_TOOL_REGISTRY
from core.code_tools.profiles import (
    CHAT_TOOLS,
    COWORK_TOOLS,
    all_tool_names,
    profile_tool_names,
)
from core.code_tools.tool_loop import run_tool_loop


class FakeOllama:
    """Returns a scripted sequence of /api/chat tool-call responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def tool_call(self, model, messages, tools):
        self.calls += 1
        return self._responses.pop(0)


def _msg(content="", tool_calls=None):
    m = {"content": content}
    if tool_calls is not None:
        m["tool_calls"] = tool_calls
    return {"message": m}


class ProfileTests(unittest.TestCase):
    def test_profiles_are_subsets_of_registry(self):
        known = {t.name for t in CODE_TOOL_REGISTRY.tools}
        for name in CHAT_TOOLS + COWORK_TOOLS:
            self.assertIn(name, known, f"{name} not in registry")

    def test_chat_has_web_and_document_tools(self):
        names = set(profile_tool_names("chat"))
        for expected in ("web_search", "web_fetch", "create_docx", "write_file"):
            self.assertIn(expected, names)

    def test_cowork_is_superset_of_chat(self):
        self.assertTrue(set(profile_tool_names("chat")).issubset(profile_tool_names("cowork")))

    def test_code_profile_is_full_registry(self):
        self.assertEqual(set(profile_tool_names("code")), set(all_tool_names()))
        self.assertEqual(len(all_tool_names()), 42)

    def test_unknown_names_are_dropped(self):
        # An unknown mode falls back to the full registry, not a crash.
        self.assertEqual(set(profile_tool_names("does-not-exist")), set(all_tool_names()))


class ToolLoopTests(unittest.TestCase):
    def test_returns_final_text_when_no_tool_calls(self):
        fake = FakeOllama([_msg(content="hello there")])
        messages = [{"role": "user", "content": "hi"}]
        out = run_tool_loop(
            tool_names=CHAT_TOOLS, provider="ollama", model="x",
            ollama=fake, messages=messages, verbose=False,
        )
        self.assertEqual(out, "hello there")

    def test_executes_allowed_tool_then_finishes(self):
        # First turn asks to list_dir (a read tool, no approval), second finishes.
        responses = [
            _msg(tool_calls=[{"function": {"name": "list_dir", "arguments": {"path": "."}}}]),
            _msg(content="done"),
        ]
        fake = FakeOllama(responses)
        messages = [{"role": "user", "content": "list files"}]
        out = run_tool_loop(
            tool_names=CHAT_TOOLS + ("list_dir",), provider="ollama", model="x",
            ollama=fake, messages=messages, approve=lambda *_: True, verbose=False,
        )
        self.assertEqual(out, "done")
        self.assertTrue(any(m.get("role") == "tool" for m in messages))

    def test_out_of_profile_tool_is_isolated(self):
        # run_command is NOT in the chat profile -> must be refused, not executed.
        responses = [
            _msg(tool_calls=[{"function": {"name": "run_command", "arguments": {"command": "echo hi"}}}]),
            _msg(content="ok"),
        ]
        fake = FakeOllama(responses)
        messages = [{"role": "user", "content": "run something"}]
        run_tool_loop(
            tool_names=CHAT_TOOLS, provider="ollama", model="x",
            ollama=fake, messages=messages, approve=lambda *_: True, verbose=False,
        )
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        self.assertTrue(tool_msgs)
        self.assertTrue(tool_msgs[0]["content"].startswith("ISOLATION_ERROR"))


if __name__ == "__main__":
    unittest.main()
