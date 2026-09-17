"""The console text area.

A ``QTextEdit`` rather than a ``QPlainTextEdit``, because inline images and
``_repr_html_`` need a rich ``QTextDocument``.

Editing happens *in the document* rather than in a mirrored string buffer, which
is what keeps native undo, input methods, dead keys, mouse selection and word
wrap working. The price is that the read-only region has to be defended, and it
is defended in layers -- every single-layer scheme leaks somewhere.
"""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets

from chisurf.core.console import ansi as ansi_module
from chisurf.gui.chinsole.theme import ConsoleTheme, resolve_theme, stylesheet

__all__ = ["ConsoleView", "PromptBlockData", "BLOCK_OUTPUT", "BLOCK_INPUT", "BLOCK_CONTINUE"]

BLOCK_OUTPUT = 0
BLOCK_INPUT = 1
BLOCK_CONTINUE = 2
BLOCK_ERROR = 3


class PromptBlockData(QtGui.QTextBlockUserData):
    """Per-block bookkeeping: what the block is, and how long its prompt is.

    Three behaviours fall out of storing this rather than recomputing it:
    copying without prompts, highlighting only the input, and knowing where the
    editable region starts.

    Parameters
    ----------
    kind : int
    prompt_len : int
    """

    def __init__(self, kind: int = BLOCK_OUTPUT, prompt_len: int = 0) -> None:
        super().__init__()
        self.kind = kind
        self.prompt_len = prompt_len


