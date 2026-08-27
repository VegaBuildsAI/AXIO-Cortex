"""Local, read-only document extraction tools."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

from core.config import MAX_FILE_BYTES

from .registry import CodeTool, ToolResult


def read_docx(path: str, max_chars: int = 50_000) -> ToolResult:
    source = Path(path).expanduser()
    if not source.is_absolute():
        return ToolResult("ERROR: path must be absolute", ok=False)
    source = source.resolve()
    if not source.is_file() or source.suffix.lower() != ".docx":
        return ToolResult(f"ERROR: DOCX file not found: {source}", ok=False)
    if source.stat().st_size > max(MAX_FILE_BYTES * 25, 5_000_000):
        return ToolResult(f"ERROR: DOCX is too large: {source.stat().st_size} bytes", ok=False)
    limit = max(1_000, min(int(max_chars), 200_000))
    try:
        with zipfile.ZipFile(source) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
    except (OSError, KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        return ToolResult(f"ERROR reading DOCX: {exc}", ok=False)
    paragraphs: list[str] = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        text = "".join(node.text or "" for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
        if text:
            paragraphs.append(text)
    content = "\n".join(paragraphs)
    if len(content) > limit:
        content = content[:limit] + f"\n... truncated at {limit} chars"
    return ToolResult(content or "(DOCX contains no extractable text)")


TOOLS = [
    CodeTool("read_docx", "Extract bounded text from a local DOCX without modifying it.", {"type": "object", "properties": {"path": {"type": "string"}, "max_chars": {"type": "integer", "minimum": 1000, "maximum": 200000}}, "required": ["path"]}, read_docx, "read"),
]
