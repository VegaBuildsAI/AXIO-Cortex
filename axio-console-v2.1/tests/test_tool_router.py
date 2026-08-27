import json
import tempfile
import unittest
from pathlib import Path

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
        self.assertEqual(step_budget("run the full benchmark evaluation"), 100)
        self.assertEqual(step_budget("migrate the architecture end-to-end"), 50)

    def test_every_dynamic_subset_is_bounded_and_has_stable_core(self):
        registry = build_default_registry()
        core = {"read_file", "list_dir", "search_files", "verification_gate"}
        for task_type in TaskType:
            subset = registry.get_subset(task_type, budget=7)
            names = {tool.name for tool in subset}
            self.assertLessEqual(len(names), 7)
            self.assertTrue(core <= names)

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
        self.assertLessEqual(len(second_names), 8)

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
