from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from ..analysis.labels import (
    ATOM_PROPERTIES,
    DERIVED_PROPERTIES,
    atom_namespace,
    evaluate_labels,
)
from .base import BaseCmd
from .registry import command

if TYPE_CHECKING:
    pass


#: The atom dtype every chisurf reader produces (``keys_formats`` in
#: ``chisurf/core/fio/structure/coordinates.py``). A pseudoatom has to match it,
#: or the object it creates is incompatible with everything that reads atoms.
PSEUDOATOM_DTYPE = np.dtype([
    ("i", "i4"),
    ("chain", "|U1"),
    ("res_id", "i4"),
    ("res_name", "|U5"),
    ("atom_id", "i4"),
    ("atom_name", "|U5"),
    ("element", "|U2"),
    ("xyz", "3f8"),
    ("charge", "f8"),
    ("radius", "f8"),
    ("bfactor", "f8"),
    ("mass", "f8"),
])


def _fmt(pos) -> str:
    """Format a position for a message."""
    return "(" + ", ".join(f"{float(v):.3f}" for v in pos) + ")"


def _pseudoatom_array(
    dtype: np.dtype,
    pos,
    bfactor: float,
    occupancy: float,
    res_id: int,
) -> np.ndarray:
    """Build a one-atom array in ``dtype``, filling only fields it has.

    Taking the dtype from the object being appended to, rather than assuming one,
    is what lets a pseudoatom join a structure read by any reader.
    """
    atom = np.zeros(1, dtype=dtype)
    values = {
        "xyz": np.asarray(pos, dtype=float),
        "atom_name": "PS1",
        "res_name": "PSD",
        "res_id": int(res_id),
        "chain": "P",
        "element": "P",
        "bfactor": float(bfactor),
        "occupancy": float(occupancy),
        "radius": 1.0,
        "mass": 0.0,
        "charge": 0.0,
    }
    for field_name, value in values.items():
        if field_name in (dtype.names or ()):
            atom[field_name][0] = value
    return atom


def _coerce_field(dtype: np.dtype, value: object):
    """Cast a value assigned in an expression to the atom field's own type.

    A structured array silently truncates or raises depending on the field, so the
    cast is done here where a bad assignment can be reported against the property
    the user actually named.
    """
    if dtype.kind in ("U", "S"):
        text = str(value)
        return text.encode() if dtype.kind == "S" else text
    if dtype.kind in ("i", "u"):
        return int(round(float(value)))
    return value


