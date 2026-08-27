---
name: axio-harness-integration
description: AXIO Cortex harness integration plan. Read before any implementation on gemma_code.py, axio.py, or tools. Defines what to build, what order, and what not to touch.
sources: [cowork]
aliases: [axio-plan, harness-plan, axio-integration]
---

# AXIO Cortex — Harness Integration Plan

## Hard Constraints

- **PLAN MODE**: no implementation until all analysis phases complete
- **No fine-tuning** while critical harness gaps exist (context, tools, error recovery)
- **All 42 tools preserved and visible by default** — bounded routing is experimental only
- **Target model**: Gemma 4 12B via Ollama (`gemma4:12b`)

---

## Current Architecture (from memory — axio-console unavailable in session)

| Component | Location | State |
|---|---|---|
| Agent loop | `modes/gemma_code.py` (~580 lines) | active |
| Skills | `skills/gemma4/{SKILL,PLAN_MODE,CODE_BEST_PRACTICES}.md` | active |
| System prompts | `prompts/gemma4_{code,plan}_system.md` | active |
| Launcher | `axio.py` | active |
| Plan Mode + TaskTracker | `gemma_code.py` | active |
| Vision | base64 multimodal | active |
| Tool exposure | 42 simultaneous + 42/42 calling-skill catalog | **current default** |

**Model routing:** `chat→gemma4:12b` · `cowork→auto` · `gemma_code→gemma4:12b` · `code→qwen3.6:35b-a3b` · `rev_agent→qwen3.6:35b-a3b`

---

## Harness Score: 32 / 100 (Level 1 — partial)

| Category | /100 |
|---|---|
| Agent loop | 45 |
| Planning | 55 |
| Tool architecture | 30 |
| Tool use | 35 |
| Context engineering | 20 |
| Repository reasoning | 35 |
| Error recovery | 25 |
| Verification | 40 |
| Observability | 20 |
| Benchmark readiness | 10 |

---

## Gap → Decision Map

### CRITICAL

**G1 — Context window locked at 8K–32K**
Gemma 4 12B native: 128K. Ollama default: conservative allocation.
Decision: Modelfile — same weights, unlock native context.
```
FROM gemma4:12b
PARAMETER num_ctx 131072
```
`ollama create gemma4:128k -f gemma4-128k.Modelfile`
Fallback if OOM: `num_ctx 65536`

---

**G2 — Observation truncation — IMPLEMENTED (Aug 25, 2026)**
Tool outputs enter context raw → context overflow on any large file/command.
Decision: 3-tier truncation before every observation enters `messages[]`.
```python
def truncate_observation(text, max_chars=4000):
    if len(text) <= max_chars:
        return text
    if len(text) <= max_chars * 2:
        return text[:max_chars] + f"\n[…{len(text)-max_chars} chars truncated]"
    h = max_chars // 2
    return text[:h] + f"\n[…{len(text)-max_chars} chars…]\n" + text[-h:]
```

---

**G3 — Dynamic tool router — IMPLEMENTED (Aug 25, 2026)**
Selection error rate scales with list length on 12B models. Reliable threshold: 5–11.
Source: assessment doc §6, §12 (not Goose documentation).

Original decision: **Dynamic Tool Router** — all 38 preserved in registry, ≤8 injected per task phase.
Live A/B later showed unacceptable accuracy loss, so the deployed Code default was restored to
all registered tools; dynamic routing remains an explicit experimental option. Four native
artifact writers were later added, bringing Code to 42 visible tools.

```
prompt → classify_task() → TaskType → ToolRegistry.get_subset(TaskType) → ollama.chat(tools=subset)
```

Code runtime policy (corrected after live A/B on Aug 25, 2026):

- Default: `AXIO_CODE_TOOL_ROUTING_MODE=full` exposes all 42 registered Code tools.
- Each tool has a specific model-visible calling card in
  `skills/axio-coding/tool-calling-skills.yaml`; tests enforce exact registry parity.
- Experimental only: `AXIO_CODE_TOOL_ROUTING_MODE=dynamic` enables the subset below.

Experimental TaskType → active subset:

