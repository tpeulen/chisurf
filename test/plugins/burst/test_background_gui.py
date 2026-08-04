"""Headless test for the Burst Background Estimation diagnostics plots.

The tool was rebuilt as an AutoForm over a Qt-free view model: the two plots are
now the ``bg_iht_plot`` / ``bg_rate_plot`` sections of ``background.view.json``
rather than ``iht_plot`` / ``rate_plot`` attributes on the widget, and the
detector colouring moved to :func:`...view_model.det_color`. This test follows
the split -- what is drawn is asserted on the view model, and that it draws and
paints is asserted on the sections.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("qtpy")


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _diagnostics():
    """Return a two-detector diagnostics dict with a known background tail."""
    from chisurf.core.fluorescence.burst import interphoton_time_diagnostics

    rng = np.random.default_rng(0)

    def dt(rate):
        return np.concatenate([
            rng.exponential(1 / rate, 20000),
            rng.exponential(1 / 200.0, 5000),
        ])

    return {"m.ptu": {
        "green": interphoton_time_diagnostics(dt(2.0), tail_fraction=0.2),
        "red": interphoton_time_diagnostics(dt(3.5), tail_fraction=0.2),
    }}


def test_the_view_model_turns_diagnostics_into_plottable_series():
    """The plotted content is Qt-free and testable without a widget."""
    from chisurf.plugins.burst.burst_background.view_model import BackgroundViewModel

    model = BackgroundViewModel(show_channel_definition=False)
    assert model.iht_series() == []

    model.diagnostics = _diagnostics()
    series = model.iht_series()

    # Two detectors, each contributing a histogram and its fitted tail.
    assert len(series) >= 4
    names = {s.get("name") for s in series if s.get("name")}
    assert any("green" in str(n) for n in names)
    assert any("red" in str(n) for n in names)
    for s in series:
        assert len(s["x"]) == len(s["y"])
        assert np.all(np.isfinite(np.asarray(s["y"], dtype=float)))

    model.clear()
    assert model.iht_series() == []


def test_diagnostics_plots_build_and_render(qapp, tmp_path):
    """Both plot sections take the diagnostics and paint headlessly."""
    from chisurf.plugins.burst.burst_background import BurstBackgroundEstimator
    from chisurf.plugins.burst.burst_background.gui import sections

    w = BurstBackgroundEstimator(show_channel_definition=False)
    iht = w.findChildren(sections._IhtPlotSection)
    rate = w.findChildren(sections._RatePlotSection)
    assert len(iht) == 1 and len(rate) == 1, "the view spec must build both plots"

    w.model.diagnostics = _diagnostics()
    w.model.notify()

    # The series reached the plot: its CSV export is the public way to ask.
    exported = tmp_path / "iht.csv"
    iht[0].plot.export_csv(str(exported))
    rows = exported.read_text().splitlines()
    assert len(rows) > 1, "the inter-photon-time plot holds no series"

    w.resize(720, 600)
    assert not w.grab().isNull()

    w.model.clear()
    empty = tmp_path / "empty.csv"
    iht[0].plot.export_csv(str(empty))
    assert empty.read_text().strip() == "", "clearing must drop the plotted series"


def test_semantic_detector_colors():
    """Green and red detectors keep their meaning; anything else is stable."""
    from chisurf.plugins.burst.burst_background.view_model import det_color

    assert det_color("green") == (44, 160, 44)
    assert det_color("red") == (214, 39, 40)
    assert det_color("spot7") == det_color("spot7")
