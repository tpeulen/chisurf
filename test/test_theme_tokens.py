"""Guard: ChiSurf's emtk windows take their colours from the theme, and the choice persists.

The light theme (Settings ▸ Light theme, :mod:`emtk.theme`) only reaches what reads the
palette. A literal colour handed to ``im.text_colored`` or ``im.push_style_color`` stays
the colour it was picked for: light-blue captions vanish on a light window, a dark field
stays dark. So this file fails when shipped emtk code passes a colour tuple literal to either.
Name a theme colour instead: ``emtk.style.TEXT_DANGER`` / ``TEXT_WARNING`` / ``TEXT_TIP`` /
``TEXT_NOTE`` / ``HEADING_1..4`` / ``CODE_BG`` ..., or a button ``role``. Chrome a window
keeps on purpose for the dark theme only is a named constant pushed under
``not emtk.theme.is_light()`` (the code editor's ``DARK_CHROME``).

It also checks that the theme choice round-trips through ``gui.theme`` and that the
shell's Settings menu offers it.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SOURCE = _ROOT / "chisurf"
_CALLS = {"text_colored", "push_style_color"}


def _literal_colour(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Tuple)
        and len(node.elts) in (3, 4)
        and all(isinstance(e, ast.Constant) and isinstance(e.value, (int, float)) for e in node.elts)
    )


def literal_colour_findings(path: pathlib.Path, root: pathlib.Path = _ROOT) -> list[str]:
    """``text_colored((r, g, b), …)`` / ``push_style_color(Col.X, (r, g, b))`` calls in *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in _CALLS:
            continue
        colour = node.args[0] if node.func.attr == "text_colored" and node.args else (
            node.args[1] if len(node.args) > 1 else None)
        # a conditional between two literals is still a literal
        candidates = [colour.body, colour.orelse] if isinstance(colour, ast.IfExp) else [colour]
        if any(c is not None and _literal_colour(c) for c in candidates):
            found.append(f"{path.relative_to(root)}:{node.lineno}: {ast.unparse(node)[:90]}")
    return found


def _shipped():
    for path in sorted(_SOURCE.rglob("*.py")):
        parts = path.relative_to(_ROOT).parts
        if "__pycache__" in parts or any(p in ("test", "tests") for p in parts):
            continue
        if "cookiecutter" in str(path):
            continue
        yield path


def test_no_window_hands_emtk_a_literal_colour():
    drift = [hit for path in _shipped() for hit in literal_colour_findings(path)]
    assert not drift, "\n".join(drift)


@pytest.mark.parametrize(
    "source, expected",
    [
        ("im.text_colored((200, 210, 230, 255), 'x')", 1),
        ("im.push_style_color(Col.TEXT, (0.9, 0.4, 0.4, 1.0))", 1),
        ("im.text_colored(A if ok else (1, 2, 3), 'x')", 1),
        ("im.text_colored(style.TEXT_DANGER, 'x')", 0),
        ("im.push_style_color(role, colour)", 0),
    ],
)
def test_the_scan_sees_literals_and_leaves_named_colours(tmp_path, source, expected):
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    assert len(literal_colour_findings(probe, tmp_path)) == expected


@pytest.fixture
def settings_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    from emtk import theme

    yield tmp_path / "settings"
    theme.apply_theme("dark")


def test_the_theme_choice_is_applied_and_kept(settings_dir):
    import yaml
    from emtk import style, theme

    from chisurf.core.settings import get_path
    from chisurf.core.settings import theme as stored_theme

    assert stored_theme.stored() in theme.THEMES
    assert stored_theme.choose("light")
    assert theme.current_theme() == "light" and theme.is_light()
    assert style.WINDOW_BG == theme.LIGHT["WINDOW_BG"]
    saved = yaml.safe_load((get_path("settings") / "settings_chisurf.yaml").read_text())
    assert saved["gui"]["theme"] == "light"
    assert stored_theme.stored() == "light"
    theme.apply_theme("dark")
    assert stored_theme.apply_stored() == "light", "the next start opens in the stored theme"
    assert theme.is_light()
    with pytest.raises(KeyError):
        stored_theme.choose("sepia")


def test_the_plot_background_follows_the_theme_unless_set(settings_dir):
    from emtk import style, theme

    from chisurf.chiplot.backends.emtk_backend import EmtkCanvas

    canvas = EmtkCanvas()
    assert canvas._background == tuple(style.PLOT_BG[:3])
    theme.apply_theme("light")
    assert canvas._background == tuple(theme.LIGHT["PLOT_BG"][:3])
    canvas.set_background((1, 2, 3))
    assert canvas._background == (1, 2, 3)
    canvas.set_background(None)
    assert canvas._background == tuple(theme.LIGHT["PLOT_BG"][:3])


def test_the_shell_settings_menu_switches_the_theme(settings_dir):
    from emtk import theme

    from chisurf.emtk.main_app import EmtkShellApp

    app = EmtkShellApp({}, loader=lambda plugin_id: None)
    try:
        settings = next(items for title, items in app.session_menus() if "Settings" in title)
        actions = {action.key: action for action in settings}
        assert actions["theme_dark"].checked() and not actions["theme_light"].checked()
        actions["theme_light"].run()
        assert theme.current_theme() == "light" and actions["theme_light"].checked()
        actions["theme_dark"].run()
        assert theme.current_theme() == "dark"
    finally:
        app.close()
