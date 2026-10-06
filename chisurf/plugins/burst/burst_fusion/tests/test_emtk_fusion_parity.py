"""The native burst fusion tool at parity with the Qt BurstFusionTool.

Both hosts draw the same ``BurstFusionApp``. The Qt tool loads the demo and fuses
synchronously (``load_demo``, ``process_bursts``); the emtk app does both on the
controller's worker. The Qt tool runs in a subprocess (this process stays Qt-free)
on the plugin's own demo, whose molecule count is declared, and the results are
compared.
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
from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.plugins.burst.burst_fusion.gui.app import create_app  # noqa: E402
from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory, qt_free  # noqa: E402


def _draw(app, size=(1200, 800), n=2):
    painter = RecordingPainter()
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _frames_until(app, done, timeout=120.0):
    end = time.monotonic() + timeout
    while not done():
        assert time.monotonic() < end, "not reached by drawing frames"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _settle(app):
    _frames_until(app, lambda: not app.controller.running)


def _demo(app):
    app.controller.demo()
    _settle(app)
    return app


_QT = r"""
import json, pathlib, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.burst.burst_fusion.gui.tool import BurstFusionTool
w = BurstFusionTool()
w.load_demo()
out = w.process_bursts()
print("FACTS" + json.dumps({"out": pathlib.Path(out).name, "files": sorted(p.name for p in pathlib.Path(out).rglob("*") if p.is_file()),
                            "status": w.model._status, "summary": w.model.summary_rows()}, default=str))
