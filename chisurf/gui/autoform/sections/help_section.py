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
  A *relative* ``resource`` is resolved next to the view spec that declares it
  (the model's ``_view_json``, else the model's module directory), so a plugin
  ships its help file beside its ``view.json``.
- ``title`` — modal window title (default ``"Help"``).
- ``label`` — button glyph (default ``"?"``).
- ``align`` — ``"right"`` (default) right-aligns the button; ``"left"`` / ``"full"``.

Markdown links in the body are live. A link naming a documentation page — say
``[the concept](docs/concepts/pair_correlation.md)`` — opens the ChiSurf
documentation browser at that page; ``http``/``https``, a ``doi:`` and a bare
``10.xxxx/…`` DOI open in the system browser. See
:mod:`chisurf.gui.widgets.tools.doc_links`.
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
        self._model = model
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

    def _resource_path(self) -> pathlib.Path | None:
        """Resolve ``resource`` to an existing file.

        An absolute (or CWD-relative) path is used as given. A *relative* path is
        resolved next to the view spec it was authored in — the model's
        ``_view_json`` when it exposes one, else the directory of the model's
        module — so a plugin can ship its help text beside its ``view.json``
        without knowing the working directory.
        """
        if not self._resource:
            return None
        path = pathlib.Path(self._resource)
        if path.is_file():
            return path
        if path.is_absolute():
            return None
        bases: list[pathlib.Path] = []
        view_json = getattr(self._model, "_view_json", None)
        if view_json:
            bases.append(pathlib.Path(view_json).parent)
        module = getattr(type(self._model), "__module__", "") if self._model is not None else ""
        module_file = getattr(__import__("sys").modules.get(module, None), "__file__", None)
        if module_file:
            bases.append(pathlib.Path(module_file).parent)
        for base in bases:
            candidate = base / path
            if candidate.is_file():
                return candidate
        return None

    def _content(self) -> str:
        if self._text:
            return self._text
        path = self._resource_path()
        if path is not None:
            return path.read_text(encoding="utf-8")
        return "No help available."

    def _show(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(self._title)
        dialog.resize(560, 480)
        layout = QtWidgets.QVBoxLayout(dialog)
        browser = QtWidgets.QTextBrowser()
        # Links in a help page are cross-references, not decoration: a document
        # opens in the ChiSurf documentation browser at that page, a web address
        # or a DOI opens in the system browser.
        from chisurf.gui.widgets.tools.doc_links import wire_text_browser

        resource = self._resource_path()
        wire_text_browser(browser, resource.parent if resource is not None else None)
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
