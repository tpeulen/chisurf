"""The emtk burst-MLE windows draw what the wizard computed, or say that there is none (no invented data, card ML-X).

The earlier app drew a Gaussian "IRF" and an exponential "decay" built with ``np.exp`` for any data and a lifetime
histogram from its own ``tau1`` / ``tau2`` fields, and read wizard attributes (``irf_background_patterns``,
``burst_files``) that do not exist. These tests fail if a plotted array or a table cell does not come from the
wizard's fit.

Input: the in-repository BH SPC-132 smFRET DNA sample (real photons; ``conftest.py`` copies it to a temp folder),
fitted by the wizard's own ``auto_extract_irf_bg`` and ``process_bursts``. Nothing is generated and nothing is read
from outside the repository.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from emtk import implot
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.burst_mle_analysis import fit_display
from chisurf.plugins.burst.burst_mle_analysis.gui import fit_view
from chisurf.plugins.burst.burst_mle_analysis.gui.app import BurstMleApp
from chisurf.plugins.emtk_test_input import Driver

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
# No fit: nothing is plotted
# ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("size", SIZES)
def test_without_a_fit_nothing_is_plotted_and_every_window_says_so(monkeypatch, fresh_wizard, size):
    assert fresh_wizard.fit_curves is None
    spy = PlotSpy(monkeypatch)
    painter = draw(BurstMleApp(fresh_wizard), size, spy=spy)
    assert spy.calls == [], f"a plot call drew data with no fit: {[c[:2] for c in spy.calls]}"
    shown = " ".join(texts(painter))
    assert "No fit yet" in shown
    assert "No burst lifetimes yet" in shown
    assert "Pooled state lifetimes exist only" in shown
    assert "Decay Data" not in shown and "IRF Pattern" not in shown
    # The status comes from the wizard: no burst file, no IRF/background loaded.
    assert "Burst files: 0" in shown
    assert "No IRF and background for the current detector yet" in shown


def test_the_parameter_table_is_the_wizards_not_a_copy(fresh_wizard):
    """Start values shown are the wizard's (tau 4.0, gamma/r0/rho 0.1/0.38/1.22), not the old 3.8/1.2/0.8 of the app."""
    wiz = fresh_wizard
    shown = texts(draw(BurstMleApp(wiz)))
    for row in fit_view.parameter_rows(wiz):
        assert row.name in shown
        assert f"{row.initial:.4g}" in shown
    assert fit_view.parameter_rows(wiz)[0].initial == wiz.tau
    assert "3.8" not in shown and "0.8" not in shown


# ------------------------------------------------------------------------------------------------------------------
# After the real fit
# ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("size", SIZES)
def test_after_a_fit_the_decay_window_holds_exactly_the_wizards_curves(
    monkeypatch, fitted_green, size
):
    wiz = fitted_green
    spy = PlotSpy(monkeypatch)
    draw(BurstMleApp(wiz), size, spy=spy)

    # Independent of fit_display: window the wizard's recorded view the way plot_fit_result does.
    view = wiz._fit_view
    n = len(view.data) // 2
    vv_sb, vv_eb, vh_sb, vh_eb = wiz._get_channel_ranges_bins()
    data = np.hstack(
        [
            np.asarray(view.data, float)[0:n][vv_sb:vv_eb],
            np.asarray(view.data, float)[n : 2 * n][vh_sb:vh_eb],
        ]
    )
    model = np.hstack(
        [
            np.asarray(view.model, float)[0:n][vv_sb:vv_eb],
            np.asarray(view.model, float)[n : 2 * n][vh_sb:vh_eb],
        ]
    )

    _, _, (x, y) = spy.named("Data (VV|VH)")
    np.testing.assert_array_equal(y, data)
    np.testing.assert_array_equal(x, np.arange(data.size))
    np.testing.assert_allclose(spy.named("Model (fit)")[2][1], model)
    assert data.sum() > 1000 and model.sum() > 0

    # And the same numbers the Qt plot shows: the chiplot series the wizard drew.
    qt = {name: handle.get_data()[1] for name, handle in wiz.combined_plot.series()}
    for label in ("Data (VV|VH)", "Model (fit)", "IRF", "Background"):
        np.testing.assert_allclose(spy.named(label)[2][1], np.asarray(qt[label], float))

    # Nothing else is plotted (no invented IRF peak, no second series).
    assert sorted(c[1] for c in spy.calls) == ["Background", "Data (VV|VH)", "IRF", "Model (fit)"]