| TaskType | Active tools (≤8) |
|---|---|
| `CODE_EDIT` | read_file, edit_file, write_file, search_files, run_command, list_dir, task_update, finish |
| `DEBUGGING` | read_file, run_command, search_files, edit_file, verify_file, list_dir, task_update, finish |
| `RESEARCH` | read_file, web_search, web_fetch, search_files, list_dir, task_update, finish |
| `PLANNING` | read_file, search_files, task_update, list_dir, web_search, finish |
| `TESTING` | run_command, read_file, edit_file, search_files, list_dir, task_update, finish |
| `FILE_OPS` | list_dir, read_file, write_file, move_file, delete_file, create_dir, task_update, finish |

Dynamic-mode escape hatch: `request_tool(name, reason)` → harness validates + adds to active subset for next step.
Phase re-classification: each step result re-runs classifier; subset swaps if TaskType changes.

Implementation: `core/code_tools/router.py` currently keeps the Code registry at exactly 42 real tools.
In the experimental dynamic mode, `request_tool` is synthetic so total model-visible capabilities remain ≤8. RevRec registers nine
additional finance adapters in its own shared-registry instance and uses the same bounded router.

---

**G4 — History processor — IMPLEMENTED (Aug 25, 2026)**
Context grows unboundedly across steps.
Decision: Before every `ollama.chat()`, compress history:
keep `[system_prompt] + last_5_observations + current_user_message`.
Older observations → trajectory log only (not discarded, not in context).

---

### HIGH

**G5 — No windowed file viewer**
Full file loads fill context on large files.
Decision: `read_file(path, offset=0, limit=100)` — returns lines [offset, offset+limit].
Append: `"[N lines above | M lines below — use offset/limit to navigate]"`

**G6 — No edit linting + rollback**
Syntax errors silently persist after write/edit.
Decision: post-write gate: `py_compile` → on fail: auto-revert + error message + `"DO NOT re-run write_file — fix the syntax error first"`.
Extended: `flake8 --select=E9,F8` (errors only, not style).

**G7 — Hierarchical error recovery — IMPLEMENTED (Aug 25, 2026)**
All errors treated identically.
Decision: `ErrorClass` enum → tiered dispatcher:

| Class | Trigger | Response |
|---|---|---|
| `FORMAT` | malformed tool_call | re-query with format hint, max 2x |
| `TIMEOUT` | run_command > 10s | kill + autosubmit partial diff |
| `IDENTICAL` | same tool_call 2x in a row | escalate to user |
| `CONTEXT` | context > 90% full | force history compression |
| `FATAL` | unrecoverable | capture git diff + finish with partial |

**G8 — Trajectory logger — IMPLEMENTED (Aug 25, 2026)**
No replay, no failure analysis.
Decision: per-step JSONL → `logs/trajectories/YYYYMMDD-HHMMSS.jsonl`
Fields per entry: `{step, timestamp, task_type, active_tools, tool_call, observation_raw, observation_truncated, token_count}`

**G9 — No typed action taxonomy**
Errors not classified for differentiated recovery (see G7).
Decision: `ErrorClass` enum (Pydantic-style) covers this alongside G7.

**G10 — No autosubmit fallback**
Catastrophic failures produce nothing.
Decision: on `FATAL` or step budget exhausted → `git diff HEAD` → force `finish()` with partial evidence.

---

### MEDIUM

**G11 — Adaptive step budget — IMPLEMENTED (Aug 25, 2026)**
Fixed `max_steps=20` for all tasks.
Decision:
```python
BUDGETS = {"simple": 10, "normal": 20, "complex": 50, "benchmark": 100}
budget = BUDGETS[classify_complexity(prompt)]
```
No-progress detection: 3 consecutive steps with no file change + no new observation → escalate.

**G12 — Tool descriptions not ACI-optimized**
Descriptions written for human readers, not 12B attention span.
Decision: rewrite each tool description to: verb-first, 1-sentence function, explicit input/output constraints, side-effects declared.

**G13 — No adaptive step budget** *(see G11)*

**G14 — No verification gate**
No test execution or regression check post-edit.
Decision: `finish()` requires: diff present + test command result (if available) + explicit summary of changes.

---

### LOW

**G15 — No MCP extension mechanism**
Tools hard-coded, not composable.
Decision: defer until P3.

**G16 — No workspace abstraction**
Local-only execution, no sandbox.
Decision: defer until P3.

---

## Tool Audit

