import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.self_memory import (
    DEFAULT_CONFIG,
    SelfMemoryEngine,
    SingleInstanceLock,
    _cosine,
    resource_gate_reasons,
)


def config(**patch):
    value = json.loads(json.dumps(DEFAULT_CONFIG))
    value.update(patch)
    return value


def row(row_id, content, vector, metadata):
    return {
        "id": row_id,
        "content": content,
        "embedding": vector,
        "metadata": dict(metadata),
        "created_at": metadata.get("first_seen", "2026-01-01T00:00:00+00:00"),
    }


class FakeBackend:
    def __init__(self, rows=None, messages=None):
        self.rows = list(rows or [])
        self.messages = list(messages or [])

    def find_similar(self, embedding, source_type, threshold=0.0):
        candidates = [
            item for item in self.rows
            if item["metadata"].get("source_type", "self_learned") == source_type
        ]
        if not candidates:
            return None
        best = max(candidates, key=lambda item: _cosine(embedding, item["embedding"]))
        result = dict(best)
        result["similarity"] = _cosine(embedding, best["embedding"])
        return result if result["similarity"] >= threshold else None

    def list_chunks(self, source_type, limit=1000):
        return [
            item for item in self.rows
            if item["metadata"].get("source_type", "self_learned") == source_type
        ][:limit]

    def count_chunks(self, source_type):
        return len(self.list_chunks(source_type))

    def recent_messages(self, since_iso=None, limit=500):
        if not since_iso:
            return self.messages[:limit]
        return [
            item for item in self.messages
            if str(item.get("created_at", "")) > str(since_iso)
        ][:limit]

    def get_facts(self):
        return {"learned_principles": [], "global_preferences": {}}


class FakeManager:
    def __init__(self, rows=None, vector=None, messages=None):
        self._postgres_backend = FakeBackend(rows, messages=messages)
        self.vector = vector or [1.0, 0.0]
        self.facts = {"learned_principles": [], "global_preferences": {}}
        self.stored = []
        self.updated = []
        self.deleted = []

    def embed_text(self, text):
        return list(self.vector)

    def get_facts(self):
        return json.loads(json.dumps(self.facts))

    def update_facts(self, patch):
        for key, value in patch.items():
            self.facts[key] = value

    def update_chunk_metadata(self, chunk_id, metadata):
        self.updated.append((chunk_id, dict(metadata)))
        for item in self._postgres_backend.rows:
            if str(item["id"]) == str(chunk_id):
                item["metadata"] = dict(metadata)

    def store_chunk(
        self, text, metadata=None, embedding=None, chunk_id=None,
        require_primary=False,
    ):
        item = row(chunk_id, text, embedding or self.vector, metadata or {})
        self._postgres_backend.rows.append(item)
        self.stored.append(item)
        return chunk_id

    def delete_chunks(self, source_type, key, value):
        self.deleted.append((source_type, key, value))
        self._postgres_backend.rows[:] = [
            item for item in self._postgres_backend.rows
            if not (
                item["metadata"].get("source_type", "self_learned") == source_type
                and str(item["metadata"].get(key)) == str(value)
            )
        ]


class SelfMemoryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 24, tzinfo=timezone.utc)

    def engine(self, manager, **cfg):
        return SelfMemoryEngine(
            manager,
            state={},
            config=config(**cfg),
            client=object(),
            now_fn=lambda: self.now,
            log=lambda *_: None,
        )

    def test_dedup_reinforces_without_new_row(self):
        existing = row(
            "old", "Michael prefiere español", [1.0, 0.0],
            {
                "source_type": "self_learned", "path": "self-memory/old",
                "kind": "preference", "reinforced_count": 1,
                "confidence": 0.55, "last_seen": "2026-08-01T00:00:00+00:00",
            },
        )
        manager = FakeManager([existing])
        engine = self.engine(manager)

        result = engine.add_lesson("Michael prefiere español", kind="preference")

        self.assertEqual(result, "old")
        self.assertEqual(len(manager.stored), 0)
        self.assertEqual(existing["metadata"]["reinforced_count"], 2)
        self.assertEqual(engine.metrics.reinforced, 1)

    def test_promotion_to_always_loaded_fact_at_threshold(self):
        existing = row(
            "stable", "Validar antes de afirmar", [1.0, 0.0],
            {
                "source_type": "self_learned", "path": "self-memory/stable",
                "kind": "operational", "reinforced_count": 2,
                "confidence": 0.75, "promoted": False,
                "last_seen": "2026-08-01T00:00:00+00:00",
            },
        )
        manager = FakeManager([existing])
        engine = self.engine(manager, promote_after=3)

        engine.add_lesson("Validar antes de afirmar", kind="operational")

        self.assertIn("Validar antes de afirmar", manager.facts["learned_principles"])
        self.assertTrue(existing["metadata"]["promoted"])
        self.assertEqual(engine.metrics.promoted, 1)

    def test_decay_retires_stale_low_confidence_lesson(self):
        stale = row(
            "stale", "Detalle antiguo no confirmado", [1.0, 0.0],
            {
                "source_type": "self_learned", "path": "self-memory/stale",
                "confidence": 0.36, "promoted": False,
                "last_seen": "2026-01-01T00:00:00+00:00",
            },
        )
        manager = FakeManager([stale])
        engine = self.engine(manager, decay_days=45, decay_step=0.10, min_confidence_keep=0.35)

        engine.decay()

        self.assertEqual(manager._postgres_backend.rows, [])
        self.assertEqual(engine.metrics.retired, 1)

    def test_compaction_shrinks_store_and_preserves_provenance(self):
        rows = [
            row(
                "a", "Primera variante", [1.0, 0.0],
                {"source_type": "self_learned", "path": "self-memory/a", "confidence": 0.6},
            ),
            row(
                "b", "Segunda variante", [0.99, 0.01],
                {"source_type": "self_learned", "path": "self-memory/b", "confidence": 0.7},
            ),
            row(
                "c", "Memoria distinta", [0.0, 1.0],
                {"source_type": "self_learned", "path": "self-memory/c", "confidence": 0.8},
            ),
        ]
        manager = FakeManager(rows)
        engine = self.engine(
            manager,
            compaction_trigger=2,
            compaction_target=2,
            compaction_similarity=0.90,
        )
        engine._merge_cluster = lambda cluster: "Lección canónica fusionada"

        engine.compact()

        self.assertEqual(len(manager._postgres_backend.rows), 2)
        self.assertEqual(set(manager.stored[0]["metadata"]["merged_from"]), {"a", "b"})
        self.assertEqual(engine.metrics.merged, 1)

    def test_contradiction_marks_older_lesson_superseded(self):
        old = row(
            "old", "La arquitectura usa el puerto anterior", [0.8, 0.2],
            {
                "source_type": "self_learned", "path": "self-memory/old",
                "kind": "architecture", "confidence": 0.8,
            },
        )
        manager = FakeManager([old], vector=[1.0, 0.0])
        engine = self.engine(
            manager,
            dedup_threshold=0.99,
            contradiction_candidate_threshold=0.50,
        )
        engine._classify_relationship = lambda old_text, new_text: "contradicts"

        new_id = engine.add_lesson(
            "La arquitectura usa únicamente el puerto canónico nuevo",
            kind="architecture",
        )

        self.assertEqual(old["metadata"]["superseded_by"], new_id)
        self.assertEqual(engine.metrics.contradictions, 1)
        self.assertEqual(len(manager.stored), 1)

    def test_reflection_marks_older_contradiction_superseded(self):
        older = row(
            "older", "Usar siempre el puerto 5433", [1.0, 0.0],
            {
                "source_type": "self_learned", "path": "self-memory/older",
                "confidence": 0.8, "last_seen": "2026-08-01T00:00:00+00:00",
            },
        )
        newer = row(
            "newer", "Usar siempre el puerto 5432", [0.99, 0.01],
            {
                "source_type": "self_learned", "path": "self-memory/newer",
                "confidence": 0.9, "last_seen": "2026-08-20T00:00:00+00:00",
            },
        )
        manager = FakeManager([older, newer])
        engine = self.engine(manager, contradiction_candidate_threshold=0.50)
        engine._classify_relationship = lambda left, right: "contradicts"

        engine.reconcile_contradictions([older, newer])

        self.assertEqual(older["metadata"]["superseded_by"], "newer")
        self.assertEqual(engine.metrics.contradictions, 1)

    def test_mines_exemplars_corrections_and_code_outcomes_with_watermarks(self):
        messages = [
            {
                "id": "m1", "session_id": "s1", "mode": "chat",
                "role": "assistant", "model": "claude-sonnet-4-6",
                "content": "A" * 120, "created_at": "2026-08-24T01:00:00+00:00",
            },
            {
                "id": "m2", "session_id": "s1", "mode": "chat",
                "role": "user", "model": "gemma4:12b",
                "content": "No, en realidad prefiero respuestas concisas.",
                "created_at": "2026-08-24T02:00:00+00:00",
            },
            {
                "id": "m3", "session_id": "s2", "mode": "code",
                "role": "assistant", "model": "claude-sonnet-4-6",
                "content": "The regression was fixed and all tests passed." * 3,
                "created_at": "2026-08-24T03:00:00+00:00",
            },
        ]
        manager = FakeManager(messages=messages)
        state = {}
        engine = SelfMemoryEngine(
            manager,
            state=state,
            config=config(
                dedup_threshold=1.1,
                contradiction_candidate_threshold=1.1,
            ),
            client=object(),
            now_fn=lambda: self.now,
            log=lambda *_: None,
        )
        engine._chat = lambda prompt: json.dumps({
            "lessons": [{
                "text": "Ejecutar la suite completa después de corregir regresiones",
                "kind": "operational",
                "confidence": 0.9,
            }]
        })

        engine.mine_sources()

        self.assertEqual(engine.metrics.exemplars_added, 2)
        self.assertIn(
            "No, en realidad prefiero respuestas concisas.",
            manager.facts["global_preferences"]["learned_corrections"],
        )
        self.assertEqual(
            set(state["source_watermarks"]),
            {"exemplars", "corrections", "code_outcomes"},
        )
        source_types = [item["metadata"]["source_type"] for item in manager.stored]
        self.assertEqual(source_types.count("exemplar"), 2)
        self.assertGreaterEqual(source_types.count("self_learned"), 2)

    def test_dry_run_reports_promotion_without_writes(self):
        existing = row(
            "stable", "Principio durable", [1.0, 0.0],
            {
                "source_type": "self_learned", "path": "self-memory/stable",
                "kind": "operational", "reinforced_count": 2,
                "confidence": 0.8, "promoted": False,
            },
        )
        manager = FakeManager([existing])
        engine = SelfMemoryEngine(
            manager,
            state={},
            config=config(promote_after=3),
            dry_run=True,
            client=object(),
            now_fn=lambda: self.now,
            log=lambda *_: None,
        )

        engine.add_lesson("Principio durable", kind="operational")

        self.assertEqual(manager.updated, [])
        self.assertEqual(manager.stored, [])
        self.assertEqual(manager.facts["learned_principles"], [])
        self.assertEqual(engine.metrics.promoted, 1)

    def test_resource_gate_reports_battery_cpu_and_ram(self):
        reasons = resource_gate_reasons(
            config(),
            {"on_battery": True, "cpu_percent": 80.0, "memory_percent": 90.0},
        )
        self.assertEqual(len(reasons), 3)

    def test_single_instance_lock_yields_to_existing_holder(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "self-memory.lock"
            first = SingleInstanceLock(path)
            second = SingleInstanceLock(path)
            try:
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
            finally:
                second.release()
                first.release()


if __name__ == "__main__":
    unittest.main()
