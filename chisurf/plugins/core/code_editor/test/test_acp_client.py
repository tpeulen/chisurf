"""Tests for the Agent Client Protocol (ACP) client and its use in the code editor (emtk app).

The client is toolkit-free; the editor integration is the emtk assistant (``gui/chat_app.py``
``ChatModel``) over the editor model, ported from the retired Qt ``CodeEditor`` /
``AgentPanelWidget`` tests.
"""

from __future__ import annotations

import time

import pytest

from chisurf.plugins.core.code_editor.acp_client import AcpClient
from chisurf.plugins.core.code_editor.gui.chat_app import PROVIDERS, ChatModel
from chisurf.plugins.core.code_editor.gui.editor_app import EditorModel


def _pump(model, predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        model.process_events()
        time.sleep(0.01)
    model.process_events()


class TestAcpClient:
    """Test AcpClient JSON-RPC handling and signals."""

    def test_initialize_and_session_handshake(self):
        """AcpClient sends initialize and session/new and processes response."""
        received_requests = []

        def mock_transport(payload: dict) -> None:
            received_requests.append(payload)
            req_id = payload.get("id")
            method = payload.get("method")
            if method == "initialize":
                client.handle_incoming_message(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "protocolVersion": 1,
                            "agentInfo": {"name": "Test Agent", "version": "1.0"},
                            "agentCapabilities": {},
                        },
                    }
                )
            elif method == "session/new":
                client.handle_incoming_message(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "sessionId": "sess_123",
                            "modes": {
                                "currentModeId": "chisurf_tools",
                                "availableModes": [{"id": "chisurf_tools", "name": "Tools"}],
                            },
                        },
                    }
                )

        client = AcpClient(transport=mock_transport)
        client.start()
        assert client.is_ready

        # Test initialize
        init_cb_called = []
        client.initialize(callback=lambda res: init_cb_called.append(res))
        assert len(init_cb_called) == 1
        assert client.agent_info.get("name") == "Test Agent"

        # Test new_session
        session_created_events = []
        client.session_created.connect(session_created_events.append)
        client.new_session()
        assert client.session_id == "sess_123"
        assert session_created_events == ["sess_123"]
        assert client.current_mode_id == "chisurf_tools"

    def test_streaming_updates_emit_signals(self):
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
        client.handle_incoming_message(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": "sess_123",
                    "update": {
                        "sessionUpdate": "agent_message_chunk",
                        "content": {"type": "text", "text": "Analyzing data..."},
                    },
                },
            }
        )

        # Agent thought chunk
        client.handle_incoming_message(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": "sess_123",
                    "update": {
                        "sessionUpdate": "agent_thought_chunk",
                        "content": {"type": "text", "text": "Plan: fit lifetime"},
                    },
                },
            }
        )

        # Tool call
        client.handle_incoming_message(
            {
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
            }
        )

        # Mode update
        client.handle_incoming_message(
            {
                "jsonrpc": "2.0",
                "method": "session/update",
                "params": {
                    "sessionId": "sess_123",
                    "update": {
                        "sessionUpdate": "current_mode_update",
                        "currentModeId": "full_control",
                    },
                },
            }
        )

        assert chunks == [("sess_123", "Analyzing data...")]
        assert thoughts == [("sess_123", "Plan: fit lifetime")]
        assert len(tools) == 1 and tools[0][1]["name"] == "load_data"
        assert modes == [("sess_123", "full_control")]
        assert client.current_mode_id == "full_control"

    def test_fs_read_and_write_dispatch(self, tmp_path):
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
        client.handle_incoming_message(
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "fs/read_text_file",
                "params": {"path": "analysis.py", "line": 0, "limit": 10},
            }
        )

        assert read_calls == [("analysis.py", 0, 10)]
        assert len(sent_responses) == 1
        assert sent_responses[0]["id"] == 99
        assert sent_responses[0]["result"]["content"] == "content_of_analysis.py"

        # Agent requests file write
        client.handle_incoming_message(
            {
                "jsonrpc": "2.0",
                "id": 100,
                "method": "fs/write_text_file",
                "params": {"path": "fit.py", "content": "print('fitted')"},
            }
        )

        assert written_files.get("fit.py") == "print('fitted')"
        assert len(sent_responses) == 2
        assert sent_responses[1]["id"] == 100
        assert sent_responses[1]["result"] == {}


