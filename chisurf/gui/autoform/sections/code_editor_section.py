"""AutoForm ``code_editor`` section — a syntax-highlighting text editor.

Declared in a ``.view.json`` as::

    {"type": "custom", "key": "code_editor", "target": "script",
     "title": "Script", "options": {"language": "python", "height": 260}}

The bound attribute holds the text: it is read when the section is built and
written back on every edit, so a model that has a ``script`` string gets a
real editor -- colours, multiple cursors, undo, find -- for one line of JSON.

Where the editor comes from
---------------------------
It is not a ``QPlainTextEdit``. The widget is
:class:`cmtk.widgets.text_editor.TextEditor`, the port of
ImGuiColorTextEdit that chimol draws in its own viewport chrome, hosted in a
``QWidget`` by :class:`cmtk.qt_host.ControlHost`.

That indirection is the point rather than an accident. The alternative --
a Qt editor here and the ported one in the viewport -- is two editors with two
sets of keybindings, two highlighters and two ideas of what Tab does, which
diverge the first time either is touched. Hosting the same object means the
script panel in a fitting model and the script panel in the 3-D viewer are the
same editor, and a fix to one is a fix to both.

Options
-------
``language`` : str, default ``"python"``
    One of the names in
    :func:`cmtk.widgets.text_editor.shipped_languages`, case-insensitive
    (``python``, ``c``, ``c++``, ``glsl``, ``lua``, ``json``, ``markdown``,
    ``sql``, ``chimol``), or ``"none"`` for no highlighting.
``height`` : int, default 240
    Minimum height in pixels.
``read_only`` : bool, default ``False``
``show_whitespace`` : bool, default ``False``
``tab_size`` : int, default 4
``handle`` : str, optional
    Attribute name under which the widget is published on the model
    (``model.<handle> = widget``), for code that needs the editor itself --
    to add error markers, for instance.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from .registry import register_section

logger = logging.getLogger(__name__)


def _make_editor(text: str, options: dict):
    """Build a configured :class:`TextEditor`, or raise ``ImportError``."""
    from cmtk.widgets import text_editor as te

    wanted = str(options.get("language", "python")).strip().lower()
    language = None
    if wanted not in ("", "none"):
        for name, one in te.shipped_languages().items():
            if name.lower() == wanted:
                language = one
                break
        else:
            logger.warning("code_editor: unknown language %r, highlighting off", wanted)

    editor = te.TextEditor(text, language, read_only=bool(options.get("read_only", False)))
    editor.config.tab_size = int(options.get("tab_size", 4))
    editor.config.show_spaces = bool(options.get("show_whitespace", False))
    editor.config.show_tabs = editor.config.show_spaces
    return editor


class CodeEditorWidget(QtWidgets.QWidget):
    """The hosted editor plus the one-line status strip under it.

    The strip is not decoration: with multiple cursors and a language that can
    be switched, "where am I and what is this being read as" stops being
    obvious from the text alone, and every editor that omits it grows a bug
    report asking why Tab inserted four spaces.
    """

    #: AutoForm.refresh_plots() calls refresh() on sections that ask for it.
    AUTOFORM_REFRESH = True

    def __init__(self, model, target: str, **options) -> None:
        super().__init__()
        self._model = model
        self._target = target
        self._options = dict(options)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.editor = None
        self._host = None
        try:
            self.editor = _make_editor(self._read(), self._options)
            from cmtk.qt_host import ControlHost

            self._host = ControlHost(self.editor, on_change=self._on_change)
            self._host.setMinimumHeight(int(self._options.get("height", 240)))
            layout.addWidget(self._host, 1)
        except ImportError as problem:
            logger.warning("code_editor unavailable (%s); falling back to plain text", problem)
            self._plain = QtWidgets.QPlainTextEdit(self._read())
            self._plain.textChanged.connect(self._on_plain_change)
            self._plain.setMinimumHeight(int(self._options.get("height", 240)))
            layout.addWidget(self._plain, 1)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.status)
        self._update_status()

        handle = self._options.get("handle")
        if handle:
            setattr(model, str(handle), self)

    # -- model binding -------------------------------------------------- #
    def _read(self) -> str:
        """The bound attribute's current value, as text."""
        value = getattr(self._model, self._target, "")
        if callable(value):
            value = value()
        return "" if value is None else str(value)

    def _write(self, text: str) -> None:
        """Write the text back to the model, if the attribute is settable."""
        try:
            setattr(self._model, self._target, text)
        except AttributeError:
            # A read-only property is a legitimate binding -- a model that
            # generates a script for display. Log once at debug and keep the
            # editor usable rather than raising on every keystroke.
            logger.debug("code_editor: %s is not settable", self._target)

    def _on_change(self, editor) -> None:
        """Called by the host after an event the editor consumed."""
        self._write(editor.text)
        self._update_status()

    def _on_plain_change(self) -> None:
        """Fallback path: the plain-text editor changed."""
        self._write(self._plain.toPlainText())

    def refresh(self) -> None:
        """Re-read the model, unless the user is mid-edit.

        A refresh that overwrites what somebody is typing is the classic way a
        bound editor becomes unusable, so the text is only pulled in when it
        actually differs *and* the editor has not been modified since it was
        last written.
        """
        if self.editor is None:
            return
        text = self._read()
        if text != self.editor.text and not self.editor.modified:
            self.editor.set_text(text)
            if self._host is not None:
                self._host.update()
        self._update_status()

    # -- status --------------------------------------------------------- #
    def _update_status(self) -> None:
        """Redraw the caption under the editor."""
        if self.editor is None:
            return
        line, index = self.editor.cursors.main.end
        extra = len(self.editor.cursors) - 1
        carets = f", +{extra} cursors" if extra else ""
        self.status.setText(
            f"{self.editor.language_name}  ·  "
            f"line {line + 1}, col {index + 1}{carets}  ·  "
            f"{self.editor.line_count} lines"
        )

    # -- public surface ------------------------------------------------- #
    @property
    def text(self) -> str:
        """The editor's contents."""
        if self.editor is not None:
            return self.editor.text
        return self._plain.toPlainText()

    def set_text(self, text: str) -> None:
        """Replace the contents."""
        if self.editor is not None:
            self.editor.set_text(str(text))
            if self._host is not None:
                self._host.update()
        else:
            self._plain.setPlainText(str(text))
        self._write(str(text))
        self._update_status()

    def mark_line(self, line: int, tooltip: str = "", error: bool = True) -> None:
        """Flag a line -- a syntax error, a breakpoint, a failed step."""
        if self.editor is None:
            return
        colour = (220, 90, 80) if error else (120, 190, 120)
        self.editor.add_marker(int(line), colour, colour, str(tooltip))
        if self._host is not None:
            self._host.update()

    def clear_marks(self) -> None:
        """Remove every marker."""
        if self.editor is not None:
            self.editor.clear_markers()
            if self._host is not None:
                self._host.update()


@register_section("code_editor")
def _code_editor_section_factory(model, target: str, **options):
    """Custom-section factory for the syntax-highlighting code editor."""
    return CodeEditorWidget(model, target, **options)


__all__ = ["CodeEditorWidget"]
