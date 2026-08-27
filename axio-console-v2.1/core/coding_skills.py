"""Discovery, prompt loading, and Python runtime inspection for AXIO Code skills."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.config import BASE, CODE_SKILL_MAX_CHARS, CODE_SKILLS_ROOT, PROMPTS_DIR


@dataclass(frozen=True)
class CodingSkill:
    name: str
    description: str
    path: Path
    body: str
    always_apply: bool
    triggers: tuple[str, ...]


@dataclass(frozen=True)
class ToolCallingSkill:
    """Compact, model-visible operating instructions for one registered tool."""

    name: str
    when: str
    rules: tuple[str, ...]
    after: str


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    normalized = text.lstrip("\ufeff")
    lines = normalized.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, normalized
    try:
        closing = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return {}, normalized
    metadata = yaml.safe_load("\n".join(lines[1:closing])) or {}
    return metadata if isinstance(metadata, dict) else {}, "\n".join(lines[closing + 1 :]).strip()


def discover_coding_skills(root: Path | None = None) -> list[CodingSkill]:
    skills_root = Path(root or CODE_SKILLS_ROOT)
    if not skills_root.is_dir():
        return []

    skills: list[CodingSkill] = []
    for entrypoint in sorted(skills_root.glob("*/SKILL.md")):
        try:
            frontmatter, body = _split_frontmatter(entrypoint.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            continue
        skill_metadata = frontmatter.get("metadata") or {}
        if not isinstance(skill_metadata, dict):
            skill_metadata = {}
        triggers = skill_metadata.get("triggers") or []
        if isinstance(triggers, str):
            triggers = [triggers]
        skills.append(
            CodingSkill(
                name=str(frontmatter.get("name") or entrypoint.parent.name),
                description=str(frontmatter.get("description") or "").strip(),
                path=entrypoint.parent.resolve(),
                body=body,
                always_apply=bool(skill_metadata.get("always_apply", False)),
                triggers=tuple(str(item).lower() for item in triggers if str(item).strip()),
            )
        )
    return skills


def select_coding_skills(task: str, root: Path | None = None) -> list[CodingSkill]:
    lowered = (task or "").lower()
    return [
        skill
        for skill in discover_coding_skills(root)
        if skill.always_apply or any(trigger in lowered for trigger in skill.triggers)
    ]


def load_tool_calling_skills(root: Path | None = None) -> dict[str, ToolCallingSkill]:
    """Load the exact per-tool skill catalog bundled with the AXIO coding skill."""
    skills_root = Path(root or CODE_SKILLS_ROOT)
    catalog_path = skills_root / "axio-coding" / "tool-calling-skills.yaml"
    try:
        payload = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError):
        return {}
    raw_tools = payload.get("tools") if isinstance(payload, dict) else None
    if not isinstance(raw_tools, dict):
        return {}

    catalog: dict[str, ToolCallingSkill] = {}
    for name, raw in raw_tools.items():
        if not isinstance(raw, dict):
            continue
        rules = raw.get("rules") or []
        if isinstance(rules, str):
            rules = [rules]
        catalog[str(name)] = ToolCallingSkill(
            name=str(name),
            when=str(raw.get("when") or "").strip(),
            rules=tuple(str(rule).strip() for rule in rules if str(rule).strip()),
            after=str(raw.get("after") or "").strip(),
        )
    return catalog


def render_tool_calling_skills(root: Path | None = None) -> str:
    """Render all registered tool skills compactly for the model system prompt."""
    from core.code_tools import CODE_TOOL_REGISTRY

    catalog = load_tool_calling_skills(root)
    registered_names = [tool.name for tool in CODE_TOOL_REGISTRY.tools]
    missing = [name for name in registered_names if name not in catalog]
    extra = [name for name in catalog if CODE_TOOL_REGISTRY.get(name) is None]
    if missing or extra:
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        return "# Tool-Calling Skills\n\nCATALOG ERROR: " + "; ".join(details)

    lines = [
        f"# Tool-Calling Skills ({len(registered_names)}/{len(registered_names)})",
        "All registered tools are visible. Call the dedicated tool directly; do not invent tool names.",
    ]
    for name in registered_names:
        skill = catalog[name]
        rules = "; ".join(skill.rules)
        lines.append(
            f"- `{name}` — USE: {skill.when} RULES: {rules}. AFTER: {skill.after}"
        )
    return "\n".join(lines)


def _base_system_prompt() -> str:
    prompt_path = PROMPTS_DIR / "system_coding_agent.md"
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "You are AXIO Code, an execution-focused coding agent running on Windows."


def build_code_plan_prompt(tool_names: list[str] | tuple[str, ...] = ()) -> str:
    """Load the maintained, backend-neutral Code planning prompt."""
    prompt_path = PROMPTS_DIR / "system_code_plan.md"
    fallback = (
        "You are AXIO Code in PLAN MODE. Return only a numbered, read-only "
        "execution plan. Do not call tools or modify state."
    )
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except OSError:
        prompt = fallback
    names = ", ".join(tool_names) if tool_names else "the tools exposed by the runtime"
    return prompt.replace("{{TOOL_NAMES}}", names)


def build_coding_system_prompt(task: str = "", root: Path | None = None) -> str:
    """Build the system prompt from the maintained base prompt and active skills."""
    sections = [_base_system_prompt()]
    active = select_coding_skills(task, root)
    if active:
        sections.append("# Active AXIO Skills")
    for skill in active:
        body = (
            skill.body.replace("{{SKILL_ROOT}}", str(skill.path))
            .replace("{{PROJECT_ROOT}}", str(BASE))
            .replace("{{PYTHON_EXECUTABLE}}", str(resolve_python_interpreter(BASE)))
        )
        sections.append(f"## {skill.name}\n\n{body}")
    tool_skills = render_tool_calling_skills(root)
    if tool_skills:
        sections.append(tool_skills)
    prompt = "\n\n".join(section for section in sections if section).strip()
    return prompt[:CODE_SKILL_MAX_CHARS]


def format_skill_catalog(root: Path | None = None) -> str:
    skills = discover_coding_skills(root)
    if not skills:
        return f"No coding skills found under {Path(root or CODE_SKILLS_ROOT)}"
    lines = [f"Coding skills root: {Path(root or CODE_SKILLS_ROOT)}"]
    for skill in skills:
        activation = "always" if skill.always_apply else ", ".join(skill.triggers) or "manual"
        lines.append(f"- {skill.name}: {skill.description} [activation: {activation}]")
        lines.append(f"  {skill.path / 'SKILL.md'}")
    tool_skills = load_tool_calling_skills(root)
    lines.append(f"- tool-calling skills: {len(tool_skills)} specific tool cards")
    if tool_skills:
        lines.append(f"  {Path(root or CODE_SKILLS_ROOT) / 'axio-coding' / 'tool-calling-skills.yaml'}")
    return "\n".join(lines)


def resolve_python_interpreter(working_dir: str | Path | None = None) -> Path:
    """Prefer the target workspace venv, then AXIO's venv, then this interpreter."""
    candidates: list[Path] = []
    if working_dir:
        workspace = Path(working_dir).expanduser()
        candidates.extend(
            [workspace / ".venv" / "Scripts" / "python.exe", workspace / ".venv" / "bin" / "python"]
        )
    candidates.extend(
        [BASE / ".venv" / "Scripts" / "python.exe", BASE / ".venv" / "bin" / "python", Path(sys.executable)]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return Path(sys.executable).resolve()


_PYTHON_INSPECT_CODE = r"""
import importlib.metadata as md
import json
import platform
import sys

packages = sorted(
    ({"name": d.metadata.get("Name", d.name), "version": d.version} for d in md.distributions()),
    key=lambda item: item["name"].lower(),
)
print(json.dumps({
    "executable": sys.executable,
    "version": platform.python_version(),
    "implementation": platform.python_implementation(),
    "prefix": sys.prefix,
    "base_prefix": sys.base_prefix,
    "in_virtualenv": sys.prefix != sys.base_prefix,
    "platform": platform.platform(),
    "packages": packages,
}, ensure_ascii=False))
""".strip()


def inspect_python_environment(working_dir: str | Path | None = None) -> str:
    """Return a fresh, non-mutating inventory from the interpreter AXIO would use."""
    interpreter = resolve_python_interpreter(working_dir)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            [str(interpreter), "-c", _PYTHON_INSPECT_CODE],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=str(Path(working_dir).resolve()) if working_dir else str(BASE),
            env=env,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"ERROR inspecting Python environment: {exc}"
    if result.returncode != 0:
        return f"ERROR inspecting Python environment:\n{result.stderr.strip()}"
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return f"ERROR parsing Python environment: {exc}"

    packages = data.pop("packages", [])
    dependency_files = []
    base = Path(working_dir).resolve() if working_dir else BASE
    for filename in ("pyproject.toml", "requirements.txt", "setup.cfg", "Pipfile", "poetry.lock"):
        candidate = base / filename
        if candidate.is_file():
            dependency_files.append(str(candidate))

    lines = [
        f"Python executable: {data['executable']}",
        f"Version: {data['implementation']} {data['version']}",
        f"Virtual environment: {'yes' if data['in_virtualenv'] else 'no'}",
        f"Prefix: {data['prefix']}",
        f"Base prefix: {data['base_prefix']}",
        f"Platform: {data['platform']}",
        f"Workspace dependency files: {', '.join(dependency_files) if dependency_files else '(none found)'}",
        f"Installed distributions ({len(packages)}):",
    ]
    lines.extend(f"- {item['name']}=={item['version']}" for item in packages)
    return "\n".join(lines)
