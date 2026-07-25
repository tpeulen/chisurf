"""Commands that reported success while doing nothing.

Every test here covers a command that was registered, documented, and answered
with a cheerful message while having no effect at all. They are grouped because
they share one cause: a second copy of a table that had drifted from the real one.

* ``alter`` carried its own property map naming ``chain_id``, ``b_factor`` and
  ``occupancy`` -- none of which are fields -- so ``alter sele, b=42`` reported
  "Altered 1299 atoms" and wrote nothing. Its test used the same wrong names, so it
  passed.
* ``alter`` then assigned raw Angstrom into the render-space array, shrinking the
  molecule tenfold and moving it off centre on *every* call, however innocent.
* ``spectrum`` was ``self.color("spectrum")``: a three-argument command that
  discarded its expression, its palette and its selection.

The lesson each encodes: a command that cannot demonstrate its effect on the data
is not tested by asserting the message it prints.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    """Build a viewer with 148L loaded and a command interpreter over it."""
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd
    from chisurf.plugins.chimol.chimol.io.structure import _read_full_model
    from chisurf.plugins.chimol.chimol.renderer.view import MolView

    view = MolView()
    view.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
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


def _state(view):
    return view._objects[view.get_active_object_id()].state


def _chain(view) -> np.ndarray:
    return np.char.strip(view._atoms["chain"].astype(str))


# --------------------------------------------------------------------------- #
# alter -- the property map
# --------------------------------------------------------------------------- #
def test_alter_actually_writes_the_b_factor(session):
    """The regression: it reported altering 1299 atoms and wrote nothing."""
    cmd, view, _, errors = session
    cmd.do("alter chain E, b=42")
    assert errors == []
    assert np.all(view._atoms["bfactor"][_chain(view) == "E"] == 42.0)


def test_alter_leaves_unselected_atoms_alone(session):
    cmd, view, _, _ = session
    cmd.do("alter chain E, b=42")
    assert not np.any(view._atoms["bfactor"][_chain(view) != "E"] == 42.0)


def test_alter_writes_strings(session):
    cmd, view, _, _ = session
    cmd.do("alter resn NAG, resn='XXX'")
    names = np.char.strip(view._atoms["res_name"].astype(str))
    assert int(np.count_nonzero(names == "XXX")) == 14


def test_alter_reports_which_field_it_wrote(session):
    """So that writing nothing cannot read like writing something."""
    cmd, _, messages, _ = session
    cmd.do("alter chain E, b=42")
    assert "bfactor" in messages[-1]


def test_an_alter_that_changes_nothing_says_so(session):
    cmd, _, messages, _ = session
    cmd.do("alter all, pass")
    assert "nothing changed" in messages[-1]


def test_alter_does_not_move_the_molecule(session):
    """A property-only edit must not touch geometry.

    It used to assign raw Angstrom into the render-space array, which is scaled by
    ten and centred -- so every `alter` shrank the molecule and shifted it.
    """
    cmd, view, _, _ = session
    before = np.asarray(_state(view).all_atom_coords).copy()
    cmd.do("alter all, b=1")
    assert np.allclose(before, np.asarray(_state(view).all_atom_coords))


def test_alter_refuses_coordinates_and_says_where_they_live(session):
    """PyMOL keeps coordinates in `alter_state`; the error should point there."""
    cmd, _, _, errors = session
    cmd.do("alter all, x = x + 10")
    assert errors and "alter_state" in errors[-1]


# --------------------------------------------------------------------------- #
# iterate
# --------------------------------------------------------------------------- #
def test_iterate_sees_the_values_alter_wrote(session):
    """The two must agree about what `b` means, which is the point of one table."""
    cmd, view, _, errors = session
    cmd.do("alter resn NAG, b=7")
    cmd.do("iterate resn NAG, stored.setdefault('b', []).append(b)")
    assert errors == []
    assert cmd._stored["b"] == [7.0] * 14


def test_iterate_accumulates_across_commands(session):
    """`stored` is what makes iterate useful for pulling data out."""
    cmd, _, _, _ = session
    cmd.do("iterate name CA, stored.setdefault('n', []).append(resi)")
    assert len(cmd._stored["n"]) == 165


def test_iterate_does_not_write(session):
    cmd, view, _, _ = session
    before = np.asarray(view._atoms["bfactor"]).copy()
    cmd.do("iterate all, b = 999")
    assert np.allclose(before, view._atoms["bfactor"])


def test_iterate_has_no_coordinates_in_scope(session):
    """As in PyMOL: that is `iterate_state`."""
    cmd, _, _, errors = session
    cmd.do("iterate all, print(x)")
    assert errors and "iterate_state" in errors[-1]


def test_an_empty_selection_is_reported(session):
    cmd, _, _, errors = session
    cmd.do("iterate resn ZZZ, print(name)")
    assert errors and "matched no atoms" in errors[-1]


# --------------------------------------------------------------------------- #
# alter_state / iterate_state
# --------------------------------------------------------------------------- #
def test_alter_state_moves_atoms(session):
    cmd, view, _, errors = session
    before = float(np.asarray(view._atoms["xyz"])[:, 0].mean())
    cmd.do("alter_state 1, all, x = x + 10")
    assert errors == []
    after = float(np.asarray(view._atoms["xyz"])[:, 0].mean())
    assert after == pytest.approx(before + 10.0)


def test_alter_state_honours_the_selection(session):
    cmd, view, _, _ = session
    names = np.char.strip(view._atoms["res_name"].astype(str))
    before = np.asarray(view._atoms["xyz"]).copy()
    cmd.do("alter_state 1, resn NAG, y = y - 5")
    after = np.asarray(view._atoms["xyz"])
    assert np.allclose(after[names != "NAG"], before[names != "NAG"])
    assert np.allclose(after[names == "NAG", 1], before[names == "NAG", 1] - 5.0)


def test_alter_state_rebuilds_the_render_geometry_at_the_right_scale(session):
    """Moving atoms must update the scene arrays *through the scale*, not past it."""
    cmd, view, _, _ = session
    before = np.asarray(_state(view).all_atom_coords)
    extent = float(before.max() - before.min())
    cmd.do("alter_state 1, all, x = x + 10")
    after = np.asarray(_state(view).all_atom_coords)
    assert float(after.max() - after.min()) == pytest.approx(extent, abs=1e-6)


def test_alter_state_keeps_the_secondary_structure(session):
    """Where a helix is does not depend on where the molecule sits."""
    cmd, view, _, _ = session
    before = list(np.asarray(_state(view).secondary_structure).tolist())
    cmd.do("alter_state 1, all, z = z + 1")
    assert list(np.asarray(_state(view).secondary_structure).tolist()) == before


def test_iterate_state_reads_coordinates(session):
    cmd, view, _, errors = session
    cmd.do("iterate_state 1, name CA, stored.setdefault('xs', []).append(x)")
    assert errors == []
    assert len(cmd._stored["xs"]) == 165


def test_a_state_that_does_not_exist_is_reported(session):
    cmd, _, _, errors = session
    cmd.do("alter_state 3, all, x=x")
    assert errors and "one coordinate set" in errors[-1]


# --------------------------------------------------------------------------- #
# spectrum
# --------------------------------------------------------------------------- #
def test_spectrum_writes_per_atom_colours(session):
    """It used to set a global colour mode and discard all three arguments."""
    cmd, view, _, errors = session
    cmd.do("spectrum b")
    assert errors == []
    colors = np.asarray(_state(view).colors_per_atom_override)
    assert colors.shape == (len(view._atoms), 4)


def test_spectrum_ramps_the_named_property(session):
    """The lowest b-factor takes the first colour, the highest the last."""
    cmd, view, _, _ = session
    cmd.do("spectrum b, blue_red")
    colors = np.asarray(_state(view).colors_per_atom_override)
    b = np.asarray(view._atoms["bfactor"], dtype=float)
    assert np.allclose(colors[b.argmin(), :3], [0.0, 0.0, 1.0], atol=0.05)
    assert np.allclose(colors[b.argmax(), :3], [1.0, 0.0, 0.0], atol=0.05)


def test_spectrum_honours_its_selection(session):
    """Colouring a ligand must not recolour the protein."""
    cmd, view, _, _ = session
    cmd.do("spectrum b, blue_red, all")
    before = np.asarray(_state(view).colors_per_atom_override).copy()
    cmd.do("spectrum b, rainbow, resn NAG")
    after = np.asarray(_state(view).colors_per_atom_override)

    names = np.char.strip(view._atoms["res_name"].astype(str))
    assert np.allclose(after[names != "NAG"], before[names != "NAG"])
    assert not np.allclose(after[names == "NAG"], before[names == "NAG"])


def test_spectrum_honours_an_explicit_range(session):
    cmd, _, messages, _ = session
    cmd.do("spectrum b, rainbow, all, 0, 100")
    assert "0 to 100" in messages[-1]


def test_spectrum_reports_the_range_it_used(session):
    """So a ramp can be reproduced, or two structures put on the same scale."""
    cmd, view, messages, _ = session
    cmd.do("spectrum b")
    b = np.asarray(view._atoms["bfactor"], dtype=float)
    assert f"{b.min():.4g}" in messages[-1]


def test_spectrum_enumerates_a_non_numeric_property(session):
    """PyMOL colours by residue type this way; refusing would be less useful."""
    cmd, view, _, errors = session
    cmd.do("spectrum resn")
    assert errors == []
    colors = np.asarray(_state(view).colors_per_atom_override)
    names = np.char.strip(view._atoms["res_name"].astype(str))
    # Same residue name, same colour.
    for resn in ("ALA", "NAG"):
        chosen = colors[names == resn]
        assert np.allclose(chosen, chosen[0])


def test_a_palette_of_one_colour_is_refused(session):
    cmd, _, _, errors = session
    cmd.do("spectrum b, red")
    assert errors and "at least two colours" in errors[-1]


def test_an_unknown_colour_is_reported(session):
    cmd, _, _, errors = session
    cmd.do("spectrum b, notacolour_alsonot")
    assert errors


# --------------------------------------------------------------------------- #
# The ramp itself
# --------------------------------------------------------------------------- #
def test_the_ramp_puts_the_ends_on_the_ends():
    """Clamping to n-2 is what puts the maximum on the last colour."""
    from chisurf.plugins.chimol.chimol.analysis.spectrum import spectrum_colors

    palette = np.array([[0.0, 0, 0], [0.5, 0.5, 0.5], [1.0, 1, 1]])
    ramped, lo, hi = spectrum_colors([0.0, 0.5, 1.0], palette)
    assert (lo, hi) == (0.0, 1.0)
    assert np.allclose(ramped[0, :3], [0.0, 0, 0])
    assert np.allclose(ramped[1, :3], [0.5, 0.5, 0.5])
    assert np.allclose(ramped[2, :3], [1.0, 1, 1])


def test_the_ramp_interpolates_between_neighbours():
    from chisurf.plugins.chimol.chimol.analysis.spectrum import spectrum_colors

    palette = np.array([[0.0, 0, 0], [1.0, 1, 1]])
    ramped, _, _ = spectrum_colors([0.0, 0.25, 1.0], palette)
    assert np.allclose(ramped[1, :3], [0.25, 0.25, 0.25])


def test_a_constant_property_takes_the_first_colour():
    """Not a division by zero, and not an arbitrary point in the ramp."""
    from chisurf.plugins.chimol.chimol.analysis.spectrum import spectrum_colors

    palette = np.array([[0.0, 0, 0], [1.0, 1, 1]])
    ramped, lo, hi = spectrum_colors([5.0, 5.0, 5.0], palette)
    assert lo == hi == 5.0
    assert np.allclose(ramped[:, :3], 0.0)


def test_palette_names_come_from_pymols_table():
    from chisurf.plugins.chimol.chimol.analysis.spectrum import palette_colors

    assert palette_colors("rainbow") == [
        "blue", "cyan", "green", "yellow", "orange", "red"
    ]
    assert palette_colors("gcbmry")[0] == "green"


def test_an_unlisted_palette_is_read_as_colour_names():
    """Which is why `blue_white_red` works without being a defined palette."""
    from chisurf.plugins.chimol.chimol.analysis.spectrum import palette_colors

    assert palette_colors("blue_white_red") == ["blue", "white", "red"]


# --------------------------------------------------------------------------- #
# pseudoatom, copy, as
# --------------------------------------------------------------------------- #
def test_pseudoatom_creates_a_usable_object(session):
    """It used to build its own atom dtype and crash before finishing."""
    cmd, view, _, errors = session
    cmd.do("pseudoatom pt, pos=[1,2,3]")
    assert errors == []
    entry = next(
        view._objects[o["id"]] for o in view.list_objects() if o["name"] == "pt"
    )
    assert np.allclose(entry.state.atoms["xyz"][0], [1.0, 2.0, 3.0])


def test_a_pseudoatom_matches_the_reader_dtype(session):
    """Otherwise nothing downstream -- selections, export, colouring -- can read it."""
    cmd, view, _, _ = session
    cmd.do("pseudoatom pt, pos=[1,2,3]")
    entry = next(
        view._objects[o["id"]] for o in view.list_objects() if o["name"] == "pt"
    )
    assert {"chain", "res_id", "res_name", "atom_name", "bfactor", "xyz"} <= set(
        entry.state.atoms.dtype.names
    )


def test_a_pseudoatom_does_not_break_the_next_command(session):
    """The crash left a half-built object active, breaking every later selection."""
    cmd, _, messages, errors = session
    cmd.do("pseudoatom pt, pos=[1,2,3]")
    errors.clear()
    cmd.do("count_atoms 148l and name CA")
    assert errors == []
    assert messages[-1] == "165"


def test_pseudoatom_appends_to_an_existing_object(session):
    cmd, view, _, errors = session
    before = len(view._atoms)
    cmd.do("pseudoatom 148l, pos=[9,9,9]")
    assert errors == []
    assert len(view._atoms) == before + 1


def test_copy_makes_an_independent_object(session):
    """`copy_object` used `copied.id`, which the entry does not have."""
    cmd, view, _, errors = session
    cmd.do("copy dup, 148l")
    assert errors == []
    ids = {o["name"]: o["id"] for o in view.list_objects()}
    assert "dup" in ids
    source = view._objects[ids["148l"]].state.atoms
    duplicate = view._objects[ids["dup"]].state.atoms
    assert np.allclose(source["xyz"], duplicate["xyz"])
    assert not np.shares_memory(source["xyz"], duplicate["xyz"])


def test_editing_a_copy_leaves_the_original_alone(session):
    """The point of copying; a shared array would make the two indistinguishable."""
    cmd, view, _, _ = session
    cmd.do("copy dup, 148l")
    ids = {o["name"]: o["id"] for o in view.list_objects()}
    before = np.asarray(view._objects[ids["148l"]].state.atoms["xyz"]).copy()
    cmd.do("alter_state 1, dup, x = x + 100")
    assert np.allclose(view._objects[ids["148l"]].state.atoms["xyz"], before)


def test_copy_reports_a_failure_rather_than_half_doing_it(session):
    cmd, _, _, errors = session
    cmd.do("copy dup, nosuchobject")
    assert errors and "Unknown source object" in errors[-1]


def test_as_accepts_a_selection(session):
    """PyMOL's `as` takes one; rejecting it made every such script a syntax error."""
    cmd, _, _, errors = session
    cmd.do("as sticks, resn NAG")
    assert errors == []


def test_as_without_a_selection_still_works(session):
    cmd, _, _, errors = session
    cmd.do("as cartoon")
    assert errors == []
