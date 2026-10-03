"""The emtk H2MM windows draw what the fit computed, or say that there is none (PRD-153 rule 8a, card H-X).

The earlier app drew a hard-coded rate matrix, seeded ``np.random.normal`` transition clusters and invented
exponential dwell curves whenever there was no result, and read result fields (``rates``, dict-shaped
``transitions``) that the real ``H2mmAnalysis`` does not have, so even after a real fit it kept drawing the
inventions. These tests fail if a plotted array or a table cell does not come from the backend's analysis.

The fits here are **generated**: photons are simulated from a known two-state model (the same generator the
backend tests use) and fitted by the real ``analyze``; nothing is read from outside the repository.
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

from chisurf.plugins.burst.burst_h2mm.core import h2mm
from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze
from chisurf.plugins.burst.burst_h2mm.gui import result_view
from chisurf.plugins.burst.burst_h2mm.gui.app import H2mmApp

SIZES = [(1200, 800), (800, 600)]
GUI = Path(__file__).parents[1] / "gui"


def generated_fit(seed: int, trans=((0.99, 0.01), (0.02, 0.98)), obs=((0.85, 0.15), (0.20, 0.80)), states=(1, 2)):
    """A fit of GENERATED photons: a two-state model simulates the bursts, ``analyze`` fits them. Returns ``(analysis, data)``."""
    truth = h2mm.H2mmModel(np.array([0.5, 0.5]), np.array(trans), np.array(obs))
    rng = np.random.default_rng(seed)
    times = [np.concatenate([[0], np.cumsum(rng.poisson(4, 59) + 1)]).astype(np.int64) for _ in range(80)]
    data = h2mm.prepare_bursts(times, h2mm.simulate_bursts(truth, times, seed=seed + 1), 2)
    return analyze(data, state_counts=states, n_restarts=1, max_iter=100), data


def generated_analysis(seed: int, **kwargs):
    return generated_fit(seed, **kwargs)[0]


@pytest.fixture(scope="module")
def ana():
    return generated_analysis(2)


@pytest.fixture(scope="module")
def other_ana():
    return generated_analysis(7, trans=((0.95, 0.05), (0.10, 0.90)), obs=((0.95, 0.05), (0.10, 0.90)))


class PlotSpy:
    """Records every ``implot.plot_*`` call (name, label, the numpy arrays it was given)."""

    def __init__(self, monkeypatch) -> None:
        self.calls: list[tuple[str, str, list[np.ndarray]]] = []
        for name in [n for n in dir(implot) if n.startswith("plot_") and "pixels" not in n]:
            original = getattr(implot, name)
            monkeypatch.setattr(implot, name, self._wrap(name, original))

    def _wrap(self, name, original):
        def spy(*args, **kwargs):
            label = args[0] if args and isinstance(args[0], str) else ""
            arrays = [np.asarray(a, dtype=float) for a in list(args) + list(kwargs.values()) if _is_array(a)]
            self.calls.append((name, label, arrays))
            return original(*args, **kwargs)

        return spy

    def clear(self):
        self.calls.clear()


def _is_array(value) -> bool:
    return isinstance(value, (np.ndarray, list, tuple)) and len(value) > 0 and not isinstance(value[0], str)


def hold(tool, ana):
    """Give *tool* what a finished fit leaves on ``H2mmTool``: the summary ``_result`` and the ``_bundle`` with the analysis."""
    from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings, StreamSettings
    from chisurf.plugins.burst.burst_h2mm.backend.services import H2mmAnalysisBundle, _result_from_analysis

    if ana is None:
        tool._result, tool._bundle = None, None
    else:
        settings = H2mmSettings(streams=[StreamSettings("donor", [0]), StreamSettings("acceptor", [1])])
        tool._result = _result_from_analysis(ana, settings)
        tool._bundle = H2mmAnalysisBundle(ana, None, settings)
    return tool


def stub_tool(ana):
    return hold(SimpleNamespace(_result=None, _bundle=None, data_folder=None, _fit_task=None), ana)


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


@pytest.mark.parametrize("size", SIZES)
def test_without_a_fit_nothing_is_plotted_and_every_window_says_so(monkeypatch, size):
    spy = PlotSpy(monkeypatch)
    painter = draw(H2mmApp(stub_tool(None)), size, spy=spy)
    assert spy.calls == [], f"a plot call drew data with no fit: {[c[:2] for c in spy.calls]}"
    shown = " ".join(texts(painter))
    assert "No H2MM fit yet" in shown
    assert "No transition rates yet" in shown
    assert "No transition density yet" in shown
    assert "No dwell times yet" in shown
    # No matrix, no demo label, no invented state names in the rate window.
    assert "Demo" not in shown and "S0 → S1" not in shown and "τ=" not in shown
    assert "rate_mat_table" not in shown and "State S0" not in shown


@pytest.mark.parametrize("size", SIZES)
def test_after_a_fit_the_plots_hold_exactly_the_analysis(monkeypatch, ana, size):
    spy = PlotSpy(monkeypatch)
    painter = draw(H2mmApp(stub_tool(ana)), size, spy=spy)

    # TDP: one scatter, the finite (E before, E after) of the decoded transitions, in decoding order.
    scatters = [c for c in spy.calls if c[0] == "plot_scatter"]
    assert len(scatters) == 1
    before = np.array([t.e_from for t in ana.transitions])
    after = np.array([t.e_to for t in ana.transitions])
    good = np.isfinite(before) & np.isfinite(after)
    assert good.sum() > 0
    np.testing.assert_array_equal(scatters[0][2][0], before[good])
    np.testing.assert_array_equal(scatters[0][2][1], after[good])

    # Dwell window: one line per state with complete dwells, the 30-bin histogram of its dwells in ms.
    lines = [c for c in spy.calls if c[0] == "plot_line"]
    arrays = ana.dwell_time_arrays()
    expected = [s for s, a in sorted(arrays.items()) if a.size]
    assert [c[1] for c in lines] == [f"S{s}" for s in expected]
    for call, state in zip(lines, expected):
        counts, edges = np.histogram(arrays[state] * ana.base_time_s * 1e3, bins=30)
        np.testing.assert_array_equal(call[2][1], counts)
        np.testing.assert_allclose(call[2][0], (edges[:-1] + edges[1:]) / 2)

    # Nothing else is plotted: no reference line, no invented series.
    assert len(spy.calls) == len(scatters) + len(lines)

    # The rate table's cells are the analysis' matrix.
    shown = texts(painter)
    rates = np.asarray(ana.trans_rates)
    for i in range(rates.shape[0]):
        for j in range(rates.shape[0]):
            if i != j:
                assert f"{rates[i, j]:.1f}" in shown
    assert f"Best model: {ana.best.n_states} states ({ana.n_bursts} bursts, {ana.n_photons} photons)" in shown
    assert "No H2MM fit yet" not in " ".join(shown)


def test_a_different_fit_gives_different_plots(monkeypatch, ana, other_ana):
    """The plotted arrays follow the analysis the tool holds: swap it and they change."""
    spy = PlotSpy(monkeypatch)
    tool = stub_tool(ana)
    app = H2mmApp(tool)
    draw(app, spy=spy)
    first = [(c[0], c[1], [a.copy() for a in c[2]]) for c in spy.calls]
    hold(tool, other_ana)
    painter = draw(app, spy=spy)
    second = spy.calls
    assert first and second
    differs = len(first) != len(second) or any(
        a[1] != b[1] or len(a[2]) != len(b[2]) or any(x.shape != y.shape or not np.array_equal(x, y) for x, y in zip(a[2], b[2]))
        for a, b in zip(first, second)
    )
    assert differs, "two different fits drew the same plots"
    rates = np.asarray(other_ana.trans_rates)
    assert f"{rates[0, 1]:.1f}" in texts(painter)


def test_the_fit_is_dropped_again_the_windows_return_to_the_empty_state(monkeypatch, ana):
    spy = PlotSpy(monkeypatch)
    tool = stub_tool(ana)
    app = H2mmApp(tool)
    draw(app, spy=spy)
    assert spy.calls
    hold(tool, None)
    painter = draw(app, spy=spy)
    assert spy.calls == []
    assert "No transition rates yet" in " ".join(texts(painter))


def test_the_gate_count_is_computed_from_the_transitions(ana):
    points = result_view.transition_points(ana)
    assert points is not None
    everything = result_view.transitions_in_gate(points, (0.0, 1.0), (0.0, 1.0))
    assert everything == (points[0].size, points[0].size)
    nothing = result_view.transitions_in_gate(points, (2.0, 3.0), (2.0, 3.0))
    assert nothing == (0, points[0].size)
    assert result_view.transitions_in_gate(None, (0, 1), (0, 1)) == (0, 0)


def test_the_result_view_returns_nothing_without_an_analysis():
    assert result_view.n_states(None) is None
    assert result_view.rate_matrix(None) is None
    assert result_view.transition_points(None) is None
    assert result_view.dwell_histograms(None) == ([], [])


def test_the_app_source_cannot_make_data_up():
    """Static guard: no numpy / random import in the app, no numeric literal fed to a plot call."""
    tree = ast.parse((GUI / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & {"numpy", "random"}, "the app imports numpy/random"
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in {"numpy", "random"}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.startswith("plot_"):
            for arg in node.args[1:]:
                assert not isinstance(arg, (ast.List, ast.Tuple, ast.Constant)), f"literal data in {node.func.attr}"


@pytest.fixture(scope="module")
def qapp():
    from qtpy.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


class TestAgainstTheRealTool:
    """The controls are views on the tool's own widgets, so what is typed is what ``_gather_settings`` fits with."""

    @pytest.fixture
    def tool(self, qapp):
        from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

        tool = H2mmTool(embedded=True)
        yield tool
        tool.close()

    def test_the_controls_show_the_tools_settings_not_their_own_defaults(self, tool):
        tool.sb_restarts.setValue(7)
        tool.sb_max_iter.setValue(1234)
        tool.sb_min_photons.setValue(9)
        tool.sb_min_states.setValue(2)
        tool.sb_max_states.setValue(5)
        app = H2mmApp(tool)
        shown = texts(draw(app))
        for value in ("7", "1234", "9", "2", "5"):
            assert value in shown, f"{value} of the tool's settings is not drawn: {shown}"

    def test_a_change_made_in_the_app_reaches_the_tool_settings(self, tool):
        app = H2mmApp(tool)
        draw(app)
        gui = app.h2mm_gui
        gui.restarts, gui.max_iter, gui.min_photons, gui.min_states, gui.max_states = 6, 321, 8, 2, 4
        gui.criterion, gui.engine = "icl", "em"
        gui._sync_to_tool()
        settings = tool._gather_settings()
        assert (settings.n_restarts, settings.max_iter, settings.min_photons) == (6, 321, 8)
        assert (settings.min_states, settings.max_states, settings.criterion, settings.engine) == (2, 4, "icl", "em")

    def test_a_result_the_tool_holds_is_drawn(self, tool, monkeypatch, ana):
        spy = PlotSpy(monkeypatch)
        hold(tool, ana)
        app = H2mmApp(tool)
        painter = draw(app, spy=spy)
        assert any(c[0] == "plot_scatter" for c in spy.calls)
        assert f"{np.asarray(ana.trans_rates)[0, 1]:.1f}" in texts(painter)


