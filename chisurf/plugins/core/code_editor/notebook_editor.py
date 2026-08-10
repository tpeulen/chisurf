"""A native notebook editor that runs its cells in ChiSurf's in-process shell.

``.ipynb`` files are loaded with :mod:`nbformat`, shown as a vertical stack of
editable cells, and executed **in process** through
:class:`chisurf.core.console.shell.Shell` -- the same interpreter the ChiSurf
console uses. There is no Jupyter kernel and no web view: the ``Shell`` already
understands IPython semantics (magics, ``_ih``/``_oh``,
``get_ipython()``, ``%matplotlib inline``), so ``%matplotlib inline`` renders a
figure painted by the cell's code as a PNG embedded in that cell's output --
"plots embedded" without any external backend.

Deliberate design boundary (mirroring the spyder-notebook reference, whose
*native* ``junk/spyder-notebook`` checkout is annotated): spyder-notebook hosts
the full Jupyter **web** client over a kernel server. That is what this widget
is *not*: execution must stay inside the built-in interpreter, so the web
frontend is skipped entirely and only the tab/dirty/save UX contract is kept.

The widget exposes a facade that matches the rest of the code_editor plugin's
tab-host expectations (``current_file``, ``document()``, ``toPlainText()``,
``setText``, ``set_current_file``, ``line_column()``) so it can sit in the same
``DockArea`` as the plain-text tabs with no special-casing in the host.

Beyond plain editing, the notebook behaves like a real notebook:

- a **terminal** (:class:`chisurf.gui.chinsole.Chinsole`) is attached below the
  cells and shares this notebook's :class:`Shell`; running a cell types a
  one-line marker of its source onto the terminal's live prompt, stream output
  lands there too, and commands typed directly in the terminal share variables
  with the cells (one kernel, two surfaces);
- **markdown cells are rendered** by default and only editable on double-click;
  ``Ctrl+Enter`` renders them back into view, like Jupyter;
- a hairline ``＋`` strip between every pair of cells inserts a new cell
  *between* two cells, not just at the end;
- a one-row toolbar carries what is not a per-cell action: run all, restart the
  kernel, clear every output, and hide the terminal.

Every surface is **sized to its content**, which is what makes a notebook of
real length readable on one screen:

- the ``[n]`` prompt and the run/delete buttons sit in a narrow left gutter
  rather than in a header row above each cell;
- a source editor is exactly as tall as it has lines and does not scroll until
  it passes :attr:`NotebookCell.MAX_EDITOR_HEIGHT`;
- an output panel is exactly as tall as its text or its figure, up to
  :attr:`CellOutput.MAX_HEIGHT`, and a figure is scaled to the panel width;
- a figure belongs to one surface -- the cell that drew it -- and is not also
  painted into the terminal.
"""

from __future__ import annotations

import base64
import contextlib
import copy
import os
import pathlib
import sys
import typing

from qtpy import QtCore, QtGui, QtWidgets

import chisurf as cs
from chisurf import logging
from chisurf.core.console import ansi as _ansi
from chisurf.core.console.history import HistoryManager
from chisurf.core.console.shell import Shell
from chisurf.gui.chinsole.theme import resolve_theme
from chisurf.plugins.core.code_editor.text_editor import (
    TextEditor,
    get_editor_settings,
    make_editor_font,
)

nbformat = None

__all__ = ["NotebookEditor", "NotebookCell", "CellOutput", "shipped_notebooks"]


def _as_bytes(payload: typing.Any) -> bytes:
    """Return *payload* as raw bytes.

    A MIME bundle may carry an image as bytes or as base64 text depending on
    who produced it.

    Parameters
    ----------
    payload : bytes or str

    Returns
    -------
    bytes
    """
    if isinstance(payload, bytes):
        return payload
    try:
        return base64.b64decode(payload)
    except Exception:
        return str(payload).encode("utf-8", errors="replace")


def _render_markdown(source: str) -> str:
    """Render *source* as an HTML fragment for a ``QTextBrowser``.

    Parameters
    ----------
    source : str
        The markdown cell's raw source.

    Returns
    -------
    str
    """
    import markdown as _md

    return _md.markdown(source or "", extensions=["extra", "sane_lists"])


def _echo_line(source: str) -> str:
    """Return a one-line marker of *source* for the terminal log.

    The cell already shows its own source; echoing all of it into the terminal
    turns the console into a second copy of the notebook and leaves no room
    for the output it is there to show. One line, elided, is enough to say
    *which* cell ran.

    Parameters
    ----------
    source : str

    Returns
    -------
    str
    """
    lines = [line for line in source.splitlines() if line.strip()]
    if not lines:
        return ""
    head = lines[0].strip()
    if len(head) > 76:
        head = head[:75] + "…"
    if len(lines) > 1:
        head = f"{head}  … (+{len(lines) - 1} lines)"
    return head


def _cell_source(node: dict) -> str:
    """Return a notebook cell's source as one string.

    Parameters
    ----------
    node : dict
        A nbformat cell node.

    Returns
    -------
    str
    """
    source = node.get("source", "")
    if isinstance(source, list):
        return "".join(str(part) for part in source)
    return str(source or "")


def _ensure_nbformat() -> None:
    """Import :mod:`nbformat` on first use (kept lazy).

    Raises
    ------
    ImportError
        When the dependency is not installed.
    """
    global nbformat
    if nbformat is None:
        import nbformat as _nbformat

        nbformat = _nbformat


