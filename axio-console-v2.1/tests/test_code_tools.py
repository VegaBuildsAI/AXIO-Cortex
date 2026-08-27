import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.code_tools import build_default_registry
from core.code_tools.document_tools import read_docx
from core.code_tools.filesystem import apply_patch
from core.code_tools.git_tools import git_diff, git_status
from core.code_tools.node_tools import inspect_node_environment
from core.code_tools.verification import extract_verification_requirements


class CodeToolRegistryTests(unittest.TestCase):
    def test_registry_generates_matching_backend_schemas(self):
        registry = build_default_registry()
        ollama = {item["function"]["name"] for item in registry.ollama_schemas()}
        claude = {item["name"] for item in registry.claude_schemas()}

        self.assertEqual(ollama, claude)
        self.assertTrue({"apply_patch", "run_npm_script", "git_diff", "verification_gate"} <= ollama)
        self.assertEqual(registry.get("delete_file").risk, "destructive")
        self.assertEqual(registry.get("git_status").risk, "read")

    def test_execute_policy_approves_execution_and_audits_decline(self):
        registry = build_default_registry()
        audited = []
        result = registry.execute(
            "run_command",
            {"command": "Write-Output should-not-run"},
            approve=lambda tool, args: False,
            audit=lambda tool, args, output: audited.append((tool.name, output)),
        )

        self.assertTrue(result.startswith("CANCELLED:"))
        self.assertEqual(audited, [("run_command", "CANCELLED: User declined.")])
        self.assertFalse(registry.records[-1].ok)

    def test_write_outside_active_workspace_requires_approval(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            registry.start_task("write", [workspace])
            outside = root / "outside.txt"
            result = registry.execute(
                "write_file",
                {"path": str(outside), "content": "blocked"},
                approve=lambda tool, args: False,
            )

        self.assertTrue(result.startswith("CANCELLED:"))
        self.assertFalse(outside.exists())


class AtomicPatchTests(unittest.TestCase):
    def test_apply_patch_validates_every_edit_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("alpha", encoding="utf-8")
            second.write_text("beta", encoding="utf-8")

            result = apply_patch([
                {"path": str(first), "old_text": "alpha", "new_text": "changed"},
                {"path": str(second), "old_text": "missing", "new_text": "changed"},
            ])

            self.assertFalse(result.ok)
            self.assertEqual(first.read_text(encoding="utf-8"), "alpha")
            self.assertEqual(second.read_text(encoding="utf-8"), "beta")

    def test_apply_patch_supports_multiple_valid_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.txt"
            second = root / "second.txt"
            first.write_text("alpha", encoding="utf-8")
            second.write_text("beta", encoding="utf-8")

            result = apply_patch([
                {"path": str(first), "old_text": "alpha", "new_text": "one"},
                {"path": str(second), "old_text": "beta", "new_text": "two"},
            ])

            self.assertTrue(result.ok)
            self.assertEqual(first.read_text(encoding="utf-8"), "one")
            self.assertEqual(second.read_text(encoding="utf-8"), "two")


class RuntimeAndVerificationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("git"), "Git unavailable")
    def test_git_tools_report_status_and_diff_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run([shutil.which("git"), "init", str(root)], check=True, capture_output=True)
            target = root / "tracked.txt"
            target.write_text("before\n", encoding="utf-8")
            subprocess.run([shutil.which("git"), "-C", str(root), "add", "tracked.txt"], check=True, capture_output=True)
            target.write_text("after\n", encoding="utf-8")

            status = git_status(str(root))
            diff = git_diff(str(root))

        self.assertTrue(status.ok)
        self.assertIn("tracked.txt", status.content)
        self.assertTrue(diff.ok)
        self.assertIn("-before", diff.content)
        self.assertIn("+after", diff.content)

    def test_node_inventory_reports_package_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"scripts": {"test": "node -e \"console.log('ok')\""}}),
                encoding="utf-8",
            )
            report = inspect_node_environment(str(root))

        self.assertIn("Node executable:", report)
        self.assertIn("npm scripts: test", report)

    @unittest.skipUnless(shutil.which("node") and (shutil.which("npm.cmd") or shutil.which("npm")), "Node/npm unavailable")
    def test_npm_success_becomes_verification_evidence(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry.start_task("create the file and run npm.cmd test", [root])
            target = root / "out.js"
            (root / "package.json").write_text(
                json.dumps({"scripts": {"test": "node -e \"console.log('ok')\""}}),
                encoding="utf-8",
            )
            registry.execute("write_file", {"path": str(target), "content": "// ok\n"})
            output = registry.execute(
                "run_npm_script",
                {"working_dir": str(root), "script": "test"},
                approve=lambda tool, args: True,
            )
            gate = registry.execute("verification_gate", {"required_checks": ["npm:test"]})

        self.assertIn("EXIT CODE: 0", output)
        self.assertTrue(gate.startswith("VERIFICATION PASSED:"))
        self.assertTrue(registry.completion_status()[0])

    def test_gate_blocks_mutation_without_runtime_evidence(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry.start_task("change a file", [root])
            target = root / "out.txt"
            registry.execute("write_file", {"path": str(target), "content": "x"})
            gate = registry.execute("verification_gate", {})

        self.assertTrue(gate.startswith("VERIFICATION BLOCKED:"))
        self.assertFalse(registry.completion_status()[0])

    def test_requirement_parser_ignores_install_but_tracks_checks(self):
        checks = extract_verification_requirements(
            "npm.cmd install, npm --version, then npm.cmd run verify:engine and npm test"
        )
        self.assertEqual(checks, ("npm:test", "npm:verify:engine"))

    def test_read_docx_extracts_paragraph_text_without_dependency(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>Hello AXIO</w:t></w:r></w:p></w:body></w:document>'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", xml)
            result = read_docx(str(path))

        self.assertTrue(result.ok)
        self.assertEqual(result.content, "Hello AXIO")


if __name__ == "__main__":
    unittest.main()
