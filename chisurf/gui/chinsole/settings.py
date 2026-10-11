"""The chinsole console's settings: the Qt font on top of :mod:`chisurf.core.console.settings`.

The settings themselves are Qt-free and live in the engine package, where the emtk
shell's console reads them too; only :func:`editor_font` needs Qt.
"""

from __future__ import annotations

from chisurf.core.console.settings import (  # noqa: F401 - re-exported for the Qt console
    DEFAULTS,
    _without_absent_matplotlib,
    console_init_source,
    console_settings,
)

__all__ = [
    "DEFAULTS",
    "console_settings",
    "console_init_source",
    "editor_font",
]


def editor_font(settings: dict | None = None):
    """Return the console font.

    Follows ``gui.editor`` unless ``gui.console.font_family`` / ``font_size``
    override it, so the console and the script editor look like one application
    by default. This is what the qtconsole widget did through
    ``make_editor_font_from_settings``.

    Parameters
    ----------
    settings : dict, optional
        Result of :func:`console_settings`; re-read when omitted.

    Returns
    -------
    qtpy.QtGui.QFont
    """
    from qtpy import QtGui

    if settings is None:
        settings = console_settings()

    family = settings.get("font_family") or ""
    size = int(settings.get("font_size") or 0)

    if not family or size <= 0:
        try:
            import chisurf.core.settings

            editor = chisurf.core.settings.gui.get("editor") or {}
        except Exception:
            editor = {}
        family = family or str(editor.get("font_family") or "")
        size = size if size > 0 else int(editor.get("font_size") or 0)

    font = QtGui.QFont()
    if family:
        font.setFamily(family)
    else:
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
    if size > 0:
        font.setPointSize(size)
    font.setStyleHint(QtGui.QFont.Monospace)
    font.setFixedPitch(True)
    return font
