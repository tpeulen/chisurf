"""EMTK immediate-mode AI Assistant / Chat widget and application.

Supports ACP (Agent Client Protocol) over stdio subprocesses as well as in-process
AgentSession/LLMClient execution, streaming tokens, code block extraction, tool badges,
permission request banners, and editor integration.
"""

from __future__ import annotations

import json
import logging
import queue
import shlex
import threading
from typing import Any, Callable

import emtk.im as im
from emtk.app import ImApp
from emtk.im_core import Col
from emtk.widgets.chat import (
    ChatHistory,
    draw_chat_input_bar,
    draw_chat_transcript,
)

from chisurf.plugins.core.code_editor.acp_client import AcpClient

_LOGGER = logging.getLogger(__name__)

PROVIDERS = ["acp", "openai", "mistral", "openrouter", "local", "custom"]
PROVIDER_LABELS = {
    "acp": "ACP Agent (stdio)",
    "openai": "OpenAI (ChatGPT)",
    "mistral": "Mistral",
    "openrouter": "OpenRouter",
    "local": "Local (Ollama/LMStudio)",
    "custom": "Custom",
}

MODES = ["chat_only", "chisurf_tools", "full_control"]
MODE_LABELS = {
    "chat_only": "Chat only",
    "chisurf_tools": "ChiSurf tools",
    "full_control": "Full control",
}