class CellOutput(QtWidgets.QTextEdit):
    """Read-only rich-text output panel for one notebook cell.

    Appends stream text (with stderr tinted) and embeds images (matplotlib
    "inline" figures arrive here as ``image/png``). Every append is also
    recorded so :meth:`collect_outputs` can rebuild the ``outputs`` list of an
    ipynb cell, and so :meth:`render_outputs` can replay a saved notebook's
    output back onto the widget.

    The panel is **sized to its content** rather than given a fixed height: a
    one-line result occupies one line, and a figure occupies exactly the
    figure. Only past :attr:`MAX_HEIGHT` does it stop growing and scroll, so a
    long print loop cannot push the next cell off the screen.
    """

    #: Tallest the panel grows before it scrolls instead (pixels).
    MAX_HEIGHT = 360

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.setContentsMargins(0, 0, 0, 0)
        self.document().setDocumentMargin(3)
        font = make_editor_font(get_editor_settings())
        self.setFont(font)
        self.document().setDefaultFont(font)
        self.document().setDefaultStyleSheet(
            "pre { white-space: pre-wrap; font-family: monospace; }"
        )

        palette = self.palette()
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#f4f4f4"))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#1a1a1a"))
        self.setPalette(palette)

        # The cell's output panel is a light surface, so a traceback's ANSI
        # colours are resolved against the light palette rather than the
        # console's dark one.
        self._theme = resolve_theme("chisurf-light")
        self._ansi = _ansi.AnsiParser()
        self._records: list[tuple] = []
        self._images: list[tuple[str, QtGui.QImage, dict]] = []
        self._clamped = False
        self._counter = 0
        self._max_blocks = 2000
        self.setFixedHeight(0)
        self.setVisible(False)
        self.document().documentLayout().documentSizeChanged.connect(
            lambda _size: self.fit_to_content()
        )

    # ------------------------------------------------------------------
    # append API
    # ------------------------------------------------------------------

    def append_text(self, text: str, kind: str = "stdout") -> None:
        """Append *text* in the given stream style.

        ANSI escapes are **interpreted**, not printed: the shell colours a
        traceback the way a terminal expects, and a cell that inserted the
        bytes verbatim showed ``[91m--->`` instead of a red arrow.

        Parameters
        ----------
        text : str
        kind : str, optional
            ``"stdout"`` or ``"stderr"``.
        """
        if not text:
            return
        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        base = QtGui.QTextCharFormat()
        base.setForeground(
            QtGui.QColor(self._theme.stderr_fg if kind == "stderr" else "#1a1a1a")
        )
        for event in self._ansi.feed(text):
            if isinstance(event, _ansi.Text):
                cursor.insertText(event.text, self._ansi_format(event.state, base))
        self._records.append(("stream", kind, text))
        self._trim_old_blocks()
        self.setVisible(True)
        self.fit_to_content()
        if self._clamped:
            self.ensureCursorVisible()

    def append_image(
        self,
        payload: bytes,
        fmt: str = "png",
        mime: str = "image/png",
        metadata: dict | None = None,
    ) -> None:
        """Embed an image *payload* in the cell output.

        Parameters
        ----------
        payload : bytes
        fmt : str, optional
        mime : str, optional
        metadata : dict, optional
            May carry a preferred ``width``.
        """
        image = QtGui.QImage.fromData(payload, fmt.upper())
        if image.isNull():
            self.append_text(f"<could not decode {fmt} image>\n", kind="stderr")
            return

        name = f"nb-img-{self._counter}"
        self._counter += 1
        self.document().addResource(
            QtGui.QTextDocument.ImageResource, QtCore.QUrl(name), image
        )

        cursor = self.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        if self.document().characterCount() > 1:
            cursor.insertBlock()
        cursor.insertImage(self._image_format(name, image, metadata))
        self._records.append(("display", mime, bytes(payload), dict(metadata or {})))
        self._images.append((name, image, dict(metadata or {})))
        self.setVisible(True)
        self.fit_to_content()

    def _image_format(
        self,
        name: str,
        image: QtGui.QImage,
        metadata: dict | None = None,
    ) -> QtGui.QTextImageFormat:
        """Return the on-screen geometry for an embedded *image*.

        A figure is shown at its natural size and only shrunk -- keeping its
        aspect ratio -- when it is wider than the output panel, so a plot never
        needs a horizontal scrollbar and never overflows the cell.
        """
        image_format = QtGui.QTextImageFormat()
        image_format.setName(name)
        natural = int((metadata or {}).get("width") or image.width()) or 1
        ratio = (image.height() or 1) / (image.width() or 1)
        limit = max(120, self.viewport().width() - 2 * int(self.document().documentMargin()) - 2)
        width = min(natural, limit)
        image_format.setWidth(width)
        image_format.setHeight(int(width * ratio))
        return image_format

    def _relayout_images(self) -> None:
        """Re-scale every embedded image to the panel's current width."""
        if not self._images:
            return
        doc = self.document()
        cursor = QtGui.QTextCursor(doc)
        cursor.beginEditBlock()
        by_name = {name: (image, metadata) for name, image, metadata in self._images}
        block = doc.begin()
        while block.isValid():
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                fmt = fragment.charFormat()
                if fmt.isImageFormat():
                    name = fmt.toImageFormat().name()
                    if name in by_name:
                        image, metadata = by_name[name]
                        cursor.setPosition(fragment.position())
                        cursor.setPosition(
                            fragment.position() + fragment.length(),
                            QtGui.QTextCursor.KeepAnchor,
                        )
                        cursor.setCharFormat(self._image_format(name, image, metadata))
                iterator += 1
            block = block.next()
        cursor.endEditBlock()

    def append_svg(self, payload: bytes | str) -> None:
        """Rasterise and embed an SVG payload.

        Parameters
        ----------
        payload : bytes or str
        """
        try:
            from qtpy import QtSvg
        except ImportError:
            self.append_text("<SVG output needs QtSvg>\n", kind="stderr")
            return
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(data))
        if not renderer.isValid():
            self.append_text("<invalid SVG>\n", kind="stderr")
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

    def append_mime(
        self,
        data: dict,
        metadata: dict,
        kind: str,
        execution_count: int | None,
    ) -> None:
        """Render a MIME bundle from the shell's ``display`` callback.

        Parameters
        ----------
        data : dict
        metadata : dict
        kind : str
        execution_count : int or None
        """
        if "image/png" in data:
            self.append_image(_as_bytes(data["image/png"]), "png", "image/png", metadata.get("image/png"))
            return
        if "image/jpeg" in data:
            self.append_image(_as_bytes(data["image/jpeg"]), "jpeg", "image/jpeg", metadata.get("image/jpeg"))
            return
        if "image/svg+xml" in data:
            self.append_svg(data["image/svg+xml"])
            return
        text = data.get("text/plain")
        if text is None:
            return
        text = str(text)
        if kind == "execute_result" and execution_count is not None:
            text = f"Out[{execution_count}]: {text}"
        if not text.endswith("\n"):
            text += "\n"
        self.append_text(text)
        self._records.append(("display_text", str(text)))

    # ------------------------------------------------------------------
    # nbformat round-trip
    # ------------------------------------------------------------------

    def clear(self) -> None:  # noqa: A003 - Qt override
        """Clear the output and its record of appended content."""
        super().clear()
        self._ansi = _ansi.AnsiParser()
        self._records = []
        self._images = []
        self._counter = 0
        self.setVisible(False)
        self.setFixedHeight(0)

    def collect_outputs(self) -> list[dict]:
        """Return the recorded outputs as nbformat output nodes.

        Returns
        -------
        list of dict
        """
        outputs: list[dict] = []
        pending: tuple[str, list[str]] | None = None

        def flush() -> None:
            nonlocal pending
            if pending is not None:
                name, texts = pending
                outputs.append(
                    {
                        "output_type": "stream",
                        "name": name,
                        "text": texts,
                    }
                )
            pending = None

        for record in self._records:
            if record[0] == "stream":
                _, name, text = record
                if pending is not None and pending[0] == name:
                    pending[1].append(text)
                else:
                    flush()
                    pending = (name, [text])
            elif record[0] == "display":
                _, mime, payload, metadata = record
                flush()
                outputs.append(
                    {
                        "output_type": "display_data",
                        "data": {mime: base64.b64encode(payload).decode("ascii")},
                        "metadata": metadata,
                    }
                )
            elif record[0] == "display_text":
                flush()
                outputs.append(
                    {
                        "output_type": "execute_result",
                        "execution_count": None,
                        "data": {"text/plain": record[1]},
                        "metadata": {},
                    }
                )
        flush()
        return outputs

    def render_outputs(self, outputs: list[dict]) -> None:
        """Replay saved *outputs* onto the widget.

        Parameters
        ----------
        outputs : list of dict
        """
        self.clear()
        for output in outputs:
            if not isinstance(output, dict):
                continue
            output_type = output.get("output_type")
            if output_type == "stream":
                text = output.get("text", "")
                if isinstance(text, list):
                    text = "".join(str(part) for part in text)
                self.append_text(str(text), kind=output.get("name", "stdout"))
            elif output_type in {"display_data", "execute_result"}:
                self.append_mime(
                    output.get("data") or {},
                    output.get("metadata") or {},
                    output_type,
                    output.get("execution_count"),
                )
            elif output_type == "error":
                text = "\n".join(
                    [output.get("ename", ""), output.get("evalue", "")]
                    + list(output.get("traceback", []))
                )
                self.append_text(text + "\n", kind="stderr")

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _ansi_format(
        self,
        state: "_ansi.SgrState",
        base: QtGui.QTextCharFormat,
    ) -> QtGui.QTextCharFormat:
        """Return the char format *state* selects, over *base*.

        Parameters
        ----------
        state : chisurf.core.console.ansi.SgrState
        base : QtGui.QTextCharFormat
            The stream's default format, used where *state* selects nothing.

        Returns
        -------
        QtGui.QTextCharFormat
        """
        fmt = QtGui.QTextCharFormat(base)
        palette = self._theme.ansi
        for colour, setter in (
            (state.fg, fmt.setForeground),
            (state.bg, fmt.setBackground),
        ):
            if colour is None:
                continue
            if isinstance(colour, int):
                if 0 <= colour < len(palette):
                    setter(QtGui.QColor(palette[colour]))
            else:
                setter(QtGui.QColor(colour))
        if state.bold:
            fmt.setFontWeight(QtGui.QFont.Bold)
        if state.italic:
            fmt.setFontItalic(True)
        if state.underline:
            fmt.setFontUnderline(True)
        if state.strike:
            fmt.setFontStrikeOut(True)
        return fmt

    def fit_to_content(self) -> None:
        """Resize the panel to exactly the height of what it holds.

        The document is laid out against the current viewport width first, so a
        wrapped line and an embedded figure both report their true height.
        """
        doc = self.document()
        width = max(1, self.viewport().width())
        if abs(doc.textWidth() - width) > 0.5:
            doc.setTextWidth(width)
        if not self._records:
            height = 0
        else:
            height = doc.size().height()
            # Stream text ends in a newline, which leaves a trailing empty
            # block; counting it adds a blank line under every printed result.
            # Its height comes from the layout, not from the font metrics --
            # a block holding an image is not one line tall.
            last = doc.lastBlock()
            if last.isValid() and not last.text() and doc.blockCount() > 1:
                height -= doc.documentLayout().blockBoundingRect(last).height()
            height = int(height + 2)
            height = max(self.fontMetrics().lineSpacing() + 6, height)
        self._clamped = height > self.MAX_HEIGHT
        height = min(self.MAX_HEIGHT, height)
        # The trailing empty block is inside the document but outside the
        # fitted height, so the panel must not be scrollable while it fits --
        # otherwise the view slides down onto that blank line and clips the
        # last real line of output.
        self.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarAsNeeded if self._clamped else QtCore.Qt.ScrollBarAlwaysOff
        )
        if not self._clamped:
            self.verticalScrollBar().setValue(0)
        if self.height() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Re-fit the panel when the notebook width changes.

        Text rewraps and an embedded figure is re-scaled to the new width, so
        the panel's height has to be recomputed from the laid-out document.
        """
        super().resizeEvent(event)
        self._relayout_images()
        QtCore.QTimer.singleShot(0, self.fit_to_content)

    def _trim_old_blocks(self) -> None:
        """Keep the widget's document bounded so a runaway print loop cannot
        wedge the cell.
        """
        doc = self.document()
        while doc.blockCount() > self._max_blocks:
            cursor = QtGui.QTextCursor(doc)
            cursor.movePosition(QtGui.QTextCursor.Start)
            cursor.movePosition(QtGui.QTextCursor.NextBlock, QtGui.QTextCursor.KeepAnchor)
            cursor.removeSelectedText()


class _MarkdownView(QtWidgets.QTextBrowser):
    """The rendered markdown surface of a cell.

    ``QTextBrowser`` has no ``doubleClicked`` signal on the Qt version this
    app builds against, so double-click-to-edit is surfaced through an
    override of ``mouseDoubleClickEvent`` instead.

    Signals
    -------
    doubleClicked(object)
        Emitted with the mouse event when the view is double-clicked.
    """

    doubleClicked = QtCore.Signal(object)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        """Emit :attr:`doubleClicked` and let the browser keep its default behavior."""
        self.doubleClicked.emit(event)
        super().mouseDoubleClickEvent(event)


class NotebookCell(QtWidgets.QWidget):
    """One editable notebook cell: a code editor, its output, and a header.

    Signals
    -------
    runRequested(object)
        Emitted with ``self`` when the user asks to run this cell.
    removeRequested(object)
        Emitted with ``self`` when the user asks to delete this cell.
    textChanged()
        Emitted when the cell's source is edited.
    """

    runRequested = QtCore.Signal(object)
    removeRequested = QtCore.Signal(object)
    textChanged = QtCore.Signal()

    MIN_EDITOR_HEIGHT = 26
    MAX_EDITOR_HEIGHT = 560
    MAX_RENDER_HEIGHT = 2000

    #: Width of the left column holding the run button and the ``[n]`` prompt.
    GUTTER_WIDTH = 40

    def __init__(
        self,
        cell_type: str = "code",
        source: str = "",
        outputs: list[dict] | None = None,
        cell_metadata: dict | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cell_type = cell_type if cell_type in ("code", "markdown", "raw") else "code"
        self.cell_metadata = dict(cell_metadata or {})
        self._source_node: dict | None = None
        self.execution_count: int | None = None
        self._edit_mode = False

        self.setObjectName("notebook_cell")
        # Without this a stylesheet border on a bare QWidget is never painted.
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget#notebook_cell { border-bottom: 1px solid palette(mid); }"
            "QToolButton#notebook_cell_button { color: #777; border: none; }"
            "QToolButton#notebook_cell_button:hover { color: #111; }"
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 4, 2)
        layout.setSpacing(2)

        # -- left gutter: run, delete, and the In[n] prompt -----------------
        # Jupyter's prompt column, rather than a full-width header row above
        # every cell: one row of chrome per cell is ~20px that the notebook
        # gets back as content.
        self._header = QtWidgets.QWidget(self)
        self._header.setFixedWidth(self.GUTTER_WIDTH)
        gutter = QtWidgets.QVBoxLayout(self._header)
        gutter.setContentsMargins(0, 0, 0, 0)
        gutter.setSpacing(0)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(0)

        self.run_button = QtWidgets.QToolButton(self._header)
        self.run_button.setObjectName("notebook_cell_button")
        self.run_button.setText("▶")
        self.run_button.setAutoRaise(True)
        self.run_button.setFixedSize(18, 16)
        self.run_button.setToolTip(
            "Render this cell (Ctrl+Return, Shift+Return)"
            if self.cell_type == "markdown"
            else "Run cell (Ctrl+Return, Shift+Return)"
        )
        self.run_button.autoRepeat = False
        self.run_button.clicked.connect(lambda _checked=False: self.runRequested.emit(self))
        buttons.addWidget(self.run_button)

        self.close_button = QtWidgets.QToolButton(self._header)
        self.close_button.setObjectName("notebook_cell_button")
        self.close_button.setText("✕")
        self.close_button.setAutoRaise(True)
        self.close_button.setFixedSize(18, 16)
        self.close_button.setToolTip("Delete cell")
        self.close_button.clicked.connect(
            lambda _checked=False: self.removeRequested.emit(self)
        )
        buttons.addWidget(self.close_button)
        gutter.addLayout(buttons)

        self.prompt_label = QtWidgets.QLabel("[ ]", self._header)
        self.prompt_label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop)
        prompt_font = self.prompt_label.font()
        prompt_font.setPointSizeF(max(7.0, prompt_font.pointSizeF() - 1.5))
        self.prompt_label.setFont(prompt_font)
        self.prompt_label.setStyleSheet("color: #888;")
        gutter.addWidget(self.prompt_label)
        gutter.addStretch(1)

        if self.cell_type != "code":
            self.prompt_label.setText("md" if self.cell_type == "markdown" else "raw")
        layout.addWidget(self._header, 0, QtCore.Qt.AlignTop)

        # -- right column: source, rendered markdown, output ----------------
        self._body = QtWidgets.QWidget(self)
        body = QtWidgets.QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(1)
        layout.addWidget(self._body, 1)

        editor_language = "Plain text"
        if self.cell_type == "code":
            editor_language = "Python"
        self.editor = TextEditor(parent=self._body, language=editor_language)
        self.editor._definition_uses_host = True
        self.editor.set_current_file(None)
        body.addWidget(self.editor)

        self.render_view = _MarkdownView(self._body)
        self.render_view.setObjectName("notebook_markdown_view")
        self.render_view.setOpenExternalLinks(True)
        self.render_view.setOpenLinks(True)
        self.render_view.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.render_view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.render_view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.render_view.document().setDocumentMargin(1)
        self.render_view.setStyleSheet(
            "QTextBrowser { background: transparent; border: none; }"
        )
        self.render_view.doubleClicked.connect(self._enter_edit_mode)
        body.addWidget(self.render_view)

        self.output = CellOutput(self._body)
        body.addWidget(self.output)

        self.editor.textChanged.connect(self._on_editor_changed)
        self.set_source(source)
        if outputs is not None:
            self.output.render_outputs(outputs)
        if self.cell_type == "markdown":
            self.render_markdown()
        self._sync_visibility()

    def _on_editor_changed(self) -> None:
        """Keep the editor height tracking its content and forward the change."""
        self._update_height()
        self.textChanged.emit()

    def _update_height(self) -> None:
        """Size the editor to exactly its lines, bounded both ways.

        The editor never scrolls vertically while it fits: a cell that shows
        five lines gets five lines of height, not four-and-a-scrollbar. Only a
        cell past :attr:`MAX_EDITOR_HEIGHT` keeps its vertical scrollbar.
        """
        if self.editor is None:
            return
        document = self.editor.document()
        metrics = self.editor.fontMetrics()
        height = (
            document.blockCount() * metrics.lineSpacing()
            + 2 * int(document.documentMargin())
            + 2 * self.editor.frameWidth()
        )
        if self.editor.horizontalScrollBar().maximum() > 0:
            height += self.editor.horizontalScrollBar().sizeHint().height()
        clamped = height > self.MAX_EDITOR_HEIGHT
        height = max(self.MIN_EDITOR_HEIGHT, min(self.MAX_EDITOR_HEIGHT, height))
        self.editor.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarAsNeeded if clamped else QtCore.Qt.ScrollBarAlwaysOff
        )
        if self.editor.height() != height:
            self.editor.setFixedHeight(int(height))

    # ------------------------------------------------------------------
    # markdown edit/rendered modes
    # ------------------------------------------------------------------

    def _sync_visibility(self) -> None:
        """Show the source editor, or the rendered markdown, as appropriate.

        The gutter stays visible either way -- a *rendered* markdown cell has
        to remain deletable and re-runnable without first being opened for
        editing.
        """
        if self.cell_type == "markdown":
            self.editor.setVisible(self._edit_mode)
            self.render_view.setVisible(not self._edit_mode)
        else:
            self.editor.setVisible(True)
            self.render_view.setVisible(False)

    def _enter_edit_mode(self, _pos=None) -> None:
        """Enter markdown edit mode (double-click on the rendered view)."""
        self._set_edit_mode(True)

    def _set_edit_mode(self, edit: bool) -> None:
        """Switch a markdown cell between its rendered and editable surfaces."""
        if self.cell_type != "markdown" or self._edit_mode == edit:
            return
        self._edit_mode = edit
        self._sync_visibility()
        if edit:
            self.editor.setFocus()

    def render_markdown(self) -> None:
        """Render the cell's source and show the rendered view (exit edit mode)."""
        if self.cell_type != "markdown":
            return
        self.render_view.setHtml(_render_markdown(self.editor.toPlainText()))
        self._edit_mode = False
        self._sync_visibility()
        self._update_render_height()

    def _update_render_height(self) -> None:
        """Size the rendered markdown view to its document, bounded."""
        if self.cell_type != "markdown":
            return
        doc = self.render_view.document()
        doc.setTextWidth(max(1, self.render_view.viewport().width()))
        height = int(doc.size().height()) + 2
        height = max(18, min(self.MAX_RENDER_HEIGHT, height))
        if self.render_view.height() != height:
            self.render_view.setFixedHeight(height)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Size rendered markdown once the cell is laid out."""
        super().showEvent(event)
        if self.cell_type == "markdown":
            self._update_render_height()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Reflow the cell when the notebook width changes.

        A narrower notebook can bring a horizontal scrollbar into the source
        editor and rewraps rendered markdown; both change the cell's height.
        """
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._update_height)
        if self.cell_type == "markdown":
            QtCore.QTimer.singleShot(0, self._update_render_height)

    def set_source(self, source: str) -> None:
        """Replace the cell source and restore the editor size."""
        self.editor.blockSignals(True)
        self.editor.setPlainText(source)
        self.editor.blockSignals(False)
        self.editor.document().setModified(False)
        self._update_height()

    def set_prompt(self, count: int | None) -> None:
        """Show the ``[n]`` gutter prompt reflecting *count*.

        Only code cells carry a prompt; a markdown or raw cell keeps its type
        label instead.
        """
        if self.cell_type != "code":
            return
        self.prompt_label.setText(f"[{count}]" if count is not None else "[ ]")

    def clear_output(self) -> None:
        """Clear the cell's output panel."""
        self.output.clear()
        self.set_prompt(None)

    def to_nbformat_node(self) -> dict:
        """Return a nbformat cell node for this cell's current state.

        Returns
        -------
        dict
        """
        _ensure_nbformat()
        if self._source_node is not None:
            node = copy.deepcopy(self._source_node)
        elif self.cell_type == "markdown":
            node = nbformat.v4.new_markdown_cell(source="")
        elif self.cell_type == "raw":
            node = nbformat.v4.new_raw_cell(source="")
        else:
            node = nbformat.v4.new_code_cell(source="")
        if not node.get("metadata"):
            node["metadata"] = {}
        for key, value in self.cell_metadata.items():
            node["metadata"][key] = value
        node["source"] = self.editor.toPlainText()
        if self.cell_type == "code":
            node["execution_count"] = self.execution_count
            node["outputs"] = self.collect_outputs()
        else:
            node["outputs"] = []
            node["execution_count"] = None
        return node

    def collect_outputs(self) -> list[dict]:
        """Return this cell's recorded outputs as nbformat nodes."""
        return self.output.collect_outputs()


