# Cross-Mode Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect `chat`, `cowork`, and `code` through shared Postgres-backed operational memory while keeping `RevRec` isolated.

**Architecture:** Keep `MemoryManager` as the low-level memory API and add `ModeMemorySession` as the shared workflow helper used by interactive modes. Cross-mode recall is filtered to operational modes only: `chat`, `cowork`, `code`, and `console`; `revrec` remains same-mode only.

**Tech Stack:** Python standard library, `unittest`, existing AXIO `MemoryManager`, Postgres/pgvector backend, PowerShell test commands.

---

## File Structure

- Modify: `axio-console-v2.1/core/memory_backends/postgres_backend.py`
  - Responsibility: Store and recall Postgres memory rows. Add optional allowed-mode filtering to recall.
- Modify: `axio-console-v2.1/core/memory.py`
  - Responsibility: Preserve same-mode memory behavior while exposing optional allowed-mode recall and prefix building.
- Create: `axio-console-v2.1/core/mode_memory.py`
  - Responsibility: Shared mode-facing memory workflow for `chat`, `cowork`, and `code`.
- Modify: `axio-console-v2.1/modes/cowork.py`
  - Responsibility: Inject memory into workspace assistant prompts and persist successful turns.
- Modify: `axio-console-v2.1/modes/code.py`
  - Responsibility: Inject memory into coding tasks and persist compact task summaries.
- Modify: `axio-console-v2.1/modes/chat.py`
  - Responsibility: Use the helper workflow without changing existing chat behavior.
- Modify: `axio-console-v2.1/core/__init__.py`
  - Responsibility: Export `ModeMemorySession`.
- Modify: `axio-console-v2.1/tests/test_postgres_backend_unit.py`
  - Responsibility: Prove Postgres recall supports same-mode and allowed-mode queries.
- Create: `axio-console-v2.1/tests/test_memory_cross_mode.py`
  - Responsibility: Prove `MemoryManager` passes allowed modes into backend recall and excludes `revrec` by default through the helper.
- Create: `axio-console-v2.1/tests/test_mode_memory_session.py`
  - Responsibility: Prove the helper records sessions and handles memory commands.
- Create: `axio-console-v2.1/tests/test_cowork_memory_integration.py`
  - Responsibility: Prove cowork prompt construction includes memory prefix.
- Create: `axio-console-v2.1/tests/test_code_memory_integration.py`
  - Responsibility: Prove code task construction includes memory prefix and final agent text can be stored.

---

### Task 1: Postgres Cross-Mode Recall

**Files:**
- Modify: `axio-console-v2.1/tests/test_postgres_backend_unit.py`
- Modify: `axio-console-v2.1/core/memory_backends/postgres_backend.py`
- Modify: `axio-console-v2.1/core/memory.py`

- [ ] **Step 1: Add failing backend tests for allowed-mode recall**

Append these tests to `PostgresMemoryBackendUnitTests` in `axio-console-v2.1/tests/test_postgres_backend_unit.py`:

```python
    def test_recall_without_modes_filters_to_backend_mode(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("chat", connection_factory=lambda: conn)
        conn.cursor_obj.rows = []

        backend.recall([0.0] * 768, n_results=2)

        sql, params = conn.cursor_obj.calls[-1]
        self.assertIn("WHERE mode = %s", sql)
        self.assertEqual(params[1], "chat")

    def test_recall_with_allowed_modes_filters_to_those_modes(self):
        conn = FakeConnection()
        backend = PostgresMemoryBackend("code", connection_factory=lambda: conn)
        conn.cursor_obj.rows = [
            {"content": "Cowork remembered AXIO", "metadata": {"mode": "cowork"}, "distance": 0.1}
        ]

        rows = backend.recall(
            [0.0] * 768,
            n_results=3,
            modes=["code", "cowork", "chat", "console"],
        )

        sql, params = conn.cursor_obj.calls[-1]
        self.assertIn("WHERE mode = ANY(%s)", sql)
        self.assertEqual(params[1], ["code", "cowork", "chat", "console"])
        self.assertEqual(rows[0]["metadata"]["mode"], "cowork")
```

