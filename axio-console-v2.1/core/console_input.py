"""Shared bounded multiline input for AXIO terminal modes."""

from __future__ import annotations

from collections.abc import Callable

from core.config import INPUT_MAX_CHARS
from core.ui import lo


PASTE_COMMANDS = frozenset({"paste", "multiline", "/paste", "/multiline"})


def is_multiline_command(value: str) -> bool:
    """Return whether a normal console line requests multiline capture."""
    return value.strip().lower() in PASTE_COMMANDS


def read_multiline_input(
    input_fn: Callable[[str], str] | None = None,
    max_chars: int = INPUT_MAX_CHARS,
) -> str:
    """Capture complete lines until ``::end`` without silent truncation.

    Windows terminals deliver a multiline paste to ``input()`` one line at a
    time.  This function deliberately consumes those lines as one message.
    Leading, trailing, and blank lines inside the capture are preserved.
    """
    if max_chars < 1:
        raise ValueError("Multiline input limit must be at least 1 character.")

    reader = input_fn or input
    print(
        f"  {lo(f'Multiline input (maximum {max_chars:,} characters).')}\n"
        f"  {lo('Paste the complete text, then write ::end on a new line.')}\n"
        f"  {lo('Write ::cancel on a new line to discard it.')}"
    )

    lines: list[str] = []
    size = 0
    while True:
        try:
            line = reader("  ... ")
        except EOFError:
            break

        marker = line.strip().lower()
        if marker == "::end":
            break
        if marker == "::cancel":
            return ""

        next_size = size + len(line) + (1 if lines else 0)
        if next_size > max_chars:
            raise ValueError(
                f"Multiline input exceeds {max_chars:,} characters. "
                "Save it as a file and load it as context, or raise "
                "AXIO_INPUT_MAX_CHARS."
            )
        lines.append(line)
        size = next_size

    return "\n".join(lines)


def capture_summary(value: str) -> str:
    """Return a concise, testable summary of a captured message."""
    return f"Captured {len(value):,} characters across {value.count(chr(10)) + 1} line(s)."
