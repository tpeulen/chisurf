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
import re

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


# --------------------------------------------------------------------------------------------
# Draw-list fills and module-level surface constants
# --------------------------------------------------------------------------------------------
#: Painter and draw-list calls that take a colour.
_DRAW_CALLS = {
    "fill_rect", "stroke_rect", "add_rect", "add_rect_filled", "add_line", "add_polyline",
    "add_text", "add_circle", "add_circle_filled", "add_triangle_filled", "add_bezier_cubic",
}
#: Games draw boards in a palette of their own (a game is its own world, as a photo is);
#: the splash is artwork drawn before any theme is applied.
_EXEMPT = ("chisurf/plugins/misc/games/", "chisurf/emtk/splash.py")
#: A module constant named like one of these is a window surface or its text: it must come
#: from the theme. Data colours (a series, a gate, a region, a graph edge) and accent rims
#: are free to be constants.
_SURFACE_NAME = re.compile(r"(^|_)(BG|BACKDROP|BACKGROUND|PANEL|TITLE|TEXT|DIM|BRIGHT|GRID)(_|$)")
#: Calls whose ``background=`` paints a Qt host: dies with the Qt host, not an emtk surface.
_QT_HOST_CALLS = {"ControlHost", "QtHost", "_QtHost"}


def _emtk_file(path: pathlib.Path) -> bool:
    rel = path.relative_to(_ROOT).as_posix()
    if any(rel.startswith(prefix) for prefix in _EXEMPT):
        return False
    text = path.read_text(encoding="utf-8")
    return "emtk" in text


def draw_literal_findings(path: pathlib.Path, root: pathlib.Path = _ROOT) -> list[str]:
    """Painter / draw-list calls in *path* given a colour tuple literal."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in _DRAW_CALLS:
            continue
        values = list(node.args) + [k.value for k in node.keywords]
        values += [v for a in values if isinstance(a, ast.IfExp) for v in (a.body, a.orelse)]
        if any(_literal_colour(v) for v in values):
            found.append(f"{path.relative_to(root)}:{node.lineno}: {ast.unparse(node)[:90]}")
    return found


def surface_constant_findings(path: pathlib.Path, root: pathlib.Path = _ROOT) -> list[str]:
    """Module colour constants named as a surface or its text that are drawn with.

    A constant only exported (``__all__``) or only handed to a Qt host's ``background=``
    is not drawn by emtk and is not reported (:func:`qt_host_only_constants` lists those).
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    found = []
    for name, lineno in _surface_constants(tree):
        uses = _uses(tree, name)
        if any(not qt for qt in uses):
            found.append(f"{path.relative_to(root)}:{lineno}: {name} is drawn; name a theme colour")
    return found


def qt_host_only_constants(path: pathlib.Path) -> list[str]:
    """Surface constants of *path* used only as a Qt host's background (the Qt-retirement list)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    return [name for name, _ in _surface_constants(tree)
            if (uses := _uses(tree, name)) and all(uses)]


def _colour_constant(node: ast.AST) -> bool:
    """``(r, g, b[, a])`` of ints 0..255: a colour, not a grid's ``(0.01, 4.0, 128)``."""
    return (
        isinstance(node, ast.Tuple)
        and len(node.elts) in (3, 4)
        and all(isinstance(e, ast.Constant) and type(e.value) is int and 0 <= e.value <= 255
                for e in node.elts)
    )


def _surface_constants(tree: ast.Module):
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and _colour_constant(node.value)
                and _SURFACE_NAME.search(node.targets[0].id)):
            yield node.targets[0].id, node.lineno


def _uses(tree: ast.Module, name: str) -> list[bool]:
    """One entry per read of *name*: True when it is a Qt host's ``background=``."""
    qt_reads = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            callee = getattr(node.func, "id", getattr(node.func, "attr", ""))
            if callee in _QT_HOST_CALLS:
                for keyword in node.keywords:
                    if keyword.arg == "background":
                        for sub in ast.walk(keyword.value):
                            if isinstance(sub, ast.Name) and sub.id == name:
                                qt_reads.add(id(sub))
    return [id(node) in qt_reads for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load)]