- [ ] **Step 2: Run backend tests and verify they fail**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_postgres_backend_unit -v
```

Expected: failure because `PostgresMemoryBackend.recall()` does not accept `modes`.

- [ ] **Step 3: Implement allowed-mode recall in Postgres backend**

Replace `PostgresMemoryBackend.recall()` in `axio-console-v2.1/core/memory_backends/postgres_backend.py` with:

```python
    def recall(self, embedding: list[float], n_results: int, modes: list[str] = None):
        if len(embedding) != 768:
            raise ValueError(
                f"Expected embedding dimension 768, got {len(embedding)}"
            )
        if modes:
            sql = """
                SELECT content, metadata, embedding <=> %s::vector AS distance
                FROM memory_embeddings
                WHERE mode = ANY(%s)
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """
            params = (embedding, modes, embedding, n_results)
        else:
            sql = """
                SELECT content, metadata, embedding <=> %s::vector AS distance
                FROM memory_embeddings
                WHERE mode = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """
            params = (embedding, self.mode, embedding, n_results)

        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "text": row["content"],
                "metadata": row["metadata"],
                "distance": row["distance"],
            }
            for row in rows
        ]
```

- [ ] **Step 4: Extend `MemoryManager.recall()` and prefix builder signatures**

In `axio-console-v2.1/core/memory.py`, change:

```python
    def recall(self, query: str, n_results: int = None):
```

to:

```python
    def recall(self, query: str, n_results: int = None, allowed_modes: list[str] = None):
```

Inside the Postgres branch, replace:

```python
                return self._postgres_backend.recall(embedding, n)
```

with:

```python
                return self._postgres_backend.recall(embedding, n, modes=allowed_modes)
```

Change:

```python
    def build_memory_prefix(self, query: str = "") -> str:
```

to:

```python
    def build_memory_prefix(self, query: str = "", allowed_modes: list[str] = None) -> str:
```

Inside `build_memory_prefix`, replace:

```python
            recalls = self.recall(query, n_results=MEMORY_RECALL_RESULTS)
```

with:

```python
            recalls = self.recall(
                query,
                n_results=MEMORY_RECALL_RESULTS,
                allowed_modes=allowed_modes,
            )
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_postgres_backend_unit -v
```

Expected: all tests in `test_postgres_backend_unit` pass.

- [ ] **Step 6: Commit backend recall change**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
git add axio-console-v2.1/core/memory_backends/postgres_backend.py axio-console-v2.1/core/memory.py axio-console-v2.1/tests/test_postgres_backend_unit.py
git commit -m "Add cross-mode memory recall filters"
```

---

### Task 2: Shared Mode Memory Session Helper

**Files:**
- Create: `axio-console-v2.1/tests/test_mode_memory_session.py`
- Create: `axio-console-v2.1/tests/test_memory_cross_mode.py`
- Create: `axio-console-v2.1/core/mode_memory.py`
- Modify: `axio-console-v2.1/core/__init__.py`

- [ ] **Step 1: Write failing helper behavior tests**

Create `axio-console-v2.1/tests/test_mode_memory_session.py`:

