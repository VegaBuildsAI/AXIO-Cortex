import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.config import MODE_BACKENDS, MODELS
from web_api.runs import RunManager
from web_api.services import AxioServices
from web_api.store import ConversationStore
from web_api.workspaces import WorkspaceRegistry


class DeterministicRoutingTests(unittest.TestCase):
    def test_ui_mode_backends_are_fixed(self):
        self.assertEqual(MODE_BACKENDS["chat"], "ollama")
        self.assertEqual(MODE_BACKENDS["cowork"], "ollama")
        self.assertEqual(MODE_BACKENDS["code"], "claude")
        self.assertEqual(MODELS["chat"], "gemma4:12b")
        self.assertEqual(MODELS["coding"], "gemma4:12b")

    def test_data_root_can_be_redirected_out_of_user_home(self):
        with tempfile.TemporaryDirectory() as temp:
            env = {**os.environ, "AXIO_DATA_ROOT": temp}
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from core.config import AXIO_DATA_ROOT, MEMORY_DIR; "
                        "print(AXIO_DATA_ROOT); print(MEMORY_DIR)"
                    ),
                ],
                cwd=Path(__file__).resolve().parent.parent,
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )

        paths = completed.stdout.strip().splitlines()
        self.assertEqual(Path(paths[0]), Path(temp).resolve())
        self.assertEqual(Path(paths[1]), Path(temp).resolve() / "memory")


class ConversationStoreTests(unittest.TestCase):
    def test_conversation_round_trip_and_safe_id(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ConversationStore(Path(temp))
            conversation = store.create("chat", "New conversation")
            store.add_message(conversation["id"], "user", "Hello AXIO")

            loaded = store.get(conversation["id"])

            self.assertEqual(loaded["title"], "Hello AXIO")
            self.assertEqual(loaded["messages"][0]["content"], "Hello AXIO")
            self.assertIsNone(store.get("../escape"))


class WorkspaceRegistryTests(unittest.TestCase):
    def test_files_use_opaque_ids_and_paths_cannot_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            root.mkdir()
            (root / "app.py").write_text("print('AXIO')", encoding="utf-8")
            (root / ".env").write_text("SECRET=hidden", encoding="utf-8")
            registry = WorkspaceRegistry(Path(temp) / "workspaces.json")
            workspace = registry.open(str(root))

            files = registry.files(workspace["id"])

            self.assertEqual([item["relative_path"] for item in files], ["app.py"])
            self.assertNotEqual(files[0]["id"], "app.py")
            with self.assertRaises(ValueError):
                registry.resolve(workspace["id"], "../outside.txt", must_exist=False)


class RunApprovalTests(unittest.TestCase):
    def test_protected_action_waits_for_explicit_approval(self):
        manager = RunManager()
        observed = {}

        def worker(run):
            approval = manager.request_approval(
                run,
                "run_command",
                {"command": "echo safe"},
                timeout=2,
            )
            observed["decision"] = approval.decision

        run = manager.create("conversation", "code", worker)
        deadline = time.time() + 2
        approval_id = None
        while time.time() < deadline and not approval_id:
            for event in run.events:
                if event["type"] == "approval_required":
                    approval_id = event["data"]["approval_id"]
                    break
            time.sleep(0.01)

        self.assertIsNotNone(approval_id)
        manager.resolve_approval(approval_id, "approved")
        deadline = time.time() + 2
        while time.time() < deadline and run.status not in {"completed", "failed"}:
            time.sleep(0.01)

        self.assertEqual(observed["decision"], "approved")
        self.assertEqual(run.status, "completed")


class ServiceFailureTests(unittest.TestCase):
    def test_memory_permission_failure_warns_without_failing_saved_response(self):
        class FakeStore:
            def add_message(self, *args, **kwargs):
                return {"id": "message", "role": "assistant"}

        class FakeRuns:
            def __init__(self):
                self.events = []

            def emit(self, run_id, event_type, data):
                self.events.append((event_type, data))

        runs = FakeRuns()
        service = AxioServices(FakeStore(), object(), runs)
        run = SimpleNamespace(
            id="run",
            conversation_id="conversation",
            cancel=threading.Event(),
        )

        with patch("web_api.services.AuditLogger"), patch(
            "web_api.services.ModeMemorySession",
            side_effect=PermissionError("memory is read-only"),
        ):
            service._finish_turn(run, "prompt", "response", "chat", "qwen3:14b")

        self.assertIn("message", [event[0] for event in runs.events])
        warnings = [data for event, data in runs.events if event == "warning"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("response was saved", warnings[0]["message"])

    def test_code_connection_error_is_actionable(self):
        class FakeStore:
            def get(self, conversation_id):
                return {"id": conversation_id, "workspace_id": "workspace"}

        class FakeRuns:
            def emit(self, *args, **kwargs):
                return None

        class OfflineClaude:
            def __init__(self, *args, **kwargs):
                pass

            def tool_call(self, *args, **kwargs):
                raise RuntimeError("Connection error.")

        service = AxioServices(FakeStore(), object(), FakeRuns())
        service._conversation_messages = lambda conversation_id: [
            {"role": "user", "content": "diagnostic"}
        ]
        run = SimpleNamespace(
            id="run",
            conversation_id="conversation",
            cancel=threading.Event(),
        )

        # This exercises the Claude cloud path, so force LOCAL_ONLY off (otherwise
        # _code_worker dispatches to the local Ollama agent and ignores the mock).
        with patch("web_api.services.LOCAL_ONLY", False), patch(
            "web_api.services.ClaudeClient", OfflineClaude
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "launch AXIO with run_ui.cmd outside a restricted sandbox",
            ):
                service._code_worker(run, "diagnostic", [])


if __name__ == "__main__":
    unittest.main()
