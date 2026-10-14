"""Every Energy Calc potential scores a real trajectory.

Six of the nine potentials used to fail on a trajectory: the frame was a plain
full-atom ``Structure`` while the contact, H-bond, Gō and ASA kernels need the
residue-level (centroid) structure, Ramachandran returned 0 for every frame, and
the accessible-volume entry was a stub. Each potential is run here through
:meth:`PotentialEnergyViewModel.process` on the T4L example trajectory, and the
numbers are checked against what the structure must give, not only for "no
exception".
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

_T4L = pathlib.Path(__file__).resolve().parents[3] / "modelling/fret/examples/olga_t4l"
_TOP = _T4L / "3GUN_NMSim_cl-rep-001.pdb"
_DCD = _T4L / "3GUN_NMSim_cl-rep_894.dcd"
_STRIDE = 200  # frames 0, 200, 400, 600, 800

pytestmark = pytest.mark.skipif(not _DCD.is_file(), reason="T4L example trajectory not present")


def _score(tmp_path, name, values=None, weight=1.0):
    """Run Energy Calc with the one potential *name*; return ``(frame numbers, energies, potential)``."""
    from chisurf.plugins.traj.potential_energy.potential_specs import make_potential
    from chisurf.plugins.traj.potential_energy.view_model import PotentialEnergyViewModel

    model = PotentialEnergyViewModel()
    model.set_trajectory(str(_DCD))
    model.set_topology(str(_TOP))
    model.stride = _STRIDE
    potential = make_potential(name, values or {})
    model.add_potential(potential, weight, name=name)
    out = tmp_path / f"{name.replace(' ', '_')}.txt"
    assert model.process(out) == 5
    table = np.loadtxt(out, skiprows=1, ndmin=2)
    return table[:, 0], table[:, 1], potential


def test_av_potential_is_not_offered():
    """The accessible-volume entry built a stub whose chi-squared was always 0."""
    from chisurf.plugins.traj.potential_energy.potential_specs import potential_names

    assert "AV-Potential" not in potential_names()
    assert len(potential_names()) == 8


def test_hbond(tmp_path):
    frames, energy, potential = _score(tmp_path, "H-Bond")
    assert list(frames) == [1, 201, 401, 601, 801]
    assert np.all(np.isfinite(energy))
    # T4L is mostly helical: about one backbone H-bond per residue (162).
    assert 120 < potential.nHbond < 220
    # Sequence neighbours are not paired: their peptide bond sat on the
    # repulsive core of the C-N term and gave ~5e4 per frame.
    assert np.all(np.abs(energy) < 1000.0)


def test_hbond_pair_terms_switch(tmp_path):
    """The OH/ON/CN/CH switches change the energy (getEnergy read the unswitched table)."""
    _, all_terms, _ = _score(tmp_path, "H-Bond")
    _, without_oh, _ = _score(tmp_path, "H-Bond", {"oh": False})
    assert not np.allclose(all_terms, without_oh)


def test_iso_unres(tmp_path):
    _, energy, potential = _score(tmp_path, "Iso-UNRES")
    assert np.all(np.isfinite(energy))
    assert potential.getNbrContacts() > 1000
    assert np.ptp(energy) > 0.0


def test_miyazawa_jernigan(tmp_path):
    _, energy, potential = _score(tmp_path, "Miyazawa-Jernigan")
    # A folded protein has many favourable side-chain contacts.
    assert np.all(energy < -500.0)
    assert potential.getNbrContacts() > 200


def test_go_native_is_the_first_frame(tmp_path):
    _, energy, _ = _score(tmp_path, "Go-Potential")
    assert np.all(np.isfinite(energy))
    # The native contacts are those of the first frame scored, so it is the minimum.
    assert np.argmin(energy) == 0
    assert np.all(energy[1:] > energy[0])


def test_asa_calpha(tmp_path):
    _, energy, _ = _score(tmp_path, "ASA-Calpha")
    # 162 C-alpha spheres of radius 2.5 + 1.0 Å: the buried ones hide most of it.
    total = 162 * 4.0 * np.pi * 3.5**2
    assert np.all((energy > 0.05 * total) & (energy < 0.6 * total))
    # Column 6 of the lookup (CG) used to be read: only PRO has it, so the area
    # was one constant sphere set for every frame.
    assert np.ptp(energy) > 10.0


def test_ramachandran(tmp_path):
    _, energy, potential = _score(tmp_path, "Ramachandran")
    # 160 residues have both phi and psi; helical and beta residues sit at -3 to -4.5.
    assert potential.n_scored == 160
    assert np.all(energy / potential.n_scored < -2.0)


def test_clash(tmp_path):
    _, energy, _ = _score(tmp_path, "Clash potential")
    assert np.all(np.isfinite(energy)) and np.all(energy >= 0.0)


def test_radius_of_gyration(tmp_path):
    _, energy, _ = _score(tmp_path, "Radius of Gyration", weight=2.0)
    # Weighted by 2; T4L's radius of gyration is 15-17 Å over the run.
    assert np.all((energy > 30.0) & (energy < 34.0))


def test_centroid_frame_map():
    """Centroids are the mass-weighted side-chain mean; placed H sit 1.01 Å from N."""
    import chisurf.core.structure
    from chisurf.core.structure import trajectory_data as md
    from chisurf.core.structure.protein import CentroidFrameMap, a2id, residue_atoms_internal

    full = chisurf.core.structure.TrajectoryFile(md.load_frame(str(_DCD), 0, top=str(_TOP)))[0]
    frame = next(iter(md.iterload(str(_DCD), stride=400, top=str(_TOP))))[1].xyz[0]
    mapping = CentroidFrameMap(full)
    centroid = mapping.set_frame(frame)
    assert centroid.residue_types.shape == (centroid.n_residues,) == (162,)

    atoms = full.atoms
    r = 10
    res_id = centroid.atoms[centroid.l_res[r, a2id["CA"]]]["res_id"]
    res_name = str(centroid.atoms[centroid.l_res[r, a2id["CA"]]]["res_name"])
    sel = np.where(atoms["res_id"] == res_id)[0]
    side = [
        i
        for i in sel
        if atoms[i]["atom_name"] == "CB"
        or atoms[i]["atom_name"] not in residue_atoms_internal[res_name]
    ]
    expected = np.average(frame[side], axis=0, weights=atoms["mass"][side])
    np.testing.assert_allclose(centroid.xyz[centroid.l_res[r, a2id["CB"]]], expected, atol=1e-5)

    n = centroid.l_res[r, a2id["N"]]
    h = centroid.l_res[r, a2id["H"]]
    assert h >= 0 and centroid.atoms[n]["atom_name"] == "N"
    assert np.linalg.norm(centroid.xyz[h] - centroid.xyz[n]) == pytest.approx(1.01, abs=1e-6)
    with pytest.raises(ValueError, match="atoms"):
        mapping.set_frame(frame[:-1])


def test_structure_copies_a_frame_structure():
    """``Structure(structure)`` failed for a structure built from a trajectory frame."""
    import chisurf.core.structure
    from chisurf.core.structure import trajectory_data as md

    frame = chisurf.core.structure.TrajectoryFile(md.load_frame(str(_DCD), 0, top=str(_TOP)))[0]
    copy = chisurf.core.structure.Structure(frame)
    assert copy.n_atoms == frame.n_atoms
