#!/usr/bin/env python3
"""Print the Python environment AXIO Code would select for a workspace."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.coding_skills import inspect_python_environment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", nargs="?", default=str(PROJECT_ROOT))
    args = parser.parse_args()
    print(inspect_python_environment(args.workspace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
