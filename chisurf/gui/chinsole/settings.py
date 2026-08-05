"""Settings resolution for the chinsole console.

Every key is optional. The defaults here are what the console uses when
``gui.console`` is absent from ``settings_chisurf.yaml`` -- which is the state
of every installation that predates chinsole, since ChiSurf merges packaged
defaults *underneath* the user's file and never overwrites it.

Qt-free by design: :func:`console_settings` returns plain data so the engine and
its head-less tests can read it. Only :func:`editor_font` touches Qt.
"""

from __future__ import annotations

import typing

__all__ = [
    "DEFAULTS",
    "console_settings",
    "console_init_source",
    "editor_font",
]


#: Console settings and their defaults. ``0`` means "derive it" for the numeric
#: sizing keys, so a user who wants the console font to follow the editor's does
#: not have to keep two numbers in sync.
DEFAULTS: dict[str, typing.Any] = {
    "theme": "auto",
    "font_family": "",
    "font_size": 0,
    "max_blocks": 5000,
    "max_output_chars": 500_000,
    "flush_interval_ms": 30,
    "completion": "popup",
    "calltips": True,
    "paging": "vsplit",
    "history_length": 5000,
    "banner": True,
    "confirm_exit": True,
    "ansi_colors": True,
    "images": True,
    "image_max_width": 0,
    "autoindent": True,
}


def console_settings() -> dict[str, typing.Any]:
    """Return the ``gui.console`` block merged over :data:`DEFAULTS`.

    Returns
    -------
    dict
        Never missing a key, so callers index rather than ``.get`` with a
        second copy of the default.
    """
    resolved = dict(DEFAULTS)
    try:
        import chisurf.core.settings

        block = chisurf.core.settings.gui.get("console") or {}
    except Exception:
        return resolved
    for key, value in block.items():
        if key in resolved:
            resolved[key] = value
    return resolved


def console_init_source() -> str:
    """Return the startup snippet to run in a fresh console.

    Returns
    -------
    str
        Empty when the setting is absent or blank.

    Notes
    -----
    The shipped value still contains IPython spellings -- ``%matplotlib
    inline``, ``%config Completer.use_jedi = False`` and
    ``get_ipython().cache_size = 0`` -- and so does every user's settings file,
    which ChiSurf never overwrites. chinsole therefore implements all three
    rather than asking anyone to edit their settings: see
    :mod:`chisurf.gui.chinsole.magics_builtin` and ``Shell.cache_size``.
    """
    try:
        import chisurf.core.settings

        return str(chisurf.core.settings.gui.get("console_init") or "")
    except Exception:
        return ""


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
