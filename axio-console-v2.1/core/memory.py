"""
AXIO Core -- Memory Manager
Three-tier memory system for all AXIO modes.

  Tier 1  Short-term   : crash-safe local journals + Postgres sessions/messages
  Tier 2  Medium-term  : Postgres/pgvector primary + Chroma semantic mirror
  Tier 3  Long-term    : Postgres facts + atomic JSON mirror, with a global
                         console profile and mode-specific context

Usage (any mode):
    from core.memory import MemoryManager, _handle_memory_cmd

    mem = MemoryManager(mode="chat")
    prefix = mem.build_memory_prefix(user_query)
    mem.update_facts({"last_topic": "Python async"})
    mem.store_session(session, ollama_client=ollama)

Modes: "chat", "code", "cowork", "revrec", "console"
"""

from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from .memory_durability import (
    acknowledge,
    atomic_write_json,
    dead_letter,
    enqueue,
    pending_count,
    pending_events,
    record_attempt,
    save_session_snapshot,
    MAX_REPLAY_ATTEMPTS,
)

# ---------------------------------------------------------------------------
#  Config imports
# ---------------------------------------------------------------------------
try:
    from .config import (
        MEMORY_DIR, CHROMA_DIR, OLLAMA_HOST,
        MEMORY_RECALL_RESULTS, MEMORY_SUMMARIZE, MEMORY_SUMMARY_MODEL,
        AXIO_MEMORY_BACKEND,
    )
except ImportError:
    MEMORY_DIR            = Path.home() / ".axio" / "memory"
    CHROMA_DIR            = Path.home() / ".axio" / "chroma-resilient"
    OLLAMA_HOST           = "http://127.0.0.1:11434"
    MEMORY_RECALL_RESULTS = 5
    MEMORY_SUMMARIZE      = True
    MEMORY_SUMMARY_MODEL  = "gemma4:12b"
    AXIO_MEMORY_BACKEND   = "json"

# ---------------------------------------------------------------------------
#  ChromaDB -- optional dependency
# ---------------------------------------------------------------------------
try:
    import chromadb
    from chromadb.config import Settings as _ChromaSettings
    _CHROMA_OK = True
except ImportError:
    _CHROMA_OK = False

# ---------------------------------------------------------------------------
#  Requests
# ---------------------------------------------------------------------------
try:
    import requests as _requests
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

# ---------------------------------------------------------------------------
#  Valid modes
# ---------------------------------------------------------------------------
VALID_MODES = ("chat", "code", "cowork", "revrec", "console")

# Modes that must NOT contribute to the shared console master memory.
# RevRec is a specialized revenue-recognition domain; its deal context must
# stay isolated from the cross-mode (chat/cowork/code) knowledge base.
ISOLATED_MODES = ("revrec",)

# ---------------------------------------------------------------------------
#  Postgres graceful-fallback warning (printed at most once per process)
# ---------------------------------------------------------------------------
_PG_FALLBACK_WARNED = False


def _warn_pg_fallback(exc: Exception):
    """Warn once that the Postgres backend failed and JSON memory is used."""
    global _PG_FALLBACK_WARNED
    if not _PG_FALLBACK_WARNED:
        _PG_FALLBACK_WARNED = True
        print(
            f"  [AXIO memory] Postgres backend unavailable ({exc}); "
            f"falling back to local JSON/keyword memory."
        )


def _is_transient(exc: Exception) -> bool:
    """True if a replay failure is worth retrying (DB unreachable), False if
    it is a permanent 'poison' event (bad payload / constraint violation) that
    would wedge the queue forever if we kept retrying it head-of-line."""
    if isinstance(exc, ValueError):
        return False  # e.g. wrong-dimension embedding -- never succeeds
    try:
        import psycopg
        if isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError)):
            return True  # connection lost -- retry next cycle
        if isinstance(exc, psycopg.Error):
            return False  # IntegrityError / DataError / ProgrammingError -- permanent
    except ImportError:
        pass
    # Unknown error: treat as transient so a fluke never discards real data.
    return True

