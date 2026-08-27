import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import rev_agent
from core.code_tools.router import DynamicToolRouter


class RevRecToolHarnessTests(unittest.TestCase):
    def setUp(self):
        rev_agent.REVREC_TOOLS.start_task("test", [Path.cwd()])

    def test_revrec_registry_adds_finance_tools_without_altering_code_registry(self):
        names = {tool.name for tool in rev_agent.REVREC_TOOLS.tools}
        self.assertEqual(len(names), 51)
        self.assertTrue({
            "analyze_contract",
            "create_allocation_schedule",
            "read_pdf",
            "write_memo",
            "verification_gate",
        } <= names)
        self.assertEqual(rev_agent.REVREC_TOOLS.get("write_memo").risk, "write")
        self.assertEqual(rev_agent.REVREC_TOOLS.get("write_memo").category, "finance")

    def test_pdf_task_exposes_finance_tools_within_eight_tool_budget(self):
        router = DynamicToolRouter(
            rev_agent.REVREC_TOOLS,
            "analyze this contract.pdf under ASC 606",
            budget=8,
            preferred_names=rev_agent._finance_preferred("analyze this contract.pdf under ASC 606"),
            visibility="dynamic",
        )
        names = {item["function"]["name"] for item in router.schemas("ollama")}
        self.assertEqual(len(names), 8)
        self.assertIn("read_pdf", names)
        self.assertIn("analyze_contract", names)
        self.assertIn("verification_gate", names)
        self.assertIn("request_tool", names)

    def test_finance_write_records_evidence_and_requires_shared_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rev_agent.REVREC_TOOLS.start_task("write an audit memo", [root])
            with patch.object(rev_agent, "OUTPUT_DIR", root):
                result = rev_agent.execute_tool(
                    "write_memo",
                    {"filename": "memo.md", "contract_name": "Acme", "content": "Analysis"},
                )
            before_gate = rev_agent.REVREC_TOOLS.completion_status()
            gate = rev_agent.execute_tool("verification_gate", {})

            self.assertTrue((root / "memo.md").is_file())
            self.assertTrue(result.startswith("OK:"))
            self.assertFalse(before_gate[0])
            self.assertIn("VERIFICATION PASSED", gate)
            self.assertTrue(rev_agent.REVREC_TOOLS.completion_status()[0])

    def test_finance_error_does_not_count_as_mutation_or_evidence(self):
        rev_agent.REVREC_TOOLS.start_task("read a missing pdf", [Path.cwd()])
        result = rev_agent.execute_tool("read_pdf", {"path": "Z:/missing.pdf"})
        self.assertTrue(result.startswith("ERROR:"))
        self.assertFalse(rev_agent.REVREC_TOOLS.state.mutated)
        self.assertFalse(rev_agent.REVREC_TOOLS.state.successful_checks)


if __name__ == "__main__":
    unittest.main()
