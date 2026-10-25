"""The MCP server: ChiSurf's agent tools, served to MCP clients (Claude, …).

Users who live in a normal chat interface point their MCP client at this
server; every agent tool — the burst chain, the fits, ``run_python``,
``record_finding`` — appears as an MCP tool, so the client's model drives
ChiSurf exactly like the built-in assistant does. The transport is
newline-delimited JSON-RPC over stdio (the same discipline as the ACP
server), which keeps the implementation stdlib-only. Read and write tiers
are served; destructive tools are not, unless the client asks and the user
widens the tier in code.
"""

from __future__ import annotations

import json
import sys
from typing import Any

SERVER_INFO = {"name": "chisurf", "version": "1.0.0"}
PROTOCOL_VERSION = "2024-11-05"


class McpServer:
    """Answer MCP requests against the agent tool registry."""

    def __init__(self, registry: Any = None, context: Any = None, output: Any = None) -> None:
        from chisurf.core.agent.context import AgentContext
        from chisurf.core.agent.spec import SAFETY_WRITE
        from chisurf.core.agent.tools import build_default_registry

        self._output = output or sys.stdout.buffer
        self.registry = registry or build_default_registry()
        self.context = context or AgentContext(working_directory=".")
        # The plugin manifests' declared RPC methods, as tools — born in the
        # destructive tier, so only the allowlisted ones appear below.
        from chisurf.core.agent.mcp_server import register_manifest_rpc_tools

        register_manifest_rpc_tools(self.registry)
        self._tools = {
            spec.name: spec for spec in self.registry.filtered(max_safety=SAFETY_WRITE)
        }

    # ── the MCP surface ───────────────────────────────────────────────────

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Answer one decoded JSON-RPC message; ``None`` for notifications."""
        method = message.get("method", "")
        request_id = message.get("id")
        params = message.get("params") or {}
        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self._tool_list()}
            elif method == "tools/call":
                result = self._call(params)
            elif request_id is None:
                return None  # a notification we do not need to answer
            else:
                result = None
                response = self._error(request_id, -32601, f"unknown method {method!r}")
                self._send(response)
                return response
        except Exception as err:  # noqa: BLE001 - errors are MCP results
            if request_id is None:
                return None
            response = self._error(request_id, -32603, str(err))
            self._send(response)
            return response
        if request_id is None:
            return None
        response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        self._send(response)
        return response

    def serve(self, input_stream: Any = None) -> None:
        """Read newline-delimited requests until the stream closes."""
        stream = input_stream or sys.stdin
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._send(self._error(None, -32700, "invalid JSON"))
                continue
            self.handle_message(message)

    # ── handlers ──────────────────────────────────────────────────────────

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }

    def _tool_list(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "inputSchema": spec.parameters or {"type": "object", "properties": {}},
            }
            for spec in sorted(self._tools.values(), key=lambda s: s.name)
        ]

    def _call(self, params: dict[str, Any]) -> dict[str, Any]:
        from chisurf.core.agent.spec import ToolError, call_handler

        name = str(params.get("name", ""))
        spec = self._tools.get(name)
        if spec is None:
            raise ToolError(f"unknown tool {name!r}")
        try:
            outcome = call_handler(spec, self.context, dict(params.get("arguments") or {}))
        except ToolError as err:
            return {"content": [{"type": "text", "text": str(err)}], "isError": True}
        text = json.dumps(outcome, indent=2, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": False}

    # ── plumbing ──────────────────────────────────────────────────────────

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _send(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        self._output.write(line)
        self._output.flush()


def register_manifest_rpc_tools(registry: Any) -> int:
    """Register one tool per RPC method declared in a plugin manifest.

    The plugin manifests are the contract: ``rpc_methods`` entries carry the
    method's dotted name and summary, so the whole backend surface becomes
    MCP-visible without hand-written wrappers — a new plugin's services show
    up the next time an MCP client connects. Invocation goes through the
    action dispatcher (the same seam the Qt-free server drives). Every
    generated tool is born in the destructive tier: raw backend calls are
    the full API surface, so nothing is served to chat clients until it is
    explicitly allowlisted via ``CHISURF_MCP_RPC_SERVED`` (comma-separated
    method names or ``*``).
    """
    import os
    import re
    from pathlib import Path

    import chisurf
    from chisurf.core.agent.spec import SAFETY_DANGEROUS, SAFETY_WRITE

    served = {
        part.strip()
        for part in os.environ.get("CHISURF_MCP_RPC_SERVED", "").split(",")
        if part.strip()
    }
    serve_all = "*" in served

    def _invoke(context, arguments=None, _method=""):
        from chisurf.core.actions import dispatch

        return dispatch(_method, dict(arguments or {}))

    count = 0
    for manifest_path in sorted((Path(chisurf.__file__).parent / "plugins").rglob("manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        plugin = manifest.get("id") or manifest_path.parent.name
        for method in manifest.get("rpc_methods") or []:
            name = str(method.get("name", "")).strip()
            if not name:
                continue
            tool_name = re.sub(r"[^a-zA-Z0-9_-]", "_", f"rpc_{name}")
            summary = str(method.get("summary", name))
            long_running = bool(method.get("long_running"))
            description = (
                f"[{plugin}] {summary}"
                + (" (long-running; the call blocks until it finishes)" if long_running else "")
                + f" — backend RPC method {name}."
            )

            @registry.add(
                name=tool_name,
                description=description,
                parameters={
                    "type": "object",
                    "properties": {
                        "arguments": {
                            "type": "object",
                            "description": "Keyword arguments for the backend method, as declared by the plugin.",
                        }
                    },
                },
                safety=SAFETY_DANGEROUS,
            )
            def _rpc_tool(context, arguments=None, _method=name):  # default binds per method
                return _invoke(context, arguments, _method)

            # The allowlist, applied per method: served tools are moved into
            # the write tier so the MCP surface picks them up.
            if serve_all or name in served:
                registry.tools[tool_name].safety = SAFETY_WRITE
            count += 1
    return count


def main() -> None:
    """Run the server on stdio (the entrypoint an MCP client launches).

    fd 1 carries the protocol and nothing else: chisurf's import-time
    warnings are moved to stderr before the first import, so a chatty
    startup can never corrupt the JSON-RPC stream.
    """
    import os

    protocol_out = os.fdopen(os.dup(1), "wb")
    sys.stdout = sys.stderr  # chatty imports must not reach the client
    McpServer(output=protocol_out).serve()


if __name__ == "__main__":  # pragma: no cover - manual launch
    main()
