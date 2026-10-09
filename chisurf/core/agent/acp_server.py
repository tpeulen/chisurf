"""Agent Client Protocol (ACP) server for the ChiSurf agent.

This module implements the server side of the Agent Client Protocol (JSON-RPC 2.0
over stdio or custom streams), allowing code editors (such as ChiSurf's Code Editor,
Zed, JetBrains, or VS Code) to interact with ChiSurf's AI agent runtime.

See: https://agentclientprotocol.com
"""

from __future__ import annotations

import json
import logging
import pathlib
import sys
import threading
import uuid
from collections.abc import Callable
from typing import Any, BinaryIO

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.llm import LLMClient, LLMSettings
from chisurf.core.agent.runtime import AgentConfig, AgentSession
from chisurf.core.agent.spec import SAFETY_DANGEROUS, SAFETY_READ, SAFETY_WRITE
from chisurf.core.agent.tools import build_default_registry

_LOG = logging.getLogger("chisurf.agent.acp_server")

PROTOCOL_VERSION = 1

MODE_SAFETY_MAP = {
    "chat_only": SAFETY_READ,
    "chisurf_tools": SAFETY_WRITE,
    "full_control": SAFETY_DANGEROUS,
}

AVAILABLE_MODES = [
    {
        "id": "chat_only",
        "name": "Chat only",
        "description": "Answers and writes code; touches no files or fits.",
    },
    {
        "id": "chisurf_tools",
        "name": "ChiSurf tools",
        "description": "Loads data, creates and runs fits, edits parameters.",
    },
    {
        "id": "full_control",
        "name": "Full control",
        "description": "Runs Python code and writes files, asking first.",
    },
]