def test_a_fit_run_through_the_tool_is_what_the_app_draws(qapp, tmp_path, monkeypatch):
    """Run the real tool (its worker, ``_on_fit_result``, the bundle) and compare the app with the analysis it produced."""
    import time

    from chisurf.plugins.burst.burst_h2mm.backend.services import H2mmAnalysisBundle, _result_from_analysis
    from chisurf.plugins.burst.burst_h2mm.gui import tool as tool_mod

    produced = {}

    def run_analysis(settings, analysis_folder=None, progress=None, **_):
        ana, data = generated_fit(5)
        produced["ana"] = ana
        return _result_from_analysis(ana, settings), H2mmAnalysisBundle(ana, data, settings)

    monkeypatch.setattr(tool_mod, "run_analysis", run_analysis)
    tool = tool_mod.H2mmTool(embedded=True)
    try:
        tool.data_folder = tmp_path
        app = H2mmApp(tool)
        assert "No H2MM fit yet" in " ".join(texts(draw(app)))
        tool._run_analysis()
        deadline = time.time() + 60
        while tool._result is None and time.time() < deadline:
            qapp.processEvents()
            time.sleep(0.02)
        assert tool._result is not None
        spy = PlotSpy(monkeypatch)
        painter = draw(app, spy=spy)
        ana = produced["ana"]
        assert f"{np.asarray(ana.trans_rates)[0, 1]:.1f}" in texts(painter)
        points = result_view.transition_points(ana)
        np.testing.assert_array_equal(spy.named("Transitions")[2][0], points[0])
    finally:
        tool.close()


def test_help_and_guide_resources_exist_and_the_tour_walks():
    assert (GUI / "help.md").is_file()
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    app = H2mmApp(stub_tool(None))
    gui = app.h2mm_gui
    gui.start_guide()
    seen = 0
    while gui.tour.active:
        draw(app)
        gui.tour.next()
        seen += 1
        assert seen <= len(steps) + 1
    assert seen == len(steps)


def _named(self, label):
    found = [c for c in self.calls if c[1] == label]
    assert len(found) == 1, f"{label!r} drawn {len(found)} times: {[c[:2] for c in self.calls]}"
    return found[0]


PlotSpy.named = _named
