"""The native Rotate/Translate tool at parity with the Qt RotateTranslateTrajectoryWidget.

The Qt widget runs in a subprocess (this process stays Qt-free) on the hgbp1 test
trajectory, its matrix and translation typed into its own editors: its answers with
nothing chosen, a cancelled dialog and a save are compared with the emtk app's, and
both files against x' = R x + t computed here.
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
R = [[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]  # 90 degrees about z
T = [10.0, 0.0, 0.0]
STRIDE = 4

from chisurf.plugins.traj.traj_rotate_translate.app import (  # noqa: E402
    RotateTranslateApp,
    rotation_problem,
)


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=120.0):
    end = time.monotonic() + timeout
    while app.running:
        assert time.monotonic() < end, "the transform did not finish"
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
    app = RotateTranslateApp()
    app.model.set_trajectory(TRAJ)
    app.model.set_topology(TOP)
    app.model.set_rotation_matrix(R)
    app.model.set_translation_vector(T)
    app.model.stride = STRIDE
    return app


def _read(path):
    from chisurf.core.structure import trajectory_data as md

    return md.load(str(path), top=TOP)


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.traj.traj_rotate_translate import sections
from chisurf.plugins.traj.traj_rotate_translate.widget import RotateTranslateTrajectoryWidget
traj, top, target, matrix, vector, stride = sys.argv[1:7]
told, errors = [], []
sections.dialogs.information = lambda parent, title, text: told.append([title, text])
sections.dialogs.error = lambda parent, title, text: errors.append([title, text])
w = RotateTranslateTrajectoryWidget()
io = w.findChild(sections._IoSection)
io._save()                                            # nothing chosen yet
io._load_trajectory(traj); io._load_topology(top)
for i, row in enumerate(json.loads(matrix)):          # typed into the editors, as a user would
    for j, value in enumerate(row):
        io._rot_edits[i][j].setText(str(value))
for k, value in enumerate(json.loads(vector)):
    io._trans_edits[k].setText(str(value))
w.model.stride = int(stride)
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
io._save()                                            # the dialog closed
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (target, "DCD trajectory (*.dcd)"))
io._save()
QtWidgets.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (target + "/inside_a_file.dcd", ""))
io._save()                                            # an unwritable target
print("FACTS" + json.dumps({"told": told, "errors": errors, "log": w.model._log,
                            "matrix": w.model.rotation_matrix.tolist()}))
"""


@pytest.fixture(scope="module")
def qt(tmp_path_factory):
    pytest.importorskip("qtpy")
    target = tmp_path_factory.mktemp("qt") / "moved.dcd"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            _QT,
            TRAJ,
            TOP,
            str(target),
            json.dumps(R),
            json.dumps(T),
            str(STRIDE),
        ],
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


# 1. the same file as the Qt widget; that file is R x + t of the source
def test_a_save_writes_what_the_qt_widget_writes(qt, tmp_path):
    from chisurf.core.structure import trajectory_data as md

    app = _loaded()
    try:
        app.begin_save()
        assert app.dialog.title == "Save trajectory" and app.dialog.filters == [
            ("DCD trajectory", ["*.dcd"])
        ]
        assert app.dialog.filename == "hgbp1_transition_moved.dcd"
        target = tmp_path / "moved.dcd"
        _pick(app, target)
        _settle(app)
        ours, theirs = _read(target), _read(qt["target"])
        source = np.asarray(md.load(TRAJ, top=TOP, stride=STRIDE).xyz, dtype=float)
        expected = source @ np.asarray(R).T + np.asarray(T)
        assert ours.n_frames == theirs.n_frames == 116
        assert np.asarray(ours.xyz) == pytest.approx(np.asarray(theirs.xyz), abs=1e-4)
        assert np.asarray(ours.xyz) == pytest.approx(expected, abs=1e-3)
        x, y, z = source[0, 0]  # (10 - y, x, z), the help page's example
        assert np.asarray(ours.xyz)[0, 0] == pytest.approx([10 - y, x, z], abs=1e-3)
        assert (
            _messages(app.model.log_text())[-1] == f"Rotated/translated trajectory saved: {target}"
        )
        assert qt["matrix"] == R
    finally:
        app.close()


# 2. actions and errors, in the Qt widget's words
def test_nothing_chosen_a_cancel_and_a_failure_answer_as_the_qt_widget_does(qt, tmp_path):
    app = RotateTranslateApp()
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
        (tmp_path / "file").write_text("x")
        app.save(str(tmp_path / "file" / "inside_a_file.dcd"))
        _settle(app)
        [(title, _text)] = qt["errors"]
        assert title == "Save failed" and app.status.startswith("Save failed: ")
        assert _messages(app.model.log_text())[-1].startswith("Save failed: ")
        assert any(
            s.startswith("Save failed: ") for s in _draw(app).strings
        )  # shown, not only stored
    finally:
        app.close()


