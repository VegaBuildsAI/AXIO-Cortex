"""Evidence extraction and completion-gate tool for AXIO Code."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Sequence

from .registry import CodeTool, ToolResult

if TYPE_CHECKING:
    from .registry import CodeToolRegistry


_NPM_PATTERN = re.compile(r"\bnpm(?:\.cmd)?\s+(?:run\s+)?([\w:.-]+)", re.IGNORECASE)
_PYCOMPILE_PATTERN = re.compile(r"py_compile", re.IGNORECASE)
_SELFTEST_PATTERN = re.compile(r"--self[-_]?test\b", re.IGNORECASE)
_PYTEST_PATTERN = re.compile(r"(?:\bpytest\b|-m\s+pytest\b|-m\s+unittest\b)", re.IGNORECASE)
# A python interpreter (py / python / python3 / a path to python[.exe]) running a .py file.
_PYRUN_PATTERN = re.compile(
    r"(?:^|[\\/\s\"'])(?:py|python|python3|[^\s\"']*python(?:\.exe)?)\s+(?:-[^\s]+\s+)*"
    r"[\"']?([^\s\"']+\.py)[\"']?",
    re.IGNORECASE,
)
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
    """Map a shell command to the verification-check ids a successful run proves.

    Recognizes Python build/test evidence (py_compile, --selftest, pytest/unittest,
    a plain `python foo.py` run) in addition to npm scripts, so a headless check
    run through run_command counts toward the completion gate — not only run_python.
    """
    command = command or ""
    ids: set[str] = set()
    if _PYCOMPILE_PATTERN.search(command):
        ids.add("compile")
    if _SELFTEST_PATTERN.search(command):
        ids.add("python:selftest")
    if _PYTEST_PATTERN.search(command):
        ids.add("python:tests")
    if not ids:
        match = _PYRUN_PATTERN.search(command)
        if match:
            from pathlib import PurePath
            ids.add(f"python:{PurePath(match.group(1)).name}")
    lowered = command.casefold()
    if any(word in lowered for word in ("test", "build", "verify", "check", "lint")):
        ids.update(extract_verification_requirements(command))
    return tuple(sorted(ids))


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
