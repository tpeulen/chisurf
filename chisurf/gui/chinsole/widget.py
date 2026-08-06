"""The console widget: view, engine, and the API the rest of ChiSurf calls.

One widget serves the three consoles ChiSurf used to have separately -- the
main-window dock, chimol's command bar and the code editor's output panel --
because the only structural difference between them is where input lives. That
is a :class:`ConsoleRole`, not a class hierarchy.
"""

from __future__ import annotations

import os

import contextlib
import dataclasses
import enum
import pathlib
import typing

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.core.console import dispatch
from chisurf.core.console.history import HistoryManager
from chisurf.core.console.shell import Shell
from chisurf.gui.chinsole import settings as console_settings
from chisurf.gui.chinsole.bridge import OutputPump
from chisurf.gui.chinsole.completion_popup import CallTipWidget, CompletionPopup
from chisurf.gui.chinsole.pager import PagerWidget
from chisurf.gui.chinsole.theme import ConsoleTheme, resolve_theme, theme_from_settings
from chisurf.gui.chinsole.view import ConsoleView

__all__ = ["Chinsole", "ConsoleConfig", "ConsoleRole", "CommandDispatcher"]


class ConsoleRole(enum.Enum):
    """How a console presents itself.

    Attributes
    ----------
    INTERACTIVE
        Prompt inline in the scrollback; the main-window console.
    COMMAND
        A separate one-line input under the output; chimol's command bar.
    OUTPUT
        Read-only; the code editor's output panel.
    """

    INTERACTIVE = "interactive"
    COMMAND = "command"
    OUTPUT = "output"


@dataclasses.dataclass
class ConsoleConfig:
    """How to build a console.

    Attributes
    ----------
    role : ConsoleRole
    namespace : dict or None
        Seeded into the shell.
    banner : str or None
    history_path : pathlib.Path or bool or None
        ``False`` disables persistence.
    session_log : pathlib.Path or None
        Every executed cell is appended here. This is ChiSurf's macro
        provenance trail and is deliberately separate from the input history.
    init_source : str or None
    theme : str or ConsoleTheme or None
    prompt, continuation : str
    """

    role: ConsoleRole = ConsoleRole.INTERACTIVE
    namespace: dict | None = None
    banner: str | None = None
    history_path: pathlib.Path | bool | None = None
    session_log: pathlib.Path | None = None
    init_source: str | None = None
    theme: str | ConsoleTheme | None = None
    prompt: str = "In [{n}]: "
    continuation: str = "     ...: "


class CommandDispatcher(typing.Protocol):
    """A non-Python command language a console can also accept.

    chimol's ``cmd`` grammar arrives through this rather than by subclassing,
    so the precedence rule lives in chinsole and cannot drift between the Qt
    console and the terminal REPL.
    """

    def names(self) -> typing.Sequence[str]:
        """Return the command names, for completion."""

    def completions(self, line: str, cursor: int) -> typing.Sequence[str]:
        """Return completions for a partially typed command."""

    def handles(self, line: str) -> bool:
        """Return whether *line* looks like one of these commands."""

    def execute(self, line: str) -> None:
        """Run *line*."""


