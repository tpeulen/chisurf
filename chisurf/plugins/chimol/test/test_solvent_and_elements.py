"""Waters, ions, and two-letter elements.

Every structure in the test data was a protein with no waters and no metal ions,
so a whole class of defect could not be seen:

* ``remove solvent`` — the Action menu's "remove waters" — **crashed**. It assigned
  raw Angstrom into the render-space array and then handed ``set_structure`` the
  live state, which begins by clearing the arrays it is about to read;
* the ``element`` field was **one character wide**, so every two-letter symbol was
  truncated: ``ZN`` became ``Z``, ``CL`` became ``C``. ``metals`` matched nothing
  ever, ``elem ZN`` matched nothing, and a chlorine coloured as a carbon.

Hence ``solvated_fragment.pdb``: six residues of backbone, a zinc, and eight
waters. Small enough that a hundred-odd window loads stay quick, and the first
structure here that exercises any of this.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

_FRAGMENT = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "solvated_fragment.pdb"
)

_N_WATERS = 8
_N_POLYMER = 30          # six alanines, five atoms each
_N_TOTAL = _N_POLYMER + 1 + _N_WATERS     # + the zinc


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    """Build a viewer with the solvated fragment loaded, plus a command runner."""
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.cmd.command import Cmd
    from chimol.io.structure import _read_full_model
    from chimol.renderer.view import MolView

    view = MolView()
    view.add_structure(
        _read_full_model(cs_struct.Structure, _FRAGMENT),
        name="frag",
        source_path=str(_FRAGMENT),
    )

    class _Window:
        viewer = view

        def _refresh_objects_from_viewer(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Window())
    messages: list[str] = []
    errors: list[str] = []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return cmd, view, messages, errors


def _count(cmd, messages, expression) -> int:
    messages.clear()
    cmd.do(f"count_atoms {expression}")
    return int(messages[-1])


# --------------------------------------------------------------------------- #
# The reader
# --------------------------------------------------------------------------- #
def test_the_fixture_has_what_it_claims(session):
    _, view, _, _ = session
    names = np.char.strip(view._atoms["res_name"].astype(str))
    assert len(view._atoms) == _N_TOTAL
    assert int(np.count_nonzero(names == "HOH")) == _N_WATERS
    assert int(np.count_nonzero(names == "ZN")) == 1


def test_a_two_letter_element_survives_the_reader(session):
    """`ZN`, not `Z`. The field was one character wide.

    Everything keyed on the element inherited that: `metals` never matched, and a
    two-letter symbol could not be selected or coloured correctly.
    """
    _, view, _, _ = session
    elements = np.char.strip(view._atoms["element"].astype(str))
    assert "ZN" in set(elements.tolist())
    assert "Z" not in set(elements.tolist())


# --------------------------------------------------------------------------- #
# Selecting them
# --------------------------------------------------------------------------- #
def test_solvent_finds_the_waters(session):
    cmd, _, messages, _ = session
    assert _count(cmd, messages, "solvent") == _N_WATERS


def test_metals_finds_the_ion(session):
    """Zero before the element field was widened, on every structure."""
    cmd, _, messages, _ = session
    assert _count(cmd, messages, "metals") == 1


def test_an_element_selection_takes_two_letters(session):
    cmd, _, messages, _ = session
    assert _count(cmd, messages, "elem ZN") == 1


def test_polymer_excludes_the_solvent_and_the_ion(session):
    cmd, _, messages, _ = session
    assert _count(cmd, messages, "polymer") == _N_POLYMER


def test_a_lone_ion_is_inorganic(session):
    """One atom, no carbon: PyMOL's classifier calls that inorganic."""
    cmd, _, messages, _ = session
    assert _count(cmd, messages, "inorganic") == 1


def test_hetatm_covers_the_ion_and_the_waters(session):
    cmd, _, messages, _ = session
    assert _count(cmd, messages, "hetatm") == _N_WATERS + 1


# --------------------------------------------------------------------------- #
# Removing them -- the Action menu's "remove waters"
# --------------------------------------------------------------------------- #
def test_remove_solvent_works(session):
    """It crashed: `set_structure` was handed the live state it then cleared."""
    cmd, view, messages, errors = session
    cmd.do("remove solvent")
    assert errors == []
    assert len(view._atoms) == _N_TOTAL - _N_WATERS
    names = np.char.strip(view._atoms["res_name"].astype(str))
    assert "HOH" not in set(names.tolist())


def test_removing_rebuilds_the_render_coordinates(session):
    """And in scene units, not raw Angstrom -- the old code assigned the latter."""
    cmd, view, _, _ = session
    cmd.do("remove solvent")
    render = np.asarray(view._all_atom_coords, dtype=float)
    assert render.shape[0] == len(view._atoms)

    # Per axis, not over the flattened array: the render coordinates are centred
    # as well as scaled, so a global min-to-max mixes the axes up and no longer
    # scales cleanly. Each axis's span does.
    scale = float(view._scale_factor)
    raw_span = np.ptp(np.asarray(view._atoms["xyz"], dtype=float), axis=0)
    assert np.allclose(np.ptp(render, axis=0), raw_span * scale, rtol=1e-6)


def test_removing_leaves_the_rest_selectable(session):
    """A stale mask or trace makes the *next* command fail, not this one."""
    cmd, view, messages, errors = session
    cmd.do("remove solvent")
    errors.clear()
    assert _count(cmd, messages, "polymer") == _N_POLYMER
    assert _count(cmd, messages, "metals") == 1
    assert errors == []


def test_removing_everything_empties_the_object_rather_than_deleting_it(session):
    """PyMOL keeps the object, so a mistaken `remove all` costs a reload, not a session."""
    cmd, view, messages, errors = session
    cmd.do("remove all")
    assert errors == []
    assert "empty" in messages[-1]
    assert [o["name"] for o in view.list_objects()] == ["frag"]


def test_removing_the_ion(session):
    cmd, view, _, errors = session
    cmd.do("remove metals")
    assert errors == []
    assert len(view._atoms) == _N_TOTAL - 1


# --------------------------------------------------------------------------- #
# The bonds of a solvated structure
# --------------------------------------------------------------------------- #
def test_waters_are_not_bonded_to_anything(session):
    """They are far apart in the fixture, and a lone oxygen bonds to nothing."""
    _, view, _, _ = session
    bonds = np.asarray(view._bond_pairs)
    names = np.char.strip(view._atoms["res_name"].astype(str))
    is_water = names == "HOH"
    assert not np.any(is_water[bonds[:, 0]] | is_water[bonds[:, 1]])


def test_the_backbone_is_bonded(session):
    _, view, _, _ = session
    assert np.asarray(view._bond_pairs).shape[0] >= 8
