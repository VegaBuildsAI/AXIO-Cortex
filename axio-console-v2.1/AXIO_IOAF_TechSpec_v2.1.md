# AXIO Platform — Technical Specification
> **Version:** 2.1 — Final Debugged Release 1
> **Author:** Michael Vega (msvv11@gmail.com)
> **Date:** 2026-05-09
> **Classification:** Internal — IOAF Architecture Reference

---

## 1. Platform Overview

**AXIO** is a local-first multi-model AI orchestration platform implementing the **IOAF (Intelligent Orchestrated Agent Framework)** — a three-tier memory architecture that makes AI sessions stateful and cumulative across time.

AXIO runs entirely on-premises using locally hosted open-source LLMs via Ollama as the primary compute tier, with the Anthropic Claude API as the premium escalation tier. All data, sessions, and memory remain on the user's machine by default.

### 1.1 Core Problem Solved

Today's AI tools are **stateless** — every session starts from zero, users repeat context every time, no learning accumulates. AXIO ends this by maintaining a persistent, queryable knowledge base that grows with every session across all four modes.

### 1.2 Design Principles

| Principle | Implementation |
|-----------|----------------|
| Local-first | Ollama-hosted LLMs are default; cloud is opt-in |
| Stateful | Three-tier memory persists facts, embeddings, and raw sessions |
| Cost-aware | Route to cheapest model that meets quality threshold |
| Fault-tolerant | Exponential backoff retry; fallback chain on every route |
| Mode-specific | Each mode has its own model, tools, and memory namespace |

---

## 2. System Architecture

### 2.1 Launch Entry Point

```
py axio.py [mode] [--claude]
```

`axio.py` is the unified 185-line launcher. It:
- Parses mode and flags
- Sets `FORCE_CLAUDE=1` env var if `--claude` is passed
- Delegates to the appropriate mode module under `modes/`
- Falls back to an interactive mode selector if no mode argument

**Flags:**

| Flag | Effect |
|------|--------|
| `chat` / `cowork` / `code` / `revrec` | Launch mode directly |
| `benchmark` | Run full model assessment suite |
| `--claude <mode>` | Force all prompts through Claude Sonnet for the session |

### 2.2 Directory Structure

```
axio-console-v2.1/
├── axio.py                   ← Unified launcher
├── rev_agent.py              ← RevRec domain agent (ASC 606/IFRS 15)
├── .env                      ← Local secrets (never committed)
├── .env.example              ← Safe template
│
├── core/
│   ├── config.py             ← Single source of truth for all constants
│   ├── memory.py             ← IOAF MemoryManager — 3-tier system
│   ├── models.py             ← OllamaClient, ClaudeClient, ModelRouter
│   ├── router.py             ← Keyword/regex prompt routing
│   ├── session.py            ← JSON session persistence
│   ├── logger.py             ← JSONL audit logging
│   └── ui.py                 ← Terminal colors, banners, spinners
│
├── modes/
│   ├── chat.py               ← Chat mode
│   ├── code.py               ← Code mode (agentic, file tools)
│   ├── cowork.py             ← Cowork mode (workspace-aware)
│   └── revrec.py             ← RevRec mode (monkey-patches rev_agent)
│
├── engine/
│   ├── assess.py             ← Assessment runner
│   ├── scorer.py             ← Rubric-based LLM-as-judge
│   ├── math_tool.py          ← Python exact arithmetic (bypasses LLM)
│   └── rubrics/              ← Scoring rubrics per task type
│
├── scripts/
│   └── benchmark_models.py   ← Full benchmark runner
│
├── config/
│   ├── models.yaml           ← Model role assignments
│   └── routing.yaml          ← Routing rules per route
│
└── logs/                     ← JSONL audit logs (auto-created)
```

---

## 3. Four Operational Modes

| Mode | Primary Model (Claude) | Primary Model (Local) | Tools | Memory Namespace |
|------|----------------------|----------------------|-------|-----------------|
| **Chat** | claude-haiku-4-5-20251001 | mistral:latest | None | `chat_memory.json` |
| **Code** | claude-sonnet-4-6 | qwen3-coder:30b | read/write/edit file, list_dir, create_dir, search, grep, PowerShell | `code_memory.json` |
| **Cowork** | claude-sonnet-4-6 | auto-routed | File indexing, workspace state | `cowork_memory.json` |
| **RevRec** | claude-sonnet-4-6 | qwen3:14b | All Code tools + Excel: create_allocation_schedule, create_deferred_revenue_schedule, create_variable_consideration_model, create_contract_modification_analysis, create_memo | `revrec_memory.json` |

