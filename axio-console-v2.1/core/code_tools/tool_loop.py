"""A lean, reusable model<->tool loop shared by Chat, Cowork, and the agent runtime.

This is intentionally simpler than Code mode's full agentic harness (no dynamic
tool router, verification gate, or completion nudges): it drives a bounded
tool-calling conversation over a *subset* of the 42-tool registry, executes each
requested tool through the registry's own risk/approval gate, and returns the
model's final text. Tools outside the allowed subset are refused with an
ISOLATION_ERROR string (never raised), which is the same isolation guarantee the
agent dispatcher relies on.

Both backends are supported and share the registry executor:
  * Ollama  -> OllamaClient.tool_call(model, messages, schemas)
  * Claude  -> ClaudeClient.tool_call(messages, schemas, system=...)
"""

from __future__ import annotations

import json
from typing import Callable, Sequence

from . import CODE_TOOL_REGISTRY, summarize_arguments

ApproveFn = Callable[[object, dict], bool]
AuditFn = Callable[[object, dict, str], None]


def resolve_tools(names: Sequence[str]) -> list:
    """Registry CodeTool objects for the given names, preserving order."""
    resolved = []
    for name in names:
        tool = CODE_TOOL_REGISTRY.get(name)
        if tool is not None:
            resolved.append(tool)
    return resolved


def interactive_approver(tool, args: dict) -> bool:
    """Default terminal approval gate, matching Code mode's conventions."""
    print(f"\n  [tool] requests {tool.risk} tool: {tool.name}")
    print(f"    {summarize_arguments(args)}")
    try:
        if tool.risk == "destructive":
            return input("  Type DELETE to allow permanent deletion: ").strip() == "DELETE"
        if tool.risk == "external":
            return input("  Type ALLOW to authorize the external action: ").strip() == "ALLOW"
        return input("  Allow? (y/n): ").strip().lower() == "y"
    except (KeyboardInterrupt, EOFError):
        return False


def _execute(name: str, args: dict, allowed: set[str],
             approve: ApproveFn | None, audit: AuditFn | None) -> str:
    if name not in allowed:
        return (f"ISOLATION_ERROR: '{name}' is not available in this mode. "
                f"Allowed: {sorted(allowed)}")
    return CODE_TOOL_REGISTRY.execute(name, args, approve=approve, audit=audit)


def run_tool_loop(
    *,
    tool_names: Sequence[str],
    provider: str,
    messages: list[dict],
    model: str | None = None,
    ollama=None,
    claude=None,
    system: str = "",
    approve: ApproveFn | None = None,
    audit: AuditFn | None = None,
    max_steps: int = 6,
    verbose: bool = True,
) -> str:
    """Run a bounded tool-calling loop and return the model's final text.

    `messages` is mutated in place with the assistant/tool turns so the caller
    can persist the full exchange if desired. `provider` is "ollama" or "claude".
    """
    provider = provider.strip().lower()
    tools = resolve_tools(tool_names)
    allowed = {tool.name for tool in tools}
    schemas = CODE_TOOL_REGISTRY.emit_subset(tools, provider)
    if approve is None:
        approve = interactive_approver

    def _run_call(name: str, raw_args) -> str:
        args = raw_args
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if not isinstance(args, dict):
            args = {}
        if verbose:
            print(f"  {name}({summarize_arguments(args, limit=50)})")
        out = _execute(name, args, allowed, approve, audit)
        if verbose:
            preview = out[:100].replace("\n", " ")
            print(f"    {preview}{'...' if len(out) > 100 else ''}")
        return out

    for _ in range(max_steps):
        if provider == "ollama":
            data = ollama.tool_call(model, messages, schemas)
            message = data.get("message", {})
            calls = message.get("tool_calls", [])
            content = (message.get("content") or "").strip()
            if not calls:
                return content
            messages.append({"role": "assistant", "content": content, "tool_calls": calls})
            for call in calls:
                fn = call.get("function", {})
                out = _run_call(fn.get("name", ""), fn.get("arguments", {}))
                messages.append({"role": "tool", "content": out})
        elif provider == "claude":
            response = claude.tool_call(messages, schemas, system=system)
            if response is None:
                return "Claude returned no response"
            text_parts = [b.text for b in response.content if b.type == "text"]
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use" or not tool_uses:
                return "\n".join(text_parts).strip()
            results = []
            for tu in tool_uses:
                out = _run_call(tu.name, tu.input if isinstance(tu.input, dict) else {})
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out})
            messages.append({"role": "user", "content": results})
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    return "(stopped: reached the tool-step limit before a final answer)"
