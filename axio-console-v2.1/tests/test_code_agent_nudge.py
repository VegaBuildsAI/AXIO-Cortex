import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    def test_multiline_input_preserves_lines_until_explicit_end(self):
        lines = iter(["primera linea", "segunda linea", "::end"])

        result = codemod.read_multiline_task(lambda _prompt: next(lines), max_chars=100)

        self.assertEqual(result, "primera linea\nsegunda linea")

    def test_multiline_input_rejects_oversize_instead_of_truncating(self):
        lines = iter(["123456", "::end"])

        with self.assertRaisesRegex(ValueError, "exceeds"):
            codemod.read_multiline_task(lambda _prompt: next(lines), max_chars=5)

    def test_context_commands_restore_native_folder_and_file_pickers(self):
        with patch.object(codemod.SESSION_CONTEXT, "load_browse_folder", return_value="folder") as folder:
            self.assertEqual(codemod.handle_context_command("browse", "browse"), (True, "folder"))
            folder.assert_called_once_with()

        with patch.object(codemod.SESSION_CONTEXT, "load_browse_files", return_value="files") as files:
            self.assertEqual(codemod.handle_context_command("browse files", "browse files"), (True, "files"))
            files.assert_called_once_with()

    def test_ollama_continues_and_combines_output_limit_chunks(self):
        scripted = [
            {"done_reason": "length", "message": {"content": "parte uno", "tool_calls": []}},
            {"done_reason": "stop", "message": {"content": "TASK_COMPLETE parte dos", "tool_calls": []}},
        ]
        client = FakeOllama(scripted)

        result = codemod._run_ollama_agent("explica", "m", client, FakeLogger())

        self.assertEqual(client.i, 2)
        self.assertIn("parte uno", result)
        self.assertIn("parte dos", result)

    def test_claude_continues_and_combines_max_token_chunks(self):
        scripted = [
            Resp([Blk("text", text="parte uno")], "max_tokens"),
            Resp([Blk("text", text="TASK_COMPLETE parte dos")], "end_turn"),
        ]
        client = FakeClaude(scripted)

        result = codemod._run_claude_agent("explica", client, FakeLogger())

        self.assertEqual(client.i, 2)
        self.assertIn("parte uno", result)
        self.assertIn("parte dos", result)

    def test_claude_narrates_then_creates_after_nudge(self):
        """Without the nudge, the agent would return on the planning turn and
        never write the file. With it, it gets nudged, executes, and finishes."""
        with tempfile.TemporaryDirectory() as d:
            target = str(Path(d) / "out.py")
            scripted = [
                Resp([Blk("text", text="Let me create both files:")], "end_turn"),
                Resp([Blk("tool_use", name="write_file",
                          input={"path": target, "content": "# ok\n"}, id="t1")], "tool_use"),
                Resp([Blk("tool_use", name="run_python",
                          input={"script_path": target, "working_dir": d}, id="t2")], "tool_use"),
                Resp([Blk("tool_use", name="verification_gate",
                          input={"required_checks": ["python:out.py"]}, id="t3")], "tool_use"),
                Resp([Blk("text", text="TASK_COMPLETE archivos creados")], "end_turn"),
            ]
            with patch("builtins.input", return_value="y"):
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
                {"message": {"content": "", "tool_calls": [
                    {"function": {"name": "run_python",
                                  "arguments": {"script_path": target, "working_dir": d}}}]}},
                {"message": {"content": "", "tool_calls": [
                    {"function": {"name": "verification_gate",
                                  "arguments": {"required_checks": ["python:o.py"]}}}]}},
                {"message": {"content": "TASK_COMPLETE listo", "tool_calls": []}},
            ]
            with patch("builtins.input", return_value="y"):
                result = codemod._run_ollama_agent("crea", "m", FakeOllama(scripted), FakeLogger())

            self.assertTrue(os.path.exists(target), "tool never ran (premature stop)")
            self.assertIn("listo", result)
            self.assertNotIn("TASK_COMPLETE", result)

    def test_completion_is_blocked_after_write_without_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            target = str(Path(directory) / "unverified.py")
            scripted = [
                Resp([Blk("tool_use", name="write_file",
                          input={"path": target, "content": "# changed\n"}, id="t1")], "tool_use"),
                Resp([Blk("text", text="TASK_COMPLETE done")], "end_turn"),
                Resp([Blk("text", text="TASK_COMPLETE done")], "end_turn"),
                Resp([Blk("text", text="TASK_COMPLETE done")], "end_turn"),
            ]
            with patch("builtins.input", return_value="y"):
                result = codemod._run_claude_agent("change file", FakeClaude(scripted), FakeLogger())

        self.assertIn("stopped without verification", result.lower())


if __name__ == "__main__":
    unittest.main()
