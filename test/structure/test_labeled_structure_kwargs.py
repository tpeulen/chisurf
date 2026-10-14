"""Keyword plumbing of the labelled-structure helpers and the AV parameter groups."""

from __future__ import annotations

import numpy as np

PDB = "./test/data/atomic_coordinates/pdb_files/hGBP1_closed.pdb"


def test_fret_rate_spectrum_reads_kappa2_from_its_own_key():
    """The FRET rate is proportional to kappa^2 at a fixed Foerster radius.

    ``kappa2`` was read from the ``forster_radius`` key, so a caller's
    orientation factor was ignored (and a Foerster radius of ~50 A used as one).
    Halving kappa^2 must halve every rate.
    """
    import chisurf.core.structure
    import chisurf.core.structure.labeled_structure as labeled

    structure = chisurf.core.structure.Structure(PDB)
    donor = {"residue_seq_number": 18, "atom_name": "CB"}
    acceptor = {"residue_seq_number": 577, "atom_name": "CB"}
    common = dict(forster_radius=52.0, interleave=False)
    full = labeled.av_fret_rate_spectrum(structure, donor, acceptor, kappa2=2 / 3, **common)
    half = labeled.av_fret_rate_spectrum(structure, donor, acceptor, kappa2=1 / 3, **common)
    rates_full = np.asarray(full)[0, 1]
    rates_half = np.asarray(half)[0, 1]
    assert rates_full.max() > 0.0
    np.testing.assert_allclose(rates_half, 0.5 * rates_full, rtol=1e-10)


def test_sticking_keeps_the_fit_out_of_its_parameter_list():
    """``Sticking(fit, structure)`` passed the fit as the group's parameter list."""
    from chisurf.core.structure.av.parameters import Sticking

    owner = object()
    sticking = Sticking(owner, None)
    assert sticking.fit is owner
    assert list(sticking.parameters) == []
