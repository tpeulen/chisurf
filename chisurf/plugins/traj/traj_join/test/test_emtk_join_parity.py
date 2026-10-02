"""The native Join-Trajectories tool at parity with the Qt JoinTrajectoriesWidget.

The Qt widget runs in a subprocess (this process stays Qt-free) on the hgbp1 test
trajectory through its own section: its answers with too few files, a cancelled
dialog and a save are compared with the emtk app's, and the joined files against the
join done here with numpy. The chunk size is smaller than the trajectory on purpose:
the old join interleaved and chunk-reversed on exactly that.
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
CHUNK = 100

from chisurf.plugins.traj.traj_join.app import JoinTrajectoriesApp  # noqa: E402


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=120.0):
    end = time.monotonic() + timeout
    while app.running:
        assert time.monotonic() < end, "the join did not finish"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _pick(app, path):
    app.dialog.draw = lambda: [str(path)]
    _draw(app, n=1)
    assert app.dialog is None


def _messages(log):
    return [re.sub(r"^\[\d\d:\d\d:\d\d\] ", "", line) for line in log]


def _loaded(mode="time", reverse_2=True, second=TRAJ):
    app = JoinTrajectoriesApp()
    app.model.set_trajectory_1(TRAJ)
    app.model.set_trajectory_2(second)
    app.model.set_topology(TOP)
    app.model.join_mode, app.model.reverse_traj_2, app.model.chunk_size = mode, reverse_2, CHUNK
    return app


@pytest.fixture(scope="module")
def source():
    from chisurf.core.structure import trajectory_data as md

    return np.asarray(md.load(TRAJ, top=TOP).xyz)


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.traj.traj_join import sections
from chisurf.plugins.traj.traj_join.widget import JoinTrajectoriesWidget
traj, top, target, chunk = sys.argv[1:5]
told, errors = [], []
sections.dialogs.information = lambda parent, title, text: told.append([title, text])
sections.dialogs.error = lambda parent, title, text: errors.append([title, text])
w = JoinTrajectoriesWidget()
io = w.findChild(sections._IoSection)
io._load_trajectory_1(traj)
io._save_joined()                                     # one trajectory only
io._load_trajectory_2(traj); io._load_topology(top)
w.model.reverse_traj_2, w.model.chunk_size = True, int(chunk)
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
io._save_joined()                                     # the dialog closed
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (target, "DCD trajectory (*.dcd)"))
io._save_joined()
print("FACTS" + json.dumps({"told": told, "errors": errors, "log": w.model._log}))
"""


@pytest.fixture(scope="module")
def qt(tmp_path_factory):
    pytest.importorskip("qtpy")
    target = tmp_path_factory.mktemp("qt") / "joined.dcd"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, TRAJ, TOP, str(target), str(CHUNK)], capture_output=True,
                          text=True, timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt widget's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    facts = json.loads(line[len("FACTS"):])
    facts["target"] = target
    return facts


def _read(path):
    from chisurf.core.structure import trajectory_data as md

    return np.asarray(md.load(str(path), top=TOP).xyz)


# 1. the same file as the Qt widget; that file is trajectory 1, then trajectory 2 backwards
def test_a_time_join_appends_the_whole_reversed_trajectory(qt, source, tmp_path):
    app = _loaded()
    try:
        app.begin_save()
        assert app.dialog.title == "Save trajectory" and app.dialog.filters == [("DCD trajectory", ["*.dcd"])]
        assert app.dialog.filename == "hgbp1_transition_joined.dcd"
        target = tmp_path / "joined.dcd"
        _pick(app, target)
        _settle(app)
        ours, theirs = _read(target), _read(qt["target"])
        expected = np.concatenate([source, source[::-1]])
        assert ours.shape == theirs.shape == expected.shape == (928, 5235, 3)
        np.testing.assert_allclose(ours, expected, atol=1e-3)         # not A0-99, B99-0, A100-199, ...
        np.testing.assert_allclose(ours, theirs, atol=1e-4)
        np.testing.assert_allclose(ours[463], ours[464], atol=1e-3)  # forward and back: the turn repeats a frame
        assert _messages(app.model.log_text())[-2:] == ["Wrote 928 frames of 5235 atoms",
                                                        f"Joined trajectory saved: {target}"]
        assert "Wrote 928 frames of 5235 atoms" in _messages(qt["log"])
    finally:
        app.close()


def test_an_atoms_join_stacks_frame_by_frame(source, tmp_path):
    app = _loaded(mode="atoms", reverse_2=False)
    try:
        app.save(str(tmp_path / "stacked.dcd"))
        _settle(app)
        from chisurf.core.fio.trajectory.dcd import read_dcd

        stacked = np.asarray(read_dcd(str(tmp_path / "stacked.dcd"))[0])     # no topology names 2 x 5235 atoms
        assert stacked.shape == (464, 2 * 5235, 3)
        np.testing.assert_allclose(stacked, np.concatenate([source, source], axis=1), atol=1e-3)
    finally:
        app.close()


@pytest.mark.parametrize("mode, words", [("time", "needs the same atoms"), ("atoms", "needs the same number of frames")])
def test_a_mismatch_stops_the_join_instead_of_truncating(mode, words, tmp_path):
    from chisurf.core.structure import trajectory_data as md

    trajectory = md.load(TRAJ, top=TOP)
    if mode == "time":       # fewer atoms: self-describing PDBs (a shared topology would refuse the DCD on load)
        first, second = tmp_path / "all.pdb", tmp_path / "part.pdb"
        trajectory[0].save_pdb(str(first))
        trajectory[0].atom_slice(np.arange(100)).save_pdb(str(second))
        app = JoinTrajectoriesApp()
        app.model.set_trajectory_1(str(first))
        app.model.set_trajectory_2(str(second))
    else:                    # fewer frames
        short = tmp_path / "short.dcd"
        trajectory[:10].save_dcd(str(short))
        app = _loaded(mode=mode, reverse_2=False, second=str(short))
    try:
        app.save(str(tmp_path / "joined.dcd"))
        _settle(app)
        assert app.status.startswith("Join failed: ") and words in app.status
        assert app.status in _draw(app).strings
    finally:
        app.close()


