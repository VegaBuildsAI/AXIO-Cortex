"""
AXIO Code Mode
Autonomous tool-calling coding agent — reads, writes, edits, searches,
and runs PowerShell, looping until the task is complete.
Equivalent to Claude Code — delegates multi-step coding tasks end-to-end.

Model: qwen3-coder:30b (local) with auto-upgrade to Claude for complex tasks.

Commands:
  tools          List all available tools
  model <name>   Switch active model
  model claude   Force Claude API for next task
  help / exit
"""

import json
import subprocess
from pathlib import Path

from core.models  import OllamaClient, ClaudeClient, ModelRouter
from core.logger  import AuditLogger
from core.ui      import (
    mode_banner, divider, Spinner,
    CYAN, YELLOW, GREEN, RED, DIM, BOLD, RESET, ok, warn, err, hi, lo
)
from core.config       import MODELS, CLAUDE_MODEL, MAX_ITERS, MAX_FILE_BYTES, TIMEOUT
from core.file_context import SESSION_CONTEXT
from core.mode_memory  import ModeMemorySession


# ─────────────────────────────────────────────────────────
#  TOOL SCHEMAS (sent to Ollama / Claude)
# ─────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the full contents of a file. Always read before editing.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Absolute path to the file"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file with new content. Creates parent directories automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":    {"type": "string", "description": "Absolute path to the file"},
                    "content": {"type": "string", "description": "Full content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Find and replace a specific string in a file. Read the file first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path":     {"type": "string"},
                    "old_text": {"type": "string", "description": "Exact text to find"},
                    "new_text": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and subdirectories at a given path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Directory path to list"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_dir",
            "description": "Create a directory and all necessary parent directories.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Permanently delete a single file.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Find files matching a glob pattern inside a directory tree.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string"},
                    "pattern":   {"type": "string", "description": "Glob pattern e.g. *.py"},
                },
                "required": ["directory", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_files",
            "description": "Search for a text pattern inside file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory":    {"type": "string"},
                    "pattern":      {"type": "string"},
                    "file_pattern": {"type": "string", "description": "Glob filter e.g. *.py"},
                },
                "required": ["directory", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a PowerShell command. Always asks user confirmation before executing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command":     {"type": "string"},
                    "working_dir": {"type": "string", "description": "Optional working directory"},
                },
                "required": ["command"],
            },
        },
    },
]

# Anthropic tool format (for Claude backend)
TOOLS_CLAUDE = [
    {
        "name":         t["function"]["name"],
        "description":  t["function"]["description"],
        "input_schema": t["function"]["parameters"],
    }
    for t in TOOLS
]


# ─────────────────────────────────────────────────────────
#  TOOL IMPLEMENTATIONS
# ─────────────────────────────────────────────────────────

def tool_read_file(path: str) -> str:
    p = Path(path)
    if not p.exists():     return f"ERROR: File not found: {path}"
    if not p.is_file():    return f"ERROR: Path is a directory: {path}"
    if p.stat().st_size > MAX_FILE_BYTES:
        return f"ERROR: File too large ({p.stat().st_size} bytes). Use grep_files."
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"ERROR reading file: {e}"

def tool_write_file(path: str, content: str) -> str:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"OK: Wrote {len(content):,} chars to {path}"
    except Exception as e:
        return f"ERROR writing file: {e}"

def tool_edit_file(path: str, old_text: str, new_text: str) -> str:
    p = Path(path)
    if not p.exists(): return f"ERROR: File not found: {path}"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        if old_text not in content:
            return f"ERROR: Text not found in {path}. Read the file first."
        p.write_text(content.replace(old_text, new_text, 1), encoding="utf-8")
        return f"OK: Edited {path}"
    except Exception as e:
        return f"ERROR editing file: {e}"