class ChatModel:
    """State and backend controller for the EMTK chat widget."""

    def __init__(self, editor_ref: Any = None) -> None:
        self.history = ChatHistory()
        self.provider = "acp"
        self.mode = "chisurf_tools"
        self.model_name = "default"
        self.temperature = 0.2
        self.input_text = ""
        self.is_generating = False
        self._closed = False
        self._in_process_thread: threading.Thread | None = None
        self._ignore_response = False
        self._agent_session = None
        self._agent_key = None
        self._tool_count = 0
        self._active_runtime_tools: dict[str, str] = {}
        self.editor_ref = editor_ref

        # Pending permission dialog: {"id": str, "title": str, "options": list}
        self.pending_permission: dict[str, Any] | None = None
        self._permission_response_cb: Callable[[str], None] | None = None

        # Thread-safe event queue for incoming ACP / agent callbacks
        self.event_queue: queue.Queue[Callable[[], None]] = queue.Queue()

        # ACP Client
        self.acp_client: AcpClient | None = None
        self._init_acp()

    def _init_acp(self) -> None:
        """Initialize and wire up ACP client signals."""
        try:
            self.acp_client = AcpClient(
                root_path=getattr(self.editor_ref, "project_root", None),
                read_file_handler=self._handle_read_file,
                write_file_handler=self._handle_write_file,
                permission_handler=self._handle_permission_request,
            )
            self.acp_client.message_chunk.connect(self._on_acp_message_chunk)
            self.acp_client.tool_call.connect(self._on_acp_tool_call)
            self.acp_client.prompt_finished.connect(self._on_acp_prompt_finished)
            self.acp_client.mode_changed.connect(self._on_acp_mode_changed)
            self.acp_client.error_received.connect(self._on_acp_error)
            self.acp_client.status_changed.connect(self._on_acp_status)
        except Exception as e:
            _LOGGER.warning(f"Could not initialize AcpClient: {e}")

    # -- Event queue dispatch -------------------------------------------------

    def process_events(self) -> None:
        """Process any pending background callbacks on the main/render thread."""
        if self._closed:
            return
        while not self.event_queue.empty():
            try:
                fn = self.event_queue.get_nowait()
                fn()
            except Exception as e:
                _LOGGER.error(f"Error executing queued chat event: {e}")

    # -- ACP Client Signal Handlers -------------------------------------------

    def _on_acp_message_chunk(self, session_id: str, chunk: str) -> None:
        if self._closed or self._ignore_response:
            return
        self.event_queue.put(
            lambda: self._handle_chunk(chunk) if not self._ignore_response else None
        )

    def _handle_chunk(self, chunk: str) -> None:
        self.is_generating = True
        self.history.append_chunk(chunk)

    def _on_acp_tool_call(self, session_id: str, data: dict) -> None:
        if self._closed:
            return
        call_id = data.get("toolCallId") or data.get("id") or "tool"
        name = data.get("title") or data.get("name") or "tool"
        status = data.get("status", "running")
        output = str(data.get("output", ""))
        args = data.get("arguments") or data.get("rawInput")
        self.event_queue.put(
            lambda: self.history.add_or_update_tool_call(
                call_id, name, args, status=status, output=output
            )
        )

    def _on_acp_prompt_finished(self, session_id: str, stop_reason: str) -> None:
        if self._closed:
            return
        self.event_queue.put(lambda: self._handle_finished(stop_reason))

    def _handle_finished(self, stop_reason: str = "complete") -> None:
        cancelled = self._ignore_response or stop_reason in ("cancelled", "canceled")
        self.is_generating = False
        self._ignore_response = False
        self.history.finish_generation(
            "cancelled" if cancelled else "error" if stop_reason == "error" else "complete"
        )

    def _on_acp_error(self, error: str) -> None:
        if self._closed:
            return
        self.event_queue.put(lambda: self.history.add_message("error", str(error)))
        self.event_queue.put(lambda: self._handle_finished("error"))

    def _on_acp_status(self, status: str) -> None:
        if self._closed:
            return
        if status == "ACP stopped" and self.is_generating:
            if self._ignore_response:
                self.event_queue.put(lambda: self._handle_finished("cancelled"))
            else:
                self._on_acp_error("The ACP agent stopped before finishing the prompt.")

    def _on_acp_mode_changed(self, session_id: str, mode: str) -> None:
        if self._closed:
            return
        self.event_queue.put(lambda: setattr(self, "mode", mode))

    def _handle_permission_request(self, tool_data: dict, options: list[dict]) -> str:
        if self._closed:
            return "cancelled"
        ready = threading.Event()
        response = ["cancelled"]

        def answer(option_id: str) -> None:
            response[0] = option_id
            ready.set()

        def present() -> None:
            if not ready.is_set():
                self.pending_permission = {
                    "title": tool_data.get("title", "Tool execution requires approval."),
                    "options": options,
                }

        self._permission_response_cb = answer
        self.event_queue.put(present)
        ready.wait()
        return response[0]

    def respond_permission(self, option_id: str) -> None:
        if self._permission_response_cb:
            try:
                self._permission_response_cb(option_id)
            except Exception as e:
                _LOGGER.error(f"Error responding to permission: {e}")
        self.pending_permission = None
        self._permission_response_cb = None

    # -- Filesystem Handlers for ACP ------------------------------------------

    def _handle_read_file(
        self, path: str, line: int | None = None, limit: int | None = None
    ) -> str:
        if self.editor_ref and hasattr(self.editor_ref, "get_file_content"):
            callback = self.editor_ref.get_file_content
            invoke = getattr(self.editor_ref, "invoke", None)
            content = invoke(callback, path) if invoke else callback(path)
            if content is not None:
                return self._read_slice(content, line, limit)
        try:
            with open(path, encoding="utf-8") as f:
                return self._read_slice(f.read(), line, limit)
        except Exception as e:
            return f"Error reading file: {e}"

    @staticmethod
    def _read_slice(content: str, line: int | None, limit: int | None) -> str:
        if line is None and limit is None:
            return content
        start = max(0, (line or 1) - 1)
        rows = content.splitlines(keepends=True)
        return "".join(rows[start : None if limit is None else start + max(0, limit)])

    def _handle_write_file(self, path: str, content: str) -> None:
        if self.editor_ref and hasattr(self.editor_ref, "set_file_content"):
            callback = self.editor_ref.set_file_content
            invoke = getattr(self.editor_ref, "invoke", None)
            updated = invoke(callback, path, content) if invoke else callback(path, content)
            if updated:
                return
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    # -- User Actions ---------------------------------------------------------

    def use_provider_settings(self, settings) -> bool:
        """Apply provider selection only after the transport command is valid."""
        if self.is_generating:
            return False
        command = None
        if settings.provider == "acp":
            try:
                command = shlex.split(settings.command.strip())
                if not command:
                    raise ValueError("Enter an ACP executable and arguments")
            except ValueError as error:
                settings._set_status(f"Invalid ACP command: {error}", "red")
                return False
        if command is not None and self.acp_client is not None:
            self.acp_client.stop()
            self.acp_client.command = command
        self.provider = settings.provider
        self.model_name = "default"
        self.temperature = settings.temperature
        self._agent_session = None
        self._agent_key = None
        return True

    def export_settings(self) -> dict:
        return {
            "provider": self.provider,
            "mode": self.mode,
            "model_name": self.model_name,
            "temperature": self.temperature,
        }

    def restore_settings(self, settings: dict) -> None:
        if settings.get("provider") in PROVIDERS:
            self.provider = settings["provider"]
        if settings.get("mode") in MODES:
            self.mode = settings["mode"]
        if isinstance(settings.get("model_name"), str):
            self.model_name = settings["model_name"]
        if (
            isinstance(settings.get("temperature"), (int, float))
            and 0 <= settings["temperature"] <= 2
        ):
            self.temperature = float(settings["temperature"])

    def send_prompt(self, text: str) -> None:
        clean_text = text.strip()
        if not clean_text or self.is_generating or self._closed:
            return

        self.history.add_message("user", clean_text)
        self.is_generating = True
        self._ignore_response = False

        if self.provider == "acp":
            client = self.acp_client
            if client is None:
                self.history.add_message("error", "ACP Client is not available.")
                self.is_generating = False
                return
            try:
                if not client.is_running:
                    from chisurf.core.settings import ai_settings

                    configured = str(ai_settings.get_api_settings("acp").get("command", "")).strip()
                    if configured and client.command == client._default_command():
                        client.command = shlex.split(configured)
                if not client.is_running and not client.start():
                    raise RuntimeError("ACP agent could not start")
                mode = self.mode

                def submit(session_id: str) -> None:
                    if self._closed or self._ignore_response:
                        self.event_queue.put(lambda: self._handle_finished("cancelled"))
                        return
                    try:
                        client.set_mode(mode, session_id=session_id)
                        client.prompt(clean_text, session_id=session_id)
                    except Exception as error:
                        self._on_acp_error(str(error))

                if client.session_id:
                    submit(client.session_id)
                else:
                    client.new_session(
                        cwd=getattr(self.editor_ref, "project_root", None), callback=submit
                    )
            except Exception as error:
                self._on_acp_error(str(error))
        else:
            self._in_process_thread = threading.Thread(
                target=self._run_in_process_prompt, args=(clean_text,), daemon=True
            )
            self._in_process_thread.start()

    def _on_runtime_event(self, event: str, payload: dict) -> None:
        if self._closed or self._ignore_response:
            return
        if event == "message.completed":
            self.event_queue.put(
                lambda: (
                    self.history.add_message("assistant", str(payload.get("content", "")))
                    if not self._ignore_response
                    else None
                )
            )
        elif event.startswith("tool."):
            name = payload.get("tool", "tool")
            if event == "tool.started":
                self._tool_count += 1
                self._active_runtime_tools[name] = f"runtime_{self._tool_count}"
            call_id = self._active_runtime_tools.get(name, name)
            status = (
                "running"
                if event == "tool.started"
                else (
                    "complete" if event == "tool.completed" and payload.get("ok", True) else "error"
                )
            )
            self.event_queue.put(
                lambda: self.history.add_or_update_tool_call(
                    call_id,
                    name,
                    payload.get("arguments"),
                    status=status,
                    output=json.dumps(payload.get("result", payload.get("error", "")), default=str),
                )
            )
        elif event == "agent.failed":
            self.event_queue.put(
                lambda: self.history.add_message("error", str(payload.get("error", "Agent failed")))
            )

    def _run_in_process_prompt(self, prompt: str) -> None:
        """Use the same persistent, Qt-free agent contract as the CLI and Qt panel."""
        try:
            from chisurf.core.agent import (
                AgentConfig,
                AgentContext,
                AgentSession,
                LLMClient,
                LLMSettings,
                ToolRegistry,
            )

            key = (self.provider, self.mode, self.model_name, self.temperature)
            if self._agent_session is None or key != self._agent_key:
                overrides = {"temperature": self.temperature}
                if self.model_name != "default":
                    overrides["model"] = self.model_name
                settings = LLMSettings.from_provider(self.provider, **overrides)
                settings.validate()

                def confirm(tool: str, arguments: dict) -> bool:
                    decision = self._handle_permission_request(
                        {"title": f"{tool}: {json.dumps(arguments, default=str)}"},
                        [
                            {"optionId": "allow_once", "name": "Allow once"},
                            {"optionId": "deny_once", "name": "Deny"},
                        ],
                    )
                    return decision == "allow_once"

                context = AgentContext(
                    working_directory=str(getattr(self.editor_ref, "project_root", ".")),
                    allow_code_execution=self.mode == "full_control",
                    confirm=confirm,
                    event_callback=self._on_runtime_event,
                )
                self._agent_session = AgentSession(
                    LLMClient(settings),
                    context=context,
                    config=AgentConfig(
                        max_safety="dangerous"
                        if self.mode == "full_control"
                        else "write"
                        if self.mode == "chisurf_tools"
                        else "read"
                    ),
                    registry=ToolRegistry() if self.mode == "chat_only" else None,
                )
                self._agent_key = key
            if self._closed:
                return
            result = self._agent_session.ask(prompt)
            if result.error and not self._closed:
                self.event_queue.put(
                    lambda error=result.error: self.history.add_message("error", str(error))
                )
            self._on_acp_prompt_finished("", result.stop_reason)
        except Exception as err:
            if not self._closed:
                self.event_queue.put(
                    lambda error=str(err): self.history.add_message(
                        "error", f"Agent error: {error}"
                    )
                )
                self.event_queue.put(self._handle_finished)

    def cancel(self) -> None:
        was_generating = self.is_generating
        self._ignore_response = True
        if self._agent_session is not None:
            self._agent_session.cancel()
        if self._permission_response_cb:
            self.respond_permission("cancelled")
        active_worker = self._in_process_thread is not None and self._in_process_thread.is_alive()
        active_acp = self.acp_client is not None and self.acp_client.is_running and was_generating
        if active_acp:
            self.acp_client.cancel()
        # Do not allow a second turn to reset the cancelled session while its
        # first network request or tool is still returning.
        self.is_generating = bool(active_worker or active_acp)
        self.history.finish_generation("cancelled")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.cancel()
        if self.acp_client is not None:
            self.acp_client.stop()
        self.is_generating = False
        while not self.event_queue.empty():
            try:
                self.event_queue.get_nowait()
            except queue.Empty:
                break

    def clear(self) -> None:
        self.cancel()
        if self.acp_client is not None and self.acp_client.is_running:
            self.acp_client.stop()
        self.is_generating = bool(
            self._in_process_thread is not None and self._in_process_thread.is_alive()
        )
        self.history.clear()
        self._agent_session = None
        self._agent_key = None
        self.pending_permission = None


