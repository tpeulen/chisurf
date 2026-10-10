"""Tests for Agent Client Protocol (ACP) client and CodeEditor integration."""

from __future__ import annotations

import json
import pathlib

import pytest
from qtpy import QtCore, QtWidgets

from chisurf.plugins.core.code_editor.acp_client import AcpClient
from chisurf.plugins.core.code_editor.agent_panel import AgentPanelWidget
from chisurf.plugins.core.code_editor.editor import CodeEditor


class TestAcpClient:
    """Test AcpClient JSON-RPC handling and signals."""

    def test_initialize_and_session_handshake(self, qapp):
        """AcpClient sends initialize and session/new and processes response."""
        received_requests = []

        def mock_transport(payload: dict) -> None:
            received_requests.append(payload)
            req_id = payload.get("id")
            method = payload.get("method")
            if method == "initialize":
                client.handle_incoming_message({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": 1,
                        "agentInfo": {"name": "Test Agent", "version": "1.0"},
                        "agentCapabilities": {},
                    },
                })
            elif method == "session/new":
                client.handle_incoming_message({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "sessionId": "sess_123",
                        "modes": {
                            "currentModeId": "chisurf_tools",
                            "availableModes": [{"id": "chisurf_tools", "name": "Tools"}],
                        },
                    },
                })

        client = AcpClient(transport=mock_transport)
        client.start()
        assert client.is_ready

        # Test initialize
        init_cb_called = []
        client.initialize(callback=lambda res: init_cb_called.append(res))
        QtWidgets.QApplication.processEvents()
        assert len(init_cb_called) == 1
        assert client.agent_info.get("name") == "Test Agent"

        # Test new_session
        session_created_events = []
        client.session_created.connect(session_created_events.append)
        client.new_session()
        QtWidgets.QApplication.processEvents()
        assert client.session_id == "sess_123"
        assert session_created_events == ["sess_123"]
        assert client.current_mode_id == "chisurf_tools"

    def test_streaming_updates_emit_signals(self, qapp):
        """session/update notifications fire message_chunk, thought_chunk, tool_call."""
        client = AcpClient(transport=lambda p: None)
        client.session_id = "sess_123"

        chunks = []
        thoughts = []
        tools = []
        modes = []

        client.message_chunk.connect(lambda s, t: chunks.append((s, t)))
        client.thought_chunk.connect(lambda s, t: thoughts.append((s, t)))
        client.tool_call.connect(lambda s, t: tools.append((s, t)))
        client.mode_changed.connect(lambda s, m: modes.append((s, m)))

        # Agent message chunk
        client.handle_incoming_message({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "sess_123",
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": "Analyzing data..."},
                },
            },
        })

        # Agent thought chunk
        client.handle_incoming_message({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "sess_123",
                "update": {
                    "sessionUpdate": "agent_thought_chunk",
                    "content": {"type": "text", "text": "Plan: fit lifetime"},
                },
            },
        })

        # Tool call
        client.handle_incoming_message({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "sess_123",
                "update": {
                    "sessionUpdate": "tool_call",
                    "toolCallId": "c1",
                    "name": "load_data",
                    "status": "in_progress",
                },
            },
        })

        # Mode update
        client.handle_incoming_message({
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "sessionId": "sess_123",
                "update": {
                    "sessionUpdate": "current_mode_update",
                    "currentModeId": "full_control",
                },
            },
        })

        assert chunks == [("sess_123", "Analyzing data...")]
        assert thoughts == [("sess_123", "Plan: fit lifetime")]
        assert len(tools) == 1 and tools[0][1]["name"] == "load_data"
        assert modes == [("sess_123", "full_control")]
        assert client.current_mode_id == "full_control"

    def test_fs_read_and_write_dispatch(self, qapp, tmp_path):
        """fs/read_text_file and fs/write_text_file invoke registered handlers."""
        read_calls = []
        written_files = {}

        def mock_read(path: str, line: int | None, limit: int | None) -> str:
            read_calls.append((path, line, limit))
            return "content_of_" + path

        def mock_write(path: str, content: str) -> None:
            written_files[path] = content

        sent_responses = []

        def mock_transport(payload: dict) -> None:
            sent_responses.append(payload)

        client = AcpClient(
            transport=mock_transport,
            read_file_handler=mock_read,
            write_file_handler=mock_write,
        )

        # Agent requests file read
        client.handle_incoming_message({
            "jsonrpc": "2.0",
            "id": 99,
            "method": "fs/read_text_file",
            "params": {"path": "analysis.py", "line": 0, "limit": 10},
        })
        QtWidgets.QApplication.processEvents()

        assert read_calls == [("analysis.py", 0, 10)]
        assert len(sent_responses) == 1
        assert sent_responses[0]["id"] == 99
        assert sent_responses[0]["result"]["content"] == "content_of_analysis.py"

        # Agent requests file write
        client.handle_incoming_message({
            "jsonrpc": "2.0",
            "id": 100,
            "method": "fs/write_text_file",
            "params": {"path": "fit.py", "content": "print('fitted')"},
        })
        QtWidgets.QApplication.processEvents()

        assert written_files.get("fit.py") == "print('fitted')"
        assert len(sent_responses) == 2
        assert sent_responses[1]["id"] == 100
        assert sent_responses[1]["result"] == {}


