"""Layout of the micro-time histogram at 1200x800 and 800x600, asserted on the recorded draw.

Defects the screenshots showed: the options as a tall column of label-above-field rows in a dock that cut them off, the
plot squeezed into a corner, an unsized file chooser, buttons one per line, the Compute button below the fold at 800 px.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_layout_checks import SIZES, assert_aligned, assert_disjoint, assert_icons_clear, assert_texts_apart  # noqa: E402
from chisurf.plugins.traj.traj_save_topology.test.real_input import hermetic  # noqa: E402,F401
from chisurf.plugins.tttr.microtime_histogram.tests.test_emtk_histogram_clicks import SETUP, SPC, Ui  # noqa: E402
from chisurf.plugins.tttr.microtime_histogram.gui.app import create_app  # noqa: E402
# isort: on


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def ui(request, tmp_path):
    ui = Ui(create_app(), request.param)
    ui.app.definition_changed(SETUP)
    ui.app.model.filetype = "SPC-130"
    ui.drop(SPC)
    ui.app.model.output = str(tmp_path / "decay.dat")
    ui.app.model.auto_save = False
    ui.click("compute")
    ui.settle()
    yield ui
    ui.app.close()


def left_edge_of_plot(ui):
    return ui.app.item_rects["plot"][0] - 70       # the axis labels start left of the plot item


def test_the_run_buttons_are_always_inside_the_dock_without_scrolling(ui):
    for name in ("compute", "save", "save_as", "transfer", "guide", "help"):
        x, y, w, h = ui.app.item_rects[name]
        assert x >= 0 and x + w <= left_edge_of_plot(ui), (name, ui.app.item_rects[name])
        assert y + h <= ui.size[1], (name, "is below the window")
    assert ui.app.item_rects["compute"][1] < 0.4 * ui.size[1]


def test_every_option_field_lies_inside_the_dock_and_the_window(ui):
    for name in ("detector", "parallel_text", "perpendicular_text", "window", "filetype", "binning", "dt_ns", "g_factor",
                 "vv_shift", "vh_shift", "output", "polarization", "polarized", "photon_files", "photon_list"):
        x, y, w, h = ui.app.item_rects[name]
        assert x >= 0 and x + w <= left_edge_of_plot(ui) + 5, (name, ui.app.item_rects[name])


def test_inputs_start_in_one_caption_column(ui):
    assert_aligned(ui.app.item_rects, ["parallel_text", "perpendicular_text", "detector", "window", "filetype", "binning"])
    assert_aligned(ui.app.item_rects, ["dt_ns", "g_factor", "vv_shift", "vh_shift"])


def test_number_fields_are_short_and_buttons_do_not_overlap(ui):
    for name in ("dt_ns", "g_factor", "vv_shift", "vh_shift"):
        assert ui.app.item_rects[name][2] <= 180, name
    assert_disjoint(ui.app.item_rects, ["compute", "save", "save_as", "transfer"])
    assert_disjoint(ui.app.item_rects, ["photon_files", "photon_folder", "photon_database"])


def test_file_buttons_share_a_row_when_they_fit(ui):
    rects = ui.app.item_rects
    if ui.size[0] >= 1200:
        assert rects["photon_files"][1] == rects["photon_folder"][1] == rects["photon_database"][1]


def test_texts_do_not_overlap_and_pictograms_are_clear(ui):
    assert_texts_apart(ui.last)
    assert_icons_clear(ui.last)


def test_the_plot_gets_the_space_and_has_axes_and_a_legend(ui):
    x, y, w, h = ui.app.item_rects["plot"]
    assert ui.app.item_rects["plot"][2] >= 0.45 * ui.size[0] and h >= 0.8 * ui.size[1] - 60
    shown = ui.last.strings
    assert "Time (ns)" in shown and "Counts" in shown and "VV + 2G VH" in shown


def test_the_idle_window_has_no_misleading_controls(tmp_path):
    for size in SIZES:
        ui = Ui(create_app(), size)
        try:
            ui.app.definition_changed(SETUP)
            ui.draw(3)
            for name in ("compute", "save", "save_as", "transfer"):
                assert not ui.app.enabled(name)
            assert ui.shown("Nothing queued.") and ui.shown("Time (ns)")
            assert_texts_apart(ui.last)
        finally:
            ui.app.close()


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_the_file_dialog_is_sized_and_inside_the_window(size):
    ui = Ui(create_app(), size)
    try:
        ui.click("photon_files")
        win = ui.app.dialog_window
        ui.draw(3)
        assert ui.shown("Cancel") and ui.shown("TTTR inputs")
        cx, cy, cw, ch = ui.text_rect("Cancel")
        assert cx + cw <= size[0] and cy + ch <= size[1]
    finally:
        ui.app.close()
