"""
AXIO Harness -- Dispatcher  (Plan Fase C · C2)

Builds the model payload for a single agent: its specialized system prompt plus
*only* the tool schemas in that agent's live tool set — never the full 9-tool
catalogue, and never another agent's tools. This is where tool isolation is
enforced on the way in (which schemas the model sees) and on the way out
(`execute_for` refuses any tool outside the agent's set).

The concrete tool catalogue and executor live in modes/code.py; they are
imported lazily so the harness package stays importable in a bare test env.
"""

from __future__ import annotations

from agents.base import AgentSpec


def _catalogue():
    """(schemas_by_name, execute_tool) from the live Code Mode tool catalogue."""
    from modes.code import TOOLS, execute_tool
    schemas = {t["function"]["name"]: t for t in TOOLS}
    return schemas, execute_tool


def tool_schemas_for(spec: AgentSpec) -> list[dict]:
    """The subset of concrete tool schemas this agent is allowed to call today."""
    schemas, _ = _catalogue()
    live = spec.live_tools()
    return [schemas[name] for name in live if name in schemas]


def build_payload(spec: AgentSpec, model: str, task: str,
                  memory_prefix: str = "") -> dict:
    """Assemble an Ollama-style request payload scoped to one agent.

    The caller supplies the model name (orchestrator routing decision) and an
    optional memory prefix. The returned dict is backend-agnostic enough to feed
    OllamaClient.tool_call(model, messages, tools).
    """
    system = spec.system_prompt
    if memory_prefix:
        system = f"{memory_prefix}\n\n{system}"
    return {
        "model": model,
        "agent": spec.name,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ],
        "tools": tool_schemas_for(spec),
    }


def execute_for(spec: AgentSpec, name: str, args: dict) -> str:
    """Execute a tool call on behalf of an agent, enforcing its tool set.

    Returns an ISOLATION error string (never raises) if the tool is outside the
    agent's live set — this is the guarantee tested by the agent-isolation suite.
    Path resolution still happens inside modes.code.execute_tool.
    """
    if name not in spec.live_tools():
        return (f"ISOLATION_ERROR: {spec.name} may not call '{name}'. "
                f"Allowed: {list(spec.live_tools())}")
    _, execute_tool = _catalogue()
    return execute_tool(name, args)
