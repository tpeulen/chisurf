"""The native BVA tool at parity with the Qt BVATool.

Both hosts draw the same ``BurstBvaApp``; what differs is the run around it -- the
Qt tool's ChiSurfProgress worker, result cache, stamp and auto update against the
emtk ``BvaController``. The Qt worker runs in a subprocess on the same demo burst
folder (this process stays Qt-free) and the answers are compared.
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
from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory, qt_free  # noqa: E402  (before tttrlib's `test`)

from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build  # noqa: E402
from chisurf.plugins.burst.burst_bva.core import computation as core  # noqa: E402
from chisurf.plugins.burst.burst_bva.gui.app import create_app  # noqa: E402


@pytest.fixture(autouse=True)
def _scratch_settings(tmp_path, monkeypatch):
    """The defaults INI (window length, last folder ...) lives in a scratch settings folder."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))


@pytest.fixture
def folder(tmp_path):
    return build(tmp_path / "measurement")


def _app(folder=None, auto_update=False):
    app = create_app()
    app.model.auto_update = auto_update
    app.model.donor_channels_text, app.model.acceptor_channels_text = "0", "1"
    if folder is not None:
        app.model.set_folder(folder)
    return app


def _draw(app, size=(1200, 800), n=2):
    painter = RecordingPainter()
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _frames_until(app, done, timeout=60.0):
    end = time.monotonic() + timeout
    while not done():
        assert time.monotonic() < end, "not reached by drawing frames"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _settle(app):
    _frames_until(app, lambda: not app.controller.running)


def _std(df):
    """The per-burst Std of the proximity ratio (DataStore ``columns`` are Column objects: use the names)."""
    from chisurf.core.datastore import column_names

    return np.asarray(df["Proximity Ratio Std"], float) if "Proximity Ratio Std" in column_names(df) else None


_QT = r"""
import json, pathlib, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import numpy as np
from chisurf.plugins.burst.burst_bva.gui.tool import BVATool
class Task:
    def set_range(self, *a): pass
    def set_text(self, *a): pass
    def progress_window(self, *a):
        return type("P", (), {"set_value": lambda s, v: None, "set_maximum": lambda s, v: None})()
def run(w):
    s = w.model.bva_settings()
    w._analysis_done(w._analysis_worker(s, True, w.analysis_fingerprint(s), w.input_files(), w.fingerprint_params(s), Task()))
    return np.asarray(w.model.df["Proximity Ratio Std"], float).tolist()
w = BVATool()
w.model.auto_update = False
w.model.donor_channels_text, w.model.acceptor_channels_text = "0", "1"
w.model.set_folder(pathlib.Path(sys.argv[1]))
first = run(w)
w.model.set_folder(pathlib.Path(sys.argv[2]))
second = run(w)
print("FACTS" + json.dumps({"first": first, "second": second, "status": w.model.status_text,
                            "companions": sorted(p.name for p in (pathlib.Path(sys.argv[1]) / "bv4").glob("*"))}))
"""


def _qt_facts(first, second):
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, str(first), str(second)], capture_output=True, text=True,
                          timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt tool's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS"):])


# 1. the Qt tool's answer, and the known one; the companions it writes
def test_a_run_gives_the_qt_tools_bva_and_writes_the_same_companions(tmp_path):
    a, b = build(tmp_path / "qt_a"), build(tmp_path / "qt_b", seed=9)
    qt = _qt_facts(a, b)
    ours_a = build(tmp_path / "a")
    app = _app(ours_a)
    try:
        app.controller.run()
        _settle(app)
        std = _std(app.model.df)
        assert std == pytest.approx(np.asarray(qt["first"]), nan_ok=True)
        assert sorted(p.name for p in (ours_a / "bv4").glob("*")) == qt["companions"]
        assert app.model.status_text == qt["status"]
        index = np.arange(len(std))
        # dynamic bursts (every 4th) spread far above the static ones
        assert np.nanmedian(std[index % 4 == 3]) > 2 * np.nanmedian(std[index % 4 != 3])
    finally:
        app.close()


# 1. a new folder is computed on its own bursts (the read table was reused across folders)
def test_a_new_folder_is_computed_on_its_own_bursts(tmp_path):
    a, b = build(tmp_path / "a"), build(tmp_path / "b", seed=9)
    fresh = _app(b)
    try:
        fresh.controller.run()
        _settle(fresh)
        expected = _std(fresh.model.df)
    finally:
        fresh.close()
    app = _app(a)
    try:
        app.controller.run()
        _settle(app)
        app.model.set_folder(b)
        app.controller.run()
        _settle(app)
        assert _std(app.model.df) == pytest.approx(expected, nan_ok=True)
    finally:
        app.close()
    qt = _qt_facts(build(tmp_path / "qa"), build(tmp_path / "qb", seed=9))
    assert np.asarray(qt["second"]) == pytest.approx(expected, nan_ok=True)   # the Qt tool too


