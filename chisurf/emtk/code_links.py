"""Open a documentation link to source in the code editor.

A page that names a function should be able to *take you there*. The link is
resolved by symbol (:mod:`chisurf.plugins.core.help.api.source_links`) and
handed to the code editor, which already knows how to open a file in a new tab
or raise the tab it is in.

Reusing the editor that is open, rather than opening another one, is the point:
following three references from a page should leave one editor with three tabs,
not three editors.
"""

from __future__ import annotations

import logging
import pathlib
import sys
from typing import Any

from chisurf.core.support.weak_registry import WeakOrderedRegistry

logger = logging.getLogger(__name__)

__all__ = ["open_source"]


_ACTIVE_EMTK_EDITORS = WeakOrderedRegistry()


def register_emtk_editor(editor: Any) -> None:
    """Register an active EMTK code editor instance."""
    if editor not in _ACTIVE_EMTK_EDITORS:
        _ACTIVE_EMTK_EDITORS.append(editor)


def host_in_open_shell(plugin_id: str, then: Any = None) -> bool:
    """Open *plugin_id* in the emtk shell of this process, if one is open; ``then()`` once built.

    Looked up in :data:`sys.modules`, so a process without the shell never imports it.
    """
    import sys

    shell_module = sys.modules.get("chisurf.emtk.main_app")
    host = getattr(shell_module, "host_in_shell", None)
    return bool(host(plugin_id, then)) if callable(host) else False


def unregister_emtk_editor(editor: Any) -> None:
    """Unregister an EMTK code editor instance."""
    if editor in _ACTIVE_EMTK_EDITORS:
        _ACTIVE_EMTK_EDITORS.remove(editor)


def _is_qt_active() -> bool:
    """Return whether a Qt application event loop is actively running."""
    try:
        widgets = sys.modules.get("qtpy.QtWidgets")
        if widgets is None:
            for name in (
                "PySide6.QtWidgets",
                "PyQt6.QtWidgets",
                "PySide2.QtWidgets",
                "PyQt5.QtWidgets",
            ):
                widgets = sys.modules.get(name)
                if widgets is not None:
                    break
        return widgets is not None and widgets.QApplication.instance() is not None
    except Exception:
        return False


def open_source(
    target: str,
    base: pathlib.Path | None = None,
    prefer_emtk: bool | None = None,
) -> bool:
    """Open *target* in the full code editor (qt->qt; emtk->emtk).

    Parameters
    ----------
    target : str
        ``path``, ``path#symbol`` or ``src:path#symbol``.
    base : pathlib.Path, optional
        Directory a relative path is resolved against first.
    prefer_emtk : bool, optional
        If True, route to EMTK code editor.
        If False, route to Qt code editor.
        If None, route to EMTK if active or Qt absent, otherwise Qt.

    Returns
    -------
    bool
        Whether the editor was given the file. ``False`` lets the caller fall
        back — a link that resolves to nothing must not be swallowed.
    """
    from chisurf.plugins.core.help.api.source_links import resolve

    resolved = resolve(target, base)
    if resolved is None:
        logger.debug("no source file for %r", target)
        return False

    line_num = resolved.line or None

    if prefer_emtk is True:
        use_emtk = True
    elif prefer_emtk is False:
        use_emtk = False
    else:
        use_emtk = bool(_ACTIVE_EMTK_EDITORS) or not _is_qt_active()

    # 1. EMTK Environment: route to full EMTK code editor
    if use_emtk:
        for editor in reversed(_ACTIVE_EMTK_EDITORS):
            if editor is not None:
                try:
                    editor.open_file(str(resolved.path), line=line_num)
                    return True
                except Exception:
                    logger.debug("could not open in active EMTK editor", exc_info=True)

        # No editor yet: the open emtk shell makes one as a dock (not a second process
        # whose OS window falls behind the main one); without a shell, a standalone editor.
        def show_in_editor() -> None:
            for editor in reversed(_ACTIVE_EMTK_EDITORS):
                if editor is not None:
                    editor.open_file(str(resolved.path), line=line_num)
                    return

        if host_in_open_shell("code_editor", show_in_editor):
            return True
        try:
            import subprocess
            import sys

            cmd = [
                sys.executable,
                "-m",
                "chisurf.emtk",
                "--plugin",
                "code_editor",
                "--path",
                str(resolved.path),
            ]
            if line_num:
                cmd.extend(["--anchor", str(line_num)])
            subprocess.Popen(cmd)
            return True
        except Exception:
            logger.debug("could not spawn EMTK code editor process", exc_info=True)
            return False

    # 2. Qt Environment: route to full Qt code editor
    try:
        from qtpy import QtWidgets

        from chisurf.plugins.core.code_editor.editor import CodeEditor
        from chisurf.plugins.core.code_editor.gui.tool import CodeEditorEmtkTool

        for widget in QtWidgets.QApplication.topLevelWidgets():
            if not widget.isVisible():
                continue
            if isinstance(widget, (CodeEditor, CodeEditorEmtkTool)):
                widget.open_file(str(resolved.path), line=line_num)
                w = widget.window() if hasattr(widget, "window") else widget
                w.show()
                w.raise_()
                w.activateWindow()
                return True
            found = widget.findChild(CodeEditor)
            if found is not None:
                found.open_file(str(resolved.path), line=line_num)
                w = widget.window() if hasattr(widget, "window") else widget
                w.show()
                w.raise_()
                w.activateWindow()
                return True
    except Exception:
        logger.debug("error searching open Qt code editors", exc_info=True)

    try:
        from chisurf.plugins.core.code_editor.window import CodeEditorWindow

        window = CodeEditorWindow()
        window.show()
        window.editor.open_file(str(resolved.path), line=line_num)
        return True
    except Exception:
        logger.debug("could not start Qt code editor window", exc_info=True)
        return False

    if resolved.missing_symbol:
        logger.warning(
            "%s no longer defines %r — the documentation link is stale",
            resolved.path.name,
            resolved.symbol,
        )
    return True
