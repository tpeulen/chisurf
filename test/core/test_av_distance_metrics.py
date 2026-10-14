"""``BasicAV`` distances read the right slot of ``IMP.bff.av_pair_statistics``.

The kernel returns ``(R_mp, <R_DA>, <R_DA>_E, sigma_R)``. ``BasicAV.dRDA`` read slot 0
and so returned R_mp under the name <R_DA> (40.44 A on 148L 27/95 CA, where the
pair sample gives 44.12 A) until 2026-10-14. Found while reviewing the
accessible-volume guide, whose numbers came from it.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

PDB = pathlib.Path(__file__).resolve().parents[1] / "data/atomic_coordinates/pdb_files/148l.pdb"


@pytest.fixture(scope="module")
def pair():
    pytest.importorskip("IMP.bff")
    from chisurf.core.structure import Structure
    from chisurf.core.structure.av import BasicAV

    structure = Structure(filename=str(PDB))
    kw = dict(linker_length=20.5, linker_width=1.5, radius1=3.5, simulation_type="AV1")
    donor = BasicAV(structure, residue_seq_number=27, atom_name="CA", **kw)
    acceptor = BasicAV(structure, residue_seq_number=95, atom_name="CA", **kw)
    return donor, acceptor


def test_mean_distance_is_the_pair_sample_mean_not_rmp(pair):
    donor, acceptor = pair
    distances, weights = donor._pair_sample(acceptor)
    sample_mean = float(np.dot(distances, weights) / weights.sum())
    assert donor.dRDA(acceptor) == pytest.approx(sample_mean, abs=1e-6)
    assert abs(donor.dRDA(acceptor) - donor.dRmp(acceptor)) > 1.0


def test_the_three_distances_are_ordered(pair):
    """R_mp < <R_DA> (Jensen, for overlapping clouds) and <R_DA>_E > <R_DA> here (R0 = 52 A)."""
    donor, acceptor = pair
    rmp, rda, rda_e = donor.dRmp(acceptor), donor.dRDA(acceptor), donor.dRDAE(acceptor, 52.0)
    assert rmp < rda < rda_e
