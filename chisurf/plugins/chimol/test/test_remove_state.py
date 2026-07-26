"""``remove`` — deleting atoms must not change how the rest is drawn.

Reported as "remove waters changes rep", and it was three faults stacked:

* the trim was a **hand-written list of three masks**, one of which
  (``cartoon_mask``) is per *residue* and so never matched, and which missed
  ``colors_per_atom_override``, ``protected_mask`` and ``masked_mask``. The
  colour array kept its old length, so what remained was painted with colours
  belonging to atoms that no longer existed;
* the rebuild afterwards **re-derived** the representation from the default
  "hetero atoms get balls" rule, so deleting the waters put a sphere on the zinc
  — an atom nobody had selected;
* with the last selected atom gone the mask was empty but the **flag** stayed
  set, and the builder fell back to drawing points along the chain.

The trim now shares the list ``sort`` permutes, so the two cannot disagree about
what is atom-indexed, and the defaults apply only when the state does not fit.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

_FRAGMENT = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "solvated_fragment.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    win = MolViewPluginWindow()
    win.resize(800, 600)
    win.show()
    for _ in range(12):
        qapp.processEvents()
    win._load_structure_from_path(_FRAGMENT)
    for _ in range(20):
        qapp.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(10):
            qapp.processEvents()

    yield win.viewer, shared, do, errors
    win.close()


def _state(viewer):
    return viewer._objects[viewer.get_active_object_id()].state


def _shown_spheres(viewer):
    state = _state(viewer)
    mask = state.ball_mask
    if mask is None:
        return []
    names = np.char.strip(np.asarray(state.atoms["res_name"]).astype(str))
    return [str(names[k]) for k in np.nonzero(np.asarray(mask, dtype=bool))[0]]


# --------------------------------------------------------------------------- #
# The reported bug
# --------------------------------------------------------------------------- #
def test_removing_the_waters_does_not_put_a_sphere_on_the_zinc(session):
    """The whole report in one assertion."""
    viewer, _shared, do, errors = session
    do("hide everything")
    do("show cartoon, polymer")
    do("show spheres, solvent")
    assert set(_shown_spheres(viewer)) == {"HOH"}

    do("remove solvent")
    assert errors == []
    assert _shown_spheres(viewer) == [], (
        "nothing else was ever selected for spheres"
    )


def test_the_representation_flag_clears_with_its_mask(session):
    """An empty mask under a set flag made the builder draw its own default."""
    viewer, _shared, do, _errors = session
    do("hide everything")
    do("show spheres, solvent")
    assert _state(viewer).show_atoms is True
    do("remove solvent")
    assert _state(viewer).show_atoms is False


def test_only_the_cartoon_is_left_in_the_scene(session):
    viewer, _shared, do, _errors = session
    do("hide everything")
    do("show cartoon, polymer")
    do("show spheres, solvent")
    do("remove solvent")
    scene = viewer.get_current_scene()
    assert scene.objects
    assert all("cartoon" in str(o.id) for o in scene.objects), [
        str(o.id) for o in scene.objects
    ]


# --------------------------------------------------------------------------- #
# Every atom-indexed array has to shrink with the atoms
# --------------------------------------------------------------------------- #
def test_the_colour_array_shrinks_with_the_atoms(session):
    """It kept its old length, so the survivors got other atoms' colours."""
    viewer, _shared, do, _errors = session
    do("spectrum count, rainbow, all")
    state = _state(viewer)
    assert len(state.colors_per_atom_override) == len(state.atoms)

    do("remove solvent")
    state = _state(viewer)
    assert len(state.colors_per_atom_override) == len(state.atoms)


def test_a_surviving_atom_keeps_its_own_colour(session):
    """Shrinking is not enough -- the values have to follow the right atoms."""
    viewer, shared, do, _errors = session
    do("spectrum count, rainbow, all")
    state = _state(viewer)
    names = np.char.strip(np.asarray(state.atoms["atom_name"]).astype(str))
    res_ids = np.asarray(state.atoms["res_id"])
    before = {
        f"{res_ids[k]}:{names[k]}": tuple(
            np.round(np.asarray(state.colors_per_atom_override)[k], 6)
        )
        for k in range(len(names))
    }

    do("remove solvent")
    state = _state(viewer)
    names = np.char.strip(np.asarray(state.atoms["atom_name"]).astype(str))
    res_ids = np.asarray(state.atoms["res_id"])
    for k in range(len(names)):
        key = f"{res_ids[k]}:{names[k]}"
        assert tuple(
            np.round(np.asarray(state.colors_per_atom_override)[k], 6)
        ) == before[key], key


def test_protection_shrinks_with_the_atoms(session):
    """The mask must follow the atoms, and keep marking the same ones.

    Not "everything is protected afterwards": `protect polymer` leaves the zinc
    alone, so one of the survivors is legitimately unprotected. Asserting `.all()`
    tests the fixture, not the trim.
    """
    viewer, shared, do, _errors = session
    do("protect polymer")
    state = _state(viewer)
    _obj, _name, polymer = shared._resolve_selection_to_atom_mask(viewer, "polymer")
    expected = int(np.asarray(polymer, dtype=bool).sum())
    assert int(np.asarray(state.protected_mask, dtype=bool).sum()) == expected

    do("remove solvent")
    state = _state(viewer)
    assert len(state.protected_mask) == len(state.atoms)
    # The waters were never protected, so the count is unchanged by their going.
    assert int(np.asarray(state.protected_mask, dtype=bool).sum()) == expected


def test_bonds_to_removed_atoms_are_dropped(session):
    """A bond referring to a deleted index would point at the wrong atom."""
    viewer, _shared, do, _errors = session
    do("remove solvent")
    state = _state(viewer)
    bonds = np.asarray(state.bond_pairs, dtype=int)
    if bonds.size:
        assert bonds.max() < len(state.atoms)
        assert bonds.min() >= 0


def test_surviving_bonds_still_join_the_same_atoms(session):
    """Indices are remapped, not merely filtered."""
    viewer, _shared, do, _errors = session

    def bond_names():
        state = _state(viewer)
        names = np.char.strip(np.asarray(state.atoms["atom_name"]).astype(str))
        res_ids = np.asarray(state.atoms["res_id"])
        return {
            tuple(sorted((f"{res_ids[i]}:{names[i]}", f"{res_ids[j]}:{names[j]}")))
            for i, j in np.asarray(state.bond_pairs, dtype=int)
        }

    before = bond_names()
    do("remove solvent")
    after = bond_names()
    # The waters were unbonded, so every bond should have survived intact.
    assert after == before


def test_removing_nothing_leaves_everything_alone(session):
    viewer, _shared, do, _errors = session
    do("hide everything")
    do("show spheres, solvent")
    before = list(_shown_spheres(viewer))
    do("remove resn NOSUCH")
    assert _shown_spheres(viewer) == before
