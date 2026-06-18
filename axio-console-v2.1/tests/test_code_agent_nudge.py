import os
import tempfile
import unittest
from pathlib import Path

import modes.code as codemod


class FakeLogger:
    def log_tool(self, *a, **k):
        pass


# --- Minimal Anthropic-style response objects ---
class Blk:
    def __init__(self, type, text=None, name=None, input=None, id=None):
        self.type = type
        self.text = text
        self.name = name
        self.input = input
        self.id = id


class Resp:
    def __init__(self, content, stop_reason):
        self.content = content
        self.stop_reason = stop_reason


class FakeClaude:
    def __init__(self, scripted):
        self.scripted = scripted
        self.i = 0

    def tool_call(self, messages, tools, system=""):
        r = self.scripted[self.i]
        self.i += 1
        return r


class FakeOllama:
    def __init__(self, scripted):
        self.scripted = scripted
        self.i = 0

    def tool_call(self, model, messages, tools):
        r = self.scripted[self.i]
        self.i += 1
        return r


class CodeAgentNudgeTests(unittest.TestCase):
    def test_claude_narrates_then_creates_after_nudge(self):
        """Without the nudge, the agent would return on the planning turn and
        never write the file. With it, it gets nudged, executes, and finishes."""
        with tempfile.TemporaryDirectory() as d:
            target = str(Path(d) / "out.py")
            scripted = [
                Resp([Blk("text", text="Let me create both files:")], "end_turn"),
                Resp([Blk("tool_use", name="write_file",
                          input={"path": target, "content": "# ok\n"}, id="t1")], "tool_use"),
                Resp([Blk("text", text="TASK_COMPLETE archivos creados")], "end_turn"),
            ]
            result = codemod._run_claude_agent("crea archivo", FakeClaude(scripted), FakeLogger())

            self.assertTrue(os.path.exists(target), "tool never ran (premature stop)")
            self.assertIn("archivos creados", result)
            self.assertNotIn("TASK_COMPLETE", result)

    def test_claude_stops_after_max_consecutive_nudges(self):
        """Repeated no-tool turns must not loop forever."""
        scripted = [Resp([Blk("text", text="pensando...")], "end_turn")] * 10
        result = codemod._run_claude_agent("x", FakeClaude(scripted), FakeLogger())
        self.assertIsInstance(result, str)

    def test_ollama_narrates_then_creates_after_nudge(self):
        with tempfile.TemporaryDirectory() as d:
            target = str(Path(d) / "o.py")
            scripted = [
                {"message": {"content": "Voy a crear el archivo", "tool_calls": []}},
                {"message": {"content": "", "tool_calls": [
                    {"function": {"name": "write_file",
                                  "arguments": {"path": target, "content": "# ok"}}}]}},
                {"message": {"content": "TASK_COMPLETE listo", "tool_calls": []}},
            ]
            result = codemod._run_ollama_agent("crea", "m", FakeOllama(scripted), FakeLogger())

            self.assertTrue(os.path.exists(target), "tool never ran (premature stop)")
            self.assertIn("listo", result)
            self.assertNotIn("TASK_COMPLETE", result)


if __name__ == "__main__":
    unittest.main()