### 3.1 Chat Mode

Fast general-purpose conversation. Uses Claude Haiku (cheapest tier) by default. Full session memory. Supports `/memory`, `/clear`, `/save`, `/exit` commands. Math expressions are intercepted by `math_tool.py` before any model call.

### 3.2 Code Mode

Autonomous agentic coding loop. Maintains a `_session_claude` sticky flag — once the session routes to Claude, it stays on Claude for the remainder unless manually switched. Supports `model claude`, `model local`, `model <name>` commands.

**File tools available:** `read_file`, `write_file`, `edit_file`, `list_dir`, `create_dir`, `search_files`, `grep_files`. PowerShell execution via `run_powershell`.

### 3.3 Cowork Mode

Workspace-aware assistant. Maintains `WorkspaceState` with indexed file tree. Auto-routes each prompt through `core/router.py` to select the best local model. Supports `@file.py` syntax to load files into context.

### 3.4 RevRec Mode

ASC 606 / IFRS 15 revenue recognition specialist. Monkey-patches `rev_agent.SYSTEM_PROMPT` to inject memory prefix. Runs the full `rev_agent.py` (1700+ lines) with 17 tools total:

- **Domain tools (11):** `analyze_contract`, `identify_performance_obligations`, `determine_transaction_price`, `allocate_transaction_price`, `recognize_revenue`, `create_allocation_schedule`, `create_deferred_revenue_schedule`, `create_variable_consideration_model`, `create_contract_modification_analysis`, `create_memo`, `read_pdf`
- **File tools (6):** `write_file`, `edit_file`, `list_dir`, `create_dir`, `search_files`, `grep_files`

To run RevRec with full Claude capability: `py axio.py --claude revrec`

---

## 4. IOAF Three-Tier Memory System

