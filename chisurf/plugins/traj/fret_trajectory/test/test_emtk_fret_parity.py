"""The native Trajectory→FRET at parity with the Qt Structure2Transfer tool.

The Qt tool runs in a subprocess (this process stays Qt-free) on the hgbp1 test
trajectory with the same dipole atoms: its pickers' choice and its table are compared
with the emtk app's, and the table against distances, κ² and rates computed here from
the coordinates (the rate as 3/2 κ² (R0/R)⁶ / τ0).
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
from emtk.testing import PixelPainter, RecordingPainter

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
DATA = REPO / "test" / "data" / "atomic_coordinates" / "trajectory" / "hgbp1"
TRAJ, TOP = str(DATA / "hgbp1_transition.dcd"), str(DATA / "topol.pdb")
DONOR, ACCEPTOR = (1, 20), (3000, 3010)
R0, TAU0, STRIDE = 52.0, 4.0, 4

from chisurf.plugins.traj.fret_trajectory.app import FretTrajectoryApp  # noqa: E402


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _settle(app, timeout=120.0):
    end = time.monotonic() + timeout
    while app.running:
        assert time.monotonic() < end, "processing did not finish"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _loaded(dipoles=True):
    app = FretTrajectoryApp()
    m = app.model
    m.set_trajectory(TRAJ)                    # before the topology: it must still end with atoms to pick
    m.set_topology(TOP)
    m.stride, m.forster_radius, m.tau0, m.t_step, m.dipoles = STRIDE, R0, TAU0, 1.0, dipoles
    m.donor, m.acceptor = DONOR, ACCEPTOR
    return app


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.traj.fret_trajectory import sections
from chisurf.plugins.traj.fret_trajectory.gui import Structure2Transfer
traj, top, target = sys.argv[1:4]
told = []
sections.dialogs.information = lambda parent, title, text: told.append([title, text])
w = Structure2Transfer()
m = w.model
w.model.run_section.run()                             # nothing chosen
io = w.findChild(sections._TrajectoryIoSection)
io._load_topology(top); io._load(traj)                 # the topology row now exists in the Qt tool too
m.stride, m.forster_radius, m.tau0, m.t_step, m.dipoles = 4, 52.0, 4.0, 1.0, True
pairs = m.atom_pair_section
pairs.set_donor(1, 20); pairs.set_acceptor(3000, 3010)
labels = [[s.chain_combo.currentText(), s.residue_combo.currentText(), s.atom_combo.currentText()]
          for s in (pairs.d1, pairs.d2, pairs.a1, pairs.a2)]
result = m.run_section.run(target)
print("FACTS" + json.dumps({"told": told, "labels": labels, "rows": result.tolist(), "log": m._log}))
"""


@pytest.fixture(scope="module")
def qt(tmp_path_factory):
    pytest.importorskip("qtpy")
    target = tmp_path_factory.mktemp("qt") / "fret.csv"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, TRAJ, TOP, str(target)], capture_output=True, text=True,
                          timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt tool's: a skip here once hid a broken topology row.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    facts = json.loads(line[len("FACTS"):])
    facts["target"] = target
    return facts


@pytest.fixture(scope="module")
def reference():
    """Dipole-centre distance, κ and the rate for every 4th frame, from the coordinates."""
    from chisurf.core.structure import trajectory_data as md

    xyz = np.asarray(md.load(TRAJ, top=TOP, stride=STRIDE).xyz, dtype=float)
    d1, d2, a1, a2 = (xyz[:, i] for i in (*DONOR, *ACCEPTOR))
    dd, da = d2 - d1, a2 - a1
    rda = (a1 + a2) / 2 - (d1 + d2) / 2
    r = np.linalg.norm(rda, axis=1)
    unit = lambda v: v / np.linalg.norm(v, axis=1)[:, None]  # noqa: E731
    ud, ua, ur = unit(dd), unit(da), unit(rda)
    kappa = np.sum(ud * ua, 1) - 3 * np.sum(ud * ur, 1) * np.sum(ua * ur, 1)
    rate = 1.5 * kappa ** 2 * (R0 / r) ** 6 / TAU0
    return r, kappa, rate


