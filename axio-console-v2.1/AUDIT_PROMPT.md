# AXIO Console — Full Architecture Audit

## Context: Who I Am and What I'm Building

My name is Michael. I am building **AXIO**, a multi-model AI orchestration framework that I call **IOAF (Intelligent Orchestrated Agent Framework)**. The core idea is simple but profound: **AI systems should remember and learn from every interaction**. Today's AI tools are stateless — each session starts from zero. AXIO is designed to end that.

AXIO runs entirely on my local machine (Windows, `C:\Users\AXIO\AXIO Model Improvement\axio-console-v2.1\`) using Ollama-hosted open-source LLMs as the default backend, with the Anthropic Claude API available as a premium cloud layer. The system is consciously modeled after Anthropic's own product line — Claude Chat, Claude Code, and Claude Cowork — but running locally, under my control, with persistent memory that accumulates across every session.

---

## The Architecture I Designed

### Four Operational Modes

| Mode    | Claude Model          | Local Model        | Purpose |
|---------|-----------------------|--------------------|---------|
| Chat    | claude-haiku-4-5-20251001 | mistral / qwen3:8b | Fast general-purpose conversation with memory |
| Code    | claude-sonnet-4-6     | qwen2.5-coder:32b  | Autonomous coding agent with file tools |
| Cowork  | claude-sonnet-4-6     | auto-routed        | File-aware workspace assistant |
| RevRec  | claude-sonnet-4-6     | qwen3:14b          | ASC 606 / IFRS 15 revenue recognition specialist |

### The IOAF Three-Tier Memory System

This is the heart of the project. Every mode uses a single `MemoryManager` class (`core/memory.py`) that manages:

**Tier 1 — Session JSON** (`~/.axio/sessions/`)
Raw conversation history saved as JSON. Short-term. Source material for higher tiers.

**Tier 2 — ChromaDB Vector Store** (`~/.axio/chroma/`)
At session end, `qwen3:14b` summarizes the conversation. That summary is embedded using `nomic-embed-text` (local Ollama) and stored in ChromaDB. At session start, the user's first prompt is also embedded and compared against stored summaries — top-N semantically similar past sessions are retrieved and injected as system context before the first token is generated.

**Tier 3 — Structured Facts JSON** (`~/.axio/memory/{mode}_memory.json`)
Explicit key-value facts per mode: user name, active projects, preferences, workspace paths, recent clients, etc. Always loaded regardless of whether Ollama or ChromaDB is available. Provides deterministic baseline context.

**Console Master Memory** (`~/.axio/memory/console_memory.json`)
All four modes append their session summaries here. This is the cross-mode knowledge base and the eventual training data source.

### Model Routing

`core/router.py` keyword-matches each prompt to one of: `fast`, `smart`, `coding`, `premium`. Premium routes go to Claude API; others go to local Ollama. Each mode also supports a `--claude` flag to force all prompts through Claude.

**Critical recent change:** `ClaudeClient.__init__` now accepts an optional `model: str` parameter. Chat mode passes `CLAUDE_MODEL_CHAT` (Haiku). All other modes call `ClaudeClient()` with no argument and inherit `CLAUDE_MODEL` (Sonnet). This per-mode model selection was added in `core/config.py`:
```python
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
CLAUDE_MODEL_CHAT = os.getenv("CLAUDE_MODEL_CHAT", "claude-haiku-4-5-20251001")
```

### Key Files

```
axio-console-v2.1/
├── axio.py                        # Main launcher / mode router (~185 lines)
├── rev_agent.py                   # RevRec domain agent — ASC 606/IFRS 15, Excel, KPMG Handbook (~1698 lines)
├── console.py                     # Legacy? Or still active? Needs clarification (~474 lines)
├── agent.py                       # Legacy? (~544 lines)
├── axio_agent_console_FINAL.py    # Old version, hardcoded to claude-opus-4-1-20250805 (~523 lines)
├── axio_final.py                  # Old version, hardcoded to claude-opus-4-1-20250805 (~367 lines)
├── core/
│   ├── __init__.py                # Exports MemoryManager, ensure_chromadb, _handle_memory_cmd
│   ├── config.py                  # All constants, paths, model names, API keys (~112 lines)
│   ├── memory.py                  # IOAF MemoryManager — 3-tier system (~541 lines) ← CORE
│   ├── models.py                  # OllamaClient, ClaudeClient, ModelRouter (~261 lines)
│   ├── router.py                  # Keyword-based prompt routing logic (~75 lines)
│   ├── session.py                 # SessionManager — JSON persistence (~107 lines)
│   ├── logger.py                  # AuditLogger — per-mode JSONL logs (~85 lines)
│   └── ui.py                      # Terminal colors, banners, spinners (~117 lines)
├── modes/
│   ├── chat.py                    # Chat Mode — uses ClaudeClient(model=CLAUDE_MODEL_CHAT) (~253 lines)
│   ├── code.py                    # Code Mode — agentic loop, file tools (~605 lines)
│   ├── cowork.py                  # Cowork Mode — WorkspaceState, file loading (~302 lines)
│   └── revrec.py                  # RevRec Mode — monkey-patches rev_agent.SYSTEM_PROMPT (~68 lines)
```

### Known Issues / History

1. **File truncation bug**: `core/config.py` and `core/models.py` were found truncated on disk (Windows CRLF + Edit tool size-padding bug). Both were rewritten via bash heredoc and are now complete.
2. **RevRec integration**: `modes/revrec.py` integrates with `rev_agent.py` via monkey-patching — it imports `rev_agent`, injects `memory_prefix` into `rev_agent.SYSTEM_PROMPT`, then calls `rev_agent.main()`. This is intentional to avoid modifying rev_agent.py directly.
3. **Legacy files**: `axio_agent_console_FINAL.py`, `axio_final.py`, `agent.py`, and `console.py` exist in the root. Their relationship to the current `axio.py` launcher is unclear and needs investigation.
4. **ChromaDB**: Version 1.5.9 installed. `nomic-embed-text` (274MB) pulled via Ollama. The memory system never lets ChromaDB use its built-in ONNX downloader — it always provides explicit embeddings from Ollama or falls back to keyword search silently.

---

## Your Audit Mission

You are Claude Code. You have full access to read every file in this project. Please perform a **deep, structured audit** of the AXIO codebase with the following deliverables:

### 1. Architecture Integrity Check
- Does the actual code in `axio.py` + `modes/` match the intended architecture described above?
- Is the per-mode Claude model selection (`CLAUDE_MODEL_CHAT` for Haiku in Chat, `CLAUDE_MODEL` for Sonnet elsewhere) correctly wired end-to-end?
- Is `ModelRouter` being used consistently across modes, or are some modes routing differently?
- Does `core/config.py` export everything that `core/models.py`, `core/memory.py`, and the modes actually import?

### 2. Memory System Completeness
Read `core/memory.py` fully, then check each mode:
- Is `MemoryManager` instantiated in all four modes with the correct mode string?
- Is `build_memory_prefix()` called before every model invocation in all four modes?
- Is `store_session()` called on **both** clean exit (`/exit`) and interrupt (`Ctrl+C`) in all four modes?
- Is `update_facts()` called when relevant facts become available (e.g. workspace path in Cowork)?
- Is the `/memory` command and `/memory set k v` handler present in all four modes?
- Is `console_memory.json` actually being written to after sessions end?
- Does the keyword fallback in `recall()` work correctly when ChromaDB is unavailable?

### 3. Dead Code and Legacy File Analysis
Audit these files and determine their status:
- `console.py` — Is this still called anywhere? Does it duplicate `modes/` functionality? Should it be archived or integrated?
- `agent.py` — Same question. What does it do vs `modes/code.py`?
- `axio_agent_console_FINAL.py` — Clearly an old version. Is it referenced anywhere? Safe to delete?
- `axio_final.py` — Same. Still needed?
- `rev_agent.py` — 1,698 lines. What is actually used by `modes/revrec.py`? Is `CLAUDE_MODEL` defined at line 75 (`claude-sonnet-4-6`) consistent with the current config, or is it a stale override?

### 4. Error Handling and Resilience
- What happens in each mode if Ollama is offline at startup?
- What happens if `ANTHROPIC_API_KEY` is not set and the user tries `/backend` in Chat?
- What happens in `modes/revrec.py` if `rev_agent.py` raises an exception mid-session (memory is not stored)?
- Does `core/memory.py` handle ChromaDB import failures gracefully across all code paths?
- Are there any unguarded `open()`, file read, or JSON parse calls that could crash a session?

### 5. Cross-Mode Consistency
All four modes should follow the same pattern. Check for inconsistencies:
- Session initialization: same structure?
- Memory prefix injection: same point in the request flow?
- Exit handlers: same cleanup steps?
- Status line / banner display: same style via `core/ui.py`?
- Logger calls: consistent use of `AuditLogger`?

### 6. Security
- Is `CLAUDE_API_KEY` ever printed, logged, or included in any response?
- Are there any hardcoded API keys or model names that conflict with the `.env`-driven config?
- Does `core/logger.py` redact sensitive content from JSONL audit logs?
- Is `.env` excluded from any output written to disk?

### 7. Missing Features and Gaps vs Vision
Based on the IOAF architecture described above, identify:
- What is implemented vs what is described but missing?
- Does the Console mode (`console.py`) actually function as a master orchestrator, or is it vestigial?
- Is cross-mode memory recall possible (e.g., Code mode reading RevRec memories)?
- Are there any obvious next implementation steps that the current code structure makes easy vs hard?

### 8. Code Quality
- Are there circular imports between `core/` modules?
- Is there duplicated logic across modes that should be refactored into `core/`?
- Are type hints used consistently?
- Are there any obvious performance issues (e.g. loading all session history into memory on every prompt)?

---

## Output Format

Please structure your findings as follows:

```
## AXIO Audit Report

### Executive Summary
[3-5 sentence overall health assessment]

### 1. Architecture Integrity — [PASS / WARN / FAIL]
...findings...

### 2. Memory System — [PASS / WARN / FAIL]
...findings per mode...

### 3. Dead Code — [files to keep / archive / delete]
...

### 4. Error Handling — [PASS / WARN / FAIL]
...

### 5. Cross-Mode Consistency — [PASS / WARN / FAIL]
...

### 6. Security — [PASS / WARN / FAIL]
...

### 7. Gaps vs Vision — [critical / nice-to-have]
...

### 8. Code Quality — [PASS / WARN / FAIL]
...

### Priority Fix List
[Ordered list of what to fix first, with file + line references]
```

Be direct. If something is broken, say it is broken. If a file should be deleted, say so. The goal is a production-ready, coherent codebase that faithfully implements the IOAF vision.

Start by reading `axio.py`, then `core/config.py`, `core/memory.py`, `core/models.py`, and all four `modes/` files. Then investigate the legacy files. Then write the report.