# the matrix and translation editors write the model; a non-rotation is named
def test_the_editors_write_the_matrix_and_translation(monkeypatch):
    from emtk import im

    app = RotateTranslateApp()
    try:
        # the cells are typed fields (the Qt editors are line edits): Enter in them hands the text over
        answers = {"##r01": "-1", "##r10": "1", "##r00": "0", "##r11": "0", "##t0": "10"}
        original = im.input_text
        monkeypatch.setattr(
            im,
            "input_text",
            lambda label, v, *a, **k: (
                (True, answers[label]) if label in answers else original(label, v, *a, **k)
            ),
        )
        _draw(app, n=1)
        monkeypatch.setattr(im, "input_text", original)
        assert np.asarray(app.model.rotation_matrix).tolist() == R
        assert np.asarray(app.model.translation_vector).tolist() == T
        assert {"rotation_matrix", "translation"} <= set(app.item_rects)
    finally:
        app.close()


@pytest.mark.parametrize(
    "matrix, words",
    [
        ([[1, 0.5, 0], [0, 1, 0], [0, 0, 1]], "sheared"),
        ([[-1, 0, 0], [0, 1, 0], [0, 0, 1]], "mirrored"),
        (R, ""),
    ],
)
def test_a_matrix_that_is_not_a_rotation_is_named(matrix, words):
    assert (words in rotation_problem(matrix)) and (bool(rotation_problem(matrix)) == bool(words))
    app = RotateTranslateApp()
    try:
        app.model.set_rotation_matrix(matrix)
        strings = " ".join(_draw(app).strings)
        assert ("Not a rotation" in strings) == bool(words)
    finally:
        app.close()


def test_frames_are_requested_and_the_form_disabled_while_saving(monkeypatch, tmp_path):
    import threading

    from chisurf.plugins.traj.traj_rotate_translate import view_model

    gate = threading.Event()
    original = view_model.RotateTranslateViewModel.save_rotated_translated
    monkeypatch.setattr(
        view_model.RotateTranslateViewModel,
        "save_rotated_translated",
        lambda self, target: (gate.wait(10), original(self, target))[1],
    )
    app = _loaded()
    try:
        app.save(str(tmp_path / "moved.dcd"))
        assert app.running and app.animating() and "Working…" in _draw(app).strings
        app.save(str(tmp_path / "second.dcd"))
        gate.set()
        _settle(app)
        assert (tmp_path / "moved.dcd").exists() and not (tmp_path / "second.dcd").exists()
    finally:
        gate.set()
        app.close()


# guide: every target drawn; the matrix step waits for an edit, the save step for a press
def test_the_guide_points_at_real_controls_and_waits(monkeypatch):
    from emtk import im

    app = RotateTranslateApp()
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys == {
            "trajectory",
            "topology",
            "rotation_matrix",
            "translation",
            "stride",
            "save",
            "log",
        }
        assert keys <= set(app.item_rects)
        steps = app.tour.steps
        index = next(
            i for i, s in enumerate(steps) if s.get("target", {}).get("name") == "rotation_matrix"
        )
        app.tour.start(index)
        assert app.tour.awaiting and steps[index]["title"] in " ".join(
            _draw(app, size, n=1).strings
        )
        original = im.input_text
        monkeypatch.setattr(
            im,
            "input_text",
            lambda label, v, *a, **k: (
                (True, "0.5") if label == "##r22" else original(label, v, *a, **k)
            ),
        )
        _draw(app, size, n=1)
        monkeypatch.setattr(im, "input_text", original)
        assert not app.tour.awaiting

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        for target, button in (("trajectory", "trajectory_browse"), ("save", "save")):
            index = next(
                i for i, s in enumerate(steps) if s.get("target", {}).get("name") == target
            )
            app.tour.start(index)
            assert app.tour.awaiting
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
    app = RotateTranslateApp()
    try:
        strings = _draw(app, size).strings
        assert {
            "Rotation matrix",
            "Translation [Ang.]",
            "💾  Save rotated/translated…",
            "Stride",
            "Log",
        } <= {s.strip() for s in strings}
        app = _loaded()
        app.save(str(tmp_path / "moved.dcd"))
        _settle(app)
        assert "Rotated/translated trajectory saved" in " ".join(_draw(app, size).strings)
        log = app.item_rects["log"]
        assert log[1] + log[3] <= size[1] + 1 and log[3] > 100
    finally:
        app.close()


def test_settings_round_trip():
    app = _loaded()
    other = RotateTranslateApp()
    other.restore_settings(json.loads(json.dumps(app.export_settings())))
    m = other.model
    assert (m.trajectory_filename, m.topology_filename, m.stride) == (TRAJ, TOP, STRIDE)
    assert (
        np.asarray(m.rotation_matrix).tolist() == R
        and np.asarray(m.translation_vector).tolist() == T
    )


def test_help_opens_with_its_page():
    app = RotateTranslateApp()
    app.show_help()
    assert app.help_window.open and "R x + t" in " ".join(_draw(app).strings)


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("traj_rotate_translate")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("traj_rotate_translate")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
