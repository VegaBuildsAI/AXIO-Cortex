"""
AXIO Cowork Mode
File-aware workspace assistant with intelligent model routing.
Equivalent to Claude Cowork — loads project files as context, auto-routes
prompts to the best model, and writes model output back to disk.

Commands:
  workspace <path>   Set the active project folder
  ls                 List files in workspace
  load <file>        Load a file into context
  unload <file>|all  Remove file(s) from context
  loaded             Show currently loaded files
  write <file>       Write last response's code block to a file
  route <prompt>     Preview routing without sending
  models             List configured models
  apikey             Check Claude API key status
  help / exit
"""

import os
import re
from pathlib import Path

from core.models  import OllamaClient, ClaudeClient, ModelRouter
from core.logger  import AuditLogger
from core.ui      import (
    mode_banner, divider, Spinner,
    CYAN, YELLOW, GREEN, RED, DIM, BOLD, RESET, ok, warn, err, hi, lo
)
from core.config       import TEXT_EXTENSIONS, MAX_FILE_CHARS, MODELS, CLAUDE_MODEL
from core.file_context import SESSION_CONTEXT


# ─────────────────────────────────────────────────────────
#  WORKSPACE STATE
# ─────────────────────────────────────────────────────────

class WorkspaceState:
    """Holds the active project folder and loaded file context."""

    def __init__(self):
        self.root:         Path | None = None
        self.loaded_files: dict        = {}   # rel_path → content
        self.last_response: str        = ""

    # ── workspace management ──────────────────────────────

    def set(self, path_str: str) -> str:
        p = Path(path_str.strip('"').strip("'"))
        if not p.exists():
            return err(f"Path not found: {p}")
        self.root         = p
        self.loaded_files = {}
        return ok(f"Workspace set: {p}")

    def list_files(self) -> str:
        if not self.root:
            return warn("No workspace set. Use: workspace <path>")
        files = [
            f for f in self.root.rglob("*")
            if f.is_file()
            and f.suffix in TEXT_EXTENSIONS
            and ".git"        not in f.parts
            and "__pycache__" not in f.parts
        ]
        if not files:
            return warn("No readable files found.")
        lines = [f"\n  {BOLD}Workspace:{RESET} {self.root}"]
        for f in sorted(files)[:40]:
            rel     = f.relative_to(self.root)
            loaded  = f"  {ok('[loaded]')}" if str(rel) in self.loaded_files else ""
            lines.append(f"    {rel}{loaded}")
        if len(files) > 40:
            lines.append(f"    {lo(f'... and {len(files)-40} more')}")
        return "\n".join(lines) + "\n"

    def load_file(self, filename: str) -> str:
        if not self.root:
            return warn("Set a workspace first: workspace <path>")
        target = self.root / filename.strip()
        if not target.exists():
            matches = list(self.root.rglob(filename.strip()))
            if matches:
                target = matches[0]
            else:
                return err(f"File not found: {filename}")
        content = target.read_text(encoding="utf-8", errors="replace")
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS] + f"\n... [truncated at {MAX_FILE_CHARS} chars]"
        rel = str(target.relative_to(self.root))
        self.loaded_files[rel] = content
        # sync to session-wide context so RevRec / Code see the same files
        SESSION_CONTEXT._add_file(target)
        return ok(f"Loaded: {rel} ({len(content):,} chars)")

    def unload_file(self, key: str) -> str:
        if key == "all":
            self.loaded_files = {}
            SESSION_CONTEXT.clear()
            return ok("All files unloaded.")
        if key in self.loaded_files:
            del self.loaded_files[key]
            SESSION_CONTEXT.remove(key)
            return ok(f"Unloaded: {key}")
        return warn(f"Not loaded: {key}")

    def write_output(self, filename: str) -> str:
        if not self.last_response:
            return warn("No previous response to write.")
        if not self.root:
            return warn("Set a workspace first: workspace <path>")
        target = self.root / filename.strip()
        target.parent.mkdir(parents=True, exist_ok=True)
        code_blocks = re.findall(r"```(?:\w+)?\n([\s\S]*?)```", self.last_response)
        content = code_blocks[0] if code_blocks else self.last_response
        target.write_text(content, encoding="utf-8")
        return ok(f"Written: {target}")

    def context_block(self) -> str:
        # Start from workspace-loaded files (content already cached)
        all_files = dict(self.loaded_files)

        # Merge SESSION_CONTEXT files not already present
        for p in SESSION_CONTEXT.files:
            key = str(p)
            if key not in all_files:
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
                    all_files[key] = content
                except Exception:
                    all_files[key] = f"[could not read: {p}]"

        if not all_files:
            return ""
        parts = ["\n\n--- WORKSPACE CONTEXT ---"]
        for fname, content in all_files.items():
            parts.append(f"\n## File: {fname}\n```\n{content}\n```")
        parts.append("--- END WORKSPACE CONTEXT ---\n")
        return "\n".join(parts)