class TestCodeEditorAcpIntegration:
    """The editor's assistant: ACP filesystem sync."""

    def test_editor_assistant_creates_an_acp_client_with_handlers(self, tmp_path):
        """The assistant builds its ACP client with the editor's read/write/permission handlers."""
        editor = EditorModel(project_root=tmp_path)
        chat = ChatModel(editor_ref=editor)
        try:
            client = chat.acp_client
            assert client is not None
            assert client.read_file_handler == chat._handle_read_file
            assert client.write_file_handler == chat._handle_write_file
        finally:
            chat.close()
            editor.close()

    def test_acp_read_prefers_open_tab_unsaved_content(self, tmp_path):
        """fs/read_text_file returns the open tab's content even before it is saved."""
        editor = EditorModel(project_root=tmp_path)
        chat = ChatModel(editor_ref=editor)
        try:
            test_file = tmp_path / "script.py"
            test_file.write_text("saved content on disk", encoding="utf-8")
            doc = editor.open_file(test_file)
            doc.editor.text = "UNSAVED MODIFIED CONTENT"
            assert chat._handle_read_file(str(test_file)) == "UNSAVED MODIFIED CONTENT"
        finally:
            chat.close()
            editor.close()

    def test_acp_write_updates_open_tab_in_memory(self, tmp_path):
        """fs/write_text_file puts the text into the open tab, left modified for review.

        Deliberate difference from the Qt editor, which also wrote the disk at once: the emtk
        editor writes the file when the user saves the agent's edit
        (``test_emtk_editor.py::test_acp_buffer_operations_are_queued_to_native_render_thread``).
        """
        editor = EditorModel(project_root=tmp_path)
        chat = ChatModel(editor_ref=editor)
        try:
            test_file = tmp_path / "script.py"
            test_file.write_text("old text", encoding="utf-8")
            doc = editor.open_file(test_file)
            chat._handle_write_file(str(test_file), "new agent code")
            assert doc.text == "new agent code"
            assert doc.is_modified
            assert test_file.read_text(encoding="utf-8") == "old text"
            editor.save_document(editor.documents.index(doc))
            assert test_file.read_text(encoding="utf-8") == "new agent code"
        finally:
            chat.close()
            editor.close()


class TestAssistantAcpFlow:
    """The assistant routes a turn to ACP."""

    def test_the_assistant_lists_the_acp_provider(self):
        """The provider choice includes the ACP agent."""
        assert "acp" in PROVIDERS

    def test_an_acp_turn_streams_into_the_transcript(self):
        """send_prompt starts an ACP prompt and the streamed chunks reach the transcript."""
        chat = ChatModel()
        sent_prompts = []

        def mock_transport(payload: dict) -> None:
            req_id = payload.get("id")
            method = payload.get("method")
            if method == "initialize":
                chat.acp_client.handle_incoming_message(
                    {"jsonrpc": "2.0", "id": req_id,
                     "result": {"protocolVersion": 1, "agentInfo": {}, "agentCapabilities": {}}}
                )
            elif method == "session/new":
                chat.acp_client.handle_incoming_message(
                    {"jsonrpc": "2.0", "id": req_id, "result": {"sessionId": "s_acp_1", "modes": {}}}
                )
            elif method == "session/prompt":
                sent_prompts.append(payload)
                chat.acp_client.handle_incoming_message(
                    {
                        "jsonrpc": "2.0",
                        "method": "session/update",
                        "params": {
                            "sessionId": "s_acp_1",
                            "update": {
                                "sessionUpdate": "agent_message_chunk",
                                "content": {"type": "text", "text": "Fit complete with chi2=1.01"},
                            },
                        },
                    }
                )
                chat.acp_client.handle_incoming_message(
                    {"jsonrpc": "2.0", "id": req_id, "result": {"stopReason": "end_turn"}}
                )

        try:
            chat.acp_client.stop()
            client = AcpClient(transport=mock_transport)
            chat.acp_client = client
            client.message_chunk.connect(chat._on_acp_message_chunk)
            client.prompt_finished.connect(chat._on_acp_prompt_finished)
            client.error_received.connect(chat._on_acp_error)
            chat.provider = "acp"
            chat.send_prompt("Fit my lifetime decay")
            _pump(chat, lambda: not chat.is_generating)
            transcript = " ".join(m.content for m in chat.history.messages)
            assert sent_prompts
            assert "Fit complete with chi2=1.01" in transcript
        finally:
            chat.close()

    def test_acp_client_server_stdio_roundtrip(self, tmp_path):
        """AcpClient connects to AcpServer over real stdio process and handshakes."""
        import sys

        command = [sys.executable, "-m", "chisurf.core.agent.acp_server", "--no-qt"]
        client = AcpClient(root_path=tmp_path, command=command)
        started = client.start()
        assert started is True

        # Wait for initialize response
        for _ in range(100):
            if client.is_ready:
                break
            time.sleep(0.05)

        assert client.is_ready is True
        assert "ChiSurf" in client.agent_info.get("name", "")

        # Create session
        client.new_session()
        for _ in range(100):
            if client.session_id is not None:
                break
            time.sleep(0.05)

        assert client.session_id is not None
        assert client.current_mode_id == "chisurf_tools"

        # Switch mode
        client.set_mode("full_control")
        for _ in range(100):
            if client.current_mode_id == "full_control":
                break
            time.sleep(0.05)

        assert client.current_mode_id == "full_control"

        client.stop()