class NotebookEditor(QtWidgets.QWidget):
    """A notebook document shown as an editable stack of cells.

    This is the tab widget the code_editor plugin hosts for ``.ipynb`` files.
    Cells run in a single in-process :class:`Shell` instance so variables and
    ``%`` magics persist across cells exactly as they do in a Jupyter kernel --
    but inside ChiSurf's own built-in interpreter.

    Signals
    -------
    textChanged()
    statusChanged(dict)
    symbolsChanged(list)
    filePathChanged(str)
    definitionRequested(str, int, int)
    runStateChanged(bool)
    cellAdded(object)
    """

    textChanged = QtCore.Signal()
    statusChanged = QtCore.Signal(dict)
    symbolsChanged = QtCore.Signal(list)
    filePathChanged = QtCore.Signal(str)
    definitionRequested = QtCore.Signal(str, int, int)
    runStateChanged = QtCore.Signal(bool)
    cellAdded = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.current_file: str | None = None
        self.language = "Notebook"
        self._cells: list[NotebookCell] = []
        self._active_cell: NotebookCell | None = None
        self._focus_cell: NotebookCell | None = None
        self._source_nb: dict | None = None

        self._beacon = QtGui.QTextDocument(self)
        self._beacon.setModified(False)

        self._status_timer = QtCore.QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(250)
        self._status_timer.timeout.connect(self._emit_changed)

        # The shell must exist before the terminal, whose shell is swapped for
        # this one so typing in the console and running cells share a kernel.
        self._shell = self._make_shell()
        self.terminal = self._make_terminal()
        self._build_ui()
        self.new_notebook()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble the toolbar, the scrollable cell stack, and the terminal."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_toolbar())

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        self.splitter.setHandleWidth(4)
        self.splitter.setStyleSheet(
            "QSplitter::handle:vertical { background: palette(mid); margin: 0 40px; }"
        )
        layout.addWidget(self.splitter)

        self.scroll = QtWidgets.QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.splitter.addWidget(self.scroll)

        self.container = QtWidgets.QWidget()
        self.stack = QtWidgets.QVBoxLayout(self.container)
        self.stack.setContentsMargins(0, 0, 0, 0)
        self.stack.setSpacing(0)
        self.scroll.setWidget(self.container)

        self.add_row = QtWidgets.QWidget(self.container)
        add_layout = QtWidgets.QHBoxLayout(self.add_row)
        add_layout.setContentsMargins(NotebookCell.GUTTER_WIDTH + 4, 3, 4, 3)
        add_layout.setSpacing(4)
        self.add_button = self._make_add_button("＋ Code", "code")
        self.add_markdown_button = self._make_add_button("＋ Markdown", "markdown")
        add_layout.addWidget(self.add_button)
        add_layout.addWidget(self.add_markdown_button)
        add_layout.addStretch(1)

        self.splitter.addWidget(self.terminal)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(1, True)
        self.splitter.setSizes([620, 130])

    def _build_toolbar(self) -> QtWidgets.QWidget:
        """Return the one-row notebook toolbar.

        Everything a notebook needs that is not a per-cell action -- run every
        cell, restart the kernel, drop the outputs, hide the terminal -- lives
        in a single 22px strip, so no cell has to carry that chrome.
        """
        bar = QtWidgets.QWidget(self)
        bar.setObjectName("notebook_toolbar")
        bar.setFixedHeight(22)
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(2, 0, 2, 0)
        row.setSpacing(1)

        def button(text: str, tip: str, slot) -> QtWidgets.QToolButton:
            widget = QtWidgets.QToolButton(bar)
            widget.setText(text)
            widget.setAutoRaise(True)
            widget.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            widget.setToolTip(tip)
            widget.clicked.connect(slot)
            row.addWidget(widget)
            return widget

        self.run_all_button = button(
            "▶▶ Run all", "Run every code cell from the top", lambda: self.run_all()
        )
        self.restart_button = button(
            "⟳ Restart",
            "Discard the kernel's variables and start a fresh one",
            lambda: self.restart_kernel(),
        )
        self.clear_button = button(
            "⌫ Clear",
            "Clear the output of every cell",
            lambda: self.clear_all_outputs(),
        )
        row.addStretch(1)

        self.terminal_button = QtWidgets.QToolButton(bar)
        self.terminal_button.setText("▤ Terminal")
        self.terminal_button.setAutoRaise(True)
        self.terminal_button.setCheckable(True)
        self.terminal_button.setChecked(True)
        self.terminal_button.setToolTip(
            "Show the kernel terminal below the cells (it shares the notebook's variables)"
        )
        self.terminal_button.toggled.connect(self._on_terminal_toggled)
        row.addWidget(self.terminal_button)
        return bar

    def _on_terminal_toggled(self, visible: bool) -> None:
        """Show or hide the attached terminal, giving the cells its height."""
        if self.terminal is None:
            return
        self.terminal.setVisible(visible)
        if visible and self.splitter.sizes()[1] == 0:
            total = sum(self.splitter.sizes()) or self.height()
            self.splitter.setSizes([max(1, total - 130), 130])

    def restart_kernel(self) -> None:
        """Replace the shell with a fresh one and clear every prompt.

        The cells keep their source; only the kernel's state is discarded, so
        the notebook can be re-run from a known-empty namespace.
        """
        self._shell = self._make_shell()
        if self.terminal is not None:
            self.terminal.shell = self._shell
            self.terminal.append_output("\n— kernel restarted —\n")
        for cell in self._cells:
            cell.execution_count = None
            cell.set_prompt(None)

    def clear_all_outputs(self) -> None:
        """Clear every cell's output panel and prompt."""
        for cell in self._cells:
            cell.clear_output()
        self._mark_modified()

    def _make_add_button(self, text: str, cell_type: str) -> QtWidgets.QToolButton:
        """Return a compact button appending a cell of *cell_type* at the end."""
        button = QtWidgets.QToolButton(self.add_row)
        button.setText(text)
        button.setAutoRaise(True)
        button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        button.setToolTip(f"Add a {cell_type} cell at the end")
        button.clicked.connect(
            lambda _checked=False, kind=cell_type: self._on_add_cell_clicked(kind)
        )
        return button

    def _make_terminal(self):
        """Build the REPL console attached below the cells.

        The console shares this notebook's :class:`Shell`, so commands typed in
        the terminal and cells executed above read and write the same
        namespace -- one kernel, two surfaces.
        """
        from chisurf.gui.chinsole import Chinsole, ConsoleConfig, ConsoleRole

        terminal = Chinsole(
            ConsoleConfig(
                role=ConsoleRole.INTERACTIVE,
                banner="Notebook kernel — commands typed here share variables with the cells above.\n",
                history_path=False,
            ),
            parent=self,
        )
        terminal.shell = self._shell
        return terminal

    def _rebuild_stack(self) -> None:
        """Rebuild the cell stack from ``self._cells`` with insert gaps.

        A compact ``＋`` button sits between every pair of cells so a new cell
        can be added *between* existing ones, not just at the end. The stack is
        rebuilt on add/remove only; individual cell widgets keep their state.
        """
        while self.stack.count():
            item = self.stack.takeAt(0)
            widget = item.widget()
            if (
                widget is not None
                and widget.objectName() == "notebook_insert_button"
            ):
                widget.hide()
                widget.deleteLater()
        for index, cell in enumerate(self._cells):
            if index > 0:
                self.stack.addWidget(self._make_insert_button(index))
            self.stack.addWidget(cell)
        self.stack.addWidget(self.add_row)
        self.stack.addStretch(1)

    def _make_insert_button(self, index: int) -> QtWidgets.QToolButton:
        """Return a hairline ``＋`` strip that adds a cell before *index*.

        The strip is deliberately the thinnest thing that can still be clicked:
        it sits between every pair of cells, so its height is paid once per
        cell boundary over the whole notebook.
        """
        button = QtWidgets.QToolButton(self.container)
        button.setObjectName("notebook_insert_button")
        button.setText("＋")
        button.setAutoRaise(True)
        button.setFixedHeight(9)
        button.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        font = button.font()
        font.setPointSizeF(max(6.0, font.pointSizeF() - 3.0))
        button.setFont(font)
        button.setStyleSheet(
            "QToolButton#notebook_insert_button { color: #bbb; border: none; }"
            "QToolButton#notebook_insert_button:hover"
            " { color: #333; background: palette(midlight); }"
        )
        button.setToolTip("Insert a code cell between these two cells")
        button.clicked.connect(
            lambda _checked=False, i=index: self._on_insert_cell_clicked(i)
        )
        return button

    def _on_insert_cell_clicked(self, index: int) -> None:
        """Add a code cell right before the cell at *index* and focus it."""
        cell = self.add_cell(cell_type="code", after_index=index - 1)
        self._focus_cell = cell
        cell.editor.setFocus()

    def _on_add_cell_clicked(self, cell_type: str = "code") -> None:
        """Add a cell of *cell_type* right after the last cell."""
        cell = self.add_cell(cell_type=cell_type)
        self._focus_cell = cell
        if cell_type == "markdown":
            cell._set_edit_mode(True)
        self._focus_cell.editor.setFocus()

    # ------------------------------------------------------------------
    # the shell (in-process execution)
    # ------------------------------------------------------------------

    def _make_shell(self) -> Shell:
        """Return the persistent in-process shell this notebook runs on.

        Returns
        -------
        Shell
        """
        shell = Shell(
            user_ns={
                "__name__": "__main__",
                "__file__": self.current_file or "",
                "cs": cs,
                "np": __import__("numpy"),
                "os": os,
                "sys": sys,
            },
            write=self._on_write,
            display=self._on_display,
            history=HistoryManager(path=False),
        )
        try:
            shell.enable_matplotlib("inline")
        except Exception as exc:  # noqa: BLE001 - a notebook must still open
            logging.log(1, f"notebook: could not enable matplotlib inline: {exc}")
        return shell

    def _on_write(self, stream_name: str, text: str) -> None:
        """Route stream output to the executing cell and the attached terminal."""
        cell = self._active_cell
        if cell is not None:
            cell.output.append_text(text, kind=stream_name)
        if self.terminal is not None:
            self.terminal.pump.write(stream_name, text)

    def _on_display(
        self,
        data: dict,
        metadata: dict,
        kind: str,
        execution_count: int | None,
    ) -> None:
        """Route a rich display to the cell that produced it.

        A figure belongs to **one** surface: the cell's output when a cell is
        running, and the terminal only when the user typed the command there.
        Mirroring an inline figure into both painted the same plot twice and
        cost the terminal its whole height.
        """
        cell = self._active_cell
        if cell is not None:
            cell.output.append_mime(data, metadata, kind, execution_count)
            return
        if self.terminal is not None:
            self.terminal._on_display(data, metadata, kind, execution_count)

    # ------------------------------------------------------------------
    # cell management
    # ------------------------------------------------------------------

    def cells(self) -> list[NotebookCell]:
        """Return the notebook's cells, top to bottom."""
        return list(self._cells)

    def code_cells(self) -> list[NotebookCell]:
        """Return the executable code cells."""
        return [cell for cell in self._cells if cell.cell_type == "code"]

    def add_cell(
        self,
        cell_type: str = "code",
        source: str = "",
        outputs: list[dict] | None = None,
        cell_metadata: dict | None = None,
        source_node: dict | None = None,
        execution_count: int | None = None,
        after_index: int | None = None,
    ) -> NotebookCell:
        """Insert a cell widget into the stack.

        Parameters
        ----------
        cell_type : str, optional
            The kind of cell: ``"code"``, ``"markdown"`` or ``"raw"``.
        source : str, optional
            Initial cell source text.
        outputs : list of dict, optional
            nbformat output nodes to render in the cell.
        cell_metadata : dict, optional
            The original nbformat node this cell was created from; kept so a
            save round-trip preserves the cell's other metadata.
        source_node : dict, optional
            Original nbformat node for provenance.
        execution_count : int, optional
            Prompt number to show for the cell.
        after_index : int, optional
            The index of the cell the new one is inserted right after. When
            omitted the cell is appended at the end.

        Returns
        -------
        NotebookCell
        """
        cell = NotebookCell(
            cell_type=cell_type,
            source=source,
            outputs=outputs,
            cell_metadata=cell_metadata,
            parent=self.container,
        )
        cell._source_node = source_node
        cell.execution_count = execution_count
        cell.set_prompt(execution_count)
        cell.runRequested.connect(self.run_cell)
        cell.removeRequested.connect(self.remove_cell)
        cell.textChanged.connect(self._on_cell_text_changed)
        cell.editor.statusChanged.connect(
            lambda _status, c=cell: self._on_cell_status_changed(c)
        )
        cell.editor.definitionRequested.connect(self.definitionRequested.emit)
        for combo in ("Shift+Return", "Ctrl+Return", "Meta+Return"):
            shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(combo), cell.editor)
            shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda _c=cell: self.runRequested.emit(cell))

        if after_index is not None and 0 <= after_index < len(self._cells):
            self._cells.insert(after_index + 1, cell)
        else:
            self._cells.append(cell)
        self._rebuild_stack()
        cell._update_height()
        self.cellAdded.emit(cell)
        self._mark_modified()
        return cell

    def remove_cell(self, cell: NotebookCell) -> None:
        """Remove *cell* from the notebook."""
        if cell not in self._cells:
            return
        self._cells.remove(cell)
        for shortcut in list(cell.editor.findChildren(QtWidgets.QShortcut)):
            shortcut.deleteLater()
        # Unparent before deleting: a widget that is merely out of the layout
        # but still a child of the container keeps painting at its last
        # geometry until the deferred delete runs, which shows up as a ghost
        # cell overlapping the top of the notebook.
        cell.setParent(None)
        cell.deleteLater()
        self._rebuild_stack()
        if self._active_cell is cell:
            self._active_cell = None
        if self._focus_cell is cell:
            self._focus_cell = None
        self._mark_modified()
        self._emit_changed()

    def _clear_cells(self) -> None:
        """Remove every cell widget."""
        while self._cells:
            cell = self._cells.pop(0)
            cell.setParent(None)
            cell.deleteLater()
        self._active_cell = None
        self._focus_cell = None
        self._rebuild_stack()

    # ------------------------------------------------------------------
    # notebook loading / saving
    # ------------------------------------------------------------------

    def new_notebook(self) -> None:
        """Replace the document with a fresh empty notebook (one code cell)."""
        _ensure_nbformat()
        self._clear_cells()
        nb = nbformat.v4.new_notebook()
        nb.metadata.setdefault("kernelspec", {"display_name": "Python 3", "language": "python", "name": "python3"})
        nb.metadata.setdefault("language_info", {"name": "python"})
        nb.cells = [nbformat.v4.new_code_cell(source="")]
        self._source_nb = nb
        for node in nb.cells:
            self.add_cell(
                cell_type=node.get("cell_type", "code"),
                source=_cell_source(node),
                outputs=node.get("outputs") or [],
                cell_metadata=node.get("metadata") or {},
                source_node=node,
                execution_count=node.get("execution_count"),
            )
        self._beacon.setModified(False)

    def open_file(self, path: str) -> bool:
        """Load a notebook from *path*.

        Parameters
        ----------
        path : str

        Returns
        -------
        bool
            ``True`` on success; ``False`` when ``path`` is not a valid ipynb
            (the Raw JSON fallback is then the plain-text tab's job).
        """
        _ensure_nbformat()
        try:
            nb = nbformat.read(str(path), as_version=4)
        except Exception as exc:  # noqa: BLE001 - a corrupt notebook is a text file
            logging.log(1, f"Could not load notebook {path}: {exc}")
            return False
        self._clear_cells()
        self._source_nb = nb
        self.set_current_file(str(path))
        for node in nb.cells:
            self.add_cell(
                cell_type=node.get("cell_type", "code"),
                source=_cell_source(node),
                outputs=node.get("outputs") or [],
                cell_metadata=node.get("metadata") or {},
                source_node=node,
                execution_count=node.get("execution_count"),
            )
        if not self._cells:
            self.add_cell(cell_type="code", source="")
        self._beacon.setModified(False)
        self._emit_changed()
        return True

    def reload(self) -> None:
        """Re-read the notebook from disk (or reset when untitled)."""
        if self.current_file and os.path.isfile(self.current_file):
            self.open_file(self.current_file)
        else:
            self.new_notebook()

    def to_nbformat(self) -> dict:
        """Return the current document as a nbformat notebook node.

        Returns
        -------
        dict
        """
        _ensure_nbformat()
        source_nb = self._source_nb
        if source_nb is None:
            nb = nbformat.v4.new_notebook()
        else:
            nb = copy.deepcopy(source_nb)
            nb["cells"] = []
        nb["cells"] = [cell.to_nbformat_node() for cell in self._cells]
        return nbformat.from_dict(nb)

    def save_to(self, path: str) -> None:
        """Write the notebook to *path* as an ipynb file."""
        _ensure_nbformat()
        nb = self.to_nbformat()
        payload = nbformat.writes(nb, sort_keys=False, indent=1)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(payload)
        self._source_nb = nb
        self.set_current_file(path)
        self._beacon.setModified(False)
    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------

    def run_cell(self, cell: NotebookCell) -> None:
        """Run a cell: render markdown, or execute code in the notebook shell.

        Parameters
        ----------
        cell : NotebookCell
            The cell to run.
        """
        if cell.cell_type == "markdown":
            cell.render_markdown()
            return
        if self._shell is None or cell.cell_type != "code":
            return
        if self._shell._busy:
            self._write_busy(cell)
            return
        index = self._cells.index(cell)
        source = cell.editor.toPlainText()
        cell.clear_output()
        count = self._shell.execution_count
        cell.execution_count = count
        self._active_cell = cell
        cell.set_prompt(count)
        if self.terminal is not None:
            self.terminal.pump.begin_cell()
            if source.strip():
                self._echo_to_terminal(count, source)
        self.runStateChanged.emit(True)
        try:
            self._shell.run_cell(
                source,
                store_history=True,
                filename=self._cell_source_name(index),
            )
        finally:
            self._active_cell = None
            if self.terminal is not None:
                self.terminal.pump.end_cell()
                self._refresh_terminal_prompt()
            self.runStateChanged.emit(False)
        self._mark_modified()

    def _terminal_prompt_is_idle(self) -> bool:
        """Return whether the terminal shows an empty prompt we may write onto."""
        view = getattr(self.terminal, "view", None)
        if view is None or not getattr(view, "shows_prompt", False):
            return False
        try:
            return not view.input_buffer()
        except Exception:  # noqa: BLE001 - a console without a prompt is fine
            return False

    def _echo_to_terminal(self, count: int, source: str) -> None:
        """Log which cell ran onto the terminal's live prompt.

        When the terminal is sitting at an untouched ``In [n]:`` prompt the
        echo is written straight onto it, exactly as if the line had been
        typed; only when the user has something half-typed there does the echo
        carry its own prompt, so their input is not swallowed.
        """
        line = _echo_line(source)
        if self._terminal_prompt_is_idle():
            self.terminal.append_output(f"{line}\n")
        else:
            self.terminal.append_output(f"In [{count}]: {line}\n")

    def _refresh_terminal_prompt(self) -> None:
        """Move the terminal's prompt to the next execution count."""
        if not self._terminal_prompt_is_idle():
            return
        with contextlib.suppress(Exception):
            self.terminal.view.show_prompt(self._shell.execution_count)

    def run_current_cell(self) -> None:
        """Run the cell that currently holds focus."""
        cell = self._focus_cell or self._active_cell
        if cell is None and self._cells:
            cell = self._cells[-1]
        if cell is not None:
            self.run_cell(cell)

    def run_all(self) -> None:
        """Run every code cell, top to bottom."""
        for cell in self.code_cells():
            self.run_cell(cell)

    def _write_busy(self, cell: NotebookCell) -> None:
        """Tell the user a cell is still running."""
        cell.output.append_text("the notebook is still running a cell; wait for it to finish\n", kind="stderr")
        cell.output.setVisible(True)

    def _cell_source_name(self, index: int) -> str:
        """Return the traceback-facing name for *index*."""
        base = self.current_file or "notebook"
        return f"{base}:<{index + 1}>"

    # ------------------------------------------------------------------
    # host facade (matches TextEditor's duck-type surface)
    # ------------------------------------------------------------------

    def document(self) -> QtGui.QTextDocument:
        """Return the dirty-tracking beacon document.

        Returns
        -------
        QtGui.QTextDocument
        """
        return self._beacon

    def set_current_file(self, path: str | None) -> None:
        """Set the path this notebook is stored at."""
        path_str = str(path) if path else ""
        if self.current_file == path_str:
            return
        self.current_file = path_str
        self.filePathChanged.emit(path_str)
        self._emit_changed()

    def line_column(self) -> tuple[int, int]:
        """Return the focused cell's cursor position (one-based line, column)."""
        cell = self._focus_cell or (self._cells[0] if self._cells else None)
        if cell is None:
            return 1, 0
        return cell.editor.line_column()

    def text(self) -> str:
        """Return the flattened source of all cells."""
        return self.toPlainText()

    def toPlainText(self) -> str:
        """Return the flattened source of all cells (facade compatibility)."""
        return "\n\n".join(cell.editor.toPlainText() for cell in self._cells)

    def setText(self, text: str) -> None:
        """Replace the notebook from *text* (a JSON ipynb or plain source)."""
        _ensure_nbformat()
        try:
            nb = nbformat.reads(text, as_version=4)
        except Exception:
            self._clear_cells()
            self._source_nb = nbformat.v4.new_notebook()
            self.add_cell(cell_type="code", source=text)
            self._mark_modified()
            self._emit_changed()
            return
        self._source_nb = nb
        self._clear_cells()
        for node in nb.cells:
            self.add_cell(
                cell_type=node.get("cell_type", "code"),
                source=_cell_source(node),
                outputs=node.get("outputs") or [],
                cell_metadata=node.get("metadata") or {},
                source_node=node,
                execution_count=node.get("execution_count"),
            )
        self._mark_modified()
        self._emit_changed()

    def refresh_symbols(self) -> list:
        """Return the symbol outline; notebooks have none per cell.

        Returns
        -------
        list
        """
        return []

    def symbols(self) -> list:
        """Return the current (empty) symbol list."""
        return []

    def goto_line_column(self, line: int, column: int = 0) -> None:
        """Move the focused cell's cursor without emitting nav history."""
        cell = self._focus_cell or (self._cells[0] if self._cells else None)
        if cell is not None:
            cell.editor.goto_line_column(line, column, record=False)

    def _find_bar(self):
        """Return the focused cell's find bar, mirroring TextEditor."""
        cell = self._focus_cell or (self._cells[0] if self._cells else None)
        if cell is not None:
            return cell.editor._find_bar
        return None

    # ------------------------------------------------------------------
    # change propagation
    # ------------------------------------------------------------------

    def _mark_modified(self) -> None:
        """Mark the document dirty (used by run / cell edits / saves)."""
        if not self._beacon.isModified():
            self._beacon.setModified(True)

    def _on_cell_text_changed(self) -> None:
        """A cell's source was edited: mark dirty and debounce notifications."""
        self._mark_modified()
        self._status_timer.start()

    def _on_cell_status_changed(self, cell: NotebookCell) -> None:
        """Remember the focused cell and refresh the host status line."""
        if cell is not self._focus_cell:
            self._focus_cell = cell
        self._emit_status_changed()

    def _emit_changed(self) -> None:
        """Notify the host that content changed."""
        self._emit_status_changed()
        self.textChanged.emit()

    def _emit_status_changed(self) -> None:
        """Emit the host-visible status payload."""
        cell = self._focus_cell or (self._cells[0] if self._cells else None)
        line, column = (cell.editor.line_column() if cell is not None else (1, 0))
        self.statusChanged.emit(
            {
                "file": self.current_file or "",
                "line": line,
                "column": column,
                "modified": self._beacon.isModified(),
                "language": self.language,
            }
        )

    def _emit_output_marker(self) -> None:
        """Legacy no-op retained for parity with the text editor surface."""

    # ------------------------------------------------------------------
    # convenience
    # ------------------------------------------------------------------

    def save(self) -> bool:
        """Save to the current path, or return ``False`` when untitled.

        Returns
        -------
        bool
        """
        if not self.current_file:
            return False
        try:
            self.save_to(self.current_file)
        except OSError as exc:
            logging.log(1, f"Error saving notebook {self.current_file}: {exc}")
            return False
        return True


def _shipped_notebooks_dir() -> pathlib.Path | None:
    """Return the checkout's curated ``examples/notebooks`` directory.

    The notebooks are the shipped examples that ChiSurf's source tree carries
    (mirroring how ``docs_root`` resolves the documentation). Resolved from the
    installed package file so the same lookup works from a source checkout; a
    packaged install without the examples directory yields ``None`` and the
    menu stays empty.
    """
    here = pathlib.Path(cs.__file__).resolve().parent
    candidate = here.parent / "examples" / "notebooks"
    if candidate.is_dir():
        return candidate
    return None


def shipped_notebooks() -> list[pathlib.Path]:
    """Return the curated shipped notebooks, sorted by name.

    Returns
    -------
    list of pathlib.Path
        The ``*.ipynb`` files under ``examples/notebooks`` (top level only),
        or an empty list when that directory is absent.
    """
    base = _shipped_notebooks_dir()
    if base is None:
        return []
    notebooks = sorted(base.glob("*.ipynb"))
    return [path for path in notebooks if path.is_file()]
