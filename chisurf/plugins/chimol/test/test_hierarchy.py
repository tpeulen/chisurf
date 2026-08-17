"""The tree a structure is organised into, and the panel that shows it.

An integrative mmCIF describes its own organisation in detail -- 31 nucleoporins
in 544 copies, for the eight-spoke nuclear pore -- in the same shape an RMF from
IMP carries. Reading one and showing a flat cloud of 234,184 anonymous beads
throws that away.

The panel had a defect that only a tree deeper than two levels reveals, which is
why it survived: `parent()` returned row 0 for every parent and called the root's
children top-level, while row 0 of the top level was the root itself. The view
drew the root twice and dropped the entire molecule level.
"""
from __future__ import annotations

import numpy as np
import pytest

from chimol.core.model.hierarchy import HierarchyNode


# --------------------------------------------------------------------------- #
# The node
# --------------------------------------------------------------------------- #
def test_nodes_compare_by_identity_not_by_value():
    """Two copies of the same molecule are equal field for field, and distinct.

    A dataclass ``__eq__`` would also walk two whole subtrees to answer a
    question a tree model asks on every index it builds.
    """
    a = HierarchyNode(name="A", node_type="CHAIN")
    b = HierarchyNode(name="A", node_type="CHAIN")
    assert a != b
    assert a == a


def test_add_child_parents_and_returns():
    root = HierarchyNode(name="root", node_type="ROOT")
    child = root.add_child(HierarchyNode(name="mol", node_type="MOLECULE"))
    assert child.parent is root
    assert root.children == [child]
    assert root.count() == 2


# --------------------------------------------------------------------------- #
# Building one from an integrative mmCIF
# --------------------------------------------------------------------------- #
_TWO_MOLECULE_CIF = """data_test
_entry.id TEST
loop_
_entity.id
_entity.type
_entity.pdbx_description
1 polymer Nup84
2 polymer Nup85
loop_
_entity_poly_seq.entity_id
_entity_poly_seq.num
_entity_poly_seq.mon_id
1 1 ALA
1 2 GLY
2 1 ALA
2 2 GLY
loop_
_struct_asym.id
_struct_asym.entity_id
A 1
B 1
C 2
loop_
_ihm_model_list.model_id
_ihm_model_list.model_group_id
_ihm_model_list.model_name
_ihm_model_list.model_group_name
_ihm_model_list.assembly_id
_ihm_model_list.protocol_id
_ihm_model_list.representation_id
1 1 . 'Group' 1 . 1
loop_
_ihm_sphere_obj_site.id
_ihm_sphere_obj_site.entity_id
_ihm_sphere_obj_site.seq_id_begin
_ihm_sphere_obj_site.seq_id_end
_ihm_sphere_obj_site.asym_id
_ihm_sphere_obj_site.Cartn_x
_ihm_sphere_obj_site.Cartn_y
_ihm_sphere_obj_site.Cartn_z
_ihm_sphere_obj_site.object_radius
_ihm_sphere_obj_site.model_id
1 1 1 2 A 0.0 0.0 0.0 10.0 1
2 1 1 2 A 20.0 0.0 0.0 12.0 1
3 1 1 2 B 0.0 20.0 0.0 11.0 1
4 2 1 2 C 0.0 0.0 20.0 9.0 1
"""


@pytest.fixture
def parsed(tmp_path):
    from chimol.io.structure import _parse_mmcif_backbone

    cif = tmp_path / "two.cif"
    cif.write_text(_TWO_MOLECULE_CIF)
    return _parse_mmcif_backbone(str(cif))


def test_the_reader_returns_a_hierarchy(parsed):
    assert parsed.hierarchy is not None
    assert parsed.hierarchy.node_type == "ROOT"


def test_copies_are_grouped_under_the_molecule_they_copy(parsed):
    """This is the level a bead cloud cannot show: which nucleoporin is which."""
    root = parsed.hierarchy
    molecules = {m.name: m for m in root.children}
    assert set(molecules) == {"Nup84", "Nup85"}
    assert [c.name.split(" ")[0] for c in molecules["Nup84"].children] == ["A", "B"]
    assert [c.name.split(" ")[0] for c in molecules["Nup85"].children] == ["C"]
    assert all(c.node_type == "CHAIN" for m in root.children for c in m.children)


def test_every_row_belongs_to_exactly_one_copy(parsed):
    """Otherwise a click on a chain selects the wrong beads, or none."""
    root = parsed.hierarchy
    n_rows = parsed.coords.shape[0]
    rows: list[int] = []
    for molecule in root.children:
        for chain in molecule.children:
            rows.extend(chain.atom_indices)
    assert sorted(rows) == list(range(n_rows))


def test_a_molecule_carries_its_copies_rows(parsed):
    root = parsed.hierarchy
    for molecule in root.children:
        expected = sorted(i for c in molecule.children for i in c.atom_indices)
        assert sorted(molecule.atom_indices) == expected