```python
import unittest
from unittest.mock import patch

from core.mode_memory import ModeMemorySession, shared_recall_modes


class FakeMemoryManager:
    instances = []

    def __init__(self, mode):
        self.mode = mode
        self.prefix_calls = []
        self.facts_updates = []
        self.chunks = []
        self.stored = []
        self.commands = []
        FakeMemoryManager.instances.append(self)

    def build_memory_prefix(self, query="", allowed_modes=None):
        self.prefix_calls.append((query, allowed_modes))
        return f"[memory:{self.mode}:{query}]"

    def update_facts(self, patch):
        self.facts_updates.append(patch)

    def store_chunk(self, text, metadata=None):
        self.chunks.append((text, metadata or {}))

    def store_session(self, session, ollama_client=None):
        self.stored.append((session, ollama_client))

    def get_facts(self):
        return {"notes": ["stored note"]}

    def stats(self):
        return {"mode": self.mode, "backend": "fake", "chroma_docs": 0, "last_session": "never"}


class ModeMemorySessionTests(unittest.TestCase):
    def setUp(self):
        FakeMemoryManager.instances = []

    def test_shared_recall_modes_excludes_revrec(self):
        self.assertEqual(
            shared_recall_modes("code"),
            ["code", "console", "chat", "cowork"],
        )
        self.assertEqual(shared_recall_modes("revrec"), ["revrec"])

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_prefix_uses_allowed_recall_modes(self):
        session = ModeMemorySession("cowork")

        prefix = session.prefix("AXIO Docker Memory")

        self.assertEqual(prefix, "[memory:cowork:AXIO Docker Memory]")
        self.assertEqual(
            session.memory.prefix_calls[0][1],
            ["cowork", "console", "chat", "code"],
        )

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_record_turn_builds_session_messages(self):
        session = ModeMemorySession("code")

        session.record_turn("fix bug", "fixed", model="qwen3-coder", metadata={"route": "local"})

        self.assertEqual(len(session.session["messages"]), 2)
        self.assertEqual(session.session["messages"][0]["role"], "user")
        self.assertEqual(session.session["messages"][1]["role"], "assistant")
        self.assertEqual(session.session["model"], "qwen3-coder")
        self.assertEqual(session.turn_metadata[0]["route"], "local")

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_record_private_writes_current_mode_chunk(self):
        session = ModeMemorySession("chat")

        session.record_private("Private project fact")

        self.assertEqual(session.memory.chunks[0][0], "Private project fact")
        self.assertEqual(session.memory.chunks[0][1]["source_type"], "manual_private")

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_record_global_writes_console_chunk(self):
        session = ModeMemorySession("chat")

        session.record_global("Global project fact")

        console = FakeMemoryManager.instances[-1]
        self.assertEqual(console.mode, "console")
        self.assertEqual(console.chunks[0][0], "Global project fact")
        self.assertEqual(console.chunks[0][1]["source_type"], "manual_global")

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_store_delegates_non_empty_session(self):
        session = ModeMemorySession("code")
        ollama = object()
        session.record_turn("task", "result")

        session.store(ollama_client=ollama)

        self.assertEqual(session.memory.stored[0][0]["mode"], "code")
        self.assertIs(session.memory.stored[0][1], ollama)

    @patch("core.mode_memory.MemoryManager", FakeMemoryManager)
    def test_handle_command_private_and_share(self):
        session = ModeMemorySession("cowork")

        self.assertTrue(session.handle_command("memory private keep this in cowork"))
        self.assertTrue(session.handle_command("memory share keep this global"))

        self.assertEqual(session.memory.chunks[0][0], "keep this in cowork")
        console = FakeMemoryManager.instances[-1]
        self.assertEqual(console.mode, "console")
        self.assertEqual(console.chunks[0][0], "keep this global")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Write failing cross-mode tests**

Create `axio-console-v2.1/tests/test_memory_cross_mode.py`:

```python
import unittest
from unittest.mock import patch

from core.memory import MemoryManager


class FakePostgresBackend:
    def __init__(self):
        self.recall_calls = []

    def get_facts(self):
        return {}

    def recall(self, embedding, n_results, modes=None):
        self.recall_calls.append((embedding, n_results, modes))
        return [{"text": "cross-mode hit", "metadata": {"mode": "cowork"}, "distance": 0.1}]


