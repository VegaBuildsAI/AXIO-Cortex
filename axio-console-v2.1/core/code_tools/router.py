"""Dynamic tool routing and shared agent-loop resilience for AXIO."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Mapping, Sequence

from core.config import LOG_DIR

from .registry import CodeToolRegistry


class TaskType(str, Enum):
    CODE_EDIT = "CODE_EDIT"
    DEBUGGING = "DEBUGGING"
    RESEARCH = "RESEARCH"
    PLANNING = "PLANNING"
    TESTING = "TESTING"
    FILE_OPS = "FILE_OPS"


COMPLEXITY_BUDGETS = {"simple": 10, "normal": 20, "complex": 50, "benchmark": 100}
REQUEST_TOOL_NAME = "request_tool"
REQUEST_TOOL_DESCRIPTION = (
    "Request one registered AXIO tool that is not currently visible. It becomes available "
    "on the next step after the harness validates its name."
)
REQUEST_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Exact registered tool name"},
        "reason": {"type": "string", "description": "Why the active subset is insufficient"},
    },
    "required": ["name", "reason"],
}


def classify_task(prompt: str, recent_obs: str | Sequence[str] = ()) -> TaskType:
    """Cheap deterministic classifier used before every model step."""
    observations = [recent_obs] if isinstance(recent_obs, str) else list(recent_obs)
    text = " ".join([prompt, *observations[-3:]]).lower()
    prompt_text = (prompt or "").lower().strip()

    if re.search(r"\b(error|traceback|exception|failing|failed|bug|debug|fix failure|root cause)\b", text):
        return TaskType.DEBUGGING
    if re.search(r"\b(web|internet|latest|research|investigate|documentation|docs|source|citation)\b", prompt_text):
        return TaskType.RESEARCH
    if re.search(r"\b(plan|planning|audit|review|assess|architecture|design|roadmap|read.only)\b", prompt_text):
        return TaskType.PLANNING
    if re.search(r"\b(test|tests|testing|verify|verification|benchmark|build|lint|typecheck)\b", prompt_text) and not re.search(
        r"\b(create|implement|change|edit|write|fix|refactor|migrate)\b", prompt_text
    ):
        return TaskType.TESTING
    if re.search(r"\b(move|rename|copy|delete|remove|organize|list files|create directory|folder)\b", prompt_text):
        return TaskType.FILE_OPS
    return TaskType.CODE_EDIT


def classify_complexity(prompt: str) -> str:
    text = (prompt or "").lower()
    if re.search(r"\b(benchmark|swe-bench|bfcl|inspect eval|full evaluation)\b", text):
        return "benchmark"
    if len(text) > 1200 or re.search(
        r"\b(architecture|migration|migrate|large codebase|end.to.end|por completo|complete plan|multi.phase|refactor)\b",
        text,
    ):
        return "complex"
    if len(text.split()) <= 12 and not re.search(r"\b(and|then|after|multiple|several)\b", text):
        return "simple"
    return "normal"


def step_budget(prompt: str) -> int:
    return COMPLEXITY_BUDGETS[classify_complexity(prompt)]


def truncate_observation(text: str, max_chars: int = 4000) -> str:
    """Keep head, diagnostic lines, and tail within one strict character budget."""
    raw = str(text or "")
    if len(raw) <= max_chars:
        return raw
    if max_chars < 240:
        return raw[:max_chars]
    marker_budget = 150
    head_size = int((max_chars - marker_budget) * 0.45)
    tail_size = int((max_chars - marker_budget) * 0.40)
    diagnostic_budget = max_chars - marker_budget - head_size - tail_size
    diagnostics = [
        line.strip()
        for line in raw.splitlines()
        if re.search(r"(?i)\b(error|failed|failure|warning|traceback|exit code|passed)\b", line)
    ]
    diagnostic = "\n".join(dict.fromkeys(diagnostics))[:diagnostic_budget]
    omitted = len(raw) - head_size - tail_size
    marker = f"\n\n[HARNESS: observation truncated; {omitted} chars omitted"
    if diagnostic:
        marker += f"; diagnostic lines preserved]\n{diagnostic}\n"
    else:
        marker += "]\n"
    result = raw[:head_size] + marker + raw[-tail_size:]
    return result[:max_chars]


def process_history(messages: Sequence[dict], provider: str, keep_observations: int = 5) -> list[dict]:
    """Keep the initial task plus complete pairs for the latest tool observations."""
    history = list(messages)
    if len(history) <= 3:
        return history
    normalized = provider.lower()

    def is_observation(message: dict) -> bool:
        if normalized == "ollama":
            return message.get("role") == "tool"
        content = message.get("content")
        return message.get("role") == "user" and isinstance(content, list) and any(
            isinstance(item, dict) and item.get("type") == "tool_result" for item in content
        )

    observation_indices = [index for index, message in enumerate(history) if is_observation(message)]
    if len(observation_indices) <= keep_observations:
        return history
    start = observation_indices[-keep_observations]
    if start > 0 and history[start - 1].get("role") == "assistant":
        start -= 1
    prefix: list[dict] = []
    if normalized == "ollama" and history and history[0].get("role") == "system":
        prefix.append(history[0])
    first_user = next((item for item in history if item.get("role") == "user"), None)
    if first_user is not None and first_user not in prefix and history.index(first_user) < start:
        prefix.append(first_user)
    return [*prefix, *history[start:]]


def classify_error(observation: str) -> str:
    text = (observation or "").lower()
    if "unknown tool" in text:
        return "unknown_tool"
    if "wrong arguments" in text or "invalid argument" in text or "validation" in text:
        return "invalid_arguments"
    if "permission" in text or "access denied" in text or "cancelled:" in text:
        return "permission"
    if "not found" in text or "no such file" in text:
        return "missing_resource"
    if "timeout" in text or "timed out" in text:
        return "timeout"
    if "connection" in text or "network" in text or "dns" in text:
        return "network"
    return "execution"


@dataclass
class LoopGuard:
    repeat_limit: int = 2
    no_progress_limit: int = 3
    max_interventions: int = 3
    signatures: Counter = field(default_factory=Counter)
    errors: Counter = field(default_factory=Counter)
    seen_observations: set[str] = field(default_factory=set)
    no_progress_steps: int = 0
    interventions: int = 0

    def record(self, name: str, arguments: Mapping[str, object], observation: str, mutation_success: bool = False) -> str:
        encoded = json.dumps(dict(arguments or {}), ensure_ascii=False, sort_keys=True, default=str)
        signature = hashlib.sha256(f"{name}\0{encoded}".encode("utf-8")).hexdigest()
        self.signatures[signature] += 1
        digest = hashlib.sha256((observation or "").encode("utf-8", errors="replace")).hexdigest()
        novel = digest not in self.seen_observations
        self.seen_observations.add(digest)
        self.no_progress_steps = 0 if mutation_success or novel else self.no_progress_steps + 1

        intervention = ""
        if self.signatures[signature] > self.repeat_limit:
            intervention = f"Repeated identical call {name} more than {self.repeat_limit} times; change approach or request another tool."
        if (observation or "").startswith(("ERROR:", "CANCELLED:")):
            normalized = re.sub(r"\d+", "#", observation.strip().lower())[:500]
            self.errors[normalized] += 1
            if self.errors[normalized] > self.repeat_limit:
                kind = classify_error(observation)
                intervention = f"Repeated {kind} error; do not retry unchanged. Inspect inputs, permissions, or choose a safer alternative."
        if self.no_progress_steps >= self.no_progress_limit:
            intervention = "No progress across three steps; restate the current blocker and choose a materially different action."
            self.no_progress_steps = 0
        if intervention:
            self.interventions += 1
            return "[HARNESS] " + intervention
        return ""

    @property
    def should_stop(self) -> bool:
        return self.interventions >= self.max_interventions


class DynamicToolRouter:
    """Classify each step while supporting full or experimental bounded visibility."""

    def __init__(
        self,
        registry: CodeToolRegistry,
        prompt: str,
        *,
        budget: int = 8,
        preferred_names: Sequence[str] = (),
        visibility: str = "full",
    ) -> None:
        normalized_visibility = visibility.strip().lower()
        if normalized_visibility not in {"full", "dynamic"}:
            raise ValueError("Tool visibility must be 'full' or 'dynamic'")
        if normalized_visibility == "dynamic" and budget < 5:
            raise ValueError("Dynamic tool budget must allow four core tools plus request_tool")
        self.registry = registry
        self.prompt = prompt
        self.budget = budget
        self.visibility = normalized_visibility
        self.preferred_names = list(dict.fromkeys(preferred_names))
        self.granted_names: list[str] = []
        self.recent_observations: deque[str] = deque(maxlen=3)
        self.task_type = classify_task(prompt)
        self.active_names: tuple[str, ...] = ()

    def observe(self, observation: str) -> None:
        self.recent_observations.append(observation)

    def schemas(self, provider: str) -> list[dict]:
        self.task_type = classify_task(self.prompt, tuple(self.recent_observations))
        if self.visibility == "full":
            subset = list(self.registry.tools)
            self.active_names = tuple(tool.name for tool in subset)
            return self.registry.emit_subset(subset, provider)
        include = [*self.granted_names, *self.preferred_names]
        subset = self.registry.get_subset(self.task_type, self.budget - 1, include)
        self.active_names = tuple(tool.name for tool in subset)
        schemas = self.registry.emit_subset(subset, provider)
        if provider.lower() == "ollama":
            schemas.append({
                "type": "function",
                "function": {
                    "name": REQUEST_TOOL_NAME,
                    "description": REQUEST_TOOL_DESCRIPTION,
                    "parameters": REQUEST_TOOL_SCHEMA,
                },
            })
        elif provider.lower() == "claude":
            schemas.append({
                "name": REQUEST_TOOL_NAME,
                "description": REQUEST_TOOL_DESCRIPTION,
                "input_schema": REQUEST_TOOL_SCHEMA,
            })
        return schemas

    @property
    def exposed_names(self) -> tuple[str, ...]:
        if self.visibility == "dynamic":
            return (*self.active_names, REQUEST_TOOL_NAME)
        return self.active_names

    def handle_unavailable_call(self, name: str, arguments: Mapping[str, object]) -> str | None:
        if self.visibility == "full" and self.registry.get(name) is not None:
            return None
        if name == REQUEST_TOOL_NAME:
            requested = str((arguments or {}).get("name", "")).strip()
            reason = str((arguments or {}).get("reason", "")).strip()
            if not requested or self.registry.get(requested) is None:
                return f"ERROR: request_tool rejected unknown registered tool '{requested}'"
            self._grant(requested)
            return f"[HARNESS] Tool '{requested}' validated and will be exposed next step. Reason: {reason or 'not supplied'}"
        if self.registry.get(name) is not None and name not in self.active_names:
            self._grant(name)
            return f"[HARNESS] Registered tool '{name}' was outside the active subset and will be exposed next step; call it again then."
        return None

    def _grant(self, name: str) -> None:
        if name not in self.granted_names:
            self.granted_names.append(name)
        maximum_grants = max(1, self.budget - 5)
        self.granted_names = self.granted_names[-maximum_grants:]


class TrajectoryLogger:
    """Lossless per-step JSONL trace kept separately from the compact audit log."""

    def __init__(self, mode: str, run_id: str | None = None, root: Path | None = None) -> None:
        directory = Path(root) if root is not None else LOG_DIR / "trajectories"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_id = run_id or uuid.uuid4().hex[:10]
        self.path = directory / f"{stamp}-{mode}-{self.run_id}.jsonl"

    def log_step(
        self,
        *,
        step: int,
        task_type: TaskType | str,
        active_tools: Sequence[str],
        tool_call: Mapping[str, object] | None,
        observation_raw: str,
        observation_truncated: str,
        event: str = "tool",
    ) -> None:
        entry = {
            "ts": datetime.now().isoformat(),
            "run_id": self.run_id,
            "step": step,
            "event": event,
            "task_type": str(getattr(task_type, "value", task_type)),
            "active_tools": list(active_tools),
            "tool_call": dict(tool_call) if tool_call is not None else None,
            "observation_raw": observation_raw,
            "observation_truncated": observation_truncated,
            "token_count": max(1, len(observation_truncated) // 4) if observation_truncated else 0,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
