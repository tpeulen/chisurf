"""The native Align-Trajectory tool at parity with the Qt AlignTrajectoryWidget.

The Qt widget runs in a subprocess (this process stays Qt-free) on the hgbp1 test
trajectory through its own section: its answers with nothing chosen, a cancelled
dialog and a save are compared with the emtk app's, and both aligned files against a
superposition done here directly.
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
FIT, STRIDE = "0, 1, 2, 3", 4

from chisurf.plugins.traj.traj_align.app import AlignTrajectoryApp  # noqa: E402


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=120.0):
    end = time.monotonic() + timeout
    while app.running:
        assert time.monotonic() < end, "the alignment did not finish"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _pick(app, path):
    app.dialog.draw = lambda: [str(path)]
    _draw(app, n=1)
    assert app.dialog is None


def _messages(log):
    return [re.sub(r"^\[\d\d:\d\d:\d\d\] ", "", line) for line in log]


def _loaded(selection=FIT, stride=STRIDE):
    app = AlignTrajectoryApp()
    app.model.set_trajectory(TRAJ)
    app.model.set_topology(TOP)
    app.model.atom_selection, app.model.stride = selection, stride
    return app


def _read(path):
    from chisurf.core.structure import trajectory_data as md

    return md.load(str(path), top=TOP)


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.traj.traj_align import sections
from chisurf.plugins.traj.traj_align.widget import AlignTrajectoryWidget
traj, top, target, selection, stride = sys.argv[1:6]
told, errors = [], []
sections.dialogs.information = lambda parent, title, text: told.append([title, text])
sections.dialogs.error = lambda parent, title, text: errors.append([title, text])
w = AlignTrajectoryWidget()
io = w.findChild(sections._IoSection)
io._save_aligned()                                    # nothing chosen yet
io._load_trajectory(traj); io._load_topology(top)
w.model.atom_selection, w.model.stride = selection, int(stride)
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
io._save_aligned()                                    # the dialog closed
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (target, "DCD trajectory (*.dcd)"))
io._save_aligned()
w.model.atom_selection = "CA, 1"
io._save_aligned()                                    # a selection that is not atom ids
w.model.atom_selection = selection
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (target + "/inside_a_file.dcd", ""))
io._save_aligned()                                    # an unwritable target
print("FACTS" + json.dumps({"told": told, "errors": errors, "log": w.model._log}))
"""


@pytest.fixture(scope="module")
def qt(tmp_path_factory):
    pytest.importorskip("qtpy")
    target = tmp_path_factory.mktemp("qt") / "aligned.dcd"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, TRAJ, TOP, str(target), FIT, str(STRIDE)],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and (
        "No module named" in proc.stderr or "could not connect to display" in proc.stderr
    ):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt widget's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    facts = json.loads(line[len("FACTS") :])
    facts["target"] = target
    return facts


@pytest.fixture(scope="module")
def reference():
    """The source read at the stride and superposed onto frame 0 on the fitting atoms, here."""
    from chisurf.core.structure import trajectory_data as md

    source = md.load(TRAJ, top=TOP, stride=STRIDE)
    frame0 = md.load_frame(TRAJ, 0, top=TOP)
    aligned = md.load(TRAJ, top=TOP, stride=STRIDE)  # superpose works in place
    return source, aligned.superpose(frame0, frame=0, atom_indices=np.array([0, 1, 2, 3], np.int32))


# 1. the same aligned file as the Qt widget; that file is the superposition
def test_a_save_writes_what_the_qt_widget_writes(qt, reference, tmp_path):
    app = _loaded()
    try:
        app.begin_save()
        assert app.dialog.title == "Save aligned trajectory" and app.dialog.mode == "save"
        assert app.dialog.filters == [("DCD trajectory", ["*.dcd"])]
        assert app.dialog.filename == "hgbp1_transition_aligned.dcd"
        target = tmp_path / "aligned.dcd"
        _pick(app, target)
        _settle(app)
        ours, theirs = _read(target), _read(qt["target"])
        source, aligned = reference
        assert ours.n_frames == theirs.n_frames == source.n_frames == 116  # 464 frames at stride 4
        assert np.asarray(ours.xyz) == pytest.approx(np.asarray(theirs.xyz), abs=1e-4)
        assert np.asarray(ours.xyz) == pytest.approx(np.asarray(aligned.xyz), abs=1e-3)
        moved = np.abs(np.asarray(source.xyz) - np.asarray(aligned.xyz)).max()
        assert moved > 1.0  # the alignment did move the frames
        assert _messages(app.model.log_text())[-1] == f"Aligned trajectory saved: {target}"
        assert _messages(qt["log"]).count(f"Aligning {TRAJ} (stride={STRIDE})") >= 1
    finally:
        app.close()


