"""Topology over ChiSurf's atom array (:mod:`chisurf.core.structure.topology`).

The numbers here were taken from the library this replaces, on the project's
own test structure, and are asserted literally rather than recomputed — a test
that derives its expectation the same way the code does would agree with a
wrong implementation.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.structure.topology import Topology

PDB = (pathlib.Path(__file__).resolve().parents[1]
       / "data/atomic_coordinates/trajectory/hgbp1/topol.pdb")


@pytest.fixture(scope="module")
def topology():
    return Topology.from_file(str(PDB))


def test_counts_match_the_reference(topology):
    # 5235 / 570 / 2 as reported by the implementation being replaced.
    assert (topology.n_atoms, topology.n_residues, topology.n_chains) == (5235, 570, 2)
    assert len(topology) == 5235


def test_residues_are_numbered_in_file_order_not_by_number(topology):
    """A residue index is a position, not the number written in the file.

    Numbering by ``res_id`` alone would merge residue 5 of every chain, and
    numbering by sorted unique value would reorder them. Both produce a
    plausible residue count and the wrong grouping.
    """
    indices = [r.index for r in topology.residues]
    assert indices == list(range(topology.n_residues))
    first = topology.residue(0)
    assert first.index == 0
    # The file does not start at residue 0, so index and resSeq differ.
    assert first.resSeq != first.index


def test_a_residue_belongs_to_its_chain(topology):
    residues = list(topology.residues)
    chains = {r.chain.index for r in residues}
    assert chains == {0, 1}
    assert all(isinstance(r.chain.chain_id, str) for r in residues)


def test_every_atom_resolves_to_a_residue_and_a_chain(topology):
    atoms = list(topology.atoms)
    assert len(atoms) == 5235
    assert atoms[0].index == 0
    assert all(a.index == i for i, a in enumerate(atoms))
    assert all(0 <= a.residue.index < topology.n_residues for a in atoms)


def test_elements_survive(topology):
    # A one-character element field truncates ZN to Z and CL to C; the array
    # this is built on widened it for exactly that reason, so check it arrived.
    elements = {a.element for a in topology.atoms}
    assert elements - {""}, "no elements at all"
    assert all(len(e) <= 2 for e in elements)


def test_select_goes_through_the_topology(topology):
    assert len(topology.select("name CA")) == 570          # one per residue
    assert len(topology.select("all")) == topology.n_atoms
    np.testing.assert_array_equal(
        topology.select("name CA"), np.flatnonzero(topology.select_mask("name CA"))
    )


def test_subset_keeps_order_and_renumbers(topology):
    subset = topology.subset([5, 3, 1])
    assert subset.n_atoms == 3
    names = [a.name for a in subset.atoms]
    assert names == [topology.atom(i).name for i in (5, 3, 1)]
    assert [a.index for a in subset.atoms] == [0, 1, 2]


def test_to_store_has_a_row_per_atom(topology):
    from chisurf.core.datastore import column_names, row_count

    table = topology.to_store()
    assert row_count(table) == topology.n_atoms
    assert {"serial", "name", "element", "resSeq", "resName", "chainID"} <= set(column_names(table))


def test_equality_ignores_coordinates(topology):
    # Two frames of one molecule share a topology; comparing positions would
    # make every frame a different topology.
    other = Topology(topology.atom_array.copy())
    other.atom_array["xyz"] += 5.0
    assert topology == other
    assert topology != topology.subset(range(10))


def test_an_out_of_range_index_raises(topology):
    with pytest.raises(IndexError):
        topology.residue(topology.n_residues + 1)
    with pytest.raises(IndexError):
        topology.chain(99)
