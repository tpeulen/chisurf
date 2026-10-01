"""The native 2CDE tool at parity with the Qt BurstTwoCdeTool.

Both hosts draw the same ``BurstTwoCdeApp``; what differs is the run around it --
the Qt tool's ChiSurfProgress worker, result cache, stamp and show-time run against
the emtk ``TwoCdeController``. The Qt worker runs in a subprocess on the same demo
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

from chisurf.plugins.burst.burst_2cde.core import computation as core  # noqa: E402
from chisurf.plugins.burst.burst_2cde.gui.app import create_app  # noqa: E402
from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    return build(tmp_path / "measurement")


def _app(folder=None):
    app = create_app()
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


def _settle(app, timeout=60.0):
    """Frames until the worker is done (the host would draw them on request)."""
    end = time.monotonic() + timeout
    while app.controller.running:
        assert time.monotonic() < end, "2CDE did not finish"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _values(df):
    return np.asarray(df[core.COLUMN_FRET_2CDE], float)


_QT = r"""
import json, pathlib, sys
from types import SimpleNamespace
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.burst.burst_2cde.gui.tool import BurstTwoCdeTool
folder = pathlib.Path(sys.argv[1])
w = BurstTwoCdeTool()
w.model.donor_channels_text, w.model.acceptor_channels_text = "0", "1"
w.model.set_folder(folder)
progress = SimpleNamespace(set_value=lambda v: None, set_maximum=lambda v: None)
task = SimpleNamespace(set_range=lambda a, b: None, set_text=lambda t: None, progress_window=lambda t: progress)
df, variant = w._analysis_worker(str(folder), w.settings(), w.analysis_fingerprint(), w.input_files(),
                                 w.fingerprint_params(), task)
import numpy as np
from chisurf.plugins.burst.burst_2cde.core import computation as core
print("FACTS" + json.dumps({"values": np.asarray(df[core.COLUMN_FRET_2CDE], float).tolist(), "variant": variant,
                            "params": w.fingerprint_params(),
                            "companions": sorted(p.name for p in (folder / "2c4").glob("*"))}))
