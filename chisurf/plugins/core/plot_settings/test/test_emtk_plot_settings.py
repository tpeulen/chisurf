"""Settings ▸ Plots, native emtk window: controls, live preview, layout, against the old tool.

Hermetic: every test runs on a private copy of the ``gui`` settings and a temporary
settings folder, so a change never reaches the process settings or ``~/.chisurf``.

The retired Qt tool's capture (``qt_reference.json``, recorded before it was deleted)
stays the inventory every control is checked against; what was dropped on purpose is
listed in :data:`RETIRED` with the reason.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SPEC = json.loads((GUI / "plot_settings_emtk.view.json").read_text(encoding="utf-8"))
QT = json.loads((HERE / "qt_reference.json").read_text(encoding="utf-8"))

#: Controls of the retired tool that are gone on purpose: each changed no plot.
RETIRED = {
    "backend": "one renderer (emtk): a choice with one option",
    "hide_title": "gui.plot.hideTitle was read by no plot",
    "pg_antialias": "pyqtgraph option; emtk always antialiases",
    "pg_left_button_pan": "pyqtgraph option; emtk plots pan with the left button",
    "pg_background": "pyqtgraph option; plots follow the theme",
    "pg_foreground": "pyqtgraph option; plots follow the theme",
}

#: Fields that style the node graphs, not the fit plots the preview shows.
NODE_GRAPH_FIELDS = (
    "ng_show_grid",
    "ng_line_width",
    "ng_grid_opacity_pct",
    "ng_grid_spacing",
    "ng_node_size",
)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path))
    import chisurf.core.settings as css

    monkeypatch.setitem(css.cs_settings, "gui", copy.deepcopy(css.cs_settings.get("gui", {})))
    return tmp_path


def make_app():
    from chisurf.plugins.core.plot_settings.gui.app import PlotSettingsApp
    from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

    return PlotSettingsApp(PlotSettingsModel(persist=False))


def draw(app, size=(1200, 800), frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def spec_controls(sections=SPEC["sections"]):
    for section in sections:
        if section.get("attr"):
            yield section
        yield from spec_controls(section.get("sections", []))


# ── inventory ──────────────────────────────────────────────────────────
def test_every_control_of_the_old_tool_is_here_or_retired_with_a_reason():
    from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

    old = (
        set(QT["ranges"])
        | {
            "color_data",
            "color_model",
            "color_irf",
            "color_residuals",
            "color_auto_corr",
            "color_region_selector",
            "enable_grid",
            "show_data_grid",
            "show_residual_grid",
            "show_acorr_grid",
            "enable_region_selector",
            "show_legend",
            "label_axis",
            "ng_show_grid",
        }
        | set(RETIRED)
    )
    drawn = {section["attr"] for section in spec_controls()}
    assert drawn == set(PlotSettingsModel.fields())
    missing = old - drawn - set(RETIRED)
    assert not missing, f"controls lost in the redesign: {sorted(missing)}"


def test_the_ranges_are_the_old_tools():
    from chisurf.plugins.core.plot_settings.gui.model import RANGES

    for attr, (lo, hi) in QT["ranges"].items():
        assert RANGES[attr] == (lo, hi), attr
    for section in spec_controls():
        if section["attr"] in RANGES and "minimum" in section:
            assert (section["minimum"], section["maximum"]) == RANGES[section["attr"]]


def test_every_control_and_panel_has_a_description():
    def walk(sections):
        for section in sections:
            yield section
            yield from walk(section.get("sections", []))

    for section in walk(SPEC["sections"]):
        if section.get("type") == "button_row":
            assert all(b.get("description") for b in section["buttons"])
        else:
            assert section.get("description"), section


def test_no_ui_string_names_pyqtgraph():
    for name in ("plot_settings_emtk.view.json", "guide.json", "help.md"):
        assert "pyqtgraph" not in (GUI / name).read_text(encoding="utf-8").lower(), name


def test_every_guide_step_points_at_a_drawn_control():
    app = make_app()
    for section in SPEC["sections"][0]["sections"]:
        if section.get("collapsible"):
            app.form.folds[section["title"]] = True
    draw(app, size=(1200, 1600))
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    for step in steps:
        name = step["target"]["name"]
        assert app.target_rect(name), f"guide step '{step['title']}' points at {name!r}, not drawn"


# ── the preview ────────────────────────────────────────────────────────
def test_the_sample_is_a_convolved_noisy_decay_and_a_close_but_inexact_fit():
    from chisurf.plugins.core.plot_settings.gui.model import preview_sample

    s = preview_sample()
    lo, hi = s["range"]
    data, model = s["data"], s["model"]
    # Poisson counts: whole numbers, with noise around the smooth model.
    assert np.all(data == np.round(data))
    # Convolved with the IRF: the decay peaks after the prompt, not on it, and rises
    # from the background over several channels instead of in one step.
    peak, prompt = int(np.argmax(data)), int(np.argmax(s["irf"]))
    assert peak > prompt
    assert data[prompt - 4] < 0.2 * data[peak] and data[prompt] > 0.3 * data[peak]
    # A background floor before the prompt.
    assert 0 < np.mean(data[:10]) < 20
    # The model does not sit on the data: the weighted residuals show a misfit.
    assert not np.allclose(model, data[lo:hi], rtol=0.02)
    assert abs(np.mean(s["wres"][-60:])) > 0.3 or abs(np.mean(s["wres"][:20])) > 0.3
    assert len(s["acorr"]) > 10


def test_the_preview_draws_three_panels_like_a_fit_window():
    app = make_app()
    draw(app)
    assert set(app.preview_panels) == {"acorr", "residuals", "data"}
    tops = [app.preview_panels[p]["rect"][1] for p in ("acorr", "residuals", "data")]
    assert tops == sorted(tops), "a.corr. on top, residuals under it, data below"
    labels = {row["label"] for row in app.preview_drawn}
    assert {"data", "model", "IRF", "w.res.", "a.corr.", "other fit"} <= labels


def _preview_signature(app):
    draw(app)
    return json.dumps(
        {
            "drawn": app.preview_drawn,
            "panels": {k: {**v, "rect": None} for k, v in app.preview_panels.items()},
            "scale": app.preview_scale,
        },
        sort_keys=True,
        default=str,
    )


CHANGES = {
    "color_data": "#00ff00",
    "color_model": "#00ff00",
    "color_irf": "#00ff00",
    "color_residuals": "#00ff00",
    "color_auto_corr": "#00ff00",
    "line_width": 5.0,
    "enable_region_selector": False,
    "color_region_selector": "#ffff00",
    "region_alpha": 200,
    "active_transparency": 0.5,
    "inactive_transparency": 0.9,
    "label_axis": False,
    "show_legend": False,
    "font_size": 16,
    "enable_grid": False,
    "grid_alpha_pct": 90,
    "show_data_grid": False,
    "show_residual_grid": False,
    "show_acorr_grid": False,
}


def test_the_changes_cover_every_fit_plot_setting():
    from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

    assert set(CHANGES) | set(NODE_GRAPH_FIELDS) == set(PlotSettingsModel.fields())


@pytest.mark.parametrize("attr", sorted(CHANGES))
def test_every_fit_plot_setting_changes_the_preview(attr):
    app = make_app()
    before = _preview_signature(app)
    setattr(app.model, attr, CHANGES[attr])
    assert _preview_signature(app) != before, f"{attr} does not show in the preview"


def test_colours_and_opacities_reach_the_drawn_series():
    app = make_app()
    app.model.color_model = "#123456"
    app.model.inactive_transparency = 0.5
    draw(app)
    model = next(r for r in app.preview_drawn if r["label"] == "model")
    other = [r for r in app.preview_drawn if r["label"] == "other fit"]
    assert model["color"] == "#123456" and model["alpha"] == 255
    assert other and all(r["alpha"] == 128 for r in other)
    data = next(r for r in app.preview_drawn if r["label"] == "data")
    assert data["width"] == pytest.approx(0.5 * model["width"])


# ── layout ─────────────────────────────────────────────────────────────
def test_wide_puts_the_preview_beside_the_controls_narrow_above_them():
    app = make_app()
    draw(app, size=(1400, 900))
    settings, preview = app.item_rects["settings"], app.item_rects["preview_plot"]
    assert preview[0] > settings[0] + settings[2] - 1, "preview right of the controls"
    draw(app, size=(560, 900))
    settings, preview = app.item_rects["settings"], app.item_rects["preview_plot"]
    assert preview[1] + preview[3] <= settings[1] + 1, "preview above the controls"


def test_a_change_is_flushed_once_the_mouse_is_up(hermetic):
    from chisurf.plugins.core.plot_settings.gui.app import PlotSettingsApp
    from chisurf.plugins.core.plot_settings.gui.model import PlotSettingsModel

    app = PlotSettingsApp(PlotSettingsModel())
    app.model.color_irf = "#010203"
    assert app.model.unsaved
    draw(app, frames=1)
    assert not app.model.unsaved
    assert "#010203" in (hermetic / "settings_chisurf.yaml").read_text(encoding="utf-8")


def test_window_state_round_trips():
    app = make_app()
    app.restore_settings({"folds": {"Node graphs": True}})
    assert app.export_settings() == {"folds": {"Node graphs": True}}
