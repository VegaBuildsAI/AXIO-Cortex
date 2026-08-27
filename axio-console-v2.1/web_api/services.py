from __future__ import annotations

import difflib
import json
import subprocess
from pathlib import Path

import requests

from core.config import (
    CLAUDE_MODEL,
    LOCAL_ONLY,
    MAX_FILE_CHARS,
    MAX_ITERS,
    MODELS,
    OLLAMA_HOST,
    TIMEOUT,
)
from core import pricing
from core.logger import AuditLogger
from core.mode_memory import ModeMemorySession
from core.models import ClaudeClient, OllamaClient

from .runs import RunManager, RunState
from .store import ConversationStore
from .workspaces import WorkspaceRegistry


CODE_SYSTEM_PROMPT = """You are AXIO Code, a careful local coding agent.
Work only inside the active workspace. Use tools to inspect before changing files.
Protected actions require user approval. Complete and verify the task when possible.
Never claim a command, edit, or test ran unless its tool result confirms it."""


CLAUDE_TOOLS = [
    {
        "name": "list_files",
        "description": "List readable files in the active workspace.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_file",
        "description": "Read a UTF-8 text file relative to the active workspace.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "search_files",
        "description": "Search readable workspace files for a text string.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "file_pattern": {"type": "string", "default": "*"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a text file relative to the workspace. Requires approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "delete_file",
        "description": "Delete a file relative to the workspace. Requires approval.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "run_command",
        "description": "Run an approved PowerShell command inside the workspace.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
]

# OpenAI-style copy of the same tools for the local Ollama agent (/api/chat).
# Derived from CLAUDE_TOOLS so the two schemas never drift.
OLLAMA_CODE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["input_schema"],
        },
    }
    for tool in CLAUDE_TOOLS
]

# Continue-nudge: keep the local agent from ENDING on a planning turn that made
# no tool call (mirrors the terminal Code agent in modes/code.py).
_CODE_MAX_NUDGES = 2
_CODE_NUDGE = (
    "Continue working: call the tools needed to FINISH and VERIFY the task. "
    "Do not just describe what you will do — actually do it now. If the entire "
    "task is already complete and verified, reply with exactly TASK_COMPLETE "
    "followed by a short summary."
)


def _is_complete_signal(text: str) -> bool:
    upper = (text or "").upper()
    return "TASK_COMPLETE" in upper or "TAREA_COMPLETA" in upper


def _strip_complete_signal(text: str) -> str:
    import re

    return re.sub(r"(?i)\b(TASK_COMPLETE|TAREA_COMPLETA)\b[:\-\s]*", "", text or "").strip()