> **FigJam diagram:** [AXIO IOAF — Three-Tier Memory System](https://www.figma.com/board/iNJUG5sGf7YYCEJRV99IOv)

The core innovation of AXIO. Every mode uses `core/memory.py → MemoryManager`. Memory is loaded at session start and written at session end (on `/exit` or `KeyboardInterrupt`).

### Tier 1 — Session JSON (`~/.axio/sessions/`)

Raw conversation history saved as timestamped JSON files. Short-term. Source material for Tier 2 summarization. Always written — no external dependencies.

### Tier 2 — ChromaDB Vector Store (`~/.axio/chroma/`)

**At session end:**
1. `qwen3:14b` summarizes the full conversation (MEMORY_SUMMARY_MODEL)
2. Summary is embedded via `nomic-embed-text:latest` (768-dimensional cosine similarity)
3. Embedding stored in ChromaDB PersistentClient v1.5.9

**At session start:**
1. User's first prompt is embedded
2. Top-N semantically similar past sessions retrieved (`MEMORY_RECALL_RESULTS=5`)
3. Retrieved summaries injected into system prompt prefix

ChromaDB import failures are caught silently — system falls back to keyword search. Always starts even without ChromaDB or nomic-embed-text.

### Tier 3 — Structured Facts JSON (`~/.axio/memory/`)

Key-value facts extracted by `auto_update_facts()` from every user message. Examples: user name, active project names, workspace paths, client names, preferences. Always loaded — no Ollama dependency.

| File | Contents |
|------|----------|
| `chat_memory.json` | Chat mode facts |
| `code_memory.json` | Code mode facts (workspaces, languages) |
| `revrec_memory.json` | RevRec facts (clients, contract types) |
| `console_memory.json` | Master cross-mode knowledge base |

### Memory Commands (all modes)

```
/memory              Show current memory facts
/memory set k v      Store a fact
/clear               Clear session message history
/info                Show message count, current backend
/save                Save session to disk
/exit                Clean exit — triggers memory storage
```

---

## 5. Model Routing Engine

> **FigJam diagram:** [AXIO IOAF — Model Routing & Fallback Architecture](https://www.figma.com/board/NM2PhZHkCeRrhDF3cqnR0Y)

### 5.1 Router (`core/router.py`)

`ModelRouter.detect(prompt)` returns a `(route, model)` tuple using keyword matching and regex patterns. Routes are evaluated in priority order.

| Route | Trigger Pattern | Primary Model | Fallback |
|-------|----------------|---------------|----------|
| `math` | `\d[\s]*[+\-*/^][\s]*[\d(]` | `python_exact` (math_tool.py) | none needed |
| `coding_agent` | code keywords | `qwen3-coder:30b` | `qwen3:8b` |
| `revenue_analysis` | ASC 606/IFRS keywords | `qwen3:14b` | `claude-sonnet-4-6` |
| `quick_chat` | general | `qwen3:8b` | `claude-haiku-4-5-20251001` |
| `premium_reasoning` | complex/deep keywords | `claude-sonnet-4-6` | `qwen3:14b` |

### 5.2 Math Tool Intercept

Before any model call, all three live modes check:
```python
route, model = router.detect(user_input)
if route == "math":
    result = math_solve(user_input)
    if result.get("score") == 100:
        print(f"\n[Python exact] {result['expression']} = {result['result']}")
        continue  # skip model call entirely
```

This clears the MATH-001 timeout health flags for qwen3:8b and qwen3:14b (both previously timed out attempting 8-digit multiplication in-context at 600s).

### 5.3 FORCE_CLAUDE Override

When `--claude` flag is passed:
1. `axio.py` sets `os.environ["FORCE_CLAUDE"] = "1"`
2. All modes check this env var on startup
3. Every prompt routes to Claude regardless of router output
4. `_session_claude = True` sticky flag persists for the session

### 5.4 Model Performance Benchmarks (ASSESS-006, 2026-05-09)

| Model | Coding | Architecture | Revenue | Math | Avg |
|-------|--------|-------------|---------|------|-----|
| qwen3:14b | 92 | — | **85** | timeout | ~88 |
| qwen3:8b | 92 | 82 | 72 | timeout | ~82 |
| qwen3-coder:30b | **92** | 75 | 72 | 0 | ~73 |
| llama3.1:8b | 72 | 45 | 35 | 15 | ~42 |
| python_exact | — | — | — | **100** | — |

---

## 6. Model Clients (`core/models.py`)

### 6.1 OllamaClient

Wraps local Ollama REST API. Features:
- `is_running()` — health check with 3s timeout
- `list_models()` — available local models
- `chat_stream()` — streaming response with exponential backoff retry (3 attempts, 2× multiplier)
- `chat()` — non-streaming wrapper

### 6.2 ClaudeClient

Wraps Anthropic SDK. Features:
- Per-mode model selection: `ClaudeClient(model=CLAUDE_MODEL_CHAT)` for Chat; default `CLAUDE_MODEL` for all others
- `CLAUDE_MAX_TOKENS` configurable (default 4096)
- Exponential backoff retry with rate-limit handling
- `tool_call(messages, tools, system)` — handles full tool-use loop (matches Code mode agentic pattern)

### 6.3 ModelRouter

`detect(prompt) → (route: str, model: str)`

Reads `FORCE_CLAUDE` env var. If set, returns `("premium_reasoning", CLAUDE_MODEL)` regardless of prompt content.

---

## 7. Assessment Engine

`py axio.py benchmark` runs `scripts/benchmark_models.py` → `engine/assess.py` → `engine/scorer.py`.

**Benchmark tasks:**

| ID | Task Type | Prompt | Scorer |
|----|-----------|--------|--------|
| MATH-001 | Exact arithmetic | 84736291 × 69384725 | python_exact (100 or 0) |
| CODING-001 | Code generation | Flask REST API implementation | rubrics/coding.md (LLM judge) |
| REVREC-001 | ASC 606 analysis | SaaS performance obligation tree | rubrics/revenue.md (LLM judge) |
| ARCH-001 | Architecture | Microservices design | rubrics/architecture.md (LLM judge) |

Results logged to `logs/model_tests.jsonl`. Assessment snapshots to `engine/assessments.jsonl`.

---

## 8. Environment Configuration

```bash
# Anthropic API
ANTHROPIC_API_KEY=sk-ant-api03-...

# Claude models (Claude 4.x)
CLAUDE_MODEL=claude-sonnet-4-6           # Code, Cowork, RevRec
CLAUDE_MODEL_CHAT=claude-haiku-4-5-20251001  # Chat mode only
CLAUDE_MAX_TOKENS=4096

# Local Ollama models
OLLAMA_HOST=http://127.0.0.1:11434
MODEL_CHAT=mistral:latest
MODEL_CODING=qwen3-coder:30b
MODEL_REASONING=qwen3:14b
MODEL_FAST=qwen3:8b
MODEL_FALLBACK=qwen3:8b

# Memory system
MEMORY_RECALL_RESULTS=5
MEMORY_SUMMARIZE=1
MEMORY_SUMMARY_MODEL=qwen3:14b
MEMORY_EMBED_MODEL=nomic-embed-text:latest

# Session
CONTEXT_MESSAGE_LIMIT=50
LOG_LEVEL=INFO
```

---

## 9. Dependencies

### Python packages
```bash
pip install anthropic requests python-dotenv chromadb rich
```

### Ollama models
```bash
ollama pull mistral
ollama pull qwen3:8b
ollama pull qwen3:14b
ollama pull qwen3-coder:30b
ollama pull llama3.1:8b
ollama pull nomic-embed-text    # Required for Tier 2 ChromaDB memory
```

---

## 10. FigJam Architecture Diagrams

| Diagram | URL |
|---------|-----|
| IOAF Model Routing & Fallback Architecture | https://www.figma.com/board/NM2PhZHkCeRrhDF3cqnR0Y |
| IOAF Three-Tier Memory System | https://www.figma.com/board/iNJUG5sGf7YYCEJRV99IOv |
| Four-Mode Platform Workflow | https://www.figma.com/board/GTXZvCwuku1cf6UdBXDXvD |

---

## 11. Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.0 | 2026-04-15 | Initial monolithic `axio_agent_console_FINAL.py` |
| v2.0 | 2026-05-06 | Six core fixes: configurable models, retry logic, error handling, session pruning, security |
| v2.1 | 2026-05-09 | Full refactor: four-mode launcher, IOAF memory system, assessment engine, math tool, corrected rubrics and routing, Claude parity for RevRec, file tools in RevRec |

### v2.1 Key Changes from v2.0

1. Monolithic file split into `core/`, `modes/`, `engine/` modules
2. IOAF three-tier memory system implemented (`core/memory.py`)
3. ChromaDB + nomic-embed-text for semantic session recall
4. Assessment engine with rubric-based LLM-as-judge scoring
5. `math_tool.py` — Python exact arithmetic, bypasses all LLMs
6. Per-mode Claude model selection (Haiku for Chat, Sonnet for all others)
7. `--claude` flag for session-wide Claude override
8. REVREC rubric rewritten to match actual ASC 606 task
9. Benchmark-informed routing: qwen3:14b → revenue (85/100), qwen3-coder:30b → coding only
10. RevRec Claude call refactored to use shared `ClaudeClient.tool_call()`
11. Six file tools added to RevRec (write, edit, list, create, search, grep)
12. ChromaDB 1.5.9 installed and Tier 2 memory verified end-to-end

---

## 12. Known Issues & Roadmap

### Active Issues

| Issue | Severity | Status |
|-------|----------|--------|
| qwen3 thinking-mode token overflow on benchmarks | Medium | Documented — fix: pass `"think": false` in Ollama options |
| ARCH-001 timeout on qwen3:14b at 8192 context | Low | Acceptable — route to Claude for arch tasks if needed |

### Roadmap

- [ ] Pass `"think": false` in Ollama options for benchmark tasks to prevent thinking-token context overflow
- [ ] Expose cross-mode memory recall in UI (Code mode reading RevRec memories)
- [ ] Web UI wrapper (FastAPI + React) for browser-based access
- [ ] Streaming output for RevRec tool chains
- [ ] Multi-contract batch processing in RevRec

---

*This document is the authoritative technical specification for AXIO v2.1 Final Debugged Release 1.*
*Update alongside CLAUDE.md whenever a significant architectural change is made.*
