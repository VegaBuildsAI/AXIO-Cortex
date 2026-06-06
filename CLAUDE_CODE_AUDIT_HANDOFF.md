# Claude Code Audit Handoff: AXIO Cortex Live Memory

Purpose: give Claude Code enough context to audit the current implementation without loading the whole repo or burning tokens. Start here, then inspect only the referenced files.

## Executive Summary

AXIO started as `AXIO Console`: a local multi-mode AI console with `chat`, `cowork`, `code`, and `RevRec` modes. The current goal is `AXIO Cortex`: a local-first AI system with live, persistent memory backed by Docker Postgres + pgvector, where operational modes can learn from prior work and reuse relevant context.

Codex implemented the first live-memory foundation:

- Docker Postgres + pgvector local database.
- Postgres schema for sessions, messages, facts, embeddings, logs, benchmarks, and model scores.
- Optional Postgres memory backend selected by `AXIO_MEMORY_BACKEND=postgres`.
- Migration from local JSON memory files into Postgres.
- Chat memory persistence and model-selection fix.
- Shared memory layer for `chat`, `cowork`, and `code`.
- `RevRec` intentionally isolated as a specialized revenue-recognition agent.

Audit objective: verify whether the code, files, tests, and logic correctly support the long-term goal of **living memory for AXIO Cortex** while preserving local-first safety and avoiding memory contamination between unrelated agent domains.

## Token-Efficient Read Order

Do not read the whole repo first. Use this order.

1. Read this file.
2. Inspect primary implementation files only:
   - `docker-compose.yml`
   - `docker/postgres/init/001_schema.sql`
   - `docker/postgres/init/002_indexes.sql`
   - `axio-console-v2.1/core/config.py`
   - `axio-console-v2.1/core/db.py`
   - `axio-console-v2.1/core/memory.py`
   - `axio-console-v2.1/core/memory_backends/postgres_backend.py`
   - `axio-console-v2.1/core/mode_memory.py`
3. Inspect mode integrations:
   - `axio-console-v2.1/modes/chat.py`
   - `axio-console-v2.1/modes/cowork.py`
   - `axio-console-v2.1/modes/code.py`
   - `axio-console-v2.1/modes/revrec.py`
4. Inspect tests only if needed to confirm behavior:
   - `axio-console-v2.1/tests/test_postgres_backend_unit.py`
   - `axio-console-v2.1/tests/test_memory_cross_mode.py`
   - `axio-console-v2.1/tests/test_mode_memory_session.py`
   - `axio-console-v2.1/tests/test_chat_memory_persistence.py`
   - `axio-console-v2.1/tests/test_chat_model_selection.py`
   - `axio-console-v2.1/tests/test_cowork_memory_integration.py`
   - `axio-console-v2.1/tests/test_code_memory_integration.py`
5. Read specs/plans only for intent clarification:
   - `docs/superpowers/specs/2026-06-05-docker-live-database-design.md`
   - `docs/superpowers/specs/2026-06-05-cross-mode-memory-design.md`
   - `docs/superpowers/plans/2026-06-05-docker-live-database-implementation.md`
   - `docs/superpowers/plans/2026-06-05-cross-mode-memory.md`

## Fast Symbol Map

