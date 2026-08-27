import unittest

from modes.chat import _select_default_chat_model


class ChatModelSelectionTests(unittest.TestCase):
    def test_prefers_configured_chat_model_even_if_embedding_model_is_first(self):
        models = [
            {"name": "nomic-embed-text:latest"},
            {"name": "mistral:latest"},
        ]

        selected = _select_default_chat_model(models, "mistral:latest")

        self.assertEqual(selected, "mistral:latest")

    def test_keeps_configured_model_when_it_is_not_currently_loaded(self):
        models = [
            {"name": "nomic-embed-text:latest"},
            {"name": "qwen3:8b"},
        ]

        selected = _select_default_chat_model(models, "mistral:latest")

        self.assertEqual(selected, "mistral:latest")


if __name__ == "__main__":
    unittest.main()
