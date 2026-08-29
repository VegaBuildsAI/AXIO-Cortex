"""
AXIO Harness -- Dispatcher  (Plan Fase C · C2)

Builds the model payload for a single agent: its specialized system prompt plus
*only* the tool schemas in that agent's live tool set — never the full registry,
and never another agent's tools. This is where tool isolation is enforced on the
way in (which schemas the model sees) and on the way out (`execute_for` refuses
any tool outside the agent's set).

The concrete tool catalogue and executor are the shared 42-tool
``core.code_tools.CODE_TOOL_REGISTRY``; it is imported lazily so the harness
package stays importable in a bare test env.
"""

from __future__ import annotations

from agents.base import AgentSpec


def _registry():
    from core.code_tools import CODE_TOOL_REGISTRY
    return CODE_TOOL_REGISTRY


def _live_tool_objects(spec: AgentSpec) -> list:
    reg = _registry()
    objs = []
    for name in spec.live_tools():
        tool = reg.get(name)
        if tool is not None:
            objs.append(tool)
    return objs


def tool_schemas_for(spec: AgentSpec, provider: str = "ollama") -> list[dict]:
    """Provider schemas for the subset of tools this agent may call today."""
    return _registry().emit_subset(_live_tool_objects(spec), provider)


def build_payload(spec: AgentSpec, model: str, task: str,
                  memory_prefix: str = "", provider: str = "ollama") -> dict:
    """Assemble a request payload scoped to one agent.

    The caller supplies the model name (orchestrator routing decision) and an
    optional memory prefix. The returned dict feeds OllamaClient.tool_call
    (provider="ollama") or the equivalent Claude call (provider="claude").
    """
    system = spec.system_prompt
    if memory_prefix:
        system = f"{memory_prefix}\n\n{system}"
    return {
        "model": model,
        "agent": spec.name,
        "system": system,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ],
        "tools": tool_schemas_for(spec, provider),
    }


def execute_for(spec: AgentSpec, name: str, args: dict, *,
                approve=None, audit=None) -> str:
    """Execute a tool call on behalf of an agent, enforcing its tool set.

    Returns an ISOLATION error string (never raises) if the tool is outside the
    agent's live set — the guarantee tested by the agent-isolation suite. When
    allowed, the call goes through the registry's own risk/approval gate.
    """
    if name not in spec.live_tools():
        return (f"ISOLATION_ERROR: {spec.name} may not call '{name}'. "
                f"Allowed: {list(spec.live_tools())}")
    return _registry().execute(name, args, approve=approve, audit=audit)
