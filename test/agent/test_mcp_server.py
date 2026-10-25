"""The MCP server: the registry, served to chat clients like Claude.

The user's normal chat interface becomes a ChiSurf driver: every agent tool
appears as an MCP tool, answers come back as text, and the destructive tier
stays out. Tests drive ``handle_message`` directly — no process, no stdio.
"""

from __future__ import annotations

import json

from chisurf.core.agent.mcp_server import McpServer


def make_request(method, params=None, id_=1):
    message = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        message["params"] = params
    return message


def test_initialize_and_ping(tmp_path):
    server = McpServer(context=_context(tmp_path))
    result = server.handle_message(make_request("initialize", {"protocolVersion": "x"}, 1))["result"]
    assert result["serverInfo"]["name"] == "chisurf"
    assert "tools" in result["capabilities"]
    assert server.handle_message(make_request("ping", id_=2))["result"] == {}


def test_the_full_registry_is_listed_with_schemas(tmp_path):
    server = McpServer(context=_context(tmp_path))
    tools = server.handle_message(make_request("tools/list", {}, 3))["result"]["tools"]
    names = {t["name"] for t in tools}
    for expected in ("run_burst_analysis", "select_species", "fit_distance_distribution",
                     "ask_user", "record_finding", "save_skill", "list_files"):
        assert expected in names
    # Arbitrary-code execution stays out of the served tier by default.
    assert "run_python" not in names
    schema = next(t for t in tools if t["name"] == "save_skill")["inputSchema"]
    assert schema["required"] == ["title", "body"]


def test_the_destructive_tier_is_not_served(tmp_path):
    server = McpServer(context=_context(tmp_path))
    tools = {t["name"] for t in server.handle_message(make_request("tools/list", {}, 4))["result"]["tools"]}
    from chisurf.core.agent.spec import SAFETY_DANGEROUS
    from chisurf.core.agent.tools import build_default_registry

    dangerous = {
        spec.name
        for spec in build_default_registry().filtered(max_safety=SAFETY_DANGEROUS)
        if spec.safety == SAFETY_DANGEROUS
    }
    assert tools.isdisjoint(dangerous)


def test_a_tool_call_returns_the_result_as_text(tmp_path):
    server = McpServer(context=_context(tmp_path))
    (tmp_path / "xy").mkdir()
    result = server.handle_message(
        make_request("tools/call", {"name": "list_files", "arguments": {"directory": str(tmp_path)}}, 5)
    )["result"]
    assert result["isError"] is False
    payload = json.loads(result["content"][0]["text"])
    assert "xy" in json.dumps(payload)


def test_a_tool_error_comes_back_as_iserror_not_a_crash(tmp_path):
    server = McpServer(context=_context(tmp_path))
    result = server.handle_message(
        make_request("tools/call", {"name": "nope", "arguments": {}}, 6)
    )
    assert result["error"]["code"] == -32603 or result["result"]["isError"]


def _context(directory):
    from chisurf.core.agent.context import AgentContext

    return AgentContext(working_directory=str(directory))
