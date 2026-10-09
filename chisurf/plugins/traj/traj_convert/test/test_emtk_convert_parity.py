"""The native trajectory converter at parity with the Qt MDConverter widget.

The Qt widget runs in a subprocess (this process stays Qt-free) on the hgbp1 test
trajectory through its own sections: its answers (no trajectory, done, failed) and its
output are compared with the emtk app's, and every output against the frames selected
here from the source directly -- the range inclusive of its last frame, split and folder
modes included (the three conversions guide 81 listed as broken).
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

from chisurf.plugins.traj.traj_convert.app import MDConverterApp  # noqa: E402


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=120.0):
    end = time.monotonic() + timeout
    while app.running:
        assert time.monotonic() < end, "the conversion did not finish"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _messages(log):
    return [re.sub(r"^\[\d\d:\d\d:\d\d\] ", "", line) for line in log]


def _loaded(target, first=10, last=50, stride=10, **settings):
    app = MDConverterApp()
    m = app.model
    m.set_topology(TOP)
    m.set_trajectory(TRAJ)
    m.set_target_directory(str(target))
    m.first_frame, m.last_frame, m.stride, m.filename = first, last, stride, "frames"
    for key, value in settings.items():
        setattr(m, key, value)
    return app


def _run(app):
    app.begin_save()
    _settle(app)
    return app


@pytest.fixture(scope="module")
def source():
    from chisurf.core.structure import trajectory_data as md

    return np.asarray(md.load(TRAJ, top=TOP).xyz)


def _read(path, top=TOP):
    from chisurf.core.structure import trajectory_data as md

    return np.asarray(md.load(str(path), top=top).xyz)


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.traj.traj_convert import sections
from chisurf.plugins.traj.traj_convert.widget import MDConverter
traj, top, target = sys.argv[1:4]
told, errors = [], []
sections.dialogs.information = lambda parent, title, text: told.append([title, text])
sections.dialogs.error = lambda parent, title, text: errors.append([title, text])
w = MDConverter()
run = w.findChild(sections._RunSection)
run._convert()                                        # nothing chosen
m = w.model
m.set_topology(top); m.set_trajectory(traj); m.set_target_directory(target)
m.first_frame, m.last_frame, m.stride, m.filename = 10, 50, 10, "frames"
run._convert()
m.first_frame, m.last_frame = 100, 50                 # a range that selects nothing
run._convert()
print("FACTS" + json.dumps({"told": told, "errors": errors, "log": m._log}))
"""


@pytest.fixture(scope="module")
def qt(tmp_path_factory):
    pytest.importorskip("qtpy")
    target = tmp_path_factory.mktemp("qt")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, TRAJ, TOP, str(target)],
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


# 1. the Qt widget's output and answers; the range includes its last frame
def test_a_range_converts_as_the_qt_widget_does_and_keeps_its_last_frame(qt, source, tmp_path):
    app = _run(_loaded(tmp_path))
    try:
        ours, theirs = _read(tmp_path / "frames.dcd"), _read(qt["target"] / "frames.dcd")
        np.testing.assert_allclose(ours, source[[10, 20, 30, 40, 50]], atol=1e-3)  # 50 included now
        np.testing.assert_allclose(ours, theirs, atol=1e-4)
        assert app.notice == "Conversion done!" == qt["told"][-1][1]
        assert "Wrote 5 frames of 5235 atoms" in _messages(app.model.log_text())
        assert "Wrote 5 frames of 5235 atoms" in _messages(qt["log"])
    finally:
        app.close()


def test_last_frame_minus_one_reaches_the_end(source, tmp_path):
    app = _run(_loaded(tmp_path, first=460, last=-1, stride=1))
    try:
        np.testing.assert_allclose(_read(tmp_path / "frames.dcd"), source[460:464], atol=1e-3)
    finally:
        app.close()


