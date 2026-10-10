"""Headless test for the Burst Background Estimation diagnostics plots.

What is drawn is asserted on the Qt-free view model, and that it paints is asserted on the native app.
"""

from __future__ import annotations

import numpy as np


def _diagnostics():
    """Return a two-detector diagnostics dict with a known background tail."""
    from chisurf.core.fluorescence.burst import interphoton_time_diagnostics

    rng = np.random.default_rng(0)

    def dt(rate):
        return np.concatenate(
            [
                rng.exponential(1 / rate, 20000),
                rng.exponential(1 / 200.0, 5000),
            ]
        )

    return {
        "m.ptu": {
            "green": interphoton_time_diagnostics(dt(2.0), tail_fraction=0.2),
            "red": interphoton_time_diagnostics(dt(3.5), tail_fraction=0.2),
        }
    }


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


def test_diagnostics_plots_build_and_render():
    """The native app takes the diagnostics and paints them headlessly; clearing drops the series."""
    from emtk.testing import RecordingPainter

    from chisurf.plugins.burst.burst_background.gui.app import create_app

    app = create_app()
    try:
        app.model.diagnostics = _diagnostics()
        app.model.notify()
        assert len(app.model.iht_series()) >= 4
        for _ in range(3):
            painter = RecordingPainter()
            app.draw(painter, 0, 0, 1200, 800)
        assert painter.strings, "nothing was drawn"

        app.model.clear()
        assert app.model.iht_series() == []
    finally:
        app.close()


def test_semantic_detector_colors():
    """Green and red detectors keep their meaning; anything else is stable."""
    from chisurf.plugins.burst.burst_background.view_model import det_color

    assert det_color("green") == (44, 160, 44)
    assert det_color("red") == (214, 39, 40)
    assert det_color("spot7") == det_color("spot7")