| Tool | Decision | Constraint added |
|---|---|---|
| `read_file` | RESTRICT | `offset=0, limit=100` default; windowed |
| `write_file` | RESTRICT | py_compile gate; auto-revert on fail |
| `edit_file` | RESTRICT | unique match required; lint post-edit |
| `search_files` | RESTRICT | cap 30 results |
| `run_command` | RESTRICT | 10s timeout; 4000 char output cap |
| `verify_file` | MERGE | fold into write/edit post-conditions |
| `task_update` | KEEP | no change |
| `web_search` | RESTRICT | RESEARCH mode only |
| `web_fetch` | RESTRICT | 3000 char cap; RESEARCH mode only |
| `finish` | NEW | AgentFinish — requires diff + summary + verification |
| `list_dir` | NEW | 2-level depth; exclude `node_modules/`, `.git/` |
| `request_tool` | EXPERIMENTAL | escape hatch; always in the dynamic-mode subset only |

---

## Roadmap

### P0 — Before any benchmarking (~4 days total)

| # | Task | Effort |
|---|---|---|
| 1 | 128K Modelfile | 30 min |
| 2 | Observation truncation (3-tier, 4000 chars) | 1 day |
| 3 | Tool Router (classifier + registry + request_tool) | 2–3 days |

### P1 — Short term (~5 days)

| # | Task | Effort |
|---|---|---|
| 4 | Windowed file viewer (offset/limit) | 1–2 days |
| 5 | Edit linting + rollback (py_compile + flake8) | 1–2 days |
| 6 | History processor (last 5 observations) | 1 day |
| 7 | Hierarchical error recovery (ErrorClass + dispatcher) | 1–2 days |

### P2 — Medium term (~5 days)

| # | Task | Effort |
|---|---|---|
| 8 | Trajectory logger (JSONL per step) | 1 day |
| 9 | AgentFinish + verification gate | 2 days |
| 10 | Adaptive step budget + no-progress detection | 0.5 day |

### P3 — Later

| # | Task |
|---|---|
| 11 | Skill router (task → SKILL.md → tool activation) |
| 12 | AXIO-BFCL benchmark (20–30 labeled tasks, same model/machine/task) |

---

## Do Not Touch

```
Plan Mode + TaskTracker
Vision (base64 multimodal)
axio.py launcher
Ollama tool_call interface
skills/gemma4/ content
```

---

## Decision Framework

| Action | Items |
|---|---|
| KEEP | Plan Mode, TaskTracker, Vision, `axio.py`, Ollama tool_call, `skills/gemma4/` |
| IMPROVE | Tool descriptions (ACI), agent loop (5-phase), `ollama.chat` call (128K), step counter → adaptive budget |
| REPLACE | Full tool exposure → router · raw observations → truncated · full file read → windowed · generic error → tiered recovery |
| ADD | History processor · trajectory JSONL · AgentFinish · edit linting · task classifier · `list_dir` · `request_tool` · 128K modelfile |
| DEFER | MCP extensions · workspace abstraction · fine-tuning/LoRA · SWE-bench full eval · multi-agent |

---

## SOTA Reference

| Level | Description | Target score |
|---|---|---|
| 0 | No harness | — |
| 1 | Basic loop, no safety | 0–40 |
| 2 | Truncation + bounded tools | 40–60 |
| 3 | History + recovery + logging | 60–75 |
| 4 | Verification + adaptive budget + benchmark | 75–88 |
| 5 | Full ACI + SKILL routing + AXIO-BFCL | 88–100 |

Current implementation: Level 4 feature set (bounded routing, history, recovery, trajectory,
verification, and adaptive budgets). No new benchmark score is claimed until the evaluation suite
is run against live models.

---

## Source Attribution

| Finding | Source |
|---|---|
| ACI principles (bounded output, persistent state, guarded destructive) | SWE-agent `agents.py` + `tools.py` |
| Windowed file reader (100-line window) | SWE-agent |
| Linting gate (flake8 subset) | SWE-agent |
| `last_n_observations` history processor | SWE-agent |
| Per-step JSONL trajectory | SWE-agent |
| Error recovery table | SWE-agent |
| 0-tool simplicity → 74% SWE-bench | mini-SWE-agent |
| Typed actions (Pydantic) + autosubmit fallback | OpenHands |
| Plan Mode validation + phase-based tool exposure | Cline |
| 128K modelfile pattern | OpenCode |
| Extension-based tool activation (contextual) | Goose |
| Tool count degradation on 12B models | Assessment doc §6, §12 |