"""


def _qt_facts(settings_dir):
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", CHISURF_SETTINGS_DIR=str(settings_dir))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and (
        "No module named" in proc.stderr or "could not connect to display" in proc.stderr
    ):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt tool's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS") :])


# 1. the demo fused: the Qt tool's result and files, and towards the declared molecule count
def test_the_demo_fuses_as_in_the_qt_tool(tmp_path, monkeypatch):
    import functools

    from chisurf.plugins.burst.burst_fusion import demo

    qt = _qt_facts(tmp_path / "qt_settings")
    # A demo of its own: the cached one already holds fused folders from earlier runs, and the
    # writer then picks a new name ("…_0") instead of overwriting.
    monkeypatch.setattr(
        demo, "create_demo", functools.partial(demo.create_demo, directory=tmp_path / "own")
    )
    app = _demo(create_app())
    try:
        truth = app.model._demo["truth"]
        app.controller.run()
        _settle(app)
        out = Path(app.model.written_folder)
        assert out.name == qt["out"]
        assert sorted(p.name for p in out.rglob("*") if p.is_file()) == qt["files"]
        # The status names the written folder, under each side's own settings folder (the demo is
        # cached there; this process resolved its settings folder at import).
        assert app.model._status.replace(str(out.parent), "<demo>") == qt["status"].replace(
            str(tmp_path / "qt_settings" / "demo" / "burst_fusion"), "<demo>"
        )
        assert json.loads(json.dumps(app.model.summary_rows(), default=str)) == qt["summary"]
        stats = app.model.analysis.statistics
        before, after = stats["n_bursts_before"], stats["n_bursts_after"]
        assert abs(after - truth["n_molecules"]) < abs(
            before - truth["n_molecules"]
        )  # towards the 300 molecules
    finally:
        app.close()


# 2. the run's states
def test_stop_before_writing_keeps_the_previous_results(monkeypatch):
    import threading

    from chisurf.plugins.burst.burst_fusion.gui import view_model

    app = _demo(create_app())
    gate = threading.Event()
    original = view_model.FusionViewModel.analyze
    monkeypatch.setattr(
        view_model.FusionViewModel,
        "analyze",
        lambda self, cancel_check=None: (gate.wait(10), original(self, cancel_check))[1],
    )
    try:
        app.controller.run()
        _draw(app, n=1)
        assert app.controller.running and app.next_frame_in() is not None  # frames while running
        app.controller.stop()
        gate.set()
        _settle(app)
        assert (
            app.controller.status == "Fusion cancelled before writing; previous results retained."
        )
        assert not app.model.written_folder
    finally:
        gate.set()
        app.close()


def test_the_status_line_is_drawn_once():
    app = _demo(create_app())
    try:
        app.controller.estimate()
        _settle(app)
        strings = " ".join(_draw(app).strings)
        assert strings.count("283 bursts") == 1  # the result once (the controller repeated it)
    finally:
        app.close()


def test_settings_round_trip_and_report(tmp_path):
    app = _demo(create_app())
    try:
        app.model.settings.threshold = 0.7
        path = tmp_path / "fusion.json"
        app.controller.save_settings(path)
        app.model.settings.threshold = 0.5
        app.controller.load_settings(path)
        assert app.model.settings.threshold == 0.7
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({**json.loads(path.read_text()), "threshold": 3.0}))
        with pytest.raises(ValueError):
            app.controller.load_settings(bad)
        with pytest.raises(ValueError):
            app.controller.export_summary(tmp_path / "early.json")  # nothing estimated yet
        app.controller.estimate()
        _settle(app)
        report = tmp_path / "report.json"
        app.controller.export_summary(report)
        assert json.loads(report.read_text())["settings"]["threshold"] == 0.7
    finally:
        app.close()


def test_errors_reach_the_window(tmp_path):
    app = create_app()
    try:
        app.controller.run()
        assert app.controller.status == app.model.can_run()
        stray = tmp_path / "notes.txt"
        stray.write_text("x")
        app.on_paths_dropped([str(stray)])
        assert (
            app.controller.status
            == "Burst fusion reads a burst-analysis folder; notes.txt is not one."
        )
        assert not app.model.folder
        assert "is not one" in " ".join(_draw(app).strings)
    finally:
        app.close()


# 5. the folder by dialog and by drop
def test_the_folder_dialog_and_a_drop_take_a_burst_folder(tmp_path):
    folder = tmp_path / "burstwise"
    folder.mkdir()
    app = create_app()
    try:
        for action, (title, mode) in {
            "folder": ("Select burst folder", "folder"),
            "load": ("Load fusion settings", "open"),
            "save": ("Save fusion settings", "save"),
            "export": ("Export fusion report", "save"),
        }.items():
            app.controller.browse(action)
            assert (app.controller.dialog.title, app.controller.dialog.mode) == (title, mode), (
                action
            )
        app.controller.browse("folder")
        app.controller.dialog.draw = lambda: [str(folder)]
        _frames_until(app, lambda: app.controller.dialog is None)
        assert app.model.folder == str(folder)
        other = tmp_path / "other"
        other.mkdir()
        app.on_paths_dropped([str(other)])
        assert app.model.folder == str(other)
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


# 4. the fragments histogram shows every bar -- on a plot already drawn before the data came
def test_the_fragments_axis_holds_every_bar(monkeypatch):
    from emtk import implot

    ticks = []
    tik = implot.setup_axis_ticks
    monkeypatch.setattr(
        implot,
        "setup_axis_ticks",
        lambda axis, values, n_ticks=None, labels=None, *a, **k: (
            ticks.append(labels),
            tik(axis, values, n_ticks, labels, *a, **k),
        )[1],
    )
    seen = _y_ranges(monkeypatch)
    app = create_app()
    try:
        app.fusion_gui.selected_tab = "Fragments"
        _draw(app)  # the plot exists, empty
        _demo(app)
        app.controller.estimate()
        _settle(app)
        _draw(app, n=2)
        counts = [int(v) for s in app.model.group_size_series() for v in s["y"]]
        lo, hi = seen["Fragments per fused burst"]
        assert lo < min(counts) and hi > max(counts), (lo, hi, counts)
        sizes = sorted({int(v) for s in app.model.group_size_series() for v in s["x"]})
        assert [str(n) for n in sizes] in ticks
    finally:
        app.close()


# 3. every guide target is drawn
def test_every_guide_target_is_drawn():
    app = _demo(create_app())
    try:
        app.controller.estimate()
        _settle(app)
        keys = {
            app.fusion_gui.tour._target_key(s.get("target")) for s in app.fusion_gui.tour.steps
        } - {""}
        drawn = set(app.item_rects) | set(app.fusion_gui.form_state.rects)
        assert keys and keys <= drawn, keys - drawn
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size):
    app = create_app()
    try:
        _draw(app, size)
        _demo(app)
        app.controller.estimate()
        _settle(app)
        strings = _draw(app, size).strings
        assert "Same-molecule probability" in strings and "Fragments per fused burst" in strings
    finally:
        app.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    result = qt_free("burst_fusion")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    app = build_emtk_app("burst_fusion")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
