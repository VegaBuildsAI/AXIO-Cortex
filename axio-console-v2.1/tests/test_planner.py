"""Planner: JSON plan parsing, coercion/fallback, and an orchestrated run."""

from __future__ import annotations

import json
import unittest

from harness.planner import build_plan, plan_from_model_output, run_orchestrated


class PlanParsingTests(unittest.TestCase):
    def test_parses_valid_json_plan(self):
        raw = json.dumps({"task": "add a helper", "steps": [
            {"id": 1, "phase": "IMPLEMENT", "description": "write helper", "agent": "FSAgent", "depends_on": []},
            {"id": 2, "phase": "TEST", "description": "run tests", "agent": "TestAgent", "depends_on": [1]},
        ]})
        plan = plan_from_model_output("add a helper", raw)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[1].agent, "TestAgent")
        self.assertEqual(plan.steps[1].depends_on, (1,))

    def test_json_inside_code_fence_and_prose(self):
        raw = "Sure!\n```json\n" + json.dumps({"steps": [
            {"id": 1, "phase": "IMPLEMENT", "description": "x", "agent": "FSAgent"}]}) + "\n```"
        plan = plan_from_model_output("t", raw)
        self.assertEqual(len(plan.steps), 1)

    def test_invalid_agent_is_remapped_by_heuristic(self):
        raw = json.dumps({"steps": [
            {"id": 1, "phase": "ANALYZE", "description": "search for the config loader", "agent": "Nobody"}]})
        plan = plan_from_model_output("t", raw)
        self.assertEqual(plan.steps[0].agent, "SearchAgent")

    def test_unknown_phase_defaults_to_implement(self):
        raw = json.dumps({"steps": [
            {"id": 1, "phase": "WAT", "description": "do", "agent": "FSAgent"}]})
        self.assertEqual(plan_from_model_output("t", raw).steps[0].phase, "IMPLEMENT")

    def test_forward_dependency_dropped(self):
        raw = json.dumps({"steps": [
            {"id": 1, "phase": "IMPLEMENT", "description": "a", "agent": "FSAgent", "depends_on": [2]},
            {"id": 2, "phase": "TEST", "description": "b", "agent": "TestAgent", "depends_on": [1]},
        ]})
        plan = plan_from_model_output("t", raw)
        self.assertEqual(plan.steps[0].depends_on, ())      # forward ref removed
        self.assertEqual(plan.steps[1].depends_on, (1,))

    def test_garbage_falls_back_to_single_step(self):
        plan = plan_from_model_output("scrape a website", "not json at all")
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].agent, "WebAgent")   # heuristic on the task text


class FakePlanOllama:
    def __init__(self, plan_json, tool_responses):
        self.plan_json = plan_json
        self._tool = list(tool_responses)

    def chat_stream(self, model, messages, print_output=True):
        return self.plan_json

    def tool_call(self, model, messages, tools):
        return self._tool.pop(0)


class OrchestratedRunTests(unittest.TestCase):
    def test_end_to_end_single_step(self):
        plan_json = json.dumps({"task": "write file", "steps": [
            {"id": 1, "phase": "IMPLEMENT", "description": "write the file", "agent": "FSAgent"}]})
        fake = FakePlanOllama(plan_json, [{"message": {"content": "file written"}}])
        summary = run_orchestrated(
            "write a file", provider="ollama", model="x", ollama=fake,
            approve=lambda *_: True, verbose=False, parallel=False, printer=lambda *_: None,
        )
        self.assertIn("Completed 1/1", summary)
        self.assertIn("FSAgent", summary)

    def test_build_plan_uses_model(self):
        plan_json = json.dumps({"steps": [
            {"id": 1, "phase": "IMPLEMENT", "description": "do it", "agent": "FSAgent"}]})
        fake = FakePlanOllama(plan_json, [])
        plan = build_plan("do it", provider="ollama", model="x", ollama=fake)
        self.assertEqual(len(plan.steps), 1)


if __name__ == "__main__":
    unittest.main()