def test_no_emtk_window_draws_a_literal_colour():
    drift = [hit for path in _shipped() if _emtk_file(path) for hit in draw_literal_findings(path)]
    assert not drift, "\n".join(drift)


def test_no_emtk_window_draws_a_dark_only_surface_constant():
    drift = [hit for path in _shipped() if _emtk_file(path)
             for hit in surface_constant_findings(path)]
    assert not drift, "\n".join(drift)


@pytest.mark.parametrize(
    "source, draws, constants",
    [
        ("p.fill_rect(x, y, w, h, (21, 21, 21))", 1, 0),
        ("dl.add_rect_filled(a, b, fill if ok else (20, 20, 20, 225))", 1, 0),
        ("p.fill_rect(x, y, w, h, style.PLOT_BG)", 0, 0),
        ("PANEL_BG = (38, 41, 48, 255)\np.fill_rect(0, 0, 1, 1, PANEL_BG)", 0, 1),
        ("WINDOW_BG = (30, 32, 38, 255)\n__all__ = ['WINDOW_BG']", 0, 0),
        ("WINDOW_BG = (30, 32, 38, 255)\nhost = ControlHost(app, background=WINDOW_BG[:3])", 0, 0),
        ("ACCENT_BLUE = (31, 119, 180, 255)\nplot(ACCENT_BLUE)", 0, 0),
    ],
)
def test_the_draw_scans_see_fills_and_surface_constants(tmp_path, source, draws, constants):
    probe = tmp_path / "probe.py"
    probe.write_text(source, encoding="utf-8")
    assert len(draw_literal_findings(probe, tmp_path)) == draws
    assert len(surface_constant_findings(probe, tmp_path)) == constants


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


def test_the_code_editor_scheme_follows_the_theme_until_one_is_chosen(settings_dir, tmp_path):
    from emtk import theme
    from emtk.widgets.text_editor import LIGHT_PALETTE, TextEditor, Token

    from chisurf.plugins.core.code_editor.gui.editor_app import EditorModel
    from chisurf.plugins.core.code_editor.gui.editor_preferences import COLOR_SCHEMES, THEME_SCHEME

    model = EditorModel(tmp_path)
    assert model.color_scheme == THEME_SCHEME
    editor = TextEditor("x = 1")
    model.apply_editor_preferences(editor, apply_language=False)
    assert model.display_colors == COLOR_SCHEMES["Dark"]
    theme.apply_theme("light")
    model.apply_editor_preferences(editor, apply_language=False)
    assert model.display_colors == COLOR_SCHEMES["Light"]
    assert editor.palette[Token.KEYWORD] == LIGHT_PALETTE[Token.KEYWORD]
    model.set_color_scheme("Monokai")  # an explicit scheme wins over the theme
    model.apply_editor_preferences(editor, apply_language=False)
    assert model.display_colors == COLOR_SCHEMES["Monokai"]
    model.set_color_scheme(THEME_SCHEME)
    model.set_display_color("paper_color", "#fafafa")  # an edited colour is a choice too
    assert model.color_scheme == "Light"


def test_a_node_graph_follows_a_theme_switch_with_its_host_colours(settings_dir):
    from emtk import nodes, style, theme
    from emtk.testing import RecordingPainter

    from chisurf.emtk.node_editor.control import GraphControl

    control = GraphControl()
    control.style_hooks.append(
        lambda s: s.colors.__setitem__(nodes.Col.GRID_BACKGROUND, tuple(style.PLOT_BG))
    )
    dark_line = control.editor.style.colors[nodes.Col.GRID_LINE]
    theme.apply_theme("light")
    control.draw(RecordingPainter(), 0.0, 0.0, 300.0, 200.0)
    colours = control.editor.style.colors
    assert colours[nodes.Col.GRID_BACKGROUND] == tuple(theme.LIGHT["PLOT_BG"])
    assert colours[nodes.Col.GRID_LINE][:3] == theme.LIGHT["TEXT"][:3] != dark_line[:3]
    assert colours[nodes.Col.NODE_BACKGROUND] == nodes._LIGHT[nodes.Col.NODE_BACKGROUND]