# 2. the run's states, as the Qt tool's
def test_auto_update_recomputes_without_writing_and_run_writes(folder, monkeypatch):
    reads = []
    original = core.read_burst_analysis
    monkeypatch.setattr(core, "read_burst_analysis", lambda *a, **k: (reads.append(1), original(*a, **k))[1])
    app = _app(folder, auto_update=True)
    try:
        app.model.set_folder(folder)                             # auto update: computes, writes nothing
        _settle(app)
        assert app.model.df is not None and not (folder / "bv4").exists()
        app.model.photons_per_slice = 12
        app.model.notify("param")
        _settle(app)
        assert reads == [1]                                     # the table is read once and reused
        app.controller.run()                                    # an explicit Run writes
        _settle(app)
        assert (folder / "bv4" / "bva.stamp.json").exists() and (folder / "bv4" / "bva_settings.json").exists()
        app.controller.run()
        assert app.model.status_text == "Unchanged — kept the previous BVA result (Restart recomputes it)"
        assert app.model.restart_attention and not app.controller.running
        app.controller.restart()
        _settle(app)
        assert not app.model.restart_attention
    finally:
        app.close()


def test_stop_then_an_explicit_run_computes(folder, monkeypatch):
    import threading

    gate = threading.Event()
    original = core.compute_bva
    monkeypatch.setattr(core, "compute_bva", lambda *a, **k: (gate.wait(10), original(*a, **k))[1])
    app = _app(folder)
    try:
        app.controller.run()
        _draw(app, n=1)
        assert app.controller.running and app.next_frame_in() is not None   # frames while running
        app.controller.stop()
        gate.set()
        _settle(app)
        assert app.model.df is None and app.model.status_text == "BVA cancelled."
        app.controller.run()
        _settle(app)
        assert app.model.df is not None
    finally:
        gate.set()
        app.close()


def test_a_failed_bv4_write_keeps_the_result(folder, monkeypatch):
    monkeypatch.setattr(core, "write_bv4_analysis", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    app = _app(folder)
    try:
        app.controller.run()
        _settle(app)
        assert app.model.df is not None
        assert "could not write the bv4 companions: disk full" in app.model.status_text
    finally:
        app.close()


def test_errors_reach_the_window(tmp_path, monkeypatch):
    app = _app()
    try:
        app.controller.run()
        assert app.model.status_text == "Select a data folder first."
        empty = tmp_path / "empty"
        empty.mkdir()
        app.model.set_folder(empty)
        monkeypatch.setattr(core, "read_burst_analysis", lambda *a, **k: (_ for _ in ()).throw(ValueError("no bursts")))
        app.controller.run()
        _settle(app)
        assert app.model.status_text == "BVA failed: no bursts"
        assert "BVA failed: no bursts" in _draw(app).strings
    finally:
        app.close()


# 5. folder by drop, by dialog; the plot saved as a picture of the window
def test_drops_take_folders_and_containers_and_report_the_rest(folder, tmp_path):
    app = _app()
    try:
        stray = tmp_path / "notes.txt"
        stray.write_text("x")
        assert app.files_dropped([str(stray)])
        assert app.model.status_text == "BVA reads a burst-analysis folder; notes.txt is not one."
        assert app.files_dropped([str(folder)])
        assert app.model.analysis_folder == folder
    finally:
        app.close()


def test_the_folder_dialog_and_save_plot(folder, tmp_path):
    app = _app()
    try:
        _draw(app)
        app.controller.browse()
        assert app.controller.dialog.title == "Select Data Folder"
        app.controller.dialog.draw = lambda: [str(folder)]
        _frames_until(app, lambda: app.controller.dialog is None)
        assert app.model.analysis_folder == folder
        app.controller.run()
        _settle(app)
        app.controller.save_plot()
        assert app.controller.dialog.title == "Save Plot"
        target = tmp_path / "bva_plot.png"
        app.controller.dialog.draw = lambda: [str(target)]
        _frames_until(app, lambda: target.exists())
        assert target.read_bytes().startswith(b"\x89PNG")
        assert app.model.status_text == f"Plot saved: {target}"
    finally:
        app.close()


# 3. every guide target is drawn
def test_every_guide_target_is_drawn(folder):
    app = _app(folder)
    try:
        app.controller.run()
        _settle(app)
        keys = {app.bva_gui.tour._target_key(s.get("target")) for s in app.bva_gui.tour.steps} - {""}
        assert keys and keys <= set(app.item_rects), keys - set(app.item_rects)
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(folder, size):
    app = _app()
    try:
        assert "Burst folder:" in _draw(app, size).strings
        pane_right = app.item_rects["controls"][0] + app.item_rects["controls"][2]
        for name in ("run", "restart", "stop", "folder", "guide", "help"):   # the row wraps, nothing is cut
            x, _y, w, _h = app.item_rects[name]
            assert x + w <= pane_right, name
        app.model.set_folder(folder)
        app.controller.run()
        _settle(app)
        strings = _draw(app, size).strings
        assert "Done – 60 bursts with Std > 0 on 60 total" in " ".join(strings)
        assert {"Static line", "Bursts", "Profile mean"} <= set(strings)
    finally:
        app.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    result = qt_free("burst_bva")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    app = build_emtk_app("burst_bva")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
