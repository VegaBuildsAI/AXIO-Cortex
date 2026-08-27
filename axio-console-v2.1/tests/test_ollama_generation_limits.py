import unittest
from unittest.mock import patch

import requests

from core.config import OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT
from core.models import OllamaClient


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "done": True,
            "done_reason": "stop",
            "message": {"content": "ok", "tool_calls": []},
            "prompt_eval_count": 10,
            "eval_count": 20,
        }


class FakeServerErrorResponse:
    status_code = 500
    text = "model runner failed"

    def raise_for_status(self):
        raise requests.exceptions.HTTPError("500", response=self)


class OllamaGenerationLimitTests(unittest.TestCase):
    def test_tool_call_sends_configured_context_and_output_budgets(self):
        client = OllamaClient("http://127.0.0.1:11434")
        with (
            patch.object(client, "_supports_thinking", return_value=False),
            patch("core.models.requests.post", return_value=FakeResponse()) as request,
        ):
            data = client.tool_call("model", [{"role": "user", "content": "hello"}], [])

        payload = request.call_args.kwargs["json"]
        self.assertEqual(payload["options"]["num_ctx"], OLLAMA_NUM_CTX)
        self.assertEqual(payload["options"]["num_predict"], OLLAMA_NUM_PREDICT)
        self.assertEqual(client.last_done_reason, "stop")
        self.assertEqual(client.last_usage, {"input": 10, "output": 20})
        self.assertEqual(data["message"]["content"], "ok")

    def test_tool_call_retries_http_500_and_reports_server_body(self):
        client = OllamaClient("http://127.0.0.1:11434")
        with (
            patch.object(client, "_supports_thinking", return_value=False),
            patch("core.models.requests.post", return_value=FakeServerErrorResponse()) as request,
            patch("core.models.time.sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "model runner failed"):
                client.tool_call("model", [{"role": "user", "content": "hello"}], [])

        self.assertEqual(request.call_count, 3)


if __name__ == "__main__":
    unittest.main()
