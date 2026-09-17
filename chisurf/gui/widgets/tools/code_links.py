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

logger = logging.getLogger(__name__)

__all__ = ["open_source"]


def _existing_editor():
    """Return an open code editor widget, or ``None``.

    Both the plugin window and a bare ``CodeEditor`` count: a tool may embed
    the editor without the window around it.
    """
    try:
        from qtpy import QtWidgets

        from chisurf.plugins.core.code_editor.editor import CodeEditor
    except Exception:
        logger.debug("the code editor is unavailable", exc_info=True)
        return None

    for widget in QtWidgets.QApplication.topLevelWidgets():
        if not widget.isVisible():
            continue
        if isinstance(widget, CodeEditor):
            return widget
        found = widget.findChild(CodeEditor)
        if found is not None:
            return found
    return None


def open_source(target: str, base: pathlib.Path | None = None) -> bool:
    """Open *target* in the code editor.

    Parameters
    ----------
    target : str
        ``path``, ``path#symbol`` or ``src:path#symbol``.
    base : pathlib.Path, optional
        Directory a relative path is resolved against first.

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

    editor = _existing_editor()
    if editor is None:
        try:
            from chisurf.plugins.core.code_editor.window import CodeEditorWindow

            window = CodeEditorWindow()
            window.show()
            editor = window.editor
        except Exception:
            logger.debug("could not start the code editor", exc_info=True)
            return False

    try:
        editor.open_file(str(resolved.path), line=resolved.line or None)
        window = editor.window()
        window.show()
        window.raise_()
        window.activateWindow()
    except Exception:
        logger.debug("could not open %s in the editor", resolved.path, exc_info=True)
        return False

    if resolved.missing_symbol:
        # The file opened, but the symbol the page named is gone -- a rename,
        # and the page is now out of date. Say so rather than leaving the
        # reader at line 1 wondering.
        logger.warning(
            "%s no longer defines %r — the documentation link is stale",
            resolved.path.name,
            resolved.symbol,
        )
        try:
            from chisurf.gui import dialogs

            dialogs.warning(
                editor,
                "Symbol not found",
                f"{resolved.path.name} no longer defines “{resolved.symbol}”.\n"
                "It was renamed or removed; the file is open at its start.",
            )
        except Exception:
            logger.debug("could not report the stale link", exc_info=True)
    return True
