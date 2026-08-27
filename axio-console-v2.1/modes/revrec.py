"""
AXIO RevRec Mode
ASC 606 / IFRS 15 revenue recognition domain specialist.
Wraps the existing rev_agent.py — its domain expertise and Excel tooling are
registered into the shared dynamic tool router and verification harness.

Knowledge base: KPMG Revenue for Software and SaaS Handbook (Dec 2025)
"""

import sys
from pathlib import Path

from core.ui import mode_banner, YELLOW, RESET, GREEN, lo, ok, err
from core.mode_memory import ModeMemorySession


def run():
    """Entry point called by axio.py. Delegates to rev_agent.main()."""
    mode_banner(
        "revrec",
        "ASC 606 / IFRS 15 specialist  |  Excel models  |  KPMG Handbook Dec 2025",
    )

    # rev_agent.py lives in the axio-console root — add it to the path
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        import rev_agent
        memory = ModeMemorySession("revrec")
        original_prompt = rev_agent.SYSTEM_PROMPT
        prefix = memory.prefix("ASC 606 IFRS 15 revenue recognition")
        if prefix:
            rev_agent.SYSTEM_PROMPT = prefix.strip() + "\n\n" + original_prompt
        try:
            rev_agent.main()
        finally:
            rev_agent.SYSTEM_PROMPT = original_prompt
            memory.store()
    except ImportError:
        print(f"  {err('rev_agent.py not found in axio-console root.')}\n")
    except SystemExit:
        pass   # rev_agent calls sys.exit on quit — swallow cleanly
    except Exception as e:
        print(f"  {err(f'RevRec error: {e}')}\n")
