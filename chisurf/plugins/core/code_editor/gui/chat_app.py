"""EMTK immediate-mode AI Assistant / Chat widget and application.

Supports ACP (Agent Client Protocol) over stdio subprocesses as well as in-process
AgentSession/LLMClient execution, streaming tokens, code block extraction, tool badges,
permission request banners, and editor integration.
"""

from __future__ import annotations

import functools
import json
import logging
import queue
import shlex
import threading
from typing import TYPE_CHECKING, Any, Callable

import emtk.im as im
from emtk.app import ImApp
from emtk.i18n import tr
from emtk.im_core import Col
from emtk.widgets.chat import (
    ChatHistory,
    ChatMessage,
    draw_chat_input_bar,
    draw_chat_transcript,
)

from chisurf.plugins.core.code_editor.acp_client import AcpClient
from chisurf.plugins.core.code_editor.agent_modes import (
    AgentMode,
    greeting_for,
    provider_status,
    tool_highlight,
)

if TYPE_CHECKING:
    from chisurf.core.agent import AgentSession
    from chisurf.plugins.ai_settings.gui.app import AISettingsApp
    from chisurf.plugins.core.code_editor.wiki import WikiIndex

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


def _default_registry():
    """The agent's full tool registry (imported when a tool mode first needs it)."""
    from chisurf.core.agent import build_default_registry

    return build_default_registry()


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
        self._agent_session: AgentSession | None = None
        #: (provider, mode, model, temperature) the session was built for
        self._agent_key: tuple[str, str, str, float] | None = None
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

    @property
    def greeting(self) -> str:
        """What the assistant is for in the current mode (shown while the transcript is empty)."""
        return greeting_for(AgentMode(self.mode))

    def set_mode(self, mode: str) -> None:
        """Switch the mode: the tool set changes, so the conversation starts over and re-greets.

        An empty transcript shows the new mode's greeting by itself; a conversation gets it as a
        message, so the banner never describes the previous mode.
        """
        if mode not in MODES or mode == self.mode:
            return
        self.mode = mode
        self._agent_session = None
        self._agent_key = None
        if self.acp_client and self.acp_client.is_running:
            self.acp_client.set_mode(mode)
        if self.history.messages:
            self.history.add_message("system", self.greeting)

    def provider_status(self) -> tuple[bool, str]:
        """Whether the selected provider is usable, and why (the status dot's tooltip).

        Read at most every two seconds per provider: it opens the provider settings.
        """
        import time

        now = time.monotonic()
        cached = getattr(self, "_status_cache", None)
        if cached is None or cached[0] != self.provider or now - cached[1] > 2.0:
            self._status_cache = (self.provider, now, provider_status(self.provider))
        return self._status_cache[2]

    def transcript_text(self) -> str:
        """Everything the transcript shows, as text: messages, tool calls and their results."""
        if not self.history.messages:
            return self.greeting
        parts = []
        for message in self.history.messages:
            parts.append(message.content)
            for call in getattr(message, "tool_calls", None) or []:
                if isinstance(call, dict):
                    parts.extend(str(call.get(k, "")) for k in ("name", "output"))
                else:
                    parts.extend(str(getattr(call, k, "")) for k in ("name", "output"))
        return "\n".join(part for part in parts if part)

    def build_agent_context(self, mode: AgentMode):
        """The execution context of a tool-enabled turn.

        Code execution and its confirmation exist only in ``FULL_CONTROL``; runtime events reach
        the transcript through :meth:`_on_runtime_event`.
        """
        from chisurf.core.agent import AgentContext

        def confirm(tool: str, arguments: dict) -> bool:
            decision = self._handle_permission_request(
                {"title": f"{tool}: {json.dumps(arguments, default=str)}"},
                [
                    {"optionId": "allow_once", "name": "Allow once"},
                    {"optionId": "deny_once", "name": "Deny"},
                ],
            )
            return decision == "allow_once"

        full = mode is AgentMode.FULL_CONTROL
        return AgentContext(
            working_directory=str(getattr(self.editor_ref, "project_root", None) or "."),
            allow_code_execution=full,
            confirm=confirm if full else None,
            event_callback=self._on_runtime_event,
        )

    def agent_session_for(self, mode: AgentMode):
        """The conversation for *mode*, kept between questions so follow-ups keep their context.

        Returns ``None`` when the provider is not configured; the reason is written to the
        transcript then.
        """
        from chisurf.core.agent import (
            AgentConfig,
            AgentSession,
            LLMClient,
            LLMSettings,
            ToolRegistry,
        )

        key = (self.provider, mode.value, self.model_name, self.temperature)
        if self._agent_session is not None and key == self._agent_key:
            return self._agent_session
        overrides: dict[str, Any] = {"temperature": self.temperature}
        if self.model_name != "default":
            overrides["model"] = self.model_name
        try:
            settings = LLMSettings.from_provider(self.provider, **overrides)
            settings.validate()
        except Exception as error:
            self.history.add_message("system", f"⚠️ {error}")
            return None
        self._agent_session = AgentSession(
            LLMClient(settings),
            context=self.build_agent_context(mode),
            registry=ToolRegistry() if mode is AgentMode.CHAT_ONLY else _default_registry(),
            config=AgentConfig(max_safety=mode.safety),
            extra_instructions=(
                "You are running inside the ChiSurf desktop application; the "
                "user can see the fits you create in its windows."
            ),
        )
        self._agent_key = key
        return self._agent_session

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
        last = self.history.messages[-1] if self.history.messages else None
        if not cancelled and last is not None and last.role == "assistant":
            self.apply_file_writes(last.content)

    def apply_file_writes(self, response: str) -> list[tuple[str, str]]:
        """Write the files *response* asks for into the editor, then check them off the UI thread.

        As the Qt agent panel did: each ``WRITE_FILE`` block goes into its document (see
        ``EditorModel.apply_file_writes``) and is checked with ``py_compile`` and Ruff; an answer
        without one runs no check.

        Returns
        -------
        list of tuple
            ``(filename, content)`` of every write found.
        """
        from chisurf.plugins.core.code_editor.file_writes import parse_file_writes

        editor = self.editor_ref
        if editor is None or not hasattr(editor, "apply_file_writes"):
            return []
        writes = parse_file_writes(response)
        if not writes:
            return []  # nothing written, nothing checked (the answer stays the last message)
        editor.apply_file_writes(writes)
        self.history.add_message("system", "Applying generated code to the editor...")

        def check() -> None:
            from chisurf.plugins.core.code_editor.validation import validate_writes

            try:
                issues = validate_writes(writes, editor=editor)
            except Exception as error:  # the check failing is reported, not raised on a worker
                # bound now: ``error`` is unbound once the except block ends, so the
                # deferred lambda this replaced raised NameError instead of reporting
                self.event_queue.put(
                    functools.partial(
                        self.history.add_message, "error", f"Validation failed: {error}"
                    )
                )
                return
            if issues:
                total = sum(len(found) for _, found in issues)
                lines = [f"Validation found {total} issue(s):"] + [
                    f"- {name}:{d.get('line', '?')} {d.get('code', '')} {d.get('message', '')}"
                    for name, found in issues
                    for d in found
                ]
                text = "\n".join(lines)
            else:
                text = "All checks pass — code is clean."
            self.event_queue.put(lambda: self.history.add_message("system", text))

        threading.Thread(target=check, daemon=True).start()
        return writes

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
        """ACP ``fs/write_text_file``: an open tab of the file takes the text, left modified.

        The file on disk changes only when the user saves the agent's edit (the Qt editor also
        wrote the disk at once; the emtk editor keeps the agent's change reviewable). A file that
        is not open is written directly.
        """
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
                    # The numbers a user watches for (3 dataset(s), chi2r ...), else the raw result.
                    output=tool_highlight(payload)
                    or (str(payload.get("error")) if payload.get("error") else "")
                    or json.dumps(payload.get("result", ""), default=str),
                )
            )
        elif event == "agent.failed":
            self.event_queue.put(
                lambda: self.history.add_message("error", str(payload.get("error", "Agent failed")))
            )
        elif event == "skill.loaded":
            trigger = "matched" if payload.get("trigger") == "auto" else "requested"
            self.event_queue.put(
                lambda: self.history.add_message(
                    "system", f"📘 Skill {payload.get('skill')} ({trigger})"
                )
            )
        elif event == "agent.completed":
            stop_reason = payload.get("stop_reason", "answer")
            tools = payload.get("tools", [])
            lines = [] if stop_reason == "answer" else [f"⏹ Stopped: {stop_reason}"]
            if tools:
                lines.append(
                    f"— {payload.get('steps', 0)} step(s), {len(tools)} tool call(s): "
                    f"{', '.join(dict.fromkeys(tools))}"
                )
            if lines:
                self.event_queue.put(lambda: self.history.add_message("system", "\n".join(lines)))

    def _run_in_process_prompt(self, prompt: str) -> None:
        """Use the same persistent, Qt-free agent contract as the CLI (:meth:`agent_session_for`)."""
        try:
            session = self.agent_session_for(AgentMode(self.mode))
            if session is None:
                self.event_queue.put(self._handle_finished)
                return
            if self._closed:
                return
            result = session.ask(prompt)
            if result.error and not self._closed:
                self.event_queue.put(
                    functools.partial(self.history.add_message, "error", str(result.error))
                )
            self._on_acp_prompt_finished("", result.stop_reason)
        except Exception as err:
            if not self._closed:
                self.event_queue.put(
                    functools.partial(self.history.add_message, "error", f"Agent error: {err}")
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
        acp_client = self.acp_client
        active_acp = acp_client is not None and acp_client.is_running and was_generating
        if acp_client is not None and active_acp:
            acp_client.cancel()
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


class WikiWindow:
    """The LLM Wiki the assistant reads: search the pages, read one, feed the codebase in.

    The emtk twin of the Qt agent panel's *Wiki* dialog (``code_editor/wiki.py`` holds the logic).
    """

    def __init__(self) -> None:
        from emtk.dialog_window import DialogWindow

        self.window = DialogWindow("LLM Wiki", size=(700.0, 500.0), key="code_editor_wiki")
        self.window.open = False
        self.index: WikiIndex | None = None
        self.search = ""
        self.selected = ""
        self.page_text = ""
        self.status = ""
        self.populating = False
        self._events: queue.Queue = queue.Queue()

    def show(self) -> None:
        from chisurf.plugins.core.code_editor.wiki import WikiIndex

        if self.index is None:
            self.index = WikiIndex()
            self.page_text = self.index.index_text or self.index.message
        self.window.show()

    def refresh(self) -> None:
        if self.index is not None:
            self.index.reload()
            self.page_text = self.index.index_text or self.index.message

    def select(self, entry: str) -> None:
        self.selected = entry
        if self.index is not None:
            self.page_text = self.index.read(entry)

    def populate(self) -> None:
        """Feed the codebase into the wiki on a worker; progress shows under the page."""
        if self.populating:
            return
        from chisurf.plugins.core.code_editor import wiki

        self.populating = True
        self.status = "Populating LLM Wiki from codebase..."

        def work() -> None:
            try:
                count = wiki.populate_from_codebase(progress=lambda text: self._events.put(text))
                self._events.put(f"LLM Wiki populated with {count} codebase files.")
            except Exception as error:  # a failure is said, not raised on the worker
                self._events.put(f"Failed to populate wiki: {error}")
            self._events.put(None)

        threading.Thread(target=work, daemon=True).start()

    def draw(self, frame: tuple[float, float, float, float]) -> None:
        while not self._events.empty():
            event = self._events.get_nowait()
            if event is None:
                self.populating = False
                self.refresh()
            else:
                self.status = event
        if not self.window.open:
            return
        closed = self.window.begin(frame) == "close"
        box = self.window.content_box
        im.set_next_item_width(max(120.0, box[2] - 230.0))
        _, self.search = im.input_text("##wiki_search", self.search, hint=tr("Search wiki..."))
        im.set_item_tooltip(tr("Show only the pages whose section or title contains this text"))
        im.same_line()
        if im.small_button(tr("🔄 Refresh") + "##wiki_refresh"):
            self.refresh()
        im.set_item_tooltip(tr("Re-read the wiki's index and pages"))
        im.same_line()
        im.begin_disabled(self.populating)
        if im.small_button(tr("📡 Populate Wiki") + "##wiki_populate"):
            self.populate()
        im.set_item_tooltip(tr("Feed the current codebase into the LLM Wiki"))
        im.end_disabled()
        x, y = im.get_cursor_screen_pos()
        list_h = max(60.0, (box[1] + box[3] - y) * 0.35)
        im.begin_child((x, y, box[2], list_h), child_id="wiki_pages")
        for entry in self.index.entries(self.search) if self.index is not None else []:
            if im.selectable(f"{entry}##wiki_{entry}", entry == self.selected):
                self.select(entry)
            im.set_item_tooltip(tr("Show this page"))
        im.end_child()
        x, y = im.get_cursor_screen_pos()
        status_h = 22.0 if self.status else 0.0
        im.begin_child(
            (x, y, box[2], max(40.0, box[1] + box[3] - y - status_h)), child_id="wiki_page"
        )
        im.text_wrapped(self.page_text)
        im.end_child()
        if self.status:
            im.text_disabled(self.status)
        self.window.end()
        if closed:
            self.window.hide()


class ChatGui:
    """Immediate-mode rendering and interaction for the chat assistant."""

    def __init__(self, model: ChatModel | None = None, editor_ref: Any = None) -> None:
        self.model = model or ChatModel(editor_ref=editor_ref)
        self.provider_settings: AISettingsApp | None = None
        self.provider_settings_open = False
        self.wiki = WikiWindow()

    def use_example(self, prompt: str) -> None:
        """Put an example prompt in the input box for the user to edit or send (Things to ask)."""
        self.model.input_text = prompt.strip()

    def draw_provider_settings(self) -> None:
        if not self.provider_settings_open or self.provider_settings is None:
            return
        im.set_next_window_size((700, 660), im.Cond.FIRST_USE_EVER)
        if im.begin("Provider settings##chat_provider_settings"):
            if im.button(tr("Use settings and close")):
                if self.model.use_provider_settings(self.provider_settings.model):
                    self.provider_settings_open = False
            im.set_item_tooltip(tr("Use this provider configuration for subsequent chat turns"))
            im.same_line()
            if im.button(tr("Close provider settings")):
                self.provider_settings_open = False
            im.set_item_tooltip(
                tr("Close the provider form; field edits use the shared provider store")
            )
            im.begin_child(
                (*im.get_cursor_screen_pos(), *im.get_content_region_avail()),
                child_id="chat_provider_fields",
            )
            self.provider_settings.draw_inline()
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

        # An empty transcript shows the mode's greeting: what the assistant is for.
        shown = (
            self.model.history
            if self.model.history.messages
            else [ChatMessage(role="system", content=self.model.greeting)]
        )
        draw_chat_transcript(
            shown,
            size=(width, transcript_h),
            on_insert_code=self._on_insert_code,
            on_replace_code=self._on_replace_code,
            on_link=self._open_link,
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

    def draw_overlays(self, width: float, height: float) -> None:
        """Windows drawn over the whole frame, outside the pane the chat sits in (the Wiki)."""
        self.wiki.draw((0.0, 0.0, width, height))

    def _draw_toolbar(self, width: float) -> None:
        avail_w = im.get_content_region_avail()[0]
        combo_w = max(70.0, (avail_w - 34.0) / 2.0)  # room for the status dot

        # Provider and mode belong to the turn that is currently running.
        im.begin_disabled(self.model.is_generating)
        # Provider selector
        im.set_next_item_width(combo_w)
        current_p_idx = (
            PROVIDERS.index(self.model.provider) if self.model.provider in PROVIDERS else 0
        )
        p_labels = [PROVIDER_LABELS.get(p, p) for p in PROVIDERS]
        changed_p, new_p_idx = im.combo("##p_select", current_p_idx, p_labels)
        im.set_item_tooltip(tr("Choose the assistant provider"))
        if changed_p:
            self.model.provider = PROVIDERS[new_p_idx]
        ready, why = self.model.provider_status()
        im.same_line()
        im.text_colored((152, 195, 121, 255) if ready else (224, 108, 117, 255), "●")
        im.set_item_tooltip(why)

        im.same_line()

        # Mode selector
        im.set_next_item_width(combo_w)
        current_m_idx = MODES.index(self.model.mode) if self.model.mode in MODES else 0
        m_labels = [MODE_LABELS.get(m, m) for m in MODES]
        changed_m, new_m_idx = im.combo("##m_select", current_m_idx, m_labels)
        im.set_item_tooltip(tr("Choose which tools the assistant may use"))
        if changed_m:
            self.model.set_mode(MODES[new_m_idx])

        if im.small_button("Provider settings…"):
            if self.provider_settings is None:
                # (was AISettingsGui, which no longer exists: this button raised ImportError)
                from chisurf.plugins.ai_settings.gui.app import AISettingsApp

                self.provider_settings = AISettingsApp()
            self.provider_settings.select_provider(self.model.provider)
            self.provider_settings_open = True
        im.set_item_tooltip(
            tr("Configure API endpoint, masked credential, models, sampling or the ACP command")
        )
        im.end_disabled()
        if im.small_button(tr("💡 Things to ask") + "##chat_examples"):
            im.open_popup("chat_examples")
        im.set_item_tooltip(
            tr("Example prompts shipped with ChiSurf and tested against a real model")
        )
        if im.begin_popup("chat_examples"):
            from chisurf.core.agent.example_prompts import starter_prompts

            examples = starter_prompts(limit=10)
            if not examples:
                im.menu_item(tr("(no examples available)"), enabled=False)
            for index, example in enumerate(examples):
                if im.menu_item(f"{example.title}##example_{index}"):
                    self.use_example(example.prompt)
                im.set_item_tooltip(" ".join(example.explanation.split()))
            im.end_popup()
        im.same_line()
        if im.small_button(tr("📚 Wiki") + "##chat_wiki"):
            self.wiki.show()
        im.set_item_tooltip(
            tr("Browse the LLM Wiki the assistant reads, or feed the codebase into it")
        )
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

    def _open_link(self, target: str) -> None:
        """Route an answer link: docs pages to the documentation browser, URLs to the browser."""
        from chisurf.emtk.doc_links import open_link

        open_link(target)

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
        vp = im.get_main_viewport()
        self.chat_gui.draw_overlays(float(vp.size[0] or 440.0), float(vp.size[1] or 680.0))


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