# 1. the Qt tool's pickers and table; the table is the physics
def test_processing_writes_what_the_qt_tool_writes(qt, reference, tmp_path):
    app = _loaded()
    try:
        _draw(app)
        index = app.atom_index()
        labels = [[*map(str, index.where(i)), index.name(i)] for i in (*DONOR, *ACCEPTOR)]
        assert labels == qt["labels"] == [["A", "1", "CA"], ["A", "3", "C"], ["B", "332", "HA"], ["B", "334", "CA"]]
        app.begin_save()
        assert app.dialog.title == "Output-file" and app.dialog.filename == "hgbp1_transition_fret.csv"
        target = tmp_path / "fret.csv"
        app.dialog.draw = lambda: [str(target)]
        _draw(app, n=1)                                   # the pick starts the worker
        assert app.dialog is None and app.running
        _settle(app)
        ours = np.loadtxt(target, skiprows=1)
        theirs = np.asarray(qt["rows"])
        assert ours.shape == theirs.shape == (116, 6)
        np.testing.assert_allclose(ours, theirs, rtol=1e-3, atol=1e-2)
        r, kappa, rate = reference
        np.testing.assert_allclose(ours[:, 0], np.arange(116) * STRIDE)          # frame numbers
        np.testing.assert_allclose(ours[:, 2], r, atol=0.01)                      # RDA, the dipole centres
        np.testing.assert_allclose(np.abs(ours[:, 3]), np.abs(kappa), rtol=1e-3, atol=1e-3)
        np.testing.assert_allclose(ours[:, 5], rate, rtol=2e-3)
        assert app.model.log_text()[-1].endswith("(116 frames)")
    finally:
        app.close()


def test_without_dipoles_the_first_atoms_and_two_thirds(tmp_path):
    from chisurf.core.structure import trajectory_data as md

    app = _loaded(dipoles=False)
    try:
        app.save(str(tmp_path / "iso.csv"))
        _settle(app)
        table = np.loadtxt(tmp_path / "iso.csv", skiprows=1)
        xyz = np.asarray(md.load(TRAJ, top=TOP, stride=STRIDE).xyz, dtype=float)
        r = np.linalg.norm(xyz[:, ACCEPTOR[0]] - xyz[:, DONOR[0]], axis=1)
        np.testing.assert_allclose(table[:, 2], r, atol=0.01)
        np.testing.assert_allclose(table[:, 4], 2 / 3, rtol=1e-3)
    finally:
        app.close()


# 2. either order of choosing the files; actions and errors in the Qt words
def test_the_trajectory_may_come_before_its_topology():
    app = FretTrajectoryApp()
    try:
        trajectory, topology = app.paths
        assert app.set_path(trajectory, TRAJ)                 # used to raise: a DCD cannot be read alone
        assert app.model.pdb is None and "choose the topology" in app.model.log_text()[-1]
        assert "Choose the trajectory and its topology to pick the atoms." in _draw(app).strings
        assert app.set_path(topology, TOP)
        assert app.model.pdb is not None and len(app.model.pdb) == 5235
    finally:
        app.close()


def test_nothing_chosen_and_a_cancel_answer_as_the_qt_tool_does(qt, tmp_path):
    app = FretTrajectoryApp()
    try:
        app.begin_save()
        assert [app.status] == [text for _title, text in qt["told"]] == ["Open a trajectory first."]
        app = _loaded()
        app.begin_save()
        app.dialog.draw = lambda: False
        _draw(app, n=1)
        assert app.dialog is None and app.model.log_text()[-1].endswith("Process cancelled")
    finally:
        app.close()


def test_a_failure_is_reported_as_processing_failed(tmp_path):
    app = _loaded()
    try:
        app.save(str(tmp_path / "missing" / "bad.csv"))         # a folder that does not exist
        _settle(app)
        assert app.status.startswith("Processing failed: ") and app.status in _draw(app).strings
    finally:
        app.close()


# the cascading pickers write the model
def test_the_pickers_cascade_chain_residue_atom(monkeypatch):
    from emtk import im

    app = _loaded()
    try:
        _draw(app)
        original = im.combo
        index = app.atom_index()
        picks = {"##acceptor1.residue": index.residues["B"].index(300)}
        monkeypatch.setattr(im, "combo", lambda label, current, items, *a, **k: (True, picks[label]) if label in picks
                            else original(label, current, items, *a, **k))
        _draw(app, n=1)
        monkeypatch.setattr(im, "combo", original)
        new = app.model.acceptor[1]
        assert index.where(new) == ("B", 300) and new == index.atoms("B", 300)[0]          # first atom of residue
        assert app.model.acceptor[0] == ACCEPTOR[0] and app.model.donor == DONOR
    finally:
        app.close()


