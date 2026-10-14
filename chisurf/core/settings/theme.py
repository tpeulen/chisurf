"""The window's theme: ``gui.theme`` in ``settings_chisurf.yaml`` (``dark``, the default, or ``light``).

The colours themselves are emtk's (:mod:`emtk.theme`: a value for every palette name, for
windows, docks, tabs, tables, fields, menus, plots and the workspace). This module only keeps
which one the user chose: :func:`apply_stored` hands it to emtk at startup, :func:`choose`
switches the running window and writes the choice, so the next start opens in it too.
Qt-free: the emtk shell's Settings menu calls these.
"""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)

#: Key of the choice under ``gui``.
KEY = "theme"
#: The theme a missing or unknown setting falls back to.
DEFAULT = "dark"


def stored() -> str:
    """The stored theme name (``gui.theme``), or :data:`DEFAULT` when unset or unknown."""
    try:
        from chisurf.core.settings import cs_settings

        name = str((cs_settings.get("gui") or {}).get(KEY) or DEFAULT).strip().lower()
    except Exception:  # noqa: BLE001 - unreadable settings: the default look
        return DEFAULT
    from emtk.theme import THEMES

    return name if name in THEMES else DEFAULT


def apply_stored(styles=()) -> str:
    """Apply the stored theme to emtk (and to *styles* that already exist); returns its name."""
    from emtk import theme

    name = stored()
    try:
        theme.apply_theme(name, styles=styles)
    except Exception:  # noqa: BLE001 - a theme must never stop the window from starting
        _log.exception("Could not apply the theme %r; using the dark one", name)
        theme.apply_theme(DEFAULT, styles=styles)
        name = DEFAULT
    return name


def choose(name: str, styles=()) -> bool:
    """Switch the running window to theme *name* and keep it for the next start.

    Parameters
    ----------
    name : str
        A theme of :data:`emtk.theme.THEMES` (``"dark"``, ``"light"``).
    styles : iterable of emtk.im_core.Style
        Styles the caller keeps (an app with a style of its own) that should switch too.

    Returns
    -------
    bool
        True when the choice was written to the user's settings file.

    Raises
    ------
    KeyError
        *name* is not a theme.
    """
    from emtk import theme

    theme.apply_theme(name, styles=styles)
    try:
        import chisurf.core.settings as settings

        settings.cs_settings.setdefault("gui", {})[KEY] = name
        settings.gui[KEY] = name
    except Exception:  # noqa: BLE001 - the file is what persists
        pass
    from chisurf.core.settings.settings_utils import update_settings_section

    return update_settings_section("gui", {KEY: name})


__all__ = ["DEFAULT", "KEY", "apply_stored", "choose", "stored"]
