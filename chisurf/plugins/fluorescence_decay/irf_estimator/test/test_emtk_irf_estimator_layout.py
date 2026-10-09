"""Layout of the IRF estimator at 1200x800 and 800x600, asserted on the recorded draw (after one real estimate).

Defects the screenshots showed: parameter fields stretched across the dock without the spin arrows the Qt boxes have,
toolbar buttons two per row and different widths at the two sizes, pictograms touching their captions, a long path
wrapped mid-word.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_layout_checks import (
    SIZES,
    assert_aligned,
    assert_disjoint,
    assert_icons_clear,
    assert_texts_apart,
)  # noqa: E402
from chisurf.plugins.fluorescence_decay.irf_estimator.test.test_emtk_irf_estimator_clicks import (  # noqa: E402
    DECAY,
    IRFEstimatorApp,
    Ui,
    hermetic,
)  # noqa: F401
# isort: on


@pytest.fixture(scope="module")
def app_ui():
    ui = Ui(IRFEstimatorApp(), SIZES[0])
    ui.drop(DECAY)
    ui.type_into("rl_iterations", "100")
    ui.click("use_range_selection")
    ui.click("request_estimate")
    ui.settle()
    yield ui
    ui.app.close()


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def ui(request, app_ui):
    app_ui.size = request.param
    app_ui.draw(4)
    return app_ui


def dock_right(ui):
    return 0.32 * ui.size[0] + 2


FIELDS = [
    "dt",
    "window_length",
    "polyorder",
    "rl_iterations",
    "regularization",
    "manual_background",
    "first_channel",
    "last_channel",
]


def test_every_control_lies_inside_the_parameters_dock_and_the_window(ui):
    for name in [
        "request_load",
        "request_dataset",
        "request_save",
        "request_transfer",
        "request_guide",
        "request_help",
        "request_estimate",
        "use_range_selection",
        "auto_update_enabled",
        *FIELDS,
    ]:
        x, y, w, h = ui.app.item_rects[name]
        assert x >= 0 and x + w <= dock_right(ui), (name, ui.app.item_rects[name])
        assert y + h <= ui.size[1], (name, "below the window")


def test_parameter_fields_start_in_one_caption_column_and_are_short(ui):
    assert_aligned(ui.app.item_rects, FIELDS)
    for name in FIELDS:
        assert ui.app.item_rects[name][2] <= 200, (name, ui.app.item_rects[name])


def test_toolbar_buttons_do_not_overlap_and_the_estimate_button_is_in_view(ui):
    assert_disjoint(
        ui.app.item_rects, ["request_load", "request_dataset", "request_save", "request_transfer"]
    )
    assert (
        ui.app.item_rects["request_estimate"][1] + ui.app.item_rects["request_estimate"][3]
        <= ui.size[1]
    )


def unrotated(painter):
    """The recording without the rotated y-axis label (it is recorded as an unrotated box over the tick labels)."""
    from emtk.testing import RecordingPainter

    out = RecordingPainter()
    out.texts = [t for t in painter.texts if t[5] != "Intensity (counts/channel)"]
    out.strings = [t[5] for t in out.texts]
    return out


def test_no_overlapping_texts_and_clear_pictograms(ui):
    assert_texts_apart(unrotated(ui.last))
    assert_icons_clear(ui.last)


def test_the_plot_gets_the_space_has_axes_and_the_results_are_complete(ui):
    x, y, w, h = ui.app.item_rects["plot"]
    assert w >= 0.6 * ui.size[0] - 30 and h >= 0.55 * ui.size[1]
    shown = ui.last.strings
    for text in (
        "Time (ns)",
        "Intensity (counts/channel)",
        "Measured Decay",
        "Estimated IRF (scaled)",
    ):
        assert text in shown, text
    for label in ("Lifetime (τ):", "Decay Rate (k):", "Amplitude (A):", "Offset (C):"):
        assert label in shown, label


def test_the_idle_window_has_no_misleading_controls():
    for size in SIZES:
        ui = Ui(IRFEstimatorApp(), size)
        try:
            for name in ("request_estimate", "request_save", "request_transfer"):
                assert not ui.app.form_model.enabled(name)
            assert_texts_apart(unrotated(ui.last))
            assert ui.shown("Time (ns)")
        finally:
            ui.app.close()
