"""Standalone launchers of the emtk Code Editor and Chat apps.

The editor is the emtk app (``gui/editor_app.py``); the emtk shell opens it as a dock.
"""

from __future__ import annotations

from chisurf.plugins.core.code_editor.gui.chat_app import make_chat_app
from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app


def run_code_editor(
    project_root: str | None = None,
    filename: str | None = None,
    line: int | None = None,
    size: tuple[int, int] = (1200, 800),
) -> None:
    """Run the Code Editor directly as a pure EMTK desktop app."""
    app = make_editor_app(project_root=project_root)
    if filename:
        app.model.open_file(filename, line=line)
    from emtk.native import NativeHost

    host = NativeHost(app, size=size, title="ChiSurf Code Editor")
    host.run()


def run_chat() -> None:
    """Run the AI Chat assistant directly as a pure EMTK desktop app."""
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
    "run_code_editor",
    "run_chat",
    "make_editor_app",
    "make_chat_app",
]
