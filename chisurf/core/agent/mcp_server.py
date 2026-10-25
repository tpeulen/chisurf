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
