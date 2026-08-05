"""Colour themes for the chinsole console.

A :class:`ConsoleTheme` carries every colour the console draws with: the widget
chrome, the prompts, the sixteen ANSI base colours and the syntax palette. They
are kept together deliberately -- the widget that qtconsole gave ChiSurf set its
chrome from one style and its syntax colours from another (a light stylesheet
over the dark ``linux`` syntax style, see :mod:`chisurf.gui.chinsole`), so the
console rendered light chrome with dark-background syntax colours against a dark
application theme. One object means that cannot be expressed.

This module holds no Qt import, so themes can be resolved and asserted on
head-lessly. Converting a hex string to a ``QColor`` is the widget's job.
"""

from __future__ import annotations

import dataclasses
import typing

__all__ = [
    "ConsoleTheme",
    "THEMES",
    "LEGACY_ALIASES",
    "resolve_theme",
    "theme_from_settings",
    "stylesheet",
]


@dataclasses.dataclass(frozen=True)
class ConsoleTheme:
    """A complete console colour scheme.

    Parameters
    ----------
    name : str
        Canonical theme name.
    background, foreground : str
        Widget chrome, as ``#rrggbb``.
    prompt_in, prompt_out, prompt_continuation : str
        Prompt colours.
    stderr_fg, traceback_fg, traceback_highlight : str
        Error rendering.
    selection_bg, selection_fg, cursor : str
        Text selection and caret.
    ansi : tuple of str
        The sixteen ANSI base colours, normal 0-7 then bright 8-15.
    syntax : dict
        Token-name to colour mapping consumed by
        :class:`chisurf.gui.syntax.PythonHighlighter`.
    dark : bool
        Whether the background is dark. Drives contrast decisions that would
        otherwise have to be re-derived from the background luminance.
    """

    name: str
    background: str
    foreground: str
    prompt_in: str
    prompt_out: str
    prompt_continuation: str
    stderr_fg: str
    traceback_fg: str
    traceback_highlight: str
    selection_bg: str
    selection_fg: str
    cursor: str
    ansi: tuple[str, ...]
    syntax: typing.Mapping[str, str]
    dark: bool = True


#: The eight normal + eight bright ANSI colours of a dark terminal.
_ANSI_DARK = (
    "#000000", "#cd3131", "#0dbc79", "#e5e510",
    "#2472c8", "#bc3fbc", "#11a8cd", "#e5e5e5",
    "#666666", "#f14c4c", "#23d18b", "#f5f543",
    "#3b8eea", "#d670d6", "#29b8db", "#ffffff",
)

#: The same sixteen slots re-picked for a light background. Bright yellow and
#: bright cyan are unreadable on white, so the light theme darkens them rather
#: than inheriting terminal convention.
_ANSI_LIGHT = (
    "#000000", "#cd3131", "#00825e", "#8a7500",
    "#0451a5", "#a626a4", "#0b7f8f", "#555555",
    "#666666", "#cd3131", "#00875f", "#7a6800",
    "#0451a5", "#a626a4", "#0b7f8f", "#000000",
)

_SYNTAX_DARK = {
    "keyword": "#569cd6",
    "builtin": "#4ec9b0",
    "class": "#4ec9b0",
    "function": "#dcdcaa",
    "string": "#ce9178",
    "fstring_expr": "#d7ba7d",
    "comment": "#6a9955",
    "number": "#b5cea8",
    "decorator": "#dcdcaa",
    "self": "#9cdcfe",
    "operator": "#d4d4d4",
    "magic": "#c586c0",
}

_SYNTAX_LIGHT = {
    "keyword": "#0000ff",
    "builtin": "#267f99",
    "class": "#267f99",
    "function": "#795e26",
    "string": "#a31515",
    "fstring_expr": "#8a5a00",
    "comment": "#008000",
    "number": "#098658",
    "decorator": "#795e26",
    "self": "#001080",
    "operator": "#333333",
    "magic": "#af00db",
}

_SYNTAX_MONO = {k: "#000000" for k in _SYNTAX_DARK}
_SYNTAX_MONO["comment"] = "#555555"


