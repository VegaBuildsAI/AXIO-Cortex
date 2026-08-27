import unittest

from scripts.benchmark_tool_router import TASKS, score_selection, summarize_rows


class ToolRouterBenchmarkTests(unittest.TestCase):
    def test_dataset_has_three_cases_per_task_type(self):
        counts = {}
        for task in TASKS:
            counts[task.task_type.value] = counts.get(task.task_type.value, 0) + 1
        self.assertEqual(set(counts.values()), {3})
        self.assertEqual(len(TASKS), 18)

    def test_request_tool_requires_the_correct_target(self):
        task = next(item for item in TASKS if item.request_target == "apply_patch")
        valid = {"request_tool"}
        wrong = score_selection(
            task,
            "router",
            [{"name": "request_tool", "arguments": {"name": "delete_file"}}],
            valid,
        )
        correct = score_selection(
            task,
            "router",
            [{"name": "request_tool", "arguments": {"name": "apply_patch"}}],
            valid,
        )
        self.assertFalse(wrong["correct"])
        self.assertTrue(correct["correct"])

    def test_summary_computes_prompt_reduction_and_accuracy_delta(self):
        rows = [
            {"arm": "baseline", "task_type": "CODE_EDIT", "correct": False,
             "valid_tool": True, "tool_call_count": 1, "visible_tool_count": 38,
             "prompt_eval_count": 1000, "elapsed_seconds": 10.0},
            {"arm": "router", "task_type": "CODE_EDIT", "correct": True,
             "valid_tool": True, "tool_call_count": 1, "visible_tool_count": 8,
             "prompt_eval_count": 500, "elapsed_seconds": 8.0},
        ]
        summary = summarize_rows(rows)
        self.assertEqual(summary["deltas"]["accuracy_percentage_points"], 100.0)
        self.assertEqual(summary["deltas"]["prompt_token_reduction_percent"], 50.0)
        self.assertTrue(summary["recommended_pilot_pass"])


if __name__ == "__main__":
    unittest.main()