class EditingMixin(BaseCmd):
    """Commands that change what a structure *is*, rather than how it looks."""

    #: Namespace persisting across commands, so results can be accumulated the way
    #: PyMOL's ``pymol.stored`` is used: ``iterate name CA, stored.setdefault(...)``.
    #: Without somewhere to put them, ``iterate`` can only print.
    @property
    def _stored(self) -> dict:
        store = getattr(self, "_stored_namespace", None)
        if store is None:
            store = {}
            self._stored_namespace = store
        return store

    @command("pseudoatom")
    def pseudoatom(
        self,
        name: str = "",
        selection: str = "none",
        label: str = "",
        pos: str = "",
        b: float = 0.0,
        q: float = 1.0,
        color: str = "",
        state: int = 0,
        mode: str = "",
        quiet: bool = True,
    ) -> None:
        """Create/append a pseudoatom (PyMOL ``pseudoatom name[, selection, ...]``)."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        if not name:
             self._emit_error("pseudoatom name is required")
             return

        pos_val = pos
        b_factor = float(b) if b is not None else 0.0
        occupancy = float(q) if q is not None else 1.0

        pos: list[float] | None = None
        if isinstance(pos_val, str):
             if pos_val.startswith("[") and pos_val.endswith("]"):
                  try:
                       pos = [float(x) for x in pos_val[1:-1].replace(",", " ").split()]
                  except Exception:
                       pos = None
        elif isinstance(pos_val, (list, tuple)) and len(pos_val) == 3:
             pos = [float(x) for x in pos_val]

        # If selection center logic
        if not pos and selection.lower() != "none" and selection:
             try:
                  obj_id, _, mask = self._resolve_selection_to_atom_mask(viewer, selection)
                  entry = viewer._objects.get(obj_id)
                  if entry and entry.state.atoms is not None:
                       coords = entry.state.all_atom_coords[mask]
                       if coords.size > 0:
                            pos = np.mean(coords, axis=0).tolist()
             except Exception:
                  pass

        # One atom array shape, matching what every reader produces. This used to
        # build its own dtype naming `chain_id`, `b_factor` and `occupancy` -- none
        # of which are fields -- so the resulting object was incompatible with
        # everything downstream and the command crashed before it finished.
        if not pos:
            pos = [0.0, 0.0, 0.0]

        obj_info = self._find_object_by_name(viewer, name)
        if obj_info is None:
            atoms = _pseudoatom_array(PSEUDOATOM_DTYPE, pos, b_factor, occupancy, 1)

            class _Pseudo:
                """The shape :meth:`set_structure` reads."""

            structure = _Pseudo()
            structure.atoms = atoms
            structure.xyz = np.asarray(atoms["xyz"], dtype=float)
            structure.n_atoms = 1

            entry = viewer._create_object(name=name)
            viewer.set_active_object(entry.object_id)
            viewer.set_structure(structure)
            if window is not None and hasattr(window, "_refresh_objects_from_viewer"):
                window._refresh_objects_from_viewer()
            self._emit_message(f"pseudoatom: created {name} at {_fmt(pos)}")
            return

        object_id = str(obj_info["id"])
        entry = viewer._objects.get(object_id)
        existing = getattr(getattr(entry, "state", None), "atoms", None)
        if existing is None:
            self._emit_error(f"pseudoatom: {name} carries no atoms to append to")
            return

        next_res = int(np.max(existing["res_id"])) + 1 if len(existing) else 1
        addition = _pseudoatom_array(
            existing.dtype, pos, b_factor, occupancy, next_res
        )
        entry.state.atoms = np.concatenate([existing, addition])
        self._rebuild_after_coordinate_change(viewer, object_id)
        if window is not None and hasattr(window, "_refresh_objects_from_viewer"):
            window._refresh_objects_from_viewer()
        self._emit_message(
            f"pseudoatom: appended to {name} at {_fmt(pos)}"
        )
        return



    @command("label", mode="raw1")
    def label(self, selection: str = "", expression: str = "") -> None:
        """Label atoms with a Python expression (PyMOL ``label sel, expr``).

        The second argument is an **expression**, not a template: it is evaluated
        once per atom with that atom's properties in scope, so
        ``label name CA, "%s-%s" % (resn, resi)`` works exactly as it does in
        PyMOL. An empty expression clears, matching ``cmd.label(sel, "")``.

        Available names are PyMOL's: ``name``, ``resn``, ``resi``, ``chain``,
        ``segi``, ``elem``, ``b``, ``q``, ``vdw``, ``index``, ``oneletter`` and
        ``x``/``y``/``z``.
        """
        if not selection:
            self._emit_error('Usage: label <selection>, <expression>')
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        try:
            obj_id, _, atom_mask = self._resolve_selection_to_atom_mask(
                viewer, selection
            )
        except Exception as exc:
            self._emit_error(f"label: {exc}")
            return

        entry = viewer._objects.get(obj_id)
        state = getattr(entry, "state", None) if entry is not None else None
        atoms = getattr(state, "atoms", None)
        coords = getattr(state, "all_atom_coords", None)
        if atoms is None:
            self._emit_error("label: the object has no atoms")
            return

        expr = (expression or "").strip().strip('"').strip("'") \
            if (expression or "").strip() in ('""', "''") else (expression or "")
        if not expr.strip():
            viewer.clear_labels(object_id=obj_id)
            self._emit_message("Cleared labels")
            return

        try:
            indices, texts = evaluate_labels(atoms, coords, expr, atom_mask)
        except SyntaxError as exc:
            self._emit_error(f"label: could not parse {expr!r}: {exc}")
            return

        if not len(indices):
            self._emit_error(
                f"label: '{expr}' produced no labels "
                "(the expression may not apply to these atoms)"
            )
            return

        total = viewer.set_labels(indices, texts, object_id=obj_id)
        self._emit_message(f"Labelled {len(indices)} atoms ({total} in total)")

    @command("iterate", mode="raw1")
    def iterate(self, selection: str = "", expression: str = "") -> None:
        """Run a read-only Python statement per selected atom (PyMOL ``iterate``).

        The atom's properties are in scope under PyMOL's names -- ``name``,
        ``resn``, ``resi``, ``chain``, ``segi``, ``elem``, ``b``, ``q``, ``vdw``,
        ``index``, ``oneletter`` -- so published snippets work unchanged.
        Coordinates are **not** in scope; that is ``iterate_state``, as in PyMOL.

        A persistent ``stored`` namespace is available for accumulating results,
        which is what makes the command useful for pulling data out::

            iterate name CA, stored.setdefault('b', []).append(b)
        """
        self._alter_or_iterate(selection, expression, write=False, coordinates=False)

    @command("alter", mode="raw1")
    def alter(self, selection: str = "", expression: str = "") -> None:
        """Change atom properties per selected atom (PyMOL ``alter``).

        Assigning to a property name writes it back: ``alter chain E, b=42``.
        Coordinates cannot be changed here -- PyMOL keeps that in ``alter_state``,
        because moving atoms invalidates geometry that properties do not.
        """
        self._alter_or_iterate(selection, expression, write=True, coordinates=False)

    @command("iterate_state", mode="raw2")
    def iterate_state(
        self, state: str = "", selection: str = "", expression: str = ""
    ) -> None:
        """Run a read-only statement per atom, with coordinates in scope.

        ``iterate_state 1, name CA, stored.setdefault('xs', []).append(x)``.
        chimol holds one coordinate set per object, so the state argument is
        accepted for compatibility and only ``1`` (or ``0``, meaning "all") is
        meaningful.
        """
        if not self._check_state(state, "iterate_state"):
            return
        self._alter_or_iterate(selection, expression, write=False, coordinates=True)

    @command("alter_state", mode="raw2")
    def alter_state(
        self, state: str = "", selection: str = "", expression: str = ""
    ) -> None:
        """Change atom coordinates per selected atom (PyMOL ``alter_state``).

        ``alter_state 1, all, x = x + 10`` moves the selection ten Angstrom.
        Coordinates are in Angstrom in the structure's own frame; the render-space
        arrays are rebuilt afterwards, which is the step that makes this differ
        from ``alter``.
        """
        if not self._check_state(state, "alter_state"):
            return
        self._alter_or_iterate(selection, expression, write=True, coordinates=True)

    def _check_state(self, state: str, label: str) -> bool:
        """Accept PyMOL's state argument, which chimol has only one of."""
        text = str(state).strip()
        if not text:
            self._emit_error(f"Usage: {label} state, selection, expression")
            return False
        try:
            index = int(float(text))
        except ValueError:
            self._emit_error(f"{label}: state must be a number, got {state!r}")
            return False
        if index not in (0, 1, -1):
            self._emit_error(
                f"{label}: this object has one coordinate set, so state "
                f"{index} does not exist"
            )
            return False
        return True

    def _alter_or_iterate(
        self,
        sele_expr: str,
        python_expr: str,
        *,
        write: bool,
        coordinates: bool,
    ) -> None:
        """Run a Python statement once per selected atom.

        The four commands are one routine over two flags: ``write`` distinguishes
        ``alter`` from ``iterate``, ``coordinates`` distinguishes the ``_state``
        pair from the plain one. That split is PyMOL's, and it is not cosmetic --
        changing coordinates invalidates every array derived from them, and
        changing a b-factor does not.

        Parameters
        ----------
        sele_expr : str
            Selection expression.
        python_expr : str
            Python statement evaluated per atom.
        write : bool
            Persist assignments back to the atom array.
        coordinates : bool
            Put ``x``/``y``/``z`` in scope, and persist them when ``write``.
        """
        label = ("alter" if write else "iterate") + ("_state" if coordinates else "")
        if not sele_expr or not python_expr:
            self._emit_error(f"Usage: {label} selection, expression")
            return

        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        try:
            obj_id, obj_name, atom_mask = self._resolve_selection_to_atom_mask(
                viewer, sele_expr
            )
        except Exception as exc:
            self._emit_error(f"{label}: {exc}")
            return

        entry = viewer._objects.get(obj_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None:
            self._emit_error(f"{label}: object {obj_name} has no atoms")
            return

        indices = np.nonzero(np.asarray(atom_mask, dtype=bool))[0]
        if indices.size == 0:
            self._emit_error(f"{label}: '{sele_expr}' matched no atoms")
            return

        # Only fields this structure actually carries, so an assignment to one it
        # lacks is reported rather than silently dropped.
        fields = set(atoms.dtype.names or ())
        writable = {
            name: field
            for name, field in ATOM_PROPERTIES.items()
            if field in fields
        }

        try:
            code = compile(python_expr, "<chimol>", "exec")
        except SyntaxError as exc:
            self._emit_error(f"{label}: could not parse {python_expr!r}: {exc}")
            return

        xyz = np.asarray(atoms["xyz"], dtype=float) if "xyz" in fields else None
        globals_ = {"stored": self._stored, "np": np}
        changed_fields: set[str] = set()
        moved = False
        ignored: set[str] = set()
        count = 0

        try:
            for index in indices:
                namespace = atom_namespace(
                    atoms, int(index), xyz if coordinates else None
                )
                before = dict(namespace)

                exec(code, globals_, namespace)  # noqa: S102 -- PyMOL's API is Python
                count += 1

                if not write:
                    continue

                for name, value in namespace.items():
                    if name not in before or value == before[name]:
                        continue
                    if coordinates and name in ("x", "y", "z"):
                        xyz[index, "xyz".index(name)] = float(value)
                        moved = True
                        continue
                    field = writable.get(name)
                    if field is None:
                        # Either a derived name, or one this structure lacks.
                        if name in DERIVED_PROPERTIES or name in ATOM_PROPERTIES:
                            ignored.add(name)
                        continue
                    atoms[field][index] = _coerce_field(atoms.dtype[field], value)
                    changed_fields.add(field)
        except NameError as exc:
            # The commonest mistake is reaching for a coordinate from `alter`,
            # where PyMOL does not put one in scope. Say which command does.
            if not coordinates and any(
                f"'{axis}'" in str(exc) for axis in ("x", "y", "z")
            ):
                self._emit_error(
                    f"{label}: coordinates are not in scope here -- use "
                    f"{'alter_state' if write else 'iterate_state'}, as in PyMOL"
                )
            else:
                self._emit_error(f"{label}: {exc}")
            return
        except Exception as exc:
            self._emit_error(f"{label}: {type(exc).__name__} at atom {count}: {exc}")
            return

        if write and moved:
            atoms["xyz"] = xyz
            self._rebuild_after_coordinate_change(viewer, obj_id)
        elif write and changed_fields:
            # Properties only: the geometry is untouched, so nothing derived from
            # coordinates may be recomputed. Assigning raw Angstrom into the
            # render-space array here shrank the molecule tenfold and moved it off
            # centre on every `alter`, however innocent.
            viewer._update_view()

        if ignored:
            self._emit_error(
                f"{label}: cannot write {', '.join(sorted(ignored))} -- "
                + (
                    "coordinates need alter_state"
                    if ignored & {"x", "y", "z"}
                    else "this structure has no such field"
                )
            )

        verb = "Iterated over" if not write else "Altered"
        detail = ""
        if write:
            parts = sorted(changed_fields) + (["coordinates"] if moved else [])
            detail = f" ({', '.join(parts)})" if parts else " (nothing changed)"
        self._emit_message(f"{verb} {count} atoms{detail}")

    def _rebuild_after_coordinate_change(self, viewer, object_id: str) -> None:
        """Re-derive everything that depends on coordinates, after moving atoms.

        The render-space positions, the backbone trace, the bond list and the
        bounding sphere are all functions of the coordinates, so a moved atom
        invalidates them together. ``set_structure`` is the one path that rebuilds
        the lot; the secondary structure is carried across it by hand, since which
        residue is a helix does not depend on where the molecule sits.
        """
        entry = viewer._objects.get(object_id)
        state = getattr(entry, "state", None)
        if state is None:
            return
        secondary = getattr(state, "secondary_structure", None)

        # A detached holder, not the live state: `set_structure` begins by
        # clearing the active object's arrays, so handing it that same object
        # nulls the atoms it is about to read and it reports an unsupported type.
        class _Rebuilt:
            """The shape :meth:`set_structure` reads: an atoms array."""

        rebuilt = _Rebuilt()
        rebuilt.atoms = state.atoms
        rebuilt.xyz = np.asarray(state.atoms["xyz"], dtype=float)
        rebuilt.n_atoms = int(len(state.atoms))

        with viewer._activate_object(object_id):
            viewer.set_structure(rebuilt)
            if secondary is not None:
                viewer._secondary_structure = secondary
        viewer._update_view()

    @command("remove", aliases=("rm",))
    def remove(self, selection: str = "") -> None:
        """Delete the atoms matched by ``selection``."""
        if not selection:
            self._emit_error("Usage: remove selection")
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        try:
            obj_id, obj_name, atom_mask = self._resolve_selection_to_atom_mask(
                viewer, selection
            )
        except Exception as exc:
            self._emit_error(str(exc))
            return

        entry = viewer._objects.get(obj_id)
        if entry is None or entry.state.atoms is None:
            return

        keep_mask = ~atom_mask
        if np.all(keep_mask):
            return

        removed = int(np.sum(atom_mask))

        if not np.any(keep_mask):
            # PyMOL keeps the object and empties it rather than deleting it, so
            # a mistaken `remove all` is undone by reloading rather than by
            # rebuilding the session.
            entry.state.atoms = np.array([], dtype=entry.state.atoms.dtype)
            entry.state.all_atom_coords = None
            entry.state.coords = None
            viewer._update_view()
            self._emit_message(f"Removed {removed} atoms from {obj_name} (now empty)")
            return

        entry.state.atoms = entry.state.atoms[keep_mask].copy()

        # Every per-atom mask has to shrink with the array, or the next redraw
        # indexes past the end of it.
        for name in ("ball_mask", "sticks_mask", "cartoon_mask"):
            mask = getattr(entry.state, name, None)
            if mask is not None and len(mask) == len(keep_mask):
                setattr(entry.state, name, np.asarray(mask)[keep_mask].copy())

        # Everything derived from the coordinates -- the render-space positions,
        # the trace, the bonds, the bounding sphere -- is now stale. This used to
        # assign the raw Angstrom coordinates straight into the render array
        # (which is scaled and centred) and then hand `set_structure` the live
        # state, which begins by clearing the very arrays it is about to read.
        self._rebuild_after_coordinate_change(viewer, obj_id)

        self._emit_message(f"Removed {removed} atoms from {obj_name}")