class ChatGui:
    """Immediate-mode rendering and interaction for the chat assistant."""

    def __init__(self, model: ChatModel | None = None, editor_ref: Any = None) -> None:
        self.model = model or ChatModel(editor_ref=editor_ref)
        self.provider_settings = None
        self.provider_settings_open = False

    def draw_provider_settings(self) -> None:
        if not self.provider_settings_open or self.provider_settings is None:
            return
        im.set_next_window_size((700, 660), im.Cond.FIRST_USE_EVER)
        if im.begin("Provider settings##chat_provider_settings"):
            if im.button("Use settings and close"):
                if self.model.use_provider_settings(self.provider_settings.model):
                    self.provider_settings_open = False
            im.set_item_tooltip("Use this provider configuration for subsequent chat turns")
            im.same_line()
            if im.button("Close provider settings"):
                self.provider_settings_open = False
            im.set_item_tooltip(
                "Close the provider form; field edits use the shared provider store"
            )
            im.begin_child(
                (*im.get_cursor_screen_pos(), *im.get_content_region_avail()),
                child_id="chat_provider_fields",
            )
            self.provider_settings.draw()
            im.end_child()
        im.end()

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        self.model.process_events()
        if self.provider_settings is not None:
            self.provider_settings.process_events()

        avail_w = im.get_content_region_avail()[0]
        width = float(w or avail_w or 360.0)

        # 1. Top Controls Bar: Provider, Mode
        self._draw_toolbar(width)

        # 2. Permission request notification banner if pending
        if self.model.pending_permission:
            self._draw_permission_banner()

        # 3. Dynamic sizing: Input bar takes fixed space at bottom, transcript fills the rest
        input_box_h = 52.0
        buttons_h = 30.0
        input_total_h = input_box_h + buttons_h + 14.0

        rem_h = im.get_content_region_avail()[1]
        transcript_h = max(70.0, rem_h - input_total_h)

        draw_chat_transcript(
            self.model.history,
            size=(width, transcript_h),
            on_insert_code=self._on_insert_code,
            on_replace_code=self._on_replace_code,
        )

        im.separator()

        # 4. Input bar: multiline field and Send / Cancel / Clear
        new_prompt, send_requested = draw_chat_input_bar(
            self.model.input_text,
            is_generating=self.model.is_generating,
            on_send=self.model.send_prompt,
            on_cancel=self.model.cancel,
            on_clear=self.model.clear,
            input_height=input_box_h,
        )
        self.model.input_text = new_prompt
        self.draw_provider_settings()

    def _draw_toolbar(self, width: float) -> None:
        avail_w = im.get_content_region_avail()[0]
        combo_w = max(70.0, (avail_w - 12.0) / 2.0)

        # Provider and mode belong to the turn that is currently running.
        im.begin_disabled(self.model.is_generating)
        # Provider selector
        im.set_next_item_width(combo_w)
        current_p_idx = (
            PROVIDERS.index(self.model.provider) if self.model.provider in PROVIDERS else 0
        )
        p_labels = [PROVIDER_LABELS.get(p, p) for p in PROVIDERS]
        changed_p, new_p_idx = im.combo("##p_select", current_p_idx, p_labels)
        im.set_item_tooltip("Choose the assistant provider")
        if changed_p:
            self.model.provider = PROVIDERS[new_p_idx]

        im.same_line()

        # Mode selector
        im.set_next_item_width(combo_w)
        current_m_idx = MODES.index(self.model.mode) if self.model.mode in MODES else 0
        m_labels = [MODE_LABELS.get(m, m) for m in MODES]
        changed_m, new_m_idx = im.combo("##m_select", current_m_idx, m_labels)
        im.set_item_tooltip("Choose which tools the assistant may use")
        if changed_m:
            self.model.mode = MODES[new_m_idx]
            if self.model.acp_client and self.model.acp_client.is_running:
                self.model.acp_client.set_mode(self.model.mode)

        if im.small_button("Provider settings…"):
            if self.provider_settings is None:
                from chisurf.plugins.ai_settings.gui.app import AISettingsGui

                self.provider_settings = AISettingsGui()
            self.provider_settings.select_provider(self.model.provider)
            self.provider_settings_open = True
        im.set_item_tooltip(
            "Configure API endpoint, masked credential, models, sampling or the ACP command"
        )
        im.end_disabled()
        im.separator()

    def _draw_permission_banner(self) -> None:
        req = self.model.pending_permission
        if not req:
            return

        im.text_colored((255, 200, 80, 255), "Permission Request")
        width = max(80.0, im.get_content_region_avail()[0])
        title = str(req.get("title", "Tool execution requires approval."))
        details_h = min(140.0, max(28.0, im.calc_text_size(title, wrap_width=width)[1] + 8.0))
        im.begin_child(
            (*im.get_cursor_screen_pos(), width, details_h), child_id="permission_details"
        )
        im.text_wrapped(title)
        im.end_child()
        columns = max(1, int(width // 90))
        for index, opt in enumerate(req.get("options", [])):
            if index % columns:
                im.same_line()
            opt_id = opt.get("optionId", "allow")
            opt_name = opt.get("name", opt_id)
            allowed = opt_id.startswith("allow") or opt_id in ("yes", "proceed")
            im.push_style_color(Col.BUTTON, (46, 140, 67, 255) if allowed else (160, 60, 60, 255))
            if im.button(
                f"{opt_name}##{opt_id}", (max(60.0, min(120.0, width / columns - 6)), 24.0)
            ):
                self.model.respond_permission(opt_id)
            im.set_item_tooltip(f"Respond to permission request: {opt_name}")
            im.pop_style_color()
        im.separator()

    def _on_insert_code(self, code: str) -> None:
        if self.model.editor_ref and hasattr(self.model.editor_ref, "insert_code_at_cursor"):
            self.model.editor_ref.insert_code_at_cursor(code)

    def _on_replace_code(self, code: str) -> None:
        if self.model.editor_ref and hasattr(self.model.editor_ref, "replace_selected_code"):
            self.model.editor_ref.replace_selected_code(code)


class ChatApp(ImApp):
    """EMTK Application for the standalone or embedded Chat widget."""

    def __init__(self, model: ChatModel | None = None, editor_ref: Any = None) -> None:
        self.chat_gui = ChatGui(model=model, editor_ref=editor_ref)
        super().__init__(gui=self._render, continuous=False)

    def export_settings(self) -> dict:
        return self.chat_gui.model.export_settings()

    def restore_settings(self, settings: dict) -> None:
        self.chat_gui.model.restore_settings(settings)

    def close(self) -> None:
        self.chat_gui.model.close()
        if self.chat_gui.provider_settings is not None:
            self.chat_gui.provider_settings.close()

    def animating(self) -> bool:
        if self.chat_gui.model._closed:
            return False
        return (
            super().animating()
            or self.chat_gui.model.is_generating
            or not self.chat_gui.model.event_queue.empty()
            or (
                self.chat_gui.provider_settings is not None and self.chat_gui.provider_settings.busy
            )
        )

    def _render(self) -> None:
        self.chat_gui.draw()


def make_chat_app() -> ChatApp:
    """Factory for pure EMTK execution (e.g. via emtk.native or emtk.web)."""
    return ChatApp()


def main() -> None:
    """Run AI Assistant directly via pure EMTK without Qt."""
    from emtk.native import main as emtk_main

    emtk_main(
        [
            "--app",
            "chisurf.plugins.core.code_editor.gui.chat_app:make_chat_app",
            "--size",
            "440x680",
        ]
    )


if __name__ == "__main__":
    main()
