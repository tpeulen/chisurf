"""Layout of Lazy Lifetime Analysis at 1200x800 and 800x600, asserted on the recorded draw (after one real fit).

Defects the screenshots showed: the four file paths cut to a few characters beside their captions in a narrow dock, the
Results summary and Export button below the fold at 800 px, fields stretched across the dock, a pictogram touching
its caption.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_layout_checks import SIZES, assert_disjoint, assert_icons_clear, assert_texts_apart  # noqa: E402
from chisurf.plugins.fluorescence_decay.lltf.test.test_emtk_lltf_clicks import DECAY, IRF, LLTFApp, Ui, hermetic  # noqa: E402,F401
# isort: on


@pytest.fixture(scope="module")
def app_ui(tmp_path_factory):
    import os

    os.environ["MPLBACKEND"] = "Agg"
    ui = Ui(LLTFApp(), SIZES[0])
    ui.drop(DECAY, IRF)
    ui.app.model.output_dir = str(tmp_path_factory.mktemp("lltf_layout"))
    ui.type_into("n_lifetimes", "2")
    ui.click("Fit")
    ui.settle()
    yield ui
    ui.app.close()


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def ui(request, app_ui):
    app_ui.size = request.param
    app_ui.press_text("Results")
    app_ui.draw(4)
    return app_ui


def dock_right(ui):
    return 0.40 * ui.size[0]


def test_file_rows_show_a_readable_path_inside_the_inputs_dock(ui):
    for attr in ("decay_file", "irf_file", "config_file", "output_dir"):
        x, y, w, h = ui.app.item_rects[attr]
        assert w >= 150, (attr, w, "path field cut to a stub")
        assert x + w <= dock_right(ui) + 2, attr
    for key in ("Load...", "load_irf", "Edit...", "Select..."):
        x, y, w, h = ui.app.item_rects[key]
        assert x + w <= dock_right(ui) + 2 and y + h <= ui.size[1], key


def test_fit_and_stop_are_reachable_beside_the_options(ui):
    for key in ("Fit", "stop", "Guide", "help"):
        x, y, w, h = ui.app.item_rects[key]
        assert x + w <= dock_right(ui) + 2 and y + h <= ui.size[1], key
    assert_disjoint(ui.app.item_rects, ["Fit", "stop"])


def test_option_fields_are_short_and_inside_the_dock(ui):
    for attr in ("n_lifetimes", "max_lifetimes", "prob_threshold"):
        x, y, w, h = ui.app.item_rects[attr]
        assert x + w <= dock_right(ui) + 2, attr


def test_the_results_tab_is_complete_without_scrolling(ui):
    shown = ui.last.strings
    assert "Export result JSON" in " ".join(shown) and "Component" in shown and "Lifetime (ns)" in shown
    assert any(s.startswith("Number of lifetimes") for s in shown), "the summary is cut off"
    x, y, w, h = ui.app.item_rects["export_json"]
    assert y + h <= ui.size[1] * 0.55


def test_no_overlapping_texts_and_clear_pictograms(ui):
    assert_texts_apart(ui.last)
    assert_icons_clear(ui.last)


def test_the_plots_get_the_larger_part_of_the_window_and_have_axes(ui):
    shown = ui.last.strings
    assert "Time (ns)" in shown and "Counts" in shown and "Data" in shown and "Fit" in shown
    assert "Decay and fit" in shown and "Weighted residuals" in shown
