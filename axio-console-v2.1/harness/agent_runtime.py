"""
AXIO Harness -- Agent Runtime

Turns a per-agent :class:`AgentSpec` into a live model<->tool loop and provides
the ``run_agent(spec, task) -> {"status","result"}`` callable the Orchestrator
injects. Each agent:

  * sees ONLY its own tool subset (dispatcher isolation over the 42-tool registry),
  * executes tools through the registry's shared risk/approval gate, and
  * when its spec grants ``peers``, may delegate a focused subtask to a peer via a
    synthetic ``delegate_to_peer`` tool — the peer-to-peer channel — bounded by a
    recursion-depth guard and the spec's ``can_call`` allow-map.

This is the missing link between B's Orchestrator (which injects ``run_agent``)
and the live Ollama/Claude models.
"""

from __future__ import annotations

from agents.base import AgentSpec
from agents.registry import get
from core.code_tools.tool_loop import run_tool_loop

DELEGATE_TOOL = "delegate_to_peer"
MAX_DELEGATION_DEPTH = 2


def _delegate_schema(spec: AgentSpec, provider: str) -> dict:
    peers = list(spec.peers)
    desc = ("Delegate a focused, self-contained subtask to a peer agent and receive "
            f"its result. Allowed peers: {peers}.")
    params = {
        "type": "object",
        "properties": {
            "peer": {"type": "string", "enum": peers, "description": "Peer agent name."},
            "subtask": {"type": "string", "description": "Self-contained subtask for the peer."},
        },
        "required": ["peer", "subtask"],
    }
    if provider == "claude":
        return {"name": DELEGATE_TOOL, "description": desc, "input_schema": params}
    return {"type": "function",
            "function": {"name": DELEGATE_TOOL, "description": desc, "parameters": params}}


def run_agent(spec: AgentSpec, task: str, *, provider: str, model=None,
              ollama=None, claude=None, approve=None, audit=None,
              memory_prefix: str = "", verbose: bool = True, bus=None,
              depth: int = 0) -> dict:
    """Run one agent to completion, returning {"status": "ok"|"ERROR", ...}."""
    provider = provider.strip().lower()
    system = spec.system_prompt
    if memory_prefix:
        system = f"{memory_prefix}\n\n{system}"

    extra_schemas: list[dict] = []
    special: dict = {}
    if spec.peers and depth < MAX_DELEGATION_DEPTH:
        extra_schemas.append(_delegate_schema(spec, provider))

        def _delegate(args: dict) -> str:
            peer = str(args.get("peer", "")).strip()
            subtask = str(args.get("subtask", "")).strip()
            if not spec.can_call(peer):
                return (f"PEER_DENIED: {spec.name} may not call '{peer}'. "
                        f"Allowed peers: {list(spec.peers)}")
            try:
                peer_spec = get(peer)
            except KeyError as exc:
                return f"PEER_UNKNOWN: {exc}"
            if bus is not None:
                bus.publish(spec.name, peer, "PEER_DELEGATE", {"subtask": subtask[:120]})
            resp = run_agent(
                peer_spec, subtask, provider=provider, model=model, ollama=ollama,
                claude=claude, approve=approve, audit=audit, memory_prefix=memory_prefix,
                verbose=verbose, bus=bus, depth=depth + 1,
            )
            if resp.get("status") == "ok":
                return f"[{peer} result]\n{resp.get('result', '')}"
            return f"[{peer} failed] {resp.get('reason', resp.get('result', ''))}"

        special[DELEGATE_TOOL] = _delegate

    if provider == "ollama":
        messages = [{"role": "system", "content": system}, {"role": "user", "content": task}]
        loop_kwargs = dict(ollama=ollama, model=model)
    else:
        messages = [{"role": "user", "content": task}]
        loop_kwargs = dict(claude=claude, system=system)

    try:
        result = run_tool_loop(
            tool_names=spec.live_tools(), provider=provider, messages=messages,
            approve=approve, audit=audit, max_steps=spec.max_steps, verbose=verbose,
            extra_schemas=extra_schemas, special_handlers=special, **loop_kwargs,
        )
    except Exception as exc:  # a live agent failure must not crash the orchestrator
        return {"status": "ERROR", "reason": f"{spec.name} failed: {exc}"}
    return {"status": "ok", "result": result}


def make_run_agent(*, provider: str, model=None, ollama=None, claude=None,
                   approve=None, audit=None, memory_prefix: str = "",
                   verbose: bool = True, bus=None):
    """Bind runtime context into the ``run_agent(spec, task)`` the Orchestrator needs."""

    def _run(spec: AgentSpec, task: str) -> dict:
        return run_agent(
            spec, task, provider=provider, model=model, ollama=ollama, claude=claude,
            approve=approve, audit=audit, memory_prefix=memory_prefix,
            verbose=verbose, bus=bus, depth=0,
        )

    return _run