def tool_list_dir(path: str) -> str:
    p = Path(path)
    if not p.exists():  return f"ERROR: Path not found: {path}"
    if not p.is_dir():  return f"ERROR: Not a directory: {path}"
    try:
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = []
        for item in items[:80]:
            if item.is_dir():
                lines.append(f"  [DIR]  {item.name}/")
            else:
                lines.append(f"  [FILE] {item.name:<45} {item.stat().st_size:>10} bytes")
        total = len(list(p.iterdir()))
        if total > 80:
            lines.append(f"  ... ({total - 80} more items)")
        return "\n".join(lines) if lines else "(empty directory)"
    except Exception as e:
        return f"ERROR listing directory: {e}"

def tool_create_dir(path: str) -> str:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return f"OK: Created directory: {path}"
    except Exception as e:
        return f"ERROR creating directory: {e}"

def tool_delete_file(path: str) -> str:
    p = Path(path)
    if not p.exists():  return f"ERROR: File not found: {path}"
    if p.is_dir():      return f"ERROR: Path is a directory."
    try:
        p.unlink()
        return f"OK: Deleted {path}"
    except Exception as e:
        return f"ERROR deleting file: {e}"

def tool_search_files(directory: str, pattern: str) -> str:
    d = Path(directory)
    if not d.exists(): return f"ERROR: Directory not found: {directory}"
    try:
        matches = [
            str(m) for m in d.rglob(pattern)
            if ".git" not in m.parts and "__pycache__" not in m.parts
        ][:60]
        return f"Found {len(matches)} file(s):\n" + "\n".join(matches) if matches else f"No files matching '{pattern}'"
    except Exception as e:
        return f"ERROR searching files: {e}"

def tool_grep_files(directory: str, pattern: str, file_pattern: str = "*") -> str:
    d = Path(directory)
    if not d.exists(): return f"ERROR: Directory not found: {directory}"
    results = []
    for f in d.rglob(file_pattern):
        if not f.is_file() or ".git" in f.parts or "__pycache__" in f.parts:
            continue
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pattern.lower() in line.lower():
                    results.append(f"{f}:{i}:  {line.strip()}")
                if len(results) >= 50:
                    break
        except Exception:
            pass
        if len(results) >= 50:
            break
    return f"Found {len(results)} match(es):\n" + "\n".join(results) if results else f"No matches for '{pattern}'"

def tool_run_command(command: str, working_dir: str = None) -> str:
    print(f"\n  {YELLOW}[AGENT] Wants to run:{RESET}")
    print(f"  {lo(f'  {command}')}")
    if working_dir:
        print(f"  {lo(f'  cwd: {working_dir}')}")
    confirm = input(f"  Allow? (y/n): ").strip().lower()
    if confirm != "y":
        return "CANCELLED: User declined."
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=120, cwd=working_dir,
        )
        parts = []
        if result.stdout.strip(): parts.append(f"STDOUT:\n{result.stdout.strip()}")
        if result.stderr.strip(): parts.append(f"STDERR:\n{result.stderr.strip()}")
        if result.returncode != 0: parts.append(f"EXIT CODE: {result.returncode}")
        return "\n".join(parts) if parts else "(no output)"
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out after 120s"
    except Exception as e:
        return f"ERROR running command: {e}"


TOOL_MAP = {
    "read_file":    tool_read_file,
    "write_file":   tool_write_file,
    "edit_file":    tool_edit_file,
    "list_dir":     tool_list_dir,
    "create_dir":   tool_create_dir,
    "delete_file":  tool_delete_file,
    "search_files": tool_search_files,
    "grep_files":   tool_grep_files,
    "run_command":  tool_run_command,
}

def execute_tool(name: str, args: dict) -> str:
    fn = TOOL_MAP.get(name)
    if not fn: return f"ERROR: Unknown tool '{name}'"
    try:
        return fn(**args)
    except TypeError as e:
        return f"ERROR: Wrong arguments for {name}: {e}"
    except Exception as e:
        return f"ERROR: {e}"


# ─────────────────────────────────────────────────────────
#  SYSTEM PROMPT
# ─────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are AXIO Code — an autonomous file, code, and automation agent running on Windows.

You have tools to read/write/edit files, search code, manage directories, and run PowerShell commands.