THEMES: dict[str, ConsoleTheme] = {
    "chisurf-dark": ConsoleTheme(
        name="chisurf-dark",
        background="#1e1e1e",
        foreground="#d4d4d4",
        prompt_in="#4ec9b0",
        prompt_out="#ce9178",
        prompt_continuation="#5a5a5a",
        stderr_fg="#f14c4c",
        traceback_fg="#f14c4c",
        traceback_highlight="#3a1d1d",
        selection_bg="#264f78",
        selection_fg="#ffffff",
        cursor="#d4d4d4",
        ansi=_ANSI_DARK,
        syntax=_SYNTAX_DARK,
        dark=True,
    ),
    "chisurf-light": ConsoleTheme(
        name="chisurf-light",
        background="#ffffff",
        foreground="#1e1e1e",
        prompt_in="#0451a5",
        prompt_out="#a31515",
        prompt_continuation="#9a9a9a",
        stderr_fg="#cd3131",
        traceback_fg="#cd3131",
        traceback_highlight="#fdeaea",
        selection_bg="#add6ff",
        selection_fg="#000000",
        cursor="#1e1e1e",
        ansi=_ANSI_LIGHT,
        syntax=_SYNTAX_LIGHT,
        dark=False,
    ),
    "chisurf-mono": ConsoleTheme(
        name="chisurf-mono",
        background="#ffffff",
        foreground="#000000",
        prompt_in="#000000",
        prompt_out="#000000",
        prompt_continuation="#777777",
        stderr_fg="#000000",
        traceback_fg="#000000",
        traceback_highlight="#eeeeee",
        selection_bg="#c0c0c0",
        selection_fg="#000000",
        cursor="#000000",
        ansi=tuple(["#000000"] * 8 + ["#555555"] * 8),
        syntax=_SYNTAX_MONO,
        dark=False,
    ),
}


#: qtconsole's three ``set_default_style`` names, which is what ChiSurf's
#: ``gui.console_style`` setting has always held. They keep working: an existing
#: user's ``console_style: linux`` resolves to ``chisurf-dark`` and needs no
#: migration.
LEGACY_ALIASES = {
    "linux": "chisurf-dark",
    "lightbg": "chisurf-light",
    "nocolor": "chisurf-mono",
    "bw": "chisurf-mono",
}


def resolve_theme(name: str | ConsoleTheme | None = None) -> ConsoleTheme:
    """Return the theme for *name*.

    Parameters
    ----------
    name : str or ConsoleTheme or None, optional
        A canonical theme name, one of :data:`LEGACY_ALIASES`, ``"auto"``, a
        :class:`ConsoleTheme` (returned unchanged), or ``None`` for ``"auto"``.

    Returns
    -------
    ConsoleTheme
        Never ``None``: an unknown name falls back to the automatic choice
        rather than raising, because this is reached from a settings file the
        user edits by hand and a typo must not stop the console from starting.
    """
    if isinstance(name, ConsoleTheme):
        return name
    if not name or name == "auto":
        return THEMES[_auto_theme_name()]
    key = str(name).strip().lower()
    key = LEGACY_ALIASES.get(key, key)
    theme = THEMES.get(key)
    if theme is None:
        import chisurf

        chisurf.logging.warning(
            "Unknown console theme %r; using %s. Known: %s",
            name, _auto_theme_name(), ", ".join(sorted(THEMES)),
        )
        return THEMES[_auto_theme_name()]
    return theme


def _auto_theme_name() -> str:
    """Return the theme name implied by the application's Qt style sheet.

    ChiSurf ships seven ``.qss`` themes, six of them dark. The console should
    follow the one the user already chose rather than carry a second, unrelated
    appearance setting.

    Returns
    -------
    str
        Key into :data:`THEMES`.
    """
    try:
        import chisurf.core.settings

        style = str(chisurf.core.settings.gui.get("style_sheet") or "")
    except Exception:
        return "chisurf-dark"
    return "chisurf-light" if "light" in style.lower() else "chisurf-dark"


def theme_from_settings() -> ConsoleTheme:
    """Return the console theme selected by the ChiSurf settings.

    Resolution order is ``gui.console.theme``, then the legacy
    ``gui.console_style``, then automatic. The legacy key is consulted second
    rather than ignored because it is what every existing installation has.

    Returns
    -------
    ConsoleTheme
    """
    try:
        import chisurf.core.settings

        gui = chisurf.core.settings.gui
    except Exception:
        return THEMES["chisurf-dark"]
    console = gui.get("console") or {}
    name = console.get("theme") or gui.get("console_style") or "auto"
    return resolve_theme(name)


def stylesheet(theme: ConsoleTheme) -> str:
    """Return the Qt style sheet for a console view using *theme*.

    Parameters
    ----------
    theme : ConsoleTheme

    Returns
    -------
    str
    """
    return (
        "QPlainTextEdit, QTextEdit {\n"
        f"    background-color: {theme.background};\n"
        f"    color: {theme.foreground};\n"
        f"    selection-background-color: {theme.selection_bg};\n"
        f"    selection-color: {theme.selection_fg};\n"
        "    border: none;\n"
        "}\n"
    )
