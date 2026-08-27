import json
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from core.code_tools import build_default_registry
from core.code_tools import retrieval_tools as retrieval
from core.code_tools import web_tools as web
from core.code_tools.network_policy import UnsafeUrlError, validate_public_url
from core.code_tools.scaffold_tools import scaffold_module, scaffold_project


class FakeHttpResponse:
    def __init__(self, body: str, *, status: int = 200, content_type: str = "text/html; charset=utf-8"):
        self._body = body.encode("utf-8")
        self.status_code = status
        self.headers = {"content-type": content_type}
        self.encoding = "utf-8"

    def iter_content(self, chunk_size=65536):
        yield self._body

    def close(self):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return json.loads(self._body.decode("utf-8"))


class RegistryAndNetworkPolicyTests(unittest.TestCase):
    def test_registry_exposes_exact_curated_42_to_both_backends(self):
        registry = build_default_registry()
        ollama = [item["function"]["name"] for item in registry.ollama_schemas()]
        claude = [item["name"] for item in registry.claude_schemas()]
        new_tools = {
            "web_search", "web_fetch", "web_extract", "browser_open", "browser_snapshot",
            "browser_click", "index_workspace", "semantic_search", "search_docs",
            "scaffold_project", "scaffold_module",
        }
        github_tools = {
            "github_status", "github_pr_list", "github_pr_view", "git_branch", "git_commit",
            "github_push", "github_fork", "github_pr_create", "github_pr_merge",
        }

        self.assertEqual(len(ollama), 42)
        self.assertEqual(ollama, claude)
        self.assertTrue(new_tools <= set(ollama))
        self.assertTrue(github_tools <= set(ollama))
        self.assertTrue({"create_docx", "create_xlsx", "create_pptx", "create_pdf"} <= set(ollama))
        self.assertEqual(registry.get("index_workspace").risk, "index")
        self.assertEqual(registry.get("browser_click").risk, "execute")
        self.assertEqual(registry.get("github_push").risk, "external")

    def test_network_policy_blocks_local_private_file_and_url_credentials(self):
        for url in (
            "http://127.0.0.1/admin",
            "http://10.0.0.2/",
            "file:///C:/Windows/win.ini",
            "https://user:secret@example.com/",
        ):
            with self.subTest(url=url), self.assertRaises(UnsafeUrlError):
                validate_public_url(url)

    def test_network_policy_allows_resolved_public_https(self):
        with patch("core.code_tools.network_policy.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            self.assertEqual(validate_public_url("https://example.com/docs"), "https://example.com/docs")

    def test_browser_click_keeps_execute_approval_gate(self):
        registry = build_default_registry()
        result = registry.execute("browser_click", {"ref": "axio-1"}, approve=lambda tool, args: False)
        self.assertTrue(result.startswith("CANCELLED:"))


class WebToolsTests(unittest.TestCase):
    def test_fetch_caches_and_extract_removes_script_and_navigation(self):
        html = "<html><head><title>AXIO Docs</title><script>secret()</script></head><body><nav>menu</nav><main><h1>Verification</h1><p>Gate content.</p></main></body></html>"
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "web.db"
            with (
                patch.object(web, "AXIO_WEB_CACHE_DB", db),
                patch.object(web, "validate_public_url", side_effect=lambda value: value),
                patch.object(web.requests, "get", return_value=FakeHttpResponse(html)),
            ):
                fetched = web.web_fetch("https://example.com/docs")
                cache_id = json.loads(fetched.content)["cache_id"]
                extracted = web.web_extract(cache_id)

        self.assertTrue(fetched.ok)
        self.assertTrue(extracted.ok)
        body = json.loads(extracted.content)
        self.assertIn("Verification", body["content"])
        self.assertNotIn("secret()", body["content"])
        self.assertNotIn("menu", body["content"])

    def test_web_search_returns_bounded_structured_searxng_results(self):
        payload = {"results": [{"title": "Docs", "url": "https://example.com/docs", "content": "Official docs", "score": 1.0}]}
        fake = FakeHttpResponse(json.dumps(payload), content_type="application/json")
        with patch.object(web.requests, "get", return_value=fake):
            result = web.web_search("test query", max_results=1)

        self.assertTrue(result.ok)
        self.assertEqual(json.loads(result.content)["results"][0]["source"], "searxng")


class RetrievalToolsTests(unittest.TestCase):
    @staticmethod
    def fake_embed(texts):
        vectors = []
        for text in texts:
            lowered = text.casefold()
            vectors.append([1.0, 0.0] if "verification" in lowered or "gate" in lowered else [0.0, 1.0])
        return vectors

    def test_workspace_index_and_hybrid_search_return_relevant_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            (root / "gate.py").write_text("def verification_gate():\n    return 'verified'\n", encoding="utf-8")
            (root / "other.py").write_text("def unrelated():\n    return 'other'\n", encoding="utf-8")
            db = Path(directory) / "workspace.db"
            with patch.object(retrieval, "AXIO_WORKSPACE_INDEX_DB", db), patch.object(retrieval, "_embed", side_effect=self.fake_embed):
                indexed = retrieval.index_workspace(str(root))
                result = retrieval.semantic_search("verification gate", str(root), top_k=1)

        self.assertTrue(indexed.ok)
        self.assertTrue(result.ok)
        top = json.loads(result.content)["results"][0]
        self.assertTrue(top["path"].endswith("gate.py"))
        self.assertEqual(top["start_line"], 1)

    def test_search_docs_uses_official_local_cache_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "docs.db"
            with patch.object(retrieval, "AXIO_DOCS_INDEX_DB", db):
                with closing(retrieval._docs_connection()) as conn:
                    cursor = conn.execute(
                        "INSERT INTO documents(library,title,url,content,updated_at) VALUES(?,?,?,?,?)",
                        ("fastapi", "Lifespan", "https://fastapi.tiangolo.com/advanced/events/", "FastAPI lifespan context manager", 1.0),
                    )
                    conn.execute(
                        "INSERT INTO docs_fts(rowid,title,content,url,library) VALUES(?,?,?,?,?)",
                        (cursor.lastrowid, "Lifespan", "FastAPI lifespan context manager", "https://fastapi.tiangolo.com/advanced/events/", "fastapi"),
                    )
                    conn.commit()
                with patch.object(retrieval, "_search_web_data", side_effect=AssertionError("network should not run")):
                    result = retrieval.search_docs("FastAPI lifespan", library="fastapi", max_results=1)

        self.assertTrue(result.ok)
        self.assertIn("fastapi.tiangolo.com", result.content)


class ScaffoldToolsTests(unittest.TestCase):
    def test_registry_allows_in_workspace_scaffold_but_requires_verification_afterward(self):
        registry = build_default_registry()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "service"
            registry.start_task("scaffold and test a service", [root])
            result = registry.execute(
                "scaffold_project",
                {"template": "python-cli", "name": "service", "destination": str(target)},
            )

            self.assertFalse(result.startswith("CANCELLED:"))
            self.assertTrue(target.is_dir())
            self.assertTrue(registry.state.mutated)
            self.assertFalse(registry.completion_status()[0])

    def test_project_scaffold_is_atomic_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "revenue-engine"
            result = scaffold_project("fastapi-service", "revenue-engine", str(target), {"docker": True})
            second = scaffold_project("fastapi-service", "revenue-engine", str(target))

            self.assertTrue(result.ok)
            self.assertTrue((target / "app" / "main.py").is_file())
            self.assertTrue((target / "Dockerfile").is_file())
            self.assertFalse(second.ok)

    def test_module_scaffold_uses_one_expected_directory_level(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory) / "app"
            parent.mkdir()
            result = scaffold_module("fastapi-domain", "customer", str(parent))
            target = parent / "customer"

            self.assertTrue(result.ok)
            self.assertTrue((target / "schema.py").is_file())
            self.assertFalse((target / "customer" / "schema.py").exists())
            self.assertIn("class CustomerPayload", (target / "schema.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
