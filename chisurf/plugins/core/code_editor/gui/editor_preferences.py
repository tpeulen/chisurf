"""Pure native editor appearance and language preferences."""

from __future__ import annotations

from emtk.widgets.text_editor import DARK_PALETTE, LIGHT_PALETTE, Language, Token

COLOR_SCHEMES = {
    "ChiSurf": {
        "paper_color": "#cfcfcf",
        "default_color": "#000006",
        "margins_background_color": "#808080",
        "marker_background_color": "#3c6f9e",
        "caret_line_background_color": "#afafaf",
    },
    "Light": {
        "paper_color": "#ffffff",
        "default_color": "#202020",
        "margins_background_color": "#ededed",
        "marker_background_color": "#b7d6f1",
        "caret_line_background_color": "#eef4ff",
    },
    "Dark": {
        "paper_color": "#323238",
        "default_color": "#e0e0e0",
        "margins_background_color": "#28282f",
        "marker_background_color": "#2060a0",
        "caret_line_background_color": "#404047",
    },
    "Monokai": {
        "paper_color": "#272822",
        "default_color": "#f8f8f2",
        "margins_background_color": "#252526",
        "marker_background_color": "#3e3d32",
        "caret_line_background_color": "#3e3d32",
    },
}
#: The scheme that follows the window theme (:mod:`emtk.theme`): ``Light`` on a light window,
#: ``Dark`` on a dark one. The default; a scheme the user picks (or a colour they edit) wins.
THEME_SCHEME = "Theme"
#: Every scheme the picker offers, the theme-following one first.
SCHEME_CHOICES = (THEME_SCHEME, *COLOR_SCHEMES)
LANGUAGES = ("Auto", "Python", "JSON", "YAML", "Markdown", "C++", "Plain text")


def concrete_scheme(name: str) -> str:
    """The :data:`COLOR_SCHEMES` entry *name* stands for now (:data:`THEME_SCHEME` resolves by theme)."""
    if name != THEME_SCHEME:
        return name
    from emtk import theme

    return "Light" if theme.is_light() else "Dark"


def rgba(value: str) -> tuple[int, int, int, int]:
    """Parse stored RGB/RGBA hex colors without a GUI color class."""
    value = value.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) not in (6, 8):
        raise ValueError("Use a color such as #aabbcc or #aabbccdd")
    values = [int(value[index : index + 2], 16) for index in range(0, len(value), 2)]
    return values[0], values[1], values[2], values[3] if len(values) == 4 else 255


def font_choices() -> tuple[str, ...]:
    """Offer only actual monospaced families supplied by the native backend."""
    try:
        from emtk.font import available_fonts

        return available_fonts(monospaced=True)
    except ImportError:
        return ("monospace",)


def language_for(name: str):
    choices = {
        "Python": Language.python,
        "JSON": Language.json,
        "YAML": Language.yaml,
        "Markdown": Language.markdown,
        "C++": Language.cpp,
    }
    return choices[name]() if name in choices else None


def palette_for(scheme: str, text_color: str):
    scheme = concrete_scheme(scheme)
    colors = list(LIGHT_PALETTE if scheme in ("Light", "ChiSurf") else DARK_PALETTE)
    if scheme == "Monokai":
        colors[int(Token.KEYWORD)] = (249, 38, 114)
        colors[int(Token.STRING)] = (230, 219, 116)
        colors[int(Token.NUMBER)] = (174, 129, 255)
    colors[int(Token.TEXT)] = rgba(text_color)[:3]
    colors[int(Token.IDENTIFIER)] = rgba(text_color)[:3]
    return tuple(colors)
