import unittest

from modes.cowork import build_cowork_prompt


class CoworkMemoryIntegrationTests(unittest.TestCase):
    def test_build_cowork_prompt_orders_memory_context_and_user_prompt(self):
        result = build_cowork_prompt(
            user_prompt="Update the Docker docs",
            workspace_context="--- WORKSPACE CONTEXT ---\nfile contents\n--- END WORKSPACE CONTEXT ---",
            memory_prefix="[AXIO MEMORY]\nProject: AXIO Cortex\n[END MEMORY]",
        )

        self.assertTrue(result.startswith("[AXIO MEMORY]"))
        self.assertIn("--- WORKSPACE CONTEXT ---", result)
        self.assertTrue(result.rstrip().endswith("User: Update the Docker docs"))

    def test_build_cowork_prompt_without_memory_keeps_existing_shape(self):
        result = build_cowork_prompt(
            user_prompt="List risks",
            workspace_context="",
            memory_prefix="",
        )

        self.assertEqual(result, "List risks")


if __name__ == "__main__":
    unittest.main()
