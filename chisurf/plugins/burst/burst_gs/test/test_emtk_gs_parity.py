"""The native photon-by-photon kinetics tool at parity with the Qt BurstGsTool.

Both hosts draw the same ``BurstGsApp``; the Qt tool fits through ChiSurfProgress
and reports in its status bar, the emtk app fits on the controller's worker. The Qt
tool runs in a subprocess on the tool's own simulation (known rates; this process
stays Qt-free) and the fits are compared.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory, qt_free  # noqa: E402

from emtk.testing import PixelPainter, RecordingPainter  # noqa: E402

from chisurf.plugins.burst.burst_gs.gui.app import create_app  # noqa: E402


def _app(simulate=True, **settings):
    app = create_app()
    app.model.use_simulation = simulate
    for key, value in settings.items():
        setattr(app.model, key, value)
    return app


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=120.0):
    end = time.monotonic() + timeout
    while app.controller.running:
        assert time.monotonic() < end, "the fit did not finish"
        time.sleep(0.05)
        _draw(app, n=1)
    _draw(app, n=1)


_QT = r"""
import json
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.burst.burst_gs.gui.tool import BurstGsTool
w = BurstGsTool()
w.model.use_simulation = True
w._fitted(bool(w.model.compute()))
fit = w.model.analysis.fit
print("FACTS" + json.dumps({"matrix": fit.rate_matrix.tolist(), "logL": fit.log_likelihood,
                            "status": w.statusBar().currentMessage(), "report": w.model.results_text}))