class AcpServer:
    """Agent Client Protocol (ACP) JSON-RPC 2.0 server.

    Parameters
    ----------
    provider : str, optional
        ChiSurf AI provider key.
    model : str, optional
        Model identifier override.
    safety : str, default SAFETY_WRITE
        Default tool safety tier.
    cwd : str or pathlib.Path, optional
        Default working directory.
    in_stream : BinaryIO, optional
        Standard input stream (defaults to sys.stdin.buffer).
    out_stream : BinaryIO, optional
        Standard output stream (defaults to sys.stdout.buffer).
    """

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        safety: str = SAFETY_WRITE,
        cwd: str | pathlib.Path | None = None,
        in_stream: BinaryIO | None = None,
        out_stream: BinaryIO | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.default_safety = safety
        self.default_cwd = pathlib.Path(cwd or pathlib.Path.cwd()).resolve()
        self.in_stream = in_stream or sys.stdin.buffer
        self.out_stream = out_stream or sys.stdout.buffer

        self.sessions: dict[str, AgentSession] = {}
        self.session_modes: dict[str, str] = {}
        self.session_cwds: dict[str, str] = {}
        self.client_capabilities: dict[str, Any] = {}

        self._running = False
        self._write_lock = threading.Lock()
        self._next_request_id = 1
        self._pending_client_requests: dict[int, threading.Event] = {}
        self._pending_client_results: dict[int, Any] = {}

    # ── Protocol Framing & IO ──────────────────────────────────────────

    def send_response(self, request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC 2.0 response."""
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result if result is not None else {}
        self._send_raw(payload)

    def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC 2.0 notification."""
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._send_raw(payload)

    def send_request(self, method: str, params: dict[str, Any] | None = None, timeout: float = 30.0) -> Any:
        """Send a JSON-RPC 2.0 request to the client and wait for response."""
        with self._write_lock:
            req_id = self._next_request_id
            self._next_request_id += 1
            event = threading.Event()
            self._pending_client_requests[req_id] = event

        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
        self._send_raw(payload)

        if not event.wait(timeout=timeout):
            with self._write_lock:
                self._pending_client_requests.pop(req_id, None)
                self._pending_client_results.pop(req_id, None)
            raise TimeoutError(f"Client request {method} (id={req_id}) timed out after {timeout}s")

        with self._write_lock:
            self._pending_client_requests.pop(req_id, None)
            result, err = self._pending_client_results.pop(req_id, (None, None))

        if err is not None:
            raise RuntimeError(f"Client error on {method}: {err}")
        return result

    def _send_raw(self, payload: dict[str, Any]) -> None:
        """Write a JSON-RPC payload as newline-delimited JSON."""
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        with self._write_lock:
            try:
                self.out_stream.write(line)
                self.out_stream.flush()
            except (BrokenPipeError, OSError):
                self._running = False

    # ── Message Dispatch ───────────────────────────────────────────────

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Dispatch a single parsed JSON-RPC message."""
        if not isinstance(message, dict):
            return None

        # Check if this is a response from the client to a request we sent
        req_id = message.get("id")
        if req_id is not None and "method" not in message:
            with self._write_lock:
                event = self._pending_client_requests.get(req_id)
                if event is not None:
                    res = message.get("result")
                    err = message.get("error")
                    self._pending_client_results[req_id] = (res, err)
                    event.set()
            return None

        method = message.get("method")
        params = message.get("params", {}) or {}

        # Handle requests or notifications
        if method == "initialize":
            res = self.handle_initialize(params)
            if req_id is not None:
                self.send_response(req_id, res)
        elif method == "session/new":
            res = self.handle_new_session(params)
            if req_id is not None:
                self.send_response(req_id, res)
        elif method == "session/prompt":
            # Handled in worker thread so prompt doesn't block incoming cancel requests
            if req_id is not None:
                threading.Thread(
                    target=self._run_prompt_worker,
                    args=(req_id, params),
                    daemon=True,
                ).start()
        elif method == "session/cancel":
            self.handle_cancel(params)
            if req_id is not None:
                self.send_response(req_id, {})
        elif method == "session/set_mode":
            res = self.handle_set_mode(params)
            if req_id is not None:
                self.send_response(req_id, res)
        elif method == "session/close":
            res = self.handle_close_session(params)
            if req_id is not None:
                self.send_response(req_id, res)
        elif method == "ping":
            if req_id is not None:
                self.send_response(req_id, {})
        else:
            if req_id is not None:
                self.send_response(
                    req_id,
                    error={"code": -32601, "message": f"Method not found: {method}"},
                )
        return None

    # ── ACP Method Handlers ────────────────────────────────────────────

    def handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``initialize`` request."""
        self.client_capabilities = params.get("clientCapabilities", {})
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "agentInfo": {
                "name": "ChiSurf ACP Agent",
                "version": "1.0.0",
            },
            "agentCapabilities": {
                "loadSession": False,
                "promptCapabilities": {
                    "image": False,
                    "audio": False,
                    "embeddedContext": False,
                },
                "sessionCapabilities": {
                    "close": True,
                },
            },
        }

    def _create_agent_session(self, session_id: str, cwd: str, mode_id: str) -> AgentSession:
        """Create a new AgentSession for *session_id* with event wiring."""
        safety = MODE_SAFETY_MAP.get(mode_id, SAFETY_WRITE)

        def event_callback(name: str, payload: dict[str, Any]) -> None:
            self._on_agent_event(session_id, name, payload)

        def confirm_callback(tool: str, arguments: dict[str, Any]) -> bool:
            return self._ask_client_permission(session_id, tool, arguments)

        context = AgentContext(
            working_directory=cwd,
            allow_code_execution=safety == SAFETY_DANGEROUS,
            confirm=confirm_callback if safety == SAFETY_DANGEROUS else None,
            event_callback=event_callback,
        )

        try:
            settings = LLMSettings.from_provider(self.provider)
            if self.model:
                settings.model = self.model
            client = LLMClient(settings)
        except Exception as e:
            _LOG.warning("Could not initialize real LLMClient: %s, using fallback", e)
            client = LLMClient(LLMSettings(base_url="http://localhost:11434/v1", model="mock"))

        config = AgentConfig(max_safety=safety)
        session = AgentSession(
            llm=client,
            context=context,
            registry=build_default_registry(),
            config=config,
            extra_instructions=(
                "You are running as an Agent Client Protocol (ACP) agent inside ChiSurf. "
                "Help the user analyze fluorescence data, run fits, and edit code."
            ),
        )
        return session

    def handle_new_session(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``session/new`` request."""
        session_id = f"session_{uuid.uuid4().hex[:12]}"
        cwd = str(params.get("cwd") or self.default_cwd)
        initial_mode = "chisurf_tools"

        self.session_cwds[session_id] = cwd
        self.session_modes[session_id] = initial_mode
        self.sessions[session_id] = self._create_agent_session(session_id, cwd, initial_mode)

        return {
            "sessionId": session_id,
            "modes": {
                "currentModeId": initial_mode,
                "availableModes": AVAILABLE_MODES,
            },
        }

    def handle_set_mode(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``session/set_mode`` request."""
        session_id = params.get("sessionId")
        mode_id = params.get("modeId", "chisurf_tools")
        if not session_id or session_id not in self.sessions:
            return {}

        self.session_modes[session_id] = mode_id
        cwd = self.session_cwds.get(session_id, str(self.default_cwd))
        # Recreate session with new safety tier
        self.sessions[session_id] = self._create_agent_session(session_id, cwd, mode_id)

        self.send_notification(
            "session/update",
            {
                "sessionId": session_id,
                "update": {
                    "sessionUpdate": "current_mode_update",
                    "currentModeId": mode_id,
                },
            },
        )
        return {}

    def handle_close_session(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``session/close`` request."""
        session_id = params.get("sessionId")
        if session_id:
            session = self.sessions.pop(session_id, None)
            if session:
                session.cancel()
            self.session_modes.pop(session_id, None)
            self.session_cwds.pop(session_id, None)
        return {}

    def handle_cancel(self, params: dict[str, Any]) -> None:
        """Handle ``session/cancel`` notification."""
        session_id = params.get("sessionId")
        if session_id:
            session = self.sessions.get(session_id)
            if session:
                session.cancel()

    def _run_prompt_worker(self, request_id: Any, params: dict[str, Any]) -> None:
        """Execute ``session/prompt`` off the transport read loop."""
        session_id = params.get("sessionId")
        prompt_blocks = params.get("prompt", [])
        if not session_id or session_id not in self.sessions:
            self.send_response(
                request_id,
                error={"code": -32602, "message": f"Invalid session ID: {session_id}"},
            )
            return

        session = self.sessions[session_id]

        # Extract text from prompt content blocks
        text_parts = []
        if isinstance(prompt_blocks, list):
            for block in prompt_blocks:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
        elif isinstance(prompt_blocks, str):
            text_parts.append(prompt_blocks)

        prompt_text = "\n".join(text_parts).strip()
        if not prompt_text:
            self.send_response(request_id, {"stopReason": "end_turn"})
            return

        try:
            result = session.ask(prompt_text)
            stop_reason = "cancelled" if session._cancelled else "end_turn"
            if result.stop_reason == "cancelled":
                stop_reason = "cancelled"
            elif result.error:
                stop_reason = "error"

            # Check if output contains WRITE_FILE directive and client supports fs.writeTextFile
            if result.text and self.client_capabilities.get("fs", {}).get("writeTextFile"):
                self._check_and_push_file_writes(session_id, result.text)

            self.send_response(request_id, {"stopReason": stop_reason})
        except Exception as e:
            _LOG.exception("Error during ACP prompt turn")
            self.send_response(
                request_id,
                error={"code": -32603, "message": f"Prompt execution error: {e}"},
            )

    def _on_agent_event(self, session_id: str, name: str, payload: dict[str, Any]) -> None:
        """Translate runtime events into ACP ``session/update`` notifications."""
        call_id = f"call_{uuid.uuid4().hex[:8]}"

        if name == "tool.started":
            self.send_notification(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "tool_call",
                        "toolCallId": call_id,
                        "name": payload.get("tool", "unknown"),
                        "status": "in_progress",
                        "rawInput": payload.get("arguments", {}),
                    },
                },
            )
        elif name == "tool.completed":
            self.send_notification(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": call_id,
                        "status": "completed" if payload.get("ok") else "failed",
                        "rawOutput": payload.get("result", {}),
                    },
                },
            )
        elif name == "tool.failed":
            self.send_notification(
                "session/update",
                {
                    "sessionId": session_id,
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCallId": call_id,
                        "status": "failed",
                        "rawOutput": {"error": payload.get("error")},
                    },
                },
            )
        elif name == "message.completed":
            content = payload.get("content", "")
            if content:
                self.send_notification(
                    "session/update",
                    {
                        "sessionId": session_id,
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "messageId": f"msg_{uuid.uuid4().hex[:8]}",
                            "content": {"type": "text", "text": content},
                        },
                    },
                )

    def _ask_client_permission(self, session_id: str, tool: str, arguments: dict[str, Any]) -> bool:
        """Ask the client for permission to run a dangerous tool via ACP."""
        try:
            res = self.send_request(
                "session/request_permission",
                {
                    "sessionId": session_id,
                    "toolCall": {
                        "toolCallId": f"perm_{uuid.uuid4().hex[:8]}",
                        "name": tool,
                        "rawInput": arguments,
                    },
                    "options": [
                        {"id": "allow", "title": "Allow"},
                        {"id": "deny", "title": "Deny"},
                    ],
                },
                timeout=120.0,
            )
            return res.get("outcome") == "allow"
        except Exception as e:
            _LOG.warning("Permission request failed: %s", e)
            return False

    def _check_and_push_file_writes(self, session_id: str, text: str) -> None:
        """If model proposed file writes via WRITE_FILE, apply them to client via fs/write_text_file."""
        import re

        pattern = r"```python\s*#\s*WRITE_FILE:\s*([^\n]+)\n(.*?)```"
        matches = re.findall(pattern, text, flags=re.DOTALL)
        for target, code in matches:
            target = target.strip()
            if target and target.lower() != "none":
                try:
                    self.send_request(
                        "fs/write_text_file",
                        {
                            "sessionId": session_id,
                            "path": target,
                            "content": code,
                        },
                        timeout=10.0,
                    )
                except Exception as e:
                    _LOG.warning("Failed to push file write to client: %s", e)

    # ── Main Event Loop ────────────────────────────────────────────────

    def run(self) -> None:
        """Run the JSON-RPC message processing loop on stdio."""
        self._running = True
        buffer = bytearray()

        while self._running:
            try:
                if hasattr(self.in_stream, "read1"):
                    chunk = self.in_stream.read1(4096)
                else:
                    chunk = self.in_stream.readline()
                if not chunk:
                    break
                buffer.extend(chunk)

                # Process all complete messages in buffer
                while True:
                    # Check for Content-Length framing (LSP / JSON-RPC header)
                    header_end = buffer.find(b"\r\n\r\n")
                    if header_end >= 0 and buffer.startswith(b"Content-Length"):
                        header = bytes(buffer[:header_end]).decode("ascii", errors="replace")
                        length = 0
                        for line in header.split("\r\n"):
                            k, _, v = line.partition(":")
                            if k.strip().lower() == "content-length":
                                try:
                                    length = int(v.strip())
                                except ValueError:
                                    pass
                                break
                        if length > 0 and len(buffer) >= header_end + 4 + length:
                            start = header_end + 4
                            msg_bytes = bytes(buffer[start : start + length])
                            del buffer[: start + length]
                            try:
                                msg = json.loads(msg_bytes.decode("utf-8"))
                                self.handle_message(msg)
                            except Exception as e:
                                _LOG.warning("Failed to parse JSON-RPC message: %s", e)
                            continue
                        break

                    # Check for newline-delimited JSON (standard ACP over stdio)
                    nl_pos = buffer.find(b"\n")
                    if nl_pos >= 0:
                        line = bytes(buffer[:nl_pos]).strip()
                        del buffer[: nl_pos + 1]
                        if not line:
                            continue
                        try:
                            msg = json.loads(line.decode("utf-8"))
                            self.handle_message(msg)
                        except Exception as e:
                            _LOG.warning("Failed to parse newline JSON: %s", e)
                        continue
                    break

            except (KeyboardInterrupt, BrokenPipeError):
                break
            except Exception as e:
                _LOG.exception("Exception in ACP server read loop: %s", e)
                break

        self._running = False


def run_acp_server(
    provider: str | None = None,
    model: str | None = None,
    cwd: str | pathlib.Path | None = None,
    safety: str = SAFETY_WRITE,
    verbose: bool = False,
    no_qt: bool = False,
    presenter: Callable | None = None,
) -> int:
    """Entry point to launch the ACP server over stdio."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    # A server has no GUI lifetime to own. An embedding host may attach its
    # existing scheduler through the pure presentation seam.
    if presenter is not None:
        from chisurf.core.runtime import presentation
        presentation.set_presenter(presenter)

    if provider is None or provider == "acp":
        from chisurf.core.settings import ai_settings
        transport = ai_settings.get_api_settings("acp")
        delegate = transport.get("acp_backend_provider")
        provider = delegate or ai_settings.get_provider()
        if provider == "acp":
            provider = ai_settings.DEFAULT_PROVIDER
    server = AcpServer(provider=provider, model=model, safety=safety, cwd=cwd)
    server.run()
    return 0


def main() -> int:
    """Parse command line flags and launch ACP server."""
    import argparse

    parser = argparse.ArgumentParser(description="ChiSurf ACP Server")
    parser.add_argument("--provider", default=None, help="AI provider key")
    parser.add_argument("--model", default=None, help="Model override")
    parser.add_argument("--directory", "-C", default=None, help="Working directory")
    parser.add_argument("--safety", default=SAFETY_WRITE, help="Default safety tier")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--no-qt", action="store_true", help="Compatibility flag: the ACP server is always headless")
    args, _ = parser.parse_known_args()

    return run_acp_server(
        provider=args.provider,
        model=args.model,
        cwd=args.directory,
        safety=args.safety,
        verbose=args.verbose,
        no_qt=args.no_qt,
    )


if __name__ == "__main__":
    sys.exit(main())
