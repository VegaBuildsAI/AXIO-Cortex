# AXIO Console UI

The AXIO UI is a local-only, single-window interface styled in the **AXIO dark theme**
(the palette of [axiostaging.com](https://www.axiostaging.com)). It puts **Chat**, **Cowork**,
and **Code** in one window:

- **Left rail** — brand, New chat / New build, saved conversations (grouped by date), the
  **backend launcher**, live **status chips**, and the user footer.
- **Chat dock** (persistent, always visible) — ask questions, search, and review docs while you build.
- **Stage** (full-screen) — switch between **Cowork** and **Code**. Code is a structured workspace:
  file tree, background-jobs panel, and a Console / Agents / Changes activity panel (tool timeline,
  diffs, approvals). It mirrors what the terminal Code agent does.

## Backend launcher (from the UI)

The rail's **Backend** control switches the whole session at runtime, no restart:

| Choice          | Effect |
|-----------------|--------|
| **Gemma local** | `LOCAL_ONLY` on — Chat, Cowork **and** Code all run locally on Ollama `gemma4:12b`. No API key needed. |
| **Local + API** | Chat/Cowork stay local; **Code boosts to the Claude API** (`CLAUDE_MODEL`). Requires `ANTHROPIC_API_KEY`. |

Backed by `GET/POST /api/runtime-mode` (an in-process override in `core/runtime_mode.py` that
defaults from the env-time `LOCAL_ONLY`). The stage label and composer model-pill update live.

## Routing

| Mode | Backend |
|---|---|
| Chat   | Local Ollama, `gemma4:12b` |
| Cowork | Local Ollama, `gemma4:12b` |
| Code   | Claude API (`CLAUDE_MODEL`) — or local `gemma4:12b` when **Gemma local** is selected |

## Status chips

`GET /api/health` reports **Ollama**, **Claude**, **Postgres** (only when
`AXIO_MEMORY_BACKEND=postgres`), and **SearXNG** liveness; the rail shows them as chips
(cyan = up, dim = down/disabled).

## First-time setup

From `axio-console-v2.1`:

```powershell
copy .env.example .env
ollama pull gemma4:12b

py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

cd ui
npm install
```

Add a valid `ANTHROPIC_API_KEY` to `.env` to enable the **Local + API** Code path.

## Launch

```powershell
.\run_ui.cmd
```

The launcher starts both local processes and opens:

```text
http://localhost:3000
```

The API listens only on `http://127.0.0.1:8765` (docs at `http://127.0.0.1:8765/api/docs`).

## Local data

UI conversations and workspace registrations are stored under `%USERPROFILE%\.axio\ui`.
API keys remain in the Python backend and are never sent to the browser.

## Workspace safety

- The frontend receives opaque file identifiers.
- File operations are restricted to the active workspace.
- `.env`, `.git`, virtual environments, and dependency directories are protected.
- Commands, writes, overwrites, and deletions require explicit approval in Code mode.
- Code mode fails closed if the Claude API is unavailable (in **Local + API** mode).

## Multi-agent orchestrator (Agents panel)

Toggle **⚡ Multi-agent** in the Code toolbar to run the task through the `harness/`
multi-agent orchestrator instead of the flat single-agent loop. The plan (phases + agent
roster) and the live per-step flow (dispatch → done / fallback / skip) stream to the
**Agents** panel over SSE (`agent_plan` / `agent_event`). This path uses the full 42-tool
registry with the real risk/approval gate — approvals appear in the **Changes** tab.

Backed by `POST /api/conversations/{id}/messages` with `orchestrate: true`; the bridge is
`web_api/services.py::_code_worker_orchestrated` → `harness/planner.run_orchestrated`
(with `on_plan`/`on_event` hooks added to the orchestrator).

## Background jobs

Long-running dev servers/watchers (`npm dev/watch`, launched detached by
`core/code_tools/node_tools.py`) are tracked in `core/code_tools/job_registry.py` and
surfaced in the **Background jobs** panel. Endpoints: `GET /api/jobs`,
`POST /api/jobs/{id}/stop`, `GET /api/jobs/{id}/log`. Jobs are visible in the process that
launched them (the `web_api` process for the orchestrated Code path).