"""


def _qt_facts(folder):
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, str(folder)], capture_output=True, text=True, timeout=300,
                          env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"the Qt tool could not be built here: {proc.stderr[-800:]}")
    return json.loads(line[len("FACTS"):])


# 1. the same answer as the Qt tool's worker, and the known one
def test_a_run_gives_the_qt_tools_answer_and_writes_the_same_companion(folder, tmp_path):
    qt_folder = build(tmp_path / "qt_measurement")
    qt = _qt_facts(qt_folder)
    app = _app(folder)
    try:
        app.controller.run()
        _settle(app)
        ours = _values(app.model.df)
        assert ours == pytest.approx(np.asarray(qt["values"]), nan_ok=True)
        assert json.loads(json.dumps(app.model.fingerprint_params())) == qt["params"]
        assert sorted(p.name for p in (folder / "2c4").glob("*")) == qt["companions"]
        index = np.arange(len(ours))
        assert np.nanmedian(ours[index % 4 != 3]) < 15 < np.nanmedian(ours[index % 4 == 3])
        assert app.model.status_text == "FRET-2CDE: 60 / 60 bursts valid"
        assert not app.model.is_running and not app.model.is_locked
    finally:
        app.close()


# 2. the run's states, as the Qt tool's
def test_an_unchanged_run_is_kept_and_points_at_restart(folder, monkeypatch):
    app = _app(folder)
    try:
        app.controller.run()
        _settle(app)
        calls = []
        original = core.compute_2cde
        monkeypatch.setattr(core, "compute_2cde", lambda *a, **k: calls.append(1) or original(*a, **k))
        app.controller.run()
        assert app.model.status_text == "Unchanged — kept the previous 2CDE result (Restart recomputes it)"
        assert app.model.restart_attention and not calls and not app.controller.running
        app.controller.restart()
        _settle(app)
        assert calls == [1] and not app.model.restart_attention
    finally:
        app.close()


def test_stop_abandons_the_run_and_only_an_explicit_run_restarts_it(folder, monkeypatch):
    import threading

    from chisurf.plugins.burst.burst_bva.core import computation as bva

    release = threading.Event()
    real = bva.read_burst_analysis

    def slow(*a, **k):
        assert release.wait(10)
        return real(*a, **k)

    monkeypatch.setattr(core, "read_burst_analysis", slow)
    app = _app(folder)
    try:
        app.controller.run()
        assert app.model.is_locked
        app.controller.stop()
        release.set()
        _settle(app)
        assert app.model.df is None and "cancelled" in app.model.status_text
        assert not (folder / "2c4").exists()                     # nothing written
        app.controller.auto_run()                                # shown again: not by itself
        assert not app.controller.running
        assert app.model.status_text == "Stopped earlier — press Run to compute 2CDE"
        app.controller.run()                                     # an explicit Run
        _settle(app)
        assert app.model.df is not None
    finally:
        release.set()
        app.close()


def test_the_first_frame_runs_a_folder_that_is_already_set(folder):
    app = _app(folder)
    try:
        _draw(app, n=1)
        assert app.controller.running or app.model.df is not None
        _settle(app)
        assert app.model.df is not None
    finally:
        app.close()


def test_a_dropped_folder_runs_and_anything_else_is_reported(folder):
    app = _app()
    try:
        assert app.files_dropped([str(folder / "bi4_bur" / "m000.bur")])
        assert app.model.status_text == "2CDE reads a burst-analysis folder; m000.bur is not one."
        assert app.files_dropped([str(folder)])
        assert app.model.folder == str(folder)
        _settle(app)
        assert app.model.df is not None
    finally:
        app.close()


def test_progress_is_shown_while_running(folder, monkeypatch):
    import threading

    gate = threading.Event()
    seen = []
    original = core.compute_2cde

    def compute(*a, progress_window=None, **k):
        progress_window.set_value(30)
        seen.append((app.model.progress_text, app.model.progress))
        assert gate.wait(10)
        return original(*a, progress_window=progress_window, **k)

    monkeypatch.setattr(core, "compute_2cde", compute)
    app = _app(folder)
    try:
        app.controller.run()
        end = time.monotonic() + 30
        while not seen:
            assert time.monotonic() < end
            time.sleep(0.02)
        assert seen == [("Computing 2CDE …", pytest.approx(0.5))]
        painter = _draw(app)
        assert "Computing 2CDE …" in painter.strings
        assert app.next_frame_in() is not None                   # looks again soon while running
        gate.set()
        _settle(app)
        assert app.model.progress_text == "" and not app.controller.running
    finally:
        gate.set()
        app.close()


# 2. errors
def test_errors_reach_the_window(folder, tmp_path, monkeypatch):
    app = _app(tmp_path / "missing")
    try:
        app.controller.run()
        assert app.model.status_text == "Select a valid burstwise analysis folder."
        app.model.set_folder(folder)
        monkeypatch.setattr(core, "write_2cde_analysis", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
        app.controller.run()
        _settle(app)
        assert app.model.df is not None                          # the result stands, as in Qt
        assert "could not write the 2c4 companion: disk full" in app.model.status_text
        monkeypatch.setattr(core, "read_burst_analysis", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad table")))
        app.controller.restart()
        _settle(app)
        assert app.model.df is None and app.model.status_text == "Error: bad table"
        assert "Error: bad table" in _draw(app).strings
    finally:
        app.close()


# 3. every guide step points at something drawn
def test_every_guide_target_is_drawn():
    app = _app()
    try:
        _draw(app)
        steps = json.loads((HERE.parent / "gui" / "guide.json").read_text())["steps"]
        keys = {app.two_cde_gui.tour._target_key(s.get("target")) for s in steps if s.get("target")}
        keys.discard(None)
        keys.discard("")
        assert keys and keys <= set(app.item_rects), keys - set(app.item_rects)
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(folder, size):
    app = _app()
    try:
        assert {"Analysis folder:", "2CDE Parameters"} <= set(_draw(app, size).strings)
        pane_right = app.item_rects["controls"][0] + app.item_rects["controls"][2]
        for name in ("run", "restart", "stop", "folder", "guide", "help"):   # the row wraps, nothing is cut
            x, _y, w, _h = app.item_rects[name]
            assert x + w <= pane_right, name
        app.model.set_folder(folder)
        app.controller.run()
        _settle(app)
        strings = _draw(app, size).strings
        assert "FRET-2CDE: 60 / 60 bursts valid" in strings
        assert "Threshold: 10.0" in strings
    finally:
        app.close()


def _y_ranges(monkeypatch):
    """The y range each plot ends its frame with, by title (what is drawn, not what was asked)."""
    from emtk import implot
    from emtk import implot_internal as I

    seen = {}
    original = implot.end_plot

    def end_plot():
        plot = I.gp.current_plot
        if plot is not None:
            axis = plot.axes[I.AXIS_Y1]
            seen[plot.title] = (float(axis.range_min), float(axis.range_max))
        return original()

    monkeypatch.setattr(implot, "end_plot", end_plot)
    return seen


def test_the_2cde_axis_fits_every_burst_of_a_new_result(folder, monkeypatch):
    """Measured on a plot already drawn empty, as in the app: the result arrives later."""
    seen = _y_ranges(monkeypatch)
    app = _app()
    try:
        _draw(app)                                            # the empty plot exists
        app.model.set_folder(folder)
        app.controller.run()
        _settle(app)
        _draw(app, n=2)
        y = _values(app.model.df)
        lo, hi = seen["FRET-2CDE / ALEX-2CDE"]
        assert lo < np.nanmin(y) and hi > np.nanmax(y), (lo, hi)  # no burst on (or past) the edge
    finally:
        app.close()


# 6. no Qt
def test_port_is_qt_free():
    result = qt_free("burst_2cde")
    assert result["ok"], result["output"]


# 7. tooltips
def test_every_control_has_a_tooltip():
    app = build_emtk_app("burst_2cde")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
