# AXIO Platform — CLAUDE.md
> **Claude Code startup briefing.** Read this file (and its imports below) first. It is the curated context that replaces scanning the codebase.
> Version: **2.1 — Continuous Resilient Cortex Memory** · Owner: Michael (msvv11@gmail.com)

## How to work in this repo (read-first protocol)
- This file + the imported `docs/STATE.md` (live state) and `docs/CORTEX.md` (memory subsystem) are your context. **Do not scan the whole tree.** For anything not covered, `Grep`/`Read` the specific file or ask.
- **Single source of truth for constants is `core/config.py`** — never hardcode model names, paths, or limits elsewhere.
- Canonical code lives in `core/`, `core/code_tools/`, `modes/`, `config/`, `prompts/`, `skills/axio-coding/`. **Ignore** for context: marketing/manifesto docs (`AXIO_IOAF_Manifesto*`, `AXIO_LinkedIn_*`, `*.jam`), superseded plans (`AXIO_GEMMA_PLAN.md`), and May-era docs (`CHANGES.md`, `FIXES_SUMMARY.md`, `IMPROVEMENTS.md`, `docs/ARCHITECTURE.md`).
- **Knowledge sources (consult every session):** primary = this file, `AGENTS.md`, `docs/STATE.md`, `docs/CORTEX.md`. Secondary (always available) = the **Obsidian Second Brain via MCP** — `mcp__second-brain__*` (`search_files`, `read_file`, `directory_tree`, `read_multiple_files`) over `C:\Users\AXIO\Documents\Second Brain`. Search it for people, past decisions, architecture rationale, and cross-project context before scanning code.

## What AXIO is
A local-first, multi-model AI orchestration platform on **Windows** — Michael's local mirror of Claude's Chat/Cowork/Code surfaces, implementing **IOAF** three-tier persistent memory ("AXIO Cortex") so sessions are stateful and cumulative across time and modes. Runs hybrid: local **Ollama `gemma4:12b`** base + **Anthropic Claude API** boost. Repo root: `C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\` (data root: `C:\Users\AXIO\.axio`).

## Four modes (per `core/config.py:55-71`)
| Mode | Backend (`MODE_BACKENDS`) | Default model | Purpose |
|------|---------------------------|---------------|---------|
| Chat | local Ollama | `gemma4:12b` (Claude path uses `claude-haiku-4-5`) | Conversation w/ session memory + web-augmentation |
| Cowork | local Ollama (premium routes → Claude) | `gemma4:12b` | File-aware workspace assistant + web-augmentation |
| Code | **Claude API** | `claude-sonnet-4-6` (effort `high`) | Unified 38-tool coding agent: Plan Mode, skills, retrieval, web-evidence gate, GitHub PR workflow, scaffolds, verification gate |
| RevRec | local + boost | `gemma4:12b`, PDF/complex → Claude | ASC 606 / IFRS 15 revenue-recognition specialist (isolated memory) |

Claude tiers (`CLAUDE_MODELS`): `sonnet`=claude-sonnet-4-6 (default), `opus`=claude-opus-4-8. In-app: `model opus max`, `effort xhigh`. `LOCAL_ONLY=1` = 100% on-device (Code uses the local fallback).

## Architecture (where things live)
- **`axio.py`** — launcher / mode selector (chat · cowork · code · revrec).
- **`core/config.py`** — all constants, paths, models, env, routing. **Source of truth.**
- **`core/models.py`** — `OllamaClient`, `ClaudeClient`, `ModelRouter`.
- **`core/code_tools/`** — the **38-tool** Code registry (`build_default_registry()` in `__init__.py`; count = `len(CODE_TOOL_REGISTRY.tools)`). Groups: filesystem, python, node, git, **github**, document, shell, verification_gate, web, browser, retrieval, scaffold. Approval gate + risk levels in `registry.py`.
- **`core/web_intent.py`** — web-evidence gate (detect current-info intent; block Code `TASK_COMPLETE` until a web tool succeeds) + `augment_with_web()` used by Chat/Cowork.
- **`core/` memory (AXIO Cortex)** — `memory.py`, `self_memory.py`, `memory_runtime.py`, `mode_memory.py`, `memory_durability.py`, `memory_consolidation.py`, `db.py`, `memory_backends/postgres_backend.py`. **See `docs/CORTEX.md`.**
- **`modes/`** — `chat.py`, `cowork.py`, `code.py` (real Code logic; `gemma_code.py` is a 10-line shim → `code.py`), `revrec.py`.
- **`skills/axio-coding/`** — the Code agent's always-apply skill + `references/*.md` (tool routing, filesystem, git, github-workflow, web, browser, retrieval, verification-and-recovery, python/node runtime). `core/coding_skills.py` loads them.
- **`prompts/`** — `system_coding_agent.md`, `system_code_plan.md`, `system_revenue_agent.md`.
- **`rev_agent.py`** — ASC 606/IFRS 15 domain agent. **Never edit its `SYSTEM_PROMPT` directly** — `modes/revrec.py` monkey-patches it intentionally.

## Commands
```
py axio.py [chat|cowork|code|revrec]     # launch (bare = mode menu)
py axio.py --claude <mode>               # force Claude for the session (FORCE_CLAUDE=1)
LOCAL_ONLY=1 py axio.py <mode>           # 100% on-device
py -m pytest tests -q                    # test suite (145 tests)
```
In-mode: `plan <task>` / `execute` (Code) · `model <sonnet|opus> [effort]` · `memory` · `clear` · `help` · `exit`.

## Environment (`.env`; defaults in `core/config.py`)
`ANTHROPIC_API_KEY` (req) · `CLAUDE_MODEL=claude-sonnet-4-6` · `CLAUDE_MODEL_CHAT=claude-haiku-4-5-20251001` · `CLAUDE_MAX_TOKENS=16000` · `CLAUDE_EFFORT=high` · `LOCAL_ONLY` · `OLLAMA_HOST=127.0.0.1:11434` · `MODEL_*` (all default `gemma4:12b`) · `MEMORY_SUMMARY_MODEL=gemma4:12b` · `MEMORY_EMBED_MODEL=nomic-embed-text:latest` (768-dim, **do not change**) · `AXIO_MEMORY_BACKEND` (default `json`; `postgres` for live Cortex) · `AXIO_DB_*` (axio_cortex@127.0.0.1:5432) · `AXIO_SEARXNG_URL=127.0.0.1:8080`.

## Do NOT
- Hardcode constants outside `core/config.py`; edit `rev_agent.py`'s system prompt; remove `modes/gemma_code.py` (shim used by `tests/test_coding_skills.py`); change `MEMORY_EMBED_MODEL` (breaks the 768-dim vector store); trust `docs/ARCHITECTURE.md` / May-era docs for current state.

## Current state & memory subsystem
Live status, in-flight work, and recent changes → **`docs/STATE.md`**. AXIO Cortex memory internals → **`docs/CORTEX.md`**.

@docs/STATE.md
@docs/CORTEX.md
