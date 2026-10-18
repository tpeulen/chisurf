"""Tests for ChiMOL 3D biomolecule display and labeling site rendering in QuEst."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.microscopy.imaging_emtk.testing import hermetic_env
from chisurf.plugins.quenching_estimator.gui.app import make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

SIZE = (1200, 800)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def pdb(tmp_path):
    src = Path(__file__).resolve().parent / "148l.pdb"
    return Path(shutil.copy(src, tmp_path / "148l.pdb"))


@pytest.fixture
def app():
    application = make_app()
    assert application.session.ready, application.session.error
    yield application
    application.close()


def test_quest_uses_chimol_for_3d_biomolecule_and_labeling_sites(app, pdb):
    """QuEst renders the loaded macromolecule in ChiMOL with 3D donor/acceptor site spheres."""
    ui = Ui(app, SIZE)
    ui.draw(3)
    app.session.load_structure(str(pdb))

    # Switch to 3D Structure tab
    ui.press_text("3D Structure")
    ui.draw(3)

    viewer = app.chimol.viewer
    if viewer is None:
        pytest.skip(f"ChiMOL offscreen viewer unavailable in this environment: {app.chimol.error}")

    # Verify ChiMOL loaded the PDB structure
    objs = viewer.list_objects()
    assert len(objs) >= 1
    assert any("148l" in str(obj.get("source_path", "")) or "148l" in str(obj.get("name", "")) for obj in objs)

    # Verify donor sphere overlay is placed in ChiMOL
    overlays = getattr(viewer, "_point_overlays", {})
    assert "donor" in overlays
    assert overlays["donor"]["glyph"] == "sphere"
    assert overlays["donor"]["label"] == "Donor"

    # Now enable FRET and pick an acceptor residue
    ui.click("pick_acceptor")
    ui.click("res.E.5")
    ui.draw(3)

    overlays = getattr(viewer, "_point_overlays", {})
    assert "donor" in overlays
    assert "acceptor" in overlays
    assert overlays["acceptor"]["glyph"] == "sphere"
    assert overlays["acceptor"]["label"] == "Acceptor"


def test_clicking_atom_in_chimol_picks_attachment_residue(app, pdb):
    """Selecting an atom in ChiMOL updates the QuEst attachment residue."""
    ui = Ui(app, SIZE)
    ui.draw(3)
    app.session.load_structure(str(pdb))
    ui.press_text("3D Structure")
    ui.draw(3)

    viewer = app.chimol.viewer
    if viewer is None or not hasattr(viewer, "atomSelectionChanged"):
        pytest.skip("ChiMOL viewer not available")

    # Target donor, pick atom index 10 (which corresponds to residue 2 in 148l)
    atoms = app.session.structure.atoms
    target_chain = str(atoms["chain"][10])
    target_res = int(atoms["res_id"][10])

    # Simulate ChiMOL 3D atom pick signal
    viewer.atomSelectionChanged.emit([10])
    ui.draw(2)

    att = app.session.model.project["attachment"]
    assert att["chain"] == target_chain
    assert att["residue"] == target_res
