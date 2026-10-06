"""Agent Client Protocol (ACP) client for the ChiSurf Code Editor.

This module provides a pure-Python JSON-RPC 2.0 client over stdio subprocesses or
in-memory transports that connects ChiSurf's Code Editor and AI Assistant to any
ACP-compliant agent server with zero Qt dependencies.

See: https://agentclientprotocol.com
"""

from __future__ import annotations

import json
import logging
import pathlib
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import Any

_LOG = logging.getLogger("chisurf.code_editor.acp_client")


class Signal:
    """A pure-Python signal matching Qt Signal semantics (.connect(), .disconnect(), .emit()).

    Allows components to observe ACP events without requiring PyQt5 or PySide.
    """

    def __init__(self, *arg_types: type) -> None:
        self.arg_types = arg_types
        self._slots: list[Callable[..., Any]] = []
        self._lock = threading.Lock()

    def connect(self, slot: Callable[..., Any]) -> None:
        with self._lock:
            if slot not in self._slots:
                self._slots.append(slot)

    def disconnect(self, slot: Callable[..., Any]) -> None:
        with self._lock:
            if slot in self._slots:
                self._slots.remove(slot)

    def emit(self, *args: Any) -> None:
        with self._lock:
            slots = list(self._slots)
        for slot in slots:
            try:
                slot(*args)
            except Exception as e:
                _LOG.error("Error in ACP signal handler %s: %s", slot, e)


