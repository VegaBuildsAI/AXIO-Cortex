import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.code_tools import build_default_registry
from core.code_tools.router import (
    DynamicToolRouter,
    LoopGuard,
    TaskType,
    TrajectoryLogger,
    classify_complexity,
    classify_task,
    process_history,
    step_budget,
    truncate_observation,
)


class ToolRouterTests(unittest.TestCase):
    def test_registry_preserves_42_tools_and_enriches_metadata(self):
        registry = build_default_registry()
        self.assertEqual(len(registry.tools), 42)
        self.assertEqual(registry.get("web_search").category, "web")
        self.assertIn("RESEARCH", registry.get("web_search").task_types)

    def test_classifier_and_complexity_budgets_are_deterministic(self):
        self.assertEqual(classify_task("debug this traceback"), TaskType.DEBUGGING)
        self.assertEqual(classify_task("research current official docs"), TaskType.RESEARCH)
        self.assertEqual(classify_task("run the test suite"), TaskType.TESTING)
        self.assertEqual(classify_task("rename and organize these files"), TaskType.FILE_OPS)
        self.assertEqual(classify_task("implement a Python module"), TaskType.CODE_EDIT)
        self.assertEqual(classify_complexity("show status"), "simple")
        # Classification budgets apply when no explicit override is set.
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AXIO_CODE_MAX_STEPS", None)
            self.assertEqual(step_budget("run the full benchmark evaluation"), 100)
            self.assertEqual(step_budget("migrate the architecture end-to-end"), 50)
            self.assertEqual(step_budget("show status"), 10)
        # An explicit AXIO_CODE_MAX_STEPS override wins over classification (capped at 200).
        with mock.patch.dict(os.environ, {"AXIO_CODE_MAX_STEPS": "35"}):
            self.assertEqual(step_budget("show status"), 35)
            self.assertEqual(step_budget("run the full benchmark evaluation"), 35)
        with mock.patch.dict(os.environ, {"AXIO_CODE_MAX_STEPS": "9999"}):
            self.assertEqual(step_budget("x"), 200)

    def test_every_dynamic_subset_is_bounded_and_has_stable_core(self):
        registry = build_default_registry()
        core = {"read_file", "list_dir", "search_files", "verification_gate"}
        for task_type in TaskType:
            subset = registry.get_subset(task_type, budget=7)
            names = {tool.name for tool in subset}
            self.assertLessEqual(len(names), 7)
            self.assertTrue(core <= names)

    def test_code_edit_subset_can_write_and_verify(self):
        # Build tasks must be able to edit, write, and run their compile/self-test
        # commands without spending a step on request_tool.
        registry = build_default_registry()
        router = DynamicToolRouter(
            registry,
            "Read the loaded spec and implement it end to end until SELFTEST OK",
            budget=8,
            visibility="dynamic",
        )
        router.schemas("ollama")
        self.assertEqual(router.task_type, TaskType.CODE_EDIT)
        self.assertTrue({"edit_file", "write_file", "run_command"} <= set(router.exposed_names))
        self.assertEqual(len(router.exposed_names), 8)

    def test_request_tool_is_synthetic_and_grants_hidden_registered_tool(self):
        registry = build_default_registry()
        router = DynamicToolRouter(registry, "research official docs", budget=8, visibility="dynamic")
        first = router.schemas("ollama")
        first_names = {item["function"]["name"] for item in first}
        self.assertEqual(len(first_names), 8)
        self.assertIn("request_tool", first_names)
        self.assertEqual(len(registry.tools), 42)

        hidden = "scaffold_project"
        result = router.handle_unavailable_call(
            "request_tool", {"name": hidden, "reason": "need a reproducible scaffold"}
        )
        second_names = {item["function"]["name"] for item in router.schemas("ollama")}
        self.assertIn("validated", result)
        self.assertIn(hidden, second_names)
        # The set grows by the granted tool; nothing already visible is dropped.
        self.assertEqual(second_names, first_names | {hidden})

    def test_dynamic_set_is_stable_when_observations_change_task_type(self):
        # Re-classification (e.g. a Traceback -> DEBUGGING) must not swap tools:
        # a changed tool block makes Ollama re-read the whole prompt.
        registry = build_default_registry()
        router = DynamicToolRouter(registry, "implement a Python module", budget=8, visibility="dynamic")
        router.schemas("ollama")
        first = router.exposed_names
        router.observe("Traceback (most recent call last): ERROR failed")
        router.schemas("ollama")
        self.assertEqual(router.task_type, TaskType.DEBUGGING)
        self.assertEqual(router.exposed_names, first)

    def test_grants_are_bounded(self):
        from core.code_tools.router import MAX_DYNAMIC_GRANTS

        registry = build_default_registry()
        router = DynamicToolRouter(registry, "implement a Python module", budget=8, visibility="dynamic")
        router.schemas("ollama")
        base = set(router.active_names)
        extra = [tool.name for tool in registry.tools if tool.name not in base]
        for name in extra[: MAX_DYNAMIC_GRANTS + 2]:
            router.handle_unavailable_call("request_tool", {"name": name, "reason": "test"})
        router.schemas("ollama")
        self.assertTrue(base <= set(router.active_names))
        self.assertEqual(len(router.active_names), len(base) + MAX_DYNAMIC_GRANTS)

    def test_hidden_execute_tool_runs_immediately_and_stays_visible(self):
        registry = build_default_registry()
        router = DynamicToolRouter(registry, "implement a Python module", budget=8, visibility="dynamic")
        router.schemas("ollama")
        self.assertNotIn("run_python", router.active_names)
        self.assertIsNone(router.handle_unavailable_call("run_python", {"script_path": "x.py"}))
        router.schemas("ollama")
        self.assertIn("run_python", router.active_names)

    def test_unexposed_registered_call_is_reselected_without_execution(self):
        registry = build_default_registry()
        router = DynamicToolRouter(registry, "research docs", budget=8, visibility="dynamic")
        router.schemas("claude")
        result = router.handle_unavailable_call("delete_file", {"path": "x"})
        self.assertIn("outside the active subset", result)
        names = {item["name"] for item in router.schemas("claude")}
        self.assertIn("delete_file", names)

    def test_full_visibility_exposes_all_42_without_escape_hatch(self):
        registry = build_default_registry()
        router = DynamicToolRouter(registry, "create and verify a project file")
        names = {item["function"]["name"] for item in router.schemas("ollama")}
        self.assertEqual(len(names), 42)
        self.assertEqual(names, {tool.name for tool in registry.tools})
        self.assertNotIn("request_tool", names)
        self.assertEqual(len(router.exposed_names), 42)
        claude_names = {item["name"] for item in router.schemas("claude")}
        self.assertEqual(claude_names, names)
        self.assertIsNone(router.handle_unavailable_call("write_file", {"path": "ignored"}))


