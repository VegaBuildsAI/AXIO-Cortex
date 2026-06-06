import unittest

from modes.code import build_code_task


class CodeMemoryIntegrationTests(unittest.TestCase):
    def test_build_code_task_injects_memory_before_task(self):
        result = build_code_task(
            task="Add tests",
            file_context="Loaded files:\nmain.py",
            memory_prefix="[AXIO MEMORY]\nRepo: AXIO Cortex\n[END MEMORY]",
        )

        self.assertTrue(result.startswith("[AXIO MEMORY]"))
        self.assertIn("Loaded files:\nmain.py", result)
        self.assertTrue(result.rstrip().endswith("Add tests"))

    def test_build_code_task_without_memory_keeps_task(self):
        result = build_code_task(task="Run tests", file_context="", memory_prefix="")

        self.assertEqual(result, "Run tests")


if __name__ == "__main__":
    unittest.main()