def test_a_plain_pdb_has_no_hierarchy(tmp_path):
    """Nothing invented: a PDB file does not describe one."""
    from chimol.io.structure import load_structure_payload

    pdb = tmp_path / "t.pdb"
    pdb.write_text(
        "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00  0.00           C\n"
        "ATOM      2  CA  ALA A   2       3.800   0.000   0.000  1.00  0.00           C\n"
        "END\n"
    )
    _structure, backbone = load_structure_payload(pdb, structure_factory=None)
    assert backbone.hierarchy is None


# --------------------------------------------------------------------------- #
# Showing it
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp_hier():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _three_level_tree():
    root = HierarchyNode(name="entry", node_type="ROOT")
    for m in range(3):
        molecule = root.add_child(
            HierarchyNode(name=f"mol{m}", node_type="MOLECULE")
        )
        for c in range(4):
            molecule.add_child(
                HierarchyNode(name=f"chain{m}{c}", node_type="CHAIN")
            )
    return root


# The Qt `HierarchyModel`/`HierarchyDock` tests lived here. Both were deleted
# with the dock when the 3-D view became the window's only widget: the tree is
# drawn in the viewport now, and two trees over one model is two things that
# can disagree. What they pinned is pinned in
# `test_hierarchy_window.py` against the panel that replaced them -- the
# molecule level is not dropped, switching a node off takes its subtree, and
# what reaches the viewer is the rows those nodes cover.
#
# The tests below are **not** about either panel: they are about the viewer
# honouring `set_rows_hidden`, whoever calls it.
def test_hidden_rows_are_not_drawn(qapp_hier):
    """The point of the check box: fewer particles in the picture."""
    from chimol.core.viewer import Viewer

    n = 40
    rng = np.random.default_rng(1)
    xyz = rng.normal(scale=20.0, size=(n, 3))
    dtype = np.dtype(
        [
            ("atom_name", "U4"), ("res_name", "U4"), ("chain", "U4"),
            ("res_id", "i4"), ("element", "U2"), ("xyz", "f8", 3),
        ]
    )
    atoms = np.zeros(n, dtype=dtype)
    atoms["atom_name"] = "CA"
    atoms["res_name"] = "BEA"
    atoms["chain"] = "A"
    atoms["res_id"] = np.arange(1, n + 1)
    atoms["xyz"] = xyz

    view = Viewer()
    view.set_coordinates(
        xyz, trace_coords=xyz, res_ids=atoms["res_id"],
        res_names=atoms["res_name"], chain_ids=atoms["chain"], atoms=atoms,
        atom_radii=np.full(n, 5.0),
    )
    cfg = {"impostor_min_atoms": 1}
    assert view._bead_scene_object(cfg, None).geometry.positions.shape[0] == n

    view.set_rows_hidden(range(10), True)
    assert view._bead_scene_object(cfg, None).geometry.positions.shape[0] == n - 10

    view.set_rows_hidden(range(10), False)
    assert view._bead_scene_object(cfg, None).geometry.positions.shape[0] == n


def test_hiding_everything_draws_nothing(qapp_hier):
    from chimol.core.viewer import Viewer

    n = 12
    xyz = np.arange(n * 3, dtype=float).reshape(n, 3)
    dtype = np.dtype(
        [
            ("atom_name", "U4"), ("res_name", "U4"), ("chain", "U4"),
            ("res_id", "i4"), ("element", "U2"), ("xyz", "f8", 3),
        ]
    )
    atoms = np.zeros(n, dtype=dtype)
    atoms["atom_name"] = "CA"
    atoms["res_name"] = "BEA"
    atoms["chain"] = "A"
    atoms["res_id"] = np.arange(1, n + 1)
    atoms["xyz"] = xyz

    view = Viewer()
    view.set_coordinates(
        xyz, trace_coords=xyz, res_ids=atoms["res_id"],
        res_names=atoms["res_name"], chain_ids=atoms["chain"], atoms=atoms,
    )
    view.set_rows_hidden(range(n), True)
    assert view._bead_scene_object({"impostor_min_atoms": 1}, None) is None


def test_hiding_follows_the_atoms_when_they_are_reordered(qapp_hier):
    """`hidden_mask` is atom-indexed, so a `sort` has to permute it too.

    Left out of the atom-indexed list it would keep the *old* order while the
    coordinates moved, so hiding one molecule and then sorting would hide an
    arbitrary set of beads instead. The guardrail in `test_sort_mask` is what
    catches the omission; this is what the omission would have cost.
    """
    from chimol.analysis.atom_order import (
        ATOM_INDEXED_FIELDS,
    )

    assert "hidden_mask" in ATOM_INDEXED_FIELDS


def test_the_viewer_keeps_the_hierarchy_it_is_given(qapp_hier):
    """One field, whichever reader filled it."""
    from chimol.core.viewer import Viewer

    tree = _three_level_tree()
    view = Viewer()
    view.set_coordinates(
        np.zeros((3, 3), dtype=float) + np.arange(3)[:, None],
        hierarchy=tree,
    )
    assert view._get_active_state().rmf_hierarchy is tree
