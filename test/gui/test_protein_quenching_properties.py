"""The real quenching parameter properties preserve exclusion and rate semantics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.core.structure import Structure
from chisurf.core.structure.av.parameters import ProteinQuenching

SOURCE = Path(__file__).resolve().parents[1] / "data/atomic_coordinates/pdb_files/148l.pdb"
RATES = {"TRP": 3.5, "TYR": 2.0}


@pytest.fixture
def structure():
    """Use the real 148L residue/atom identities and coordinates for an independent oracle."""
    return Structure(p_object=str(SOURCE), make_coarse=False)


def _indices(structure, excluded, all_atoms):
    """Compute expected atom membership from physical residue/name rules without model helpers."""
    return {
        index
        for index, atom in enumerate(structure.atoms)
        if atom["res_name"] in RATES
        and atom["atom_name"] not in excluded
        and (all_atoms or atom["atom_name"] == "CB")
    }


@pytest.mark.parametrize("all_atoms", [False, True])
def test_core_all_atoms_flag_selects_real_coordinates_and_preserves_rates(structure, all_atoms):
    """The true/false property controls selection while per-residue rates retain their units."""
    excluded = {"N", "CA", "C", "O"}
    model = ProteinQuenching(structure=structure, excluded_atoms=excluded, quench_scale=0.4)
    model.all_atoms_quench = all_atoms
    assert model.all_atoms_quench is all_atoms
    model.quencher = {residue: {"atoms": ["CB"], "rate": rate} for residue, rate in RATES.items()}
    indices = np.concatenate([model.quencher[residue]["atom_idx"] for residue in RATES])
    assert set(indices) == _indices(structure, excluded, all_atoms)
    np.testing.assert_array_equal(model.xyz, structure.xyz[indices])
    expected_rates = [0.4 * RATES[structure.atoms[index]["res_name"]] for index in indices]
    np.testing.assert_allclose(model.k_quench, expected_rates, rtol=1e-7)
    assert model.k_quench.dtype == np.float32


@pytest.mark.parametrize("all_atoms", [False, True])
def test_explicit_atom_lists_keep_their_existing_selection_contract(structure, all_atoms):
    """Explicit atom lists keep their exact atoms/default rate regardless of all-atoms mode."""
    model = ProteinQuenching(
        structure=structure,
        all_atoms_quench=all_atoms,
        excluded_atoms={"CA"},
        quench_scale=0.4,
        quenching_amino_acids={"TRP": ["CA", "CB"]},
    )
    expected = {
        i
        for i, atom in enumerate(structure.atoms)
        if atom["res_name"] == "TRP" and atom["atom_name"] in {"CA", "CB"}
    }
    assert set(model.quencher["TRP"]["atom_idx"]) == expected
    assert model.quencher["TRP"]["rate"] == 1.0
    np.testing.assert_allclose(model.k_quench, 0.4)


@pytest.mark.parametrize(("options", "expected"), [({}, 0.01), ({"quench_scale": 0.4}, 0.4)])
def test_scale_binding_preserves_default_input_and_parameter_identity(structure, options, expected):
    """The default and the canonical ``quench_scale`` input win; assignment keeps the Parameter."""
    model = ProteinQuenching(structure=structure, **options)
    parameter = model._k_quench_scale
    assert model.kQ_scale == parameter.value == expected
    model.kQ_scale = 4.125
    assert model._k_quench_scale is parameter
    assert parameter.value == 4.125


@pytest.mark.parametrize("enabled", [False, True])
def test_all_atoms_initialization_and_assignment_match_the_flag(structure, enabled):
    """The constructor flag and assignment retain a writable bool contract."""
    model = ProteinQuenching(structure=structure, all_atoms_quench=enabled)
    assert model.all_atoms_quench is enabled
    model.all_atoms_quench = not enabled
    assert model.all_atoms_quench is (not enabled)
