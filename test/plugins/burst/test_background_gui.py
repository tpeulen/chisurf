"""Headless test for the Burst Background Estimation diagnostics plots."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("qtpy")
pytest.importorskip("pyqtgraph")


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_diagnostics_plots_build_and_render(qapp):
    from qtpy import QtWidgets  # noqa: F401
    from chisurf.plugins.burst.burst_background import BurstBackgroundEstimator
    from chisurf.core.fluorescence.burst import interphoton_time_diagnostics

    w = BurstBackgroundEstimator(show_channel_definition=False)
    assert hasattr(w, "iht_plot") and hasattr(w, "rate_plot")

    rng = np.random.default_rng(0)
    def dt(rate):
        return np.concatenate([rng.exponential(1 / rate, 20000),
                               rng.exponential(1 / 200.0, 5000)])
    w.diagnostics = {"m.ptu": {
        "green": interphoton_time_diagnostics(dt(2.0), tail_fraction=0.2),
        "red": interphoton_time_diagnostics(dt(3.5), tail_fraction=0.2),
    }}
    w._update_plots()

    # both plots received data items (histogram points + fit lines; rate bars)
    assert len(w.iht_plot.listDataItems()) >= 2
    assert len(w.rate_plot.items()) >= 1

    # the widget paints headlessly
    w.resize(720, 600)
    pm = w.grab()
    assert not pm.isNull()

    # clearing removes the plotted data
    w._clear_files()
    assert len(w.iht_plot.listDataItems()) == 0


def test_semantic_detector_colors(qapp):
    from chisurf.plugins.burst.burst_background import _det_color
    assert _det_color("green") == (44, 160, 44)
    assert _det_color("red") == (214, 39, 40)
    # unknown names are deterministic
    assert _det_color("spot7") == _det_color("spot7")
