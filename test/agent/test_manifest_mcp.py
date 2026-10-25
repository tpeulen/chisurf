"""Manifest-driven RPC tools: every plugin's declared backend surface, as MCP.

The manifests are the contract — ``rpc_methods`` entries (dotted name,
summary, long_running) become MCP tools automatically, so a new plugin's
backend is visible to chat clients without hand-written wrappers. Raw
backend calls are the full API surface, so they are born in the destructive
tier and only reach the served MCP list when allowlisted
(``CHISURF_MCP_RPC_SERVED``).
"""

from __future__ import annotations

import json

from chisurf.core.agent.mcp_server import McpServer, register_manifest_rpc_tools
from chisurf.core.agent.spec import SAFETY_DANGEROUS, SAFETY_WRITE, ToolRegistry


def test_manifest_rpc_methods_become_registry_tools():
    registry = ToolRegistry()
    added = register_manifest_rpc_tools(registry)
    assert added > 40, "the repo's manifests declare many rpc_methods"
    assert "rpc_burst_2cde_jobs_compute" in registry.names()
    spec = registry.get("rpc_burst_2cde_jobs_compute")
    assert spec is not None
    assert spec.safety == SAFETY_DANGEROUS
    assert "2CDE" in spec.description and "burst_2cde.jobs.compute" in spec.description


def test_rpc_tools_are_not_served_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("CHISURF_MCP_RPC_SERVED", raising=False)
    server = McpServer(context=_context(tmp_path))
    tools = {t["name"] for t in server.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )["result"]["tools"]}
    assert not [n for n in tools if n.startswith("rpc_")]


def test_the_allowlist_serves_named_methods(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_MCP_RPC_SERVED", "burst_2cde.jobs.compute")
    server = McpServer(context=_context(tmp_path))
    tools = {t["name"] for t in server.handle_message(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )["result"]["tools"]}
    assert "rpc_burst_2cde_jobs_compute" in tools
    assert not [n for n in tools if n.startswith("rpc_") and n != "rpc_burst_2cde_jobs_compute"]


def test_generated_tools_bind_their_own_method(tmp_path, monkeypatch):
    """No late binding: each generated tool carries its own method's description."""
    monkeypatch.setenv("CHISURF_MCP_RPC_SERVED", "*")
    registry = ToolRegistry()
    register_manifest_rpc_tools(registry)
    names = [n for n in registry.names() if n.startswith("rpc_")]
    assert len(names) > 40
    descriptions = {registry.get(n).description for n in names}
    assert len(descriptions) == len(names), "every tool must describe its own method"
    probe = registry.get("rpc_burst_2cde_workflow_prepare")
    assert probe is not None and "burst_2cde.workflow.prepare" in probe.description


def _context(directory):
    from chisurf.core.agent.context import AgentContext

    return AgentContext(working_directory=str(directory))