Use `rg` before opening large files.

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
rg -n "AXIO_MEMORY_BACKEND|AXIO_DB_|MEMORY_EMBED_MODEL|MEMORY_SUMMARY_MODEL" axio-console-v2.1
rg -n "class MemoryManager|def recall|def store_session|def build_memory_prefix|def auto_update_facts" axio-console-v2.1/core/memory.py
rg -n "class PostgresMemoryBackend|def recall|def store_chunk|def update_facts|get_facts" axio-console-v2.1/core/memory_backends/postgres_backend.py
rg -n "class ModeMemorySession|shared_recall_modes|record_global|record_private|handle_command" axio-console-v2.1/core/mode_memory.py
rg -n "ModeMemorySession|build_.*prompt|build_code_task|memory.record_turn|memory.prefix|memory.store" axio-console-v2.1/modes
```

## Implementation Timeline

Relevant commits on `main`:

```text
fd0330d Add Postgres memory configuration
a0365d8 Add Docker Postgres schema
d0ded61 Add Postgres memory backend
086c860 Select Postgres memory backend
0ccc854 Add Postgres memory migration script
ae5bd8b Document Docker live database usage
30e3ac1 Fix chat default model selection
21ff0da Persist chat sessions to memory backend
a4ffb11 Design cross-mode memory integration
b25bca6 Plan cross-mode memory integration
dd38760 Add cross-mode memory recall filters
53b7b06 Add shared mode memory session helper
a4f14c5 Integrate cowork with shared memory
d25c6a8 Integrate code mode with shared memory
cdd9757 Normalize chat memory workflow
900e0f8 Verify RevRec memory isolation
```

## Current Architecture

### Storage

Local Docker service:

- Compose service: `axio-postgres`
- Container: `axio-cortex-postgres`
- Image: `pgvector/pgvector:pg16`
- Local bind: `127.0.0.1:5432`
- Database: `axio_cortex`
- User: `axio`

Tables:

- `sessions`
- `messages`
- `memory_facts`
- `memory_embeddings`
- `audit_logs`
- `benchmark_runs`
- `model_scores`

Key design point: this is local-first. LAN exposure was discussed as a later option, but current binding remains localhost.

### Memory Layers

Low-level API:

- `MemoryManager` in `axio-console-v2.1/core/memory.py`
- Backend selector uses `AXIO_MEMORY_BACKEND`
- JSON remains default; Postgres activates with `AXIO_MEMORY_BACKEND=postgres`

Postgres backend:

- `PostgresMemoryBackend` in `axio-console-v2.1/core/memory_backends/postgres_backend.py`
- Stores structured facts in `memory_facts`
- Stores embeddings in `memory_embeddings`
- Supports same-mode recall and allowed-mode cross recall

Mode-facing helper:

- `ModeMemorySession` in `axio-console-v2.1/core/mode_memory.py`
- Wraps `MemoryManager`
- Owns per-mode session messages
- Builds memory prefixes
- Handles `memory`, `memory global`, `memory recall`, `memory share`, `memory private`

### Cross-Mode Boundary

Shared operational modes:

```text
chat
cowork
code
console
```

Isolated mode:

```text
revrec
```

Expected rule:

- `chat`, `cowork`, and `code` can recall from each other and `console`.
- `RevRec` recalls only from `revrec` by default.
- `RevRec` should not appear in default shared recall modes.

Relevant function:

```text
shared_recall_modes(mode)
```

## Mode Behavior To Audit

### Chat

File:

```text
axio-console-v2.1/modes/chat.py
```

Expected:

- Uses `ModeMemorySession("chat")`.
- Keeps legacy session save behavior.
- Uses `memory.prefix(prompt)` before model call.
- Uses `memory.record_turn(...)` after successful response.
- Supports `/memory` through the shared helper.
- Fixes default model selection so embedding models like `nomic-embed-text` are not used as chat models.

Audit risks:

- Duplicate or missing session summaries.
- `/load` ambiguity between loading saved sessions and loading file context.
- Memory command interception before slash command parsing.
- Legacy `MemoryManager("chat")` still present for backward compatibility; verify it is not causing double writes.

### Cowork

File:

```text
axio-console-v2.1/modes/cowork.py
```

Expected:

- Uses `ModeMemorySession("cowork")`.
- Builds prompt with memory prefix, workspace context, then user prompt.
- Persists memory on `exit`, Ctrl+C, or EOF.
- Records successful model responses.
- Updates `workspace_paths` when workspace changes.

Audit risks:

- Workspace context plus memory prefix could create oversized prompts.
- `memory.handle_command(prompt)` intercepts raw text commands; verify this is acceptable.
- Facts may store local absolute paths; confirm this matches local-first design.

### Code

File:

```text
axio-console-v2.1/modes/code.py
```

Expected:

- Uses `ModeMemorySession("code")`.
- Builds task with memory prefix, loaded file list, then user task.
- Agent loops return final text or error string so tasks can be stored.
- Records successful task summaries, not raw tool logs.
- Stores memory on `exit`, Ctrl+C, or EOF.

Audit risks:

- Error strings may be stored as memory. Decide if this is useful or noisy.
- `SESSION_CONTEXT.inject("", mode="list")` may produce awkward text. Verify output is acceptable.
- Tool logs are still written to `AuditLogger`; ensure long-term memory only stores compact final result.

### RevRec

File:

```text
axio-console-v2.1/modes/revrec.py
```

Expected:

- Keeps `MemoryManager("revrec")`.
- Injects RevRec-specific memory into `rev_agent.SYSTEM_PROMPT`.
- Keeps its own memory namespace.
- Is excluded from `chat`/`cowork`/`code` automatic recall.

Audit risks:

- RevRec still updates `console` indirectly through `MemoryManager.store_session()` unless changed later. Decide whether this violates the desired isolation or is acceptable as high-level global summary.

## Commands For Verification

Run from PowerShell.

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
docker compose ps
```

