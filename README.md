# AXIO Cortex
## Local-first AI console with persistent memory, multi-model routing, and Claude API escalation

---

## WHAT IS THIS?

**AXIO Cortex** is a local-first AI workspace that behaves like a personal AI operating console.
It combines four working modes, persistent memory, local Ollama models, and optional Claude API
escalation into one unified command-line platform.

The project is built around the **IOAF (Intelligent Orchestrated Agent Framework)**: a three-tier
memory architecture that makes AI sessions stateful and cumulative over time. Instead of starting
from zero every session, AXIO Cortex recalls prior conversations, facts, project context, and
semantic memory across modes.

---

## CORE IDEA

Most AI tools are stateless. Every new chat starts cold.

AXIO Cortex is designed around the opposite principle:

> AI should get smarter the longer you use it.

The platform runs locally by default, keeps memory on the user's machine, routes prompts to the
right model for the task, and escalates to Claude only when higher reasoning or coding capability
is needed.

---

## ARCHITECTURE - UNIFIED AI WORKSPACE

AXIO Cortex is organized as one console with four operational modes:

| Mode | Purpose | Local model | Premium escalation |
|------|---------|-------------|--------------------|
| Chat | Fast general conversation with memory | `mistral:latest` | Claude Haiku |
| Cowork | Workspace-aware assistant for files and projects | Auto-routed | Claude Sonnet |
| Code | Agentic coding assistant with file tools | `qwen3-coder:30b` | Claude Sonnet |
| RevRec | ASC 606 / IFRS 15 revenue recognition specialist | `qwen3:14b` | Claude Sonnet |

All modes feed the same persistent memory layer, so context from one workflow can improve another.

---

## MEMORY SYSTEM - IOAF

AXIO Cortex uses a three-tier memory system:

| Tier | Stores | Purpose |
|------|--------|---------|
| Tier 1 - Record | Raw session JSON | Permanent source of truth for every exchange |
| Tier 2 - Understanding | Semantic summaries + embeddings | Retrieves related past work by meaning |
| Tier 3 - Facts | Structured key-value memory | Fast personalization and durable project facts |

This gives the console long-term recall without requiring cloud-hosted memory.

---

## HOW TO USE

### 1. Configure environment

Copy the template and fill in local values:

```powershell
cd axio-console-v2.1
copy .env.example .env
```

Set your local Ollama endpoint and, optionally, your Claude API key:

```env
OLLAMA_HOST=http://127.0.0.1:11434
ANTHROPIC_API_KEY=your-key-here
```

### 2. Pull local models

```powershell
ollama pull mistral
ollama pull qwen3:8b
ollama pull qwen3:14b
ollama pull qwen3-coder:30b
ollama pull nomic-embed-text
```

### 3. Launch the console

```powershell
py axio.py
```

Launch a specific mode:

```powershell
py axio.py chat
py axio.py cowork
py axio.py code
py axio.py revrec
```

Force Claude for a session:

```powershell
py axio.py --claude code
```

Run benchmark assessment:

```powershell
py axio.py benchmark
```

---

## GUIDE BY NEED

| What you need | Use this mode |
|---------------|---------------|
| General AI chat with memory | `chat` |
| Work across local files and project context | `cowork` |
| Coding, file edits, debugging, and implementation | `code` |
| Revenue recognition analysis and ASC 606 / IFRS 15 workflows | `revrec` |
| Test model quality and routing decisions | `benchmark` |

---

## TECHNOLOGY STACK

AXIO Cortex is built for a local Windows workflow:

- Runtime: Python
- Local LLM backend: Ollama
- Premium reasoning backend: Claude API
- Local memory: JSON session store
- Semantic memory: ChromaDB-style vector memory
- Embeddings: `nomic-embed-text`
- CLI shell: PowerShell
- Domain benchmark engine: rubric-based model scoring

---

## REPOSITORY STRUCTURE

```text
AXIO-Cortex/
├── README.md
├── LICENSE
├── CHANGES.md
├── config/
│   ├── models.yaml
│   └── routing.yaml
├── engine/
│   └── rubrics/
├── axio-console-v2.1/
│   ├── axio.py
│   ├── rev_agent.py
│   ├── .env.example
│   ├── AGENTS.md
│   ├── CLAUDE.md
│   ├── core/
│   ├── modes/
│   ├── engine/
│   ├── prompts/
│   ├── scripts/
│   └── Contracts example/
└── run_*.bat
```

---

## PROJECT STATUS

Current version: **AXIO v2.1 - Final Debugged Release 1**

Implemented:

- [x] Unified launcher with direct mode selection
- [x] Four operating modes: Chat, Cowork, Code, RevRec
- [x] Local-first model routing
- [x] Claude API escalation path
- [x] Three-tier IOAF memory system
- [x] Revenue recognition specialist mode
- [x] Benchmark and scoring engine
- [x] Model routing configuration
- [x] Safe `.env.example` template

Planned:

- [ ] Package installer
- [ ] Cleaner public documentation
- [ ] Architecture diagram export
- [ ] Optional GUI shell
- [ ] Expanded model benchmark suite

---

## SECURITY NOTES

- `.env` is intentionally excluded from git.
- API keys should never be committed.
- Local sessions, logs, and cache folders are ignored by default.
- Claude API usage is optional; local Ollama models remain the default path.

---

## ABOUT

Created by **VegaBuildsAI** as a local-first AI console for persistent, cumulative,
mode-aware work across chat, coding, coworking, and finance/revenue-recognition workflows.

Private repository. Proprietary and confidential.
