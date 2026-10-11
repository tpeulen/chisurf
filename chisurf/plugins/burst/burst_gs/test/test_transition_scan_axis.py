"""The transition-time scan is drawn on a log time axis with the zero baseline inside the frame.

The scan is log-spaced from 1 µs to 1 ms. Drawn on a linear axis (ticks 100, 200, …
1000 µs) its whole flat region -- the part guide 49 says is the answer -- sat in the
first pixel, and the "instantaneous" baseline at exactly zero was the plot's top edge.
"""

from __future__ import annotations

import time

from emtk.testing import RecordingPainter

from chisurf.plugins.burst.burst_gs.gui.app import create_app

SIZE = (1200, 800)


def _draw(app):
    painter = RecordingPainter()
    app.draw(painter, 0, 0, *SIZE)
    return painter


def test_scan_axis_is_logarithmic_and_shows_the_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    app = create_app()
    try:
        m = app.model
        m.use_simulation = True
        m.sim_n_bursts, m.sim_photons_per_burst, m.max_iterations = 30, 60, 200
        m.scan_transition_time, m.transit_points = True, 7
        app.controller.run()
        end = time.monotonic() + 120
        while app.controller.running and time.monotonic() < end:
            time.sleep(0.02)
            _draw(app)
        assert not app.controller.running
        for _ in range(3):
            painter = _draw(app)
        strings = set(painter.strings)
        assert "Transition-time scan" in strings
        # decade ticks of a log axis, not the 100 µs steps of a linear one
        assert {"10", "100"} <= strings, sorted(strings)
        assert "500" not in strings and "700" not in strings
        low, high = app.gs_gui._transit_request
        assert high > 0.0 > low
    finally:
        app.close()


def test_the_reported_upper_bound_is_where_the_likelihood_breaks_not_the_first_point():
    """With no peak the report named the *best* point -- the shortest time scanned,
    1 µs -- as the bound, while the curve stayed within noise up to ~15 µs."""
    import numpy as np

    from chisurf.plugins.burst.burst_gs.core import GsAnalysis

    times = np.logspace(-6, -3, 7)  # 1, 3.2, 10, 32, 100, ... µs
    delta = np.array([0.0, -0.3, -1.5, -6.0, -40.0, -200.0, -800.0])
    analysis = GsAnalysis(fit=None, transit_times=times, transit_delta=delta)
    assert analysis.transit_upper_bound() == times[2]
    shuffled = GsAnalysis(fit=None, transit_times=times[::-1], transit_delta=delta[::-1])
    assert shuffled.transit_upper_bound() == times[2]
