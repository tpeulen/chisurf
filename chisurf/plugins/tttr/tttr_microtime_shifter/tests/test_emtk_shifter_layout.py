"""Layout of the micro-time shifter at 1200x800 and 800x600, asserted on the recorded draw.

Defects the screenshots showed and these tests hold: field captions of the three panels starting at three different
x, the trigger fields stretched across the dock, the Save panel's buttons pushed off the dock at 800 px ("Save
batch" lost), the New sample dialog's fields ragged with their captions on the right and its Create / Cancel
buttons far below the form, a placeholder cut mid-word.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_layout_checks import (  # noqa: E402
    SIZES,
    assert_aligned,
    assert_disjoint,
    assert_icons_clear,
    assert_texts_apart,
    boxes,
)
from chisurf.plugins.traj.traj_save_topology.test.real_input import hermetic  # noqa: E402,F401
from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.plugins.tttr.tttr_microtime_shifter.gui.app import create_app  # noqa: E402
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.demo_data import build  # noqa: E402
from chisurf.plugins.tttr.tttr_microtime_shifter.tests.test_emtk_shifter_clicks import Ui  # noqa: E402
# isort: on


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return build(tmp_path_factory.mktemp("mts_layout") / "demo")


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def ui(request, demo):
    ui = Ui(create_app(), request.param)
    ui.drop(demo)
    ui.click("auto_align")
    yield ui
    ui.app.close()


def inside_dock(ui, name):
    """The control lies inside the controls dock (its right edge is where the histogram dock starts)."""
    x, y, w, h = ui.app.item_rects[name]
    plot_left = ui.plot_box()[0] - 60  # the plot's axis labels start left of its box
    assert x >= 0 and x + w <= plot_left, (
        f"{name} {ui.app.item_rects[name]} runs past the dock (plot at {plot_left})"
    )
    assert y + h <= ui.size[1] + 0.5, f"{name} is cut off at the bottom"


CONTROLS = [
    "auto_align",
    "save_dialog",
    "save_batch",
    "browse_output_folder",
    "output_folder",
    "trigger_level",
    "trigger_position",
    "global_shift",
    "shift_0",
    "shift_8",
    "reset_0",
    "reset_8",
    "show_trigger",
    "log_y",
]


def test_every_control_lies_inside_its_dock_and_the_window(ui):
    for name in CONTROLS:
        inside_dock(ui, name)
    for name in ("add_files", "add_folder", "add_database", "remove", "clear", "guide", "help"):
        x, y, w, h = ui.app.item_rects[name]
        assert x + w <= ui.plot_box()[0] - 60 and y + h <= ui.size[1], name


def test_no_two_strings_overlap_and_icons_are_clear_of_their_captions(ui):
    assert_texts_apart(ui.last)
    assert_icons_clear(ui.last)


def test_one_caption_column_for_the_fields_of_every_panel(ui):
    assert_aligned(
        ui.app.item_rects,
        ["trigger_level", "trigger_position", "global_shift", "shift_0", "shift_8"],
    )


def test_number_fields_are_short_not_dock_wide(ui):
    for name in ("trigger_level", "trigger_position", "global_shift", "shift_0", "shift_8"):
        assert ui.app.item_rects[name][2] <= 120, (name, ui.app.item_rects[name])


def test_buttons_do_not_overlap_each_other(ui):
    assert_disjoint(
        ui.app.item_rects,
        [
            "auto_align",
            "save_dialog",
            "browse_output_folder",
            "save_batch",
            "output_folder",
            "reset_0",
            "reset_8",
            "shift_0",
            "shift_8",
        ],
    )


def test_the_save_panel_is_complete_at_every_size(ui):
    shown = " ".join(ui.last.strings)
    for caption in ("Save shifted", "Browse", "Save batch", "Batch folder", "Output folder"):
        assert caption in shown, caption
    # a field's placeholder fits whole: the text is drawn where it fits, never cut mid-word
    placeholder = next(b for b in boxes(ui.last) if b[4] == "Output folder")
    assert (
        placeholder[0] + placeholder[2]
        <= ui.app.item_rects["output_folder"][0] + ui.app.item_rects["output_folder"][2]
    )


def test_the_histogram_gets_the_space_and_has_axes(ui):
    x0, y0, w, h = ui.plot_box()
    assert w >= 0.5 * ui.size[0] and h >= 0.6 * ui.size[1]
    shown = ui.last.strings
    assert "Micro-time bin" in shown and "Counts" in shown
    assert any(s.strip() == "1000" for s in shown) and "Routing 0" in shown and "Routing 8" in shown


def test_the_idle_window_has_no_stretched_or_misleading_controls(demo):
    for size in SIZES:
        ui = Ui(create_app(), size)
        try:
            assert ui.shown("No file loaded.")
            for name in ("auto_align", "save_dialog", "save_batch"):
                assert not ui.app.enabled(name)
            idle = RecordingPainter()
            idle.texts = [
                t for t in ui.last.texts if t[5] != "Counts"
            ]  # the rotated axis label is recorded unrotated
            idle.strings = [t[5] for t in idle.texts]
            assert_texts_apart(idle)
            for name in ("trigger_level", "global_shift"):
                assert ui.app.item_rects[name][2] <= 120
        finally:
            ui.app.close()


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_the_sample_dialog_is_one_aligned_form_with_its_buttons_under_it(size, demo):
    ui = Ui(create_app(), size)
    try:
        ui.app.new_sample()
        ui.draw(3)
        rects = ui.app.item_rects
        fields = [rects[f"sample_{k}"] for k in ("name", "entity_name", "sequence", "donor")]
        assert max(f[0] for f in fields) - min(f[0] for f in fields) <= 1.5, (
            "fields do not start in one column"
        )
        assert all(f[2] <= 330 for f in fields), fields
        create, cancel = rects["sample_create"], rects["sample_cancel"]
        assert create[1] > fields[-1][1] and create[1] + create[3] <= size[1]
        assert create[1] - (fields[-1][1] + fields[-1][3]) < 80, (
            "the buttons are far below the form"
        )
        assert create[0] + create[2] <= cancel[0]
        title = next(i for i, t in enumerate(ui.last.texts) if t[5] == "New MMFDB sample")
        dialog = RecordingPainter()
        dialog.texts = ui.last.texts[
            title:
        ]  # what the dialog drew (the docks beneath it are covered)
        dialog.strings = [t[5] for t in dialog.texts]
        assert_texts_apart(dialog)
    finally:
        ui.app.close()
