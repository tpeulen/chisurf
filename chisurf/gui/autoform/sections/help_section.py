"""Reusable AutoForm section: a compact ``?`` help button opening a modal.

The ChiSurf UI rule is to keep forms uncluttered — short labels, detail in
tooltips, and *longer* explanations behind a small ``?`` button that opens a
modal help popup rather than inline paragraphs of text. This section renders that
button so any view can attach contextual help.

Declare it in a view spec as a custom section::

    {"type": "custom", "key": "help",
     "options": {"title": "Synthetic decay — help",
                 "text": "Markdown help body…"}}

- ``text`` — Markdown/plain help body shown in the modal (or ``resource`` — a
  path to a ``.md``/``.txt``/``.html`` file read at click time; ``text`` wins).
- ``title`` — modal window title (default ``"Help"``).
- ``label`` — button glyph (default ``"?"``).
- ``align`` — ``"right"`` (default) right-aligns the button; ``"left"`` / ``"full"``.
"""

from __future__ import annotations

import pathlib
from typing import Any

from qtpy import QtWidgets

from .registry import register_section


@register_section("help")
class HelpButton(QtWidgets.QWidget):
    """A small ``?`` button that opens a modal help dialog."""

    is_form_field = False

    def __init__(self, model=None, target: str = "", **options: Any):
        super().__init__()
        self._text = str(options.get("text", ""))
        self._resource = str(options.get("resource", ""))
        self._title = str(options.get("title", "Help"))
        align = str(options.get("align", "right"))

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if align == "right":
            layout.addStretch(1)
        self.button = QtWidgets.QToolButton()
        self.button.setText(str(options.get("label", "?")))
        self.button.setToolTip("Show help")
        self.button.setAutoRaise(True)
        self.button.clicked.connect(self._show)
        layout.addWidget(self.button)
        if align == "left":
            layout.addStretch(1)

    def _content(self) -> str:
        if self._text:
            return self._text
        if self._resource:
            path = pathlib.Path(self._resource)
            if path.is_file():
                return path.read_text(encoding="utf-8")
        return "No help available."

    def _show(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self._title)
        dialog.resize(560, 480)
        layout = QtWidgets.QVBoxLayout(dialog)
        browser = QtWidgets.QTextBrowser()
        browser.setOpenExternalLinks(True)
        content = self._content()
        is_html = self._resource.lower().endswith((".html", ".htm"))
        if is_html:
            browser.setHtml(content)
        elif hasattr(browser, "setMarkdown"):
            browser.setMarkdown(content)
        else:  # very old Qt — show the Markdown source as plain text
            browser.setPlainText(content)
        layout.addWidget(browser, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec_()