def test_split_writes_one_pdb_per_selected_frame_named_by_its_source_frame(source, tmp_path):
    app = _run(_loaded(tmp_path, first=0, last=-1, stride=100, split=True, ending=".pdb"))
    try:
        names = sorted(p.name for p in tmp_path.glob("frames_*.pdb"))
        assert names == [
            f"frames_{i:08d}.pdb" for i in (0, 100, 200, 300, 400)
        ]  # the stride is honoured
        for i in (0, 400):
            np.testing.assert_allclose(
                _read(tmp_path / f"frames_{i:08d}.pdb", top=None)[0], source[i], atol=1e-3
            )
        assert app.notice == "Conversion done!"
    finally:
        app.close()


def test_a_multi_frame_pdb_holds_one_model_per_frame(source, tmp_path):
    app = _run(_loaded(tmp_path, first=0, last=20, stride=10, ending=".pdb"))
    try:
        text = (tmp_path / "frames.pdb").read_text()
        models = [block for block in text.split("ENDMDL") if "ATOM" in block or "HETATM" in block]
        assert len(models) == 3
        # Read here from the fixed PDB columns: trajectory_data.load takes a structure file as one frame
        # (known issue), so it cannot be the reference for a multi-model file.
        xyz = np.array(
            [
                [
                    [float(line[30:38]), float(line[38:46]), float(line[46:54])]
                    for line in block.splitlines()
                    if line.startswith(("ATOM", "HETATM"))
                ]
                for block in models
            ]
        )
        np.testing.assert_allclose(xyz, source[[0, 10, 20]], atol=1e-3)
    finally:
        app.close()


def test_a_folder_of_pdbs_is_read_as_consecutive_frames(source, tmp_path):
    from chisurf.core.structure import trajectory_data as md

    folder = tmp_path / "pdbs"
    folder.mkdir()
    trajectory = md.load(TRAJ, top=TOP)
    for name, index in (("a.pdb", 5), ("b.pdb", 50), ("c.pdb", 400)):
        trajectory[index].save_pdb(str(folder / name))
    out = tmp_path / "out"
    out.mkdir()
    app = MDConverterApp()
    try:
        app.model.use_folder = True
        trajectory_row = next(p for p in app.paths if p.key == "trajectory")
        app.browse(trajectory_row)
        assert app.dialog.mode == "folder"  # the row follows the toggle
        app.dialog.draw = lambda: [str(folder)]
        _draw(app, n=1)
        assert app.model.trajectory == str(folder)
        app.model.set_target_directory(str(out))
        app.model.filename = "joined"
        _run(app)
        np.testing.assert_allclose(_read(out / "joined.dcd"), source[[5, 50, 400]], atol=1e-3)
        assert "Read 3 files as 3 frames" in _messages(app.model.log_text())
    finally:
        app.close()


# 2. actions and errors, in the Qt widget's words
def test_nothing_chosen_and_a_failure_answer_as_the_qt_widget_does(qt, tmp_path):
    app = MDConverterApp()
    try:
        app.begin_save()
        assert [app.status] == [qt["told"][0][1]] == ["Choose a trajectory first."]
        app.model.set_trajectory(TRAJ)
        app.begin_save()
        assert (
            app.status == "Choose a target folder first." and not app.running
        )  # never into the cwd
        app = _loaded(tmp_path, first=100, last=50)
        _run(app)
        [(title, text)] = qt["errors"]
        assert title == "Conversion failed" and app.status == f"Conversion failed: {text}"
        assert app.status == "Conversion failed: The frame range selects no frames."
        assert _draw(app).strings.count(app.status) == 1  # shown, and once
    finally:
        app.close()


# 3. the spec's fields are drawn with their descriptions and write the model
def test_every_spec_field_is_drawn_with_its_description(monkeypatch):
    from emtk import im, im_widgets
    from emtk.view_form import _commit

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)
    spec = json.loads((HERE.parent / "convert_structures.view.json").read_text())
    fields = [s for panel in spec["sections"] for s in panel.get("sections", []) if s.get("attr")]
    app = MDConverterApp()
    try:
        _draw(app)
        names = {"use_folder", "first_frame", "last_frame", "stride", "filename", "ending", "split"}
        assert {f["attr"] for f in fields} == names and names <= set(app.form.rects)
        assert all(f["description"] in tips for f in fields)
        assert {"Input.fold", "Output.fold"} <= set(app.form.rects)  # the panels fold, as in Qt
        _commit(app.model, next(f for f in fields if f["attr"] == "ending"), ".pdb", app.form)
        assert app.model.ending == ".pdb" and app.export_settings()["ending"] == ".pdb"
    finally:
        app.close()


