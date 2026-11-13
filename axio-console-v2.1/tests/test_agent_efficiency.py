"""Token and latency savings for local agents: cards, routing, keep-alive."""

import os
import unittest
from unittest.mock import MagicMock, patch

import modes.code as codemod
from core.code_tools import CODE_TOOL_REGISTRY
from core.coding_skills import build_coding_system_prompt, render_tool_calling_skills
from core.config import CODE_SKILL_MAX_CHARS, routing_mode_for
from core.models import OllamaClient


class FakeLogger:
    def log_tool(self, *a, **k):
        pass


class RecordingOllama:
    """Returns a final answer at once and records what each step was sent."""

    def __init__(self):
        self.calls = []

    def tool_call(self, model, messages, tools):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": list(tools)})
        return {"message": {"content": "TASK_COMPLETE nothing to change", "tool_calls": []}}


class ToolCardTests(unittest.TestCase):
    def test_cards_only_for_given_tools(self):
        cards = render_tool_calling_skills(tool_names=["read_file", "write_file"])
        self.assertIn("`read_file`", cards)
        self.assertIn("`write_file`", cards)
        self.assertNotIn("`git_diff`", cards)
        self.assertIn(f"(2/{len(CODE_TOOL_REGISTRY.tools)})", cards)
        self.assertIn("request_tool", cards)

    def test_full_catalog_when_no_names(self):
        cards = render_tool_calling_skills()
        for tool in CODE_TOOL_REGISTRY.tools:
            self.assertIn(f"`{tool.name}`", cards)

    def test_dynamic_system_prompt_is_smaller_and_not_truncated(self):
        full = build_coding_system_prompt("implement a module")
        small = build_coding_system_prompt(
            "implement a module", tool_names=["read_file", "edit_file", "run_command"]
        )
        self.assertLess(len(small), len(full) - 5000)
        self.assertLess(len(small), CODE_SKILL_MAX_CHARS)
        self.assertIn("`run_command`", small)


class RoutingModeTests(unittest.TestCase):
    def test_auto_is_dynamic_locally_and_full_for_claude(self):
        with patch.dict(os.environ, {"AXIO_CODE_TOOL_ROUTING_MODE": "auto"}):
            self.assertEqual(routing_mode_for("ollama"), "dynamic")
            self.assertEqual(routing_mode_for("claude"), "full")

    def test_explicit_mode_wins(self):
        with patch.dict(os.environ, {"AXIO_CODE_TOOL_ROUTING_MODE": "full"}):
            self.assertEqual(routing_mode_for("ollama"), "full")
        with patch.dict(os.environ, {"AXIO_CODE_TOOL_ROUTING_MODE": "dynamic"}):
            self.assertEqual(routing_mode_for("claude"), "dynamic")
        with patch.dict(os.environ, {"AXIO_CODE_TOOL_ROUTING_MODE": "nonsense"}):
            self.assertEqual(routing_mode_for("ollama"), "dynamic")

    def test_local_agent_sends_small_stable_prompt(self):
        fake = RecordingOllama()
        with patch.dict(os.environ, {"AXIO_CODE_TOOL_ROUTING_MODE": "auto"}):
            codemod._run_ollama_agent("implement a small module", "m", fake, FakeLogger())
        first = fake.calls[0]
        tool_names = {t["function"]["name"] for t in first["tools"]}
        self.assertLessEqual(len(tool_names), 8)
        self.assertIn("request_tool", tool_names)
        system = first["messages"][0]["content"]
        self.assertLess(len(system), CODE_SKILL_MAX_CHARS)
        # Cards exist only for tools the model can see.
        for tool in CODE_TOOL_REGISTRY.tools:
            if tool.name not in tool_names:
                self.assertNotIn(f"- `{tool.name}` —", system)


class KeepAliveTests(unittest.TestCase):
    def _ok(self, body):
        response = MagicMock()
        response.ok = True
        response.raise_for_status = lambda: None
        response.json = lambda: body
        return response

    def test_keep_alive_sent_only_when_set(self):
        body = {"message": {"content": "hi"}, "prompt_eval_count": 1, "eval_count": 1}
        with patch("core.models.requests.post", return_value=self._ok(body)) as post, \
                patch.object(OllamaClient, "_supports_thinking", return_value=False):
            OllamaClient(keep_alive="-1").tool_call("gemma4:12b", [], [])
            self.assertEqual(post.call_args.kwargs["json"]["keep_alive"], -1)
            OllamaClient(keep_alive="30m").tool_call("gemma4:12b", [], [])
            self.assertEqual(post.call_args.kwargs["json"]["keep_alive"], "30m")
            OllamaClient().tool_call("gemma4:12b", [], [])
            self.assertNotIn("keep_alive", post.call_args.kwargs["json"])

    def test_unload_kept_frees_used_models(self):
        body = {"message": {"content": "hi"}}
        client = OllamaClient(keep_alive="-1")
        with patch("core.models.requests.post", return_value=self._ok(body)) as post, \
                patch.object(OllamaClient, "_supports_thinking", return_value=False):
            client.tool_call("gemma4:12b", [], [])
            freed = client.unload_kept()
        self.assertEqual(freed, ["gemma4:12b"])
        last = post.call_args
        self.assertTrue(last.args[0].endswith("/api/generate"))
        self.assertEqual(last.kwargs["json"], {"model": "gemma4:12b", "keep_alive": 0})
        self.assertEqual(client.unload_kept(), [])  # nothing left to free

    def test_background_client_keeps_ollama_default(self):
        self.assertIsNone(OllamaClient().keep_alive)


if __name__ == "__main__":
    unittest.main()
