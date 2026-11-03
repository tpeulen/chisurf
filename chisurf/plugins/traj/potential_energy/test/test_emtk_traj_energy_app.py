"""The native potential-energy app on a small random peptide trajectory.

The radius-of-gyration column written by Process is checked against
``sqrt(mean |r_i - r_mean|^2)`` computed here from the frames. IMP-backed potentials
need ``modules/imp-tricks/src`` on the path (``IMP.cgmol``).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.traj.potential_energy.app import make_app
from chisurf.plugins.traj.potential_energy.potential_specs import get_spec, make_potential

from .test_view_model import _peptide_trajectory

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
POTENTIALS = [("Radius of Gyration", 1.0), ("Clash potential", 0.5)]


@pytest.fixture(scope="module")
def trajectory(tmp_path_factory):
    pytest.importorskip("IMP.cgmol")
    tmp = tmp_path_factory.mktemp("traj")
    dcd = tmp / "pep.dcd"
    pdb = _peptide_trajectory(str(dcd))
    return str(dcd), pdb, tmp


def check_energies(target, dcd, pdb):
    """Check the energies file at *target*: one row per frame, the radius of gyration computed here.

    The radius of gyration is ``sqrt(mean |r_i - r_mean|^2)`` of each frame's coordinates (column
    ``Radius-Gyration``, weight 1); the clash column only has to be non-negative, since its value
    depends on the van-der-Waals radii the environment provides.
    """
    from chisurf.core.structure import trajectory_data as md

    header, *rows = [line.split("\t") for line in Path(target).read_text().splitlines()]
    assert [h for h in header if h] == ["FrameNbr", "Radius-Gyration", "Clash-Potential"]
    xyz = np.asarray(md.load(str(dcd), top=str(pdb)).xyz, dtype=float)
    centred = xyz - xyz.mean(axis=1, keepdims=True)
    rg = np.sqrt((centred**2).sum(axis=2).mean(axis=1))
    assert [int(row[0]) for row in rows] == list(range(1, len(xyz) + 1))
    assert [float(row[1]) for row in rows] == pytest.approx(rg, abs=6e-4)
    assert all(float(row[2]) >= 0.0 for row in rows)


def _wait(app, timeout=60.0):
    end = time.monotonic() + timeout
    while app.running and time.monotonic() < end:
        app.draw(RecordingPainter(), 0, 0, 800, 700)
        time.sleep(0.01)
    assert not app.running


# 1. the Process button writes one row of energies per frame (on a worker)
def test_process_writes_the_radius_of_gyration_of_every_frame(trajectory):
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
        app.save(str(tmp / "second.txt"))  # one run at a time
        _wait(app)
        assert app.notice == "Processed 4 frame(s)." and app.frames_done >= 1
        check_energies(target, dcd, pdb)
        assert not (tmp / "second.txt").exists()
    finally:
        app.close()


# 2. the knowledge-based potentials default to the tables shipped with chisurf
@pytest.mark.parametrize(
    "name, table", [("H-Bond", "hb.npy"), ("Iso-UNRES", "unres.npy"), ("Miyazawa-Jernigan", "mj.npy")]
)
def test_potential_files_default_to_the_shipped_tables(name, table):
    params = [p for p in get_spec(name).params if p.kind == "file"]
    assert len(params) == 1, name
    default = Path(params[0].default)
    assert default == REPO / "chisurf" / "core" / "structure" / "potential" / "database" / table
    assert default.is_file()


# 3. the browse buttons and the save dialog Process opens
def test_browse_and_process_ask_for_files(trajectory):
    dcd, pdb, tmp = trajectory
    app = make_app()
    try:
        trajectory_row = next(p for p in app.paths if p.key == "trajectory")
        app.browse(trajectory_row)  # an input row: no dialog, the workspace fills it
        assert app.dialog is None
        app.model.set_trajectory(dcd)
        app.model.set_topology(pdb)
        app.model.add_potential(
            make_potential("Radius of Gyration", {}), 1.0, name="Radius of Gyration"
        )
        app.begin_save()
        assert app.dialog.mode == "save" and app.dialog.title == "Save energies"
        assert app.dialog.filters[0] == ("CSV-name file", ["*.txt"])
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
