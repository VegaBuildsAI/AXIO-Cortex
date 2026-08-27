"""Atomic project and module scaffolding from approved AXIO templates."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from core.config import CODE_TEMPLATES_DIR

from .registry import CodeTool, ToolResult


_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,63}$")
_ALIASES = {"python-fastapi": "fastapi-service", "fastapi": "fastapi-service"}


def _safe_name(name: str) -> tuple[str, str]:
    if not _NAME.fullmatch(name.strip()):
        raise ValueError("name must start with a letter and contain only letters, digits, _ or - (2-64 chars)")
    display = name.strip()
    package = display.replace("-", "_").casefold()
    return display, package


def _class_name(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[-_]", name) if part)


def _absolute_destination(destination: str) -> Path:
    target = Path(destination).expanduser()
    if not target.is_absolute():
        raise ValueError("destination must be an absolute path")
    target = target.resolve()
    if target.exists():
        raise ValueError(f"destination already exists; scaffolds never overwrite: {target}")
    return target


def _safe_relative(raw: str, values: dict[str, str]) -> Path:
    rendered = raw
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    pure = PurePosixPath(rendered)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Unsafe template path: {raw}")
    return Path(*pure.parts)


def _render(content: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        content = content.replace("{{" + key + "}}", value)
    return content


def _atomic_tree(target: Path, files: dict[str, str], values: dict[str, str]) -> list[str]:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{target.name}.axio-", dir=target.parent))
    created: list[str] = []
    try:
        for relative, content in files.items():
            rel = _safe_relative(relative, values)
            output = temp / rel
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(_render(content, values), encoding="utf-8", newline="")
            created.append(str(target / rel))
        os.replace(temp, target)
        return created
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _load_manifest(template: str) -> tuple[str, dict]:
    canonical = _ALIASES.get(template.strip().casefold(), template.strip().casefold())
    path = CODE_TEMPLATES_DIR / f"{canonical}.json"
    if not path.is_file():
        available = ", ".join(item.stem for item in sorted(CODE_TEMPLATES_DIR.glob("*.json")))
        raise ValueError(f"Unknown template '{template}'. Available: {available}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("files"), dict):
        raise ValueError(f"Invalid template manifest: {path}")
    return canonical, payload


def scaffold_project(template: str, name: str, destination: str, options: dict | None = None) -> ToolResult:
    try:
        display, package = _safe_name(name)
        target = _absolute_destination(destination)
        canonical, manifest = _load_manifest(template)
        opts = {"docker": False, "tests": True, "config": True} | dict(options or {})
        selected = {}
        for relative, content in manifest["files"].items():
            normalized = relative.casefold()
            if not opts["docker"] and normalized == "dockerfile":
                continue
            if not opts["tests"] and (normalized.startswith("tests/") or "/tests/" in normalized):
                continue
            if not opts["config"] and (normalized.startswith("config/") or normalized.endswith(".env.example")):
                continue
            selected[relative] = str(content)
        created = _atomic_tree(target, selected, {"PROJECT_NAME": display, "PACKAGE_NAME": package})
        return ToolResult(json.dumps({"template": canonical, "destination": str(target), "files_created": created, "options": opts}, ensure_ascii=False, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return ToolResult(f"ERROR: scaffold_project failed: {exc}", ok=False)


def _module_files(module_type: str, package: str) -> dict[str, str]:
    if module_type == "python-module":
        return {
            "__init__.py": '"""{{PROJECT_NAME}} module."""\n',
            "service.py": '"""Business logic for {{PROJECT_NAME}}."""\n\n\ndef run() -> None:\n    pass\n',
            "tests/test_service.py": "import unittest\n\n\nclass ServiceTests(unittest.TestCase):\n    def test_placeholder(self):\n        self.assertTrue(True)\n",
        }
    if module_type == "fastapi-domain":
        return {
            "__init__.py": "",
            "model.py": '"""Persistence model boundary for {{PROJECT_NAME}}."""\n',
            "schema.py": "from pydantic import BaseModel\n\n\nclass {{CLASS_NAME}}Payload(BaseModel):\n    name: str\n",
            "repository.py": '"""Repository boundary for {{PROJECT_NAME}}."""\n',
            "service.py": '"""Domain service for {{PROJECT_NAME}}."""\n',
            "router.py": "from fastapi import APIRouter\n\nrouter = APIRouter(prefix=\"/{{PACKAGE_NAME}}\", tags=[\"{{PROJECT_NAME}}\"])\n",
            "tests/test_{{PACKAGE_NAME}}.py": "import unittest\n\n\nclass {{CLASS_NAME}}Tests(unittest.TestCase):\n    def test_placeholder(self):\n        self.assertTrue(True)\n",
        }
    if module_type == "react-component":
        return {
            "{{CLASS_NAME}}.tsx": "export interface {{CLASS_NAME}}Props {\n  title: string;\n}\n\nexport function {{CLASS_NAME}}({ title }: {{CLASS_NAME}}Props) {\n  return <section><h2>{title}</h2></section>;\n}\n",
            "{{CLASS_NAME}}.test.tsx": "import { describe, expect, it } from 'vitest';\n\ndescribe('{{CLASS_NAME}}', () => {\n  it('has a test placeholder', () => expect(true).toBe(true));\n});\n",
            "index.ts": "export * from './{{CLASS_NAME}}';\n",
        }
    raise ValueError("Unknown module type. Choose: python-module, fastapi-domain, react-component")


def scaffold_module(type: str, name: str, destination: str) -> ToolResult:
    try:
        display, package = _safe_name(name)
        parent = Path(destination).expanduser()
        if not parent.is_absolute():
            raise ValueError("destination must be an absolute existing parent directory")
        parent = parent.resolve()
        if not parent.is_dir():
            raise ValueError(f"destination parent does not exist: {parent}")
        class_name = _class_name(display)
        target = parent / (class_name if type == "react-component" else package)
        if target.exists():
            raise ValueError(f"module destination already exists: {target}")
        files = _module_files(type, package)
        created = _atomic_tree(target, files, {"PROJECT_NAME": display, "PACKAGE_NAME": package, "CLASS_NAME": class_name})
        return ToolResult(json.dumps({"type": type, "destination": str(target), "files_created": created}, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        return ToolResult(f"ERROR: scaffold_module failed: {exc}", ok=False)


TOOLS = [
    CodeTool("scaffold_project", "Create a new project atomically from an approved AXIO template. Never overwrites an existing destination.", {"type": "object", "properties": {"template": {"type": "string", "enum": ["python-cli", "python-package", "fastapi-service", "python-fastapi", "mcp-server", "agent-service", "react-app", "nextjs-app", "axio-agent"]}, "name": {"type": "string"}, "destination": {"type": "string"}, "options": {"type": "object", "properties": {"docker": {"type": "boolean"}, "tests": {"type": "boolean"}, "config": {"type": "boolean"}}}}, "required": ["template", "name", "destination"]}, scaffold_project, "write"),
    CodeTool("scaffold_module", "Create one standard Python, FastAPI-domain, or React module atomically inside an existing destination. Never overwrites.", {"type": "object", "properties": {"type": {"type": "string", "enum": ["python-module", "fastapi-domain", "react-component"]}, "name": {"type": "string"}, "destination": {"type": "string"}}, "required": ["type", "name", "destination"]}, scaffold_module, "write"),
]
