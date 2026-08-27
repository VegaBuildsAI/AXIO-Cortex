"""Adapters that register RevRec domain handlers in the shared Code registry."""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from .registry import CodeTool, ToolResult


_WRITE_TOOLS = {
    "create_allocation_schedule",
    "create_deferred_revenue_schedule",
    "create_variable_consideration_model",
    "create_contract_modification_analysis",
    "write_memo",
}

_TASK_TYPES = {
    "analyze_contract": ("RESEARCH", "PLANNING"),
    "create_allocation_schedule": ("CODE_EDIT", "FILE_OPS"),
    "create_deferred_revenue_schedule": ("CODE_EDIT", "FILE_OPS"),
    "create_variable_consideration_model": ("CODE_EDIT", "FILE_OPS"),
    "create_contract_modification_analysis": ("CODE_EDIT", "FILE_OPS"),
    "read_excel": ("RESEARCH", "FILE_OPS"),
    "write_memo": ("CODE_EDIT", "FILE_OPS"),
    "read_pdf": ("RESEARCH", "FILE_OPS"),
    "list_outputs": ("FILE_OPS", "PLANNING"),
}


def _adapt_handler(name: str, handler: Callable[..., object], risk: str) -> Callable[..., ToolResult]:
    def adapted(**arguments: object) -> ToolResult:
        content = str(handler(**arguments))
        ok = not content.startswith(("ERROR:", "ERROR ", "CANCELLED:"))
        checks = (f"finance:{name}",) if ok and risk == "write" else ()
        return ToolResult(content=content, ok=ok, verification_ids=checks)

    return adapted


def build_finance_tools(
    ollama_schemas: Sequence[Mapping[str, object]],
    handlers: Mapping[str, Callable[..., object]],
) -> tuple[CodeTool, ...]:
    """Convert the maintained RevRec schemas without duplicating their definitions."""
    tools: list[CodeTool] = []
    for schema in ollama_schemas:
        function = schema.get("function") if isinstance(schema, Mapping) else None
        if not isinstance(function, Mapping):
            continue
        name = str(function.get("name", ""))
        handler = handlers.get(name)
        if not name or handler is None or name in {"read_file", "run_command"}:
            continue
        risk = "write" if name in _WRITE_TOOLS else "read"
        tools.append(CodeTool(
            name=name,
            description=str(function.get("description", "")),
            input_schema=dict(function.get("parameters") or {"type": "object", "properties": {}}),
            handler=_adapt_handler(name, handler, risk),
            risk=risk,
            category="finance",
            task_types=_TASK_TYPES.get(name, ("RESEARCH",)),
        ))
    return tuple(tools)
