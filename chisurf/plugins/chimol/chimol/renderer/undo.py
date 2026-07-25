"""Coordinate undo, transcribed from PyMOL's per-object ring buffer.

PyMOL's ``undo`` is much narrower than the word suggests, and matching that scope
is the point of this module. It is **not** a command history: it does not undo a
colour, a representation, a deletion or a loaded object. It stores *coordinate
snapshots*, per object, in a ring of sixteen slots (``cUndoMask = 0xF`` in
``layer2/ObjectMolecule.h``), and restores one only when the atom count still
matches. Anything that changes the number of atoms is outside it.

The walk is the part worth transcribing exactly, because it is not the obvious
stack pair. ``ObjectMoleculeUndo`` does three things in order:

1. write the *current* coordinates into the current slot,
2. step the iterator by ``dir`` (wrapping in the ring), backing off if that slot
   is empty,
3. restore that slot's snapshot and clear it.

Because step 1 always leaves the present state behind before moving, one ring
serves both directions: undo and redo are the same routine with ``dir`` of −1 and
+1. Two separate stacks would need explicit transfer between them and would drift
apart the first time a new edit landed mid-history.

chimol keeps several arrays derived from the same coordinates -- the CA trace, the
per-atom render-space positions, the atom array's true Angstrom coordinates -- so a
snapshot has to carry all of them or an undo would restore the picture while
leaving what ``save`` writes stale, which is worse than not undoing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = ["UNDO_SLOTS", "CoordinateSnapshot", "UndoRing"]

#: Ring depth. ``cUndoMask`` is ``0xF``, so sixteen slots.
UNDO_SLOTS = 16

#: The state fields a snapshot captures. Every one of these is derived from the
#: same coordinates, and restoring a subset would leave the object inconsistent:
#: the view would move back while an export still wrote the transformed atoms.
_COORDINATE_FIELDS = (
    "coords",
    "all_atom_coords",
    "frames",
    "center",
    "radius",
)


@dataclass
class CoordinateSnapshot:
    """One slot of the ring: an object's coordinates at a moment.

    Attributes
    ----------
    arrays : dict
        Copies of the coordinate-bearing state fields.
    atom_xyz : numpy.ndarray or None
        The atom array's own coordinates, in Angstrom.
    n_atoms : int
        Atom count when the snapshot was taken. A snapshot is only restored when
        this still matches, exactly as ``ObjectMoleculeUndo`` checks ``NIndex``:
        pouring old coordinates into a differently sized object would corrupt it.
    """

    arrays: dict
    atom_xyz: np.ndarray | None
    n_atoms: int


@dataclass
class UndoRing:
    """A ring of coordinate snapshots for one object.

    Attributes
    ----------
    slots : list
        ``UNDO_SLOTS`` entries, each a :class:`CoordinateSnapshot` or ``None``.
    iterator : int
        Position in the ring, matching PyMOL's ``UndoIter``.
    """

    slots: list = field(
        default_factory=lambda: [None] * UNDO_SLOTS
    )
    iterator: int = 0

    def push(self, state) -> bool:
        """Store the current coordinates, as ``ObjectMoleculeSaveUndo`` does.

        Parameters
        ----------
        state
            The object's render state.

        Returns
        -------
        bool
            False when the state carries no coordinates to snapshot.
        """
        snapshot = _capture(state)
        if snapshot is None:
            return False
        self.slots[self.iterator] = snapshot
        self.iterator = (self.iterator + 1) % UNDO_SLOTS
        return True

    def step(self, state, direction: int) -> str:
        """Undo (``direction`` −1) or redo (+1), swapping the present into the ring.

        Parameters
        ----------
        state
            The object's render state, modified in place on success.
        direction : int
            −1 to undo, +1 to redo.

        Returns
        -------
        str
            ``"restored"`` on success, ``"empty"`` when the ring holds nothing in
            that direction, or ``"resized"`` when the atom count has changed since
            the snapshot was taken. The two failures are reported separately
            because they mean different things to a user: an exhausted history is
            ordinary, a refused restore is not.
        """
        # Leave the present behind first, so one ring serves both directions. This
        # is why undo and redo are one routine rather than two stacks.
        self.slots[self.iterator] = _capture(state)

        step = 1 if direction >= 0 else -1
        self.iterator = (self.iterator + step) % UNDO_SLOTS
        if self.slots[self.iterator] is None:
            # Nothing that way; PyMOL backs the iterator off and does nothing.
            self.iterator = (self.iterator - step) % UNDO_SLOTS
            return "empty"

        snapshot = self.slots[self.iterator]
        if snapshot.n_atoms != _atom_count(state):
            self.iterator = (self.iterator - step) % UNDO_SLOTS
            return "resized"

        _restore(state, snapshot)
        self.slots[self.iterator] = None
        return "restored"

    def depth(self) -> int:
        """Return the number of filled slots, for reporting how much history exists."""
        return sum(1 for slot in self.slots if slot is not None)


def _atom_count(state) -> int:
    """Return the number of atoms the state currently holds."""
    atoms = getattr(state, "atoms", None)
    if atoms is not None:
        return int(len(atoms))
    coords = getattr(state, "all_atom_coords", None)
    return int(np.asarray(coords).shape[0]) if coords is not None else 0


def _capture(state) -> CoordinateSnapshot | None:
    """Copy every coordinate-bearing field out of a state."""
    arrays: dict = {}
    found = False
    for name in _COORDINATE_FIELDS:
        value = getattr(state, name, None)
        if value is None:
            arrays[name] = None
            continue
        if isinstance(value, np.ndarray):
            arrays[name] = value.copy()
            found = True
        else:
            arrays[name] = value

    atoms = getattr(state, "atoms", None)
    atom_xyz = None
    if atoms is not None and "xyz" in (atoms.dtype.names or ()):
        atom_xyz = np.asarray(atoms["xyz"], dtype=float).copy()
        found = True

    if not found:
        return None
    return CoordinateSnapshot(arrays, atom_xyz, _atom_count(state))


def _restore(state, snapshot: CoordinateSnapshot) -> None:
    """Write a snapshot back into a state, in place."""
    for name, value in snapshot.arrays.items():
        setattr(state, name, value.copy() if isinstance(value, np.ndarray) else value)

    if snapshot.atom_xyz is None:
        return
    atoms = getattr(state, "atoms", None)
    if atoms is None or "xyz" not in (atoms.dtype.names or ()):
        return
    # In place: the atom array carries names and numbers as well as coordinates,
    # and only the coordinates are being undone.
    atoms["xyz"] = snapshot.atom_xyz
