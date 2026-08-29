"""Fase B / Fase E2 — agent registry, tool isolation, internet isolation."""
from agents.base import IMPLEMENTED_TOOLS
from agents.registry import AGENT_REGISTRY, get, internet_agents
from harness import dispatcher


def test_eight_agents_present():
    assert set(AGENT_REGISTRY) == {
        "FSAgent", "RunAgent", "SearchAgent", "WebAgent",
        "GitAgent", "TestAgent", "PlanAgent", "CtxAgent",
    }


def test_only_webagent_has_internet():
    assert internet_agents() == ["WebAgent"]


def test_live_tools_are_all_implemented():
    for spec in AGENT_REGISTRY.values():
        for t in spec.live_tools():
            assert t in IMPLEMENTED_TOOLS, f"{spec.name}: {t} not implemented"


def test_fsagent_live_tools():
    live = set(get("FSAgent").live_tools())
    assert {"read_file", "write_file", "edit_file", "list_dir",
            "create_dir", "delete_file"} <= live
    assert "run_command" not in live         # FS never executes code


def test_searchagent_has_no_bash_execution():
    live = get("SearchAgent").live_tools()
    assert "run_command" not in live         # Search is read-only, no bash


def test_dispatcher_isolation_refuses_foreign_tool():
    # FSAgent may not run_command — dispatcher must refuse before executing.
    out = dispatcher.execute_for(get("FSAgent"), "run_command", {"command": "echo hi"})
    assert out.startswith("ISOLATION_ERROR")


def test_dispatcher_schemas_scoped_per_agent():
    fs = {t["function"]["name"] for t in dispatcher.tool_schemas_for(get("FSAgent"))}
    assert "run_command" not in fs
    assert "read_file" in fs
    run = {t["function"]["name"] for t in dispatcher.tool_schemas_for(get("RunAgent"))}
    # Over the 42-tool registry RunAgent's live execute tools are run_command and
    # run_python; it still may not touch filesystem/web tools.
    assert run == {"run_command", "run_python"}
    assert "read_file" not in run and "web_search" not in run


def test_peer_map_guard():
    assert get("SearchAgent").can_call("WebAgent") is True
    assert get("SearchAgent").can_call("GitAgent") is False