class TestCodeEditorAcpIntegration:
    """Test CodeEditor ACP filesystem sync and permission handling."""

    def test_editor_ensure_acp_creates_client(self, qapp, tmp_path):
        """CodeEditor.ensure_acp initializes client with handlers."""
        editor = CodeEditor(project_root=tmp_path)
        client = editor.ensure_acp()
        assert client is not None
        assert editor.acp_client is client
        client.stop()

    def test_acp_read_prefers_open_tab_unsaved_content(self, qapp, tmp_path):
        """fs/read_text_file returns open editor tab content even before save."""
        editor = CodeEditor(project_root=tmp_path)
        test_file = tmp_path / "script.py"
        test_file.write_text("saved content on disk", encoding="utf-8")

        editor.open_file(str(test_file))
        current_ed = editor._get_current_editor()
        current_ed.setPlainText("UNSAVED MODIFIED CONTENT")

        read_content = editor._handle_acp_read_file(str(test_file))
        assert read_content == "UNSAVED MODIFIED CONTENT"

    def test_acp_write_updates_open_tab_in_memory(self, qapp, tmp_path):
        """fs/write_text_file updates open editor tab buffer immediately."""
        editor = CodeEditor(project_root=tmp_path)
        test_file = tmp_path / "script.py"
        test_file.write_text("old text", encoding="utf-8")

        editor.open_file(str(test_file))
        current_ed = editor._get_current_editor()

        editor._handle_acp_write_file(str(test_file), "new agent code")
        assert current_ed.toPlainText() == "new agent code"
        assert current_ed.document().isModified()
        assert test_file.read_text(encoding="utf-8") == "new agent code"


class TestAgentPanelAcpFlow:
    """Test AgentPanelWidget routing to ACP."""

    def test_panel_lists_acp_provider(self, qapp):
        """Panel provider dropdown includes ACP Agent."""
        panel = AgentPanelWidget()
        providers = [panel.provider_combo.itemData(i) for i in range(panel.provider_combo.count())]
        assert "acp" in providers

    def test_panel_start_acp_wires_streaming(self, qapp):
        """_start_acp triggers prompt on AcpClient and streams chunks to transcript."""
        panel = AgentPanelWidget()
        sent_prompts = []

        def mock_transport(payload: dict) -> None:
            req_id = payload.get("id")
            method = payload.get("method")
            if method == "initialize":
                panel._acp_client.handle_incoming_message({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"protocolVersion": 1, "agentInfo": {}, "agentCapabilities": {}},
                })
            elif method == "session/new":
                panel._acp_client.handle_incoming_message({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"sessionId": "s_acp_1", "modes": {}},
                })
            elif method == "session/prompt":
                sent_prompts.append(payload)
                # Stream chunk
                panel._acp_client.handle_incoming_message({
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": "s_acp_1",
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "Fit complete with chi2=1.01"},
                        },
                    },
                })
                # End turn
                panel._acp_client.handle_incoming_message({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"stopReason": "end_turn"},
                })

        from chisurf.plugins.core.code_editor.acp_client import AcpClient

        panel._acp_client = AcpClient(transport=mock_transport, parent=panel)
        panel._start_acp("Fit my lifetime decay")

        for _ in range(10):
            QtWidgets.QApplication.processEvents()
        transcript = panel.transcript.toPlainText()
        assert "Fit complete with chi2=1.01" in transcript

    def test_acp_client_server_stdio_roundtrip(self, qapp, tmp_path):
        """AcpClient connects to AcpServer over real stdio process and handshakes."""
        import sys

        from chisurf.plugins.core.code_editor.acp_client import AcpClient

        command = [sys.executable, "-m", "chisurf.core.agent.acp_server", "--no-qt"]
        client = AcpClient(root_path=tmp_path, command=command)
        started = client.start()
        assert started is True

        # Wait for initialize response
        for _ in range(50):
            QtWidgets.QApplication.processEvents()
            if client.is_ready:
                break
            QtCore.QThread.msleep(50)

        assert client.is_ready is True
        assert "ChiSurf" in client.agent_info.get("name", "")

        # Create session
        client.new_session()
        for _ in range(50):
            QtWidgets.QApplication.processEvents()
            if client.session_id is not None:
                break
            QtCore.QThread.msleep(50)

        assert client.session_id is not None
        assert client.current_mode_id == "chisurf_tools"

        # Switch mode
        client.set_mode("full_control")
        for _ in range(50):
            QtWidgets.QApplication.processEvents()
            if client.current_mode_id == "full_control":
                break
            QtCore.QThread.msleep(50)

        assert client.current_mode_id == "full_control"

        client.stop()

