import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["AXIO_UI_DATA_DIR"] = tempfile.mkdtemp(prefix="axio-ui-api-")

from fastapi.testclient import TestClient

from web_api.main import app


class LocalApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_reports_config_and_local_model(self):
        from core.config import LOCAL_ONLY

        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        # local_only reflects the config flag (hybrid = False, local-only = True).
        self.assertEqual(body["local_only"], LOCAL_ONLY)
        self.assertEqual(body["bind_host"], "127.0.0.1")
        self.assertEqual(body["ollama"]["model"], "gemma4:12b")

    @patch("web_api.main.LOCAL_ONLY", False)
    @patch("web_api.main.CLAUDE_API_KEY", "")
    def test_code_fails_closed_without_claude_key_in_cloud_mode(self):
        # When LOCAL_ONLY is off and no Claude key is present, Code mode must
        # fail closed rather than silently doing nothing.
        conversation = self.client.post(
            "/api/conversations",
            json={"mode": "code", "title": "Code test"},
        ).json()

        response = self.client.post(
            f"/api/conversations/{conversation['id']}/messages",
            json={"content": "change a file"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("No local fallback", response.json()["detail"])

    def test_workspace_api_does_not_expose_protected_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "visible.py").write_text("print('ok')", encoding="utf-8")
            (root / ".env").write_text("SECRET=value", encoding="utf-8")
            workspace = self.client.post(
                "/api/workspaces/open",
                json={"path": temp},
            ).json()

            response = self.client.get(f"/api/workspaces/{workspace['id']}/files")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                [item["relative_path"] for item in response.json()],
                ["visible.py"],
            )


if __name__ == "__main__":
    unittest.main()
