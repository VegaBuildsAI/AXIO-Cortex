"""
AXIO RevRec Mode
ASC 606 / IFRS 15 revenue recognition domain specialist.
Wraps the existing rev_agent.py -- all the domain expertise and Excel tooling
lives there; this module plugs it cleanly into the AXIO platform launcher.

Knowledge base: KPMG Revenue for Software and SaaS Handbook (Dec 2025)
"""

import sys
from datetime import datetime
from pathlib import Path

from core.ui    import mode_banner, YELLOW, RESET, GREEN, lo, ok, err
from core.memory import MemoryManager, _handle_memory_cmd


def run():
    """Entry point called by axio.py. Delegates to rev_agent.main()."""
    mode_banner(
        "revrec",
        "ASC 606 / IFRS 15 specialist  |  Excel models  |  KPMG Handbook Dec 2025",
    )

    # rev_agent.py lives in the project root -- add it to the path
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # IOAF: initialise memory for revrec mode
    mem = MemoryManager(mode="revrec")

    # Build a memory prefix from past deal context and inject into
    # rev_agent's SYSTEM_PROMPT before starting the interactive loop
    memory_prefix = mem.build_memory_prefix("revenue recognition ASC 606 client deal")

    rev_agent = None
    try:
        import rev_agent

        if memory_prefix:
            rev_agent.SYSTEM_PROMPT = memory_prefix + "\n\n" + rev_agent.SYSTEM_PROMPT

        # Wire the /memory command handler and per-turn auto-facts into rev_agent's REPL
        def _revrec_handler(cmd: str):
            if cmd.startswith("__auto_facts__ "):
                mem.auto_update_facts(cmd[len("__auto_facts__ "):], "")
            else:
                _handle_memory_cmd(cmd, mem)
        rev_agent._memory_cmd_handler = _revrec_handler

        rev_agent.main()

    except ImportError:
        print(f"  {err('rev_agent.py not found in project root.')}\n")
        return
    except SystemExit:
        pass   # rev_agent calls sys.exit on quit -- swallow cleanly
    except Exception as e:
        print(f"  {err(f'RevRec error: {e}')}\n")
    finally:
        # IOAF: always archive the session, even if rev_agent raised
        _revrec_session = {
            "name":     f"revrec_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "mode":     "revrec",
            "model":    getattr(rev_agent, "AGENT_MODEL", "qwen3:14b") if rev_agent else "qwen3:14b",
            "created":  datetime.now().isoformat(),
            "updated":  datetime.now().isoformat(),
            "messages": [
                {
                    "role":    "user",
                    "content": "RevRec session completed. ASC 606 / IFRS 15 analysis.",
                }
            ],
        }
        mem.store_session(_revrec_session)
