import unittest
from unittest.mock import patch

from core.config import CODE_INPUT_MAX_CHARS, INPUT_MAX_CHARS
from core.console_input import (
    capture_summary,
    is_multiline_command,
    read_multiline_input,
)
from modes import chat, code, cowork


class _FakeLogger:
    def log_event(self, *args, **kwargs):
        pass

    def log_turn(self, *args, **kwargs):
        pass


class _FakeMemory:
    def __init__(self):
        self.session = {"messages": []}
        self.user_messages = []

    def prefix(self, _prompt):
        return ""

    def record_turn(self, prompt, *_args, **_kwargs):
        self.user_messages.append(prompt)

    def record_user(self, prompt, **_kwargs):
        self.user_messages.append(prompt)

    def record_assistant(self, *_args, **_kwargs):
        pass

    def handle_command(self, *_args, **_kwargs):
        return False

    def store(self, **_kwargs):
        pass


class _FakeChatSessions:
    last = None

    def __init__(self):
        type(self).last = self
        self.session = None
        self.turns = []

    def new(self, name=None, model="", mode="chat"):
        self.session = {
            "name": name or "test",
            "model": model,
            "mode": mode,
            "backend": "ollama",
            "messages": [],
        }
        return self.session

    def load(self, _name):
        return None

    def save(self, _session):
        pass

    def message_count(self, session):
        return len(session["messages"])

    def add_turn(self, session, prompt, response):
        self.turns.append((prompt, response))
        session["messages"].extend([
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response},
        ])


class ConsoleMultilineInputTests(unittest.TestCase):
    def test_all_modes_advertise_multiline_capture(self):
        self.assertIn("/paste", chat.HELP)
        self.assertIn("paste", cowork.HELP)
        self.assertIn("paste", code.HELP)

    def test_all_supported_commands_are_recognized(self):
        for command in ("paste", "multiline", "/paste", "/multiline", "  /PASTE  "):
            with self.subTest(command=command):
                self.assertTrue(is_multiline_command(command))
        self.assertFalse(is_multiline_command("paste this text"))

    def test_preserves_lines_blank_lines_and_command_like_content_exactly(self):
        lines = iter(["  first line  ", "", "/help", "last line ", "::end"])

        result = read_multiline_input(lambda _prompt: next(lines), max_chars=100)

        self.assertEqual(result, "  first line  \n\n/help\nlast line ")

    def test_accepts_exact_configured_character_budget(self):
        first = "a" * 30_000
        second = "b" * 29_999
        lines = iter([first, second, "::end"])

        result = read_multiline_input(lambda _prompt: next(lines))

        self.assertEqual(len(result), INPUT_MAX_CHARS)
        self.assertEqual(CODE_INPUT_MAX_CHARS, INPUT_MAX_CHARS)

    def test_rejects_one_character_over_budget_without_returning_partial_text(self):
        lines = iter(["x" * (INPUT_MAX_CHARS + 1), "::end"])

        with self.assertRaisesRegex(ValueError, "AXIO_INPUT_MAX_CHARS"):
            read_multiline_input(lambda _prompt: next(lines))

    def test_cancel_discards_the_capture(self):
        lines = iter(["do not send", "::cancel"])

        self.assertEqual(read_multiline_input(lambda _prompt: next(lines)), "")

    def test_eof_returns_every_complete_line_received(self):
        lines = iter(["one", "two"])

        def reader(_prompt):
            try:
                return next(lines)
            except StopIteration as exc:
                raise EOFError from exc

        self.assertEqual(read_multiline_input(reader), "one\ntwo")

    def test_capture_summary_reports_exact_size_and_lines(self):
        self.assertEqual(
            capture_summary("one\ntwo\nthree"),
            "Captured 13 characters across 3 line(s).",
        )

    def test_chat_loop_sends_multiline_capture_as_one_exact_turn(self):
        class FakeOllama:
            def list_models(self):
                return []

            def is_running(self):
                return True

            def chat_stream(self, _model, messages):
                self.messages = messages
                return "answer"

        memory = _FakeMemory()
        inputs = iter(["/paste", "first", "second", "::end", "/exit"])
        with (
            patch.object(chat, "LOCAL_ONLY", True),
            patch.object(chat, "OllamaClient", FakeOllama),
            patch.object(chat, "SessionManager", _FakeChatSessions),
            patch.object(chat, "AuditLogger", lambda _mode: _FakeLogger()),
            patch.object(chat, "ModeMemorySession", lambda _mode: memory),
            patch("builtins.input", side_effect=lambda _prompt="": next(inputs)),
            patch("builtins.print"),
            patch.object(chat, "mode_banner"),
            patch.object(chat, "status_line"),
            patch.object(chat, "divider"),
        ):
            chat.run()

        self.assertEqual(_FakeChatSessions.last.turns, [("first\nsecond", "answer")])
        self.assertEqual(memory.user_messages, ["first\nsecond"])

    def test_cowork_loop_does_not_execute_command_like_multiline_content(self):
        class FakeOllama:
            def is_running(self):
                return True

            def generate_stream(self, _model, prompt):
                self.prompt = prompt
                return "answer", 0.1

        memory = _FakeMemory()
        inputs = iter(["paste", "/help", "second", "::end", "exit"])
        with (
            patch.object(cowork, "LOCAL_ONLY", True),
            patch.object(cowork, "OllamaClient", FakeOllama),
            patch.object(cowork, "AuditLogger", lambda _mode: _FakeLogger()),
            patch.object(cowork, "ModeMemorySession", lambda _mode: memory),
            patch.object(cowork.ModelRouter, "detect", return_value=("fast", "gemma")),
            patch("builtins.input", side_effect=lambda _prompt="": next(inputs)),
            patch("builtins.print"),
            patch.object(cowork, "mode_banner"),
            patch.object(cowork, "divider"),
        ):
            cowork.run()

        self.assertEqual(memory.user_messages, ["/help\nsecond"])


if __name__ == "__main__":
    unittest.main()
