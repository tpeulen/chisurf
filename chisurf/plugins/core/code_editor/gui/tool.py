"""Qt host adapters of the emtk Code Editor and Chat apps, and their standalone launchers.

The editor is the emtk app (``gui/editor_app.py``); the emtk shell opens it as a dock. The Qt main
window (``--qt``) hosts the same app in a ``ControlHost`` through :class:`CodeEditorEmtkTool`.
The legacy Qt editor widgets (``CodeEditor``, ``CodeEditorWindow``, ``NotebookEditor``,
``AgentPanelWidget``) were retired 2026-10-13; their tests run on the emtk app.
"""

from __future__ import annotations

import pathlib
from typing import Any

from chisurf.plugins.core.code_editor.gui.chat_app import ChatApp, make_chat_app
from chisurf.plugins.core.code_editor.gui.editor_app import (
    WINDOW_BG,
    CodeEditorApp,
    make_editor_app,
)

from chisurf.gui.widgets.tools.chisurf_dock_tool import ChisurfDockTool


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

        from emtk.qt_host import ControlHost

        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.setCentralWidget(self.host)

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
        from emtk.qt_host import ControlHost

        self.host = ControlHost(self.app, background=WINDOW_BG[:3])
        self.setCentralWidget(self.host)


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
