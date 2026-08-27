import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import modes.code as code_mode
from core.coding_skills import (
    build_code_plan_prompt,
    build_coding_system_prompt,
    discover_coding_skills,
    inspect_python_environment,
    load_tool_calling_skills,
    render_tool_calling_skills,
    select_coding_skills,
)
from core.code_tools import CODE_TOOL_REGISTRY


class CodingSkillRegistryTests(unittest.TestCase):
    def test_axio_skill_is_discovered_and_auto_applied(self):
        skills = discover_coding_skills()

        self.assertEqual([skill.name for skill in skills], ["axio-coding"])
        self.assertIn("axio-coding", [skill.name for skill in select_coding_skills("fix this")])

    def test_system_prompt_loads_maintained_prompt_and_skill(self):
        prompt_text = build_coding_system_prompt("debug a FastAPI service")

        self.assertIn("# AXIO Code Agent", prompt_text)
        self.assertIn("# Active AXIO Skills", prompt_text)
        self.assertIn("Non-negotiable AXIO invariants", prompt_text)
        self.assertNotIn("{{SKILL_ROOT}}", prompt_text)

    def test_every_registered_tool_has_one_model_visible_calling_skill(self):
        catalog = load_tool_calling_skills()
        registered = {tool.name for tool in CODE_TOOL_REGISTRY.tools}

        self.assertEqual(len(registered), 42)
        self.assertEqual(set(catalog), registered)
        self.assertTrue(all(skill.when and skill.rules and skill.after for skill in catalog.values()))

        rendered = render_tool_calling_skills()
        prompt = build_coding_system_prompt("create and verify a file")
        self.assertIn("Tool-Calling Skills (42/42)", rendered)
        self.assertIn("All registered tools are visible", prompt)
        self.assertIn("`read_file`", prompt)
        self.assertIn("`verification_gate`", prompt)
        self.assertIn("`scaffold_module`", prompt)
        self.assertNotIn("CATALOG ERROR", prompt)
        self.assertLessEqual(len(prompt), 24000)

    def test_triggered_skill_selection_supports_future_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill_dir = root / "database-review"
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: database-review\ndescription: Database checks.\n"
                "metadata:\n  triggers: [postgres]\n---\n\nCheck transactions.\n",
                encoding="utf-8",
            )

            self.assertEqual(select_coding_skills("edit CSS", root), [])
            selected = select_coding_skills("review Postgres transactions", root)
            self.assertEqual([skill.name for skill in selected], ["database-review"])

    def test_plan_prompt_uses_live_tool_inventory_and_verification_gate(self):
        prompt = build_code_plan_prompt(["read_file", "run_python", "verification_gate"])

        self.assertIn("read_file, run_python, verification_gate", prompt)
        self.assertIn("[verification_gate]", prompt)
        self.assertNotIn("verify_file", prompt)

    def test_gemma_compatibility_mode_reuses_canonical_tools(self):
        import modes.gemma_code as gemma_mode

        self.assertIs(gemma_mode.TOOLS, code_mode.TOOLS)
        self.assertEqual(len(gemma_mode.TOOLS), 42)

    def test_plan_parser_is_bounded_and_normalizes_numbering(self):
        raw = "\n".join(f"{index}) [read_file] Step {index}" for index in range(1, 20))

        steps = code_mode.parse_plan_steps(raw)

        self.assertEqual(len(steps), 15)
        self.assertEqual(steps[0], "1. [read_file] Step 1")
        self.assertEqual(steps[-1], "15. [read_file] Step 15")


class PythonExecutionToolTests(unittest.TestCase):
    def test_environment_inventory_reports_interpreter_and_packages(self):
        report = inspect_python_environment(Path.cwd())

        self.assertIn("Python executable:", report)
        self.assertIn("Installed distributions (", report)
        self.assertIn("PyYAML==", report)

    def test_run_python_passes_arguments_without_shell_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "echo_args.py"
            script.write_text(
                "import json, sys\nprint(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            with patch("builtins.input", return_value="y"):
                result = code_mode.tool_run_python(
                    str(script),
                    args=["$(Write-Output injected)", "value with spaces"],
                    working_dir=str(root),
                )

        self.assertIn("EXIT CODE: 0", result)
        self.assertIn("$(Write-Output injected)", result)
        self.assertIn("value with spaces", result)

    def test_python_tools_are_exposed_to_both_model_backends(self):
        ollama_names = {tool["function"]["name"] for tool in code_mode.TOOLS}
        claude_names = {tool["name"] for tool in code_mode.TOOLS_CLAUDE}

        self.assertIn("inspect_python_environment", ollama_names)
        self.assertIn("run_python", ollama_names)
        self.assertIn("inspect_node_environment", ollama_names)
        self.assertIn("run_npm_script", ollama_names)
        self.assertIn("git_status", ollama_names)
        self.assertIn("git_diff", ollama_names)
        self.assertIn("apply_patch", ollama_names)
        self.assertIn("verification_gate", ollama_names)
        self.assertEqual(ollama_names, claude_names)


if __name__ == "__main__":
    unittest.main()
