"""Typed registry and centralized execution policy for AXIO Code tools."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Literal, Mapping, Sequence


RiskLevel = Literal["read", "index", "write", "execute", "destructive", "external"]
ToolHandler = Callable[..., object]
ApprovalHandler = Callable[["CodeTool", Mapping[str, object]], bool]
AuditHandler = Callable[["CodeTool", Mapping[str, object], str], None]


@dataclass(frozen=True)
class ToolResult:
    content: str
    ok: bool = True
    verification_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CodeTool:
    name: str
    description: str
    input_schema: dict
    handler: ToolHandler
    risk: RiskLevel = "read"
    category: str = "general"
    task_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolExecutionRecord:
    name: str
    risk: RiskLevel
    arguments: dict
    result: str
    ok: bool
    verification_ids: tuple[str, ...] = ()


@dataclass
class TaskVerificationState:
    task: str = ""
    required_checks: set[str] = field(default_factory=set)
    successful_checks: set[str] = field(default_factory=set)
    mutated: bool = False
    gate_passed: bool = False
    web_evidence_required: bool = False
    workspace_roots: tuple[Path, ...] = ()


class CodeToolRegistry:
    """Single source for schemas, handlers, risk gates, logging, and evidence."""

    def __init__(self) -> None:
        self._tools: dict[str, CodeTool] = {}
        self.records: list[ToolExecutionRecord] = []
        self.state = TaskVerificationState()

    def register(self, tool: CodeTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate Code tool: {tool.name}")
        category, task_types = _TOOL_METADATA.get(
            tool.name,
            (tool.category, tool.task_types),
        )
        if tool.category == "general" or not tool.task_types:
            tool = replace(
                tool,
                category=category if tool.category == "general" else tool.category,
                task_types=task_types if not tool.task_types else tool.task_types,
            )
        self._tools[tool.name] = tool

    def register_many(self, tools: Sequence[CodeTool], *, category: str = "general") -> None:
        for tool in tools:
            if tool.category == "general" and category != "general":
                tool = replace(tool, category=category)
            self.register(tool)

    def get(self, name: str) -> CodeTool | None:
        return self._tools.get(name)

    @property
    def tools(self) -> tuple[CodeTool, ...]:
        return tuple(self._tools.values())

    @property
    def handler_map(self) -> dict[str, ToolHandler]:
        return {name: tool.handler for name, tool in self._tools.items()}

    def ollama_schemas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self.tools
        ]

    def claude_schemas(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self.tools
        ]

    def emit_subset(self, tools: Sequence[CodeTool], provider: str) -> list[dict]:
        """Emit provider schemas for an already selected subset."""
        normalized = provider.strip().lower()
        if normalized == "ollama":
            return [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in tools
            ]
        if normalized == "claude":
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in tools
            ]
        raise ValueError(f"Unsupported tool schema provider: {provider}")

    def get_subset(
        self,
        task_type: str,
        budget: int = 8,
        include_names: Sequence[str] = (),
    ) -> list[CodeTool]:
        """Return a stable, bounded subset while preserving the full registry."""
        if budget < len(_CORE_TOOL_FLOOR):
            raise ValueError(f"Tool budget must be at least {len(_CORE_TOOL_FLOOR)}")
        normalized = str(getattr(task_type, "value", task_type)).upper()
        ordered_names = [*_CORE_TOOL_FLOOR, *include_names, *_TASK_TOOL_PRIORITY.get(normalized, ())]
        selected: list[CodeTool] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            if len(selected) >= budget or name in seen:
                return
            tool = self.get(name)
            if tool is not None:
                selected.append(tool)
                seen.add(name)

        for name in ordered_names:
            add(name)
        for tool in self.tools:
            if normalized in tool.task_types:
                add(tool.name)
        return selected

    def format_catalog(self) -> str:
        width = max((len(tool.name) for tool in self.tools), default=0)
        return "\n".join(
            f"  {tool.name:<{width}}  [{tool.risk}] {tool.description}"
            for tool in self.tools
        )

    def start_task(self, task: str, workspace_roots: Sequence[str | Path] | None = None) -> None:
        from .verification import extract_artifact_requirements, extract_verification_requirements
        from core.web_intent import detect_web_intent

        self.records.clear()
        self.state = TaskVerificationState(
            task=task,
            required_checks=set(extract_verification_requirements(task)) | set(extract_artifact_requirements(task)),
            web_evidence_required=detect_web_intent(task),
            workspace_roots=tuple(
                Path(root).expanduser().resolve()
                for root in (workspace_roots or [Path.cwd()])
            ),
        )

    def execute(
        self,
        name: str,
        arguments: Mapping[str, object] | None,
        *,
        approve: ApprovalHandler | None = None,
        audit: AuditHandler | None = None,
    ) -> str:
        tool = self.get(name)
        args = dict(arguments or {})
        if tool is None:
            return f"ERROR: Unknown tool '{name}'"

        result = ToolResult("")
        try:
            needs_approval = tool.risk in {"execute", "destructive", "external"}
            if tool.risk == "write" and not self._write_is_inside_workspace(tool, args):
                needs_approval = True
            if needs_approval:
                if approve is None or not approve(tool, args):
                    result = ToolResult("CANCELLED: User declined.", ok=False)
                else:
                    result = self._invoke(tool, args)
            else:
                result = self._invoke(tool, args)
        except TypeError as exc:
            result = ToolResult(f"ERROR: Wrong arguments for {name}: {exc}", ok=False)
        except Exception as exc:
            result = ToolResult(f"ERROR: {exc}", ok=False)

        record = ToolExecutionRecord(
            name=tool.name,
            risk=tool.risk,
            arguments=args,
            result=result.content,
            ok=result.ok,
            verification_ids=result.verification_ids,
        )
        self.records.append(record)

        if result.ok:
            if tool.risk in {"write", "destructive"}:
                self.state.mutated = True
                self.state.gate_passed = False
            self.state.successful_checks.update(result.verification_ids)
            if tool.name == "read_file":
                from .verification import extract_verification_requirements

                self.state.required_checks.update(
                    extract_verification_requirements(result.content)
                )

        if audit is not None:
            try:
                audit(tool, args, result.content)
            except Exception:
                # Audit failures cannot hide or change the tool's real outcome.
                pass
        return result.content

    def _write_is_inside_workspace(self, tool: CodeTool, arguments: Mapping[str, object]) -> bool:
        paths: list[Path] = []
        for key in ("path", "destination"):
            direct = arguments.get(key)
            if isinstance(direct, str):
                paths.append(Path(direct).expanduser())
        changes = arguments.get("changes")
        if isinstance(changes, list):
            for change in changes:
                if isinstance(change, dict) and isinstance(change.get("path"), str):
                    paths.append(Path(change["path"]).expanduser())
        if not paths and tool.category == "finance":
            filename = arguments.get("filename")
            if isinstance(filename, str):
                candidate = Path(filename)
                return bool(
                    self.state.workspace_roots
                    and candidate.name == filename
                    and filename not in {"", ".", ".."}
                )
        if not paths or not self.state.workspace_roots:
            return False
        for path in paths:
            if not path.is_absolute():
                return False
            resolved = path.resolve()
            if not any(resolved == root or root in resolved.parents for root in self.state.workspace_roots):
                return False
        return True

    @staticmethod
    def _invoke(tool: CodeTool, arguments: dict) -> ToolResult:
        raw = tool.handler(**arguments)
        if isinstance(raw, ToolResult):
            return raw
        content = str(raw)
        ok = not content.startswith(("ERROR:", "CANCELLED:"))
        return ToolResult(content=content, ok=ok)

    def evaluate_gate(self, required_checks: Sequence[str] | None = None) -> ToolResult:
        from .verification import normalize_check_id

        requested = {
            normalized
            for item in (required_checks or [])
            if (normalized := normalize_check_id(str(item)))
        }
        required = self.state.required_checks | requested

        missing_artifacts = sorted(
            check for check in required - self.state.successful_checks
            if check.startswith("artifact:")
        )
        if missing_artifacts:
            self.state.gate_passed = False
            return ToolResult(
                "VERIFICATION BLOCKED: Requested artifact(s) were not created and validated: "
                + ", ".join(missing_artifacts),
                ok=False,
            )

        dedicated_artifact_evidence = {
            f"artifact:{record.name.removeprefix('create_')}"
            for record in self.records
            if record.ok and record.name.startswith("create_")
        }
        applicable_checks = {
            check for check in self.state.successful_checks
            if not check.startswith("artifact:")
            or check in required
            or check in dedicated_artifact_evidence
        }

        if not self.state.mutated:
            self.state.gate_passed = True
            return ToolResult("VERIFICATION PASSED: No successful mutation requires validation.")

        if not applicable_checks:
            self.state.gate_passed = False
            return ToolResult(
                "VERIFICATION BLOCKED: Code changed, but no successful test, build, "
                "or executable verification has been recorded.",
                ok=False,
            )

        missing = sorted(required - self.state.successful_checks)
        if missing:
            self.state.gate_passed = False
            return ToolResult(
                "VERIFICATION BLOCKED: Missing successful checks: " + ", ".join(missing),
                ok=False,
            )

        self.state.gate_passed = True
        checks = ", ".join(sorted(applicable_checks))
        return ToolResult(f"VERIFICATION PASSED: {checks}")

    def completion_status(self) -> tuple[bool, str]:
        missing_artifacts = sorted(
            check for check in self.state.required_checks - self.state.successful_checks
            if check.startswith("artifact:")
        )
        if missing_artifacts:
            return (
                False,
                "The task requested artifact(s) that have not been created and structurally "
                "validated: " + ", ".join(missing_artifacts) + ".",
            )
        if not self.state.mutated:
            return True, "No successful mutation requires a completion gate."
        if self.state.gate_passed:
            return True, "Verification gate passed."
        return (
            False,
            "Changes were made but verification_gate has not passed. Run the relevant "
            "test/build tool, then call verification_gate before TASK_COMPLETE.",
        )

    def web_completion_status(self) -> tuple[bool, str]:
        """Block completion when a web-intent task recorded no web evidence."""
        if not self.state.web_evidence_required:
            return True, "No web evidence required."
        from core.web_intent import has_web_evidence, web_gate_message

        if has_web_evidence(self.records):
            return True, "Web evidence present."
        return False, web_gate_message()


_CORE_TOOL_FLOOR = ("read_file", "list_dir", "search_files", "verification_gate")

_TASK_TOOL_PRIORITY: dict[str, tuple[str, ...]] = {
    "CODE_EDIT": ("edit_file", "write_file", "run_python", "apply_patch", "run_npm_script"),
    "DEBUGGING": ("grep_files", "run_command", "edit_file", "git_diff", "run_python"),
    "RESEARCH": ("web_search", "web_fetch", "web_extract", "search_docs", "semantic_search"),
    "PLANNING": ("grep_files", "search_docs", "git_diff", "semantic_search", "web_search"),
    "TESTING": ("run_python", "run_npm_script", "git_diff", "inspect_python_environment"),
    "FILE_OPS": ("write_file", "create_dir", "delete_file", "read_docx", "grep_files"),
}

_TOOL_METADATA: dict[str, tuple[str, tuple[str, ...]]] = {
    "read_file": ("filesystem", ("CODE_EDIT", "DEBUGGING", "RESEARCH", "PLANNING", "TESTING", "FILE_OPS")),
    "write_file": ("filesystem", ("CODE_EDIT", "FILE_OPS")),
    "edit_file": ("filesystem", ("CODE_EDIT", "DEBUGGING", "TESTING")),
    "apply_patch": ("filesystem", ("CODE_EDIT", "DEBUGGING")),
    "list_dir": ("filesystem", ("CODE_EDIT", "DEBUGGING", "RESEARCH", "PLANNING", "TESTING", "FILE_OPS")),
    "create_dir": ("filesystem", ("CODE_EDIT", "FILE_OPS")),
    "delete_file": ("filesystem", ("FILE_OPS",)),
    "search_files": ("filesystem", ("CODE_EDIT", "DEBUGGING", "RESEARCH", "PLANNING", "TESTING", "FILE_OPS")),
    "grep_files": ("filesystem", ("CODE_EDIT", "DEBUGGING", "RESEARCH", "PLANNING", "TESTING")),
    "inspect_python_environment": ("python", ("DEBUGGING", "PLANNING", "TESTING")),
    "run_python": ("python", ("CODE_EDIT", "DEBUGGING", "TESTING")),
    "inspect_node_environment": ("node", ("DEBUGGING", "PLANNING", "TESTING")),
    "run_npm_script": ("node", ("CODE_EDIT", "DEBUGGING", "TESTING")),
    "git_status": ("git", ("CODE_EDIT", "DEBUGGING", "PLANNING", "TESTING")),
    "git_diff": ("git", ("CODE_EDIT", "DEBUGGING", "PLANNING", "TESTING")),
    "git_branch": ("git", ("CODE_EDIT", "FILE_OPS")),
    "git_commit": ("git", ("CODE_EDIT",)),
    "github_status": ("github", ("RESEARCH", "PLANNING")),
    "github_pr_list": ("github", ("RESEARCH", "PLANNING")),
    "github_pr_view": ("github", ("RESEARCH", "PLANNING")),
    "github_push": ("github", ("CODE_EDIT",)),
    "github_fork": ("github", ("FILE_OPS",)),
    "github_pr_create": ("github", ("CODE_EDIT",)),
    "github_pr_merge": ("github", ("CODE_EDIT",)),
    "read_docx": ("document", ("RESEARCH", "PLANNING", "FILE_OPS")),
    "run_command": ("shell", ("CODE_EDIT", "DEBUGGING", "TESTING")),
    "verification_gate": ("verification", ("CODE_EDIT", "DEBUGGING", "TESTING", "FILE_OPS")),
    "web_search": ("web", ("RESEARCH", "PLANNING")),
    "web_fetch": ("web", ("RESEARCH",)),
    "web_extract": ("web", ("RESEARCH",)),
    "browser_open": ("browser", ("RESEARCH", "TESTING")),
    "browser_snapshot": ("browser", ("RESEARCH", "TESTING")),
    "browser_click": ("browser", ("RESEARCH", "TESTING")),
    "index_workspace": ("retrieval", ("RESEARCH", "PLANNING")),
    "semantic_search": ("retrieval", ("RESEARCH", "PLANNING")),
    "search_docs": ("retrieval", ("RESEARCH", "PLANNING", "DEBUGGING")),
    "scaffold_project": ("scaffold", ("CODE_EDIT", "FILE_OPS")),
    "scaffold_module": ("scaffold", ("CODE_EDIT", "FILE_OPS")),
}


def summarize_arguments(arguments: Mapping[str, object], limit: int = 100) -> str:
    """Create a bounded, secret-conscious argument preview for human gates."""

    sensitive = ("secret", "token", "password", "key", "content", "old_text", "new_text", "patch")
    parts: list[str] = []
    for key, value in arguments.items():
        if any(marker in key.lower() for marker in sensitive):
            rendered = "<redacted>"
        else:
            rendered = repr(value)
            if len(rendered) > limit:
                rendered = rendered[:limit] + "..."
        parts.append(f"{key}={rendered}")
    return ", ".join(parts) or "(no arguments)"
