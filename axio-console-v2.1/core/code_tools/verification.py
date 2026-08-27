"""Evidence extraction and completion-gate tool for AXIO Code."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Sequence

from .registry import CodeTool, ToolResult

if TYPE_CHECKING:
    from .registry import CodeToolRegistry


_NPM_PATTERN = re.compile(r"\bnpm(?:\.cmd)?\s+(?:run\s+)?([\w:.-]+)", re.IGNORECASE)
_ARTIFACT_PATTERNS = {
    "artifact:docx": re.compile(r"(?i)(?:\.docx\b|\bword\b|documento\s+(?:de\s+)?word)"),
    "artifact:xlsx": re.compile(r"(?i)(?:\.xlsx\b|\bexcel\b|hoja\s+de\s+c[aá]lculo|libro\s+(?:de\s+)?excel)"),
    "artifact:pptx": re.compile(r"(?i)(?:\.pptx\b|\bpowerpoint\b|presentaci[oó]n\s+(?:de\s+)?powerpoint|\bppt\b)"),
    "artifact:pdf": re.compile(r"(?i)(?:\.pdf\b|\bpdf\b|documento\s+pdf|reporte\s+pdf)"),
    "artifact:txt": re.compile(r"(?i)(?:\.txt\b|archivo\s+de\s+texto|text\s+file)"),
}


def normalize_check_id(value: str) -> str:
    item = value.strip()
    if not item:
        return ""
    if item.startswith(("npm:", "python:")):
        return item.lower() if item.startswith("npm:") else item
    npm_match = _NPM_PATTERN.search(item)
    if npm_match:
        script = npm_match.group(1).lower()
        if script not in {"install", "ci", "i", "start", "dev", "run"} and not script.startswith("-"):
            return f"npm:{script}"
    return item


def extract_verification_requirements(text: str) -> tuple[str, ...]:
    checks: set[str] = set()
    for match in _NPM_PATTERN.finditer(text or ""):
        script = match.group(1).lower()
        if script not in {"install", "ci", "i", "start", "dev", "run"} and not script.startswith("-"):
            checks.add(f"npm:{script}")
    return tuple(sorted(checks))


def extract_artifact_requirements(text: str) -> tuple[str, ...]:
    """Infer only explicitly requested final artifact formats from the user task."""
    return tuple(sorted(
        check_id for check_id, pattern in _ARTIFACT_PATTERNS.items()
        if pattern.search(text or "")
    ))


def verification_ids_from_command(command: str) -> tuple[str, ...]:
    lowered = command.casefold()
    if not any(word in lowered for word in ("test", "build", "verify", "check", "lint")):
        return ()
    return extract_verification_requirements(command)


def make_verification_gate_tool(registry: "CodeToolRegistry") -> CodeTool:
    def verification_gate(required_checks: Sequence[str] | None = None, summary: str = "") -> ToolResult:
        del summary
        return registry.evaluate_gate(required_checks)

    return CodeTool(
        "verification_gate",
        "Confirm that every required check has succeeded after mutations. Must pass before TASK_COMPLETE.",
        {
            "type": "object",
            "properties": {
                "required_checks": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
            },
        },
        verification_gate,
        "read",
    )