"""


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT], capture_output=True, text=True, timeout=600, env=env,
                          cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt tool's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS"):])


# 1. the Qt tool's fit, status line and report; the simulated rates come back
def test_a_fit_gives_the_qt_tools_rates_status_and_report(qt):
    app = _app()
    try:
        app.controller.run()
        _settle(app)
        fit = app.model.analysis.fit
        assert np.asarray(fit.rate_matrix) == pytest.approx(np.asarray(qt["matrix"]))
        assert fit.log_likelihood == pytest.approx(qt["logL"])
        assert app.controller.status == qt["status"]
        assert app.model.results_text == qt["report"]
        k12, k21 = fit.rate_matrix[1, 0], fit.rate_matrix[0, 1]
        assert k12 == pytest.approx(app.model.sim_k_forward, rel=0.15)
        assert k21 == pytest.approx(app.model.sim_k_backward, rel=0.15)
    finally:
        app.close()


# 4. the rates plot names its transitions and shows the simulated truth
def test_the_rates_plot_names_each_transition_and_the_truth(monkeypatch):
    from emtk import implot

    ticks, scatters = [], []
    tik, sca = implot.setup_axis_ticks, implot.plot_scatter
    monkeypatch.setattr(implot, "setup_axis_ticks",
                        lambda axis, values, n_ticks=None, labels=None, *a, **k: (ticks.append(labels), tik(axis, values, n_ticks, labels, *a, **k))[1])
    monkeypatch.setattr(implot, "plot_scatter", lambda name, x, y, *a, **k: (scatters.append((name, list(y))), sca(name, x, y, *a, **k))[1])
    app = _app()
    try:
        app.controller.run()
        _settle(app)
        labels, rates, truth = app.gs_gui.rate_bars()
        assert labels == ["k(1→2)", "k(2→1)"]
        assert rates == pytest.approx([app.model.analysis.fit.rate_matrix[1, 0], app.model.analysis.fit.rate_matrix[0, 1]])
        ticks.clear(), scatters.clear()
        strings = _draw(app, n=1).strings
        assert labels in ticks and ("simulated", [3000.0, 1000.0]) in scatters
        assert "rate (1/s)" in strings and "Parameter / Time" not in strings
        from emtk import implot_internal as I  # the drawn axis holds the simulated 3000 with room

        seen = {}
        end = implot.end_plot

        def record():
            plot = I.gp.current_plot
            if plot is not None:
                seen[plot.title] = (plot.axes[I.AXIS_Y1].range_min, plot.axes[I.AXIS_Y1].range_max)
            return end()

        monkeypatch.setattr(implot, "end_plot", record)
        _draw(app, n=2)
        assert seen["Fitted rates"][1] > 1.05 * 3000.0
    finally:
        app.close()


# 2. actions, progress and errors
def test_progress_is_shown_and_frames_requested_while_fitting(monkeypatch):
    import threading

    from chisurf.plugins.burst.burst_gs.gui import view_model

    gate = threading.Event()
    original = view_model.BurstGsViewModel.compute

    def compute(self, progress=None):
        progress(0.4, "Optimising rates…")
        assert gate.wait(10)
        return original(self, progress=progress)

    monkeypatch.setattr(view_model.BurstGsViewModel, "compute", compute)
    app = _app()
    try:
        app.controller.run()
        end = time.monotonic() + 30
        while app.controller.progress_text != "Optimising rates…":
            assert time.monotonic() < end
            time.sleep(0.02)
        strings = _draw(app).strings
        assert "Optimising rates…" in strings
        assert app.next_frame_in() is not None
        app.controller.stop()
        gate.set()
        _settle(app)
        assert app.controller.status == "Kinetics fit cancelled."
    finally:
        gate.set()
        app.close()


def test_errors_and_the_no_result_case(monkeypatch):
    app = _app(simulate=False)
    try:
        app.controller.run()
        assert app.controller.status == "Add at least one .bur burst table, or tick Simulate."
        app.controller.browse("export")
        assert app.controller.status == "Run a fit first." and app.controller.dialog is None
        from chisurf.plugins.burst.burst_gs.gui import view_model

        app.model.use_simulation = True
        monkeypatch.setattr(view_model.BurstGsViewModel, "compute", lambda self, progress=None: False)
        app.controller.run()
        _settle(app)
        assert app.controller.status == "The fit did not produce a result — see the report."
        monkeypatch.setattr(view_model.BurstGsViewModel, "compute",
                            lambda self, progress=None: (_ for _ in ()).throw(ValueError("singular Hessian")))
        app.controller.run()
        _settle(app)
        assert app.controller.status == "The fit failed: singular Hessian"
        assert "The fit failed: singular Hessian" in " ".join(_draw(app).strings)
    finally:
        app.close()


def test_export_after_a_fit_suggests_the_qt_name(tmp_path):
    table = tmp_path / "m000.bur"
    table.write_text("First Photon\tLast Photon\n")
    app = _app()
    try:
        app.controller.add_files([table])
        app.controller.run()
        _settle(app)
        app.controller.browse("export")
        assert app.controller.dialog.title == "Export photon-by-photon kinetics"
        assert app.controller.dialog.filename == "m000.gs.csv"
        out = tmp_path / "m000.gs.csv"
        app.controller.dialog.draw = lambda: [str(out)]
        end = time.monotonic() + 30
        while app.controller.dialog is not None:
            assert time.monotonic() < end
            _draw(app, n=1)
        assert out.exists() and out.read_text().strip()
        assert app.controller.status == f"Wrote {out}"
    finally:
        app.close()


def test_drops_add_tables_and_folders_and_say_when_nothing_was_added(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "m1.bur").write_text("x")
    (tmp_path / "m2.bur").write_text("x")
    stray = tmp_path / "notes.txt"
    stray.write_text("x")
    app = _app(simulate=False)
    try:
        app.on_paths_dropped([str(tmp_path / "a"), str(tmp_path / "m2.bur")])
        assert [Path(p).name for p in app.model.bur_files] == ["m1.bur", "m2.bur"]
        app.on_paths_dropped([str(stray)])
        assert app.controller.status == "No .bur burst table among the dropped paths."
    finally:
        app.close()


# 3. every guide target is drawn
def test_every_guide_target_is_drawn():
    app = _app()
    try:
        app.controller.run()
        _settle(app)
        keys = {app.gs_gui.tour._target_key(s.get("target")) for s in app.gs_gui.tour.steps} - {""}
        assert keys and keys <= set(app.item_rects), keys - set(app.item_rects)
    finally:
        app.close()


# 5. the guide's action steps wait for the real control and a press releases them
def test_the_simulate_and_fit_steps_wait_for_their_controls():
    app = _app(simulate=False)
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + 8, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        steps = app.gs_gui.tour.steps
        simulate = next(i for i, st in enumerate(steps) if st.get("target", {}).get("attr") == "use_simulation")
        app.gs_gui.tour.start(simulate)
        assert app.gs_gui.tour.awaiting
        press("use_simulation")
        assert app.model.use_simulation and not app.gs_gui.tour.awaiting
        fit = next(i for i, st in enumerate(steps) if st.get("target", {}).get("action") == "Fit")
        app.gs_gui.tour.start(fit)
        assert app.gs_gui.tour.awaiting
        press("Fit")
        assert not app.gs_gui.tour.awaiting and (app.controller.running or app.model.analysis is not None)
        _settle(app)
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size):
    app = _app()
    try:
        assert "Use Simulation Mode" in _draw(app, size).strings
        app.controller.run()
        _settle(app)
        strings = _draw(app, size).strings
        assert "Fitted rates" in strings and "State 1" in strings
    finally:
        app.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    result = qt_free("burst_gs")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    app = build_emtk_app("burst_gs")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