Expected: `axio-cortex-postgres` is healthy.

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1"
py -m unittest discover tests -v
```

Expected at time of handoff: `28` tests pass.

If `py` is unavailable in Claude Code, use the local Python executable available in that environment. Do not change app code just to satisfy a missing shell alias.

Database inspection:

```powershell
cd "C:\Users\AXIO\AXIO Model Improvement"
docker compose exec axio-postgres psql -U axio -d axio_cortex -c "\dt"
docker compose exec axio-postgres psql -U axio -d axio_cortex -c "select mode, key, updated_at from memory_facts order by updated_at desc limit 20;"
docker compose exec axio-postgres psql -U axio -d axio_cortex -c "select mode, source_type, left(content, 160) as preview, created_at from memory_embeddings order by created_at desc limit 20;"
```

## Audit Checklist

Use this checklist instead of reading randomly.

### Correctness

- Does `AXIO_MEMORY_BACKEND=postgres` correctly switch from JSON to Postgres?
- Does JSON remain the default when env var is missing?
- Does cross-mode recall filter to allowed modes?
- Is `revrec` excluded from default shared recall?
- Are session summaries stored only when there are messages?
- Are facts merged correctly for lists and dicts?
- Does hard-coded embedding dimension `768` match `nomic-embed-text` and current schema?

### Architecture

- Is `ModeMemorySession` the right abstraction boundary?
- Is `MemoryManager` still low-level and reusable?
- Is `console` global memory used narrowly enough?
- Is the `chat` legacy memory path now redundant or still needed?
- Is there a better way to avoid duplicated session state between `SessionManager` and `ModeMemorySession`?

### Security And Privacy

- Are DB credentials only local-dev defaults?
- Is Docker bound only to `127.0.0.1`?
- Are local paths stored intentionally and safely?
- Could sensitive contract, code, or user data be promoted to `console` unexpectedly?
- Should `memory share` require explicit confirmation in high-risk modes?

### Prompt Quality

- Can memory prefixes become too long?
- Are recalled summaries clearly marked as memory context?
- Can unrelated operational memories contaminate answers?
- Is RevRec isolation strong enough?

### Failure Modes

- What happens if Postgres is down but `AXIO_MEMORY_BACKEND=postgres`?
- What happens if Ollama embeddings are unavailable?
- Does fallback behavior remain useful?
- Are exceptions swallowed too broadly in memory paths?

### Tests

- Do tests prove cross-mode filtering?
- Do tests prove mode prompt injection?
- Do tests prove actual DB integration, or only unit behavior?
- What integration tests are missing for live Postgres?

## Known Design Tradeoffs

- Postgres backend is optional, not mandatory. This preserves local JSON fallback.
- `RevRec` isolation is implemented at default recall-mode selection, not as a database-level security policy.
- Embedding dimension is fixed at `768`.
- `ModeMemorySession` stores summaries through `MemoryManager.store_session()`, which may also update `console`.
- Current tests are mostly unit tests. Live DB behavior was manually smoke-tested.

## Suggested Audit Output Format

Return findings first, ordered by severity:

```text
P0 Critical
- file:line - issue, impact, recommended fix

P1 High
- file:line - issue, impact, recommended fix

P2 Medium
- file:line - issue, impact, recommended fix

P3 Low
- file:line - issue, impact, recommended fix

Architecture Notes
- concise notes

Missing Tests
- concise list

Verdict
- Ready / Not ready for AXIO Cortex live-memory baseline
```

Do not rewrite the implementation during the first pass. Audit first. Suggest fixes with exact file references.

## Minimal Claude Code Prompt

Use this prompt to start the audit:

```text
Read CLAUDE_CODE_AUDIT_HANDOFF.md first. Audit the AXIO Cortex live-memory implementation against the goal of evolving AXIO Console into AXIO Cortex with local-first living memory. Follow the token-efficient read order. Do not read the whole repo. Produce findings by severity with file:line references, architecture notes, missing tests, and a verdict. Do not modify code in the first pass.
```

