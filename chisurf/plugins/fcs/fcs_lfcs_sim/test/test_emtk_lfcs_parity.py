"""The native lifetime-FCS simulator at parity with the Qt LifetimeFcsSimWidget.

The Qt widget runs its own button slot in a subprocess (this process stays Qt-free);
its curves, status line and pens are compared with the emtk app's for the same
settings, and both against the committed Qt model's run written out here.
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
from emtk.testing import PixelPainter, RecordingPainter

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())

from chisurf.plugins.fcs.fcs_lfcs_sim.app import (  # noqa: E402
    CROSS_COLOUR, SPECIES_COLOURS, LifetimeFcsSimApp, make_app,
)
from chisurf.plugins.fcs.fcs_lfcs_sim.model import LifetimeFcsSimModel  # noqa: E402

#: Small enough to run in about a second, with exchange so the cross-correlation is not flat.
SETTINGS = {"tau1_ns": 1.0, "d1_um2_ms": 2.0, "tau2_ns": 4.0, "d2_um2_ms": 2.0, "exchange_rate_ms": 5.0,
            "n_photons": 60_000, "seed": 7}


def _app(**settings):
    app = make_app()
    for key, value in {**SETTINGS, **settings}.items():
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
    while app.running:
        assert time.monotonic() < end, "the simulation did not finish"
        time.sleep(0.05)
        app.poll()
    _draw(app, n=1)


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.fcs.fcs_lfcs_sim.gui import tool
w = tool.LifetimeFcsSimWidget()
for k, v in json.loads(sys.argv[1]).items():
    setattr(w._model, k, v)
controls = w.findChild(tool._LfcsSimControls)
controls._on_click()
print("FACTS" + json.dumps({
    "curves": [{"name": d["name"], "a": d["species_a"], "b": d["species_b"],
                "x": list(map(float, d["x"])), "y": list(map(float, d["y"]))} for d in w._model.datasets],
    "status": controls._status.text(),
    "pens": {"species": list(tool._SPECIES_COLORS), "cross": tool._CROSS_COLOR},
    "button": controls.btn.text()}))
"""


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, json.dumps(SETTINGS)], capture_output=True, text=True,
                          timeout=600, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt widget's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS"):])


def _reference():
    """The committed Qt model's run (before the model moved to model.py), written out."""
    from chisurf.core.fluorescence.fcs.filtered import calc_ffcs_filters, filter_condition_number
    from chisurf.core.fluorescence.fcs.simulate import simulate_lifetime_fcs
    from chisurf.plugins.fcs.fcs_correlator.core import filtered_correlation_datasets

    s = SETTINGS
    sim = simulate_lifetime_fcs(lifetimes_ns=(s["tau1_ns"], s["tau2_ns"]), diffusion_um2_ms=(s["d1_um2_ms"], s["d2_um2_ms"]),
                                exchange_rate_ms=s["exchange_rate_ms"], n_photons=s["n_photons"], seed=s["seed"])
    filters, _, _ = calc_ffcs_filters(sim.total_decay, sim.reference_decays)
    datasets = filtered_correlation_datasets(sim.macro_times, sim.micro_times, filters, sim.macro_time_resolution_s,
                                             n_bins=8, n_casc=25, labels=[f"τ={s['tau1_ns']:g} ns", f"τ={s['tau2_ns']:g} ns"])
    return datasets, filter_condition_number(sim.total_decay, sim.reference_decays)


# 1. the same curves and status as the Qt widget's button, and as the committed model
def test_a_simulation_gives_the_qt_widgets_curves_and_status(qt):
    app = _app()
    try:
        app.simulate()
        _settle(app)
        ours = app.model.datasets
        assert [d["name"] for d in ours] == [c["name"] for c in qt["curves"]]
        for d, c in zip(ours, qt["curves"]):
            assert (d["species_a"], d["species_b"]) == (c["a"], c["b"])
            assert np.asarray(d["y"], float) == pytest.approx(np.asarray(c["y"]), nan_ok=True)
            assert np.asarray(d["x"], float) == pytest.approx(np.asarray(c["x"]))
        assert app.message == qt["status"]
    finally:
        app.close()


def test_the_model_runs_what_the_committed_qt_model_ran():
    model = LifetimeFcsSimModel()
    for key, value in SETTINGS.items():
        setattr(model, key, value)
    model.run()
    reference, condition = _reference()
    assert model.condition_number == pytest.approx(condition)
    for d, r in zip(model.datasets, reference, strict=True):
        assert d["name"] == r["name"]
        assert np.asarray(d["y"], float) == pytest.approx(np.asarray(r["y"], float), nan_ok=True)