class MemoryCrossModeTests(unittest.TestCase):
    def test_memory_manager_passes_allowed_modes_to_postgres_backend(self):
        mem = MemoryManager("code")
        backend = FakePostgresBackend()
        mem._postgres_backend = backend

        with patch.object(mem, "_embed_via_ollama", return_value=[0.0] * 768):
            rows = mem.recall(
                "AXIO Docker Memory",
                n_results=4,
                allowed_modes=["code", "cowork", "chat", "console"],
            )

        self.assertEqual(rows[0]["text"], "cross-mode hit")
        self.assertEqual(
            backend.recall_calls[0][2],
            ["code", "cowork", "chat", "console"],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run helper tests and verify they fail**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_mode_memory_session tests.test_memory_cross_mode -v
```

Expected: import failure because `core.mode_memory` does not exist.

- [ ] **Step 4: Implement `core/mode_memory.py`**

Create `axio-console-v2.1/core/mode_memory.py`:

```python
from __future__ import annotations

from datetime import datetime

from core.memory import MemoryManager, _handle_memory_cmd


SHARED_MEMORY_MODES = ("chat", "cowork", "code", "console")


def shared_recall_modes(mode: str) -> list[str]:
    if mode not in SHARED_MEMORY_MODES:
        return [mode]
    modes = [mode, "console"]
    for candidate in ("chat", "cowork", "code"):
        if candidate != mode:
            modes.append(candidate)
    return modes


class ModeMemorySession:
    def __init__(self, mode: str, allowed_recall_modes: list[str] = None):
        self.mode = mode
        self.memory = MemoryManager(mode)
        self.allowed_recall_modes = allowed_recall_modes or shared_recall_modes(mode)
        now = datetime.now().isoformat()
        self.session = {
            "name": f"{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "mode": mode,
            "model": "",
            "created": now,
            "updated": now,
            "messages": [],
        }
        self.turn_metadata = []

    def prefix(self, query: str = "") -> str:
        return self.memory.build_memory_prefix(
            query,
            allowed_modes=self.allowed_recall_modes,
        )

    def record_turn(
        self,
        user_text: str,
        assistant_text: str,
        model: str = "",
        metadata: dict = None,
    ):
        now = datetime.now().isoformat()
        if model:
            self.session["model"] = model
        self.session["updated"] = now
        self.session["messages"].append({"role": "user", "content": user_text})
        self.session["messages"].append({"role": "assistant", "content": assistant_text})
        self.turn_metadata.append(dict(metadata or {}))
        self.memory.auto_update_facts(user_text, assistant_text)

    def record_private(self, text: str, metadata: dict = None):
        meta = {"source_type": "manual_private", "mode": self.mode}
        if metadata:
            meta.update(metadata)
        self.memory.store_chunk(text, meta)
        self.memory.update_facts({"notes": [text[:300]]})

    def record_global(self, text: str, metadata: dict = None):
        meta = {"source_type": "manual_global", "mode": "console", "origin_mode": self.mode}
        if metadata:
            meta.update(metadata)
        console = MemoryManager("console")
        console.store_chunk(text, meta)
        console.update_facts({"notes": [text[:300]], "last_updated": datetime.now().isoformat()})

    def store(self, ollama_client=None):
        if self.session["messages"]:
            self.memory.store_session(self.session, ollama_client=ollama_client)

    def handle_command(self, command: str) -> bool:
        lower = command.lower().strip()
        if lower == "memory" or lower.startswith("memory set "):
            _handle_memory_cmd(command, self.memory)
            return True
        if lower == "memory global":
            _handle_memory_cmd("memory", MemoryManager("console"))
            return True
        if lower.startswith("memory share "):
            self.record_global(command[len("memory share "):].strip())
            print("  Memory shared globally.\n")
            return True
        if lower.startswith("memory private "):
            self.record_private(command[len("memory private "):].strip())
            print("  Memory saved privately.\n")
            return True
        if lower.startswith("memory recall "):
            query = command[len("memory recall "):].strip()
            hits = self.memory.recall(query, allowed_modes=self.allowed_recall_modes)
            if not hits:
                print("  No memory hits.\n")
                return True
            print("\n  Memory recall results:")
            for hit in hits:
                meta = hit.get("metadata") or {}
                mode = meta.get("mode", "unknown")
                text = str(hit.get("text", "")).replace("\n", " ")[:240]
                print(f"    [{mode}] {text}")
            print()
            return True
        return False
```

- [ ] **Step 5: Export helper**

In `axio-console-v2.1/core/__init__.py`, add:

```python
from .mode_memory import ModeMemorySession, shared_recall_modes  # noqa: F401
```

- [ ] **Step 6: Run helper tests**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_mode_memory_session tests.test_memory_cross_mode -v
```

Expected: all helper and cross-mode tests pass.

- [ ] **Step 7: Commit helper**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
git add axio-console-v2.1/core/mode_memory.py axio-console-v2.1/core/__init__.py axio-console-v2.1/tests/test_mode_memory_session.py axio-console-v2.1/tests/test_memory_cross_mode.py
git commit -m "Add shared mode memory session helper"
```

---

### Task 3: Cowork Memory Integration

**Files:**
- Create: `axio-console-v2.1/tests/test_cowork_memory_integration.py`
- Modify: `axio-console-v2.1/modes/cowork.py`

- [ ] **Step 1: Add prompt builder test for cowork memory injection**

Create `axio-console-v2.1/tests/test_cowork_memory_integration.py`:

```python
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
```

- [ ] **Step 2: Run cowork test and verify it fails**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_cowork_memory_integration -v
```

Expected: import failure because `build_cowork_prompt` does not exist.

- [ ] **Step 3: Add cowork prompt builder**

In `axio-console-v2.1/modes/cowork.py`, after `HELP`, add:

```python
def build_cowork_prompt(user_prompt: str, workspace_context: str = "", memory_prefix: str = "") -> str:
    parts = []
    if memory_prefix:
        parts.append(memory_prefix.strip())
    if workspace_context:
        parts.append(workspace_context.strip())
    if parts:
        parts.append(f"User: {user_prompt}")
        return "\n\n".join(parts)
    return user_prompt
```

- [ ] **Step 4: Wire cowork to `ModeMemorySession`**

In `axio-console-v2.1/modes/cowork.py`, add import:

```python
from core.mode_memory import ModeMemorySession
```

Inside `run()`, after `logger = AuditLogger("cowork")`, add:

```python
    memory = ModeMemorySession("cowork")
```

In the input exception handler and `exit` branch, call:

```python
            memory.store(ollama_client=ollama)
```

Before command routing after `lower = prompt.lower()`, add:

```python
        if memory.handle_command(prompt):
            continue
```

In the model call branch, replace:

```python
            context       = ws.context_block()
            full_prompt   = f"{context}\n\nUser: {prompt}" if context else prompt
```

with:

```python
            context = ws.context_block()
            memory_query = f"{prompt}\nWorkspace: {ws.root}" if ws.root else prompt
            memory_prefix = memory.prefix(memory_query)
            full_prompt = build_cowork_prompt(prompt, context, memory_prefix)
```

After `logger.log_turn(...)`, add:

```python
            memory.record_turn(
                prompt,
                result_text,
                model=picked,
                metadata={
                    "route": route,
                    "workspace": str(ws.root) if ws.root else "",
                    "loaded_files": ",".join(ws.loaded_files.keys()),
                },
            )
```

When the `workspace <path>` command succeeds, update facts:

```python
            if ws.root:
                memory.memory.update_facts({"workspace_paths": [str(ws.root)]})
```

- [ ] **Step 5: Run cowork integration test**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_cowork_memory_integration -v
```

Expected: all cowork memory tests pass.

- [ ] **Step 6: Commit cowork integration**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
git add axio-console-v2.1/modes/cowork.py axio-console-v2.1/tests/test_cowork_memory_integration.py
git commit -m "Integrate cowork with shared memory"
```

---

### Task 4: Code Memory Integration

**Files:**
- Create: `axio-console-v2.1/tests/test_code_memory_integration.py`
- Modify: `axio-console-v2.1/modes/code.py`

- [ ] **Step 1: Add tests for code memory task building**

Create `axio-console-v2.1/tests/test_code_memory_integration.py`:

```python
import unittest

from modes.code import build_code_task


class CodeMemoryIntegrationTests(unittest.TestCase):
    def test_build_code_task_injects_memory_before_task(self):
        result = build_code_task(
            task="Add tests",
            file_context="Loaded files:\nmain.py",
            memory_prefix="[AXIO MEMORY]\nRepo: AXIO Cortex\n[END MEMORY]",
        )

        self.assertTrue(result.startswith("[AXIO MEMORY]"))
        self.assertIn("Loaded files:\nmain.py", result)
        self.assertTrue(result.rstrip().endswith("Add tests"))

    def test_build_code_task_without_memory_keeps_task(self):
        result = build_code_task(task="Run tests", file_context="", memory_prefix="")

        self.assertEqual(result, "Run tests")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run code integration test and verify it fails**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_code_memory_integration -v
```

Expected: import failure because `build_code_task` does not exist.

- [ ] **Step 3: Add code task builder**

In `axio-console-v2.1/modes/code.py`, after `SYSTEM_PROMPT`, add:

```python
def build_code_task(task: str, file_context: str = "", memory_prefix: str = "") -> str:
    parts = []
    if memory_prefix:
        parts.append(memory_prefix.strip())
    if file_context:
        parts.append(file_context.strip())
    if parts:
        parts.append(task)
        return "\n\n".join(parts)
    return task
```

- [ ] **Step 4: Return final text from agent loops**

In `_run_ollama_agent`, replace the bare `return` after successful final response with:

```python
            return content
```

Replace error and max-iteration bare returns with strings:

```python
            return f"Error: {e}"
```

and:

```python
    return f"Agent stopped: reached max {MAX_ITERS} steps"
```

In `_run_claude_agent`, replace successful final response bare `return` with:

```python
            return final_text
```

Replace Claude error and max-iteration returns with strings:

```python
            return f"Claude error: {e}"
```

and:

```python
    return f"Stopped at max {MAX_ITERS} steps"
```

- [ ] **Step 5: Wire code to `ModeMemorySession`**

In `axio-console-v2.1/modes/code.py`, add import:

```python
from core.mode_memory import ModeMemorySession
```

Inside `run()`, after `logger = AuditLogger("code")`, add:

```python
    memory = ModeMemorySession("code")
```

In the input exception handler and `exit` branch, call:

```python
            memory.store(ollama_client=ollama)
```

After `lower = task.lower()`, add:

```python
        if memory.handle_command(task):
            continue
```

In the agent task branch, replace:

```python
            final_task = SESSION_CONTEXT.inject(task, mode="list") if SESSION_CONTEXT.count else task
```

with:

```python
            file_context = SESSION_CONTEXT.inject("", mode="list") if SESSION_CONTEXT.count else ""
            memory_prefix = memory.prefix(task)
            final_task = build_code_task(task, file_context, memory_prefix)
```

Capture the agent result:

```python
                result_text = _run_claude_agent(final_task, claude, logger)
```

and:

```python
                result_text = _run_ollama_agent(final_task, model, ollama, logger)
```

After the selected agent returns, add:

```python
            if result_text:
                memory.record_turn(
                    task,
                    result_text,
                    model=CLAUDE_MODEL if use_claude and claude_ok else model,
                    metadata={
                        "backend": "claude" if use_claude and claude_ok else "ollama",
                        "file_context_count": str(SESSION_CONTEXT.count),
                    },
                )
```

- [ ] **Step 6: Run code integration test**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_code_memory_integration -v
```

Expected: all code integration tests pass.

- [ ] **Step 7: Commit code integration**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
git add axio-console-v2.1/modes/code.py axio-console-v2.1/tests/test_code_memory_integration.py
git commit -m "Integrate code mode with shared memory"
```

---

### Task 5: Chat Helper Normalization

**Files:**
- Modify: `axio-console-v2.1/tests/test_chat_memory_persistence.py`
- Modify: `axio-console-v2.1/modes/chat.py`

- [ ] **Step 1: Preserve existing chat persistence tests**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_chat_memory_persistence -v
```

Expected: current tests pass before refactor.

- [ ] **Step 2: Add a helper-compatible save function**

In `axio-console-v2.1/modes/chat.py`, keep `_save_and_store_memory()` for existing tests and add:

```python
def _store_chat_memory(sm: SessionManager, memory_session, legacy_session: dict, ollama):
    sm.save(legacy_session)
    memory_session.store(ollama_client=ollama)
```

- [ ] **Step 3: Import and initialize `ModeMemorySession`**

In `axio-console-v2.1/modes/chat.py`, add import:

```python
from core.mode_memory import ModeMemorySession
```

Inside `run()`, after the existing `mem = MemoryManager("chat")`, add:

```python
    memory = ModeMemorySession("chat")
```

Keep `mem` until the end of this task to reduce regression risk.

- [ ] **Step 4: Use helper for prefix and commands**

Replace:

```python
            memory_prefix = mem.build_memory_prefix(prompt)
```

with:

```python
            memory_prefix = memory.prefix(prompt)
```

Before the old memory command handling branch, add:

```python
            if memory.handle_command(prompt.lstrip("/")):
                continue
```

After successful response, add:

```python
            memory.record_turn(prompt, response, model=model, metadata={"backend": backend})
```

Keep the existing legacy `session["messages"].append(...)` calls so session JSON behavior remains unchanged. Remove the existing `mem.auto_update_facts(prompt, response)` call because `memory.record_turn(...)` updates facts through the helper.

- [ ] **Step 5: Store helper session on save and exit**

Where `_save_and_store_memory(sm, mem, session, ollama)` is called on exit, `/save`, `/new`, `/load`, Ctrl+C, or EOF, call:

```python
            memory.store(ollama_client=ollama)
```

Keep the legacy save function call so existing session JSON behavior remains unchanged.

- [ ] **Step 6: Run chat tests**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_chat_memory_persistence tests.test_chat_model_selection -v
```

Expected: all chat tests pass.

- [ ] **Step 7: Commit chat normalization**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
git add axio-console-v2.1/modes/chat.py axio-console-v2.1/tests/test_chat_memory_persistence.py
git commit -m "Normalize chat memory workflow"
```

---

### Task 6: RevRec Isolation And Full Verification

**Files:**
- Create or modify: `axio-console-v2.1/tests/test_memory_cross_mode.py`
- Read-only verification: `axio-console-v2.1/modes/revrec.py`

- [ ] **Step 1: Add RevRec isolation assertion**

In `axio-console-v2.1/tests/test_memory_cross_mode.py`, add:

```python
from core.mode_memory import shared_recall_modes
```

Add this test:

```python
    def test_revrec_is_not_in_default_shared_recall_modes(self):
        for mode in ("chat", "cowork", "code"):
            self.assertNotIn("revrec", shared_recall_modes(mode))
        self.assertEqual(shared_recall_modes("revrec"), ["revrec"])
```

- [ ] **Step 2: Run isolation tests**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest tests.test_memory_cross_mode -v
```

Expected: all isolation tests pass.

- [ ] **Step 3: Run full unit suite**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest discover tests -v
```

Expected: all tests pass.

- [ ] **Step 4: Run local Postgres smoke check**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
docker compose ps
docker compose exec axio-postgres psql -U axio -d axio_cortex -c "select mode, source_type, left(content, 120) as preview, created_at from memory_embeddings order by created_at desc limit 10;"
```

Expected:

```text
axio-cortex-postgres   pgvector/pgvector:pg16   ...   Up ... (healthy)   127.0.0.1:5432->5432/tcp
```

The query should return existing memory rows. Exact row count can vary by local usage.

- [ ] **Step 5: Optional manual live check**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
$env:AXIO_MEMORY_BACKEND="postgres"
py axio.py cowork
```

Inside Cowork:

```text
memory share AXIO shared memory manual smoke test
memory recall AXIO shared memory
exit
```

Then run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
docker compose exec axio-postgres psql -U axio -d axio_cortex -c "select mode, source_type, left(content, 120) as preview from memory_embeddings where mode in ('console','cowork') order by created_at desc limit 5;"
```

Expected: at least one `console` or `cowork` row referencing the smoke test.

- [ ] **Step 6: Commit verification tests**

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
git add axio-console-v2.1/tests/test_memory_cross_mode.py
git commit -m "Verify RevRec memory isolation"
```

---

## Final Acceptance

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest discover tests -v
```

Expected: all unit tests pass.

Run:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
git status --short --branch
```

Expected:

```text
## codex/docker-live-database...origin/codex/docker-live-database [ahead ...]
```

No unstaged or staged files should remain.
