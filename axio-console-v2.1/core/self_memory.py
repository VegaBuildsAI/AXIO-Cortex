"""Continuous, local-only self-memory for AXIO Cortex.

This module maintains derived context. It never changes model weights and never
deletes raw sessions/messages. All mutations flow through MemoryManager so the
Postgres-primary, Chroma-mirror, durable-outbox contract remains intact.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import AXIO_DATA_ROOT, CONFIG_DIR, MODELS
from .models import OllamaClient


DEFAULT_CONFIG = {
    "dedup_threshold": 0.92,
    "contradiction_candidate_threshold": 0.58,
    "promote_after": 3,
    "compaction_trigger": 200,
    "compaction_target": 60,
    "compaction_similarity": 0.78,
    "decay_days": 45,
    "decay_step": 0.10,
    "min_confidence_keep": 0.35,
    "consolidate_every": 6,
    "reflect_every_hours": 168,
    "max_lessons_per_batch": 5,
    "max_promoted_principles": 30,
    "max_corrections": 30,
    "max_exemplars": 100,
    "max_contradiction_checks": 20,
    "message_batch_limit": 500,
    "resource_gate": {
        "skip_on_battery": True,
        "max_cpu_percent": 70,
        "max_memory_percent": 85,
    },
}

SELF_MEMORY_CONFIG = CONFIG_DIR / "self_memory.yaml"
LOCK_FILE = AXIO_DATA_ROOT / "self_memory.lock"


def _deep_merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_self_memory_config(path: Path = SELF_MEMORY_CONFIG) -> dict:
    config = _deep_merge({}, DEFAULT_CONFIG)
    if not path.exists():
        return config
    try:
        import yaml

        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("self_memory config must be a mapping")
        return _deep_merge(config, loaded)
    except ImportError as exc:
        raise RuntimeError("PyYAML is required for config/self_memory.yaml") from exc


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value=None) -> str:
    if isinstance(value, datetime):
        dt = value
    elif value:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            dt = _utcnow()
    else:
        dt = _utcnow()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_time(value) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return _utcnow()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _vector_list(value) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "to_list"):
        return value.to_list()
    return list(value)


def _metadata(row: dict) -> dict:
    value = row.get("metadata") or {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    return dict(value)


def _cosine(left, right) -> float:
    a = _vector_list(left)
    b = _vector_list(right)
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@dataclass
class SelfMemoryMetrics:
    new_lessons: int = 0
    reinforced: int = 0
    promoted: int = 0
    retired: int = 0
    merged: int = 0
    exemplars_added: int = 0
    contradictions: int = 0
    review_required: int = 0
    pending_events: int = 0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class SingleInstanceLock:
    """OS-backed non-blocking lock shared by continuous and scheduled runners."""

    def __init__(self, path: Path = LOCK_FILE):
        self.path = Path(path)
        self.handle = None
        self.acquired = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "a+b")
        self.handle.seek(0, os.SEEK_END)
        if self.handle.tell() == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            self.handle.close()
            self.handle = None
            return False
        self.acquired = True
        return True

    def release(self) -> None:
        if not self.handle:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
            self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()


def _windows_power_and_memory() -> dict:
    result = {"on_battery": False, "memory_percent": None}
    if os.name != "nt":
        return result

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_byte),
            ("BatteryFlag", ctypes.c_byte),
            ("BatteryLifePercent", ctypes.c_byte),
            ("SystemStatusFlag", ctypes.c_byte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    power = SYSTEM_POWER_STATUS()
    if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
        result["on_battery"] = power.ACLineStatus == 0
    memory = MEMORYSTATUSEX()
    memory.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        result["memory_percent"] = float(memory.dwMemoryLoad)
    return result


def _cpu_percent(sample_seconds: float = 0.10) -> float | None:
    try:
        if os.name != "nt":
            load = os.getloadavg()[0]
            return min(100.0, load / max(os.cpu_count() or 1, 1) * 100.0)

        class FILETIME(ctypes.Structure):
            _fields_ = [("low", ctypes.c_ulong), ("high", ctypes.c_ulong)]

        def snapshot():
            idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
            ok = ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
            )
            if not ok:
                return None
            as_int = lambda item: (item.high << 32) + item.low
            return as_int(idle), as_int(kernel), as_int(user)

        first = snapshot()
        time.sleep(sample_seconds)
        second = snapshot()
        if not first or not second:
            return None
        idle = second[0] - first[0]
        total = (second[1] - first[1]) + (second[2] - first[2])
        return max(0.0, min(100.0, (1.0 - idle / total) * 100.0)) if total else 0.0
    except Exception:
        return None


def resource_snapshot() -> dict:
    values = _windows_power_and_memory()
    values["cpu_percent"] = _cpu_percent()
    return values


def resource_gate_reasons(config: dict, snapshot: dict | None = None) -> list[str]:
    gate = config.get("resource_gate", {})
    values = snapshot or resource_snapshot()
    reasons = []
    if gate.get("skip_on_battery") and values.get("on_battery"):
        reasons.append("running on battery")
    cpu = values.get("cpu_percent")
    if cpu is not None and cpu > float(gate.get("max_cpu_percent", 100)):
        reasons.append(f"CPU {cpu:.1f}%")
    memory = values.get("memory_percent")
    if memory is not None and memory > float(gate.get("max_memory_percent", 100)):
        reasons.append(f"RAM {memory:.1f}%")
    return reasons


class SelfMemoryEngine:
    _CORRECTION_RE = re.compile(
        r"\b(no[, ]+en realidad|correcci[oó]n|prefiero|mi preferencia|"
        r"actually|correction|i prefer|please remember)\b",
        re.IGNORECASE,
    )
    _CODE_OUTCOME_RE = re.compile(
        r"\b(passed|fixed|working|failed|error|regression|aprob|correg|fall[oó]|funciona)\w*\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        manager,
        state: dict,
        config: dict | None = None,
        dry_run: bool = False,
        log=print,
        client=None,
        now_fn=None,
    ):
        self.manager = manager
        self.backend = manager._postgres_backend
        if not self.backend:
            raise RuntimeError("Self-memory requires the Postgres-primary backend")
        self.state = state
        self.config = config or load_self_memory_config()
        self.dry_run = dry_run
        self.log = log
        self.client = client or OllamaClient()
        self.now_fn = now_fn or _utcnow
        self.metrics = SelfMemoryMetrics()
        self._started = time.perf_counter()

    def reset_metrics(self) -> None:
        self.metrics = SelfMemoryMetrics()
        self._started = time.perf_counter()

    def finish_metrics(self, pending_events: int = 0) -> dict:
        self.metrics.pending_events = int(pending_events)
        self.metrics.duration_ms = int((time.perf_counter() - self._started) * 1000)
        return self.metrics.to_dict()

    def _chat(self, prompt: str) -> str:
        self.metrics.model_calls += 1
        answer = self.client.chat_stream(
            MODELS["fast"],
            [{"role": "user", "content": prompt}],
            print_output=False,
        ).strip()
        usage = getattr(self.client, "last_usage", None) or {}
        self.metrics.input_tokens += int(usage.get("input", 0) or 0)
        self.metrics.output_tokens += int(usage.get("output", 0) or 0)
        return answer

    @staticmethod
    def _json_object(text: str) -> dict:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start:end + 1])
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                pass
        return {}

    def _parse_lessons(self, text: str) -> list[dict]:
        payload = self._json_object(text)
        values = payload.get("lessons", []) if payload else []
        lessons = []
        if isinstance(values, list):
            for value in values:
                if isinstance(value, str):
                    value = {"text": value}
                if not isinstance(value, dict):
                    continue
                lesson = self._normalize_lesson(value)
                if lesson:
                    lessons.append(lesson)
        if lessons:
            return lessons[: int(self.config["max_lessons_per_batch"])]
        for line in text.splitlines():
            cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            if cleaned:
                lessons.append({"text": cleaned, "kind": "other", "confidence": 0.55})
        return lessons[: int(self.config["max_lessons_per_batch"])]

    @staticmethod
    def _normalize_lesson(value: dict) -> dict | None:
        text = " ".join(str(value.get("text", "")).split()).strip()
        if len(text) < 12:
            return None
        kind = str(value.get("kind", "other")).lower().strip()
        allowed = {"preference", "profile", "architecture", "operational", "other"}
        if kind not in allowed:
            kind = "other"
        try:
            confidence = max(0.0, min(1.0, float(value.get("confidence", 0.55))))
        except (TypeError, ValueError):
            confidence = 0.55
        return {"text": text, "kind": kind, "confidence": confidence}

    def distill_summaries(self, rows: list[dict]) -> list[dict]:
        body = "\n---\n".join(
            f"[{row['mode']}] {str(row['summary'])[:800]}" for row in rows
        )
        prompt = (
            "Eres el motor local de memoria de AXIO. Extrae solo lecciones duraderas "
            "y generalizables de los resúmenes: preferencias de Michael, perfil, "
            "decisiones de arquitectura y aprendizajes operativos. Ignora detalles "
            "efímeros. Devuelve JSON estricto con esta forma: "
            '{"lessons":[{"text":"...","kind":"preference|profile|architecture|operational|other",'
            '"confidence":0.0}]}. Máximo '
            f"{self.config['max_lessons_per_batch']} lecciones.\n\n{body[:8000]}"
        )
        return self._parse_lessons(self._chat(prompt))

    def _classify_relationship(self, old_text: str, new_text: str) -> str:
        prompt = (
            "Compara dos memorias. Responde JSON estricto: "
            '{"relationship":"duplicate|contradicts|distinct"}. '
            "duplicate significa mismo hecho; contradicts significa incompatibles; "
            f"distinct significa relacionados pero compatibles.\nA: {old_text[:1200]}\nB: {new_text[:1200]}"
        )
        relation = self._json_object(self._chat(prompt)).get("relationship", "distinct")
        return relation if relation in {"duplicate", "contradicts", "distinct"} else "distinct"

    def _promote(self, text: str, kind: str, metadata: dict) -> bool:
        if kind not in {"preference", "profile", "architecture", "operational"}:
            return False
        facts = self.backend.get_facts() if self.dry_run else self.manager.get_facts()
        principles = list(facts.get("learned_principles", []))
        if text not in principles:
            principles.append(text)
            principles = principles[-int(self.config["max_promoted_principles"]):]
            if not self.dry_run:
                self.manager.update_facts({"learned_principles": principles})
        metadata["promoted"] = True
        metadata["promoted_at"] = _iso(self.now_fn())
        metadata["promotion_key"] = "learned_principles"
        self.metrics.promoted += 1
        return True

    def add_lesson(
        self,
        text: str,
        kind: str = "other",
        confidence: float = 0.55,
        provenance: dict | None = None,
        source_type: str = "self_learned",
    ) -> str | None:
        normalized = self._normalize_lesson(
            {"text": text, "kind": kind, "confidence": confidence}
        )
        if not normalized:
            return None
        text, kind, confidence = (
            normalized["text"], normalized["kind"], normalized["confidence"]
        )
        embedding = self.manager.embed_text(text)
        if not embedding:
            self.log("  self-memory skipped lesson (embedding unavailable)")
            return None

        nearest = self.backend.find_similar(embedding, source_type, threshold=0.0)
        similarity = float(nearest.get("similarity", 0.0)) if nearest else 0.0
        relationship = None
        if nearest and similarity >= float(self.config["contradiction_candidate_threshold"]):
            if str(nearest["content"]).casefold() == text.casefold():
                relationship = "duplicate"
            else:
                relationship = self._classify_relationship(str(nearest["content"]), text)
        if nearest and (
            relationship == "duplicate"
            or (
                similarity >= float(self.config["dedup_threshold"])
                and relationship != "contradicts"
            )
        ):
            meta = _metadata(nearest)
            count = int(meta.get("reinforced_count", 1)) + 1
            meta.update({
                "reinforced_count": count,
                "last_seen": _iso(self.now_fn()),
                "confidence": min(1.0, float(meta.get("confidence", 0.55)) + 0.10),
            })
            origins = list(meta.get("provenance", []))
            if provenance and provenance not in origins:
                origins.append(provenance)
            meta["provenance"] = origins[-20:]
            if count >= int(self.config["promote_after"]) and not meta.get("promoted"):
                self._promote(str(nearest["content"]), str(meta.get("kind", kind)), meta)
            if not self.dry_run:
                self.manager.update_chunk_metadata(str(nearest["id"]), meta)
            self.metrics.reinforced += 1
            return str(nearest["id"])

        chunk_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"axio:self-memory:{source_type}:{text.casefold()}",
        ))
        now = _iso(self.now_fn())
        meta = {
            "source_type": source_type,
            "path": f"self-memory/{source_type}/{chunk_id}",
            "title": kind.replace("_", " "),
            "kind": kind,
            "reinforced_count": 1,
            "confidence": confidence,
            "first_seen": now,
            "last_seen": now,
            "provenance": [provenance] if provenance else [],
            "promoted": False,
        }

        if not self.dry_run:
            self.manager.store_chunk(
                text,
                metadata=meta,
                embedding=embedding,
                chunk_id=chunk_id,
                require_primary=True,
            )
        if nearest and relationship == "contradicts":
            old_meta = _metadata(nearest)
            old_meta["superseded_by"] = chunk_id
            old_meta["superseded_at"] = now
            old_meta["confidence"] = max(0.0, float(old_meta.get("confidence", 0.55)) - 0.30)
            if not self.dry_run:
                self.manager.update_chunk_metadata(str(nearest["id"]), old_meta)
            self.metrics.contradictions += 1
            self.log(f"  contradiction: {nearest['id']} superseded by {chunk_id}")
        self.metrics.new_lessons += 1
        return chunk_id

    def consolidate_summaries(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        lessons = self.distill_summaries(rows)
        if not lessons:
            return 0
        source_ids = [str(row.get("id", row.get("ended_at", ""))) for row in rows]
        for lesson in lessons:
            self.add_lesson(
                lesson["text"],
                lesson["kind"],
                lesson["confidence"],
                provenance={"source": "session_summaries", "ids": source_ids},
            )
        return len(rows)

    def _promote_correction(self, text: str) -> None:
        facts = self.backend.get_facts() if self.dry_run else self.manager.get_facts()
        preferences = dict(facts.get("global_preferences", {}))
        corrections = list(preferences.get("learned_corrections", []))
        if text not in corrections:
            corrections.append(text)
            corrections = corrections[-int(self.config["max_corrections"]):]
            preferences["learned_corrections"] = corrections
            if not self.dry_run:
                self.manager.update_facts({"global_preferences": preferences})
            self.metrics.promoted += 1

    @staticmethod
    def _latest_timestamp(rows: list[dict]) -> str | None:
        values = [row.get("created_at") for row in rows if row.get("created_at")]
        return _iso(max(values, key=lambda item: _parse_time(item))) if values else None

    def mine_sources(self) -> None:
        watermarks = dict(self.state.get("source_watermarks", {}))
        limit = int(self.config["message_batch_limit"])

        exemplar_rows = self.backend.recent_messages(watermarks.get("exemplars"), limit)
        for row in exemplar_rows:
            if (
                row.get("role") == "assistant"
                and str(row.get("model", "")).lower().startswith("claude-")
                and len(str(row.get("content", ""))) >= 80
            ):
                message_id = str(row["id"])
                chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"axio:exemplar:{message_id}"))
                meta = {
                    "source_type": "exemplar",
                    "path": f"self-memory/exemplar/{message_id}",
                    "title": "Claude exemplar",
                    "source_message_id": message_id,
                    "source_session_id": str(row.get("session_id", "")),
                    "first_seen": _iso(row.get("created_at")),
                }
                if not self.dry_run:
                    self.manager.store_chunk(
                        str(row["content"])[:4000], metadata=meta, chunk_id=chunk_id,
                        require_primary=True,
                    )
                self.metrics.exemplars_added += 1
        latest = self._latest_timestamp(exemplar_rows)
        if latest and not self.dry_run:
            watermarks["exemplars"] = latest
        if not self.dry_run:
            exemplars = self.backend.list_chunks(
                "exemplar", limit=int(self.config["max_exemplars"]) + limit
            )
            excess = max(0, len(exemplars) - int(self.config["max_exemplars"]))
            for item in exemplars[:excess]:
                path = _metadata(item).get("path")
                if path:
                    self.manager.delete_chunks("exemplar", "path", str(path))
                    self.metrics.retired += 1

        correction_rows = self.backend.recent_messages(watermarks.get("corrections"), limit)
        for row in correction_rows:
            content = " ".join(str(row.get("content", "")).split())
            if row.get("role") == "user" and self._CORRECTION_RE.search(content):
                content = content[:1000]
                self._promote_correction(content)
                self.add_lesson(
                    content,
                    kind="preference",
                    confidence=0.90,
                    provenance={"source": "user_correction", "message_id": str(row["id"])},
                )
        latest = self._latest_timestamp(correction_rows)
        if latest and not self.dry_run:
            watermarks["corrections"] = latest

        code_rows = self.backend.recent_messages(watermarks.get("code_outcomes"), limit)
        outcomes = [
            row for row in code_rows
            if row.get("mode") == "code"
            and row.get("role") == "assistant"
            and self._CODE_OUTCOME_RE.search(str(row.get("content", "")))
        ]
        if outcomes:
            body = "\n---\n".join(str(row["content"])[:1000] for row in outcomes[:20])
            prompt = (
                "Extrae lecciones operativas duraderas de estos resultados de código. "
                "No copies detalles efímeros. Devuelve JSON estricto "
                '{"lessons":[{"text":"...","kind":"operational","confidence":0.0}]}.\n'
                + body
            )
            for lesson in self._parse_lessons(self._chat(prompt)):
                self.add_lesson(
                    lesson["text"],
                    kind="operational",
                    confidence=lesson["confidence"],
                    provenance={
                        "source": "code_outcomes",
                        "message_ids": [str(row["id"]) for row in outcomes[:20]],
                    },
                )
        latest = self._latest_timestamp(code_rows)
        if latest and not self.dry_run:
            watermarks["code_outcomes"] = latest

        if not self.dry_run:
            self.state["source_watermarks"] = watermarks

    def decay(self, rows: list[dict] | None = None) -> None:
        rows = rows if rows is not None else self.backend.list_chunks("self_learned")
        now = self.now_fn()
        decay_days = max(1, int(self.config["decay_days"]))
        for row in rows:
            meta = _metadata(row)
            age = (now - _parse_time(meta.get("last_seen") or row.get("created_at"))).days
            if age < decay_days:
                continue
            steps = max(1, age // decay_days)
            old_conf = float(meta.get("confidence", 0.55))
            new_conf = max(0.0, old_conf - float(self.config["decay_step"]) * steps)
            if meta.get("promoted"):
                if new_conf < float(self.config["min_confidence_keep"]):
                    self.metrics.review_required += 1
                    self.log(f"  review required for promoted lesson {row['id']}")
                continue
            if new_conf < float(self.config["min_confidence_keep"]):
                path = meta.get("path")
                if path:
                    if not self.dry_run:
                        self.manager.delete_chunks("self_learned", "path", str(path))
                    self.metrics.retired += 1
                continue
            if new_conf < old_conf:
                meta["confidence"] = new_conf
                meta["last_decay_at"] = _iso(now)
                if not self.dry_run:
                    self.manager.update_chunk_metadata(str(row["id"]), meta)

    def _clusters(self, rows: list[dict]) -> list[list[dict]]:
        threshold = float(self.config["compaction_similarity"])
        remaining = list(rows)
        clusters = []
        while remaining:
            seed = remaining.pop(0)
            cluster = [seed]
            rest = []
            for row in remaining:
                if _cosine(seed.get("embedding"), row.get("embedding")) >= threshold:
                    cluster.append(row)
                else:
                    rest.append(row)
            remaining = rest
            clusters.append(cluster)
        return sorted(clusters, key=len, reverse=True)

    def reconcile_contradictions(self, rows: list[dict]) -> None:
        """Mark older contradictory derived lessons during deep reflection."""
        threshold = float(self.config["contradiction_candidate_threshold"])
        remaining_checks = int(self.config["max_contradiction_checks"])
        active = [row for row in rows if not _metadata(row).get("superseded_by")]
        for left_index, left in enumerate(active):
            for right in active[left_index + 1:]:
                if remaining_checks <= 0:
                    return
                if _cosine(left.get("embedding"), right.get("embedding")) < threshold:
                    continue
                remaining_checks -= 1
                if self._classify_relationship(
                    str(left.get("content", "")), str(right.get("content", ""))
                ) != "contradicts":
                    continue
                pair = sorted(
                    (left, right),
                    key=lambda item: _parse_time(
                        _metadata(item).get("last_seen") or item.get("created_at")
                    ),
                )
                older, newer = pair[0], pair[1]
                meta = _metadata(older)
                meta["superseded_by"] = str(newer["id"])
                meta["superseded_at"] = _iso(self.now_fn())
                meta["confidence"] = max(0.0, float(meta.get("confidence", 0.55)) - 0.30)
                if not self.dry_run:
                    self.manager.update_chunk_metadata(str(older["id"]), meta)
                self.metrics.contradictions += 1
                self.log(
                    f"  reflection contradiction: {older['id']} "
                    f"superseded by {newer['id']}"
                )

    def _merge_cluster(self, rows: list[dict]) -> str | None:
        body = "\n".join(f"- {str(row['content'])[:1000]}" for row in rows)
        prompt = (
            "Fusiona estas memorias relacionadas en UNA lección canónica, factual y "
            "concisa. Si se contradicen, conserva la más reciente y no inventes. "
            'Devuelve JSON estricto {"text":"..."}.\n' + body
        )
        text = str(self._json_object(self._chat(prompt)).get("text", "")).strip()
        return " ".join(text.split()) if len(text) >= 12 else None

    def compact(self, rows: list[dict] | None = None) -> None:
        rows = rows if rows is not None else self.backend.list_chunks("self_learned")
        if len(rows) <= int(self.config["compaction_trigger"]):
            return
        projected = len(rows)
        target = int(self.config["compaction_target"])
        for cluster in self._clusters(rows):
            if len(cluster) < 2 or projected <= target:
                continue
            merged_text = self._merge_cluster(cluster)
            if not merged_text:
                continue
            merged_ids = [str(row["id"]) for row in cluster]
            merged_id = str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                "axio:self-memory:merged:" + ":".join(sorted(merged_ids)),
            ))
            metas = [_metadata(row) for row in cluster]
            meta = {
                "source_type": "self_learned",
                "path": f"self-memory/self_learned/{merged_id}",
                "title": "compacted lesson",
                "kind": metas[0].get("kind", "other"),
                "reinforced_count": sum(int(item.get("reinforced_count", 1)) for item in metas),
                "confidence": max(float(item.get("confidence", 0.55)) for item in metas),
                "first_seen": min(str(item.get("first_seen", _iso())) for item in metas),
                "last_seen": _iso(self.now_fn()),
                "merged_from": merged_ids,
                "promoted": any(bool(item.get("promoted")) for item in metas),
            }
            if not self.dry_run:
                embedding = self.manager.embed_text(merged_text)
                if not embedding:
                    continue
                self.manager.store_chunk(
                    merged_text, metadata=meta, embedding=embedding, chunk_id=merged_id,
                    require_primary=True,
                )
                for item in metas:
                    if item.get("path"):
                        self.manager.delete_chunks(
                            "self_learned", "path", str(item["path"])
                        )
            reduced = len(cluster) - 1
            projected -= reduced
            self.metrics.merged += reduced

    def reflection_due(self) -> bool:
        last = self.state.get("last_reflection")
        if not last:
            return True
        hours = (self.now_fn() - _parse_time(last)).total_seconds() / 3600
        return hours >= float(self.config["reflect_every_hours"])

    def reflect(self, force: bool = False) -> bool:
        count = self.backend.count_chunks("self_learned")
        if not force and not self.reflection_due() and count <= int(self.config["compaction_trigger"]):
            return False
        rows = self.backend.list_chunks("self_learned")
        self.decay(rows)
        self.reconcile_contradictions(rows)
        self.compact([row for row in rows if not _metadata(row).get("superseded_by")])
        if not self.dry_run:
            self.state["last_reflection"] = _iso(self.now_fn())
        return True