class Chinsole(QtWidgets.QWidget):
    """ChiSurf's Python console.

    Parameters
    ----------
    config : ConsoleConfig, optional
    parent : QtWidgets.QWidget, optional
    """

    #: Emitted with each executed source, for recorders and logs.
    codeExecuted = QtCore.Signal(str)
    #: Emitted with output as it is appended.
    outputAppended = QtCore.Signal(str)
    #: Emitted with the line entered in ``COMMAND`` role.
    commandEntered = QtCore.Signal(str)
    #: Emitted when a cell starts and finishes.
    executionStateChanged = QtCore.Signal(bool)
    #: Emitted when the user asks to close the console.
    exit_requested = QtCore.Signal()

    # Kept so a call from a worker thread can be marshalled to this widget.
    _codeRequested = QtCore.Signal(str)
    _logRequested = QtCore.Signal(str)

    def __init__(
            self,
            config: ConsoleConfig | None = None,
            parent: QtWidgets.QWidget | None = None,
            **legacy,
    ) -> None:
        super().__init__(parent)
        self.config = config or ConsoleConfig()
        self._settings = console_settings.console_settings()
        self.theme = resolve_theme(self.config.theme) if self.config.theme else theme_from_settings()

        self.setObjectName("chinsole")
        self.view = ConsoleView(self, self.theme)
        # Named so the guided tour can point at them: it resolves a target by
        # objectName, and an unnamed widget is invisible to it.
        self.view.setObjectName("chinsole_view")
        # Only the inline role draws prompts. COMMAND types into its own
        # line edit, so an "In [n]:" in the output pane above it is a
        # prompt for something that is not entered there.
        self.view.shows_prompt = self.config.role is ConsoleRole.INTERACTIVE
        self.view._prompt_text = self.config.prompt
        self.view._continuation_text = self.config.continuation
        self.view.set_max_blocks(int(self._settings["max_blocks"]))

        self.input_line: QtWidgets.QLineEdit | None = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.paging = str(self._settings["paging"])
        self.pager = PagerWidget(self, self.theme)
        self.pager.setObjectName("chinsole_pager")
        self.pager.closed.connect(self._focus_input)
        if self.paging == "hsplit":
            self._splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        else:
            self._splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self._splitter.addWidget(self.view)
        self._splitter.addWidget(self.pager)
        layout.addWidget(self._splitter)

        if self.config.role is ConsoleRole.COMMAND:
            self.input_line = QtWidgets.QLineEdit(self)
            self.input_line.setObjectName("chinsole_input")
            self.input_line.setPlaceholderText("Command line")
            layout.addWidget(self.input_line)
            self.input_line.returnPressed.connect(self._submit_command_line)
            self.input_line.installEventFilter(self)

        font = console_settings.editor_font(self._settings)
        self.set_editor_font(font)

        self.pump = OutputPump(
            self._write_output,
            interval_ms=int(self._settings["flush_interval_ms"]),
            max_per_cell=int(self._settings["max_output_chars"]),
            parent=self,
        )
        self.pump.truncated.connect(self._report_truncation)

        self.completion_popup = CompletionPopup(self)
        self.calltip = CallTipWidget(self)
        self.completion_popup.accepted.connect(self._insert_completion)
        self.view.completion_popup = self.completion_popup

        self.dispatcher: CommandDispatcher | None = None
        self.recording = False
        self._macro = ""
        self.history_widget: QtWidgets.QPlainTextEdit | None = None
        self.session_file = self.config.session_log or self._default_session_file()
        self._history_index: int | None = None
        self._history_stash = ""
        self._completion_result = None
        self._pending_input = None

        self.shell = Shell(
            user_ns=dict(self.config.namespace or {}),
            write=self.pump.write,
            display=self._on_display,
            read_input=self.view.read_input if self.config.role is not ConsoleRole.OUTPUT else None,
            clear=self.view.clear_screen,
            edit_file=self._edit_file,
            history=HistoryManager(
                self.config.history_path
                if self.config.history_path is not None
                else None,
                max_entries=int(self._settings["history_length"]),
            ),
        )

        self._connect_view()
        self._codeRequested.connect(self._execute_from_signal, QtCore.Qt.QueuedConnection)
        self._logRequested.connect(self._log_code, QtCore.Qt.QueuedConnection)

        if self.config.role is not ConsoleRole.OUTPUT:
            if self.config.banner is None and self._settings["banner"]:
                self.view.append_output(self._default_banner())
            elif self.config.banner:
                self.view.append_output(self.config.banner)
        if self.view.shows_prompt:
            self.view.show_prompt(self.shell.execution_count, newline=False)

        if self.config.role is ConsoleRole.INTERACTIVE:
            self._add_help_buttons()

        if self.config.init_source:
            self.execute(self.config.init_source, echo=False)

    def _add_help_buttons(self) -> None:
        """Add the ``?`` and **Guide** buttons above the prompt.

        A console is the one panel in the window with a blinking cursor and no
        instructions, so the tour matters here more than on a form: `?` explains
        what something *means*, and the tour is the only thing that says what to
        type first.
        """
        try:
            from chisurf.gui.widgets.tools.help_guide import attach_help_and_guide
        except Exception:
            return

        # A container widget rather than a bare layout, so the strip can carry
        # the console's background. Left as a layout it took Qt's default light
        # grey and sat as a bright band above a dark console.
        self._help_bar = QtWidgets.QWidget(self)
        self._help_bar.setObjectName("chinsole_help_bar")
        self._help_bar.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        bar = QtWidgets.QHBoxLayout(self._help_bar)
        bar.setContentsMargins(2, 0, 2, 0)
        bar.setSpacing(2)
        bar.addStretch()
        try:
            attach_help_and_guide(
                self, bar, title="ChiSurf console", owner=self,
            )
        except Exception:
            self._help_bar.deleteLater()
            self._help_bar = None
            return
        self._style_help_bar()
        self.layout().insertWidget(0, self._help_bar)

    def _style_help_bar(self) -> None:
        """Paint the help strip in the console's colours."""
        bar = getattr(self, "_help_bar", None)
        if bar is None:
            return
        bar.setStyleSheet(
            f"QWidget#chinsole_help_bar {{ background-color: {self.theme.background}; }}"
            f"QToolButton, QPushButton {{ border: none; background: transparent;"
            f" color: {self.theme.prompt_continuation}; }}"
            f"QToolButton:hover, QPushButton:hover {{ color: {self.theme.foreground}; }}"
        )

    # ------------------------------------------------------------------
    # construction helpers
    # ------------------------------------------------------------------

    def _connect_view(self) -> None:
        """Wire the view's requests to this widget."""
        self.view.executeRequested.connect(self._on_execute_requested)
        self.view.completeRequested.connect(self.show_completions)
        self.view.calltipRequested.connect(self.show_calltip)
        self.view.historyRequested.connect(self.walk_history)
        self.view.interruptRequested.connect(self.interrupt)
        self.view.exitRequested.connect(self.exit_requested.emit)
        self.view.searchRequested.connect(self.search_history)

    @staticmethod
    def _default_session_file() -> pathlib.Path | None:
        """Return ChiSurf's per-session macro log path.

        Returns
        -------
        pathlib.Path or None
        """
        try:
            import chisurf.core.settings

            return pathlib.Path(chisurf.core.settings.session_file)
        except Exception:
            return None

    def _default_banner(self) -> str:
        """Return the startup banner.

        Returns
        -------
        str
        """
        import sys

        try:
            import chisurf

            version = chisurf.__version__
        except Exception:
            version = "?"
        python = ".".join(str(part) for part in sys.version_info[:3])
        return (
            f"ChiSurf {version} console  |  Python {python}  |  "
            f"%quickref for help, obj? for details\n"
        )

    # ------------------------------------------------------------------
    # output
    # ------------------------------------------------------------------

    def _write_output(self, name: str, text: str) -> None:
        """Append pumped output to the view.

        Parameters
        ----------
        name : str
        text : str
        """
        self.view.append_output(text, kind=name)
        self.outputAppended.emit(text)

    def _report_truncation(self, dropped: int) -> None:
        """Tell the user output was discarded.

        Parameters
        ----------
        dropped : int
        """
        self.view.append_output(
            f"\n[output truncated: {dropped:,} further characters suppressed; "
            f"raise gui.console.max_output_chars to see more]\n",
            kind="stderr",
        )

    def _on_display(
            self,
            data: dict,
            metadata: dict,
            kind: str,
            execution_count: int | None,
    ) -> None:
        """Render a MIME bundle in the richest form the view supports.

        Parameters
        ----------
        data : dict
        metadata : dict
        kind : str
        execution_count : int or None
        """
        self.pump.flush_now()

        if kind == "page" and self.paging != "none" and self.config.role is not ConsoleRole.OUTPUT:
            text = data.get("text/plain")
            if text is not None:
                self.pager.show_text(text, title=metadata.get("title", ""))
                return

        if not self._settings["images"]:
            text = data.get("text/plain")
            if text:
                self.view.append_output(text + "\n")
            return

        if "image/png" in data:
            self.view.append_image(_as_bytes(data["image/png"]), "png", metadata.get("image/png"))
            return
        if "image/jpeg" in data:
            self.view.append_image(_as_bytes(data["image/jpeg"]), "jpeg")
            return
        if "image/svg+xml" in data:
            self.view.append_svg(data["image/svg+xml"])
            return
        if "text/html" in data:
            self.view.append_html(data["text/html"])
            return

        text = data.get("text/plain")
        if text is None:
            return
        if kind == "execute_result" and execution_count is not None:
            prompt = f"Out[{execution_count}]: "
            self.view.append_output(prompt + text + "\n")
        else:
            self.view.append_output(text + "\n")

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------

    def _on_execute_requested(self, source: str) -> None:
        """Decide whether Enter runs the cell or continues it.

        Parameters
        ----------
        source : str
        """
        if self.view._reading_input:
            self.view._finish_input()
            return

        status, indent = self.shell.check_complete(source)
        if status == "incomplete":
            self.view.continue_input(indent)
            return
        self.execute(source)

    def execute(self, source: str, *, echo: bool = True, hidden: bool = False):
        """Run *source*.

        Parameters
        ----------
        source : str
        echo : bool, optional
            Unused for the inline prompt, where the text is already visible;
            kept because callers pass it.
        hidden : bool, optional
            Do not record or display.

        Returns
        -------
        ExecutionResult
        """
        if self.dispatcher is not None and self._is_command(source):
            self._run_dispatcher(source)
            return None

        self.view.set_executing(True)
        self.executionStateChanged.emit(True)
        self.pump.begin_cell()
        # Separates the typed line from its output -- but only where the
        # input *is* the line above. A COMMAND console echoes "> line"
        # itself, so a second newline just doubles the panel's height.
        if self.view.shows_prompt:
            self.view.append_output("\n")

        try:
            result = self.shell.run_cell(source, store_history=not hidden, silent=hidden)
        finally:
            self.pump.end_cell()
            self.view.set_executing(False)
            self.executionStateChanged.emit(False)

        if not hidden and source.strip():
            self._log_code(source)
            self.codeExecuted.emit(source)

        if self.shell.exit_requested:
            self.exit_requested.emit()

        self._history_index = None
        if self.view.shows_prompt:
            self.view.show_prompt(self.shell.execution_count)
        self._apply_next_input()
        return result

    def _apply_next_input(self) -> None:
        """Prefill the prompt if a magic asked for it (``%load``, ``%recall``)."""
        pending = getattr(self.shell, "_next_input", None)
        if not pending:
            return
        self.shell._next_input = None
        text, _replace = pending
        self.view.set_input_buffer(text)

    def _is_command(self, line: str) -> bool:
        """Return whether *line* belongs to the dispatcher rather than Python.

        Parameters
        ----------
        line : str

        Returns
        -------
        bool

        Notes
        -----
        The rule itself lives in :mod:`chisurf.core.console.dispatch`, shared
        with the standalone REPLs that face the same question -- it had been
        written out once per prompt, and the copies had drifted.
        """
        return dispatch.is_command(
            line,
            has_dispatcher=self.dispatcher is not None,
            namespace=getattr(self.shell, "user_ns", {}) or {},
        )

    def _run_dispatcher(self, line: str) -> None:
        """Run *line* through the command dispatcher.

        Parameters
        ----------
        line : str
        """
        # Separates the typed line from its output -- but only where the
        # input *is* the line above. A COMMAND console echoes "> line"
        # itself, so a second newline just doubles the panel's height.
        if self.view.shows_prompt:
            self.view.append_output("\n")
        try:
            self.dispatcher.execute(line)
        except Exception as exc:  # noqa: BLE001
            self.view.append_output(f"{exc}\n", kind="stderr")
        self.commandEntered.emit(line)
        self._log_code(line)
        if self.view.shows_prompt:
            self.view.show_prompt(self.shell.execution_count)

    def interrupt(self) -> None:
        """Ask a running cell to stop."""
        self.pump.drop_pending()
        interrupter = getattr(self, "_interrupter", None)
        if interrupter is not None:
            interrupter.request_interrupt()

    # ------------------------------------------------------------------
    # completion, calltips, history
    # ------------------------------------------------------------------

    def _cursor_global_position(self) -> QtCore.QPoint:
        """Return the caret's position on screen.

        Returns
        -------
        QtCore.QPoint
        """
        rect = self.view.cursorRect()
        return self.view.viewport().mapToGlobal(rect.bottomLeft())

    def show_completions(self) -> None:
        """Offer completions for what is typed."""
        if self._settings["completion"] == "none":
            return
        line, cursor = self._current_line_and_cursor()
        result = self._dispatcher_completions(line, cursor) or self.shell.complete(
            line, cursor
        )
        if not result:
            return

        if result.common_prefix:
            typed = line[result.start:cursor]
            if len(result.common_prefix) > len(typed):
                self._replace_span(result.start, cursor, result.common_prefix)
                if len(result.matches) == 1:
                    return
        if len(result.matches) == 1:
            self._replace_span(result.start, cursor, result.matches[0])
            return

        self._completion_result = result
        self.completion_popup.show_for(
            result, self._cursor_global_position(), self.view.font(), self.theme
        )

    def _dispatcher_completions(self, line: str, cursor: int):
        """Completions from the command dispatcher, or ``None``.

        Asked **before** Python, because on a command prompt what is being typed
        is usually a command. Nothing consulted the dispatcher at all before
        this: Tab went straight to the Python completer, which knows nothing of
        `split_chains` or `orient` and returned no matches -- so completion
        appeared simply not to work, while the dispatcher had the answer all
        along.

        Returning ``None`` rather than an empty result is what lets Python have
        the line when the dispatcher has nothing to say -- typing `np.arr<Tab>`
        must still complete.

        Parameters
        ----------
        line : str
        cursor : int

        Returns
        -------
        CompletionResult or None
        """
        dispatcher = self.dispatcher
        if dispatcher is None:
            return None
        try:
            matches = list(dispatcher.completions(line, cursor))
        except Exception:
            return None
        if not matches:
            return None

        from chisurf.core.console.completer import CompletionResult

        # The span the match replaces: back to the last separator, so completing
        # the *second* word of `color re` replaces `re` and not the whole line.
        head = line[:cursor]
        start = cursor
        while start > 0 and not head[start - 1].isspace() and head[start - 1] != ",":
            start -= 1
        prefix = os.path.commonprefix(matches) if len(matches) > 1 else matches[0]
        return CompletionResult(
            matches=sorted(matches),
            start=start,
            end=cursor,
            common_prefix=prefix,
            kind="command",
        )

    def _insert_completion(self, match: str) -> None:
        """Insert a chosen completion.

        Parameters
        ----------
        match : str
        """
        result = self._completion_result
        if result is None:
            return
        _line, cursor = self._current_line_and_cursor()
        self._replace_span(result.start, cursor, match)

    def _current_line_and_cursor(self) -> tuple[str, int]:
        """Return the current input line and the cursor offset in it.

        Returns
        -------
        tuple
        """
        if self.input_line is not None:
            return self.input_line.text(), self.input_line.cursorPosition()
        cursor = self.view.textCursor()
        block = cursor.block()
        data = block.userData()
        offset = getattr(data, "prompt_len", 0)
        return block.text()[offset:], max(0, cursor.positionInBlock() - offset)

    def _replace_span(self, start: int, end: int, text: str) -> None:
        """Replace the current line between *start* and *end* with *text*.

        Parameters
        ----------
        start, end : int
        text : str
        """
        if self.input_line is not None:
            current = self.input_line.text()
            self.input_line.setText(current[:start] + text + current[end:])
            self.input_line.setCursorPosition(start + len(text))
            return
        cursor = self.view.textCursor()
        block = cursor.block()
        data = block.userData()
        offset = getattr(data, "prompt_len", 0)
        cursor.beginEditBlock()
        cursor.setPosition(block.position() + offset + start)
        cursor.setPosition(block.position() + offset + end, QtGui.QTextCursor.KeepAnchor)
        cursor.insertText(text)
        cursor.endEditBlock()
        self.view.setTextCursor(cursor)

    def show_calltip(self) -> None:
        """Show the signature of the call the cursor is inside."""
        if not self._settings["calltips"]:
            return
        from chisurf.core.console.introspect import calltip

        line, cursor = self._current_line_and_cursor()
        tip = calltip(line, cursor, self.shell.user_ns)
        if tip is None:
            self.calltip.hide()
            return
        self.calltip.show_tip(
            tip, self._cursor_global_position(), self.view.font(), self.theme
        )

    def walk_history(self, direction: int) -> None:
        """Move through the input history.

        Parameters
        ----------
        direction : int
            ``-1`` for older, ``+1`` for newer.
        """
        entries = self.shell.history.entries
        if not entries:
            return
        current = self._current_text()
        if self._history_index is None:
            self._history_stash = current
            self._history_prefix = current
            self._history_index = len(entries)

        matches = [
            index for index, entry in enumerate(entries)
            if entry.startswith(self._history_prefix)
        ]
        if not matches:
            matches = list(range(len(entries)))

        position = None
        if direction < 0:
            earlier = [i for i in matches if i < self._history_index]
            position = earlier[-1] if earlier else None
        else:
            later = [i for i in matches if i > self._history_index]
            position = later[0] if later else None

        if position is None:
            if direction > 0:
                self._history_index = len(entries)
                self._set_text(self._history_stash)
            return
        self._history_index = position
        self._set_text(entries[position])

    def search_history(self) -> None:
        """Reverse-search the history for what is typed."""
        needle = self._current_text().strip()
        matches = self.shell.history.search_substring(needle)
        if not matches:
            self.view.append_output(f"\n(no history match for {needle!r})\n", kind="stderr")
            self.view.show_prompt(self.shell.execution_count)
            return
        self._set_text(matches[0])

    def _current_text(self) -> str:
        """Return the current input text.

        Returns
        -------
        str
        """
        return self.input_line.text() if self.input_line else self.view.input_buffer()

    def _set_text(self, text: str) -> None:
        """Replace the current input text.

        Parameters
        ----------
        text : str
        """
        if self.input_line is not None:
            self.input_line.setText(text)
        else:
            self.view.set_input_buffer(text)

    # ------------------------------------------------------------------
    # COMMAND role
    # ------------------------------------------------------------------

    def _submit_command_line(self) -> None:
        """Run whatever is in the one-line input."""
        text = self.input_line.text()
        if not text.strip():
            return
        self.input_line.clear()
        self.view.append_output(f"> {text}\n")
        self.execute(text)

    def eventFilter(self, obj, event):  # noqa: N802 - Qt override
        """Route keys from the one-line input.

        Parameters
        ----------
        obj : QtCore.QObject
        event : QtCore.QEvent

        Returns
        -------
        bool
        """
        if obj is self.input_line and event.type() == QtCore.QEvent.KeyPress:
            if self.completion_popup.handle_key(event):
                return True
            key = event.key()
            if key == QtCore.Qt.Key_Tab:
                self.show_completions()
                return True
            if key == QtCore.Qt.Key_Up:
                self.walk_history(-1)
                return True
            if key == QtCore.Qt.Key_Down:
                self.walk_history(+1)
                return True
        return super().eventFilter(obj, event)

    def prefill(self, line: str, placeholder: str = "") -> None:
        """Put *line* in the input and select *placeholder* within it.

        Parameters
        ----------
        line : str
        placeholder : str, optional
        """
        self._set_text(line)
        if not placeholder:
            return
        index = line.find(placeholder)
        if index < 0:
            return
        if self.input_line is not None:
            self.input_line.setSelection(index, len(placeholder))
        self._focus_input()

    def _focus_input(self) -> None:
        """Give keyboard focus to whichever widget takes input."""
        (self.input_line or self.view).setFocus()

    def set_dispatcher(self, dispatcher: CommandDispatcher | None) -> None:
        """Attach a command language.

        Parameters
        ----------
        dispatcher : CommandDispatcher or None
        """
        self.dispatcher = dispatcher

    # ------------------------------------------------------------------
    # recording, logging and the legacy API
    # ------------------------------------------------------------------

    def push(self, variables: typing.Mapping[str, typing.Any]) -> None:
        """Add *variables* to the console namespace.

        Parameters
        ----------
        variables : mapping
        """
        self.shell.push(variables)

    #: Historic spelling used across the ChiSurf GUI.
    pushVariables = push

    def append_output(self, text: str, *, kind: str = "stdout") -> None:
        """Write *text* to the console.

        Parameters
        ----------
        text : str
        kind : str, optional
        """
        self.view.append_output(text, kind=kind)
        self.outputAppended.emit(text)

    def append_message(self, text: str) -> None:
        """Write an informational message.

        Parameters
        ----------
        text : str
        """
        self.append_output(text if text.endswith("\n") else text + "\n")

    def append_error(self, text: str) -> None:
        """Write an error message.

        Parameters
        ----------
        text : str
        """
        self.append_output(
            text if text.endswith("\n") else text + "\n", kind="stderr"
        )

    def printText(self, text: str) -> None:  # noqa: N802 - legacy spelling
        """Write *text* to the console.

        Parameters
        ----------
        text : str
        """
        self.append_output(text)

    def clear(self) -> None:
        """Clear the console."""
        self.view.clear_screen()

    def clearTerminal(self) -> None:  # noqa: N802 - legacy spelling
        """Clear the console."""
        self.view.clear_screen()

    def set_editor_font(self, font: QtGui.QFont) -> None:
        """Apply *font* to the console.

        Parameters
        ----------
        font : QtGui.QFont
        """
        self.view.setFont(font)
        self.view.setTabStopDistance(
            4 * QtGui.QFontMetricsF(font).horizontalAdvance(" ")
        )
        if self.input_line is not None:
            self.input_line.setFont(font)
        pager = getattr(self, "pager", None)
        if pager is not None:
            pager.set_font(font)

    def set_style(self, name: str | ConsoleTheme) -> None:
        """Change the colour theme.

        Parameters
        ----------
        name : str or ConsoleTheme
            Accepts chinsole's names and qtconsole's legacy ones.
        """
        self.theme = resolve_theme(name)
        self.view.apply_theme(self.theme)
        self.pager.apply_theme(self.theme)
        self._style_help_bar()

    def set_default_style(self, colors: str = "lightbg") -> None:
        """Change the colour theme, qtconsole's spelling.

        Parameters
        ----------
        colors : str, optional
        """
        self.set_style(colors)

    def set_history_widget(self, widget) -> None:
        """Mirror executed input into *widget*.

        Parameters
        ----------
        widget : QtWidgets.QPlainTextEdit or None
        """
        self.history_widget = widget

    def start_recording(self) -> None:
        """Begin collecting executed code into a macro."""
        self._macro = ""
        self.recording = True

    def stop_recording(self) -> None:
        """Stop collecting."""
        self.recording = False

    @property
    def macro(self) -> str:
        """str: The code recorded so far."""
        return self._macro

    def save_macro(self, filename: str | None = None) -> str | None:
        """Write the recorded macro to a file.

        Parameters
        ----------
        filename : str, optional
            A save dialog is shown when omitted.

        Returns
        -------
        str or None
            The path written, or ``None`` if cancelled.
        """
        self.stop_recording()
        if filename is None:
            import chisurf.gui.widgets

            filename = chisurf.gui.widgets.save_file(
                "Python macros", file_type="Python file (*.cm.py)"
            )
        if not filename:
            return None
        import chisurf.core.fio as io

        with io.zipped.open_maybe_zipped(filename=filename, mode="w") as handle:
            handle.write(self._macro)
        return filename

    def run_macro(self, filename: str | None = None) -> None:
        """Run a Python file in the console.

        Parameters
        ----------
        filename : str, optional
            A file dialog is shown when omitted.
        """
        self.run_file(filename)

    def run_file(self, path: str | pathlib.Path | None = None) -> None:
        """Run a Python file in the console's namespace.

        Replaces both ``run_macro`` and the ``%run -i`` string the code editor
        used to send, so there is one way to do it.

        Parameters
        ----------
        path : str or pathlib.Path, optional
        """
        if path is None:
            import chisurf.gui.widgets

            path = chisurf.gui.widgets.get_filename(
                "Python macros", file_type="Python file (*.py)"
            )
        if not path:
            return
        self.execute(f"%run -i {str(pathlib.Path(path).as_posix())!r}")

    def _log_code(self, source: str) -> None:
        """Record *source* to the session log, macro and history widget.

        Parameters
        ----------
        source : str
        """
        text = source if source.endswith("\n") else source + "\n"
        if self.session_file is not None:
            with contextlib.suppress(OSError):
                with open(self.session_file, "a+", encoding="utf-8", errors="ignore") as handle:
                    handle.write(text)
        if self.recording:
            self._macro += text
        if isinstance(self.history_widget, QtWidgets.QPlainTextEdit):
            self.history_widget.insertPlainText(text)

    # ------------------------------------------------------------------
    # thread-safe entry points
    # ------------------------------------------------------------------

    @QtCore.Slot(str)
    def _execute_from_signal(self, code: str) -> None:
        """Execute *code*; always runs on this widget's thread.

        Parameters
        ----------
        code : str
        """
        with contextlib.suppress(Exception):
            self.execute(code)

    def execute_threadsafe(self, code: str | None = None):
        """Execute *code* from any thread.

        ``chisurf.run(...)`` is called from worker threads, and a queued signal
        is what gets the work onto the GUI thread where the namespace and every
        Qt object it touches live.

        Parameters
        ----------
        code : str, optional

        Returns
        -------
        ExecutionResult or None
        """
        if code is None:
            return None
        code = str(code)
        if QtCore.QThread.currentThread() is self.thread():
            return self.execute(code)
        self._codeRequested.emit(code)
        return None

    #: Historic spelling used by ``chisurf.run``.
    execute_on_gui_thread = execute_threadsafe

    def log_threadsafe(self, code: str | None = None) -> None:
        """Record *code* without executing it, from any thread.

        Parameters
        ----------
        code : str, optional
        """
        if not code:
            return
        code = str(code)
        if QtCore.QThread.currentThread() is self.thread():
            self._log_code(code)
        else:
            self._logRequested.emit(code)

    #: Historic spelling used by ``chisurf.log``.
    log_on_gui_thread = log_threadsafe

    def _edit_file(self, path: str, line: int = 0) -> None:
        """Open *path* in ChiSurf's editor, for ``%edit``.

        Parameters
        ----------
        path : str
        line : int, optional
        """
        try:
            import chisurf as cs

            window = getattr(cs, "cs", None)
            if window is not None and hasattr(window, "onOpenEditor"):
                window.onOpenEditor(path, line)
                return
        except Exception:
            pass
        self.append_output(f"{path}:{line}\n")

    # ------------------------------------------------------------------
    # Qt plumbing
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802 - Qt override
        """Give the completion popup first refusal on every key.

        Parameters
        ----------
        event : QtGui.QKeyEvent
        """
        if self.completion_popup.handle_key(event):
            return
        super().keyPressEvent(event)

    def setFocus(self) -> None:  # noqa: N802 - Qt override
        """Focus whichever widget takes input."""
        self._focus_input()


def _as_bytes(payload) -> bytes:
    """Return *payload* as raw bytes.

    A MIME bundle may carry an image as bytes or as base64 text depending on who
    produced it.

    Parameters
    ----------
    payload : bytes or str

    Returns
    -------
    bytes
    """
    if isinstance(payload, bytes):
        return payload
    import base64

    try:
        return base64.b64decode(payload)
    except Exception:
        return str(payload).encode("utf-8", errors="replace")
