import json
import unittest
from unittest.mock import patch

from core.code_tools import CODE_TOOL_REGISTRY, build_default_registry
from core.code_tools import brain_tools
from core.code_tools.profiles import profile_tool_names


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    """Records every SQL call; `responder(sql, params)` returns the rows."""

    def __init__(self, responder=None):
        self.calls = []
        self.responder = responder or (lambda sql, params: [])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor(self.responder(sql, params))


def _chunk(path, index, title, body, part=0, source="second_brain"):
    return {
        "id": f"{path}-{index}",
        "mode": "console",
        "source_type": source,
        "content": f"[Second Brain] {path} — {title}:\n{body}",
        "metadata": {"path": path, "title": title, "chunk_index": index,
                     "section_part": part, "note_mtime": 1.5},
        "created_at": "2026-11-12",
    }


class BrainToolRegistryTests(unittest.TestCase):
    def test_brain_tools_are_registered_read_only(self):
        for name in ("brain_search", "brain_read", "brain_list"):
            tool = CODE_TOOL_REGISTRY.get(name)
            self.assertIsNotNone(tool, name)
            self.assertEqual(tool.risk, "read")
            self.assertEqual(tool.category, "brain")

    def test_chat_and_cowork_profiles_include_brain_tools(self):
        for mode in ("chat", "cowork", "code"):
            names = profile_tool_names(mode)
            self.assertTrue({"brain_search", "brain_read", "brain_list"} <= set(names), mode)

    def test_registry_can_omit_brain_tools_for_isolated_modes(self):
        names = {tool.name for tool in build_default_registry(include_brain=False).tools}
        self.assertFalse({"brain_search", "brain_read", "brain_list"} & names)


class BrainSearchTests(unittest.TestCase):
    def _assert_never_revrec(self, conn):
        for sql, params in conn.calls:
            flat = json.dumps(params, default=str)
            self.assertNotIn("revrec", flat)
            if "memory_embeddings" in sql:
                self.assertIn("mode = ANY(%s)", sql)

    def test_vector_and_keyword_search_query_postgres_only(self):
        def responder(sql, params):
            if "set_config" in sql:
                return [{"set_config": "100"}]
            if "<=>" in sql:
                row = _chunk("01-Projects/minios.md", 0, "(intro)", "MiniOS is a tiny OS")
                return [{**row, "distance": 0.2}]
            if "ILIKE ANY" in sql:
                row = _chunk("01-Projects/minios.md", 0, "(intro)", "MiniOS is a tiny OS")
                return [{**row, "hits": 1}]
            return []

        conn = FakeConn(responder)
        with patch.object(brain_tools, "_connect", lambda: conn), \
                patch.object(brain_tools, "_embed_query", return_value=[0.0] * 768), \
                patch("pathlib.Path.read_text", side_effect=AssertionError("vault read")):
            result = brain_tools.brain_search("minios kernel")

        self.assertTrue(result.ok, result.content)
        payload = json.loads(result.content)
        self.assertEqual(payload["mode"], "exact vector + keyword")
        self.assertEqual(payload["results"][0]["path"], "01-Projects/minios.md")
        self.assertNotIn("[Second Brain]", payload["results"][0]["content"])
        self.assertIn("set_config('ivfflat.probes'", conn.calls[0][0])
        self._assert_never_revrec(conn)

    def test_keyword_only_when_ollama_is_down(self):
        def responder(sql, params):
            if "ILIKE ANY" in sql:
                row = _chunk("02-People/ana.md", 0, "Role", "Ana leads design")
                return [{**row, "hits": 2}]
            return []

        conn = FakeConn(responder)
        with patch.object(brain_tools, "_connect", lambda: conn), \
                patch.object(brain_tools, "_embed_query", return_value=None):
            result = brain_tools.brain_search("Ana design")

        self.assertTrue(result.ok, result.content)
        payload = json.loads(result.content)
        self.assertTrue(payload["mode"].startswith("keyword-only"))
        self.assertEqual(payload["results"][0]["path"], "02-People/ana.md")
        self.assertFalse(any("<=>" in sql for sql, _ in conn.calls))
        self._assert_never_revrec(conn)

    def test_source_filter_is_validated_and_applied(self):
        conn = FakeConn()
        with patch.object(brain_tools, "_connect", lambda: conn), \
                patch.object(brain_tools, "_embed_query", return_value=None):
            bad = brain_tools.brain_search("x y z", source="x'; drop table")
            good = brain_tools.brain_search("lessons learned", source="self_learned")
        self.assertFalse(bad.ok)
        self.assertTrue(good.ok)
        self.assertTrue(any("source_type = %s" in sql and "self_learned" in params
                            for sql, params in conn.calls))

    def test_postgres_down_returns_clear_error(self):
        def boom():
            raise ConnectionError("connection refused")

        with patch.object(brain_tools, "_connect", boom), \
                patch.object(brain_tools, "_embed_query", return_value=None):
            result = brain_tools.brain_search("anything")
        self.assertFalse(result.ok)
        self.assertIn("Cortex Postgres unavailable", result.content)


