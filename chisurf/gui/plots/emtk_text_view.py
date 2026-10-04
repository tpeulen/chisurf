r"""emtk-drawn read-only text views for the fit Info plot.

The Info page's report and the Export tab's mmCIF preview used to be white
Qt ``QPlainTextEdit``\ s pasted into an emtk-drawn fit window — the last
classic-Qt content inside the plot surface. Both are emtk's read-only
``TextEditor`` now, hosted by emtk's Qt ``ControlHost`` (the same host every
other emtk surface in the window uses), wrapped so the previous
``QPlainTextEdit``-style call surface (``setPlainText`` / ``toPlainText``)
keeps working for the code that fills them and the tests that read them.

A read-only emtk editor still selects, copies, searches and scrolls, which
is exactly what a fit report needs; an environment without emtk falls back
to a plain Qt editor so the page keeps working.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

logger = logging.getLogger(__name__)


class EmtkTextView(QtWidgets.QWidget):
    """A read-only text view drawn by emtk with a Qt text-edit call surface."""

    def __init__(self, parent=None, *, font_pt: float | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._editor = None
        self._host = None
        self._plain = None
        try:
            from emtk.qt_host import ControlHost
            from emtk.widgets.text_editor import TextEditor

            self._editor = TextEditor("", None, read_only=True)
            # A report is not code: no gutter numbers, no highlighted line.
            self._editor.config.show_line_numbers = False
            self._editor.config.highlight_current_line = False
            self._editor.config.show_matching_brackets = False
            if font_pt is None:
                self._host = ControlHost(self._editor)
            else:
                self._host = ControlHost(self._editor, font_pt=float(font_pt))
            layout.addWidget(self._host, 1)
        except ImportError as problem:
            logger.warning("emtk text view unavailable (%s); Qt fallback in use", problem)
            self._plain = QtWidgets.QPlainTextEdit()
            self._plain.setReadOnly(True)
            layout.addWidget(self._plain, 1)

    # -- the QPlainTextEdit surface ---------------------------------------
    def setPlainText(self, text: str) -> None:
        """Replace the report's text."""
        if self._editor is not None:
            self._editor.set_text(str(text))
            self._request_repaint()
        elif self._plain is not None:
            self._plain.setPlainText(str(text))

    def toPlainText(self) -> str:
        """The report's text."""
        if self._editor is not None:
            return self._editor.text
        if self._plain is not None:
            return self._plain.toPlainText()
        return ""

    def _request_repaint(self) -> None:
        """Schedule a Qt repaint; the host draws the editor's current state."""
        host = self._host
        if host is not None:
            update = getattr(host, "update", None)
            if callable(update):
                update()
