"""The emtk burst-MLE windows draw what the engine computed, or say that there is none (no invented data, card ML-X).

The earlier app drew a Gaussian "IRF" and an exponential "decay" built with ``np.exp`` for any data and a lifetime
histogram from its own ``tau1`` / ``tau2`` fields, and read wizard attributes (``irf_background_patterns``,
``burst_files``) that do not exist. These tests fail if a plotted array or a table cell does not come from the
engine's fit. (The app over the retired Qt wizard is gone; its tests of the drawn curves against the wizard are in
``test_emtk_mle_native.py`` against the engine, and ``test_mle_engine.py`` holds the engine against the numbers the
wizard recorded in ``qt_reference.json``.)

Also holds the plot spy and the draw helpers the other emtk tests of this plugin use.
"""

import ast
from pathlib import Path

import numpy as np
import pytest
from emtk import implot
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.burst_mle_analysis import fit_display
from chisurf.plugins.burst.burst_mle_analysis.gui import fit_view

SIZES = [(1200, 800), (800, 600)]
GUI = Path(__file__).parents[1] / "gui"


class PlotSpy:
    """Records every drawing ``implot.plot_*`` call (name, label, the numpy arrays it was given)."""

    def __init__(self, monkeypatch) -> None:
        self.calls: list[tuple[str, str, list[np.ndarray]]] = []
        for name in [n for n in dir(implot) if n.startswith("plot_") and "pixels" not in n]:
            monkeypatch.setattr(implot, name, self._wrap(name, getattr(implot, name)))

    def _wrap(self, name, original):
        def spy(*args, **kwargs):
            label = args[0] if args and isinstance(args[0], str) else ""
            arrays = [
                np.asarray(a, dtype=float)
                for a in list(args) + list(kwargs.values())
                if _is_array(a)
            ]
            self.calls.append((name, label, arrays))
            return original(*args, **kwargs)

        return spy

    def clear(self):
        self.calls.clear()

    def named(self, label):
        found = [c for c in self.calls if c[1] == label]
        assert len(found) == 1, f"{label!r} drawn {len(found)} times: {[c[:2] for c in self.calls]}"
        return found[0]


def _is_array(value) -> bool:
    return (
        isinstance(value, (np.ndarray, list, tuple))
        and len(value) > 0
        and not isinstance(value[0], str)
    )


def draw(app, size=(1200, 800), frames=2, spy=None):
    """Draw *frames* frames; the spy keeps only the calls of the last one."""
    painter = None
    for i in range(frames):
        if spy is not None and i == frames - 1:
            spy.clear()
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def texts(painter):
    return [t[5] for t in painter.texts]


# ------------------------------------------------------------------------------------------------------------------
# The parameter table and the pure computations
# ------------------------------------------------------------------------------------------------------------------
def test_the_parameter_table_is_the_models_not_a_copy(hermetic_env):
    """Start values shown are the model's (tau 4.0, gamma/r0/rho 0.1/0.38/1.22), not the old 3.8/1.2/0.8 of the app."""
    import time

    from chisurf.core.registry import catalog
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app
    from chisurf.plugins.emtk_test_input import Driver

    app = create_app()
    try:
        deadline = time.monotonic() + 60
        while not catalog.prefetch() and time.monotonic() < deadline:
            time.sleep(0.05)
        records = app.model.parameter_records()
        assert [r["name"] for r in records] == ["tau", "gamma", "r0", "rho"]
        assert records[0]["start"] == app.model.tau == 4.0
        shown = texts(Driver(app).draw(3))
        for record in records:
            assert record["name"] in shown
        assert "3.8" not in shown and "0.8" not in shown
    finally:
        app.close()


def test_burst_lifetimes_reads_the_columns_of_the_rows_and_nothing_else():
    rows = [
        {
            "Tau (green)": 2.0,
            "Tau S0 (green)": 1.0,
            "Number of Photons (fit window) (green)": 99,
            "First File": "a",
        },
        {"Tau (green)": float("nan"), "Tau S0 (green)": 1.5, "Tau (red)": 3.0},
        {"Tau (green)": 2.5},
    ]
    got = fit_view.burst_lifetimes(rows)
    assert sorted(got) == ["S0 green", "green", "red"]
    np.testing.assert_array_equal(got["green"], [2.0, 2.5])
    np.testing.assert_array_equal(got["S0 green"], [1.0, 1.5])
    assert fit_view.burst_lifetimes(None) == {} and fit_view.burst_lifetimes([]) == {}
    assert fit_view.lifetime_histograms({}) == []


# ------------------------------------------------------------------------------------------------------------------
# fit_display (the computation the engine and the app share) and the defect found on the way
# ------------------------------------------------------------------------------------------------------------------
def test_decay_curves_windows_each_polarisation_and_drops_the_irf_for_a_tail_fit():
    n = 8
    data = np.arange(2 * n, dtype=float) + 1.0
    model = data * 0.9
    irf = np.ones(2 * n)
    bg = np.full(2 * n, 2.0)
    ranges = (2, 6, 1, 4)
    curves = fit_display.decay_curves(data, model, irf, bg, ranges)
    np.testing.assert_array_equal(curves.data, np.hstack([data[2:6], data[n + 1 : n + 4]]))
    assert (
        curves.n_vv == 4
        and curves.irf is not None
        and curves.irf.sum() == pytest.approx(curves.data.sum())
    )
    np.testing.assert_allclose(
        curves.residuals, (curves.data - curves.model) / np.sqrt(curves.data)
    )
    assert fit_display.decay_curves(data, model, irf, bg, ranges, tail=True).irf is None
    runaway = fit_display.decay_curves(data, model * 1e6, irf, bg, ranges, diverged=True)
    assert runaway.model.max() <= curves.data.max() * 10.0


def test_a_tail_fit_result_is_read_by_attribute():
    """The tail fit's result is a ``TailFitResult`` read by attribute; the old mapping raised on ``res.x``."""
    result = fit_display.TailFitResult(x=[10.0, 2.0, 0.5], twoIstar=1.2)
    assert list(result.x) == [10.0, 2.0, 0.5] and result.twoIstar == 1.2


# ------------------------------------------------------------------------------------------------------------------
# Static guard
# ------------------------------------------------------------------------------------------------------------------
def test_the_app_source_cannot_make_data_up():
    """No random import in the app and no literal array handed to a plot call."""
    tree = ast.parse((GUI / "native.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert "random" not in {a.name.split(".")[0] for a in node.names}, "the app imports random"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] != "random"
        if isinstance(node, ast.Attribute) and node.attr == "random":
            raise AssertionError("the app draws from a random generator")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr.startswith("plot_")
        ):
            for arg in node.args[1:]:
                assert not isinstance(arg, (ast.List, ast.Tuple, ast.Constant)), (
                    f"literal data in {node.func.attr}"
                )


def test_help_and_guide_exist():
    import json

    assert (GUI / "help.md").read_text(encoding="utf-8").startswith("# ")
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    assert any(s.get("await") for s in steps), (
        "the guide never waits for the user to press a control"
    )