def test_frames_are_requested_and_the_form_disabled_while_converting(monkeypatch, tmp_path):
    import threading

    from chisurf.plugins.traj.traj_convert import view_model

    gate = threading.Event()
    runs = []
    original = view_model.MDConverterViewModel.convert
    monkeypatch.setattr(
        view_model.MDConverterViewModel,
        "convert",
        lambda self: (runs.append(1), gate.wait(10), original(self))[2],
    )
    app = _loaded(tmp_path)
    try:
        app.begin_save()
        assert app.running and app.animating() and "Working…" in _draw(app).strings
        app.begin_save()  # a second press while busy is ignored
        gate.set()
        _settle(app)
        time.sleep(0.3)  # a queued second run would have started by now
        assert app.notice == "Conversion done!" and not app.animating() and len(runs) == 1
    finally:
        gate.set()
        app.close()


def test_drops_fill_the_trajectory_and_target_rows(tmp_path):
    app = MDConverterApp()
    try:
        app.on_paths_dropped([TRAJ, TOP, str(tmp_path)])
        m = app.model
        assert (m.trajectory, m.topology_path, m.target_directory) == (TRAJ, TOP, str(tmp_path))
    finally:
        app.close()


# guide: every target drawn; the file and convert steps wait for presses
def test_the_guide_points_at_real_controls_and_waits():
    app = MDConverterApp()
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys == {
            "topology",
            "trajectory",
            "use_folder",
            "target",
            "first_frame",
            "split",
            "convert",
            "log",
        }
        assert keys <= set(app.item_rects)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        steps = app.tour.steps
        for target, button in (("target", "target_browse"), ("convert", "convert")):
            index = next(
                i for i, s in enumerate(steps) if s.get("target", {}).get("name") == target
            )
            app.tour.start(index)
            assert app.tour.awaiting and steps[index]["title"] in " ".join(
                _draw(app, size, n=1).strings
            )
            _draw(app, size, n=1, painter=PixelPainter)
            press(button)
            assert not app.tour.awaiting, target
            app.dialog = None
        assert app.status == "Choose a trajectory first."
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size, tmp_path):
    app = MDConverterApp()
    try:
        strings = _draw(app, size).strings
        assert {
            "Topology",
            "Trajectory",
            "Target folder",
            "▶ Convert",
            "Log",
            "Input",
            "Output",
        } <= {s.strip() for s in strings}
        app = _run(_loaded(tmp_path))
        strings = _draw(app, size).strings
        assert "Conversion done!" in strings
        assert any(
            line.endswith("Wrote 5 frames of 5235 atoms") for line in strings
        )  # the log is drawn
        log = app.item_rects["log"]
        assert log[1] + log[3] <= size[1] + 1 and log[3] > 80
    finally:
        app.close()


def test_settings_round_trip(tmp_path):
    app = _loaded(tmp_path, split=True, ending=".pdb")
    other = MDConverterApp()
    other.restore_settings(json.loads(json.dumps(app.export_settings())))
    m = other.model
    assert (
        m.trajectory,
        m.topology_path,
        m.target_directory,
        m.first_frame,
        m.last_frame,
        m.stride,
        m.split,
        m.ending,
    ) == (TRAJ, TOP, str(tmp_path), 10, 50, 10, True, ".pdb")


def test_help_opens_with_its_page():
    app = MDConverterApp()
    app.show_help()
    assert app.help_window.open and "up to and including" in " ".join(_draw(app).strings)


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("traj_convert")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("traj_convert")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
