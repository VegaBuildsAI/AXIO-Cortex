"""
AXIO Core -- Memory Manager
Three-tier memory system for all AXIO modes.

  Tier 1  Short-term   : Session JSON (existing, handled by SessionManager)
  Tier 2  Medium-term  : ChromaDB RAG -- searchable past sessions per mode
  Tier 3  Long-term    : Structured JSON facts -- preferences, key entities,
                         project context, deal history (per mode + console master)

Usage (any mode):
    from core.memory import MemoryManager, _handle_memory_cmd

    mem = MemoryManager(mode="chat")
    prefix = mem.build_memory_prefix(user_query)
    mem.update_facts({"last_topic": "Python async"})
    mem.store_session(session, ollama_client=ollama)

Modes: "chat", "code", "cowork", "revrec", "console"
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    CHROMA_DIR            = Path.home() / ".axio" / "chroma"
    OLLAMA_HOST           = "http://127.0.0.1:11434"
    MEMORY_RECALL_RESULTS = 5
    MEMORY_SUMMARIZE      = True
    MEMORY_SUMMARY_MODEL  = "qwen3:14b"
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
        "all_modes_summary":   {},
        "global_preferences":  {},
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
        base = dict(_DEFAULT_FACTS.get(mode, {}))
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
                base = dict(_DEFAULT_FACTS.get(self.mode, {}))
                base.update(self._postgres_backend.get_facts())
                return base
            except Exception as exc:
                _warn_pg_fallback(exc)
        if self._facts_path.exists():
            try:
                with open(self._facts_path, encoding="utf-8") as f:
                    data = json.load(f)
                base = dict(_DEFAULT_FACTS.get(self.mode, {}))
                base.update(data)
                return base
            except Exception:
                pass
        return dict(_DEFAULT_FACTS.get(self.mode, {}))

    def update_facts(self, patch: dict, source_session_id: str = None):
        if self._postgres_backend:
            try:
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
                self._postgres_backend.update_facts(facts, source_session_id=source_session_id)
                return
            except Exception as exc:
                _warn_pg_fallback(exc)
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
        with open(self._facts_path, "w", encoding="utf-8") as f:
            json.dump(facts, f, indent=2, ensure_ascii=False)

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

    def store_chunk(self, text: str, metadata: dict = None):
        if self._postgres_backend:
            try:
                meta = {"mode": self.mode, "ts": datetime.now().isoformat()}
                if metadata:
                    meta.update({k: str(v) for k, v in metadata.items()})
                embedding = self._embed_via_ollama(text)
                if not embedding:
                    return
                self._postgres_backend.store_chunk(text, embedding, meta)
            except Exception as exc:
                _warn_pg_fallback(exc)
            return
        if not self._chroma:
            return
        chunk_id  = str(uuid.uuid4())
        meta      = {"mode": self.mode, "ts": datetime.now().isoformat()}
        if metadata:
            meta.update({k: str(v) for k, v in metadata.items()})
        embedding = self._embed_via_ollama(text)
        if not embedding:
            # Never fall back to ChromaDB's built-in ONNX downloader
            return
        try:
            self._chroma.add(
                ids=[chunk_id],
                documents=[text],
                metadatas=[meta],
                embeddings=[embedding],
            )
        except Exception:
            pass

    def recall(self, query: str, n_results: int = None, allowed_modes: list[str] = None):
        n = n_results or MEMORY_RECALL_RESULTS
        if self._postgres_backend:
            try:
                embedding = self._embed_via_ollama(query)
                if embedding:
                    return self._postgres_backend.recall(embedding, n, modes=allowed_modes)
            except Exception as exc:
                _warn_pg_fallback(exc)
            return self._keyword_fallback(query, allowed_modes)
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
        summary = self._summarize_session(session, ollama_client)
        if not summary:
            return

        session_id = None
        if self._postgres_backend:
            # Postgres is the system of record: persist the full session
            # (Tier 1) + messages + summary embedding (Tier 2) in one place,
            # and link the facts written below back to it.
            try:
                embedding = self._embed_via_ollama(summary)
                session_id = self._postgres_backend.persist_session(
                    session, summary, embedding,
                )
            except Exception as exc:
                _warn_pg_fallback(exc)
        else:
            self.store_chunk(
                text=summary,
                metadata={
                    "session_name":  session.get("name", ""),
                    "mode":          session.get("mode", self.mode),
                    "model":         session.get("model", ""),
                    "message_count": str(len(session.get("messages", []))),
                    "created":       session.get("created", ""),
                },
            )

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
        fact_lines = []

        if facts.get("user_name"):
            fact_lines.append(f"User name: {facts['user_name']}")
        if facts.get("preferred_language"):
            fact_lines.append(f"Preferred language: {facts['preferred_language']}")
        if facts.get("preferred_tone"):
            fact_lines.append(f"Preferred tone: {facts['preferred_tone']}")
        if facts.get("primary_language"):
            fact_lines.append(f"Primary coding language: {facts['primary_language']}")
        if facts.get("tech_stack"):
            fact_lines.append(f"Tech stack: {', '.join(facts['tech_stack'][:5])}")
        if facts.get("active_projects"):
            fact_lines.append(f"Active projects: {', '.join(str(p) for p in facts['active_projects'][:3])}")
        if facts.get("known_clients"):
            fact_lines.append(f"Known clients: {', '.join(str(c) for c in facts['known_clients'][:5])}")
        if facts.get("key_projects"):
            fact_lines.append(f"Key projects: {', '.join(str(p) for p in facts['key_projects'][:3])}")
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
                        "=== RELEVANT PAST SESSIONS ===\n"
                        + "\n---\n".join(recall_texts[:3])
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
        }


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
