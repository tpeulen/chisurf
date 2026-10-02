"""The native burst IRF & background tool at parity with the Qt BurstIrfBackgroundTool.

Both hosts draw the same ``BurstIrfBackgroundApp``. The Qt tool computes
synchronously and hands the patterns to the workflow shell it is embedded in; the
emtk app computes on the controller's worker and hands them to an ``mle_receiver``.
The Qt tool runs in a subprocess on the same demo measurement (this process stays
Qt-free) and the results are compared, and both against the IRF the demo was made with.
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

from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app  # noqa: E402
from chisurf.plugins.burst.burst_irf_bg.test.demo_data import IRF_PEAK_NS, build  # noqa: E402

DETECTORS = {"green": {"chs": [0, 8], "micro_time_ranges": [[0, 4096]]},
             "red": {"chs": [1, 9], "micro_time_ranges": [[0, 4096]]}}


@pytest.fixture(scope="module")
def measurement(tmp_path_factory):
    return build(tmp_path_factory.mktemp("irf") / "measurement")


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _frames_until(app, done, timeout=60.0, size=(1200, 800)):
    end = time.monotonic() + timeout
    while not done():
        assert time.monotonic() < end, "not reached by drawing frames"
        time.sleep(0.02)
        _draw(app, size, n=1)
    _draw(app, size, n=1)


def _computed(app, path):
    app.controller.add_files([path])
    app.controller.run()
    _frames_until(app, lambda: not app.controller.running and app.model.has_results())
    return app


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.burst.burst_irf_bg.gui.tool import BurstIrfBackgroundTool

class Shell(QtWidgets.QWidget):
    received = None
    def apply_irf_background_to_mle(self, patterns):
        Shell.received = sorted(patterns)
        return len(patterns)

shell = Shell()
w = BurstIrfBackgroundTool(parent=shell)
w.model.channels_provider = lambda: json.loads(sys.argv[2])
w._send_to_mle()
early = w.gui.status_text
w.model.add_files([sys.argv[1]])
w._compute()
w._send_to_mle()
print("FACTS" + json.dumps({"rows": w.model.results_rows(), "sent": w.gui.status_text, "early": early,
                            "received": Shell.received}))
"""


@pytest.fixture(scope="module")
def qt(measurement):
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, str(measurement), json.dumps(DETECTORS)], capture_output=True,
                          text=True, timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt tool's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS"):])


# 1. the Qt tool's results, and the IRF the demo was made with
def test_results_equal_the_qt_tools_and_the_known_irf(qt, measurement):
    app = _computed(create_app(), measurement)
    try:
        rows = app.model.results_rows()
        assert json.loads(json.dumps(rows)) == qt["rows"]
        for row in rows:
            assert abs(row["prompt_ns"] - IRF_PEAK_NS) < 0.15
        rates = [r["background_khz"] for r in rows]
        assert abs(rates[0] - rates[1]) / max(rates) < 0.05     # the same non-burst stream on both
        for series in app.model.irf_series()[:2]:
            x, y = np.asarray(series["x"]), np.asarray(series["y"])
            assert abs(float(x[np.argmax(y)]) - IRF_PEAK_NS) < 0.05
    finally:
        app.close()


# 2. the MLE hand-off, in the Qt words
def test_send_to_mle_hands_the_patterns_over_as_the_qt_tool_does(qt, measurement):
    received = []
    app = create_app(mle_receiver=lambda patterns: (received.append(sorted(patterns)), len(patterns))[1])
    try:
        app.controller.send_to_mle()
        assert app.controller.status == qt["early"] == "Compute the IRF and background first."
        _computed(app, measurement)
        assert app.controller.send_to_mle()
        assert app.controller.status == qt["sent"]
        assert received == [qt["received"]]
    finally:
        app.close()
    alone = _computed(create_app(), measurement)
    try:
        assert not alone.controller.send_to_mle()
        assert "Burst Analysis" in alone.controller.status       # no workflow to receive them
    finally:
        alone.close()


