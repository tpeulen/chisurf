"""Tests for the Agent Client Protocol (ACP) server."""

from __future__ import annotations

import io
import json
import threading

from chisurf.core.agent.acp_server import PROTOCOL_VERSION, AcpServer
from chisurf.core.agent.llm import LLMClient, LLMResponse, LLMSettings


class FakeLLMClient(LLMClient):
    """Deterministic LLM for testing ACP server interactions."""

    def __init__(self, answer: str = "ChiSurf lifetime fit results."):
        super().__init__(LLMSettings(base_url="http://mock", model="mock"))
        self.answer = answer
        self.turns: list[dict] = []

    def complete(self, messages, tools=None):
        self.turns.append({"messages": messages, "tools": tools})
        return LLMResponse(text=self.answer, raw_message={"role": "assistant", "content": self.answer})


class TestAcpServer:
    """Test JSON-RPC 2.0 handling and ACP methods in AcpServer."""

    def test_initialize_returns_capabilities(self):
        """initialize returns protocol version and agent capabilities."""
        server = AcpServer()
        resp = server.handle_initialize({"clientCapabilities": {"fs": {"readTextFile": True}}})
        assert resp["protocolVersion"] == PROTOCOL_VERSION
        assert "ChiSurf" in resp["agentInfo"]["name"]
        assert resp["agentCapabilities"]["sessionCapabilities"]["close"] is True

    def test_new_session_creates_session_and_modes(self):
        """session/new returns a unique sessionId and available modes."""
        server = AcpServer()
        resp = server.handle_new_session({"cwd": "/tmp"})
        session_id = resp["sessionId"]
        assert session_id.startswith("session_")
        assert session_id in server.sessions
        assert resp["modes"]["currentModeId"] == "chisurf_tools"
        assert len(resp["modes"]["availableModes"]) == 3

    def test_set_mode_switches_mode_and_emits_notification(self):
        """session/set_mode updates mode and notifies client."""
        out = io.BytesIO()
        server = AcpServer(out_stream=out)
        new_res = server.handle_new_session({})
        sid = new_res["sessionId"]

        server.handle_set_mode({"sessionId": sid, "modeId": "full_control"})
        assert server.session_modes[sid] == "full_control"

        out.seek(0)
        lines = [json.loads(line.decode("utf-8")) for line in out if line.strip()]
        update_notifs = [m for m in lines if m.get("method") == "session/update"]
        assert any(
            n.get("params", {}).get("update", {}).get("currentModeId") == "full_control"
            for n in update_notifs
        )

    def test_prompt_runs_and_streams_response(self):
        """session/prompt streams chunks and responds with end_turn."""
        out = io.BytesIO()
        server = AcpServer(out_stream=out)
        new_res = server.handle_new_session({})
        sid = new_res["sessionId"]

        # Swap in fake session
        session = server.sessions[sid]
        session.llm = FakeLLMClient("Hello from ChiSurf ACP!")

        server._run_prompt_worker(42, {"sessionId": sid, "prompt": [{"type": "text", "text": "help me"}]})

        out.seek(0)
        lines = [json.loads(line.decode("utf-8")) for line in out if line.strip()]

        # Check prompt response
        prompt_res = next(m for m in lines if m.get("id") == 42)
        assert prompt_res["result"]["stopReason"] == "end_turn"

        # Check session/update notification with message chunk
        chunk_notif = next(
            m for m in lines
            if m.get("method") == "session/update"
            and m.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk"
        )
        assert chunk_notif["params"]["update"]["content"]["text"] == "Hello from ChiSurf ACP!"

    def test_cancel_stops_prompt_turn(self):
        """session/cancel flags active session as cancelled."""
        server = AcpServer()
        new_res = server.handle_new_session({})
        sid = new_res["sessionId"]

        server.handle_cancel({"sessionId": sid})
        assert server.sessions[sid]._cancelled is True

    def test_close_cleans_up_session(self):
        """session/close removes the session."""
        server = AcpServer()
        new_res = server.handle_new_session({})
        sid = new_res["sessionId"]

        server.handle_close_session({"sessionId": sid})
        assert sid not in server.sessions

    def test_newline_and_content_length_framing(self):
        """Server processes both newline-delimited and Content-Length framed messages."""
        msg1 = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        body1 = msg1.encode("utf-8") + b"\n"

        msg2 = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}})
        body2_content = msg2.encode("utf-8")
        body2 = f"Content-Length: {len(body2_content)}\r\n\r\n".encode("ascii") + body2_content

        in_stream = io.BytesIO(body1 + body2)
        out_stream = io.BytesIO()

        server = AcpServer(in_stream=in_stream, out_stream=out_stream)
        server.run()

        out_stream.seek(0)
        lines = [json.loads(line.decode("utf-8")) for line in out_stream if line.strip()]
        assert len(lines) == 2
        assert lines[0]["id"] == 1
        assert lines[0]["result"]["protocolVersion"] == PROTOCOL_VERSION
        assert lines[1]["id"] == 2
        assert lines[1]["result"] == {}


def test_acp_stdio_entrypoint_never_bootstraps_qt(monkeypatch):
    """The default server starts through a pure scheduler seam, not a GUI import."""
    import builtins

    from chisurf.core.agent import acp_server
    original = builtins.__import__
    attempts = []
    def no_gui(name, *args, **kwargs):
        if name.split(".")[0] in {"qtpy", "PyQt5", "PyQt6", "PySide2", "PySide6"}:
            attempts.append(name)
            raise AssertionError("GUI dependency: " + name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_gui)
    monkeypatch.setattr(acp_server.AcpServer, "run", lambda self: None)
    assert acp_server.run_acp_server() == 0
    assert attempts == []


def test_acp_entrypoint_uses_injected_pure_presenter(monkeypatch):
    """An embedding view supplies scheduling without a view import in core."""
    from chisurf.core.agent import acp_server
    from chisurf.core.runtime import presentation
    calls = []
    prior = presentation.get_presenter()
    def presenter(callback, *args, **kwargs):
        calls.append(threading.get_ident())
        return callback(*args, **kwargs)
    monkeypatch.setattr(acp_server.AcpServer, "run", lambda self: presentation.notify(lambda: calls.append("notified")))
    try:
        assert acp_server.run_acp_server(presenter=presenter) == 0
        assert calls[-1] == "notified"
    finally:
        presentation.set_presenter(prior)


def test_acp_server_uses_http_delegate_for_transport_provider(monkeypatch):
    from chisurf.core.agent import acp_server
    from chisurf.core.settings import ai_settings
    providers = []
    monkeypatch.setattr(ai_settings, "get_api_settings", lambda provider=None: {"acp_backend_provider": "local"})
    monkeypatch.setattr(ai_settings, "get_provider", lambda: "acp")
    class Server:
        def __init__(self, **kwargs):
            providers.append(kwargs["provider"])
        def run(self):
            pass
    monkeypatch.setattr(acp_server, "AcpServer", Server)
    assert acp_server.run_acp_server(provider="acp") == 0
    assert providers == ["local"]