# 1. the Qt pens: species 1 blue, species 2 red, the cross-correlation green
def test_curves_carry_the_qt_widgets_colours(qt, monkeypatch):
    from emtk import implot

    def rgb(hex_colour):
        return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))

    assert [rgb(c) for c in qt["pens"]["species"]] == [c[:3] for c in SPECIES_COLOURS]
    assert rgb(qt["pens"]["cross"]) == CROSS_COLOUR[:3]
    styles = []
    monkeypatch.setattr(implot, "set_next_line_style", lambda colour=None, weight=0, dash=None: styles.append(colour))
    app = _app()
    try:
        app.simulate()
        _settle(app)
        styles.clear()
        _draw(app, n=1)
        assert styles == [SPECIES_COLOURS[0], SPECIES_COLOURS[1], CROSS_COLOUR]
    finally:
        app.close()


def test_the_lag_axis_is_logarithmic_as_in_the_qt_plot(monkeypatch):
    from emtk import implot

    scales = []
    original = implot.setup_axis_scale
    monkeypatch.setattr(implot, "setup_axis_scale", lambda axis, scale, *a, **k: (scales.append((axis, scale)),
                                                                                  original(axis, scale, *a, **k))[1])
    app = make_app()
    try:
        _draw(app, n=1)
        assert (implot.AXIS_X1, implot.SCALE_LOG10) in scales
    finally:
        app.close()


# 2. actions while running, and errors
def test_the_form_is_locked_and_a_second_press_ignored_while_running(monkeypatch):
    import threading

    gate = threading.Event()
    calls = []
    app = _app()
    monkeypatch.setattr(app.model, "run", lambda: (calls.append(1), gate.wait(10), [])[2])
    try:
        app.simulate()
        app.simulate()                                         # ignored: one submitted
        time.sleep(0.1)
        assert calls == [1] and app.running
        assert app.message == "Simulating…"
        _draw(app, n=1)
        assert app.next_frame_in() is not None                 # looks again while the worker runs
        gate.set()
        _settle(app)
        time.sleep(0.2)                                        # a queued second job would have run by now
        assert calls == [1]
    finally:
        gate.set()
        app.close()


def test_a_failed_simulation_says_why():
    app = _app()
    app.model.run = lambda: (_ for _ in ()).throw(ValueError("photon budget too small"))
    try:
        app.simulate()
        _settle(app)
        assert app.message == "Simulation failed: photon budget too small"
        assert app.model.datasets == []
        assert any("photon budget too small" in s for s in _draw(app).strings)
    finally:
        app.close()


# 3. the spec: every field is a model attribute with a description; the Run panel is drawn
def test_the_spec_binds_the_model_and_its_run_panel():
    app = make_app()
    try:
        fields = [f for panel in app.spec["sections"] for f in panel["sections"] if f["type"] == "value"]
        assert {f["attr"] for f in fields} == {"tau1_ns", "d1_um2_ms", "tau2_ns", "d2_um2_ms",
                                               "exchange_rate_ms", "n_photons", "seed"}
        assert all(f.get("description") and hasattr(app.model, f["attr"]) for f in fields)
        strings = _draw(app).strings
        assert "Set parameters and simulate." in strings
        assert set(app.form.rects) >= {f["attr"] for f in fields}
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size):
    app = _app()
    try:
        strings = _draw(app, size).strings
        assert {"Simulate + Correlate", "Guide", "?", "lag time (ms)"} <= set(strings)
        app.simulate()
        _settle(app)
        strings = _draw(app, size).strings
        assert "τ=1 ns × τ=4 ns" in strings
        assert app.message in " ".join(strings)                 # the status line, wrapped to the pane
    finally:
        app.close()


# 5. end to end: press the drawn button; the guide step on it waits for that press
def test_pressing_simulate_runs_and_the_guide_waits_for_it():
    app = _app()
    size = (480, 360)
    try:
        _draw(app, size, painter=PixelPainter)
        step = next(i for i, s in enumerate(app.tour.steps) if s.get("await"))
        app.tour.start(step)
        assert app.tour.awaiting
        x, y, w, h = app.item_rects["lfcs_sim_controls"]
        app.pointer_move(x + w / 2, y + h / 2)
        app.press(x + w / 2, y + h / 2)
        _draw(app, size, n=1, painter=PixelPainter)
        app.release()
        _draw(app, size, n=1, painter=PixelPainter)
        assert app.running or app.model.datasets
        assert not app.tour.awaiting
        _settle(app)
        assert len(app.model.datasets) == 3
    finally:
        app.close()


def test_every_guide_target_is_drawn():
    app = make_app()
    try:
        _draw(app)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys and all(app.target_rect(k) is not None for k in keys), keys
    finally:
        app.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("fcs-lfcs-sim")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("fcs-lfcs-sim")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()


def test_the_app_class_is_exported():
    assert isinstance(make_app(), LifetimeFcsSimApp)