class BrainReadTests(unittest.TestCase):
    def test_rebuilds_note_in_chunk_order_and_rejoins_split_sections(self):
        rows = [
            _chunk("01-Projects/minios.md", 0, "(intro)", "# MiniOS\nA tiny OS."),
            _chunk("01-Projects/minios.md", 1, "Kernel", "First half of a long sec"),
            _chunk("01-Projects/minios.md", 2, "Kernel", "tion continues here.", part=1),
            _chunk("01-Projects/minios.md", 3, "Status", "Active."),
        ]
        conn = FakeConn(lambda sql, params: rows if "metadata->>'path' = %s" in sql else [])
        with patch.object(brain_tools, "_connect", lambda: conn):
            result = brain_tools.brain_read("01-Projects/minios.md")

        self.assertTrue(result.ok, result.content)
        text = result.content
        self.assertIn("# MiniOS\nA tiny OS.", text)
        self.assertIn("## Kernel\nFirst half of a long section continues here.", text)
        self.assertLess(text.index("## Kernel"), text.index("## Status"))
        sql = conn.calls[0][0]
        self.assertIn("chunk_index", sql)
        self.assertIn("ORDER BY", sql)
        self.assertNotIn("revrec", json.dumps(conn.calls[0][1]))

    def test_unique_partial_path_resolves(self):
        rows = [_chunk("01-Projects/minios.md", 0, "minios", "Body")]

        def responder(sql, params):
            if "DISTINCT" in sql:
                return [{"path": "01-Projects/minios.md"}]
            if params and params[-1] == "01-Projects/minios.md":
                return rows
            return []

        conn = FakeConn(responder)
        with patch.object(brain_tools, "_connect", lambda: conn):
            result = brain_tools.brain_read("minios.md")
        self.assertTrue(result.ok, result.content)
        self.assertIn("# 01-Projects/minios.md", result.content)

    def test_missing_note_is_an_error(self):
        conn = FakeConn()
        with patch.object(brain_tools, "_connect", lambda: conn):
            result = brain_tools.brain_read("nope.md")
        self.assertFalse(result.ok)
        self.assertIn("brain_list", result.content)


class BrainListTests(unittest.TestCase):
    def test_lists_notes_headings_and_source_counts(self):
        def responder(sql, params):
            if "array_agg" in sql:
                return [{"path": "01-Projects/minios.md", "chunks": 3,
                         "titles": ["(intro)", "Kernel", "Kernel", "Status"]}]
            if "GROUP BY 1, 2" in sql:
                return [{"mode": "console", "source_type": "second_brain", "count": 3},
                        {"mode": "console", "source_type": "self_learned", "count": 38}]
            return []

        conn = FakeConn(responder)
        with patch.object(brain_tools, "_connect", lambda: conn):
            result = brain_tools.brain_list("01-Projects/")
        self.assertTrue(result.ok, result.content)
        payload = json.loads(result.content)
        self.assertEqual(payload["items"][0]["headings"], ["Kernel", "Status"])
        self.assertEqual(payload["source_counts"][1]["count"], 38)
        self.assertEqual(conn.calls[0][1][-1], "01-Projects/%")
        for _sql, params in conn.calls:
            self.assertNotIn("revrec", json.dumps(params))


if __name__ == "__main__":
    unittest.main()