# 2. actions and errors, in the Qt widget's words
def test_one_file_and_a_cancel_answer_as_the_qt_widget_does(qt):
    app = JoinTrajectoriesApp()
    try:
        app.model.set_trajectory_1(TRAJ)
        app.begin_save()
        assert [app.status] == [text for _title, text in qt["told"]] == ["Open two trajectories first."]
        app.model.set_trajectory_2(TRAJ)
        app.begin_save()
        app.dialog.draw = lambda: False
        _draw(app, n=1)
        assert app.dialog is None and "Join cancelled" in _messages(app.model.log_text())
        assert "Join cancelled" in _messages(qt["log"])
    finally:
        app.close()


def test_two_dropped_trajectories_fill_both_rows(tmp_path):
    second = tmp_path / "second.dcd"
    second.write_bytes(Path(TRAJ).read_bytes())
    app = JoinTrajectoriesApp()
    try:
        app.on_paths_dropped([TRAJ, str(second), TOP])
        m = app.model
        assert (m.trajectory_filename_1, m.trajectory_filename_2, m.topology_filename) == (TRAJ, str(second), TOP)
    finally:
        app.close()


# 3. the spec's fields are drawn with their descriptions and write the model
def test_every_spec_field_is_drawn_with_its_description(monkeypatch):
    from emtk import im, im_widgets
    from emtk.view_form import _commit

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)
    spec = json.loads((HERE.parent / "join_trajectories.view.json").read_text())
    fields = [s for s in spec["sections"][0]["sections"] if s.get("attr")]
    app = JoinTrajectoriesApp()
    try:
        _draw(app)
        names = {"join_mode", "reverse_traj_1", "reverse_traj_2", "chunk_size"}
        assert {f["attr"] for f in fields} == names and names <= set(app.form.rects)
        assert all(f["description"] in tips for f in fields)
        assert not any("chunk of trajectory" in f["description"] for f in fields)   # whole-trajectory reversal
        _commit(app.model, next(f for f in fields if f["attr"] == "join_mode"), "atoms", app.form)
        assert app.model.join_mode == "atoms" and app.export_settings()["join_mode"] == "atoms"
    finally:
        app.close()


def test_frames_are_requested_and_the_form_disabled_while_joining(monkeypatch, tmp_path):
    import threading

    from chisurf.plugins.traj.traj_join import view_model

    gate = threading.Event()
    original = view_model.JoinTrajectoriesViewModel.save_joined
    monkeypatch.setattr(view_model.JoinTrajectoriesViewModel, "save_joined",
                        lambda self, target: (gate.wait(10), original(self, target))[1])
    app = _loaded()
    try:
        app.save(str(tmp_path / "joined.dcd"))
        assert app.running and app.animating() and "Working…" in _draw(app).strings
        app.save(str(tmp_path / "second.dcd"))
        gate.set()
        _settle(app)
        assert (tmp_path / "joined.dcd").exists() and not (tmp_path / "second.dcd").exists()
    finally:
        gate.set()
        app.close()


# guide: every target drawn; the file and save steps wait for presses
def test_the_guide_points_at_real_controls_and_waits():
    app = JoinTrajectoriesApp()
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys == {"trajectory_1", "trajectory_2", "topology", "join_mode", "reverse_traj_2", "chunk_size",
                        "save", "log"}
        assert keys <= set(app.item_rects)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        steps = app.tour.steps
        for target, button in (("trajectory_2", "trajectory_2_browse"), ("save", "save")):
            index = next(i for i, s in enumerate(steps) if s.get("target", {}).get("name") == target)
            app.tour.start(index)
            assert app.tour.awaiting and steps[index]["title"] in " ".join(_draw(app, size, n=1).strings)
            _draw(app, size, n=1, painter=PixelPainter)
            press(button)
            assert not app.tour.awaiting, target
            app.dialog = None
        assert app.status == "Open two trajectories first."
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size, tmp_path):
    app = JoinTrajectoriesApp()
    try:
        strings = _draw(app, size).strings
        assert {"Trajectory 1", "Trajectory 2", "Topology", "💾 Save joined…", "Chunk size", "Log"} <= set(strings)
        app = _loaded()
        app.save(str(tmp_path / "joined.dcd"))
        _settle(app)
        assert "Wrote 928 frames of 5235 atoms" in " ".join(_draw(app, size).strings)
        log = app.item_rects["log"]
        assert log[1] + log[3] <= size[1] + 1 and log[3] > 100
    finally:
        app.close()


def test_settings_round_trip():
    app = _loaded()
    other = JoinTrajectoriesApp()
    other.restore_settings(json.loads(json.dumps(app.export_settings())))
    m = other.model
    assert (m.trajectory_filename_1, m.trajectory_filename_2, m.topology_filename, m.join_mode, m.reverse_traj_2,
            m.chunk_size) == (TRAJ, TRAJ, TOP, "time", True, CHUNK)


def test_help_opens_with_its_page():
    app = JoinTrajectoriesApp()
    app.show_help()
    assert app.help_window.open and "round trip" in " ".join(_draw(app).strings)


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("traj_join")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("traj_join")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