def test_export_patterns_needs_a_result_and_writes_them(measurement, tmp_path):
    app = create_app()
    try:
        app.controller.browse("patterns")
        assert app.controller.status == "Compute the IRF and background first." and app.controller.dialog is None
        _computed(app, measurement)
        app.controller.browse("patterns")
        assert app.controller.dialog.title == "Export MLE patterns"
        out = tmp_path / "irf_background.npz"
        app.controller.dialog.draw = lambda: [str(out)]
        _frames_until(app, lambda: app.controller.dialog is None)
        with np.load(out) as data:
            assert {"green/irf", "red/irf"} <= set(data.files) or len(data.files) >= 2
        assert app.controller.status == f"MLE patterns exported: {out}"
    finally:
        app.close()


def test_errors_reach_the_window(tmp_path):
    app = create_app()
    try:
        app.controller.run()
        assert app.controller.status == app.model.can_compute()
        bad = tmp_path / "broken.ptu"
        bad.write_bytes(b"not a measurement")
        app.controller.add_files([bad])
        app.controller.run()
        _frames_until(app, lambda: not app.controller.running)
        assert app.controller.status.startswith("Error:")
        assert any(s.startswith("Error:") for s in _draw(app).strings)
    finally:
        app.close()


def test_the_status_is_drawn_once_and_frames_requested_while_computing(measurement, monkeypatch):
    import threading

    from chisurf.plugins.burst.burst_irf_bg.gui import view_model

    gate = threading.Event()
    original = view_model.IrfBackgroundViewModel.compute
    monkeypatch.setattr(view_model.IrfBackgroundViewModel, "compute",
                        lambda self, cancel_check=None: (gate.wait(10), original(self, cancel_check))[1])
    app = create_app()
    try:
        app.controller.add_files([measurement])
        app.controller.run()
        _draw(app, n=1)
        assert app.controller.running and app.next_frame_in() is not None
        gate.set()
        _frames_until(app, lambda: not app.controller.running and app.model.has_results())
        joined = " ".join(_draw(app).strings)
        assert joined.count("Extracted IRF + background for 2 detector(s).") == 1
    finally:
        gate.set()
        app.close()


# 3/5. the guide: every target drawn, the Extract step waits for a press
def test_every_guide_target_is_drawn_and_extract_waits(measurement):
    app = create_app()
    size = (800, 600)
    try:
        app.controller.add_files([measurement])
        _draw(app, size, painter=PixelPainter)
        keys = {app.irf_gui.tour._target_key(s.get("target")) for s in app.irf_gui.tour.steps} - {""}
        app.controller.run()
        _frames_until(app, lambda: not app.controller.running and app.model.has_results(), size=size)
        drawn = set(app.item_rects) | set(app.irf_gui.form_state.rects)         # buttons, and the spec's fields
        assert keys and keys <= drawn, keys - drawn
        _draw(app, size, n=1, painter=PixelPainter)              # the rect from the painter we press with
        step = next(i for i, st in enumerate(app.irf_gui.tour.steps) if st.get("await"))
        app.irf_gui.tour.start(step)
        assert app.irf_gui.tour.awaiting
        x, y, w, h = app.item_rects["irf_bg_run"]
        app.pointer_move(x + w / 2, y + h / 2)
        app.press(x + w / 2, y + h / 2)
        _draw(app, size, n=1, painter=PixelPainter)
        app.release()
        _draw(app, size, n=1, painter=PixelPainter)
        assert not app.irf_gui.tour.awaiting
        _frames_until(app, lambda: not app.controller.running, size=size)
    finally:
        app.close()


def test_a_dropped_folder_adds_its_measurement_not_its_container(measurement):
    measurement.with_suffix(".pto").write_bytes(b"")
    app = create_app()
    try:
        app.on_paths_dropped([str(measurement.parent)])
        assert app.model.files == [str(measurement)]
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(measurement, size):
    app = create_app()
    try:
        assert "Min photons/burst" in [t.strip() for t in _draw(app, size).strings]
        _computed(app, measurement)
        strings = _draw(app, size).strings
        assert "IRF (non-burst scatter)" in strings
        assert {"Detector", "Background (kHz)", "Prompt (ns)", "Non-burst", "Burst"} <= set(strings)   # the data_table's headers
        rows = app.model.results_rows()
        assert rows and all(f"{r['background_khz']:.3f}" in strings and r["detector"] in strings for r in rows)
    finally:
        app.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    result = qt_free("burst_irf_bg")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    app = build_emtk_app("burst_irf_bg")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