def test_the_curves_follow_the_wizard_when_the_detector_changes(monkeypatch, fitted_green):
    """Fit red instead of green: the plotted arrays change with the wizard's fit."""
    from qtpy import QtWidgets

    wiz = fitted_green
    spy = PlotSpy(monkeypatch)
    app = BurstMleApp(wiz)
    draw(app, spy=spy)
    green = spy.named("Data (VV|VH)")[2][1].copy()
    try:
        wiz.comboBox_window.setCurrentText("red")
        wiz.auto_extract_irf_bg()
        QtWidgets.QApplication.processEvents()
        draw(app, spy=spy)
        red = spy.named("Data (VV|VH)")[2][1]
        assert red.shape != green.shape or not np.array_equal(red, green)
        np.testing.assert_array_equal(red, wiz.fit_curves.data)
    finally:
        wiz.comboBox_window.setCurrentText("green")
        wiz.auto_extract_irf_bg()
        QtWidgets.QApplication.processEvents()


def test_the_fit_parameter_table_shows_the_fitted_values(fitted_green):
    wiz = fitted_green
    shown = texts(draw(BurstMleApp(wiz)))
    rows = fit_view.parameter_rows(wiz)
    assert rows[0].name == "tau" and rows[0].result == wiz.tau_result
    assert 0.5 < rows[0].result < 5.0
    assert f"{rows[0].result:.4g}" in shown
    assert "IRF and background loaded for green" in shown


# ------------------------------------------------------------------------------------------------------------------
# The controls work on the wizard (real input) and the batch fills the lifetime window
# ------------------------------------------------------------------------------------------------------------------
def test_typing_the_fit_window_changes_the_wizard_and_the_plotted_curves(fitted_green):
    wiz = fitted_green
    app = BurstMleApp(wiz)
    drv = Driver(app)
    drv.draw()
    start, stop = wiz.micro_time_range
    n_before = wiz.fit_curves.data.size
    new_stop = stop - 20
    drv.type_into_name("micro_time_stop", str(new_stop))
    assert wiz.micro_time_stop == new_stop
    assert wiz.fit_curves.data.size < n_before, "the refit did not use the shorter window"
    # restore
    drv.type_into_name("micro_time_stop", str(stop))
    assert wiz.micro_time_range == [start, stop]


def test_typing_tau_start_writes_the_wizard(fitted_green):
    wiz = fitted_green
    drv = Driver(BurstMleApp(wiz))
    old = wiz.tau
    drv.type_into_name("tau", "2.5")
    assert wiz.tau == pytest.approx(2.5)
    drv.type_into_name("tau", f"{old}")


def test_refit_button_refits_the_current_decay(fitted_green):
    wiz = fitted_green
    drv = Driver(BurstMleApp(wiz))
    drv.draw()
    before = wiz.fit_curves
    drv.click_name("toolAction_restart")
    assert wiz.fit_curves is not None and wiz.fit_curves is not before, "Refit did not refit"
    np.testing.assert_allclose(wiz.fit_curves.data, before.data)


@pytest.fixture(scope="module")
def batch_run(fitted_green):
    """Press Fit Bursts with the pointer: the real multi-process batch over the sample's bursts."""
    wiz = fitted_green
    app = BurstMleApp(wiz)
    drv = Driver(app)
    drv.draw()
    drv.click_name("toolAction_run")
    return wiz, app


