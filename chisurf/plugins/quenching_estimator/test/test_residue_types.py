"""`Structure.residue_types` holds one entry per residue, in lookup-table order.

It used to hold one entry per *atom* of a known residue, so entry *i* was not
residue *i* and the array was as long as the atom list.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.structure import Structure
from chisurf.plugins.quenching_estimator.core.structure.model import res2id

SINGLE = Path(__file__).parent / "148l.pdb"
DIMER = Path(__file__).parent / "data" / "mc4r_dimer.cif"


@pytest.mark.parametrize("path", [SINGLE, DIMER], ids=["148l", "mc4r_dimer"])
@pytest.mark.parametrize("coarse", [False, True], ids=["all_atom", "coarse"])
def test_one_type_per_residue(path, coarse):
    structure = Structure(str(path), make_coarse=coarse, verbose=False)
    types = structure.residue_types
    assert types.shape == (structure.n_residues,) == (structure.l_res.shape[0],)
    for row, residue in enumerate(structure.residue_dict.values()):
        name = str(next(iter(residue.values()))["res_name"])
        assert types[row] == res2id.get(name, -1)
    # The CA of each typed residue belongs to a residue of that type.
    ca = structure.l_ca
    typed = (types >= 0) & (ca >= 0)
    names = np.array(list(res2id))[types[typed]]
    assert np.all(structure.atoms["res_name"][ca[typed]] == names)
