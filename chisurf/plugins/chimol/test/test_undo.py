"""Coordinate undo, against PyMOL's per-object ring buffer.

PyMOL's ``undo`` is much narrower than the word suggests, and matching that scope
matters more than extending it: it is not a command history, it stores *coordinate*
snapshots per object in a ring of sixteen, and it refuses to restore one once the
atom count has changed. Promising more than that would be the wrong kind of
parity -- a user who expects ``undo`` to bring back a deleted object is better
served by being told no than by an undo that half works.

The walk is transcribed from ``ObjectMoleculeUndo``, which is not the obvious pair
of stacks: it writes the present state into the ring *before* stepping, so one ring
serves both directions. The tests below pin that reversibility, because a
two-stack implementation passes a single undo and then drifts.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.core.services.undo import UNDO_SLOTS, UndoRing

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


# --------------------------------------------------------------------------- #
# The ring, on its own
# --------------------------------------------------------------------------- #
class _State:
    """The minimum an undo snapshot needs: coordinates and an atom count."""

    def __init__(self, n: int = 4):
        self.coords = np.zeros((n, 3), dtype=float)
        self.all_atom_coords = np.zeros((n, 3), dtype=float)
        self.frames = None
        self.center = np.zeros(3, dtype=float)
        self.radius = 1.0
        self.atoms = np.zeros(n, dtype=[("xyz", float, (3,))])

    def shift(self, dx: float) -> None:
        self.coords[:, 0] += dx
        self.all_atom_coords[:, 0] += dx
        self.atoms["xyz"][:, 0] += dx

    @property
    def x(self) -> float:
        return float(self.all_atom_coords[:, 0].mean())


def test_the_ring_is_sixteen_deep():
    """``cUndoMask`` is 0xF in layer2/ObjectMolecule.h."""
    assert UNDO_SLOTS == 16
    assert len(UndoRing().slots) == 16


def test_a_push_then_an_undo_restores():
    ring, state = UndoRing(), _State()
    ring.push(state)
    state.shift(10.0)
    assert ring.step(state, -1) == "restored"
    assert state.x == pytest.approx(0.0)


def test_undo_and_redo_are_reversible():
    """The property a two-stack implementation loses.

    ``ObjectMoleculeUndo`` writes the present into the ring before stepping, so
    the same routine walks either way over one ring.
    """
    ring, state = UndoRing(), _State()
    ring.push(state)
    state.shift(10.0)

    assert ring.step(state, -1) == "restored"
    assert state.x == pytest.approx(0.0)
    assert ring.step(state, +1) == "restored"
    assert state.x == pytest.approx(10.0)
    assert ring.step(state, -1) == "restored"
    assert state.x == pytest.approx(0.0)


def test_an_empty_ring_says_so():
    """Distinct from a refused restore, because it means something different."""
    assert UndoRing().step(_State(), -1) == "empty"


def test_a_failed_step_leaves_the_coordinates_alone():
    ring, state = UndoRing(), _State()
    state.shift(7.0)
    assert ring.step(state, -1) == "empty"
    assert state.x == pytest.approx(7.0)


def test_a_changed_atom_count_is_refused():
    """PyMOL checks ``NIndex``: old coordinates cannot fill a resized object."""
    ring, state = UndoRing(), _State(4)
    ring.push(state)
    assert ring.step(_State(6), -1) == "resized"


def test_a_refused_step_does_not_consume_the_history():
    ring, state = UndoRing(), _State(4)
    ring.push(state)
    ring.step(_State(6), -1)
    state.shift(3.0)
    assert ring.step(state, -1) == "restored"


def test_several_edits_undo_in_order():
    ring, state = UndoRing(), _State()
    for _ in range(5):
        ring.push(state)
        state.shift(1.0)
    assert state.x == pytest.approx(5.0)
    for expected in (4.0, 3.0, 2.0, 1.0, 0.0):
        assert ring.step(state, -1) == "restored"
        assert state.x == pytest.approx(expected)
    assert ring.step(state, -1) == "empty"


def test_the_ring_holds_at_most_its_depth():
    """Beyond sixteen the oldest snapshot is overwritten, as a ring does."""
    ring, state = UndoRing(), _State()
    for _ in range(UNDO_SLOTS + 8):
        ring.push(state)
        state.shift(1.0)
    assert ring.depth() == UNDO_SLOTS


def test_a_snapshot_carries_every_derived_array():
    """Restoring only some would leave the object inconsistent.

    chimol derives the trace, the per-atom render positions and the atom array's
    Angstrom coordinates from the same edit, so an undo that moved the picture back
    while leaving what ``save`` writes stale would be worse than none.
    """
    ring, state = UndoRing(), _State()
    ring.push(state)
    state.shift(10.0)
    ring.step(state, -1)
    assert np.allclose(state.coords, 0.0)
    assert np.allclose(state.all_atom_coords, 0.0)
    assert np.allclose(state.atoms["xyz"], 0.0)


def test_a_state_without_coordinates_cannot_be_pushed():
    class _Bare:
        atoms = None

    assert UndoRing().push(_Bare()) is False


# --------------------------------------------------------------------------- #
# Through the commands
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    """Build a viewer with 148L loaded and a command interpreter over it."""
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.commands.command import Cmd
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import Viewer

    view = Viewer()
    view.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )

    class _Window:
        viewer = view

        def refresh_objects(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Window())
    messages: list[str] = []
    errors: list[str] = []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return cmd, view, messages, errors


def _x(view) -> float:
    return float(np.asarray(view._all_atom_coords, dtype=float)[:, 0].mean())


def test_translate_is_undoable(session):
    """The operations fill the ring, not the undo command."""
    cmd, view, _, errors = session
    start = _x(view)
    cmd.do("translate [100, 0, 0]")
    assert _x(view) != pytest.approx(start)

    cmd.do("undo")
    assert errors == []
    assert _x(view) == pytest.approx(start)


def test_redo_reapplies_it(session):
    cmd, view, _, errors = session
    cmd.do("translate [100, 0, 0]")
    moved = _x(view)
    cmd.do("undo")
    cmd.do("redo")
    assert errors == []
    assert _x(view) == pytest.approx(moved)


def test_an_empty_coordinate_ring_falls_through_to_the_object_list(session):
    """`undo` walks two stacks, and an empty ring is not an error.

    The coordinate ring is asked first -- it is the finer-grained of the two,
    and what a user who just dragged something means. With nothing on it the
    **object list** is undone instead, which is why an exhausted ring is no
    longer reported at all: it is what "nothing has been dragged" looks like,
    and the answer the user gets is about the object that goes away.
    """
    cmd, _, messages, errors = session
    cmd.do("undo")
    assert not errors, errors
    assert messages and "148l" in messages[-1], messages[-1:]


def test_nothing_to_undo_is_said_once_both_stacks_are_empty(session):
    """Said out loud, and not as a failure -- it is an ordinary answer."""
    cmd, _, messages, errors = session
    for _ in range(6):          # more than either stack holds
        cmd.do("undo")
    assert not errors, errors
    assert messages and "nothing to undo" in messages[-1]


def test_redo_with_no_history_is_reported(session):
    """Same for redo; see the note above."""
    cmd, _, messages, errors = session
    cmd.do("redo")
    assert not errors, errors
    assert messages and "nothing to redo" in messages[-1]


def test_several_translations_undo_one_at_a_time(session):
    cmd, view, messages, errors = session
    start = _x(view)
    for _ in range(3):
        cmd.do("translate [10, 0, 0]")

    for _ in range(3):
        errors.clear()
        cmd.do("undo")
        assert errors == []
    assert _x(view) == pytest.approx(start)

    # A fourth `undo` does *not* report an exhausted ring any more: it moves on
    # to the object list, and takes back the load itself. That the two stacks
    # are walked in that order is the contract; see
    # `test_an_empty_coordinate_ring_falls_through_to_the_object_list`.
    errors.clear()
    cmd.do("undo")
    assert not errors, errors
    assert messages and "148l" in messages[-1], messages[-1:]


def test_push_undo_stores_a_snapshot(session):
    cmd, view, messages, errors = session
    cmd.do("push_undo")
    assert errors == []
    assert view.undo_depth() == 1
    assert "snapshots stored" in messages[-1]


def test_an_explicit_snapshot_can_be_returned_to(session):
    cmd, view, _, errors = session
    start = _x(view)
    cmd.do("push_undo")
    cmd.do("translate [50, 0, 0]")
    cmd.do("undo")
    cmd.do("undo")
    assert _x(view) == pytest.approx(start)


def test_undo_after_extract_is_refused_with_a_reason(session):
    """An atom count that changed is not the same as an empty history."""
    cmd, view, _, errors = session
    cmd.do("translate [5, 0, 0]")
    cmd.do("extract lig, resn NAG")
    errors.clear()
    cmd.do("undo")
    assert errors and "atom count has changed" in errors[-1]


def test_history_is_per_object(session):
    """PyMOL's ring lives on the object, so one object's edits are its own."""
    cmd, view, _, errors = session
    cmd.do("create copy, polymer")
    cmd.do("translate [30, 0, 0]")

    active = view.get_active_object_id()
    other = next(
        o["id"] for o in view.list_objects() if str(o["id"]) != str(active)
    )
    assert view.undo_depth(object_id=active) >= 1
    assert view.undo_depth(object_id=other) == 0
