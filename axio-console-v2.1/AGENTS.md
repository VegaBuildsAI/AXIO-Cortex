# AXIO Platform — AGENTS.md
> **Codex / agents startup file.** Read this first, then the shared canonical context: `CLAUDE.md`, `docs/STATE.md` (live state), `docs/CORTEX.md` (memory subsystem). Do not scan the whole tree — those files are the curated context.
> Version: **2.1 — Continuous Resilient Cortex Memory** · Owner: Michael (msvv11@gmail.com)

## What AXIO is
Local-first, multi-model AI orchestration platform on **Windows** — a local mirror of Claude's Chat/Cowork/Code surfaces with **IOAF** three-tier persistent memory ("AXIO Cortex"). Runs hybrid: local **Ollama `gemma4:12b`** base + **Anthropic Claude API** boost (the premium cloud tier is the Anthropic **Claude** API — Sonnet default, Opus available). Repo root: `C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\`; data root: `C:\Users\AXIO\.axio`.

## Four modes (`core/config.py:55-71` is the source of truth)
| Mode | Backend | Default model |
|------|---------|---------------|
| Chat | local Ollama | `gemma4:12b` (Claude path: `claude-haiku-4-5-20251001`) |
| Cowork | local Ollama (premium → Claude) | `gemma4:12b` |
| Code | **Claude API** | `claude-sonnet-4-6` (effort `high`); Opus = `claude-opus-4-8` |
| RevRec | local + boost | `gemma4:12b`, PDF/complex → Claude |

`LOCAL_ONLY=1` = fully on-device. `py axio.py --claude <mode>` forces Claude for the session (`FORCE_CLAUDE=1`).

## Essentials
- **`core/config.py`** = single source of truth for constants, models, paths, routing. Never hardcode elsewhere.
- Code mode = the unified **38-tool** agent (`core/code_tools/`, count = `len(CODE_TOOL_REGISTRY.tools)`): filesystem, python, node, git, github, document, shell, verification_gate, web, browser, retrieval, scaffold. Risk-gated in `registry.py`.
- Memory = **AXIO Cortex** (Postgres/pgvector primary + Chroma mirror + JSON fallback; default backend `json`). Full detail in `docs/CORTEX.md`.
- Skills: `skills/axio-coding/SKILL.md` + `references/*.md`, loaded by `core/coding_skills.py`.

## Knowledge sources (consult every session)
Primary = this file + `CLAUDE.md` + `docs/STATE.md` + `docs/CORTEX.md`. Secondary (always) = the **Obsidian Second Brain** at `C:\Users\AXIO\Documents\Second Brain` (via the second-brain MCP where available) for people, decisions, and architecture rationale.

## Commands
```
py axio.py [chat|cowork|code|revrec]
py -m pytest tests -q            # 145 tests (unittest-based)
```

## Do NOT
Hardcode constants outside `core/config.py`; edit `rev_agent.py`'s system prompt (monkey-patched by `modes/revrec.py`); remove `modes/gemma_code.py` (shim used by tests); change `MEMORY_EMBED_MODEL` (768-dim vector store); trust `docs/ARCHITECTURE.md` or May-era docs for current state.

*Current status, in-flight work, and recent changes are maintained in `docs/STATE.md`.*