class AcpClient:
    """Client for the Agent Client Protocol (ACP) over stdio or in-memory transport.

    Pure-Python implementation with zero Qt dependencies.
    """

    def __init__(
        self,
        root_path: str | pathlib.Path | None = None,
        command: list[str] | None = None,
        parent: Any = None,
        read_file_handler: Callable[[str, int | None, int | None], str] | None = None,
        write_file_handler: Callable[[str, str], None] | None = None,
        permission_handler: Callable[[dict[str, Any], list[dict[str, Any]]], str] | None = None,
        transport: Any | None = None,
    ) -> None:
        self.root_path = pathlib.Path(root_path or pathlib.Path.cwd()).resolve()
        self.command = command or self._default_command()
        self.read_file_handler = read_file_handler
        self.write_file_handler = write_file_handler
        self.permission_handler = permission_handler
        self.transport = transport

        # Signals
        self.status_changed = Signal(str)
        self.session_created = Signal(str)
        self.message_chunk = Signal(str, str)
        self.thought_chunk = Signal(str, str)
        self.tool_call = Signal(str, dict)
        self.prompt_finished = Signal(str, str)
        self.error_received = Signal(str)
        self.mode_changed = Signal(str, str)

        self.process: subprocess.Popen[bytes] | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._running = False
        self._buffer = bytearray()
        self._next_id = 1
        self._callbacks: dict[int, Callable[[Any], None]] = {}
        self._error_callbacks: dict[int, Callable[[Any], None]] = {}
        self._lock = threading.Lock()

        self._ready = False
        self.session_id: str | None = None
        self.current_mode_id: str | None = None
        self.available_modes: list[dict[str, Any]] = []
        self.agent_info: dict[str, Any] = {}
        self.agent_capabilities: dict[str, Any] = {}

    @property
    def is_ready(self) -> bool:
        """Return whether the ACP client has initialized successfully."""
        return self._ready

    @property
    def is_running(self) -> bool:
        """Return whether the ACP process or transport is active."""
        if self.transport is not None:
            return self._ready
        return self.process is not None and self.process.poll() is None

    @staticmethod
    def _default_command() -> list[str]:
        """Return default command for launching ChiSurf's in-tree ACP server."""
        return [sys.executable, "-m", "chisurf.core.agent.acp_server"]

    def set_fs_handlers(
        self,
        read_file_handler: Callable[[str, int | None, int | None], str] | None = None,
        write_file_handler: Callable[[str, str], None] | None = None,
        permission_handler: Callable[[dict[str, Any], list[dict[str, Any]]], str] | None = None,
    ) -> None:
        """Update filesystem and permission handlers."""
        if read_file_handler is not None:
            self.read_file_handler = read_file_handler
        if write_file_handler is not None:
            self.write_file_handler = write_file_handler
        if permission_handler is not None:
            self.permission_handler = permission_handler

    # ── Process Lifecycle ──────────────────────────────────────────────

    def start(self) -> bool:
        """Start the ACP agent process and perform initialization."""
        if self.transport is not None:
            self._ready = True
            self.status_changed.emit("ACP ready (mock)")
            return True

        if self.process is not None and self.process.poll() is None:
            return True

        if not self.command:
            self.status_changed.emit("ACP unavailable")
            return False

        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.root_path),
                bufsize=0,
            )
            self._running = True
            self._stdout_thread = threading.Thread(target=self._read_stdout_worker, daemon=True)
            self._stderr_thread = threading.Thread(target=self._read_stderr_worker, daemon=True)
            self._stdout_thread.start()
            self._stderr_thread.start()
        except Exception as e:
            _LOG.error("Failed to spawn ACP process: %s", e)
            self.status_changed.emit("ACP unavailable")
            self.process = None
            return False

        self.status_changed.emit("ACP starting")
        self.initialize()
        return True

    def stop(self) -> None:
        """Shutdown the ACP process and reset connection state."""
        self._running = False
        proc = self.process
        self.process = None

        if proc is not None:
            try:
                if self.session_id:
                    self.close_session(self.session_id)
            except Exception:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        self._ready = False
        self.session_id = None
        self.status_changed.emit("ACP stopped")

    # ── JSON-RPC 2.0 Messaging ─────────────────────────────────────────

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        callback: Callable[[Any], None] | None = None,
        error_callback: Callable[[Any], None] | None = None,
    ) -> int:
        """Send a JSON-RPC request and return its id."""
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            if callback is not None:
                self._callbacks[request_id] = callback
            if error_callback is not None:
                self._error_callbacks[request_id] = error_callback

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        self._send(payload)
        return request_id

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification."""
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def respond(
        self, request_id: Any, result: Any = None, error: dict[str, Any] | None = None
    ) -> None:
        """Send a JSON-RPC response to an incoming agent request."""
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
        if error is not None:
            payload["error"] = error
        else:
            payload["result"] = result if result is not None else {}
        self._send(payload)

    def _send(self, payload: dict[str, Any]) -> None:
        """Serialize and send payload over the active transport."""
        if self.transport is not None:
            self.transport(payload)
            return

        if self.process is None or self.process.stdin is None:
            return
        line = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            self.process.stdin.write(line)
            self.process.stdin.flush()
        except Exception as e:
            _LOG.error("Failed to write to ACP stdin: %s", e)

    # ── Protocol Operations ────────────────────────────────────────────

    def initialize(self, callback: Callable[[Any], None] | None = None) -> int:
        """Send ``initialize`` request to negotiate capabilities."""
        params = {
            "protocolVersion": 1,
            "clientInfo": {
                "name": "ChiSurf Code Editor",
                "version": "1.0.0",
            },
            "clientCapabilities": {
                "fs": {
                    "readTextFile": True,
                    "writeTextFile": True,
                },
                "terminal": False,
            },
        }

        def on_init(result: Any) -> None:
            self._ready = True
            if isinstance(result, dict):
                self.agent_info = result.get("agentInfo", {})
                self.agent_capabilities = result.get("agentCapabilities", {})
            self.status_changed.emit("ACP ready")
            if callback:
                callback(result)

        return self.request("initialize", params, on_init, self._on_generic_error)

    def new_session(
        self,
        cwd: str | pathlib.Path | None = None,
        callback: Callable[[str], None] | None = None,
    ) -> int:
        """Create a new session via ``session/new``."""
        params = {"cwd": str(pathlib.Path(cwd or self.root_path).resolve())}

        def on_session(result: Any) -> None:
            if isinstance(result, dict):
                session_id = result.get("sessionId")
                if session_id:
                    self.session_id = session_id
                    modes = result.get("modes", {})
                    self.current_mode_id = modes.get("currentModeId")
                    self.available_modes = modes.get("availableModes", [])
                    self.session_created.emit(session_id)
                    if callback:
                        callback(session_id)

        return self.request("session/new", params, on_session, self._on_generic_error)

    def prompt(
        self,
        text: str,
        session_id: str | None = None,
        callback: Callable[[str], None] | None = None,
    ) -> int:
        """Submit a prompt turn via ``session/prompt``."""
        target_session = session_id or self.session_id
        if not target_session:
            raise ValueError("Cannot prompt without an active ACP session")

        params = {
            "sessionId": target_session,
            "prompt": [{"type": "text", "text": text}],
        }

        def on_prompt_done(result: Any) -> None:
            stop_reason = "end_turn"
            if isinstance(result, dict):
                stop_reason = result.get("stopReason", "end_turn")
            self.prompt_finished.emit(target_session, stop_reason)
            if callback:
                callback(stop_reason)

        return self.request("session/prompt", params, on_prompt_done, self._on_generic_error)

    def cancel(self, session_id: str | None = None) -> None:
        """Cancel an in-progress prompt turn via ``session/cancel``."""
        target_session = session_id or self.session_id
        if target_session:
            self.notify("session/cancel", {"sessionId": target_session})

    def set_mode(
        self,
        mode_id: str,
        session_id: str | None = None,
        callback: Callable[[], None] | None = None,
    ) -> int:
        """Switch operating mode via ``session/set_mode``."""
        target_session = session_id or self.session_id
        if not target_session:
            raise ValueError("Cannot set mode without an active ACP session")

        params = {"sessionId": target_session, "modeId": mode_id}

        def on_mode_done(_result: Any) -> None:
            self.current_mode_id = mode_id
            self.mode_changed.emit(target_session, mode_id)
            if callback:
                callback()

        return self.request("session/set_mode", params, on_mode_done, self._on_generic_error)

    def close_session(
        self,
        session_id: str | None = None,
        callback: Callable[[], None] | None = None,
    ) -> int:
        """Close an active session via ``session/close``."""
        target_session = session_id or self.session_id
        if not target_session:
            return 0

        params = {"sessionId": target_session}

        def on_closed(_result: Any) -> None:
            if self.session_id == target_session:
                self.session_id = None
            if callback:
                callback()

        return self.request("session/close", params, on_closed, self._on_generic_error)

    # ── Incoming Message Processing ────────────────────────────────────

    def _read_stdout_worker(self) -> None:
        """Background thread worker to read from the agent's stdout."""
        proc = self.process
        if not proc or not proc.stdout:
            return

        while self._running:
            chunk = (
                proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096)
            )
            if not chunk:
                break
            self._feed_bytes(chunk)

        self._ready = False
        self.status_changed.emit("ACP stopped")

    def _read_stderr_worker(self) -> None:
        """Background thread worker to read from the agent's stderr."""
        proc = self.process
        if not proc or not proc.stderr:
            return

        while self._running:
            line = proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if text:
                _LOG.info("ACP stderr: %s", text)
                self.status_changed.emit(f"ACP: {text.splitlines()[-1]}")

    def _feed_bytes(self, chunk: bytes) -> None:
        """Accumulate bytes and parse complete JSON-RPC messages."""
        with self._lock:
            self._buffer.extend(chunk)

        while True:
            # Check for Content-Length framing
            header_end = self._buffer.find(b"\r\n\r\n")
            if header_end >= 0 and self._buffer.startswith(b"Content-Length"):
                header = bytes(self._buffer[:header_end]).decode("ascii", errors="replace")
                length = 0
                for line in header.split("\r\n"):
                    k, _, v = line.partition(":")
                    if k.strip().lower() == "content-length":
                        try:
                            length = int(v.strip())
                        except ValueError:
                            pass
                        break
                if length > 0 and len(self._buffer) >= header_end + 4 + length:
                    start = header_end + 4
                    msg_bytes = bytes(self._buffer[start : start + length])
                    del self._buffer[: start + length]
                    try:
                        self.handle_incoming_message(json.loads(msg_bytes.decode("utf-8")))
                    except Exception as e:
                        _LOG.warning("Failed to decode ACP message: %s", e)
                    continue
                return

            # Check for newline-delimited JSON
            nl_pos = self._buffer.find(b"\n")
            if nl_pos >= 0:
                line = bytes(self._buffer[:nl_pos]).strip()
                del self._buffer[: nl_pos + 1]
                if not line:
                    continue
                try:
                    self.handle_incoming_message(json.loads(line.decode("utf-8")))
                except Exception as e:
                    _LOG.warning("Failed to decode ACP line: %s", e)
                continue
            return

    def handle_incoming_message(self, message: dict[str, Any]) -> None:
        """Process a received JSON-RPC 2.0 message."""
        if not isinstance(message, dict):
            return

        # Case 1: Response to a request we sent
        req_id = message.get("id")
        if req_id is not None and "method" not in message:
            try:
                int_id = int(req_id)
            except ValueError:
                int_id = req_id

            with self._lock:
                err_cb = self._error_callbacks.pop(int_id, None)
                cb = self._callbacks.pop(int_id, None)

            if "error" in message:
                err_data = message.get("error", {})
                err_msg = (
                    err_data.get("message", str(err_data))
                    if isinstance(err_data, dict)
                    else str(err_data)
                )
                if err_cb:
                    err_cb(err_data)
                else:
                    self.error_received.emit(err_msg)
                return

            if cb is not None:
                cb(message.get("result"))
            return

        # Case 2: Notification or request from the agent
        method = message.get("method")
        params = message.get("params", {}) or {}

        if method == "session/update":
            self._handle_session_update(params)
        elif method == "fs/read_text_file":
            self._handle_fs_read(req_id, params)
        elif method == "fs/write_text_file":
            self._handle_fs_write(req_id, params)
        elif method == "session/request_permission":
            self._handle_request_permission(req_id, params)
        else:
            if req_id is not None:
                self.respond(
                    req_id, error={"code": -32601, "message": f"Method not handled: {method}"}
                )

    def _handle_session_update(self, params: dict[str, Any]) -> None:
        """Handle ``session/update`` notifications."""
        session_id = params.get("sessionId", self.session_id or "")
        update = params.get("update", {})
        if not isinstance(update, dict):
            return

        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            content = update.get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            if text:
                self.message_chunk.emit(session_id, text)
        elif kind == "agent_thought_chunk":
            content = update.get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else str(content)
            if text:
                self.thought_chunk.emit(session_id, text)
        elif kind in ("tool_call", "tool_call_update"):
            self.tool_call.emit(session_id, update)
        elif kind == "current_mode_update":
            mode_id = update.get("currentModeId") or update.get("modeId")
            if mode_id:
                self.current_mode_id = mode_id
                self.mode_changed.emit(session_id, mode_id)

    def _handle_fs_read(self, request_id: Any, params: dict[str, Any]) -> None:
        """Handle ``fs/read_text_file`` request from the agent."""
        path = params.get("path", "")
        line = params.get("line")
        limit = params.get("limit")

        try:
            if self.read_file_handler:
                content = self.read_file_handler(path, line, limit)
            else:
                target = pathlib.Path(path)
                if not target.is_absolute():
                    target = self.root_path / target
                content = target.read_text(encoding="utf-8")
                if line is not None or limit is not None:
                    lines = content.splitlines()
                    start = max(0, int(line or 0))
                    count = int(limit) if limit is not None else len(lines)
                    content = "\n".join(lines[start : start + count])

            if request_id is not None:
                self.respond(request_id, result={"content": content})
        except Exception as e:
            if request_id is not None:
                self.respond(request_id, error={"code": -32000, "message": str(e)})

    def _handle_fs_write(self, request_id: Any, params: dict[str, Any]) -> None:
        """Handle ``fs/write_text_file`` request from the agent."""
        path = params.get("path", "")
        content = params.get("content", "")

        try:
            if self.write_file_handler:
                self.write_file_handler(path, content)
            else:
                target = pathlib.Path(path)
                if not target.is_absolute():
                    target = self.root_path / target
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            if request_id is not None:
                self.respond(request_id, result={})
        except Exception as e:
            if request_id is not None:
                self.respond(request_id, error={"code": -32000, "message": str(e)})

    def _handle_request_permission(self, request_id: Any, params: dict[str, Any]) -> None:
        """Handle ``session/request_permission`` request from the agent."""
        tool_call_data = params.get("toolCall", {})
        options = params.get("options", [])

        try:
            if self.permission_handler:
                outcome = self.permission_handler(tool_call_data, options)
            else:
                outcome = "allow"

            if request_id is not None:
                self.respond(request_id, result={"outcome": outcome})
        except Exception as e:
            if request_id is not None:
                self.respond(request_id, error={"code": -32000, "message": str(e)})

    def _on_generic_error(self, err: Any) -> None:
        """Default error handler for JSON-RPC errors."""
        msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        self.error_received.emit(msg)


__all__ = ["Signal", "AcpClient"]
