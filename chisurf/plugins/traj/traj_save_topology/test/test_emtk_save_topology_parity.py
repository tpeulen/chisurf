"""The native Save-Topology tool at parity with the Qt SaveTopology widget.

The Qt widget runs in a subprocess (this process stays Qt-free) on the hgbp1 test
trajectory: its save, its "no trajectory" and "cancelled" answers are compared with
the emtk app's, and the written PDB against frame 0 of the trajectory read directly.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import PixelPainter, RecordingPainter

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
DATA = REPO / "test" / "data" / "atomic_coordinates" / "trajectory" / "hgbp1"
TRAJ, TOP = str(DATA / "hgbp1_transition.dcd"), str(DATA / "topol.pdb")

from chisurf.plugins.traj.traj_save_topology.app import SaveTopologyApp  # noqa: E402


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=60.0):
    end = time.monotonic() + timeout
    while app.running:
        assert time.monotonic() < end, "the save did not finish"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _pick(app, path):
    """Answer the open file dialog with *path*, as a click on its action would."""
    app.dialog.draw = lambda: [str(path)]
    _draw(app, n=1)
    assert app.dialog is None


def _messages(log):
    return [re.sub(r"^\[\d\d:\d\d:\d\d\] ", "", line) for line in log]


def _loaded(**kw):
    app = SaveTopologyApp()
    app.model.set_trajectory(kw.get("traj", TRAJ))
    app.model.set_topology(kw.get("top", TOP))
    return app


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.traj.traj_save_topology import sections
from chisurf.plugins.traj.traj_save_topology.widget import SaveTopology
traj, top, target = sys.argv[1:4]
told = []
sections.dialogs.information = lambda parent, title, text: told.append([title, text])
w = SaveTopology()
io = w.findChild(sections._IoSection)
io._save_topology()                                   # nothing chosen yet
io._load_trajectory(traj); io._load_topology(top)
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
io._save_topology()                                   # the dialog closed
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (target, "PDB-files (*.pdb)"))
io._save_topology()
print("FACTS" + json.dumps({"told": told, "log": w.model._log,
                            "fields": [io._edit.text(), io._top_edit.text()]}))
"""


@pytest.fixture(scope="module")
def qt(tmp_path_factory):
    pytest.importorskip("qtpy")
    target = tmp_path_factory.mktemp("qt") / "frame0.pdb"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, TRAJ, TOP, str(target)], capture_output=True, text=True,
                          timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt widget's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    facts = json.loads(line[len("FACTS"):])
    facts["target"] = target
    return facts


# 1. the same file and the same log as the Qt widget; the file is frame 0
def test_a_save_writes_what_the_qt_widget_writes(qt, tmp_path):
    from chisurf.core.structure import trajectory_data as md

    app = _loaded()
    try:
        app.begin_save()
        assert app.dialog.title == "Save PDB-file" and app.dialog.mode == "save"
        assert app.dialog.filename == "hgbp1_transition_frame0.pdb"
        target = tmp_path / "frame0.pdb"
        _pick(app, target)
        _settle(app)
        ours = md.load(str(target))
        theirs = md.load(str(qt["target"]))
        frame0 = md.load(TRAJ, top=TOP)[0]
        assert ours.n_atoms == theirs.n_atoms == frame0.n_atoms == 5235
        assert np.asarray(ours.xyz) == pytest.approx(np.asarray(theirs.xyz))
        assert np.abs(np.asarray(ours.xyz) - np.asarray(frame0.xyz)).max() < 1e-3   # PDB keeps 3 decimals
        mine = _messages(app.model.log_text())
        assert mine[-1] == "Topology saved" and _messages(qt["log"])[-1] == "Topology saved"
        assert mine[-3:-1] == [f"Loading first frame: {TRAJ}", f"Saving topology to: {target}"]
    finally:
        app.close()


# 2. actions and errors, in the Qt widget's words
def test_nothing_chosen_and_a_cancelled_dialog_answer_as_the_qt_widget_does(qt):
    app = SaveTopologyApp()
    try:
        app.begin_save()
        assert [app.status] == [text for _title, text in qt["told"]] == ["Open a trajectory first."]
        assert app.dialog is None
        app.model.set_trajectory(TRAJ)
        app.model.set_topology(TOP)
        app.begin_save()
        app.dialog.draw = lambda: False
        _draw(app, n=1)
        assert app.dialog is None
        assert "Save cancelled" in _messages(app.model.log_text()) and "Save cancelled" in _messages(qt["log"])
        assert qt["fields"] == [TRAJ, TOP]
    finally:
        app.close()


