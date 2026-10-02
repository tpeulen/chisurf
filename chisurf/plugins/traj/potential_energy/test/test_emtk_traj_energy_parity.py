"""The native potential-energy app at parity with the Qt PotentialEnergyWidget.

The Qt facts (energies written by its model, the potential files its editors show)
come from a subprocess; this process stays Qt-free. IMP-backed potentials need
``modules/imp-tricks/src`` on the path (``IMP.cgmol``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.traj.potential_energy.app import make_app
from chisurf.plugins.traj.potential_energy.potential_specs import get_spec, make_potential

from .test_view_model import _peptide_trajectory

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
POTENTIALS = [("Radius of Gyration", 1.0), ("Clash potential", 0.5)]

_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
import chisurf.gui.widgets
from chisurf.plugins.traj.potential_energy.widget import PotentialEnergyWidget
from chisurf.plugins.traj.potential_energy.potential_specs import make_potential
dcd, pdb, out, potentials = sys.argv[1], sys.argv[2], sys.argv[3], json.loads(sys.argv[4])
w = PotentialEnergyWidget()
w.model.set_trajectory(dcd); w.model.set_topology(pdb)
for name, weight in potentials:
    w.model.add_potential(make_potential(name, {}), weight, name=name)
w.model.process(out)
editors = chisurf.gui.widgets.structure.potentialDict
files = {}
# the path each editor shows in its file field (its `potential` property is the loaded table)
for name, field in (("H-Bond", "lineEdit_3"), ("Iso-UNRES", "lineEdit"), ("Miyazawa-Jernigan", "lineEdit")):
    editor = editors[name](structure=None, parent=None)
    files[name] = getattr(editor, field).text()
print("FACTS" + json.dumps({"energies": open(out).read(), "files": files}))
"""


@pytest.fixture(scope="module")
def trajectory(tmp_path_factory):
    pytest.importorskip("IMP.cgmol")
    tmp = tmp_path_factory.mktemp("traj")
    dcd = tmp / "pep.dcd"
    pdb = _peptide_trajectory(str(dcd))
    return str(dcd), pdb, tmp


@pytest.fixture(scope="module")
def qt(trajectory):
    pytest.importorskip("qtpy")
    dcd, pdb, tmp = trajectory
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, dcd, pdb, str(tmp / "qt.txt"), json.dumps(POTENTIALS)],
                          capture_output=True, text=True, timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt widget's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS"):])


def _wait(app, timeout=60.0):
    end = time.monotonic() + timeout
    while app.running and time.monotonic() < end:
        app.draw(RecordingPainter(), 0, 0, 800, 700)
        time.sleep(0.01)
    assert not app.running


# 1. the Process button writes the Qt tool's energies (on a worker)
def test_process_writes_the_qt_tools_energies(qt, trajectory):
    dcd, pdb, tmp = trajectory
    app = make_app()
    try:
        app.model.set_trajectory(dcd)
        app.model.set_topology(pdb)
        for name, weight in POTENTIALS:
            app.model.add_potential(make_potential(name, {}), weight, name=name)
        target = str(tmp / "emtk.txt")
        app.save(target)
        assert app.running
        app.save(str(tmp / "second.txt"))               # one run at a time
        _wait(app)
        assert app.notice == "Processed 4 frame(s)." and app.frames_done >= 1
        assert open(target).read() == qt["energies"]
        assert not (tmp / "second.txt").exists()
    finally:
        app.close()


# 2. the potential files the Qt editors expose, with the same defaults
def test_potential_files_match_the_qt_editors(qt):
    for name, path in qt["files"].items():
        params = {p.attr: p for p in get_spec(name).params if p.kind == "file"}
        assert params, name
        (param,) = params.values()
        assert Path(param.default) == Path(path), name


# 3. the browse buttons and the save dialog Process opens
def test_browse_and_process_ask_for_files(trajectory):
    dcd, pdb, tmp = trajectory
    app = make_app()
    try:
        trajectory_row = next(p for p in app.paths if p.key == "trajectory")
        app.browse(trajectory_row)
        assert app.dialog is not None and app.dialog.mode == "open" and app.dialog.title == "Open trajectory"
        app.dialog = None
        app.model.set_trajectory(dcd)
        app.model.set_topology(pdb)
        app.model.add_potential(make_potential("Radius of Gyration", {}), 1.0, name="Radius of Gyration")
        app.begin_save()
        assert app.dialog.mode == "save" and app.dialog.title == "Save energies"
        assert app.dialog.filters[0] == ("CSV-name file", ["*.txt"])         # the Qt dialog's filter
    finally:
        app.close()


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws(size):
    app = make_app()
    try:
        painter = RecordingPainter()
        for _ in range(2):
            painter = RecordingPainter()
            app.draw(painter, 0, 0, *size)
        assert "Process" in painter.strings
    finally:
        app.close()


def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("traj_energy_calculator")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("traj_energy_calculator")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
