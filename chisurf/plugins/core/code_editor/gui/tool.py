"""EMTK Code Editor and Chat tools with optional Qt host adapters."""

from __future__ import annotations

import pathlib
from typing import Any

from chisurf.plugins.core.code_editor.gui.chat_app import ChatApp, make_chat_app
from chisurf.plugins.core.code_editor.gui.editor_app import (
    WINDOW_BG,
    CodeEditorApp,
    make_editor_app,
)

try:
    from qtpy import QtWidgets

    from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool

    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    QtWidgets = None

    class ChisurfDockTool:  # type: ignore[no-redef]
        """Fallback base when Qt is not available."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def setWindowTitle(self, title: str) -> None:
            pass

        def resize(self, w: int, h: int) -> None:
            pass

        def setCentralWidget(self, widget: Any) -> None:
            pass


class CodeEditorEmtkTool(ChisurfDockTool):
    """Full-featured multi-tab Code Editor implemented in pure EMTK."""

    name = "Code Editor"

    def __init__(
        self,
        *args: Any,
        filename: str | None = None,
        project_root: str | pathlib.Path | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle("Code Editor")
        self.resize(1200, 800)

        self.app = CodeEditorApp(project_root=project_root)
        self.editor = self.app.model
        if filename:
            self.app.model.open_file(filename)

        if _HAS_QT:
            from emtk.qt_host import ControlHost

            self.host = ControlHost(self.app, background=WINDOW_BG[:3])
            self.setCentralWidget(self.host)
        else:
            self.host = None

    def open_file(self, path: str | pathlib.Path, line: int | None = None) -> Any:
        return self.app.model.open_file(path, line=line)


class AgentChatEmtkTool(ChisurfDockTool):
    """Standalone AI Assistant / Chat panel implemented in pure EMTK."""

    name = "AI Assistant (EMTK)"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.setWindowTitle("AI Assistant (EMTK)")
        self.resize(440, 680)

        self.app = ChatApp()
        if _HAS_QT:
            from emtk.qt_host import ControlHost

            self.host = ControlHost(self.app, background=WINDOW_BG[:3])
            self.setCentralWidget(self.host)
        else:
            self.host = None


def run_code_editor(
    project_root: str | None = None,
    filename: str | None = None,
    line: int | None = None,
    size: tuple[int, int] = (1200, 800),
) -> None:
    """Run the Code Editor directly as a pure EMTK desktop app without Qt."""
    app = make_editor_app(project_root=project_root)
    if filename:
        app.model.open_file(filename, line=line)
    from emtk.native import NativeHost

    host = NativeHost(app, size=size, title="ChiSurf Code Editor")
    host.run()


def run_chat() -> None:
    """Run the AI Chat assistant directly as a pure EMTK desktop app without Qt."""
    from emtk.native import main as emtk_main

    emtk_main(
        [
            "--app",
            "chisurf.plugins.core.code_editor.gui.chat_app:make_chat_app",
            "--size",
            "440x680",
        ]
    )


__all__ = [
    "CodeEditorEmtkTool",
    "AgentChatEmtkTool",
    "run_code_editor",
    "run_chat",
    "make_editor_app",
    "make_chat_app",
]