# 2. actions and errors, in the Qt widget's words
def test_nothing_chosen_a_cancel_and_a_bad_selection_answer_as_the_qt_widget_does(qt, tmp_path):
    app = AlignTrajectoryApp()
    try:
        app.begin_save()
        assert [app.status] == [text for _title, text in qt["told"]] == ["Open a trajectory first."]
        assert app.dialog is None
        app.model.set_trajectory(TRAJ)
        app.model.set_topology(TOP)
        app.begin_save()
        app.dialog.draw = lambda: False
        _draw(app, n=1)
        assert app.dialog is None and "Save cancelled" in _messages(app.model.log_text())
        assert "Save cancelled" in _messages(qt["log"])
        app.model.atom_selection = "CA, 1"
        app.save(str(tmp_path / "aligned.dcd"))
        _settle(app)
        bad = "Atom selection must be a comma-separated list of atom ids; cannot parse 'CA'"
        assert _messages(app.model.log_text())[-1] == bad and bad in _messages(qt["log"])
        assert not (tmp_path / "aligned.dcd").exists()
    finally:
        app.close()


def test_a_failed_alignment_is_reported_as_the_qt_widget_titles_it(qt, tmp_path):
    (tmp_path / "file").write_text("x")
    app = _loaded()
    try:
        app.save(str(tmp_path / "file" / "inside_a_file.dcd"))
        _settle(app)
        [(title, text)] = qt["errors"]
        assert title == "Align failed" and app.status.startswith("Align failed: ")
        assert any(s.startswith("Align failed: ") for s in _draw(app).strings)
    finally:
        app.close()


# 3. the spec's fields are drawn with their descriptions and write the model
def test_every_spec_field_is_drawn_with_its_description(monkeypatch):
    from emtk import im, im_widgets
    from emtk.view_form import _commit

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)
    spec = json.loads((HERE.parent / "align_trajectory.view.json").read_text())
    fields = [s for s in spec["sections"][0]["sections"] if s.get("attr")]
    app = AlignTrajectoryApp()
    try:
        _draw(app)
        assert {f["attr"] for f in fields} == {"atom_selection", "stride"} <= set(app.form.rects)
        assert all(f["description"] in tips for f in fields)
        stride = next(f for f in fields if f["attr"] == "stride")
        _commit(app.model, stride, 8, app.form)
        assert app.model.stride == 8
        assert app.export_settings()["stride"] == 8
    finally:
        app.close()


def test_frames_are_requested_and_the_form_disabled_while_aligning(monkeypatch, tmp_path):
    import threading

    from chisurf.plugins.traj.traj_align import view_model

    gate = threading.Event()
    original = view_model.AlignTrajectoryViewModel.save_aligned
    monkeypatch.setattr(
        view_model.AlignTrajectoryViewModel,
        "save_aligned",
        lambda self, target: (gate.wait(10), original(self, target))[1],
    )
    app = _loaded()
    try:
        app.save(str(tmp_path / "aligned.dcd"))
        assert app.running and app.animating() and "Working…" in _draw(app).strings
        app.save(str(tmp_path / "second.dcd"))  # a second press while busy is ignored
        gate.set()
        _settle(app)
        assert (tmp_path / "aligned.dcd").exists() and not app.animating()
        assert not (tmp_path / "second.dcd").exists()
    finally:
        gate.set()
        app.close()


# guide: every target drawn; the file and save steps wait for their control
def test_the_guide_points_at_real_controls_and_waits():
    app = AlignTrajectoryApp()
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys == {"trajectory", "topology", "atom_selection", "stride", "save", "log"}
        assert keys <= set(app.item_rects)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        steps = app.tour.steps
        for target, button in (("topology", "topology_browse"), ("save", "save")):
            index = next(
                i for i, s in enumerate(steps) if s.get("target", {}).get("name") == target
            )
            app.tour.start(index)
            assert app.tour.awaiting
            assert steps[index]["title"] in " ".join(_draw(app, size, n=1).strings)
            _draw(app, size, n=1, painter=PixelPainter)
            press(button)
            assert not app.tour.awaiting, target
            app.dialog = None
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size, tmp_path):
    app = AlignTrajectoryApp()
    try:
        strings = _draw(app, size).strings
        assert {
            "Trajectory",
            "Topology",
            "💾  Save aligned…",
            "Atom selection",
            "Stride",
            "Log",
        } <= {s.strip() for s in strings}
        app = _loaded()
        app.save(str(tmp_path / "aligned.dcd"))
        _settle(app)
        assert "Aligned trajectory saved" in " ".join(_draw(app, size).strings)
        log = app.item_rects["log"]
        assert log[1] + log[3] <= size[1] + 1 and log[3] > 100
    finally:
        app.close()


def test_settings_round_trip():
    app = _loaded()
    other = AlignTrajectoryApp()
    other.restore_settings(json.loads(json.dumps(app.export_settings())))
    m = other.model
    assert (m.trajectory_filename, m.topology_filename, m.atom_selection, m.stride) == (
        TRAJ,
        TOP,
        FIT,
        STRIDE,
    )


def test_help_opens_with_its_page():
    app = AlignTrajectoryApp()
    app.show_help()
    assert app.help_window.open and "frame 0" in " ".join(_draw(app).strings)


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("traj_align")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("traj_align")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