# ---------------------------------------------------------------------------
#  Default structured-fact schema per mode
# ---------------------------------------------------------------------------
_DEFAULT_FACTS = {
    "chat": {
        "user_name":           "",
        "preferred_language":  "",
        "preferred_tone":      "",
        "recurring_topics":    [],
        "key_projects":        [],
        "preferences":         {},
        "last_session":        "",
        "notes":               [],
    },
    "code": {
        "primary_language":    "",
        "repo_paths":          [],
        "coding_style":        "",
        "known_bugs":          [],
        "completed_tasks":     [],
        "tech_stack":          [],
        "notes":               [],
        "last_session":        "",
    },
    "cowork": {
        "workspace_paths":     [],
        "active_projects":     [],
        "recurring_files":     [],
        "preferred_output":    "",
        "collaborators":       [],
        "notes":               [],
        "last_session":        "",
    },
    "revrec": {
        "known_clients":       [],
        "deal_history":        [],
        "applied_standards":   ["ASC 606", "IFRS 15"],
        "common_issues":       [],
        "excel_templates":     [],
        "notes":               [],
        "last_session":        "",
    },
    "console": {
        "global_profile":      {},
        "all_modes_summary":   {},
        "global_preferences":  {},
        "learned_principles":  [],
        "cross_mode_entities": [],
        "training_stats":      {"total_sessions": 0, "total_turns": 0},
        "notes":               [],
        "last_updated":        "",
    },
}


# ===========================================================================
#  MemoryManager
# ===========================================================================

