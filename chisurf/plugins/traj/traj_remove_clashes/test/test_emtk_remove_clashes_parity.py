"""The native Remove-Clashed-Frames tool at parity with the Qt RemoveClashedFrames widget.

The Qt widget runs in a subprocess (this process stays Qt-free) on the hgbp1 test
trajectory through its own section: its answers with nothing chosen, a cancelled
dialog and a save are compared with the emtk app's, and both files against a clash
test done here with scipy's pairwise distances.
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
SELECTION, STRIDE, MIN_DISTANCE = "name CA", 4, 3.5

from chisurf.plugins.traj.traj_remove_clashes.app import RemoveClashesApp  # noqa: E402


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=120.0):
    end = time.monotonic() + timeout
    while app.running:
        assert time.monotonic() < end, "the filter did not finish"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _pick(app, path):
    app.dialog.draw = lambda: [str(path)]
    _draw(app, n=1)
    assert app.dialog is None


def _messages(log):
    return [re.sub(r"^\[\d\d:\d\d:\d\d\] ", "", line) for line in log]


def _loaded():
    app = RemoveClashesApp()
    app.model.set_trajectory(TRAJ)
    app.model.set_topology(TOP)
    app.model.atom_selection, app.model.stride, app.model.min_distance = SELECTION, STRIDE, MIN_DISTANCE
    return app


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.traj.traj_remove_clashes import sections
from chisurf.plugins.traj.traj_remove_clashes.widget import RemoveClashedFrames
traj, top, target, selection, stride, distance = sys.argv[1:7]
told, errors, asked = [], [], []
sections.dialogs.information = lambda parent, title, text: told.append([title, text])
sections.dialogs.error = lambda parent, title, text: errors.append([title, text])
w = RemoveClashedFrames()
io = w.findChild(sections._IoSection)
io._save_clash_free()                                 # nothing chosen yet
io._load_trajectory(traj); io._load_topology(top)
w.model.atom_selection, w.model.stride, w.model.min_distance = selection, int(stride), float(distance)
def answer(value):
    return staticmethod(lambda parent, title, directory, filters: (asked.append([title, filters]), (value, ""))[1])
QtWidgets.QFileDialog.getSaveFileName = answer("")
io._save_clash_free()                                 # the dialog closed
QtWidgets.QFileDialog.getSaveFileName = answer(target)
io._save_clash_free()
w.model.atom_selection = "name"
io._save_clash_free()                                 # a selection that does not parse
print("FACTS" + json.dumps({"told": told, "errors": errors, "asked": asked, "log": w.model._log}))
"""


@pytest.fixture(scope="module")
def qt(tmp_path_factory):
    pytest.importorskip("qtpy")
    target = tmp_path_factory.mktemp("qt") / "clash_free.dcd"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, TRAJ, TOP, str(target), SELECTION, str(STRIDE),
                           str(MIN_DISTANCE)], capture_output=True, text=True, timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt widget's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    facts = json.loads(line[len("FACTS"):])
    facts["target"] = target
    return facts


@pytest.fixture(scope="module")
def reference():
    """The frames whose C-alpha atoms all stay >= 3.5 A apart, found here with pdist."""
    from scipy.spatial.distance import pdist

    from chisurf.core.structure import trajectory_data as md

    source = md.load(TRAJ, top=TOP, stride=STRIDE)
    atoms = source.top.select(SELECTION)
    keep = np.array([pdist(np.asarray(frame, dtype=float)[atoms]).min() >= MIN_DISTANCE for frame in source.xyz])
    return source, keep


def _read(path):
    from chisurf.core.fio.trajectory.dcd import read_times
    from chisurf.core.structure import trajectory_data as md

    return md.load(str(path), top=TOP), read_times(str(path))


# 1. the same frames as the Qt widget; exactly the frames without a clash, with their times
def test_a_save_keeps_what_the_qt_widget_keeps(qt, reference, tmp_path):
    source, keep = reference
    app = _loaded()
    try:
        app.begin_save()
        assert app.dialog.title == "Save clash-free trajectory"
        assert app.dialog.filters == [("DCD trajectory", ["*.dcd"])]
        assert qt["asked"][-1] == ["Save clash-free trajectory", "DCD trajectory (*.dcd)"]   # the Qt dialog, fixed
        assert app.dialog.filename == "hgbp1_transition_clash_free.dcd"
        target = tmp_path / "clash_free.dcd"
        _pick(app, target)
        _settle(app)
        (ours, our_times), (theirs, their_times) = _read(target), _read(qt["target"])
        assert keep.sum() == ours.n_frames == theirs.n_frames == 42 and len(keep) == 116
        assert np.asarray(ours.xyz) == pytest.approx(np.asarray(source.xyz)[keep], abs=1e-3)
        assert np.asarray(ours.xyz) == pytest.approx(np.asarray(theirs.xyz), abs=1e-4)
        assert np.asarray(our_times) == pytest.approx(np.asarray(source.time)[keep])   # the gaps stay visible
        assert np.asarray(our_times) == pytest.approx(np.asarray(their_times))
        mine = _messages(app.model.log_text())
        assert mine[-2:] == ["Kept 42 of 116 frames (min distance 3.5 Å)", f"Clash-free trajectory saved: {target}"]
        assert "Kept 42 of 116 frames (min distance 3.5 Å)" in _messages(qt["log"])
    finally:
        app.close()


