<div align="center">

# AXIO Cortex

**A local-first, multi-model AI console with persistent "Cortex" memory, a 42-tool agentic coding harness, and optional Claude escalation.**

Chat · Cowork · Code · RevRec — one console, one cumulative memory.

</div>

---

## What it is

AXIO Cortex is a personal AI operating console that runs on your own machine. It mirrors the Claude product surfaces — **Chat, Cowork, and Code** — plus a **RevRec** finance specialist, all sharing a single **persistent memory brain**. Local [Ollama](https://ollama.com) models (`gemma4:12b`) handle everyday work; the **Anthropic Claude API** is used as a premium boost for agentic coding and hard reasoning.

It is built around **IOAF** (Intelligent Orchestrated Agent Framework): a three-tier memory architecture that makes sessions **stateful and cumulative** — the console recalls prior conversations, facts, and semantic context across every mode, so it gets more useful the more you use it.

> Design principle: most AI tools are stateless and start cold every session. AXIO Cortex is the opposite — memory is durable, local-first, and shared across modes.

---

## The four modes

| Mode | Backend | Default model | What it does |
|------|---------|---------------|--------------|
| **Chat** | local Ollama | `gemma4:12b` | Fast conversation with session memory; auto **web-augmentation** for current-info questions |
| **Cowork** | local Ollama (premium → Claude) | `gemma4:12b` | File-/workspace-aware assistant with smart routing; web-augmentation |
| **Code** | **Claude API** | `claude-sonnet-4-6` (Opus available) | Unified **42-tool** agentic coding harness (see below) |
| **RevRec** | local + boost | `gemma4:12b`, complex → Claude | ASC 606 / IFRS 15 revenue-recognition specialist (isolated memory) |

`LOCAL_ONLY=1` runs everything on-device; `py axio.py --claude <mode>` forces the Claude path.

---

## Memory — the Cortex (IOAF three tiers)

Every mode reads and writes one memory layer (`core/memory.py`). Chat, Cowork, and Code **share** recall (and a cross-mode `console` master profile injected into each turn); RevRec is **isolated**.

| Tier | What it holds | Where it lives |
|------|---------------|----------------|
| **Tier 1 — short-term** | Raw session history (persist-*before*-inference) | crash-safe journals `~/.axio/journals/` + Postgres `sessions`/`messages` |
| **Tier 2 — semantic (RAG)** | Embedded chunks: session summaries, seed docs, the Obsidian *Second Brain*, self-learned lessons | **Postgres/pgvector** (primary) + **Chroma** mirror `~/.axio/chroma-resilient/` |
| **Tier 3 — long-term facts** | Structured per-mode key-value facts + deterministic `console.global_profile` | Postgres `memory_facts` + atomic JSON mirror `~/.axio/memory/` |

**Embeddings:** `nomic-embed-text` (768-dim, fixed — the vector store asserts the dimension).

**Resilience & self-memory:**
- **Resilient Cortex** — Postgres is the system-of-record; every write is mirrored locally with a durable **outbox** and **idempotent replay**, and dead-letters after repeated failure, so a database outage never loses data.
- **Continuous Self-Memory** (`core/self_memory.py`) — a bounded, local-only RAG loop that distills lessons from the console's own sessions (dedup / reinforce / promote / decay / contradiction / compaction). It is **not** weight training — no fine-tuning, no GPU.
- **Background runtime** (`core/memory_runtime.py`) + Windows scheduled tasks: startup load, periodic sync, nightly consolidation, and `pg_dump` backups (single-writer, lock-guarded).

Backend is selected by `AXIO_MEMORY_BACKEND` (`json` fallback by default; set `postgres` for the live Cortex). Full internals: [`axio-console-v2.1/docs/CORTEX.md`](axio-console-v2.1/docs/CORTEX.md).

---

## The Code harness — 42 tools, gated and verified

Code mode is a full agentic harness (`axio-console-v2.1/core/code_tools/`). It exposes a **single registry of 42 tools**, each with a **risk level** and an **approval gate**, a **read-only Plan Mode**, a **verification gate** that blocks completion until checks pass, a **web-evidence gate**, and a **dynamic tool router**.

**Tools by category** (`len(CODE_TOOL_REGISTRY.tools) == 42`):

| Category | Tools |
|----------|-------|
| Filesystem (9) | `read_file` `write_file` `edit_file` `apply_patch` `list_dir` `create_dir` `delete_file` `search_files` `grep_files` |
| Python (2) | `inspect_python_environment` `run_python` |
| Node (2) | `inspect_node_environment` `run_npm_script` |
| Git — read (2) | `git_status` `git_diff` |
| GitHub / git-write (9) | `github_status` `github_pr_list` `github_pr_view` `git_branch` `git_commit` `github_push` `github_fork` `github_pr_create` `github_pr_merge` |
| Document (1) | `read_docx` |
| Artifacts (4) | `create_docx` `create_xlsx` `create_pptx` `create_pdf` |
| Web (3) | `web_search` `web_fetch` `web_extract` |
| Browser (3) | `browser_open` `browser_snapshot` `browser_click` |
| Retrieval (3) | `index_workspace` `semantic_search` `search_docs` |
| Scaffold (2) | `scaffold_project` `scaffold_module` |
| Shell + gate (2) | `run_command` · `verification_gate` |

**Harness guarantees:**
- **Risk & approval gate** (`registry.py`) — `read`/`index` run freely; `write` prompts only outside the workspace; `execute`/`destructive`/`external` (shell, push, fork, PR-create/merge) **always require human approval**.
- **Verification gate** — after any mutation the agent must run a real check (tests/build/run) and call `verification_gate`; `TASK_COMPLETE` is blocked until it passes. No "read-back = success."
- **Web-evidence gate** (`core/web_intent.py`) — current-information requests must actually use the web tools (search → fetch → extract → cite) before completing; "no web" opts out with an unverified label. The same detector powers Chat/Cowork web-augmentation.
- **Tool router** (`CODE_TOOL_ROUTING_MODE` = `full` | `dynamic`) — can narrow tool visibility per task.
- **GitHub workflow** — branch → verify → commit → push → PR via the `gh` CLI + git, every outward action gated.
- **Skills** (`skills/axio-coding/`) — an always-apply skill plus on-demand reference docs (tool routing, git/GitHub, python/node runtime, web, browser, retrieval, verification-and-recovery), loaded by `core/coding_skills.py`.

---

## Repository structure

```text
AXIO-Cortex/
├── README.md                     ← this file
├── LICENSE
├── docker-compose.yml            ← local Postgres + pgvector (the live Cortex DB)
├── docker/postgres/init/         ← Cortex schema (sessions, messages, memory_facts, memory_embeddings…)
└── axio-console-v2.1/            ← the application
    ├── axio.py                   ← launcher / mode selector
    ├── AGENTS.md · CLAUDE.md     ← agent startup briefings (auto-loaded)
    ├── docs/
    │   ├── STATE.md              ← live current-state (auto-snapshotted)
    │   └── CORTEX.md             ← memory subsystem deep-dive
    ├── core/                     ← config, models, memory (Cortex), code_tools (the 42-tool registry)
    │   ├── config.py             ← single source of truth (models, paths, limits)
    │   ├── memory*.py, self_memory.py, memory_backends/  ← Cortex
    │   └── code_tools/           ← the agentic tool registry + router + verification
    ├── modes/                    ← chat.py · cowork.py · code.py · revrec.py
    ├── skills/axio-coding/       ← Code-agent skill + references
    ├── prompts/                  ← system prompts
    ├── scripts/                  ← memory runtime, migrations, backups, benchmarks
    ├── tests/                    ← 168 tests (unittest / pytest)
    └── rev_agent.py              ← ASC 606 / IFRS 15 domain agent
```

---

## Quick start

```powershell
# 1. Configure
cd axio-console-v2.1
copy .env.example .env          # set ANTHROPIC_API_KEY (optional), OLLAMA_HOST

# 2. Local models
ollama pull gemma4:12b
ollama pull nomic-embed-text    # 768-dim embedder for Tier-2 memory

# 3. (Optional) live Cortex database — from the repo root
docker compose up -d            # Postgres + pgvector (axio_cortex)
#    then set AXIO_MEMORY_BACKEND=postgres in axio-console-v2.1/.env

# 4. Run
py axio.py                      # menu, or: py axio.py [chat|cowork|code|revrec]

# 5. Tests
py -m pytest tests -q
```

Requirements: Python 3.12, Node (for the Code harness hooks), Ollama, Docker (optional, for the live memory backend), `gh` CLI (optional, for the GitHub tools).

---

## Documentation

- [`axio-console-v2.1/CLAUDE.md`](axio-console-v2.1/CLAUDE.md) — architecture briefing (auto-loaded by Claude Code).
- [`axio-console-v2.1/docs/CORTEX.md`](axio-console-v2.1/docs/CORTEX.md) — memory subsystem internals.
- [`axio-console-v2.1/docs/STATE.md`](axio-console-v2.1/docs/STATE.md) — current status, in-flight work, recent changes.
- `config/models.yaml` · `config/routing.yaml` — model roles and routing.

---

## Security & privacy

- `.env` is git-ignored; API keys are never committed. Sessions, logs, and caches are ignored by default.
- Local-first: memory and embeddings stay on the machine; the Postgres binding is localhost-only (`127.0.0.1`).
- Claude usage is optional — the local Ollama path is always the default.

---

*Created by **VegaBuildsAI**. Private repository — proprietary and confidential.*
