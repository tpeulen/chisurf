"""Optional Python LSP over stdio, with no Qt event-loop dependency."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable

from chisurf.plugins.core.code_editor.acp_client import Signal


class NativeLspClient:
    def __init__(self, root_path, command=None) -> None:
        self.root_path = pathlib.Path(root_path).resolve()
        self.command = command
        self.process = None
        self.is_ready = False
        self.status_changed = Signal(str)
        self.diagnostics_received = Signal(str, list)
        self._callbacks: dict[int, Callable] = {}
        self._next_id = 1
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._opened: dict[str, tuple[str, int]] = {}
        self._stopping = False

    def start(self) -> bool:
        if self.process is not None:
            return True
        command = self.command
        if command is None:
            executable = shutil.which("pylsp")
            if executable:
                command = [executable]
            elif importlib.util.find_spec("pylsp") is not None:
                command = [sys.executable, "-m", "pylsp"]
            else:
                self.status_changed.emit("Python LSP unavailable: optional python-lsp-server is not installed")
                return False
        self._stopping = False
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=str(self.root_path))
        except OSError as error:
            self.status_changed.emit(f"LSP unavailable: {error}")
            return False
        self.status_changed.emit("LSP starting")
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self.request("initialize", {"processId": None, "rootUri": self.root_path.as_uri(),
            "capabilities": {"textDocument": {"completion": {"completionItem": {"snippetSupport": False}},
                "publishDiagnostics": {}, "hover": {"contentFormat": ["markdown", "plaintext"]}}}}, self._initialized)
        return True

    def _initialized(self, result) -> None:
        if self._stopping or result is None:
            return
        self.is_ready = True
        self.notify("initialized", {})
        self.status_changed.emit("LSP ready")

    def _send(self, payload) -> None:
        process = self.process
        if process is None or process.stdin is None:
            return
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        data = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        with self._lock:
            try:
                process.stdin.write(data)
                process.stdin.flush()
            except (OSError, ValueError) as error:
                if not self._stopping:
                    self.status_changed.emit(f"LSP write failed: {error}")

    def request(self, method, params, callback=None) -> int:
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
            if callback is not None:
                self._callbacks[request_id] = callback
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        return request_id

    def notify(self, method, params) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def feed_data(self, data: bytes) -> None:
        """Consume fragmented or batched Content-Length frames."""
        self._buffer.extend(data)
        while True:
            boundary = self._buffer.find(b"\r\n\r\n")
            if boundary < 0:
                if len(self._buffer) > 8192:
                    raise ValueError("LSP header too large")
                return
            headers = bytes(self._buffer[:boundary]).decode("ascii")
            length = None
            for header in headers.split("\r\n"):
                key, _, value = header.partition(":")
                if key.lower() == "content-length":
                    length = int(value.strip())
            if length is None or length < 0 or length > 16 * 1024 * 1024:
                raise ValueError("Invalid LSP Content-Length")
            start = boundary + 4
            if len(self._buffer) < start + length:
                return
            body = bytes(self._buffer[start:start + length])
            del self._buffer[:start + length]
            self._handle_message(json.loads(body.decode("utf-8")))

    def _handle_message(self, message) -> None:
        if "id" in message and "method" in message:
            method = message["method"]
            result = [{} for _ in message.get("params", {}).get("items", [])] if method == "workspace/configuration" else None
            if method == "workspace/applyEdit":
                result = {"applied": False, "failureReason": "Unsolicited workspace edits are not supported"}
            self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})
        elif "id" in message:
            with self._lock:
                callback = self._callbacks.pop(message["id"], None)
            if "error" in message:
                self.status_changed.emit(f"LSP error: {message['error'].get('message', message['error'])}")
            if callback is not None:
                callback(message.get("result"))
        elif message.get("method") == "textDocument/publishDiagnostics":
            params = message.get("params", {})
            self.diagnostics_received.emit(params.get("uri", ""), params.get("diagnostics", []))

    def _read_stdout(self) -> None:
        process = self.process
        try:
            while process and process.stdout and not self._stopping:
                chunk = process.stdout.read1(8192)
                if not chunk:
                    break
                self.feed_data(chunk)
        except Exception as error:
            if not self._stopping:
                self.status_changed.emit(f"LSP protocol error: {error}")
        finally:
            self.is_ready = False
            if not self._stopping:
                self.status_changed.emit("LSP stopped")

    def _read_stderr(self) -> None:
        process = self.process
        try:
            if process and process.stderr:
                for line in process.stderr:
                    if self._stopping:
                        return
                    self.status_changed.emit("LSP: " + line.decode("utf-8", errors="replace").rstrip())
        except (OSError, ValueError):
            pass

    def open_document(self, path, text) -> None:
        if not self.is_ready:
            return
        uri = pathlib.Path(path).resolve().as_uri()
        previous = self._opened.get(uri)
        if previous is None:
            self._opened[uri] = (text, 1)
            self.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "python", "version": 1, "text": text}})
        elif previous[0] != text:
            version = previous[1] + 1
            self._opened[uri] = (text, version)
            self.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": version}, "contentChanges": [{"text": text}]})

    def close_document(self, path) -> None:
        uri = pathlib.Path(path).resolve().as_uri()
        if self._opened.pop(uri, None) is not None:
            self.notify("textDocument/didClose", {"textDocument": {"uri": uri}})

    def at_position(self, method, path, line, character, callback) -> None:
        self.request("textDocument/" + method, {"textDocument": {"uri": pathlib.Path(path).resolve().as_uri()},
            "position": {"line": line, "character": character}}, callback)

    def stop(self) -> None:
        self._stopping = True
        self.is_ready = False
        process, self.process = self.process, None
        if process is not None:
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
                except ProcessLookupError:
                    pass
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
        self._callbacks.clear()
        self._opened.clear()
        self.status_changed.emit("LSP stopped")
