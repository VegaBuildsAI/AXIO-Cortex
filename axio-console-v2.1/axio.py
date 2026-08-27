#!/usr/bin/env python3
"""
AXIO Platform - Unified AI Launcher
Claude-inspired three-tier architecture on local Ollama + Claude API.

  AXIO Chat    -> General-purpose conversational AI with session memory
  AXIO Cowork  -> File-aware workspace assistant with smart model routing
  AXIO Code    -> Autonomous coding agent (tool-calling, files, PowerShell)
  AXIO RevRec  -> ASC 606 / IFRS 15 domain specialist (Excel, PDF, memos)

Usage:
  py axio.py                  Interactive mode selector
  py axio.py chat             Launch Chat directly
  py axio.py cowork           Launch Cowork directly
  py axio.py code             Launch Code directly
  py axio.py revrec           Launch RevRec directly
  py axio.py benchmark        Run model benchmark suite

  py axio.py --claude chat    Force Claude Sonnet for every message in Chat
  py axio.py --claude code    Force Claude Sonnet for every task in Code
  py axio.py --claude cowork  Force Claude Sonnet in Cowork
"""

import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Dependency check
_MISSING = []
for _pkg, _imp in [("requests", "requests"), ("python-dotenv", "dotenv")]:
    try:
        __import__(_imp)
    except ImportError:
        _MISSING.append(_pkg)
if _MISSING:
    import subprocess
    print(f"Installing: {', '.join(_MISSING)}")
    subprocess.run([sys.executable, "-m", "pip", "install"] + _MISSING + ["--quiet"])

from core.ui import (
    AXIO_BANNER, CYAN, YELLOW, GREEN, PURPLE, DIM, BOLD, RESET, ok, warn, err, lo
)
from core.config import CLAUDE_API_KEY, CLAUDE_MODEL, MODELS


PLATFORM_HEADER = (
    "\n" + CYAN + BOLD +
    "  +----------------------------------------------------------------------+\n"
    "  |                      AXIO  AI  PLATFORM                             |\n"
    "  |          Local Ollama + Claude API  .  Unified Architecture         |\n"
    "  +----------------------------------------------------------------------+" +
    RESET + "\n"
)

MODE_MENU = (
    "\n  " + BOLD + "Select a mode:" + RESET + "\n\n"
    "  " + CYAN + "[1]" + RESET + "  " + BOLD + "AXIO Chat" + RESET +
    "    -  General-purpose conversational AI with session memory\n"
    "  " + GREEN + "[2]" + RESET + "  " + BOLD + "AXIO Cowork" + RESET +
    "  -  File-aware workspace assistant  .  smart model routing\n"
    "  " + YELLOW + "[3]" + RESET + "  " + BOLD + "AXIO Code" + RESET +
    "    -  Autonomous coding agent  .  tool-calling  .  PowerShell\n"
    "  " + PURPLE + "[4]" + RESET + "  " + BOLD + "AXIO RevRec" + RESET +
    "  -  ASC 606 specialist  .  Excel models  .  KPMG Handbook\n\n"
    "  " + DIM + "[b]" + RESET + "  Benchmark models   " +
    DIM + "[q]" + RESET + "  Quit\n"
)


def print_system_status():
    from core.models import OllamaClient
    ollama = OllamaClient()
    if ollama.is_running():
        mdls  = ollama.list_models()
        names = [m["name"] for m in mdls[:4]]
        extra = f" +{len(mdls)-4} more" if len(mdls) > 4 else ""
        print(f"  {DIM}Ollama :{RESET}  {ok('ONLINE')}  {DIM}({', '.join(names)}{extra}){RESET}")
    else:
        print(f"  {DIM}Ollama :{RESET}  {err('OFFLINE')}  {DIM}Run: ollama serve{RESET}")
    if CLAUDE_API_KEY:
        print(f"  {DIM}Claude :{RESET}  {ok('READY')}   {DIM}({CLAUDE_MODEL}){RESET}")
    else:
        print(f"  {DIM}Claude :{RESET}  {warn('NO KEY')}  {DIM}Set ANTHROPIC_API_KEY in .env{RESET}")
    print(
        f"  {DIM}Routing:{RESET}  "
        f"chat->{YELLOW}{MODELS['chat']}{RESET}  "
        f"coding->{YELLOW}{MODELS['coding']}{RESET}  "
        f"reasoning->{YELLOW}{MODELS['reasoning']}{RESET}"
    )
    print()


def run_benchmark():
    bench = ROOT / "scripts" / "benchmark_models.py"
    if not bench.exists():
        print(f"  {err(f'Benchmark script not found: {bench}')}\n")
        return
    import subprocess
    subprocess.run([sys.executable, str(bench)])


CHOICE_MAP = {
    "1": "chat",    "chat":      "chat",
    "2": "cowork",  "cowork":    "cowork",
    "3": "code",    "code":      "code",
    "4": "revrec",  "revrec":    "revrec",
    "b": "benchmark", "benchmark": "benchmark",
}


def launch_mode(mode, force_claude=False):
    mode = mode.strip().lower()
    try:
        if mode == "chat":
            from modes.chat import run
            run()
        elif mode == "cowork":
            from modes.cowork import run
            run()
        elif mode == "code":
            from modes.code import run
            run(force_claude_session=force_claude)
        elif mode == "revrec":
            from modes.revrec import run
            run()
        elif mode in ("benchmark", "b"):
            run_benchmark()
        else:
            print(f"  {err(f'Unknown mode: {mode}')}\n")
    except KeyboardInterrupt:
        print(f"\n  {ok('Returned to AXIO Platform.')}\n")
    except Exception as e:
        print(f"\n  {err(f'Mode error: {e}')}\n")
        import traceback; traceback.print_exc()


def interactive():
    print(AXIO_BANNER)
    print(PLATFORM_HEADER)
    print_system_status()
    while True:
        print(MODE_MENU)
        try:
            choice = input(f"  {CYAN}AXIO>{RESET} ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print(f"\n  {ok('Goodbye.')}\n"); break
        if choice in ("q", "quit", "exit"):
            print(f"\n  {ok('Goodbye.')}\n"); break
        mode = CHOICE_MAP.get(choice)
        if mode:
            print(); launch_mode(mode)
            print(PLATFORM_HEADER); print_system_status()
        else:
            hint = "Unknown choice: " + repr(choice) + "  -  enter 1, 2, 3, 4, b, or q"
            print(f"  {warn(hint)}\n")


def main():
    args = [a for a in sys.argv[1:] if a]

    # --claude flag: force every prompt through the Claude tier for this session
    force_claude = "--claude" in args
    if force_claude:
        os.environ["FORCE_CLAUDE"] = "1"
        args = [a for a in args if a != "--claude"]
        from core.config import CLAUDE_MODEL
        print(f"  {ok('Claude mode active')}  {lo(f'(all prompts -> {CLAUDE_MODEL})')}\n")

    if args:
        mode = args[0].lower()
        if mode in ("chat", "cowork", "code", "revrec", "benchmark", "b"):
            print(AXIO_BANNER)
            launch_mode(mode, force_claude=force_claude)
        else:
            print(f"  {err(f'Unknown mode: {mode}')}")
            sys.exit(1)
    else:
        interactive()


if __name__ == "__main__":
    main()