# 2. actions and errors, in the Qt widget's words
def test_nothing_chosen_a_cancel_and_a_bad_selection_answer_as_the_qt_widget_does(qt, tmp_path):
    app = RemoveClashesApp()
    try:
        app.begin_save()
        assert [app.status] == [text for _title, text in qt["told"]] == ["Open a trajectory first."]
        app.model.set_trajectory(TRAJ)
        app.model.set_topology(TOP)
        app.begin_save()
        app.dialog.draw = lambda: False
        _draw(app, n=1)
        assert app.dialog is None and "Save cancelled" in _messages(app.model.log_text())
        assert "Save cancelled" in _messages(qt["log"])
        app.model.atom_selection = "name"
        app.save(str(tmp_path / "clash_free.dcd"))
        _settle(app)
        [(title, text)] = qt["errors"]
        assert title == "Save failed" and app.status == f"Save failed: {text}"
        assert app.status in _draw(app).strings
    finally:
        app.close()


# 3. the spec's fields are drawn with their descriptions and write the model
def test_every_spec_field_is_drawn_with_its_description(monkeypatch):
    from emtk import im, im_widgets
    from emtk.view_form import _commit

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)
    spec = json.loads((HERE.parent / "remove_clashes.view.json").read_text())
    fields = [s for s in spec["sections"][0]["sections"] if s.get("attr")]
    app = RemoveClashesApp()
    try:
        _draw(app)
        assert {f["attr"] for f in fields} == {"atom_selection", "stride", "min_distance"} <= set(app.form.rects)
        assert all(f["description"] in tips for f in fields)
        _commit(app.model, next(f for f in fields if f["attr"] == "min_distance"), 3.2, app.form)
        assert app.model.min_distance == pytest.approx(3.2) and app.export_settings()["min_distance"] == 3.2
    finally:
        app.close()


def test_frames_are_requested_and_the_form_disabled_while_filtering(monkeypatch, tmp_path):
    import threading

    from chisurf.plugins.traj.traj_remove_clashes import view_model

    gate = threading.Event()
    original = view_model.RemoveClashesViewModel.save_clash_free
    monkeypatch.setattr(view_model.RemoveClashesViewModel, "save_clash_free",
                        lambda self, target: (gate.wait(10), original(self, target))[1])
    app = _loaded()
    try:
        app.save(str(tmp_path / "clash_free.dcd"))
        assert app.running and app.animating() and "Working…" in _draw(app).strings
        app.save(str(tmp_path / "second.dcd"))
        gate.set()
        _settle(app)
        assert (tmp_path / "clash_free.dcd").exists() and not (tmp_path / "second.dcd").exists()
    finally:
        gate.set()
        app.close()


# guide: every target drawn; the file and save steps wait for presses
def test_the_guide_points_at_real_controls_and_waits():
    app = RemoveClashesApp()
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys == {"trajectory", "topology", "atom_selection", "stride", "min_distance", "save", "log"}
        assert keys <= set(app.item_rects)

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
            assert app.tour.awaiting and steps[index]["title"] in " ".join(_draw(app, size, n=1).strings)
            _draw(app, size, n=1, painter=PixelPainter)
            press(button)
            assert not app.tour.awaiting, target
            app.dialog = None
        assert app.status == "Open a trajectory first."
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size, tmp_path):
    app = RemoveClashesApp()
    try:
        strings = _draw(app, size).strings
        assert {"💾  Save clash-free…", "Atom selection", "Stride", "Min distance", "Log"} <= {s.strip() for s in strings}
        app = _loaded()
        app.save(str(tmp_path / "clash_free.dcd"))
        _settle(app)
        assert "Kept 42 of 116 frames" in " ".join(_draw(app, size).strings)
        log = app.item_rects["log"]
        assert log[1] + log[3] <= size[1] + 1 and log[3] > 100
    finally:
        app.close()


def test_settings_round_trip():
    app = _loaded()
    other = RemoveClashesApp()
    other.restore_settings(json.loads(json.dumps(app.export_settings())))
    m = other.model
    assert (m.trajectory_filename, m.topology_filename, m.atom_selection, m.stride, m.min_distance) == (
        TRAJ, TOP, SELECTION, STRIDE, MIN_DISTANCE)


def test_help_opens_with_its_page():
    app = RemoveClashesApp()
    app.show_help()
    assert app.help_window.open and "bond exclusion" in " ".join(_draw(app).strings)


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("traj_remove_clashes")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("traj_remove_clashes")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