class MemoryManager:
    """
    Unified memory for one AXIO mode.

    Public API
    ----------
    build_memory_prefix(query)          -> str
    store_session(session, ollama)      -> None
    update_facts(patch: dict)           -> None
    get_facts()                         -> dict
    recall(query, n)                    -> list
    stats()                             -> dict
    """

    def __init__(self, mode: str = "chat"):
        if mode not in VALID_MODES:
            raise ValueError(f"mode must be one of {VALID_MODES}, got: {mode!r}")
        self.mode = mode
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self._facts_path = MEMORY_DIR / f"{mode}_memory.json"
        self.backend_name = AXIO_MEMORY_BACKEND
        self._postgres_backend = None
        if self.backend_name == "postgres":
            try:
                from core.memory_backends.postgres_backend import PostgresMemoryBackend
                self._postgres_backend = PostgresMemoryBackend(self.mode)
            except Exception as exc:
                _warn_pg_fallback(exc)
                self._postgres_backend = None
        self._chroma     = self._init_chroma()

    # -----------------------------------------------------------------------
    #  ChromaDB setup
    # -----------------------------------------------------------------------

    def _init_chroma(self):
        self._chroma_client = None
        if not _CHROMA_OK:
            return None
        try:
            client = chromadb.PersistentClient(
                path=str(CHROMA_DIR),
                settings=_ChromaSettings(anonymized_telemetry=False),
            )
            self._chroma_client = client
            collection = client.get_or_create_collection(
                name=f"axio_{self.mode}",
                metadata={"hnsw:space": "cosine"},
            )
            return collection
        except Exception:
            return None

    def _chroma_collection(self, mode: str):
        """Return the Chroma collection for any mode (for cross-mode recall)."""
        if mode == self.mode:
            return self._chroma
        if not self._chroma_client:
            return None
        try:
            return self._chroma_client.get_or_create_collection(
                name=f"axio_{mode}",
                metadata={"hnsw:space": "cosine"},
            )
        except Exception:
            return None

    def _facts_for_mode(self, mode: str) -> dict:
        """Load structured facts for any mode without a full MemoryManager."""
        if mode == self.mode:
            return self.get_facts()
        base = copy.deepcopy(_DEFAULT_FACTS.get(mode, {}))
        if self._postgres_backend:
            try:
                from core.memory_backends.postgres_backend import PostgresMemoryBackend
                base.update(PostgresMemoryBackend(mode).get_facts())
                path = MEMORY_DIR / f"{mode}_memory.json"
                atomic_write_json(path, base)
                return base
            except Exception as exc:
                _warn_pg_fallback(exc)
        path = MEMORY_DIR / f"{mode}_memory.json"
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    base.update(json.load(f))
            except Exception:
                pass
        return base

    # -----------------------------------------------------------------------
    #  Structured facts (Tier 3)
    # -----------------------------------------------------------------------

    def get_facts(self) -> dict:
        if self._postgres_backend:
            try:
                base = copy.deepcopy(_DEFAULT_FACTS.get(self.mode, {}))
                base.update(self._postgres_backend.get_facts())
                atomic_write_json(self._facts_path, base)
                return base
            except Exception as exc:
                _warn_pg_fallback(exc)
        if self._facts_path.exists():
            try:
                with open(self._facts_path, encoding="utf-8") as f:
                    data = json.load(f)
                base = copy.deepcopy(_DEFAULT_FACTS.get(self.mode, {}))
                base.update(data)
                return base
            except Exception:
                pass
        return copy.deepcopy(_DEFAULT_FACTS.get(self.mode, {}))

    def update_facts(self, patch: dict, source_session_id: str = None):
        facts = self.get_facts()
        for key, value in patch.items():
            if isinstance(value, list) and isinstance(facts.get(key), list):
                existing = facts[key]
                for item in value:
                    if item not in existing:
                        existing.append(item)
                facts[key] = existing
            elif isinstance(value, dict) and isinstance(facts.get(key), dict):
                facts[key].update(value)
            else:
                facts[key] = value
        facts["last_session"] = datetime.now().isoformat()
        atomic_write_json(self._facts_path, facts)

        if self._postgres_backend:
            event_id = enqueue(
                "facts",
                self.mode,
                {"facts": facts, "source_session_id": source_session_id},
            )
            try:
                self._postgres_backend.update_facts(
                    facts,
                    source_session_id=source_session_id,
                )
                acknowledge(event_id)
            except Exception as exc:
                _warn_pg_fallback(exc)

    def auto_update_facts(self, prompt: str, response: str):
        """Extract lightweight facts from a completed turn without LLM calls."""
        import re
        patch = {}

        if self.mode == "chat":
            # Name detection: "my name is X", "I'm X", "I am X"
            m = re.search(r"(?:my name is|i'm|i am)\s+([A-Z][a-z]+)", prompt, re.I)
            if m:
                patch["user_name"] = m.group(1).strip()
            # Track topic keywords from common domains
            topics = []
            for kw in ["finance", "python", "fastapi", "machine learning", "ai",
                        "coding", "legal", "contracts", "excel", "data", "cloud",
                        "accounting", "tax", "marketing", "sales", "hr", "security"]:
                if kw in prompt.lower() or kw in response.lower():
                    topics.append(kw)
            if topics:
                patch["recurring_topics"] = topics

        elif self.mode == "code":
            tech = []
            for kw in ["python", "javascript", "typescript", "rust", "go", "java",
                        "fastapi", "flask", "django", "react", "vue", "angular",
                        "postgres", "mysql", "sqlite", "mongodb", "redis",
                        "docker", "kubernetes", "aws", "azure", "gcp"]:
                if kw in prompt.lower() or kw in response.lower():
                    tech.append(kw)
            if tech:
                patch["tech_stack"] = tech

        elif self.mode == "cowork":
            # Extract mentioned file paths or project names from the combined text
            paths = re.findall(r"[A-Za-z]:[\\\/][\w\\\/\-\.]+", prompt + " " + response)
            if paths:
                patch["workspace_paths"] = [p for p in paths[:5]]

        elif self.mode == "revrec":
            # Detect company names (word(s) before Inc/Ltd/Corp/LLC/Group/Co)
            clients = re.findall(
                r"([A-Z][A-Za-z\s]{2,30}?)\s+(?:Inc|Ltd|Corp|LLC|Group|Co)\.?",
                prompt + " " + response,
            )
            if clients:
                patch["known_clients"] = [c.strip() for c in clients[:5]]

        if patch:
            try:
                self.update_facts(patch)
            except Exception:
                pass

    # -----------------------------------------------------------------------
    #  RAG store (Tier 2)
    # -----------------------------------------------------------------------

    def _embed_via_ollama(self, text: str):
        if not _REQUESTS_OK:
            return None
        try:
            from .config import MEMORY_EMBED_MODEL
            model = MEMORY_EMBED_MODEL
        except ImportError:
            model = "nomic-embed-text:latest"
        try:
            resp = _requests.post(
                f"{OLLAMA_HOST}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=30,
            )
            if resp.ok:
                return resp.json().get("embedding")
        except Exception:
            pass
        return None

    def _local_chunk_id(self, text: str, metadata: dict) -> str:
        identity = "|".join(
            str(metadata.get(key, ""))
            for key in ("source_type", "doc", "path", "title", "session_name")
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"axio:{self.mode}:{identity}:{text}"))

    def _store_local_chunk(
        self,
        text: str,
        embedding: list[float] | None,
        metadata: dict,
        chunk_id: str,
    ) -> None:
        self._store_local_chunk_for_mode(
            self.mode, text, embedding, metadata, chunk_id
        )

    def _store_local_chunk_for_mode(
        self,
        mode: str,
        text: str,
        embedding: list[float] | None,
        metadata: dict,
        chunk_id: str,
    ) -> None:
        collection = self._chroma_collection(mode)
        if not collection or not embedding:
            return
        try:
            collection.upsert(
                ids=[chunk_id],
                documents=[text],
                metadatas=[self._chroma_safe_metadata(metadata)],
                embeddings=[embedding],
            )
        except Exception:
            pass

    @staticmethod
    def _chroma_safe_metadata(metadata: dict) -> dict:
        """Keep rich JSON in Postgres while giving Chroma scalar metadata."""
        safe = {}
        for key, value in (metadata or {}).items():
            if isinstance(value, (str, int, float, bool)):
                safe[key] = value
            elif value is None:
                safe[key] = ""
            else:
                safe[key] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return safe

    @staticmethod
    def _embedding_list(value):
        if value is None:
            return None
        if hasattr(value, "to_list"):
            return value.to_list()
        return list(value)

    def reconcile_pending(self) -> int:
        """Replay durable local events into Postgres, idempotently."""
        if not self._postgres_backend:
            return 0
        try:
            from core.memory_backends.postgres_backend import PostgresMemoryBackend
        except ImportError:
            return 0

        # Replay session-creating events (live_session/session_finalize) before
        # facts, so a `facts` row never hits a foreign-key violation against a
        # `sessions` row that is still queued behind it. sort() is stable, so
        # the mtime order from pending_events() is preserved within each tier.
        _op_priority = {
            "live_session": 0,
            "session_finalize": 0,
            "chunk": 1,
            "chunk_metadata": 1,
            "delete": 1,
            "facts": 2,
        }
        events = pending_events()
        events.sort(key=lambda e: _op_priority.get(e.get("operation"), 1))

        replayed = 0
        for event in events:
            payload = event.get("payload") or {}
            operation = event.get("operation")
            try:
                backend = PostgresMemoryBackend(str(event.get("mode", self.mode)))
                if operation == "facts":
                    backend.update_facts(
                        payload.get("facts", {}),
                        source_session_id=payload.get("source_session_id"),
                    )
                elif operation == "chunk":
                    embedding = payload.get("embedding")
                    if not embedding:
                        embedding = self._embed_via_ollama(payload.get("text", ""))
                    if not embedding:
                        continue
                    backend.store_chunk(
                        payload.get("text", ""),
                        embedding,
                        payload.get("metadata", {}),
                        chunk_id=payload.get("chunk_id"),
                    )
                elif operation == "chunk_metadata":
                    row = backend.update_chunk_metadata(
                        payload.get("chunk_id", ""),
                        payload.get("metadata", {}),
                    )
                    if row:
                        self._store_local_chunk_for_mode(
                            str(event.get("mode", self.mode)),
                            row.get("content", ""),
                            self._embedding_list(row.get("embedding")),
                            row.get("metadata", {}),
                            str(row.get("id") or payload.get("chunk_id", "")),
                        )
                elif operation == "live_session":
                    backend.persist_live_session(payload.get("session", {}))
                elif operation == "session_finalize":
                    backend.persist_session(
                        payload.get("session", {}),
                        payload.get("summary", ""),
                        payload.get("embedding"),
                    )
                elif operation == "delete":
                    backend.delete_chunks(
                        payload.get("source_type", ""),
                        payload.get("key", ""),
                        payload.get("value", ""),
                    )
                else:
                    acknowledge(str(event.get("event_id", "")))
                    continue
                acknowledge(str(event.get("event_id", "")))
                replayed += 1
            except Exception as exc:
                if _is_transient(exc):
                    # Postgres is unreachable -- stop the pass and retry the
                    # whole queue next cycle (do NOT count this against the event).
                    _warn_pg_fallback(exc)
                    break
                # Permanent 'poison' event: isolate it so it can't wedge the
                # queue head-of-line. Dead-letter after repeated failures.
                attempts = record_attempt(event, exc)
                if attempts >= MAX_REPLAY_ATTEMPTS:
                    dead_letter(event)
                    print(
                        f"  [AXIO memory] dead-lettered poison event "
                        f"{event.get('event_id')} after {attempts} attempt(s): {exc}"
                    )
                else:
                    _warn_pg_fallback(exc)
                continue
        return replayed

    def persist_live_session(self, session: dict) -> None:
        """Durably mirror raw messages after every user/assistant event."""
        save_session_snapshot(session)
        if not self._postgres_backend:
            return
        event_id = enqueue(
            "live_session",
            self.mode,
            {"session": session},
        )
        try:
            self._postgres_backend.persist_live_session(session)
            acknowledge(event_id)
            self.reconcile_pending()
        except Exception as exc:
            _warn_pg_fallback(exc)

    def embed_text(self, text: str):
        """Public local-only embedding helper for memory maintenance jobs."""
        return self._embed_via_ollama(text)

    def store_chunk(
        self,
        text: str,
        metadata: dict = None,
        embedding: list[float] = None,
        chunk_id: str = None,
        require_primary: bool = False,
    ) -> str:
        meta      = {"mode": self.mode, "ts": datetime.now().isoformat()}
        if metadata:
            meta.update(metadata)
        embedding = embedding or self._embed_via_ollama(text)
        chunk_id = chunk_id or self._local_chunk_id(text, meta)
        self._store_local_chunk(text, embedding, meta, chunk_id)

        if not self._postgres_backend:
            if require_primary:
                raise RuntimeError("Postgres primary is not active")
            return chunk_id
        event_id = enqueue(
            "chunk",
            self.mode,
            {
                "chunk_id": chunk_id,
                "text": text,
                "embedding": embedding,
                "metadata": meta,
            },
            event_id=chunk_id,
        )
        if not embedding:
            if require_primary:
                raise RuntimeError("Local embedding unavailable; primary write not attempted")
            return chunk_id
        try:
            self._postgres_backend.store_chunk(
                text,
                embedding,
                meta,
                chunk_id=chunk_id,
            )
            acknowledge(event_id)
        except Exception as exc:
            _warn_pg_fallback(exc)
            if require_primary:
                raise
        return chunk_id

    def update_chunk_metadata(self, chunk_id: str, metadata: dict) -> None:
        """Durably update one chunk and refresh its Chroma mirror."""
        if not self._postgres_backend:
            return
        event_id = enqueue(
            "chunk_metadata",
            self.mode,
            {"chunk_id": chunk_id, "metadata": metadata},
        )
        try:
            row = self._postgres_backend.update_chunk_metadata(chunk_id, metadata)
            if row:
                self._store_local_chunk(
                    row.get("content", ""),
                    self._embedding_list(row.get("embedding")),
                    row.get("metadata", metadata),
                    str(row.get("id") or chunk_id),
                )
            acknowledge(event_id)
        except Exception as exc:
            _warn_pg_fallback(exc)

    def delete_chunks(self, source_type: str, key: str, value: str) -> None:
        if self._postgres_backend:
            # Enqueue a durable delete first, so an outage during the DELETE is
            # replayed by reconcile_pending() rather than leaving a stale chunk.
            event_id = enqueue(
                "delete",
                self.mode,
                {"source_type": source_type, "key": key, "value": value},
            )
            try:
                self._postgres_backend.delete_chunks(source_type, key, value)
                acknowledge(event_id)
            except Exception as exc:
                _warn_pg_fallback(exc)
        if self._chroma:
            try:
                self._chroma.delete(
                    where={
                        "$and": [
                            {"mode": {"$eq": self.mode}},
                            {"source_type": {"$eq": source_type}},
                            {key: {"$eq": value}},
                        ]
                    }
                )
            except Exception:
                pass

    def recall(self, query: str, n_results: int = None, allowed_modes: list[str] = None):
        n = n_results or MEMORY_RECALL_RESULTS
        if self._postgres_backend:
            try:
                self.reconcile_pending()
                embedding = self._embed_via_ollama(query)
                if embedding:
                    return self._postgres_backend.recall(embedding, n, modes=allowed_modes)
            except Exception as exc:
                _warn_pg_fallback(exc)
        if self._chroma:
            try:
                embedding = self._embed_via_ollama(query)
                if embedding:
                    modes  = allowed_modes or [self.mode]
                    merged = []
                    for m in modes:
                        coll = self._chroma_collection(m)
                        if not coll:
                            continue
                        try:
                            count = coll.count()
                        except Exception:
                            continue
                        if count == 0:
                            continue
                        results = coll.query(
                            query_embeddings=[embedding],
                            n_results=min(n, count),
                            include=["documents", "metadatas", "distances"],
                        )
                        docs  = results.get("documents",  [[]])[0]
                        metas = results.get("metadatas",  [[]])[0]
                        dists = results.get("distances",  [[]])[0]
                        for d, mt, dist in zip(docs, metas, dists):
                            if (mt or {}).get("superseded_by"):
                                continue
                            merged.append({"text": d, "metadata": mt, "distance": dist})
                    if merged:
                        merged.sort(key=lambda x: x["distance"])
                        return merged[:n]
            except Exception:
                pass
        return self._keyword_fallback(query, allowed_modes)

    def _keyword_fallback(self, query: str, allowed_modes: list[str] = None):
        modes   = allowed_modes or [self.mode]
        q_words = set(query.lower().split())
        hits    = []

        def _scan(obj, mode, path=""):
            if isinstance(obj, str) and obj:
                overlap = q_words & set(obj.lower().split())
                if overlap:
                    hits.append({
                        "text":     obj,
                        "metadata": {"source": "structured_facts", "mode": mode, "path": path},
                        "distance": 1 - len(overlap) / max(len(q_words), 1),
                    })
            elif isinstance(obj, list):
                for item in obj:
                    _scan(item, mode, path)
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    _scan(v, mode, f"{path}.{k}" if path else k)

        for m in modes:
            _scan(self._facts_for_mode(m), m)
        hits.sort(key=lambda x: x["distance"])
        return hits[:MEMORY_RECALL_RESULTS]

    # -----------------------------------------------------------------------
    #  Session summarizer + store
    # -----------------------------------------------------------------------

    def _summarize_session(self, session: dict, ollama_client=None) -> str:
        messages = session.get("messages", [])
        if not messages:
            return ""
        transcript_msgs = messages[-30:]
        transcript = "\n".join(
            f"{m['role'].upper()}: {m['content'][:300]}"
            for m in transcript_msgs
        )
        system_prompt = (
            "You are a memory archivist. Read this conversation and produce a "
            "concise 3-10 sentence summary. Focus on: topics discussed, decisions "
            "made, key entities (people, projects, files, companies), user "
            "preferences revealed, and any open questions. Be factual and dense. "
            "Return plain text only, no markdown."
        )
        user_msg = f"Summarize this conversation:\n\n{transcript}"
        if ollama_client and _REQUESTS_OK:
            try:
                import requests
                resp = requests.post(
                    f"{OLLAMA_HOST}/api/chat",
                    json={
                        "model":    MEMORY_SUMMARY_MODEL,
                        "messages": [
                            {"role": "system",  "content": system_prompt},
                            {"role": "user",    "content": user_msg},
                        ],
                        "stream": False,
                        # Disable qwen3 "thinking": it consumes the output budget and
                        # pushes summarization past the timeout (ASSESS-004 regression),
                        # silently forcing the fallback summary. Harmless for non-thinking
                        # models.
                        "think": False,
                        "options": {"temperature": 0.1, "num_predict": 512},
                    },
                    timeout=120,
                )
                if resp.ok:
                    return resp.json().get("message", {}).get("content", "").strip()
            except Exception:
                pass
        first_user = next(
            (m["content"][:200] for m in messages if m["role"] == "user"), ""
        )
        mode = session.get("mode", self.mode)
        name = session.get("name", "unknown")
        n    = len(messages)
        return (
            f"Session '{name}' ({mode}, {n} messages). "
            f"Started with: {first_user}"
        )

    def store_session(self, session: dict, ollama_client=None):
        if not session.get("messages"):
            return
        save_session_snapshot(session)
        summary = self._summarize_session(session, ollama_client)
        if not summary:
            return

        raw_session_id = str(session.get("id") or uuid.uuid4())
        try:
            session_id = str(uuid.UUID(raw_session_id))
        except ValueError:
            session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"axio:session:{raw_session_id}"))
        session["id"] = session_id
        summary_meta = {
            "source_type": "session_summary",
            "session_name": session.get("name", ""),
            "mode": session.get("mode", self.mode),
            "model": session.get("model", ""),
            "message_count": str(len(session.get("messages", []))),
            "created": session.get("created", ""),
        }
        embedding = self._embed_via_ollama(summary)
        summary_id = str(uuid.uuid5(uuid.UUID(session_id), "summary"))
        self._store_local_chunk(summary, embedding, summary_meta, summary_id)

        if self._postgres_backend:
            event_id = enqueue(
                "session_finalize",
                self.mode,
                {
                    "session": session,
                    "summary": summary,
                    "embedding": embedding,
                },
                event_id=summary_id,
            )
            try:
                session_id = self._postgres_backend.persist_session(
                    session, summary, embedding,
                )
                acknowledge(event_id)
                self.reconcile_pending()
            except Exception as exc:
                _warn_pg_fallback(exc)

        self.update_facts(
            {
                "last_session": session.get("updated", datetime.now().isoformat()),
                "notes":        [summary[:300]],
            },
            source_session_id=session_id,
        )
        session_mode = session.get("mode", self.mode)
        if session_mode not in ISOLATED_MODES:
            self._update_console_master(session_mode, summary)

    def _update_console_master(self, mode: str, summary: str):
        try:
            console_mem = MemoryManager(mode="console")
            console_mem.update_facts({
                "all_modes_summary": {mode: summary[:500]},
                "last_updated":      datetime.now().isoformat(),
            })
            facts = console_mem.get_facts()
            stats = facts.get("training_stats", {"total_sessions": 0, "total_turns": 0})
            stats["total_sessions"] = stats.get("total_sessions", 0) + 1
            stats["total_turns"]    = stats.get("total_turns", 0) + 1
            console_mem.update_facts({"training_stats": stats})
        except Exception:
            pass

    # -----------------------------------------------------------------------
    #  Memory prefix builder
    # -----------------------------------------------------------------------

    def build_memory_prefix(self, query: str = "", allowed_modes: list[str] = None) -> str:
        parts = []
        facts = self.get_facts()
        console_facts = self._facts_for_mode("console") if self.mode != "revrec" else {}
        global_profile = console_facts.get("global_profile", {})
        fact_lines = []

        user_name = global_profile.get("user_name") or facts.get("user_name")
        preferred_language = (
            global_profile.get("preferred_language") or facts.get("preferred_language")
        )
        preferred_tone = global_profile.get("preferred_tone") or facts.get("preferred_tone")
        key_projects = global_profile.get("key_projects") or facts.get("key_projects")

        if user_name:
            fact_lines.append(f"User name: {user_name}")
        if preferred_language:
            fact_lines.append(f"Preferred language: {preferred_language}")
        if preferred_tone:
            fact_lines.append(f"Preferred tone: {preferred_tone}")
        if facts.get("primary_language"):
            fact_lines.append(f"Primary coding language: {facts['primary_language']}")
        if facts.get("tech_stack"):
            fact_lines.append(f"Tech stack: {', '.join(facts['tech_stack'][:5])}")
        if facts.get("active_projects"):
            fact_lines.append(f"Active projects: {', '.join(str(p) for p in facts['active_projects'][:3])}")
        if facts.get("known_clients"):
            fact_lines.append(f"Known clients: {', '.join(str(c) for c in facts['known_clients'][:5])}")
        if key_projects:
            fact_lines.append(f"Key projects: {', '.join(str(p) for p in key_projects[:5])}")
        if console_facts.get("global_preferences"):
            preferences = console_facts["global_preferences"]
            fact_lines.append(
                "Global preferences: "
                + ", ".join(f"{key}={value}" for key, value in preferences.items())
            )
        if console_facts.get("learned_principles"):
            principles = console_facts["learned_principles"]
            fact_lines.append(
                "Learned principles:\n  - "
                + "\n  - ".join(str(item) for item in principles[:10])
            )
        if facts.get("notes"):
            recent_notes = facts["notes"][-3:]
            fact_lines.append("Recent memory notes:\n  - " + "\n  - ".join(recent_notes))

        if fact_lines:
            parts.append("=== LONG-TERM MEMORY ===\n" + "\n".join(fact_lines))

        if query:
            recalls = self.recall(
                query,
                n_results=MEMORY_RECALL_RESULTS,
                allowed_modes=allowed_modes,
            )
            if recalls:
                recall_texts = [r["text"] for r in recalls if r.get("text")]
                if recall_texts:
                    parts.append(
                        "=== RELEVANT MEMORY ===\n"
                        + "\n---\n".join(recall_texts[:MEMORY_RECALL_RESULTS])
                    )

        if not parts:
            return ""

        return (
            "\n\n[AXIO MEMORY -- use this context to give more personalised, "
            "consistent responses. Do not quote it verbatim.]\n"
            + "\n\n".join(parts)
            + "\n[END MEMORY]\n"
        )

    # -----------------------------------------------------------------------
    #  Diagnostics
    # -----------------------------------------------------------------------

    def stats(self) -> dict:
        if self._postgres_backend:
            try:
                backend_stats = self._postgres_backend.stats()
                facts = self.get_facts()
                return {
                    "mode":         self.mode,
                    "backend":      "postgres",
                    "facts_file":   "postgres",
                    "facts_loaded": bool(facts),
                    "chroma_ok":    False,
                    "chroma_docs":  backend_stats.get("embedding_count", 0),
                    "last_session": facts.get("last_session", "never"),
                    "primary":      "postgres",
                    "local_mirror": str(MEMORY_DIR.parent),
                    "pending_events": pending_count(),
                    **backend_stats,
                }
            except Exception as exc:
                _warn_pg_fallback(exc)
        chroma_count = 0
        chroma_ok    = False
        if self._chroma:
            try:
                chroma_count = self._chroma.count()
                chroma_ok    = True
            except Exception:
                pass
        facts = self.get_facts()
        return {
            "mode":         self.mode,
            "facts_file":   str(self._facts_path),
            "facts_loaded": bool(self._facts_path.exists()),
            "chroma_ok":    chroma_ok,
            "chroma_docs":  chroma_count,
            "last_session": facts.get("last_session", "never"),
            "primary":      "local",
            "local_mirror": str(MEMORY_DIR.parent),
            "pending_events": pending_count(),
        }

    def source_counts(self) -> list[dict]:
        if self._postgres_backend:
            try:
                return self._postgres_backend.source_counts()
            except Exception as exc:
                _warn_pg_fallback(exc)
        return []


