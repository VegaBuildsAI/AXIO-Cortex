"""The web orchestrated Code path streams the plan + live agent flow to SSE."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from harness.plan import Plan, PlanStep
from web_api.services import AxioServices


class OrchestratedBridgeTests(unittest.TestCase):
    def test_orchestrated_worker_streams_plan_and_events(self):
        emitted: list[tuple[str, dict]] = []

        class FakeRuns:
            def emit(self, run_id, event, data):
                emitted.append((event, data))
                return None

            def request_approval(self, *args, **kwargs):
                return SimpleNamespace(decision="approved")

        class FakeStore:
            def get(self, conversation_id):
                return {"id": conversation_id, "workspace_id": "ws"}

        class FakeWorkspaces:
            def get(self, workspace_id):
                return {"path": "C:/tmp/ws"}

        service = AxioServices(FakeStore(), FakeWorkspaces(), FakeRuns())
        # Keep the test off the real memory/audit path.
        service._finish_turn = lambda *a, **k: emitted.append(("finish", {"summary": a[2]}))

        plan = Plan("do it", [
            PlanStep(1, "IMPLEMENT", "write the file", "FSAgent"),
            PlanStep(2, "TEST", "run the tests", "TestAgent", depends_on=(1,)),
        ])

        def fake_orchestrated(task, *, provider, model=None, ollama=None, claude=None,
                              approve=None, memory_prefix="", verbose=True, parallel=True,
                              printer=print, on_plan=None, on_event=None):
            on_plan(plan)
            on_event({"kind": "step_start", "step": 1, "agent": "FSAgent", "phase": "IMPLEMENT"})
            on_event({"kind": "step_end", "step": 1, "agent": "FSAgent", "phase": "IMPLEMENT", "outcome": "OK"})
            return "done summary"

        run = SimpleNamespace(id="run", conversation_id="c", cancel=threading.Event())
        with patch("core.runtime_mode.get_local_only", new=lambda: False), \
             patch("web_api.services.ClaudeClient", lambda *a, **k: object()), \
             patch("web_api.services.run_orchestrated", fake_orchestrated):
            service._code_worker_orchestrated(run, "do it")

        events = [name for name, _ in emitted]
        self.assertIn("agent_plan", events)
        self.assertEqual(events.count("agent_event"), 2)
        self.assertIn("finish", events)

        plan_payload = next(data for name, data in emitted if name == "agent_plan")
        self.assertEqual(plan_payload["task"], "do it")
        self.assertEqual([s["agent"] for s in plan_payload["steps"]], ["FSAgent", "TestAgent"])
        self.assertEqual({a["name"] for a in plan_payload["agents"]}, {"FSAgent", "TestAgent"})

        summary = next(data for name, data in emitted if name == "finish")
        self.assertEqual(summary["summary"], "done summary")


if __name__ == "__main__":
    unittest.main()