class AxioServices:
    def __init__(
        self,
        store: ConversationStore,
        workspaces: WorkspaceRegistry,
        runs: RunManager,
    ):
        self.store = store
        self.workspaces = workspaces
        self.runs = runs

    def start(self, conversation: dict, content: str, file_ids: list[str]) -> RunState:
        mode = conversation["mode"]
        self.store.add_message(conversation["id"], "user", content)
        worker = {
            "chat": self._chat_worker,
            "cowork": self._cowork_worker,
            "code": self._code_worker,
        }[mode]
        return self.runs.create(
            conversation["id"],
            mode,
            lambda run: worker(run, content, file_ids),
        )

    def _conversation_messages(self, conversation_id: str) -> list[dict]:
        conversation = self.store.get(conversation_id) or {}
        return [
            {"role": message["role"], "content": message["content"]}
            for message in conversation.get("messages", [])
            if message.get("role") in {"user", "assistant"}
        ]

    def _selected_context(
        self,
        conversation: dict,
        file_ids: list[str],
    ) -> tuple[str, list[str]]:
        workspace_id = conversation.get("workspace_id")
        if not workspace_id or not file_ids:
            return "", []
        blocks = []
        names = []
        for file_id in file_ids[:20]:
            item = self.workspaces.read_file(workspace_id, file_id)
            names.append(item["relative_path"])
            blocks.append(
                f"## {item['relative_path']}\n```\n"
                f"{item['content'][:MAX_FILE_CHARS]}\n```"
            )
        return "\n\n".join(blocks), names

    def _stream_ollama(
        self,
        run: RunState,
        messages: list[dict],
        system: str,
        model: str,
    ) -> str:
        payload_messages = [{"role": "system", "content": system}, *messages]
        response = requests.post(
            f"{OLLAMA_HOST.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": payload_messages,
                "stream": True,
                "think": False,
            },
            stream=True,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        output = []
        for line in response.iter_lines():
            if run.cancel.is_set():
                response.close()
                break
            if not line:
                continue
            event = json.loads(line)
            token = event.get("message", {}).get("content", "")
            if token:
                output.append(token)
                self.runs.emit(run.id, "token", {"text": token})
            if event.get("done"):
                break
        return "".join(output)

    def _finish_turn(
        self,
        run: RunState,
        prompt: str,
        response: str,
        mode: str,
        model: str,
        metadata: dict | None = None,
    ) -> None:
        if not response or run.cancel.is_set():
            return
        backend = (metadata or {}).get("backend") or (
            "claude" if mode == "code" else "ollama"
        )
        message = self.store.add_message(
            run.conversation_id,
            "assistant",
            response,
            model=model,
            backend=backend,
        )
        self.runs.emit(run.id, "message", {"message": message})
        logger = AuditLogger(mode)
        logger.log_turn(prompt, response, model, route=mode)
        try:
            memory = ModeMemorySession(mode)
            memory.record_turn(prompt, response, model=model, metadata=metadata or {})
            # This path persists one UI turn, not a conversation close. Avoid
            # spawning the heavier exit consolidation after every response.
            memory.store(
                ollama_client=OllamaClient(),
                trigger_consolidation=False,
            )
        except OSError as exc:
            self.runs.emit(
                run.id,
                "warning",
                {
                    "message": (
                        "The response was saved, but persistent memory could not "
                        f"be updated: {exc}"
                    )
                },
            )

    def _chat_worker(self, run: RunState, content: str, file_ids: list[str]) -> None:
        conversation = self.store.get(run.conversation_id)
        context, names = self._selected_context(conversation, file_ids)
        memory = ModeMemorySession("chat")
        prefix = memory.prefix(content)
        messages = self._conversation_messages(run.conversation_id)
        if context or prefix:
            messages[-1]["content"] = "\n\n".join(
                part
                for part in [
                    prefix.strip(),
                    f"Selected files:\n{context}" if context else "",
                    content,
                ]
                if part
            )
        model = MODELS["chat"]
        self.runs.emit(
            run.id,
            "status",
            {"label": "Thinking locally", "model": model, "files": names},
        )
        response = self._stream_ollama(
            run,
            messages,
            "You are AXIO Chat, a precise local-first assistant with persistent memory.",
            model,
        )
        self._finish_turn(
            run,
            content,
            response,
            "chat",
            model,
            {"selected_files": ",".join(names)},
        )

    def _cowork_worker(self, run: RunState, content: str, file_ids: list[str]) -> None:
        conversation = self.store.get(run.conversation_id)
        context, names = self._selected_context(conversation, file_ids)
        memory = ModeMemorySession("cowork")
        prefix = memory.prefix(content)
        messages = self._conversation_messages(run.conversation_id)
        messages[-1]["content"] = "\n\n".join(
            part
            for part in [
                prefix.strip(),
                f"Workspace context:\n{context}" if context else "",
                f"User request: {content}",
            ]
            if part
        )
        model = MODELS["reasoning"]
        self.runs.emit(
            run.id,
            "status",
            {"label": "Working with local context", "model": model, "files": names},
        )
        response = self._stream_ollama(
            run,
            messages,
            "You are AXIO Cowork. Analyze the provided workspace context carefully. "
            "Do not claim to have read files that were not provided.",
            model,
        )
        self._finish_turn(
            run,
            content,
            response,
            "cowork",
            model,
            {"selected_files": ",".join(names)},
        )

    def _code_worker(self, run: RunState, content: str, file_ids: list[str]) -> None:
        conversation = self.store.get(run.conversation_id)
        workspace_id = conversation.get("workspace_id")
        if not workspace_id:
            raise ValueError("Code mode requires an active workspace.")
        if LOCAL_ONLY:
            self._code_worker_local(run, content, workspace_id)
        else:
            self._code_worker_claude(run, content, workspace_id)

    def _code_worker_local(self, run: RunState, content: str, workspace_id: str) -> None:
        """On-device coding agent: Ollama tool-calling over the workspace tools,
        reusing the same approval flow as the Claude path."""
        model = MODELS["coding"]
        ollama = OllamaClient()
        messages = [
            {"role": "system", "content": CODE_SYSTEM_PROMPT},
            *self._conversation_messages(run.conversation_id),
        ]
        final_text = ""
        nudges = 0
        self.runs.emit(
            run.id,
            "status",
            {"label": "Local coding agent active", "model": model},
        )

        for step in range(MAX_ITERS):
            if run.cancel.is_set():
                return
            self.runs.emit(run.id, "status", {"label": f"Agent step {step + 1}"})
            try:
                data = ollama.tool_call(model, messages, OLLAMA_CODE_TOOLS)
            except Exception as exc:
                raise RuntimeError(f"Local coding agent failed: {exc}") from exc

            message = data.get("message", {}) if isinstance(data, dict) else {}
            tool_calls = message.get("tool_calls") or []
            text = (message.get("content") or "").strip()

            if not tool_calls:
                if _is_complete_signal(text) or nudges >= _CODE_MAX_NUDGES:
                    final_text = _strip_complete_signal(text)
                    if final_text:
                        self.runs.emit(run.id, "token", {"text": final_text})
                    break
                nudges += 1
                messages.append({"role": "assistant", "content": text})
                messages.append({"role": "user", "content": _CODE_NUDGE})
                continue

            nudges = 0
            messages.append(
                {"role": "assistant", "content": text, "tool_calls": tool_calls}
            )
            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                name = function.get("name", "")
                args = function.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                self.runs.emit(
                    run.id,
                    "tool_started",
                    {"tool": name, "arguments": args},
                )
                result = self._execute_code_tool(run, workspace_id, name, args)
                self.runs.emit(
                    run.id,
                    "tool_result",
                    {"tool": name, "result": result[:8_000]},
                )
                messages.append({"role": "tool", "content": result})
        else:
            raise RuntimeError(f"Code agent reached the {MAX_ITERS}-step limit.")

        self._finish_turn(
            run,
            content,
            final_text,
            "code",
            model,
            {"backend": "ollama", "workspace_id": workspace_id},
        )

    def _code_worker_claude(self, run: RunState, content: str, workspace_id: str) -> None:
        claude = ClaudeClient(model=CLAUDE_MODEL)
        messages = self._conversation_messages(run.conversation_id)
        final_text = ""
        usage_acc = {}
        self.runs.emit(
            run.id,
            "status",
            {"label": "Claude coding agent active", "model": CLAUDE_MODEL},
        )

        for step in range(MAX_ITERS):
            if run.cancel.is_set():
                return
            self.runs.emit(run.id, "status", {"label": f"Agent step {step + 1}"})
            try:
                response = claude.tool_call(
                    messages,
                    CLAUDE_TOOLS,
                    system=CODE_SYSTEM_PROMPT,
                )
            except Exception as exc:
                if (
                    exc.__class__.__name__ == "APIConnectionError"
                    or "connection error" in str(exc).lower()
                ):
                    raise RuntimeError(
                        "Claude API connection failed. Verify internet access and "
                        "launch AXIO with run_ui.cmd outside a restricted sandbox."
                    ) from exc
                raise
            if response is None:
                raise RuntimeError("Claude returned no response.")
            pricing.add(usage_acc, getattr(response, "usage", None))
            text_parts = [
                block.text for block in response.content if getattr(block, "type", "") == "text"
            ]
            tool_uses = [
                block for block in response.content if getattr(block, "type", "") == "tool_use"
            ]
            messages.append({"role": "assistant", "content": response.content})
            if not tool_uses:
                final_text = "\n".join(text_parts).strip()
                if final_text:
                    self.runs.emit(run.id, "token", {"text": final_text})
                break

            tool_results = []
            for tool_use in tool_uses:
                args = tool_use.input if isinstance(tool_use.input, dict) else {}
                self.runs.emit(
                    run.id,
                    "tool_started",
                    {"tool": tool_use.name, "arguments": args},
                )
                result = self._execute_code_tool(
                    run,
                    workspace_id,
                    tool_use.name,
                    args,
                )
                self.runs.emit(
                    run.id,
                    "tool_result",
                    {"tool": tool_use.name, "result": result[:8_000]},
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
        else:
            raise RuntimeError(f"Code agent reached the {MAX_ITERS}-step limit.")

        _tokens = pricing.tokens(usage_acc)
        _cost = pricing.cost_usd(CLAUDE_MODEL, usage_acc)
        self.runs.emit(
            run.id,
            "usage",
            {"model": CLAUDE_MODEL, "tokens": _tokens, "cost_usd": _cost,
             "summary": pricing.summarize(CLAUDE_MODEL, usage_acc)},
        )
        self._finish_turn(
            run,
            content,
            final_text,
            "code",
            CLAUDE_MODEL,
            {"backend": "claude", "workspace_id": workspace_id,
             "tokens": _tokens, "cost_usd": _cost},
        )

    def _execute_code_tool(
        self,
        run: RunState,
        workspace_id: str,
        name: str,
        args: dict,
    ) -> str:
        if name == "list_files":
            files = self.workspaces.files(workspace_id)
            return "\n".join(item["relative_path"] for item in files) or "[empty workspace]"

        if name == "read_file":
            path = self.workspaces.resolve(workspace_id, str(args.get("path", "")))
            if not path.is_file():
                return "ERROR: not a file"
            return path.read_text(encoding="utf-8", errors="replace")[:200_000]

        if name == "search_files":
            query = str(args.get("query", ""))
            pattern = str(args.get("file_pattern", "*"))
            root = Path(self.workspaces.get(workspace_id)["path"])
            matches = []
            for path in root.rglob(pattern):
                if len(matches) >= 100 or not path.is_file():
                    continue
                try:
                    safe = self.workspaces.resolve(workspace_id, path.relative_to(root).as_posix())
                    for line_no, line in enumerate(
                        safe.read_text(encoding="utf-8", errors="replace").splitlines(),
                        1,
                    ):
                        if query.lower() in line.lower():
                            matches.append(f"{safe.relative_to(root)}:{line_no}: {line[:240]}")
                except (OSError, ValueError):
                    continue
            return "\n".join(matches) or "No matches."

        if name == "write_file":
            relative = str(args.get("path", ""))
            content = str(args.get("content", ""))
            target = self.workspaces.resolve(workspace_id, relative, must_exist=False)
            old = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
            diff = "\n".join(
                difflib.unified_diff(
                    old.splitlines(),
                    content.splitlines(),
                    fromfile=f"a/{relative}",
                    tofile=f"b/{relative}",
                    lineterm="",
                )
            )
            self.runs.emit(run.id, "diff", {"path": relative, "diff": diff})
            approval = self.runs.request_approval(
                run,
                "write_file",
                {"path": relative, "diff": diff[:20_000]},
            )
            if approval.decision != "approved":
                return f"DENIED: {approval.note or 'User denied file write.'}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Written: {relative}"

        if name == "delete_file":
            relative = str(args.get("path", ""))
            target = self.workspaces.resolve(workspace_id, relative)
            approval = self.runs.request_approval(
                run,
                "delete_file",
                {"path": relative},
            )
            if approval.decision != "approved":
                return f"DENIED: {approval.note or 'User denied deletion.'}"
            if not target.is_file():
                return "ERROR: not a file"
            target.unlink()
            return f"Deleted: {relative}"

        if name == "run_command":
            command = str(args.get("command", ""))
            approval = self.runs.request_approval(
                run,
                "run_command",
                {"command": command},
            )
            if approval.decision != "approved":
                return f"DENIED: {approval.note or 'User denied command.'}"
            root = Path(self.workspaces.get(workspace_id)["path"])
            completed = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=300,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            return f"exit_code={completed.returncode}\n{output[:40_000]}"

        return f"ERROR: unknown tool {name}"
