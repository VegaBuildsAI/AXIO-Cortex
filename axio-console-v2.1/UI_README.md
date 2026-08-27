# AXIO Console UI

The AXIO UI is a local-only interface for Chat, Cowork, and Code.

## Routing

| Mode | Backend |
|---|---|
| Chat | Local Ollama, `qwen3:14b` |
| Cowork | Local Ollama, `qwen3:14b` |
| Code | Claude API, configured through `CLAUDE_MODEL` |

Code intentionally has no local model fallback.

## First-time setup

From `axio-console-v2.1`:

```powershell
copy .env.example .env
ollama pull qwen3:14b

py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

cd ui
npm install
```

Add a valid `ANTHROPIC_API_KEY` to `.env` to enable Code mode.

## Launch

Run:

```powershell
.\run_ui.cmd
```

The launcher starts both local processes and opens:

```text
http://localhost:3000
```

The API listens only on:

```text
http://127.0.0.1:8765
```

API documentation is available locally at:

```text
http://127.0.0.1:8765/api/docs
```

## Local data

UI conversations and workspace registrations are stored under:

```text
%USERPROFILE%\.axio\ui
```

API keys remain in the Python backend and are never sent to the browser.

## Workspace safety

- The frontend receives opaque file identifiers.
- File operations are restricted to the active workspace.
- `.env`, `.git`, virtual environments, and dependency directories are protected.
- Commands, writes, overwrites, and deletions require explicit approval in Code mode.
- Code mode fails closed if the Claude API is unavailable.
