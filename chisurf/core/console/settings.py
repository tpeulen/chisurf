"""Settings resolution for the chinsole console.

Every key is optional. The defaults here are what the console uses when
``gui.console`` is absent from ``settings_chisurf.yaml`` -- which is the state
of every installation that predates chinsole, since ChiSurf merges packaged
defaults *underneath* the user's file and never overwrites it.

Qt-free: plain data, read by the engine, its head-less tests and both console
views -- the Qt one (:mod:`chisurf.gui.chinsole`, which adds the Qt font) and
the emtk shell's (:mod:`chisurf.emtk.console`).
"""

from __future__ import annotations

import re
import typing

__all__ = [
    "DEFAULTS",
    "console_settings",
    "console_init_source",
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
    if not resolved["font_family"]:
        # No console face of its own: the editor face of Settings ▸ Fonts (``gui.fonts.code``),
        # when it names a family -- a generic such as ``monospace`` leaves the view's default.
        resolved["font_family"] = _named_code_family(chisurf.core.settings.gui.get("fonts"))
    return resolved


def _named_code_family(fonts: typing.Any) -> str:
    """The first named (non-generic) family of ``gui.fonts.code``, or ``""``."""
    code = fonts.get("code") if isinstance(fonts, dict) else None
    family = code.get("family", "") if isinstance(code, dict) else code
    generics = {"monospace", "prose", "sans-serif", "sans", "serif", "auto"}
    for part in str(family or "").split(","):
        if part.strip() and part.strip().casefold() not in generics:
            return part.strip()
    return ""


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

    matplotlib is no longer a ChiSurf dependency, but older settings files
    still start the console with ``%matplotlib inline`` and ``import pylab as
    p``. Without matplotlib installed those lines only print a traceback into
    a fresh console, so they are dropped then; with it installed they run as
    written.
    """
    try:
        import chisurf.core.settings

        source = str(chisurf.core.settings.gui.get("console_init") or "")
    except Exception:
        return ""
    return _without_absent_matplotlib(source)


def _without_absent_matplotlib(source: str) -> str:
    """``source`` minus its matplotlib lines when matplotlib is not installed.

    Parameters
    ----------
    source : str
        A console start-up snippet.

    Returns
    -------
    str
        ``source`` unchanged if matplotlib is importable.
    """
    import importlib.util

    try:
        if importlib.util.find_spec("matplotlib") is not None:
            return source
    except (ImportError, ValueError):
        pass
    pattern = re.compile(
        r"^\s*(%matplotlib\b|%pylab\b|import\s+(pylab|matplotlib)\b|from\s+(pylab|matplotlib)\b)"
    )
    return "\n".join(line for line in source.splitlines() if not pattern.match(line))