class HarnessGuardTests(unittest.TestCase):
    def test_truncation_is_strict_and_preserves_diagnostic_signal(self):
        raw = "A" * 5000 + "\nERROR: important failure\n" + "Z" * 5000
        result = truncate_observation(raw, max_chars=4000)
        self.assertLessEqual(len(result), 4000)
        self.assertIn("observation truncated", result)
        self.assertIn("ERROR: important failure", result)

    def test_history_keeps_only_latest_five_observation_pairs(self):
        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "task"}]
        for index in range(8):
            messages.append({"role": "assistant", "content": "", "tool_calls": [{"id": index}]})
            messages.append({"role": "tool", "content": f"obs-{index}"})
        processed = process_history(messages, "ollama", keep_observations=5)
        self.assertEqual(sum(item.get("role") == "tool" for item in processed), 5)
        self.assertEqual(processed[0]["role"], "system")
        self.assertEqual(processed[1]["content"], "task")

    def test_loop_guard_intervenes_on_repeated_call_and_error(self):
        guard = LoopGuard(repeat_limit=2)
        self.assertEqual(guard.record("read_file", {"path": "x"}, "ERROR: not found"), "")
        self.assertEqual(guard.record("read_file", {"path": "x"}, "ERROR: not found"), "")
        intervention = guard.record("read_file", {"path": "x"}, "ERROR: not found")
        self.assertIn("HARNESS", intervention)
        self.assertIn("Repeated", intervention)

    def test_trajectory_contains_raw_and_truncated_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            logger = TrajectoryLogger("test", root=Path(directory))
            logger.log_step(
                step=1,
                task_type=TaskType.CODE_EDIT,
                active_tools=["read_file"],
                tool_call={"name": "read_file", "arguments": {"path": "x"}},
                observation_raw="raw",
                observation_truncated="raw",
            )
            entry = json.loads(logger.path.read_text(encoding="utf-8"))
        self.assertEqual(entry["observation_raw"], "raw")
        self.assertEqual(entry["observation_truncated"], "raw")
        self.assertEqual(entry["task_type"], "CODE_EDIT")


if __name__ == "__main__":
    unittest.main()