# ─────────────────────────────────────────────────────────
#  HELP
# ─────────────────────────────────────────────────────────
HELP = f"""
{BOLD}Workspace commands:{RESET}
  {YELLOW}workspace <path>{RESET}    Set active project folder
  {YELLOW}ls{RESET}                  List workspace files
  {YELLOW}load <file>{RESET}         Load a file into context
  {YELLOW}unload <file>|all{RESET}   Remove file(s) from context
  {YELLOW}loaded{RESET}              Show currently loaded files
  {YELLOW}write <file>{RESET}        Write last response code block to disk

{BOLD}Routing commands:{RESET}
  {YELLOW}route <prompt>{RESET}      Preview routing without sending
  {YELLOW}models{RESET}              List models and their roles
  {YELLOW}apikey{RESET}              Check Claude API key status

{BOLD}Console commands:{RESET}
  {YELLOW}help{RESET} / {YELLOW}exit{RESET}
"""


# ─────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────

def run():
    """Entry point called by axio.py."""
    mode_banner("cowork", "File-aware workspace assistant  |  Smart model routing")

    ollama = OllamaClient()
    logger = AuditLogger("cowork")
    ws     = WorkspaceState()

    # Claude (optional)
    try:
        claude    = ClaudeClient()
        claude_ok = True
        print(f"  Ollama: {ok('ONLINE ✓')}    Claude API: {ok('READY ✓')}\n")
    except Exception:
        claude    = None
        claude_ok = False
        print(f"  Ollama: {ok('ONLINE ✓')}    Claude API: {warn('OFFLINE')} {lo('(check .env)')}\n")

    print(f"  {lo('Type')} {YELLOW}help{RESET} {lo('for commands.  Type')} {YELLOW}exit{RESET} {lo('to quit.')}\n")
    logger.log_event("session_start")

    while True:
        # Build prompt prefix showing workspace/loaded state
        ws_label     = f"{DIM}({ws.root.name}){RESET} " if ws.root else ""
        loaded_label = f"{DIM}[{len(ws.loaded_files)} files]{RESET} " if ws.loaded_files else ""

        try:
            prompt = input(f"  {GREEN}COWORK›{RESET} {ws_label}{loaded_label}").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {ok('Goodbye.')}\n")
            break

        if not prompt:
            continue

        lower = prompt.lower()

        # ── commands ──────────────────────────────────────────────
        if lower == "exit":
            print(f"  {ok('Goodbye.')}\n")
            break

        elif lower == "help":
            print(HELP)

        elif lower == "models":
            print(f"\n  {BOLD}Configured models:{RESET}")
            for role, name in MODELS.items():
                print(f"    {CYAN}{name:<30}{RESET} {lo(role)}")
            print(f"    {CYAN}{CLAUDE_MODEL:<30}{RESET} {lo('cloud / premium')}\n")

        elif lower == "apikey":
            from core.config import CLAUDE_API_KEY
            if CLAUDE_API_KEY:
                print(f"  {ok('Set')} {lo(f'(sk-...{CLAUDE_API_KEY[-4:]})')}\n")
            else:
                env_hint = '$env:ANTHROPIC_API_KEY = "sk-ant-..."'
                print(f"  {warn('Not set.')} Run in PowerShell:\n"
                      f"    {lo(env_hint)}\n")

        elif lower.startswith("workspace "):
            print(f"  {ws.set(prompt[10:])}\n")
            print(ws.list_files())

        elif lower == "ls":
            print(ws.list_files())

        elif lower == "browse":
            print(f"  {SESSION_CONTEXT.load_browse_folder()}\n")
            # if workspace is set, try to cache content for files inside it
            if ws.root:
                for p in SESSION_CONTEXT.files:
                    try:
                        rel = str(p.relative_to(ws.root))
                        if rel not in ws.loaded_files:
                            ws.load_file(rel)
                    except ValueError:
                        pass  # file outside workspace root — SESSION_CONTEXT tracks it

        elif lower in ("browse files", "browse file"):
            print(f"  {SESSION_CONTEXT.load_browse_files()}\n")
            if ws.root:
                for p in SESSION_CONTEXT.files:
                    try:
                        rel = str(p.relative_to(ws.root))
                        if rel not in ws.loaded_files:
                            ws.load_file(rel)
                    except ValueError:
                        pass

        elif lower.startswith("load "):
            print(f"  {ws.load_file(prompt[5:])}\n")

        elif lower.startswith("unload "):
            print(f"  {ws.unload_file(prompt[7:])}\n")

        elif lower == "loaded":
            if ws.loaded_files:
                print(f"\n  {BOLD}Loaded files:{RESET}")
                for f in ws.loaded_files:
                    print(f"    {ok(f)}")
                print()
            else:
                print(f"  {lo('No files loaded.')}\n")

        elif lower == "context":
            print(SESSION_CONTEXT.list_str())

        elif lower.startswith("write "):
            print(f"  {ws.write_output(prompt[6:])}\n")

        elif lower.startswith("route "):
            sub_prompt    = prompt[6:]
            route, picked = ModelRouter.detect(sub_prompt)
            print(f"\n  Route : {YELLOW}{route}{RESET}")
            print(f"  Model : {CYAN}{picked}{RESET}\n")

        # ── model call ───────────────────────────────────────────
        else:
            route, picked = ModelRouter.detect(prompt)
            context       = ws.context_block()
            full_prompt   = f"{context}\n\nUser: {prompt}" if context else prompt

            print(f"  {lo(f'→ {route} | {picked}')}")
            divider()

            result_text = ""
            elapsed     = 0.0

            if route == "premium" and claude_ok:
                # Use Claude API for complex / PDF tasks
                print(f"\n  {CYAN}[claude-sonnet]{RESET} ", end="", flush=True)
                try:
                    result_text = claude.chat_stream_raw(
                        [{"role": "user", "content": full_prompt}],
                        system="You are AXIO Cowork, an expert file-aware coding assistant.",
                    )
                except Exception as e:
                    print(f"\n  {err(f'Claude error: {e}')}\n")
                    continue
            else:
                # Use Ollama (generate endpoint for workspace-aware prompts)
                if not ollama.is_running():
                    print(f"  {err('Ollama offline. Run: ollama serve')}\n")
                    continue
                try:
                    result_text, elapsed = ollama.generate_stream(picked, full_prompt)
                except Exception as e:
                    print(f"  {err(f'Error: {e}')}\n")
                    continue

            divider()
            print()

            ws.last_response = result_text
            logger.log_turn(
                prompt, result_text, picked,
                route=route, elapsed=elapsed,
                workspace=str(ws.root) if ws.root else None,
                loaded_files=list(ws.loaded_files.keys()),
            )