def test_fit_bursts_click_fills_the_lifetime_histogram_from_the_batch_rows(monkeypatch, batch_run):
    wiz, app = batch_run
    assert wiz.burst_results, "the batch produced no rows"
    lifetimes = fit_view.burst_lifetimes(wiz.burst_results)
    assert "green" in lifetimes and lifetimes["green"].size > 5
    assert 0.1 < float(np.median(lifetimes["green"])) < 10.0

    spy = PlotSpy(monkeypatch)
    draw(app, spy=spy)
    bars = [c for c in spy.calls if c[0] == "plot_bars"]
    assert [c[1] for c in bars] == sorted(lifetimes)
    everything = np.concatenate(list(lifetimes.values()))
    edges = np.linspace(everything.min(), everything.max(), fit_view.LIFETIME_BINS + 1)
    for call in bars:
        counts, _ = np.histogram(lifetimes[call[1]], bins=edges)
        np.testing.assert_array_equal(call[2][1], counts)
    # The histogram is of the wizard's rows: every counted burst is one of them.
    assert sum(float(c[2][1].sum()) for c in bars) == sum(v.size for v in lifetimes.values())
    shown = " ".join(texts(draw(app)))
    assert f"{everything.size} of {everything.size} lifetimes inside the gate" in shown


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
# fit_display (the computation both front ends share) and the two defects found on the way
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


def test_the_wizard_flags_a_diverged_fit_from_a_result_object_and_from_a_mapping(fresh_wizard):
    """``_fit_diverged`` read the quality with ``.get``: a ``Fit2xResult`` has none, so nothing was ever flagged."""
    diverged = fresh_wizard._fit_diverged
    assert diverged(SimpleNamespace(twoIstar=-1.0)) is not None
    assert diverged(fit_display.TailFitResult(x=[1.0], twoIstar=-1.0)) is not None
    assert diverged({"twoIstar": -1.0}) is not None
    assert diverged(SimpleNamespace(twoIstar=1.1)) is None
    assert diverged({"twoIstar": 1.1}) is None


def test_the_tail_fit_result_reaches_the_panel(fitted_green):
    """The tail fit's result is read by attribute; ``update_fit_ui`` raised on ``res.x`` of the old mapping."""
    wiz = fitted_green
    wiz.comboBox_fit_model.setCurrentIndex(wiz.comboBox_fit_model.findData("tail"))
    try:
        wiz.update_fit_ui(fit_display.TailFitResult(x=[10.0, 2.0, 0.5], twoIstar=1.2))
        rows = wiz._dyn_params
        assert rows.results[:3] == [10.0, 2.0, 0.5]
    finally:
        wiz.comboBox_fit_model.setCurrentIndex(wiz.comboBox_fit_model.findData("fit23"))


# ------------------------------------------------------------------------------------------------------------------
# Static guard, help and guide
# ------------------------------------------------------------------------------------------------------------------
def test_the_app_source_cannot_make_data_up():
    """No numpy / random import in the app and no literal array handed to a plot call."""
    tree = ast.parse((GUI / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & {"numpy", "random"}, (
                "the app imports numpy/random"
            )
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in {"numpy", "random"}
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr.startswith("plot_")
        ):
            for arg in node.args[1:]:
                assert not isinstance(arg, (ast.List, ast.Tuple, ast.Constant)), (
                    f"literal data in {node.func.attr}"
                )


def test_help_and_guide_exist_and_every_target_is_a_drawn_control(fresh_wizard):
    assert (GUI / "help.md").read_text(encoding="utf-8").startswith("# ")
    steps = json.loads((GUI / "guide_wizard.json").read_text(encoding="utf-8"))["steps"]
    app = BurstMleApp(fresh_wizard)
    draw(app)
    for step in steps:
        target = step.get("target")
        if target:
            key = app.mle_gui.tour._target_key(target)
            assert key in app.item_rects, (
                f"guide step {step['title']!r}: {key!r} is not a drawn control"
            )
    assert any(s.get("await") for s in steps), (
        "the guide never waits for the user to press a control"
    )


def test_the_fit_step_waits_for_the_real_press_of_fit_bursts(monkeypatch, fresh_wizard):
    wiz = fresh_wizard
    calls = []
    monkeypatch.setattr(
        wiz, "process_bursts", lambda *a, **k: calls.append(1)
    )  # the press is real; the 10 s batch is not the point
    app = BurstMleApp(wiz)
    drv = Driver(app)
    tour = app.mle_gui.tour
    app.mle_gui.start_guide()
    while tour.step_idx < next(i for i, s in enumerate(tour.steps) if s.get("await")):
        tour.next()
    drv.draw()
    assert tour.awaiting
    drv.click_name("toolAction_run")
    assert calls == [1] and not tour.awaiting