## Rules
- Always read a file before editing it
- Always list a directory before creating files inside it
- Use absolute paths for everything
- Use run_command only when necessary (install packages, run tests, git)
- Complete all steps of a task before reporting done
- Never fabricate file contents — read first, then act

## When done, report
1. Summary of what was done
2. Files created or modified (full paths)
3. Any next steps the user should take
"""


# ─────────────────────────────────────────────────────────
#  AGENT LOOP — Ollama
# ─────────────────────────────────────────────────────────

def build_code_task(task: str, file_context: str = "", memory_prefix: str = "") -> str:
    parts = []
    if memory_prefix:
        parts.append(memory_prefix.strip())
    if file_context:
        parts.append(file_context.strip())
    if parts:
        parts.append(task)
        return "\n\n".join(parts)
    return task


# ─────────────────────────────────────────────────────────
#  Continue-nudge: stop the agent from ENDING on a planning
#  turn that has no tool call. The model must act, not narrate.
# ─────────────────────────────────────────────────────────
MAX_CONSEC_NUDGES = 2

_NUDGE = (
    "Continue working: call the tools needed to FINISH and VERIFY the task. "
    "Do not just describe what you will do — actually do it now. If the entire "
    "task is already complete and verified, reply with exactly TASK_COMPLETE "
    "followed by a short summary."
)


def _is_complete_signal(text: str) -> bool:
    t = (text or "").upper()
    return "TASK_COMPLETE" in t or "TAREA_COMPLETA" in t


def _strip_complete_signal(text: str) -> str:
    import re
    return re.sub(r"(?i)\b(TASK_COMPLETE|TAREA_COMPLETA)\b[:\-\s]*", "", text or "").strip()


def _run_ollama_agent(task: str, model: str, ollama: OllamaClient, logger: AuditLogger):
    import time
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": task},
    ]
    print(f"\n  {lo(f'model: {model} | max steps: {MAX_ITERS}')}\n")
    start = time.time()
    nudges = 0

    for iteration in range(MAX_ITERS):
        spinner = Spinner(f"[{model}] step {iteration + 1}").start()
        try:
            data = ollama.tool_call(model, messages, TOOLS)
            spinner.stop()
        except Exception as e:
            spinner.stop()
            print(f"  {err(f'Error: {e}')}")
            return f"Error: {e}"

        msg        = data.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        content    = msg.get("content", "").strip()

        if not tool_calls:
            if _is_complete_signal(content) or nudges >= MAX_CONSEC_NUDGES:
                elapsed = round(time.time() - start, 1)
                final = _strip_complete_signal(content)
                print(f"\n  {CYAN}[{model}]{RESET} {final}")
                print(f"\n  {lo(f'Done in {iteration+1} step(s), {elapsed}s')}\n")
                return final
            nudges += 1
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": _NUDGE})
            print(f"  {lo('(continue) sin herramientas; pidiendo al agente que ejecute...')}")
            continue

        nudges = 0
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})

        for tc in tool_calls:
            fn_def = tc.get("function", {})
            name   = fn_def.get("name", "")
            args   = fn_def.get("arguments", {})
            if isinstance(args, str):
                try:    args = json.loads(args)
                except: args = {}

            args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
            print(f"  {YELLOW}{name}{RESET}({args_str})")

            result   = execute_tool(name, args)
            preview  = result[:100].replace("\n", " ")
            ellipsis = "..." if len(result) > 100 else ""
            print(f"  {lo(f'  {preview}{ellipsis}')}")
            logger.log_tool(task, name, args, result, model)

            messages.append({"role": "tool", "content": result})

    message = f"Agent stopped: reached max {MAX_ITERS} steps"
    print(f"  {warn(message)}")
    return message


# ─────────────────────────────────────────────────────────
#  AGENT LOOP — Claude
# ─────────────────────────────────────────────────────────

def _run_claude_agent(task: str, claude: ClaudeClient, logger: AuditLogger):
    import time
    messages = [{"role": "user", "content": task}]
    print(f"\n  {lo(f'model: {CLAUDE_MODEL} (Claude API) | max steps: {MAX_ITERS}')}\n")
    start = time.time()
    nudges = 0

    for iteration in range(MAX_ITERS):
        spinner = Spinner(f"[Claude] step {iteration + 1}").start()
        try:
            resp = claude.tool_call(messages, TOOLS_CLAUDE, system=SYSTEM_PROMPT)
            spinner.stop()
        except Exception as e:
            spinner.stop()
            print(f"  {err(f'Claude error: {e}')}")
            return f"Claude error: {e}"

        if resp is None:
            spinner.stop()
            return "Claude returned no response"

        text_parts = [b.text for b in resp.content if b.type == "text"]
        tool_uses  = [b      for b in resp.content if b.type == "tool_use"]

        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use" or not tool_uses:
            final_text = "\n".join(text_parts).strip()
            if _is_complete_signal(final_text) or nudges >= MAX_CONSEC_NUDGES:
                elapsed = round(time.time() - start, 1)
                out = _strip_complete_signal(final_text)
                print(f"\n  {CYAN}[Claude]{RESET} {out}")
                print(f"\n  {lo(f'Done in {iteration+1} step(s), {elapsed}s')}\n")
                return out
            nudges += 1
            messages.append({"role": "user", "content": _NUDGE})
            print(f"  {lo('(continue) sin herramientas; pidiendo a Claude que ejecute...')}")
            continue

        nudges = 0
        tool_results = []
        for tu in tool_uses:
            args     = tu.input if isinstance(tu.input, dict) else {}
            args_str = ", ".join(f"{k}={repr(v)[:50]}" for k, v in args.items())
            print(f"  {YELLOW}{tu.name}{RESET}({args_str})")

            result   = execute_tool(tu.name, args)
            preview  = result[:100].replace("\n", " ")
            ellipsis = "..." if len(result) > 100 else ""
            print(f"  {lo(f'  {preview}{ellipsis}')}")
            logger.log_tool(task, tu.name, args, result, CLAUDE_MODEL)

            tool_results.append({
                "type": "tool_result", "tool_use_id": tu.id, "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    message = f"Stopped at max {MAX_ITERS} steps"
    print(f"  {warn(message)}")
    return message


# ─────────────────────────────────────────────────────────
#  HELP / BANNER
# ─────────────────────────────────────────────────────────
HELP = f"""
{BOLD}How to use:{RESET}
  Type any coding task in plain English. The agent will plan and execute it.

