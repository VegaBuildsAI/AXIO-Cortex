"""Compatibility alias for Claude's experimental Gemma Code entrypoint.

The implementation is intentionally unified in modes.code so local Ollama and
Claude share the same skills, 18-tool registry, permissions, audit, memory, and
verification gate.
"""

from modes.code import TOOLS, TOOLS_CLAUDE, run

__all__ = ["TOOLS", "TOOLS_CLAUDE", "run"]
