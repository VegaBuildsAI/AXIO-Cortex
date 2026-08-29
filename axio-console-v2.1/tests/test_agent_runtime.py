"""Agent runtime: live tool execution, peer delegation, depth guard."""

from __future__ import annotations

import unittest

from agents.registry import get
from harness.agent_runtime import DELEGATE_TOOL, MAX_DELEGATION_DEPTH, make_run_agent, run_agent
from harness.event_bus import EventBus


class ScriptedOllama:
    """Replays scripted /api/chat responses and records the tools it was offered."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.tool_names_seen = []

    def tool_call(self, model, messages, tools):
        self.tool_names_seen.append({t["function"]["name"] for t in tools})
        return self._responses.pop(0)


def _final(text):
    return {"message": {"content": text}}


def _call(name, args):
    return {"message": {"content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}}


class AgentRuntimeTests(unittest.TestCase):
    def test_agent_executes_tool_then_finishes(self):
        fake = ScriptedOllama([
            _call("list_dir", {"path": "."}),   # FSAgent's live tool
            _final("done"),
        ])
        resp = run_agent(get("FSAgent"), "list the folder", provider="ollama",
                         model="x", ollama=fake, approve=lambda *_: True, verbose=False)
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["result"], "done")

    def test_delegate_tool_offered_only_under_depth_cap(self):
        # depth 0: SearchAgent (peers -> WebAgent) is offered the delegate tool.
        fake0 = ScriptedOllama([_final("ok")])
        run_agent(get("SearchAgent"), "q", provider="ollama", model="x",
                  ollama=fake0, verbose=False, depth=0)
        self.assertIn(DELEGATE_TOOL, fake0.tool_names_seen[0])

        # at the depth cap: no delegate tool is exposed (prevents runaway recursion).
        fakeN = ScriptedOllama([_final("ok")])
        run_agent(get("SearchAgent"), "q", provider="ollama", model="x",
                  ollama=fakeN, verbose=False, depth=MAX_DELEGATION_DEPTH)
        self.assertNotIn(DELEGATE_TOOL, fakeN.tool_names_seen[0])

    def test_peer_delegation_runs_peer_and_logs_bus(self):
        bus = EventBus()
        # SearchAgent delegates to WebAgent (an allowed peer); WebAgent answers.
        fake = ScriptedOllama([
            _call(DELEGATE_TOOL, {"peer": "WebAgent", "subtask": "find the release date"}),
            _final("release date is 2026"),          # WebAgent's reply
            _final("answer: 2026 (via WebAgent)"),    # SearchAgent's final synthesis
        ])
        resp = run_agent(get("SearchAgent"), "when was it released?", provider="ollama",
                         model="x", ollama=fake, verbose=False, bus=bus)
        self.assertEqual(resp["status"], "ok")
        self.assertIn("2026", resp["result"])
        self.assertTrue(any(m.msg_type == "PEER_DELEGATE" for m in bus.history))

    def test_peer_delegation_denied_for_non_peer(self):
        bus = EventBus()
        # SearchAgent may NOT call GitAgent -> the delegate observation is PEER_DENIED,
        # and GitAgent is never invoked (only two model turns happen).
        fake = ScriptedOllama([
            _call(DELEGATE_TOOL, {"peer": "GitAgent", "subtask": "commit"}),
            _final("could not delegate"),
        ])
        resp = run_agent(get("SearchAgent"), "commit please", provider="ollama",
                         model="x", ollama=fake, verbose=False, bus=bus)
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(len(fake._responses), 0)                 # exactly two turns consumed
        self.assertFalse(any(m.msg_type == "PEER_DELEGATE" for m in bus.history))

    def test_make_run_agent_binds_context_for_orchestrator(self):
        fake = ScriptedOllama([_final("bound ok")])
        runner = make_run_agent(provider="ollama", model="x", ollama=fake, verbose=False)
        resp = runner(get("CtxAgent"), "load context")
        self.assertEqual(resp, {"status": "ok", "result": "bound ok"})


if __name__ == "__main__":
    unittest.main()