def test_a_failed_save_is_shown_in_the_window(tmp_path):
    app = _loaded()
    try:
        app.save(str(tmp_path / "missing" / "frame0.pdb"))
        _settle(app)
        assert app.status.startswith("Save failed:")
        assert app.model.log_text()[-1].split("] ", 1)[1].startswith("Save failed:")
        assert any(s.startswith("Save failed:") for s in _draw(app).strings)
    finally:
        app.close()


def test_a_dcd_without_its_topology_fails_in_the_window_not_silently(tmp_path):
    app = SaveTopologyApp()
    try:
        app.model.set_trajectory(TRAJ)
        app.save(str(tmp_path / "frame0.pdb"))
        _settle(app)
        assert "stores coordinates only" in app.status
        assert not (tmp_path / "frame0.pdb").exists()
    finally:
        app.close()


def test_the_rows_take_existing_files_from_their_dialogs_and_from_drops(tmp_path):
    app = SaveTopologyApp()
    try:
        trajectory, topology = app.paths
        app.browse(trajectory)
        assert app.dialog.title == "Open trajectory" and app.dialog.filters == [("Trajectories", ["*.dcd"])]
        _pick(app, TRAJ)
        assert app.model.trajectory_filename == TRAJ
        app.browse(topology)
        assert app.dialog.title == "Open topology"
        assert app.dialog.filters == [("Structures", ["*.pdb", "*.cif", "*.ent"])]
        _pick(app, tmp_path / "gone.pdb")                       # not a file: the row keeps its value
        assert app.model.topology_filename == ""
        app.on_paths_dropped([TOP])                           # a structure goes to Topology
        assert app.model.topology_filename == TOP
        stray = tmp_path / "notes.txt"
        stray.write_text("x")
        app.on_paths_dropped([str(stray)])
        assert app.status == "No trajectory or topology file among the dropped paths."
    finally:
        app.close()


def test_frames_are_requested_and_the_form_disabled_while_saving(monkeypatch, tmp_path):
    import threading

    from chisurf.plugins.traj.traj_save_topology import view_model

    gate = threading.Event()
    original = view_model.SaveTopologyViewModel.save_topology
    monkeypatch.setattr(view_model.SaveTopologyViewModel, "save_topology",
                        lambda self, target: (gate.wait(10), original(self, target))[1])
    app = _loaded()
    try:
        app.save(str(tmp_path / "frame0.pdb"))
        assert app.running and app.animating()
        assert "Working…" in _draw(app).strings
        app.save(str(tmp_path / "second.pdb"))                # a second press while busy is ignored
        gate.set()
        _settle(app)
        assert not app.animating() and (tmp_path / "frame0.pdb").exists()
        assert not (tmp_path / "second.pdb").exists()
    finally:
        gate.set()
        app.close()


# 3. every guide target is drawn; the action steps wait for their control
def test_the_guide_points_at_real_controls_and_waits():
    app = SaveTopologyApp()
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys == {"trajectory", "topology", "save", "log"} and keys <= set(app.item_rects)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        steps = app.tour.steps
        for target, button in (("trajectory", "trajectory_browse"), ("save", "save")):
            index = next(i for i, s in enumerate(steps) if s.get("target", {}).get("name") == target)
            app.tour.start(index)
            assert app.tour.awaiting
            assert steps[index]["title"] in " ".join(_draw(app, size, n=1).strings)   # the card is drawn
            _draw(app, size, n=1, painter=PixelPainter)
            press(button)
            assert not app.tour.awaiting, target
            app.dialog = None
        assert app.status == "Open a trajectory first."      # the save press reached the action
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size, tmp_path):
    app = SaveTopologyApp()
    try:
        strings = _draw(app, size).strings
        assert {"Trajectory", "Topology", "💾 Save topology…", "Log", "📖 Guide", "❓ Help"} <= set(strings)
        app.model.set_trajectory(TRAJ)
        app.model.set_topology(TOP)
        app.save(str(tmp_path / "frame0.pdb"))
        _settle(app)
        strings = " ".join(_draw(app, size).strings)
        assert "Topology saved" in strings
        log = app.item_rects["log"]
        assert log[1] + log[3] <= size[1] + 1 and log[3] > 100        # the log fills the window, inside it
    finally:
        app.close()


def test_settings_round_trip():
    app = _loaded()
    other = SaveTopologyApp()
    other.restore_settings(json.loads(json.dumps(app.export_settings())))
    assert (other.model.trajectory_filename, other.model.topology_filename) == (TRAJ, TOP)
    stale = SaveTopologyApp()
    stale.restore_settings({"trajectory_filename": "/no/such/file.dcd"})
    assert stale.model.trajectory_filename == ""                # a moved file is not restored


def test_help_opens_with_its_page():
    app = SaveTopologyApp()
    app.show_help()
    strings = " ".join(_draw(app).strings)
    assert app.help_window.open and "frame 0" in strings


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("traj_save_topology")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("traj_save_topology")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
