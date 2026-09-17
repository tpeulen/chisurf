"""``remove resn HOH`` (or any edit that rebuilds) keeps the helices where they were.

The rebuild after an edit derives its residue list from the atom table and
can count a bound HETATM peptide the file loader did not; carrying the
secondary-structure codes across **by index** then shifted every code by the
extra residues, and the cartoon lost its helices after removing the waters.
The codes are re-addressed by ``(chain, resi)`` now.
"""

from __future__ import annotations

import os
import pathlib

import numpy as np
import pytest

_PDB = pathlib.Path.home() / ".chisurf" / "structures" / "chimol" / "chimol_pdb_148l.pdb"


@pytest.mark.skipif(
    not _PDB.exists(), reason="needs the fetched 148l with its waters and substrate"
)
def test_removing_the_waters_keeps_the_helices():
    os.environ.setdefault("CHIMOL_TOOLKIT", "none")
    from chimol.hosts.native.app import ChimolApp

    app = ChimolApp(backend="offscreen", size=(400, 300))
    app.cmd.do(f'load "{_PDB}"')
    app.cmd.do("show cartoon")
    viewer = app.viewer
    state = viewer.active_state()
    before = np.asarray(state.secondary_structure).copy()
    keys_before = list(
        zip(np.asarray(state.residue_chain_ids).tolist(), np.asarray(state.residue_ids).tolist())
    )
    n_helix = int((before == "H").sum())
    assert n_helix > 50

    app.cmd.do("remove resn HOH")
    state = viewer.active_state()
    after = np.asarray(state.secondary_structure)
    keys_after = list(
        zip(np.asarray(state.residue_chain_ids).tolist(), np.asarray(state.residue_ids).tolist())
    )
    assert len(after) == len(keys_after)
    for i, key in enumerate(keys_before):
        if key in keys_after:
            assert after[keys_after.index(key)] == before[i], key
    assert int((after == "H").sum()) == n_helix