# 3. the spec's fields are drawn with their descriptions
def test_every_spec_field_is_drawn_with_its_description(monkeypatch):
    from emtk import im, im_widgets

    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    monkeypatch.setattr(im_widgets, "set_item_tooltip", tips.append)
    spec = json.loads((HERE.parent / "structure2transfer.view.json").read_text())
    fields = [s for panel in spec["sections"] for s in panel.get("sections", []) if s.get("attr")]
    app = FretTrajectoryApp()
    try:
        _draw(app)
        names = {"stride", "forster_radius", "tau0", "t_step", "dipoles"}
        assert {f["attr"] for f in fields} == names and names <= set(app.form.rects)
        assert all(f["description"] in tips for f in fields)
    finally:
        app.close()


def test_frames_are_requested_while_processing(monkeypatch, tmp_path):
    import threading

    from chisurf.plugins.traj.fret_trajectory import view_model

    gate = threading.Event()
    runs = []
    original = view_model.FretTrajectoryViewModel.calc
    monkeypatch.setattr(view_model.FretTrajectoryViewModel, "calc",
                        lambda self, output_file, **k: (runs.append(1), gate.wait(10), original(self, output_file))[2])
    app = _loaded()
    try:
        app.save(str(tmp_path / "a.csv"))
        assert app.running and app.animating() and "Working…" in _draw(app).strings
        app.save(str(tmp_path / "b.csv"))
        gate.set()
        _settle(app)
        time.sleep(0.2)
        assert len(runs) == 1 and not (tmp_path / "b.csv").exists()
    finally:
        gate.set()
        app.close()


# guide: every target drawn; the file and process steps wait for presses
def test_the_guide_points_at_real_controls_and_waits():
    app = _loaded()
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)
        keys = {app.tour._target_key(s.get("target")) for s in app.tour.steps} - {""}
        assert keys == {"trajectory", "topology", "donor", "acceptor", "dipoles", "process", "log"}
        assert keys <= set(app.item_rects)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        steps = app.tour.steps
        for target, button in (("topology", "topology_browse"), ("process", "process")):
            index = next(i for i, s in enumerate(steps) if s.get("target", {}).get("name") == target)
            app.tour.start(index)
            assert app.tour.awaiting and steps[index]["title"] in " ".join(_draw(app, size, n=1).strings)
            _draw(app, size, n=1, painter=PixelPainter)
            press(button)
            assert not app.tour.awaiting, target
            assert app.dialog is not None
            app.dialog = None
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(size, tmp_path):
    app = FretTrajectoryApp()
    try:
        strings = _draw(app, size).strings
        assert {"Trajectory", "Topology", "Reference", "Dipole atoms", "▶ Process trajectory", "Log"} <= set(strings)
        app = _loaded()
        app.save(str(tmp_path / "fret.csv"))
        _settle(app)
        strings = _draw(app, size).strings
        assert {"Donor", "Acceptor", "CA", "HA", "332"} <= set(strings)
        assert [strings.count(c) for c in ("Chain", "Residue", "Atom")] == [2, 2, 2]  # both columns captioned
        assert any(line.endswith("(116 frames)") for line in strings)            # the log is drawn
        for attr in ("donor", "acceptor"):
            x, y, w, h = app.item_rects[attr]
            assert x + w <= size[0] + 0.5
    finally:
        app.close()


def test_settings_round_trip():
    app = _loaded()
    other = FretTrajectoryApp()
    other.restore_settings(json.loads(json.dumps(app.export_settings())))
    m = other.model
    assert (m.trajectory_file, m.topology_filename, m.donor, m.acceptor, m.stride) == (TRAJ, TOP, DONOR, ACCEPTOR, STRIDE)
    assert m.pdb is not None and m._engine.topology_file == TOP              # ready to process, atoms to pick


def test_help_opens_with_its_page():
    app = FretTrajectoryApp()
    app.show_help()
    assert app.help_window.open and "dipole centres" in " ".join(_draw(app).strings)


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("traj_fret")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("traj_fret")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
