"""The native accurate-FRET app at parity with the Qt AccurateFretTool: numbers, guide, tooltips, plots.

The Qt numbers come from ``AccurateFretTool`` built in a subprocess on the same
simulated bursts (this process stays Qt-free); the calibration workflow itself
is covered by ``test_native.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.accurate_fret.gui.app import create_app

from .test_accurate_fret_plugin import TAU_D0, _simulate

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())


def _bursts(tmp_path) -> Path:
    dd, da, aa, tau = _simulate(n=100)
    path = tmp_path / "bursts.npz"
    np.savez(
        path,
        **{
            "Green Count Rate (KHz)": dd,
            "Red Count Rate (KHz)": da,
            "S delayed yellow (kHz)": aa,
            "Tau (green)": tau,
        },
    )
    return path


def _calibrated(path):
    app = create_app()
    app.model.n_bootstrap = 0
    app.model.donor_lifetime = TAU_D0
    app.controller.load(str(path))
    app.controller._future.result(timeout=30)
    app.controller.poll()
    app.controller.run()
    app.controller._future.result(timeout=60)
    app.controller.poll()
    return app


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.burst.accurate_fret.gui.tool import AccurateFretTool
w = AccurateFretTool()
m = w.model
m.n_bootstrap = 0
m.donor_lifetime = float(sys.argv[2])
m.set_filename(sys.argv[1])
assert m.compute()
print("FACTS" + json.dumps({"factors": m.factor_rows(), "populations": m.population_rows()}, default=str))
"""


def test_calibration_equals_the_qt_tool(tmp_path):
    """Same bursts, same settings: every factor and population row the Qt tool reports."""
    pytest.importorskip("qtpy")
    path = _bursts(tmp_path)
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", CHISURF_SETTINGS_DIR=str(tmp_path / "s"))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, str(path), str(TAU_D0)],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"AccurateFretTool could not be built here: {proc.stderr[-800:]}")
    qt = json.loads(line[len("FACTS") :])
    app = _calibrated(path)
    try:
        ours = json.loads(
            json.dumps(
                {"factors": app.model.factor_rows(), "populations": app.model.population_rows()},
                default=str,
            )
        )
        assert ours == qt
    finally:
        app.close()


def test_every_guide_target_is_drawn_and_the_calibrate_step_waits():
    app = create_app()
    gui = app.accurate_gui
    try:
        steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))
        steps = steps["steps"] if isinstance(steps, dict) else steps
        for index, step in enumerate(steps):
            gui.tour.start(index)
            _draw(app)
            key = gui.tour._target_key(step.get("target"))
            if key:
                assert gui.item_rects.get(key) is not None, key
            assert gui.tour.awaiting == bool(step.get("await")), (index, key)
        calibrate = next(i for i, s in enumerate(steps) if s.get("await"))
        gui.tour.start(calibrate)
        gui.track("Calibrate")  # what the button reports when pressed
        assert not gui.tour.awaiting
    finally:
        app.close()


def test_the_legend_leaves_the_donor_only_corner_free(monkeypatch, tmp_path):
    """The E–S legend sits top right: top left is where donor-only bursts are (E ≈ 0, S ≈ 1)."""
    from emtk import implot

    seen = []
    original = implot.setup_legend
    monkeypatch.setattr(
        implot, "setup_legend", lambda loc=0, flags=0: (seen.append(loc), original(loc, flags))
    )
    app = _calibrated(_bursts(tmp_path))
    try:
        es = {s["name"]: s for s in app.model.es_series()}
        assert (
            np.median(es["donor-only"]["y"]) > 0.9 and abs(np.median(es["donor-only"]["x"])) < 0.1
        )
        _draw(app)
        assert seen and set(seen) == {implot.LOCATION_NORTH_EAST}
    finally:
        app.close()


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_calibrated_at_both_sizes(tmp_path, size):
    app = _calibrated(_bursts(tmp_path))
    try:
        painter = _draw(app, size)
        assert {"α", "β", "γ", "δ"} <= set(painter.strings)
        assert "donor-only" in painter.strings
    finally:
        app.close()


def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("accurate_fret")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("accurate_fret"))
    assert inv["controls_without_tooltip"] == []
    spec = json.loads((GUI / "accurate_fret.view.json").read_text(encoding="utf-8"))

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "choice", "toggle"):
                assert s.get("description"), s.get("attr") or s
            for b in s.get("buttons", []):
                assert b.get("description"), b
            walk(s.get("sections", []))

    walk(spec["sections"])


def test_settings_round_trip(tmp_path):
    app = create_app()
    try:
        app.model.forster_radius = 61.5
        saved = json.loads(json.dumps(app.export_settings(), default=str))
        other = create_app()
        try:
            other.restore_settings(saved)
            assert other.model.forster_radius == 61.5
        finally:
            other.close()
    finally:
        app.close()


def test_the_histogram_is_drawn_with_its_range_fitted_to_the_counts(tmp_path, monkeypatch):
    """A range fixed before the data arrived cut the tallest peak off."""
    from emtk import implot

    limits = []
    original = implot.setup_axes_limits
    monkeypatch.setattr(
        implot, "setup_axes_limits", lambda *a, **k: (limits.append(a), original(*a, **k))
    )
    app = _calibrated(_bursts(tmp_path))
    try:
        app.accurate_gui.docks.focus("hist")
        painter = _draw(app)
        assert "accurate E" in painter.strings
        peak = max(float(np.max(s["y"])) for s in app.model.efficiency_histogram())
        assert any(len(a) >= 4 and a[3] >= peak for a in limits), limits
    finally:
        app.close()
