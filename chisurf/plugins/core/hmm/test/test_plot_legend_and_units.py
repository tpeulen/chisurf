"""The HMM plots: one legend entry per series, and time axes that name their unit.

The dwell-time and scan plots drew their markers as a second item labelled ``name##pts``, which the
legend lists under the same name in the next palette colour -- every state appeared twice. The
trace and dwell-time axes read "time" / "dwell time" with no unit although the bin width is set in
seconds (guide 54 figure, 2026-10-11 walk).
"""

from __future__ import annotations

import numpy as np

from ..gui import app as app_module
from ..gui.app import HmmApp


class _RecordingPlot:
    """Stands in for ``emtk.implot``: records what the plot was asked to draw."""

    AXIS_Y1 = SCALE_LOG10 = LOCATION_NORTH_EAST = 0

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return True if name == "begin_plot" else None

        return record


def _draw(monkeypatch, app, method):
    fake = _RecordingPlot()
    monkeypatch.setattr(app_module, "implot", fake)
    getattr(app, method)(None)
    return fake.calls


def _fitted_app():
    rng = np.random.default_rng(0)
    states = np.repeat(rng.integers(0, 2, 60), 20)
    trace = np.where(states, 55.0, 18.0)[:, None] + rng.normal(0, 3, (len(states), 1))
    app = HmmApp()
    app.set_traces([trace])
    app.model.time_step = 1e-3
    app.model.n_states = 2
    app.model.run()
    app.model.min_states, app.model.max_states = 1, 3
    app.model.run_scan()
    return app


def test_markers_of_a_series_are_not_a_second_legend_entry(monkeypatch):
    app = _fitted_app()
    for method in ("dwell_plot", "scan_plot"):
        calls = _draw(monkeypatch, app, method)
        shown = [args[0].split("##", 1)[0] for name, args, _ in calls if name in ("plot_line", "plot_scatter")]
        shown = [label for label in shown if label]
        assert shown and len(shown) == len(set(shown)), (method, shown)


def test_time_axes_name_seconds_once_a_bin_width_is_set(monkeypatch):
    app = _fitted_app()
    axes = {
        method: next(args for name, args, _ in _draw(monkeypatch, app, method) if name == "setup_axes")
        for method in ("trace_plot", "dwell_plot")
    }
    assert axes["trace_plot"][0] == "time (s)"
    assert axes["dwell_plot"][0] == "dwell time (s)"
    app.model.time_step = 1.0
    assert next(a for n, a, _ in _draw(monkeypatch, app, "trace_plot") if n == "setup_axes")[0] == "bin"
