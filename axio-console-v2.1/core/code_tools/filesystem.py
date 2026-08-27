"""Filesystem tools with bounded reads and atomic text writes."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from core.config import MAX_FILE_BYTES

from .registry import CodeTool, ToolResult


_DEDICATED_BINARY_SUFFIXES = {".docx", ".xlsx", ".pptx", ".pdf"}
_DANGEROUS_BINARY_SUFFIXES = {".exe", ".dll", ".msi", ".com", ".scr", ".lnk", ".sys"}


def _absolute(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"Path must be absolute: {path}")
    return candidate.resolve()


def _read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(f"File too large ({size} bytes). Use grep_files.")
    return path.read_text(encoding="utf-8", errors="replace")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def read_file(path: str) -> str:
    return _read_text(_absolute(path))


def write_file(path: str, content: str) -> ToolResult:
    target = _absolute(path)
    if target.suffix.lower() in _DEDICATED_BINARY_SUFFIXES:
        return ToolResult(
            f"ERROR: write_file creates UTF-8 text, not native {target.suffix} binaries. "
            "Use the dedicated artifact tool for DOCX, XLSX, PPTX, or PDF.",
            ok=False,
        )
    if target.suffix.lower() in _DANGEROUS_BINARY_SUFFIXES:
        return ToolResult(
            f"ERROR: write_file does not create executable or system binary formats: {target.suffix}",
            ok=False,
        )
    _atomic_write(target, content)
    verification = ("artifact:txt",) if target.suffix.lower() == ".txt" else ()
    return ToolResult(
        f"OK: Wrote {len(content):,} chars atomically to {target}",
        verification_ids=verification,
    )


def edit_file(path: str, old_text: str, new_text: str) -> str:
    target = _absolute(path)
    content = _read_text(target)
    count = content.count(old_text)
    if count != 1:
        return ToolResult(
            f"ERROR: Expected exactly one match in {target}; found {count}. Read the file and narrow old_text.",
            ok=False,
        )
    _atomic_write(target, content.replace(old_text, new_text, 1))
    return f"OK: Edited {target} atomically"


def apply_patch(changes: list[dict], description: str = "") -> ToolResult:
    if not changes:
        return ToolResult("ERROR: changes must contain at least one edit", ok=False)

    originals: dict[Path, str] = {}
    finals: dict[Path, str] = {}
    for index, change in enumerate(changes, 1):
        try:
            target = _absolute(str(change["path"]))
            old_text = str(change["old_text"])
            new_text = str(change["new_text"])
        except KeyError as exc:
            return ToolResult(f"ERROR: Change {index} is missing {exc.args[0]}", ok=False)
        if not old_text:
            return ToolResult(f"ERROR: Change {index} old_text cannot be empty", ok=False)
        if target not in originals:
            try:
                originals[target] = _read_text(target)
            except (OSError, ValueError) as exc:
                return ToolResult(f"ERROR: {exc}", ok=False)
            finals[target] = originals[target]
        count = finals[target].count(old_text)
        if count != 1:
            return ToolResult(
                f"ERROR: Change {index} expected one match in {target}; found {count}. No files changed.",
                ok=False,
            )
        finals[target] = finals[target].replace(old_text, new_text, 1)

    written: list[Path] = []
    try:
        for target, content in finals.items():
            _atomic_write(target, content)
            written.append(target)
    except Exception as exc:
        for target in written:
            _atomic_write(target, originals[target])
        return ToolResult(f"ERROR applying patch; written files were restored: {exc}", ok=False)

    label = f" ({description})" if description else ""
    return ToolResult(f"OK: Applied {len(changes)} atomic edit(s) to {len(finals)} file(s){label}")


def list_dir(path: str) -> str:
    directory = _absolute(path)
    if not directory.is_dir():
        raise ValueError(f"Directory not found: {directory}")
    items = sorted(directory.iterdir(), key=lambda item: (item.is_file(), item.name.lower()))
    lines = []
    for item in items[:80]:
        if item.is_dir():
            lines.append(f"  [DIR]  {item.name}/")
        else:
            lines.append(f"  [FILE] {item.name:<45} {item.stat().st_size:>10} bytes")
    if len(items) > 80:
        lines.append(f"  ... ({len(items) - 80} more items)")
    return "\n".join(lines) if lines else "(empty directory)"


def create_dir(path: str) -> str:
    directory = _absolute(path)
    directory.mkdir(parents=True, exist_ok=True)
    return f"OK: Created directory: {directory}"


def delete_file(path: str) -> str:
    target = _absolute(path)
    if not target.exists():
        raise FileNotFoundError(f"File not found: {target}")
    if not target.is_file():
        raise ValueError("delete_file never deletes directories")
    target.unlink()
    return f"OK: Permanently deleted {target}"


def search_files(directory: str, pattern: str) -> str:
    root = _absolute(directory)
    if not root.is_dir():
        raise ValueError(f"Directory not found: {root}")
    matches = [
        str(match)
        for match in root.rglob(pattern)
        if ".git" not in match.parts and "__pycache__" not in match.parts
    ][:60]
    if not matches:
        return f"No files matching '{pattern}'"
    return f"Found {len(matches)} file(s):\n" + "\n".join(matches)


def grep_files(directory: str, pattern: str, file_pattern: str = "*") -> str:
    root = _absolute(directory)
    if not root.is_dir():
        raise ValueError(f"Directory not found: {root}")
    results: list[str] = []
    for candidate in root.rglob(file_pattern):
        if not candidate.is_file() or ".git" in candidate.parts or "__pycache__" in candidate.parts:
            continue
        try:
            lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            if pattern.casefold() in line.casefold():
                results.append(f"{candidate}:{number}:  {line.strip()}")
            if len(results) >= 50:
                break
        if len(results) >= 50:
            break
    if not results:
        return f"No matches for '{pattern}'"
    return f"Found {len(results)} match(es):\n" + "\n".join(results)


TOOLS = [
    CodeTool("read_file", "Read a bounded UTF-8 text file. Read before editing.", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, read_file, "read"),
    CodeTool("write_file", "Atomically create or replace a text file.", {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}, write_file, "write"),
    CodeTool("edit_file", "Atomically replace one exact, unique text occurrence.", {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}, edit_file, "write"),
    CodeTool("apply_patch", "Apply validated exact replacements across one or more files atomically per file; no file changes if validation fails.", {"type": "object", "properties": {"changes": {"type": "array", "items": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}, "description": {"type": "string"}}, "required": ["changes"]}, apply_patch, "write"),
    CodeTool("list_dir", "List bounded directory contents.", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, list_dir, "read"),
    CodeTool("create_dir", "Create a directory and its parents.", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, create_dir, "write"),
    CodeTool("delete_file", "Permanently delete exactly one file, never a directory. Requires reinforced approval.", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, delete_file, "destructive"),
    CodeTool("search_files", "Find paths with a recursive glob while excluding Git/cache trees.", {"type": "object", "properties": {"directory": {"type": "string"}, "pattern": {"type": "string"}}, "required": ["directory", "pattern"]}, search_files, "read"),
    CodeTool("grep_files", "Search text in files using a bounded case-insensitive scan.", {"type": "object", "properties": {"directory": {"type": "string"}, "pattern": {"type": "string"}, "file_pattern": {"type": "string"}}, "required": ["directory", "pattern"]}, grep_files, "read"),
]
