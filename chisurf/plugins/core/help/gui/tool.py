"""Qt host adapter of the ChiSurf help browser: the emtk app in a dock window of the Qt window.

The browser is the emtk app (:mod:`~chisurf.plugins.core.help.gui.help_app`); the emtk shell
opens it as a dock. The Qt main window (``--qt``) and its ``?`` links host the same app in a
``ControlHost`` through :class:`HelpEmtkTool`. The legacy Qt ``HelpWidget`` (a ``QTextBrowser``
reader) was retired 2026-10-13: its behaviour lives in the emtk app, its tests were ported to it
(``test_widgets.py``, ``test_ask_panel_widget.py``, ``test_figures.py``).
"""

from __future__ import annotations

import pathlib
from typing import Any

from chisurf.core.glyphs import Glyphs
from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

__all__ = ["HelpEmtkTool"]


class HelpEmtkTool(ChisurfDockTool):
    """Modern Documentation Browser and AI Assistant implemented in pure EMTK."""

    name = "Documentation"

    def __init__(
        self, parent: Any = None, *, path: str | pathlib.Path | None = None, **kwargs: Any
    ) -> None:
        super().__init__(parent, **kwargs)

        from chisurf.plugins.core.help.gui.help_app import WINDOW_BG, HelpApp

        self.setWindowTitle(f"{Glyphs.BOOK} ChiSurf Help")
        self.app = HelpApp()
        self.resize(*self.app.window_size)

        self.model = self.app.model
        if path:
            self.model.open_page(path)

        try:
            from emtk.qt_host import ControlHost

            self.host = ControlHost(self.app, background=WINDOW_BG[:3])
            self.setCentralWidget(self.host)
        except Exception:
            self.host = None

    def open_doc(self, path: str | pathlib.Path, anchor: str | None = None) -> bool:
        return self.model.open_page(path, anchor=anchor)

    def show_doc(self, path: str | pathlib.Path, anchor: str | None = None) -> bool:
        return self.model.open_page(path, anchor=anchor)

    def open_path(self, path: str | pathlib.Path, anchor: str | None = None) -> bool:
        return self.model.open_page(path, anchor=anchor)

    def open_markdown_path(self, path: str | pathlib.Path, anchor: str | None = None) -> bool:
        return self.model.open_page(path, anchor=anchor)

    def _open_document_path(self, path: str | pathlib.Path, anchor: str | None = None) -> bool:
        return self.open_markdown_path(path, anchor)

    class _FilterProxy:
        def __init__(self, model: Any) -> None:
            self._model = model

        def setText(self, text: str) -> None:
            self._model.search(text)

        def text(self) -> str:
            return self._model.search_query

    @property
    def filter_line_edit(self) -> _FilterProxy:
        return self._FilterProxy(self.model)