class ConsoleView(QtWidgets.QTextEdit):
    """Scrollback, prompt and input editing in one text area.

    Parameters
    ----------
    parent : QtWidgets.QWidget, optional
    theme : ConsoleTheme, optional
    """

    #: Emitted with a finished cell's source when the user presses Enter.
    executeRequested = QtCore.Signal(str)
    #: Emitted when the user asks for completions.
    completeRequested = QtCore.Signal()
    #: Emitted when the user asks for a calltip.
    calltipRequested = QtCore.Signal()
    #: Emitted with -1 or +1 to walk history.
    historyRequested = QtCore.Signal(int)
    #: Emitted when Ctrl-C is pressed.
    interruptRequested = QtCore.Signal()
    #: Emitted when Ctrl-D is pressed on an empty prompt.
    exitRequested = QtCore.Signal()
    #: Emitted when Ctrl-R is pressed.
    searchRequested = QtCore.Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        theme: ConsoleTheme | None = None,
    ) -> None:
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setUndoRedoEnabled(True)
        self.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setAcceptDrops(True)

        self.theme = theme or resolve_theme()
        self._prompt_pos = 0
        self._prompt_text = "In [{n}]: "
        self._continuation_text = "     ...: "
        self._executing = False
        self._reading_input = False
        self._input_loop: QtCore.QEventLoop | None = None
        self._input_result = ""
        self._input_echo = True
        self._image_counter = 0
        self._image_store: dict[str, tuple[bytes, str]] = {}
        self._ansi = ansi_module.AnsiParser()
        self._max_blocks = 5000
        self._autoscroll = True
        self._kill_ring: list[str] = []
        #: Set by :class:`~chisurf.gui.chinsole.widget.Chinsole`; consulted
        #: first in :meth:`keyPressEvent`.
        self.completion_popup = None
        #: Whether this console draws an input prompt. False for a read-only
        #: output panel, which has nothing to prompt for.
        self.shows_prompt = True

        self.apply_theme(self.theme)
        self.verticalScrollBar().valueChanged.connect(self._note_scroll_position)

    # ------------------------------------------------------------------
    # appearance
    # ------------------------------------------------------------------

    def apply_theme(self, theme: ConsoleTheme) -> None:
        """Adopt *theme*.

        Parameters
        ----------
        theme : ConsoleTheme
        """
        self.theme = theme
        self.setStyleSheet(stylesheet(theme))
        palette = self.palette()
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor(theme.background))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor(theme.foreground))
        self.setPalette(palette)

    def set_max_blocks(self, count: int) -> None:
        """Cap the scrollback.

        Parameters
        ----------
        count : int
            ``0`` for unlimited.
        """
        self._max_blocks = count

    def _trim_scrollback(self) -> None:
        """Drop the oldest blocks once the cap is exceeded.

        Trimming happens from the top and never touches the block the prompt
        lives in, so a runaway loop cannot delete the prompt out from under the
        cursor.
        """
        if not self._max_blocks:
            return
        document = self.document()
        excess = document.blockCount() - self._max_blocks
        if excess <= 0:
            return
        cursor = QtGui.QTextCursor(document)
        cursor.movePosition(QtGui.QTextCursor.Start)
        cursor.movePosition(
            QtGui.QTextCursor.NextBlock,
            QtGui.QTextCursor.KeepAnchor,
            excess,
        )
        removed = len(cursor.selectedText())
        cursor.removeSelectedText()
        self._prompt_pos = max(0, self._prompt_pos - removed)

    # ------------------------------------------------------------------
    # the editable region
    # ------------------------------------------------------------------

    def is_editable(self, position: int | None = None) -> bool:
        """Return whether *position* is inside the input area.

        Parameters
        ----------
        position : int, optional
            Defaults to the cursor.

        Returns
        -------
        bool
        """
        if position is None:
            position = self.textCursor().position()
        return position >= self._prompt_pos

    def input_buffer(self) -> str:
        """Return what the user has typed at the prompt.

        Returns
        -------
        str
            Continuation prompts removed, so the result is real Python.
        """
        document = self.document()
        cursor = QtGui.QTextCursor(document)
        cursor.setPosition(self._prompt_pos)
        cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
        text = cursor.selectedText().replace(" ", "\n")

        lines = text.split("\n")
        out = [lines[0]] if lines else [""]
        for line in lines[1:]:
            if line.startswith(self._continuation_text):
                out.append(line[len(self._continuation_text) :])
            else:
                out.append(line)
        return "\n".join(out)

    def set_input_buffer(self, text: str) -> None:
        """Replace the input area with *text*.

        Parameters
        ----------
        text : str
        """
        cursor = self.textCursor()
        cursor.setPosition(self._prompt_pos)
        cursor.movePosition(QtGui.QTextCursor.End, QtGui.QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        lines = text.split("\n")
        cursor.insertText(lines[0], self._input_format())
        for line in lines[1:]:
            self._insert_continuation(cursor)
            cursor.insertText(line, self._input_format())
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    # ------------------------------------------------------------------
    # prompts
    # ------------------------------------------------------------------

    def _input_format(self) -> QtGui.QTextCharFormat:
        """Return the format for typed input.

        Returns
        -------
        QtGui.QTextCharFormat
        """
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QColor(self.theme.foreground))
        return fmt

    def _prompt_format(self, colour: str) -> QtGui.QTextCharFormat:
        """Return the format for a prompt.

        Parameters
        ----------
        colour : str

        Returns
        -------
        QtGui.QTextCharFormat
        """
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QColor(colour))
        fmt.setFontWeight(QtGui.QFont.Bold)
        return fmt

    def show_prompt(self, number: int | None = None, *, newline: bool = True) -> None:
        """Draw a fresh input prompt at the end of the document.

        Parameters
        ----------
        number : int, optional
            The ``In [n]`` number.
        newline : bool, optional
        """
        cursor = QtGui.QTextCursor(self.document())
        cursor.movePosition(QtGui.QTextCursor.End)
        if newline and not self._at_line_start(cursor):
            cursor.insertBlock()
        text = self._prompt_text.format(n=number if number is not None else "")
        cursor.insertText(text, self._prompt_format(self.theme.prompt_in))
        cursor.block().setUserData(PromptBlockData(BLOCK_INPUT, len(text)))
        self._prompt_pos = cursor.position()
        self.setTextCursor(cursor)
        self._executing = False
        self.ensureCursorVisible()

    def _insert_continuation(self, cursor: QtGui.QTextCursor) -> None:
        """Start a continuation line at *cursor*.

        Parameters
        ----------
        cursor : QtGui.QTextCursor
        """
        cursor.insertBlock()
        cursor.insertText(
            self._continuation_text, self._prompt_format(self.theme.prompt_continuation)
        )
        cursor.block().setUserData(PromptBlockData(BLOCK_CONTINUE, len(self._continuation_text)))

    @staticmethod
    def _at_line_start(cursor: QtGui.QTextCursor) -> bool:
        """Return whether *cursor* sits at the start of its block.

        Parameters
        ----------
        cursor : QtGui.QTextCursor

        Returns
        -------
        bool
        """
        return cursor.positionInBlock() == 0

    # ------------------------------------------------------------------
    # output
    # ------------------------------------------------------------------

    def _output_cursor(self) -> QtGui.QTextCursor:
        """Return a cursor positioned where output should be written.

        Returns
        -------
        QtGui.QTextCursor
        """
        cursor = QtGui.QTextCursor(self.document())
        cursor.movePosition(QtGui.QTextCursor.End)
        return cursor

    def append_output(self, text: str, *, kind: str = "stdout") -> None:
        """Append streamed output, honouring ANSI escapes.

        Parameters
        ----------
        text : str
        kind : str, optional
            ``"stdout"`` or ``"stderr"``.
        """
        if not text:
            return
        cursor = self._output_cursor()
        base = QtGui.QTextCharFormat()
        base.setForeground(
            QtGui.QColor(self.theme.stderr_fg if kind == "stderr" else self.theme.foreground)
        )

        for event in self._ansi.feed(text):
            if isinstance(event, ansi_module.Text):
                cursor.insertText(event.text, self._format_for(event.state, base))
            elif isinstance(event, ansi_module.CarriageReturn):
                cursor.movePosition(QtGui.QTextCursor.StartOfBlock)
            elif isinstance(event, ansi_module.Backspace):
                cursor.movePosition(
                    QtGui.QTextCursor.PreviousCharacter,
                    QtGui.QTextCursor.MoveAnchor,
                    event.count,
                )
            elif isinstance(event, ansi_module.EraseLine):
                # This, with CarriageReturn above, is what makes a progress bar
                # redraw its line instead of printing thousands of them.
                cursor.movePosition(QtGui.QTextCursor.EndOfBlock, QtGui.QTextCursor.KeepAnchor)
                cursor.removeSelectedText()
            elif isinstance(event, ansi_module.EraseDisplay) and event.mode == 2:
                self.clear_screen()
                cursor = self._output_cursor()

        block = cursor.block()
        if block.userData() is None:
            block.setUserData(PromptBlockData(BLOCK_ERROR if kind == "stderr" else BLOCK_OUTPUT, 0))
        self._trim_scrollback()
        self._prompt_pos = self.document().characterCount() - 1
        if self._autoscroll:
            self.moveCursor(QtGui.QTextCursor.End)
            self.ensureCursorVisible()

    def _format_for(
        self,
        state: ansi_module.SgrState,
        base: QtGui.QTextCharFormat,
    ) -> QtGui.QTextCharFormat:
        """Translate an ANSI state into a Qt character format.

        Parameters
        ----------
        state : SgrState
        base : QtGui.QTextCharFormat

        Returns
        -------
        QtGui.QTextCharFormat
        """
        fmt = QtGui.QTextCharFormat(base)
        foreground = self._ansi_colour(state.fg)
        background = self._ansi_colour(state.bg)
        if state.inverse:
            foreground, background = background, foreground
            foreground = foreground or QtGui.QColor(self.theme.background)
            background = background or QtGui.QColor(self.theme.foreground)
        if foreground is not None:
            fmt.setForeground(foreground)
        if background is not None:
            fmt.setBackground(background)
        if state.bold:
            fmt.setFontWeight(QtGui.QFont.Bold)
        if state.italic:
            fmt.setFontItalic(True)
        if state.underline:
            fmt.setFontUnderline(True)
        if state.strike:
            fmt.setFontStrikeOut(True)
        return fmt

    def _ansi_colour(self, value: int | str | None) -> QtGui.QColor | None:
        """Resolve an ANSI colour against the theme palette.

        Parameters
        ----------
        value : int or str or None

        Returns
        -------
        QtGui.QColor or None
        """
        if value is None:
            return None
        if isinstance(value, int):
            palette = self.theme.ansi
            return QtGui.QColor(palette[value % len(palette)])
        return QtGui.QColor(value)

    def append_html(self, html: str) -> None:
        """Append rich text.

        Parameters
        ----------
        html : str
        """
        cursor = self._output_cursor()
        if not self._at_line_start(cursor):
            cursor.insertBlock()
        cursor.insertHtml(html)
        cursor.insertBlock()
        self._prompt_pos = self.document().characterCount() - 1
        if self._autoscroll:
            self.moveCursor(QtGui.QTextCursor.End)

    def append_image(
        self,
        data: bytes,
        fmt: str = "png",
        metadata: dict | None = None,
    ) -> None:
        """Append an inline image.

        Parameters
        ----------
        data : bytes
        fmt : str, optional
        metadata : dict, optional
            May carry a ``width``.
        """
        image = QtGui.QImage.fromData(data, fmt.upper())
        if image.isNull():
            self.append_output(f"<could not decode {fmt} image>\n", kind="stderr")
            return

        name = f"chinsole-img-{self._image_counter}"
        self._image_counter += 1
        self._image_store[name] = (data, fmt)
        self.document().addResource(QtGui.QTextDocument.ImageResource, QtCore.QUrl(name), image)

        image_format = QtGui.QTextImageFormat()
        image_format.setName(name)
        limit = self._image_limit()
        if limit and image.width() > limit:
            image_format.setWidth(limit)
            image_format.setHeight(image.height() * limit / image.width())

        cursor = self._output_cursor()
        if not self._at_line_start(cursor):
            cursor.insertBlock()
        cursor.insertImage(image_format)
        cursor.insertBlock()
        self._prompt_pos = self.document().characterCount() - 1
        if self._autoscroll:
            self.moveCursor(QtGui.QTextCursor.End)

    def append_svg(self, data: bytes | str) -> None:
        """Append an SVG, rasterised for the document.

        Parameters
        ----------
        data : bytes or str
        """
        try:
            from qtpy import QtSvg
        except ImportError:
            self.append_output("<SVG output needs QtSvg>\n", kind="stderr")
            return
        payload = data.encode("utf-8") if isinstance(data, str) else data
        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(payload))
        if not renderer.isValid():
            self.append_output("<invalid SVG>\n", kind="stderr")
            return
        size = renderer.defaultSize()
        ratio = self.devicePixelRatioF() or 1.0
        image = QtGui.QImage(
            int(size.width() * ratio),
            int(size.height() * ratio),
            QtGui.QImage.Format_ARGB32,
        )
        image.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(image)
        renderer.render(painter)
        painter.end()

        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        self.append_image(bytes(buffer.data()), "png")

    def _image_limit(self) -> int:
        """Return the widest an inline image may be drawn.

        Returns
        -------
        int
        """
        return max(0, self.viewport().width() - 24)

    def clear_screen(self, keep_input: bool = True) -> None:
        """Clear the scrollback.

        Parameters
        ----------
        keep_input : bool, optional
            Preserve what is currently typed.
        """
        typed = self.input_buffer() if keep_input and self.shows_prompt else ""
        self.clear()
        self._prompt_pos = 0
        self._ansi.reset()
        # A read-only console has no prompt to redraw. Doing it anyway put a
        # stray "In []:" at the head of the code editor's output panel every
        # time a script was run.
        if self.shows_prompt:
            self.show_prompt(newline=False)
        if typed:
            self.set_input_buffer(typed)

    # ------------------------------------------------------------------
    # scrolling
    # ------------------------------------------------------------------

    def _note_scroll_position(self, value: int) -> None:
        """Track whether the view is pinned to the bottom.

        Scrolling up to read something must not be undone by the next line of
        output; auto-scroll resumes when the user returns to the bottom.

        Parameters
        ----------
        value : int
        """
        bar = self.verticalScrollBar()
        self._autoscroll = value >= bar.maximum() - 4

    # ------------------------------------------------------------------
    # input handling
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802 - Qt override
        """Route a key press.

        Parameters
        ----------
        event : QtGui.QKeyEvent
        """
        # The popup gets first refusal, in one place. Splitting this between an
        # event filter on the popup and another here is how Enter ends up both
        # accepting a completion and running the cell.
        popup = self.completion_popup
        if popup is not None and popup.handle_key(event):
            return

        key = event.key()
        modifiers = event.modifiers()
        ctrl = bool(modifiers & QtCore.Qt.ControlModifier)
        shift = bool(modifiers & QtCore.Qt.ShiftModifier)

        if ctrl and key == QtCore.Qt.Key_C and not self.textCursor().hasSelection():
            self.interruptRequested.emit()
            return
        if ctrl and key == QtCore.Qt.Key_R:
            self.searchRequested.emit()
            return
        if ctrl and key == QtCore.Qt.Key_D:
            if not self.input_buffer().strip():
                self.exitRequested.emit()
                return
        if ctrl and key == QtCore.Qt.Key_L:
            self.clear_screen()
            return

        if self._executing and key not in (QtCore.Qt.Key_C,):
            # While a cell runs the prompt is gone; typing would land in output.
            if not (ctrl and key in (QtCore.Qt.Key_C, QtCore.Qt.Key_A)):
                return

        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self._handle_return(shift=shift, ctrl=ctrl)
            return

        if key == QtCore.Qt.Key_Tab and not shift:
            self._handle_tab()
            return
        if key == QtCore.Qt.Key_Backtab or (key == QtCore.Qt.Key_Tab and shift):
            self._dedent()
            return

        if key in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down) and not shift:
            if self._history_key(key):
                return

        if ctrl and key == QtCore.Qt.Key_K:
            self._kill_to_end()
            return
        if ctrl and key == QtCore.Qt.Key_U:
            self._kill_to_start()
            return
        if ctrl and key == QtCore.Qt.Key_Y:
            self._yank()
            return
        if ctrl and key == QtCore.Qt.Key_A:
            self._move_to_prompt_start(select=shift)
            return
        if ctrl and key == QtCore.Qt.Key_E:
            self.moveCursor(QtGui.QTextCursor.End)
            return

        if key == QtCore.Qt.Key_Home:
            self._move_to_prompt_start(select=shift)
            return

        if key == QtCore.Qt.Key_Backspace:
            if not self._can_delete_before():
                return
        elif key == QtCore.Qt.Key_Delete:
            if not self.is_editable():
                self._jump_to_prompt()
                return

        if self._is_text_input(event):
            if (
                not self.is_editable()
                or self.textCursor().hasSelection()
                and not self._selection_editable()
            ):
                self._jump_to_prompt()

        super().keyPressEvent(event)

        if event.text() == "(":
            self.calltipRequested.emit()

    def _is_text_input(self, event: QtGui.QKeyEvent) -> bool:
        """Return whether *event* would insert or remove text.

        Parameters
        ----------
        event : QtGui.QKeyEvent

        Returns
        -------
        bool
        """
        if event.key() in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete):
            return True
        text = event.text()
        return bool(text) and text.isprintable()

    def _selection_editable(self) -> bool:
        """Return whether the whole selection lies in the input area.

        Returns
        -------
        bool
        """
        cursor = self.textCursor()
        return self.is_editable(min(cursor.position(), cursor.anchor()))

    def _jump_to_prompt(self) -> None:
        """Move the cursor to the end, so typing over output types at the prompt.

        Beeping instead would be technically correct and infuriating.
        """
        cursor = self.textCursor()
        cursor.clearSelection()
        cursor.movePosition(QtGui.QTextCursor.End)
        self.setTextCursor(cursor)

    def _can_delete_before(self) -> bool:
        """Return whether Backspace may act at the cursor.

        Returns
        -------
        bool
        """
        cursor = self.textCursor()
        if cursor.hasSelection():
            return self._selection_editable()
        position = cursor.position()
        if position <= self._prompt_pos:
            return False
        block = cursor.block()
        data = block.userData()
        if isinstance(data, PromptBlockData) and data.kind == BLOCK_CONTINUE:
            if cursor.positionInBlock() <= data.prompt_len:
                self._join_continuation()
                return False
        return True

    def _join_continuation(self) -> None:
        """Merge a continuation line into the one above, prompt included."""
        cursor = self.textCursor()
        block = cursor.block()
        data = block.userData()
        prompt_len = data.prompt_len if isinstance(data, PromptBlockData) else 0
        cursor.beginEditBlock()
        cursor.movePosition(QtGui.QTextCursor.StartOfBlock)
        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, prompt_len)
        cursor.removeSelectedText()
        cursor.deletePreviousChar()
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _move_to_prompt_start(self, *, select: bool = False) -> None:
        """Move to the first character after the prompt on this line.

        Parameters
        ----------
        select : bool, optional
        """
        cursor = self.textCursor()
        block = cursor.block()
        data = block.userData()
        offset = data.prompt_len if isinstance(data, PromptBlockData) else 0
        mode = QtGui.QTextCursor.KeepAnchor if select else QtGui.QTextCursor.MoveAnchor
        cursor.movePosition(QtGui.QTextCursor.StartOfBlock, mode)
        cursor.movePosition(QtGui.QTextCursor.Right, mode, offset)
        self.setTextCursor(cursor)

    def _handle_return(self, *, shift: bool, ctrl: bool) -> None:
        """Decide whether Enter executes or continues.

        Parameters
        ----------
        shift : bool
            Force a newline.
        ctrl : bool
            Force execution.
        """
        source = self.input_buffer()
        if shift:
            self._newline_with_indent(source)
            return
        if ctrl:
            self.executeRequested.emit(source)
            return
        self.executeRequested.emit(source)

    def continue_input(self, indent: str) -> None:
        """Add a continuation line prefilled with *indent*.

        Parameters
        ----------
        indent : str
        """
        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        self._insert_continuation(cursor)
        if indent:
            cursor.insertText(indent, self._input_format())
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _newline_with_indent(self, source: str) -> None:
        """Insert a continuation line, indented for *source*.

        Parameters
        ----------
        source : str
        """
        from chisurf.core.console.transform import indent_hint

        self.continue_input(indent_hint(source))

    def _handle_tab(self) -> None:
        """Indent, or ask for completions."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            self._indent_selection(+1)
            return
        block_text = cursor.block().text()
        data = cursor.block().userData()
        offset = data.prompt_len if isinstance(data, PromptBlockData) else 0
        before = block_text[offset : cursor.positionInBlock()]
        if not before.strip():
            width = 4 - (len(before) % 4)
            cursor.insertText(" " * width)
            return
        self.completeRequested.emit()

    def _dedent(self) -> None:
        """Remove one indent level, or show a calltip."""
        cursor = self.textCursor()
        if cursor.hasSelection():
            self._indent_selection(-1)
            return
        block_text = cursor.block().text()
        data = cursor.block().userData()
        offset = data.prompt_len if isinstance(data, PromptBlockData) else 0
        before = block_text[offset : cursor.positionInBlock()]
        if before and not before.strip():
            remove = min(4, len(before))
            for _ in range(remove):
                cursor.deletePreviousChar()
            return
        self.calltipRequested.emit()

    def _indent_selection(self, direction: int) -> None:
        """Indent or dedent every selected line.

        Parameters
        ----------
        direction : int
            ``+1`` to indent, ``-1`` to dedent.
        """
        cursor = self.textCursor()
        start, end = sorted((cursor.anchor(), cursor.position()))
        document = self.document()
        first = document.findBlock(start).blockNumber()
        last = document.findBlock(end).blockNumber()

        cursor.beginEditBlock()
        for number in range(first, last + 1):
            block = document.findBlockByNumber(number)
            data = block.userData()
            offset = data.prompt_len if isinstance(data, PromptBlockData) else 0
            edit = QtGui.QTextCursor(block)
            edit.movePosition(QtGui.QTextCursor.StartOfBlock)
            edit.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.MoveAnchor, offset)
            if direction > 0:
                edit.insertText("    ")
            else:
                text = block.text()[offset:]
                strip = len(text) - len(text.lstrip(" "))
                for _ in range(min(4, strip)):
                    edit.deleteChar()
        cursor.endEditBlock()

    def _history_key(self, key: int) -> bool:
        """Handle Up/Down, walking history at the buffer edges.

        Parameters
        ----------
        key : int

        Returns
        -------
        bool
            Whether the key was consumed.
        """
        cursor = self.textCursor()
        document = self.document()
        first_input = document.findBlock(self._prompt_pos).blockNumber()
        last = document.blockCount() - 1
        current = cursor.block().blockNumber()

        if key == QtCore.Qt.Key_Up and current == first_input:
            self.historyRequested.emit(-1)
            return True
        if key == QtCore.Qt.Key_Down and current == last:
            self.historyRequested.emit(+1)
            return True
        return False

    def _kill_to_end(self) -> None:
        """Cut from the cursor to the end of the line."""
        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.EndOfBlock, QtGui.QTextCursor.KeepAnchor)
        if cursor.hasSelection():
            self._kill_ring.append(cursor.selectedText())
            cursor.removeSelectedText()

    def _kill_to_start(self) -> None:
        """Cut from the start of the input to the cursor."""
        cursor = self.textCursor()
        block = cursor.block()
        data = block.userData()
        offset = data.prompt_len if isinstance(data, PromptBlockData) else 0
        cursor.movePosition(QtGui.QTextCursor.StartOfBlock, QtGui.QTextCursor.KeepAnchor)
        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, offset)
        if cursor.hasSelection():
            self._kill_ring.append(cursor.selectedText())
            cursor.removeSelectedText()

    def _yank(self) -> None:
        """Paste the most recent kill."""
        if self._kill_ring:
            self.textCursor().insertText(self._kill_ring[-1])

    # ------------------------------------------------------------------
    # clipboard and drag-and-drop
    # ------------------------------------------------------------------

    def createMimeDataFromSelection(self) -> QtCore.QMimeData:  # noqa: N802 - Qt override
        """Copy the selection without prompts.

        Returns
        -------
        QtCore.QMimeData
        """
        cursor = self.textCursor()
        start, end = sorted((cursor.anchor(), cursor.position()))
        document = self.document()
        lines: list[str] = []
        block = document.findBlock(start)
        while block.isValid() and block.position() <= end:
            data = block.userData()
            offset = data.prompt_len if isinstance(data, PromptBlockData) else 0
            text = block.text()
            begin = max(0, start - block.position())
            stop = min(len(text), end - block.position())
            if begin < offset:
                begin = offset
            lines.append(text[begin:stop] if stop > begin else "")
            block = block.next()
        mime = QtCore.QMimeData()
        mime.setText("\n".join(lines))
        return mime

    def insertFromMimeData(self, source: QtCore.QMimeData) -> None:  # noqa: N802 - Qt override
        """Paste plain text, stripping any interpreter prompts.

        Parameters
        ----------
        source : QtCore.QMimeData
        """
        from chisurf.core.console.transform import strip_prompts

        if not source.hasText():
            return
        if not self.is_editable():
            self._jump_to_prompt()
        text = strip_prompts(source.text())
        lines = text.split("\n")
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.insertText(lines[0], self._input_format())
        for line in lines[1:]:
            self._insert_continuation(cursor)
            cursor.insertText(line, self._input_format())
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def canInsertFromMimeData(self, source: QtCore.QMimeData) -> bool:  # noqa: N802 - Qt override
        """Return whether *source* can be pasted.

        Parameters
        ----------
        source : QtCore.QMimeData

        Returns
        -------
        bool
        """
        return source.hasText() or source.hasUrls()

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Accept dragged files and text.

        Parameters
        ----------
        event : QtGui.QDragEnterEvent
        """
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Insert a dropped path, or run a dropped Python file.

        Parameters
        ----------
        event : QtGui.QDropEvent
        """
        mime = event.mimeData()
        if mime.hasUrls():
            paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
            if paths:
                self._jump_to_prompt()
                if len(paths) == 1 and paths[0].endswith(".py"):
                    self.set_input_buffer(f"%run -i '{paths[0]}'")
                else:
                    self.textCursor().insertText(" ".join(repr(p) for p in paths))
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Show the console context menu.

        Parameters
        ----------
        event : QtGui.QContextMenuEvent
        """
        menu = self.createStandardContextMenu()
        cursor = self.cursorForPosition(event.pos())
        image_name = cursor.charFormat().toImageFormat().name()
        if image_name and image_name in self._image_store:
            menu.addSeparator()
            menu.addAction("Copy image", lambda: self._copy_image(image_name))
            menu.addAction("Save image as…", lambda: self._save_image(image_name))
        menu.addSeparator()
        menu.addAction("Clear console", self.clear_screen)
        menu.exec_(event.globalPos())

    def _copy_image(self, name: str) -> None:
        """Put an inline image on the clipboard.

        Parameters
        ----------
        name : str
        """
        data, fmt = self._image_store[name]
        image = QtGui.QImage.fromData(data, fmt.upper())
        QtWidgets.QApplication.clipboard().setImage(image)

    def _save_image(self, name: str) -> None:
        """Write an inline image to a file the user chooses.

        Parameters
        ----------
        name : str
        """
        data, fmt = self._image_store[name]
        path, _selected = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save image", f"figure.{fmt}", f"Images (*.{fmt})"
        )
        if path:
            with open(path, "wb") as handle:
                handle.write(data)

    # ------------------------------------------------------------------
    # blocking input, for input() and pdb
    # ------------------------------------------------------------------

    def read_input(self, prompt: str = "", password: bool = False) -> str:
        """Block until the user types a line, keeping the GUI alive.

        Parameters
        ----------
        prompt : str, optional
        password : bool, optional
            Do not echo what is typed.

        Returns
        -------
        str

        Raises
        ------
        EOFError
            If the console is closed while waiting.
        """
        self._reading_input = True
        self._input_echo = not password
        self._executing = False
        if prompt:
            self.append_output(prompt)
        self._prompt_pos = self.document().characterCount() - 1
        self.moveCursor(QtGui.QTextCursor.End)
        self.setFocus()

        loop = QtCore.QEventLoop()
        self._input_loop = loop
        loop.exec_()

        self._reading_input = False
        self._input_echo = True
        if self._input_result is None:
            raise EOFError("console closed")
        return self._input_result

    def _finish_input(self) -> None:
        """Complete a pending :meth:`read_input`."""
        if self._input_loop is None:
            return
        self._input_result = self.input_buffer()
        self.append_output("\n")
        loop, self._input_loop = self._input_loop, None
        loop.quit()

    def set_executing(self, running: bool) -> None:
        """Record whether a cell is running.

        Parameters
        ----------
        running : bool
        """
        self._executing = running