{BOLD}Example tasks:{RESET}
  create a FastAPI project in C:\\Users\\AXIO\\Projects\\myapp with /health endpoint
  read C:\\Users\\AXIO\\Projects\\myapp\\main.py and fix any bugs
  search C:\\Users\\AXIO\\Projects for all Python files that import requests
  add a /version endpoint to C:\\Users\\AXIO\\Projects\\myapp\\main.py

{BOLD}Commands:{RESET}
  {YELLOW}tools{RESET}              List all available tools
  {YELLOW}model <name>{RESET}       Switch model (default: {MODELS['coding']})
  {YELLOW}model claude{RESET}       Force Claude API for next task
  {YELLOW}help{RESET} / {YELLOW}exit{RESET}
"""


# ─────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────

def run(force_claude_session: bool = False):
    """Entry point called by axio.py.

    force_claude_session=True  ->  every task uses Claude Sonnet for the
    entire session (set via --claude flag or FORCE_CLAUDE=1 in .env).
    """
    import os
    mode_banner("code", "Autonomous coding agent  |  Tool-calling  |  Files + PowerShell")

    ollama     = OllamaClient()
    logger     = AuditLogger("code")
    memory     = ModeMemorySession("code")
    model      = MODELS["coding"]

    # Persistent Claude mode: CLI flag OR env var
    _env_force = os.getenv("FORCE_CLAUDE", "").strip() in ("1", "true", "yes")
    force_claude = force_claude_session or _env_force

    # Claude (optional)
    try:
        claude    = ClaudeClient()
        claude_ok = True
        print(f"  Local agent: {ok('READY')} ({model})    Claude API: {ok('READY ✓')}\n")
    except Exception:
        claude    = None
        claude_ok = False
        print(f"  Local agent: {ok('READY')} ({model})    Claude API: {warn('OFFLINE')}\n")

    if force_claude and claude_ok:
        print(f"  {ok('Claude Sonnet mode')}  {lo('— all tasks will use Claude API')}\n")
    elif force_claude and not claude_ok:
        print(f"  {warn('--claude requested but Claude API is offline. Falling back to Ollama.')}\n")
        force_claude = False

    _session_claude = force_claude   # remember original flag for sticky behaviour

    print(f"  {lo('Type')} {YELLOW}help{RESET} {lo('for examples.  Type')} {YELLOW}exit{RESET} {lo('to quit.')}\n")

    while True:
        ctx_label    = f"{DIM}[{SESSION_CONTEXT.count} files]{RESET} " if SESSION_CONTEXT.count else ""
        claude_label = f" {lo('[Claude]')}" if force_claude else ""
        try:
            task = input(f"  {YELLOW}CODE›{RESET}{claude_label} {ctx_label}").strip()
        except (KeyboardInterrupt, EOFError):
            memory.store(ollama_client=ollama)
            print(f"\n  {ok('Goodbye.')}\n")
            break

        if not task:
            continue

        lower = task.lower()

        if memory.handle_command(task):
            continue

        if lower == "exit":
            memory.store(ollama_client=ollama)
            print(f"  {ok('Goodbye.')}\n")
            break

        elif lower == "help":
            print(HELP)

        elif lower == "tools":
            print(f"\n  {BOLD}Available tools:{RESET}")
            for t in TOOLS:
                fn = t["function"]
                print(f"  {YELLOW}{fn['name']:<20}{RESET} {fn['description'][:70]}")
            print()

        # ── shared file context ───────────────────────────────────
        elif lower == "browse":
            print(SESSION_CONTEXT.load_browse_folder())

        elif lower in ("browse files", "browse file"):
            print(SESSION_CONTEXT.load_browse_files())

        elif lower.startswith("load "):
            print(SESSION_CONTEXT.load_path(task[5:].strip()))

        elif lower in ("loaded", "context"):
            print(SESSION_CONTEXT.list_str())

        elif lower in ("unload", "clear files"):
            print(SESSION_CONTEXT.clear())

        # ── model switching ───────────────────────────────────────
        elif lower == "model claude":
            if claude_ok:
                force_claude = True
                print(f"  {ok(f'Next task will use {CLAUDE_MODEL} (Claude API)')}")
                print()
            else:
                print(f"  {err('Claude API not available. Add ANTHROPIC_API_KEY to .env')}")
                print()

        elif lower.startswith("model "):
            model        = task[6:].strip()
            force_claude = _session_claude
            print(f"  Model set to: {CYAN}{model}{RESET}\n")

        # ── agent task ────────────────────────────────────────────
        else:
            # inject session file context into the task prompt
            file_context = SESSION_CONTEXT.inject("", mode="list").strip() if SESSION_CONTEXT.count else ""
            memory_prefix = memory.prefix(task)
            final_task = build_code_task(task, file_context, memory_prefix)
            use_claude = force_claude or (claude_ok and ModelRouter.needs_claude(final_task))
            if not _session_claude:
                force_claude = False

            result_text = ""
            if use_claude and claude_ok:
                print(f"  {lo('-> routing: Claude API (complex task)')}")
                result_text = _run_claude_agent(final_task, claude, logger)
            else:
                if not ollama.is_running():
                    print(f"  {err('Ollama offline. Run: ollama serve')}\n")
                    continue
                result_text = _run_ollama_agent(final_task, model, ollama, logger)

            if result_text:
                memory.record_turn(
                    task,
                    result_text,
                    model=CLAUDE_MODEL if use_claude and claude_ok else model,
                    metadata={
                        "backend": "claude" if use_claude and claude_ok else "ollama",
                        "file_context_count": str(SESSION_CONTEXT.count),
                    },
                )