# ===========================================================================
#  /memory command handler -- shared by all modes
# ===========================================================================

def _handle_memory_cmd(cmd: str, mem: MemoryManager):
    """
    Handle the 'memory' and 'memory set <key> <value>' commands.
    Call from any mode's command loop.
    """
    try:
        from core.ui import BOLD, CYAN, YELLOW, GREEN, DIM, RESET, ok, warn, lo
    except ImportError:
        BOLD = CYAN = YELLOW = GREEN = DIM = RESET = ""
        def ok(s):   return s
        def warn(s): return s
        def lo(s):   return s

    parts = cmd.split(maxsplit=2)

    if len(parts) >= 3 and parts[1] == "set":
        key_val = cmd[len("memory set "):].split(maxsplit=1)
        if len(key_val) == 2:
            key, val = key_val
            facts = mem.get_facts()
            if key in facts and isinstance(facts[key], list):
                mem.update_facts({key: [val]})
            else:
                mem.update_facts({key: val})
            print(f"  {ok('Memory updated:')} {key} = {val}\n")
        else:
            print(f"  {warn('Usage: memory set <key> <value>')}\n")
        return

    facts = mem.get_facts()
    s     = mem.stats()

    print(f"\n  {BOLD}IOAF Memory -- {mem.mode} mode{RESET}")
    print(f"  {'-'*40}")
    chroma_status = ok("online") if s["chroma_ok"] else warn("offline (keyword fallback)")
    print(f"  ChromaDB  : {chroma_status}  ({s['chroma_docs']} stored sessions)")
    print(f"  Facts file: {lo(s['facts_file'])}")
    print(f"  Last saved: {lo(s['last_session'])}")
    print(f"\n  {BOLD}Stored facts:{RESET}")

    for key, val in facts.items():
        if not val or val == [] or val == {}:
            continue
        if isinstance(val, list):
            display = ", ".join(str(v) for v in val[:5])
            if len(val) > 5:
                display += f" (+{len(val)-5} more)"
        elif isinstance(val, dict):
            display = str(val)[:80]
        else:
            display = str(val)[:80]
        print(f"    {CYAN}{key:<25}{RESET} {display}")

    print(f"\n  {lo('Tip:')} {YELLOW}memory set <key> <value>{RESET} {lo('to correct a fact')}\n")


# ===========================================================================
#  install helper
# ===========================================================================

def ensure_chromadb() -> bool:
    global _CHROMA_OK
    if _CHROMA_OK:
        return True
    try:
        import subprocess, sys
        print("  Installing chromadb (one-time) ...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "chromadb",
             "--quiet", "--break-system-packages"],
            check=True,
        )
        import chromadb as _c  # noqa: F401
        _CHROMA_OK = True
        print("  chromadb installed OK")
        return True
    except Exception as e:
        print(f"  chromadb install failed: {e}  (RAG will use keyword fallback)")
        return False
