"""The native plot settings editor against the Qt tool: fields, ranges, actions, preview, no Qt.

Hermetic: every test points the settings folder at a temporary directory and runs on a
private copy of the ``gui.plot`` settings, so Apply never changes the process settings and
Save writes to the temporary folder, never to ``~/.chisurf``.
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path

import pytest
import yaml
from emtk.testing import PixelPainter, RecordingPainter
from emtk.view_form import _commit, parse_value

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SPEC_FILE = GUI / "plot_settings_emtk.view.json"

#: Non-default values for every field, in the layout of the ``gui.plot`` settings.
SEEDED = {
    "backend": "pyqtgraph",
    "colors": {
        "data": "#112233",
        "model": "#445566",
        "irf": "#778899",
        "residuals": "#aabbcc",
        "auto_corr": "#ddeeff",
        "region_selector": "#123456",
        "region_selector_alpha": 77,
        "active_transparency": 0.8,
        "inactive_transparency": 0.4,
        "extra_key": "kept",
    },
    "line_width": 3.5,
    "font_size": 11,
    "enable_grid": False,
    "grid_alpha": 0.6,
    "show_data_grid": False,
    "show_residual_grid": False,
    "show_acorr_grid": False,
    "enable_region_selector": False,
    "show_legend": True,
    "hideTitle": False,
    "label_axis": True,
    "node_graph": {
        "show_grid": False,
        "grid_line_width": 1.25,
        "grid_opacity": 0.3,
        "grid_spacing": 40.0,
        "node_size": 20.5,
    },
    "pyqtgraph_config": {
        "antialias": True,
        "background": "w",
        "foreground": "k",
        "leftButtonPan": False,
    },
    "other_plot_key": 5,
}


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    """A temporary settings folder and a private, seeded ``gui.plot`` dictionary."""
    folder = tmp_path / "settings"
    folder.mkdir()
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(folder))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(folder))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(folder / "m.db"))
    import chisurf.core.settings as css

    gui = copy.deepcopy(css.cs_settings.get("gui", {}))
    gui["plot"] = copy.deepcopy(SEEDED)
    monkeypatch.setitem(css.cs_settings, "gui", gui)
    return folder


@pytest.fixture
def empty_plot_settings(monkeypatch):
    """No ``gui.plot`` settings at all: every field falls back to its default."""
    import chisurf.core.settings as css

    gui = copy.deepcopy(css.cs_settings.get("gui", {}))
    gui["plot"] = {}
    monkeypatch.setitem(css.cs_settings, "gui", gui)


def live():
    import chisurf.core.settings as css

    return css.cs_settings["gui"]["plot"]


def make_model():
    from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

    return PlotSettingsModel()


def make_app(model=None):
    from chisurf.plugins.core.plot_settings.gui.app import PlotSettingsApp

    return PlotSettingsApp(model or make_model())


def draw(app, size=(1200, 800), frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def draw_pixels(app, size=(1200, 800), frames=3):
    painter = None
    for _ in range(frames):
        painter = PixelPainter(*size)
        app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
    return painter


def spec():
    return json.loads(SPEC_FILE.read_text(encoding="utf-8"))


def walk(sections):
    for section in sections:
        yield section
        yield from walk(section.get("sections", []))


def find_field(attr):
    return next(s for s in walk(spec()["sections"]) if s.get("attr") == attr)


SECTION_TITLES = (
    "Rendering Backend",
    "Colors",
    "Appearance",
    "Node Graphs (Global View)",
    "Advanced: pyqtgraph Configuration",
)


def open_all(app):
    for title in SECTION_TITLES:
        app.form.folds[title] = True


def rect_center(rect):
    return rect[0] + rect[2] / 2.0, rect[1] + rect[3] / 2.0


def click(app, name, size=(1200, 800)):
    """Press and release the pointer on the drawn control *name*."""
    draw(app, size)
    x, y = rect_center(app.form.rects[name])
    app.hover(x, y)
    draw(app, size, 1)
    app.press(x, y)
    draw(app, size, 1)
    app.release()
    draw(app, size, 2)


# ── Qt tool as the reference (the widget is built offscreen) ─────────────


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qtpy = pytest.importorskip("qtpy")
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def qt_widget(qapp):
    from chisurf.plugins.core.plot_settings.gui.tool import PlotSettingsWidget

    return PlotSettingsWidget()


def strip_widget_noise(settings):
    """The Qt collection holds only what the controls hold."""
    return json.loads(json.dumps(settings))


@pytest.mark.gui
def test_defaults_equal_the_qt_widget(qapp, empty_plot_settings):
    widget = qt_widget(qapp)
    model = make_model()
    assert strip_widget_noise(model.collect()) == strip_widget_noise(widget._collect_settings())


@pytest.mark.gui
def test_seeded_settings_load_like_the_qt_widget(qapp):
    widget = qt_widget(qapp)
    model = make_model()
    collected = model.collect()
    assert strip_widget_noise(collected) == strip_widget_noise(widget._collect_settings())
    assert collected["colors"]["data"] == "#112233"
    assert collected["colors"]["region_selector_alpha"] == 77
    assert collected["node_graph"]["grid_spacing"] == 40.0
    assert collected["pyqtgraph_config"]["background"] == "w"


@pytest.mark.gui
def test_ranges_equal_the_qt_controls(qapp):
    from chisurf.plugins.core.plot_settings.gui.model import RANGES

    widget = qt_widget(qapp)
    qt = {
        "region_alpha": widget.alpha_slider,
        "active_transparency": widget.active_transparency,
        "inactive_transparency": widget.inactive_transparency,
        "line_width": widget.line_width,
        "font_size": widget.font_size,
        "grid_alpha_pct": widget.grid_alpha,
        "ng_line_width": widget.ng_line_width,
        "ng_grid_opacity_pct": widget.ng_grid_opacity,
        "ng_grid_spacing": widget.ng_grid_spacing,
        "ng_node_size": widget.ng_node_size,
    }
    assert set(qt) == set(RANGES)
    for attr, control in qt.items():
        lo, hi = RANGES[attr]
        assert (lo, hi) == (control.minimum(), control.maximum()), attr


@pytest.mark.gui
def test_sections_start_in_the_qt_fold_state(qapp):
    from chisurf.gui.widgets.collapsible_box import CollapsibleBox

    widget = qt_widget(qapp)
    qt = {b.title(): b.is_expanded() for b in widget.findChildren(CollapsibleBox)}
    for panel in spec()["sections"][0]["sections"]:
        assert panel["title"] in qt, panel["title"]
        assert (not panel["collapsed"]) is qt[panel["title"]], panel["title"]
    assert [p["title"] for p in spec()["sections"][0]["sections"]] == list(SECTION_TITLES)
    assert qt["Preview"] is True  # the preview is its own docked window, always open


@pytest.mark.gui
def test_backend_choices_equal_the_qt_combo(qapp):
    from chisurf.gui.chiplot import available_backends

    widget = qt_widget(qapp)
    qt_items = [widget.backend_combo.itemText(i) for i in range(widget.backend_combo.count())]
    assert list(make_model().backends) == qt_items == available_backends()


# ── the model ────────────────────────────────────────────────────────────


def test_every_spec_key_exists_on_the_model():
    model = make_model()
    for section in walk(spec()["sections"]):
        for key in ("attr", "call", "source", "options_source"):
            if section.get(key):
                assert hasattr(model, section[key]), (key, section[key])
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
    from chisurf.plugins.core.plot_settings.gui.model import FIELDS

    spec_attrs = {s["attr"] for s in walk(spec()["sections"]) if s.get("attr")}
    assert spec_attrs == set(FIELDS)


def test_spec_ranges_equal_the_model_ranges():
    from chisurf.plugins.core.plot_settings.gui.model import INT_FIELDS, RANGES

    for attr, (lo, hi) in RANGES.items():
        section = find_field(attr)
        assert (section["minimum"], section["maximum"]) == (lo, hi), attr
        assert section["kind"] == ("int" if attr in INT_FIELDS else "float"), attr


def test_values_clamp_as_in_qt():
    model = make_model()
    model.set_value("line_width", 99)
    model.set_value("region_alpha", 300)
    model.set_value("ng_grid_spacing", 1)
    model.set_value("active_transparency", -2)
    model.set_value("font_size", 7.6)
    assert (model.line_width, model.region_alpha, model.ng_grid_spacing) == (10.0, 255, 4)
    assert model.active_transparency == 0.0
    assert model.font_size == 8 and isinstance(model.font_size, int)
    # what the form does when a number is typed: parse and clamp with the spec's limits
    assert parse_value("99", find_field("line_width")) == 10.0
    assert parse_value("0.1", find_field("line_width")) == 0.5
    assert parse_value("-5", find_field("region_alpha")) == 0
    assert parse_value("auto", find_field("font_size")) == 0
    assert parse_value("12 px", find_field("ng_grid_spacing")) == 12
    assert parse_value("abc", find_field("line_width")) is None


def test_loading_clamps_out_of_range_settings(monkeypatch):
    live()["line_width"] = 50.0
    live()["colors"]["region_selector_alpha"] = 999
    model = make_model()
    assert model.line_width == 10.0 and model.region_alpha == 255


def test_colour_edit_marks_dirty_and_updates_the_preview():
    model = make_model()
    assert not model.dirty
    before = {s["label"]: s["color"] for s in model.preview_series()}
    assert before == {"data": "#112233", "model": "#445566", "IRF": "#778899"}
    model.color_data = "#ff0000"
    assert model.dirty
    after = {s["label"]: s["color"] for s in model.preview_series()}
    assert after["data"] == "#ff0000" and after["model"] == before["model"]
    model.color_model = "#00ff00"
    model.color_irf = "#0000ff"
    assert [s["color"] for s in model.preview_series()] == ["#ff0000", "#00ff00", "#0000ff"]
    # an edit that is undone is not an edit
    model.color_data, model.color_model, model.color_irf = "#112233", "#445566", "#778899"
    assert not model.dirty


def test_every_colour_field_marks_dirty():
    from chisurf.plugins.core.plot_settings.gui.model import COLOR_KEYS

    for _, attr, _ in COLOR_KEYS:
        model = make_model()
        setattr(model, attr, "#010203")
        assert model.dirty, attr


def test_apply_updates_the_live_settings_and_keeps_foreign_keys():
    model = make_model()
    model.color_data = "#ff0000"
    model.set_value("line_width", 6)
    model.ng_grid_spacing = 50
    assert live()["colors"]["data"] == "#112233"  # edits are pending, not live
    model.apply()
    assert live()["colors"]["data"] == "#ff0000"
    assert live()["line_width"] == 6.0
    assert live()["node_graph"]["grid_spacing"] == 50.0
    assert live()["colors"]["extra_key"] == "kept"
    assert live()["other_plot_key"] == 5
    assert not model.dirty
    assert "Applied" in model.status_text


def test_save_writes_the_temporary_settings_file(hermetic):
    model = make_model()
    model.color_model = "#abcdef"
    model.backend = "emtk"
    path = hermetic / "settings_chisurf.yaml"
    path.write_text("other_section:\n  keep: 1\ngui:\n  theme: dark\n", encoding="utf-8")
    model.save()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["other_section"] == {"keep": 1}
    assert data["gui"]["theme"] == "dark"
    assert data["gui"]["plot"]["colors"]["model"] == "#abcdef"
    assert data["gui"]["plot"]["backend"] == "emtk"
    assert data["gui"]["plot"]["node_graph"]["grid_spacing"] == 40.0
    assert live()["colors"]["model"] == "#abcdef"  # Save applies first
    assert str(path) in model.status_text and not model.dirty


def test_save_creates_the_file_when_there_is_none(hermetic):
    model = make_model()
    model.save()
    data = yaml.safe_load((hermetic / "settings_chisurf.yaml").read_text(encoding="utf-8"))
    assert data["gui"]["plot"]["colors"]["data"] == "#112233"


def test_save_failure_is_reported_not_raised(hermetic, monkeypatch):
    model = make_model()
    monkeypatch.setattr(model, "settings_file", lambda: hermetic)  # a directory: cannot be written
    model.color_data = "#fefefe"
    model.save()
    assert model.status_text.startswith("Save failed")
    assert live()["colors"]["data"] == "#fefefe"  # the Apply half still happened


def test_reset_restores_the_active_settings():
    model = make_model()
    model.color_data = "#ff0000"
    model.set_value("line_width", 9)
    model.show_legend = False
    assert model.dirty
    model.reset()
    assert not model.dirty
    assert model.color_data == "#112233" and model.line_width == 3.5 and model.show_legend is True
    assert live()["colors"]["data"] == "#112233"  # reset never wrote anything
    # after Apply, Reset reloads what was applied
    model.color_data = "#00ff00"
    model.apply()
    model.color_data = "#ff0000"
    model.reset()
    assert model.color_data == "#00ff00"


def test_backend_choice_and_hint():
    model = make_model()
    assert model.backend == "pyqtgraph" and model.backends == ("emtk", "pyqtgraph")
    backend = find_field("backend")
    assert backend["type"] == "choice" and backend["options_source"] == "backends"
    hint = "Changes apply on next application start or when a new plot is created."
    texts = [s.get("text") for s in walk(spec()["sections"]) if s.get("type") == "info"]
    assert hint in texts
    app = make_app()
    assert hint in draw(app).strings
    model.backend = "emtk"
    assert model.dirty
    model.apply()
    assert live()["backend"] == "emtk"


def test_preview_sample_curves_are_deterministic_styling_samples():
    series = make_model().preview_series()
    assert [s["label"] for s in series] == ["data", "model", "IRF"]
    data, model_curve, irf = series
    assert len(data["x"]) == 256 and data["x"][0] == 0.0 and data["x"][-1] == 10.0
    # 1000 exp(0) + 200 exp(0) + 2 background, as the Qt preview computes it
    assert data["y"][0] == pytest.approx(1202.0)
    assert model_curve["y"][0] == pytest.approx(1192.0)
    assert irf["y"].max() == pytest.approx(502.0, rel=2e-2)
    assert (data["width"], model_curve["width"], irf["width"]) == (3.5, 3.5, 1.5)
    assert [s["dash"] for s in series] == [False, True, False]


def test_preview_follows_grid_and_background_settings():
    model = make_model()
    assert model.preview_dark is False and model.preview_grid is False  # seeded: w, no grid
    model.pg_background = "k"
    model.enable_grid, model.show_data_grid = True, True
    assert model.preview_dark and model.preview_grid
    model.show_data_grid = False
    assert not model.preview_grid


# ── the app ──────────────────────────────────────────────────────────────


def test_preview_draws_three_series_with_the_chosen_colours():
    app = make_app()
    draw(app)
    assert [(r["label"], r["color"]) for r in app.preview_drawn] == [
        ("data", "#112233"),
        ("model", "#445566"),
        ("IRF", "#778899"),
    ]
    assert [r["width"] for r in app.preview_drawn] == [3.5, 3.5, 1.5]
    assert all(r["points"] == 256 for r in app.preview_drawn)
    app.model.color_data = "#ff00ff"
    app.model.color_irf = "#00ffff"
    app.model.set_value("line_width", 5)
    draw(app)
    assert [(r["label"], r["color"], r["width"]) for r in app.preview_drawn] == [
        ("data", "#ff00ff", 5.0),
        ("model", "#445566", 5.0),
        ("IRF", "#00ffff", 1.5),
    ]


def pixel_count(painter, rgb, tolerance=0):
    px = painter.px
    count = 0
    for i in range(0, len(px), 4):
        if (
            abs(px[i] - rgb[0]) <= tolerance
            and abs(px[i + 1] - rgb[1]) <= tolerance
            and abs(px[i + 2] - rgb[2]) <= tolerance
        ):
            count += 1
    return count


def test_preview_pixels_carry_the_chosen_colours():
    model = make_model()
    model.pg_background = "k"
    model.color_data = "#ff3300"
    model.color_model = "#00ee11"
    model.color_irf = "#0033ff"
    model.set_value("line_width", 6)
    app = make_app(model)
    painter = draw_pixels(app)
    for rgb in ((0xFF, 0x33, 0x00), (0x00, 0xEE, 0x11), (0x00, 0x33, 0xFF)):
        assert pixel_count(painter, rgb) > 50, rgb
    model.color_data = "#7f00ff"
    painter = draw_pixels(app)
    assert pixel_count(painter, (0xFF, 0x33, 0x00)) == 0
    assert pixel_count(painter, (0x7F, 0x00, 0xFF)) > 50


def test_preview_legend_and_axis_labels_follow_the_settings():
    model = make_model()
    app = make_app(model)
    strings = draw(app).strings
    assert {"data", "model", "IRF"} <= set(strings) and "counts" in strings and "t / ns" in strings
    model.show_legend = False
    model.label_axis = False
    strings = draw(app).strings
    assert not {"data", "model", "IRF"} & set(strings)
    assert "counts" not in strings and "t / ns" not in strings
    assert "1000" in strings  # the log axis is labelled in decades


def test_sections_start_folded_like_qt_and_expand():
    app = make_app()
    strings = draw(app).strings
    for title in SECTION_TITLES:
        assert title in strings
    # Rendering Backend and Colors open, the rest folded
    assert "Active backend" in strings and "Data curve" in strings
    for hidden in ("Line width", "Show grid", "Antialiasing", "Grid on residuals"):
        assert hidden not in strings
    click(app, "Appearance.fold")
    strings = draw(app).strings
    assert "Line width" in strings and "Grid on residuals" in strings
    click(app, "Colors.fold")
    assert "Data curve" not in draw(app).strings
    assert app.form.folds["Colors"] is False and app.form.folds["Appearance"] is True


def test_all_sections_expand_and_every_label_is_drawn():
    app = make_app()
    open_all(app)
    strings = set(draw(app, (1200, 3000)).strings)
    from chisurf.plugins.core.plot_settings.gui.model import COLOR_KEYS

    labels = [s["label"] for s in walk(spec()["sections"]) if s.get("label")]
    assert len(labels) == 30  # the 30 labelled controls of the Qt tool
    missing = [label for label in labels if label not in strings]
    assert missing == []
    assert {label for _, _, label in COLOR_KEYS} <= strings


def test_colour_swatch_opens_the_picker_and_a_pick_marks_dirty():
    app = make_app()
    draw(app)
    click(app, "color_data.swatch")
    assert "color_data" in app.form.pickers
    assert "color_data.picker" in app.form.rects
    section = find_field("color_data")
    _commit(app.model, section, "#0a0b0c", app.form)  # what the picker does on a pick
    assert app.model.color_data == "#0a0b0c" and app.model.dirty
    draw(app)
    assert app.preview_drawn[0]["color"] == "#0a0b0c"
    assert "Edits not applied yet" in draw(app).strings[-1] or any(
        "Edits not applied yet" in s for s in draw(app).strings
    )
    click(app, "color_data.swatch")
    assert "color_data" not in app.form.pickers


def test_typing_a_hex_colour_commits_and_rejects_garbage():
    section = find_field("color_data")
    assert parse_value("#ABC", section) == "#aabbcc"
    assert parse_value("ff8800", section) == "#ff8800"
    assert parse_value("not a colour", section) is None


def test_apply_save_reset_buttons_through_the_ui(hermetic):
    app = make_app()
    app.model.color_data = "#ff0000"
    draw(app)
    assert any("Edits not applied yet" in s for s in draw(app).strings)
    click(app, "apply")
    assert live()["colors"]["data"] == "#ff0000" and not app.model.dirty
    assert any("Applied" in s for s in draw(app).strings)
    app.model.color_data = "#00ff00"
    click(app, "save")
    saved = yaml.safe_load((hermetic / "settings_chisurf.yaml").read_text(encoding="utf-8"))
    assert saved["gui"]["plot"]["colors"]["data"] == "#00ff00"
    app.model.color_data = "#0000ff"
    click(app, "reset")
    assert app.model.color_data == "#00ff00" and not app.model.dirty


@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (420, 700)])
def test_app_draws_empty_and_populated_and_fills_the_window(size, empty_plot_settings):
    app = make_app()  # empty settings: every default
    assert draw(app, size).strings
    app.model.load(copy.deepcopy(SEEDED))
    open_all(app)
    painter = draw_pixels(app, size)
    width, height = size
    px = painter.px

    def lit(x0, x1, y0, y1):
        for y in range(y0, y1):
            row = (y * width) * 4
            for x in range(x0, x1):
                if px[row + x * 4] or px[row + x * 4 + 1] or px[row + x * 4 + 2]:
                    return True
        return False

    # content reaches every edge: the sections at the top, the preview to the bottom-right
    assert lit(0, width, 0, 20)
    assert lit(0, width, height - 12, height)
    assert lit(width - 12, width, 0, height)
    assert lit(0, 12, 0, height)
    # and the window is not a column in a corner: the right-hand third is used throughout
    third = width * 2 // 3
    assert lit(third, width, 0, height // 2) and lit(third, width, height // 2, height)


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("plot_settings")
    open_all(app)
    inventory = emtk_inventory(app)
    assert inventory["controls_without_tooltip"] == []
    assert len(inventory["interactive"]) >= 25
    for section in walk(spec()["sections"]):
        if section.get("type") in ("value", "choice", "toggle", "info", "button_row", "panel", "custom"):
            assert section.get("description"), section.get("attr") or section.get("title")
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("plot_settings")
    assert result["ok"], result["output"]


def test_settings_round_trip():
    app = make_app()
    draw(app)
    click(app, "Appearance.fold")
    click(app, "Colors.fold")
    saved = app.export_settings()
    assert saved == {"folds": {"Appearance": True, "Colors": False}}
    json.dumps(saved)
    other = make_app()
    other.restore_settings(saved)
    strings = draw(other).strings
    assert "Line width" in strings and "Data curve" not in strings
    other.restore_settings({})  # nothing to restore changes nothing
    other.restore_settings({"folds": "garbage"})
    assert other.form.folds == {"Appearance": True, "Colors": False}


def test_guide_steps_point_at_controls_the_app_draws():
    from chisurf.emtk.help_guide import EmTkGuidedTour

    app = make_app()
    open_all(app)
    draw(app)
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    assert len(steps) >= 6
    for step in steps:
        name = EmTkGuidedTour._target_key(step["target"])
        rect = app.item_rects.get(name) or app.form.rects.get(name)
        assert rect is not None, f"{step['title']}: nothing drawn for {name!r}"
    awaiting = [EmTkGuidedTour._target_key(s["target"]) for s in steps if s.get("await")]
    assert awaiting == [
        "backend",
        "color_data",
        "apply",
        "Appearance.fold",
        "Advanced: pyqtgraph Configuration.fold",
    ]


def test_the_tour_hears_the_colour_and_the_apply():
    app = make_app()
    draw(app)
    heard = []
    app.form.on_used = heard.append
    _commit(app.model, find_field("color_data"), "#010101", app.form)
    click(app, "apply")
    assert "color_data" in heard and "apply" in heard


def test_help_exists_and_its_links_are_live():
    help_text = (GUI / "help.md").read_text(encoding="utf-8")
    for word in ("Apply", "Save", "Reset", "preview"):
        assert word in help_text
    repo = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
    for target in re.findall(r"\]\((docs/[^)#]+)\)", help_text):
        assert (repo / target).is_file(), target
    app = make_app()
    draw(app)
    app.help_window.show()
    assert draw(app).strings


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_pressing_a_button_never_toggles_a_row_scrolled_out_of_view(size):
    """With every section open the form overflows its window; the buttons must still be the
    only thing a click on them reaches (a scrolling child let the clipped rows take it)."""
    app = make_app()
    open_all(app)
    for name, attr in (("apply", "Applied"), ("save", "Applied and saved"), ("reset", "Reloaded")):
        before = app.model.values()
        click(app, name, size)
        assert app.model.values() == before, name
        assert app.model.message.startswith(attr), name
