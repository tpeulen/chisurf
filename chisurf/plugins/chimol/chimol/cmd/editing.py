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

    @command("sort")
    def sort(self, object: str = "") -> None:
        """Reorder atoms canonically (PyMOL ``sort [object]``).

        Mainly needed after ``alter`` has changed the names the order depends on.
        With no argument every object is sorted.

        Parameters
        ----------
        object : str, optional
            Object to sort; all of them when omitted.

        Notes
        -----
        PyMOL's order puts the side chain **before** the carbonyl: ``N, CA, CB,
        CG, ..., C, O, OXT``, because a one-character ``C`` and ``O`` score 997
        and 998 in its priority table. That is not the order a PDB file is
        written in, so sorting a freshly loaded structure does change it.
        """
        from ..analysis.atom_order import permute_atom_state, sort_order

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        wanted = str(object).strip()
        targets = []
        if wanted:
            info = self._find_object_by_name(viewer, wanted)
            if info is None:
                self._emit_error(f"sort: no such object: {wanted}")
                return
            targets.append(str(info.get("id")))
        else:
            targets = [
                str(o.get("id")) for o in viewer.list_objects()
            ]

        total_moved = 0
        for object_id in targets:
            entry = viewer._objects.get(object_id)
            state = getattr(entry, "state", None)
            atoms = getattr(state, "atoms", None)
            if atoms is None or len(atoms) == 0:
                continue
            order = sort_order(atoms)
            if np.array_equal(order, np.arange(len(atoms))):
                continue
            permute_atom_state(state, order)
            total_moved += int((order != np.arange(len(atoms))).sum())
            self._rebuild_after_coordinate_change(viewer, object_id)

        if window is not None and hasattr(window, "_refresh_objects_from_viewer"):
            window._refresh_objects_from_viewer()
        if total_moved:
            self._emit_message(f"sort: {total_moved} atoms moved")
        else:
            self._emit_message("sort: already in order")

    @command("mask")
    def mask(self, selection: str = "all") -> None:
        """Make atoms unpickable (PyMOL ``mask``).

        Useful when one molecule sits in front of another and you want to stop
        clicking through to the one behind.

        Parameters
        ----------
        selection : str, optional
            Atoms to mask; everything by default.
        """
        self._set_masking(str(selection), masked=True)

    @command("unmask")
    def unmask(self, selection: str = "all") -> None:
        """Make atoms pickable again (PyMOL ``unmask``).

        Parameters
        ----------
        selection : str, optional
            Atoms to unmask; everything by default.
        """
        self._set_masking(str(selection), masked=False)

    def _set_masking(self, selection: str, *, masked: bool) -> None:
        verb = "mask" if masked else "unmask"
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        try:
            obj_id, obj_name, sel_mask = self._resolve_selection_to_atom_mask(
                viewer, selection or "all"
            )
        except Exception as exc:
            self._emit_error(f"{verb}: {exc}")
            return

        entry = viewer._objects.get(obj_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None:
            self._emit_error(f"{verb}: {obj_name} carries no atoms")
            return

        sel_mask = np.asarray(sel_mask, dtype=bool)
        current = entry.state.masked_mask
        if current is None or np.asarray(current).shape[0] != len(atoms):
            current = np.zeros(len(atoms), dtype=bool)
        else:
            current = np.asarray(current, dtype=bool).copy()
        current[sel_mask] = masked
        entry.state.masked_mask = current
        self._emit_message(
            f"{verb}: {int(sel_mask.sum())} atoms; "
            f"{int(current.sum())} now unpickable in {obj_name}"
        )

    @command("protect")
    def protect(self, selection: str = "all") -> None:
        """Hold atoms still during transforms (PyMOL ``protect``).

        ``protect`` then ``translate`` moves everything *except* the protected
        atoms, which is how part of a structure is moved while the rest stays.

        Parameters
        ----------
        selection : str, optional
            Atoms to hold; everything by default.
        """
        self._set_protection(str(selection), protected=True)

    @command("deprotect")
    def deprotect(self, selection: str = "all") -> None:
        """Release atoms held by ``protect`` (PyMOL ``deprotect``).

        Parameters
        ----------
        selection : str, optional
            Atoms to release; everything by default.
        """
        self._set_protection(str(selection), protected=False)

    def _set_protection(self, selection: str, *, protected: bool) -> None:
        verb = "protect" if protected else "deprotect"
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        try:
            obj_id, obj_name, mask = self._resolve_selection_to_atom_mask(
                viewer, selection or "all"
            )
        except Exception as exc:
            self._emit_error(f"{verb}: {exc}")
            return

        entry = viewer._objects.get(obj_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None:
            self._emit_error(f"{verb}: {obj_name} carries no atoms")
            return

        mask = np.asarray(mask, dtype=bool)
        current = entry.state.protected_mask
        if current is None or np.asarray(current).shape[0] != len(atoms):
            current = np.zeros(len(atoms), dtype=bool)
        else:
            current = np.asarray(current, dtype=bool).copy()
        current[mask] = protected
        entry.state.protected_mask = current
        self._emit_message(
            f"{verb}: {int(mask.sum())} atoms; "
            f"{int(current.sum())} now protected in {obj_name}"
        )

    @command("smooth")
    def smooth(
        self,
        selection: str = "all",
        passes: str = "1",
        window: str = "5",
        first: str = "1",
        last: str = "0",
        ends: str = "0",
        cutoff: str = "-1",
    ) -> None:
        """Window-average the coordinate states (PyMOL ``smooth``).

        Suppresses high-frequency vibration in a trajectory so a movie shows the
        motion rather than the noise.

        Parameters
        ----------
        selection : str, optional
            Atoms to smooth; the rest keep their coordinates.
        passes : str, optional
            How many times to apply the average. Each pass reads the previous
            pass's output, so two passes differ from one wider window.
        window : str, optional
            Total window width, at least 2.
        first, last : str, optional
            State range, **1-based** as PyMOL's are; ``last=0`` means the end.
        ends : str, optional
            ``0`` leaves one state at each end alone, ``1`` smooths to the ends,
            ``2`` leaves a half-window, ``3`` wraps the trajectory.
        cutoff : str, optional
            Maximum distance an atom may move between states before the window
            stops extending; negative disables it.
        """
        from ..analysis.smoothing import smooth_frames

        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        try:
            n_passes = int(str(passes).strip() or 1)
            n_window = int(str(window).strip() or 5)
            n_first = int(str(first).strip() or 1)
            n_last = int(str(last).strip() or 0)
            n_ends = int(str(ends).strip() or 0)
            n_cutoff = float(str(cutoff).strip() or -1)
        except ValueError as exc:
            self._emit_error(f"smooth: {exc}")
            return

        try:
            obj_id, obj_name, mask = self._resolve_selection_to_atom_mask(
                viewer, selection or "all"
            )
        except Exception as exc:
            self._emit_error(f"smooth: {exc}")
            return

        entry = viewer._objects.get(obj_id)
        frames = getattr(getattr(entry, "state", None), "frames_raw", None)
        if frames is None:
            frames = getattr(getattr(entry, "state", None), "frames", None)
        if frames is None:
            self._emit_error(
                f"smooth: {obj_name} has a single state; smoothing averages "
                "over a trajectory"
            )
            return

        # PyMOL's first/last are 1-based and 0 means "the end"; the analysis
        # function works in 0-based indices like every other array here.
        zero_first = max(0, n_first - 1)
        zero_last = None if n_last <= 0 else n_last - 1
        try:
            smoothed = smooth_frames(
                np.asarray(frames, dtype=float),
                passes=n_passes,
                window=n_window,
                first=zero_first,
                last=zero_last,
                ends=n_ends,
                cutoff=n_cutoff,
                mask=np.asarray(mask, dtype=bool),
            )
        except ValueError as exc:
            self._emit_error(f"smooth: {exc}")
            return

        try:
            viewer.set_frames(smoothed, object_id=obj_id)
        except Exception as exc:
            self._emit_error(f"smooth: could not store the result: {exc}")
            return
        self._emit_message(
            f"smooth: {smoothed.shape[0]} states, window {n_window}, "
            f"{n_passes} pass{'es' if n_passes != 1 else ''} on {obj_name}"
        )

    @command("h_add")
    def h_add(self, selection: str = "all") -> None:
        """Add missing hydrogens (PyMOL ``h_add [selection]``).

        Parameters
        ----------
        selection : str, optional
            Atoms to hydrogenate; everything by default.

        Notes
        -----
        Hydrogen counts come from a **residue template**, not from counting free
        valences. PyMOL works from bond valences and warns in ``h_add``'s own
        help that PDB files do not carry them; measured on a fully hydrogenated
        protein, ``valence - heavy neighbours`` is wrong for 41.6% of atoms,
        because a double bond looks like a free valence when no orders are known.
        A residue without a template is **reported** rather than guessed at.

        Histidine is treated as ND1-protonated unless the file already carries a
        hydrogen on NE2. Without any hydrogens to go on, the tautomer cannot be
        determined from coordinates -- so it is stated rather than implied.
        """
        self._add_hydrogens(str(selection), reposition=False)

    @command("h_fill")
    def h_fill(self, selection: str = "all") -> None:
        """Replace the hydrogens on a selection (PyMOL ``h_fill``).

        Existing hydrogens are removed and put back at the template geometry,
        which is what makes it useful after moving a heavy atom: ``h_add`` leaves
        an already-hydrogenated atom alone, ``h_fill`` re-places it.

        Parameters
        ----------
        selection : str, optional
            Atoms whose hydrogens should be replaced.
        """
        self._add_hydrogens(str(selection), reposition=True)

    def _add_hydrogens(self, selection: str, *, reposition: bool) -> None:
        """Shared body of ``h_add`` and ``h_fill``."""
        from ..analysis.hydrogens import TAUTOMER_NOTES, plan_hydrogens

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        verb = "h_fill" if reposition else "h_add"

        try:
            obj_id, obj_name, mask = self._resolve_selection_to_atom_mask(
                viewer, selection or "all"
            )
        except Exception as exc:
            self._emit_error(f"{verb}: {exc}")
            return

        entry = viewer._objects.get(obj_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None:
            self._emit_error(f"{verb}: {obj_name} carries no atoms")
            return

        mask = np.asarray(mask, dtype=bool)
        elements = np.char.strip(np.asarray(atoms["element"]).astype(str))
        is_hydrogen = np.char.upper(elements) == "H"

        if reposition:
            # Drop the selection's hydrogens first, so the plan places all of
            # them rather than topping up whatever happened to be there.
            doomed = mask & is_hydrogen
            # A hydrogen bonded to a selected heavy atom also goes, or moving the
            # parent leaves its hydrogens behind.
            parents = set(np.nonzero(mask & ~is_hydrogen)[0].tolist())
            with viewer._activate_object(obj_id):
                for a, b in viewer.bond_list():
                    for x, y in ((a, b), (b, a)):
                        if int(x) in parents and is_hydrogen[int(y)]:
                            doomed[int(y)] = True
            if doomed.any():
                keep = ~doomed
                entry.state.atoms = atoms[keep].copy()
                # Every array indexed by atom has to follow, which
                # _rebuild_after_coordinate_change does from the atom array.
                self._rebuild_after_coordinate_change(viewer, obj_id)
                atoms = entry.state.atoms
                mask = mask[keep]

        with viewer._activate_object(obj_id):
            bonds = viewer.bond_list()
        plan, unknown = plan_hydrogens(atoms, bonds, mask)

        if not plan:
            note = ""
            if unknown:
                note = "; no template for " + ", ".join(sorted(unknown))
            self._emit_message(f"{verb}: nothing to add to {obj_name}{note}")
            return

        # One block of new atoms, appended in the object's own dtype so the
        # result is compatible with everything that reads atoms.
        additions = np.zeros(len(plan), dtype=atoms.dtype)
        names = atoms.dtype.names or ()
        for k, item in enumerate(plan):
            parent = atoms[item["parent"]]
            for field_name in names:
                # Inherit the parent's residue identity, then override.
                additions[field_name][k] = parent[field_name]
            if "xyz" in names:
                additions["xyz"][k] = item["xyz"]
            if "atom_name" in names:
                additions["atom_name"][k] = item["name"]
            if "element" in names:
                additions["element"][k] = "H"
            if "radius" in names:
                additions["radius"][k] = 1.2
            if "mass" in names:
                additions["mass"][k] = 1.008
            if "atom_id" in names:
                additions["atom_id"][k] = int(len(atoms)) + k + 1
            if "i" in names:
                additions["i"][k] = int(len(atoms)) + k

        entry.state.atoms = np.concatenate([atoms, additions])
        self._rebuild_after_coordinate_change(viewer, obj_id)
        if window is not None and hasattr(window, "_refresh_objects_from_viewer"):
            window._refresh_objects_from_viewer()

        message = f"{verb}: added {len(plan)} hydrogens to {obj_name}"
        self._emit_message(message)
        if unknown:
            # Named, not silently skipped: a ligand left unhydrogenated is a
            # result the user has to know about.
            self._emit_message(
                f"{verb}: no template for "
                + ", ".join(f"{k} ({v} atoms)" for k, v in sorted(unknown.items()))
                + " -- these need bond orders, which PDB files do not carry"
            )
        residues = set(
            np.char.strip(np.asarray(atoms["res_name"]).astype(str)).tolist()
        )
        for residue, note in TAUTOMER_NOTES.items():
            if residue in residues:
                self._emit_message(f"{verb}: {note}")

    @command("bond")
    def bond(self, atom1: str = "", atom2: str = "", order: str = "1") -> None:
        """Bond two atoms (PyMOL ``bond atom1, atom2 [, order]``).

        Each selection must match exactly one atom, and both must be in the same
        object -- PyMOL's own restriction, since a bond is stored inside an
        object's connectivity table and cannot span two.

        Repeating ``bond`` on an already-bonded pair sets its order, which is how
        a single bond is promoted to a double one.

        Parameters
        ----------
        atom1, atom2 : str
            Selections, each matching one atom.
        order : str, optional
            Bond order, 1 by default.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        if not str(atom1).strip() or not str(atom2).strip():
            self._emit_error("Usage: bond atom1, atom2 [, order]")
            return
        try:
            order_value = int(str(order).strip() or 1)
        except ValueError:
            self._emit_error(f"bond: order must be a whole number, not {order!r}")
            return

        picked = self._one_atom_each(viewer, atom1, atom2)
        if picked is None:
            return
        obj_name, i, j = picked
        if i == j:
            # add_bond also refuses, but it answers False for "already bonded"
            # too, and reporting that here would be a plainly wrong diagnosis.
            self._emit_error(
                f"bond: both selections matched the same atom ({i}); "
                "an atom cannot be bonded to itself"
            )
            return

        if viewer.add_bond(i, j, order_value):
            self._emit_message(
                f"bond: {obj_name} atoms {i} and {j} bonded"
                + (f" (order {order_value})" if order_value != 1 else "")
            )
        else:
            self._emit_message(
                f"bond: {obj_name} atoms {i} and {j} were already bonded; "
                f"order set to {order_value}"
            )

    @command("unbond")
    def unbond(self, atom1: str = "", atom2: str = "") -> None:
        """Remove every bond between two selections (PyMOL ``unbond``).

        Unlike ``bond`` this takes selections of any size and removes *all*
        bonds running between them, which is what PyMOL documents. Pairs that
        are not bonded are simply not affected.

        Parameters
        ----------
        atom1, atom2 : str
            Selections; every bond from one to the other is removed.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        if not str(atom1).strip() or not str(atom2).strip():
            self._emit_error("Usage: unbond atom1, atom2")
            return

        try:
            id1, name1, mask1 = self._resolve_selection_to_atom_mask(
                viewer, str(atom1)
            )
            id2, name2, mask2 = self._resolve_selection_to_atom_mask(
                viewer, str(atom2)
            )
        except Exception as exc:
            self._emit_error(f"unbond: {exc}")
            return

        if id1 != id2:
            self._emit_error(
                f"unbond: '{name1}' and '{name2}' are different objects; "
                "a bond exists inside one object"
            )
            return

        first = set(np.nonzero(np.asarray(mask1, dtype=bool))[0].tolist())
        second = set(np.nonzero(np.asarray(mask2, dtype=bool))[0].tolist())
        if not first or not second:
            self._emit_error("unbond: a selection matched no atoms")
            return

        with viewer._activate_object(id1):
            # Only bonds that actually run between the two selections, in either
            # direction -- not the cross product, which would try to remove
            # bonds that were never there.
            doomed = [
                (int(a), int(b))
                for a, b in viewer.bond_list()
                if (int(a) in first and int(b) in second)
                or (int(b) in first and int(a) in second)
            ]
            gone = viewer.remove_bonds(doomed)
        self._emit_message(f"unbond: {gone} bonds removed from {name1}")

    @command("get_bonds", aliases=("get_bond_list",))
    def get_bonds(self, selection: str = "all") -> list[tuple[int, int, int]]:
        """List the bonds within a selection (PyMOL ``get_bonds``).

        Parameters
        ----------
        selection : str, optional
            Atoms to report bonds for; both ends must be inside it.

        Returns
        -------
        list of tuple
            ``(atm1, atm2, order)`` triples.

        Notes
        -----
        ``atm1``/``atm2`` are **0-based positions within the selection**, not the
        ``index`` property -- PyMOL says the same, in capitals, because the two
        coincide for ``all`` and diverge for everything else, which is exactly
        the kind of difference that is discovered late.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return []
        try:
            obj_id, obj_name, mask = self._resolve_selection_to_atom_mask(
                viewer, str(selection).strip() or "all"
            )
        except Exception as exc:
            self._emit_error(f"get_bonds: {exc}")
            return []

        chosen = np.nonzero(np.asarray(mask, dtype=bool))[0]
        if chosen.size == 0:
            self._emit_error(f"get_bonds: '{selection}' matched no atoms")
            return []
        # Position within the selection, which is what the indices mean.
        position = {int(a): k for k, a in enumerate(chosen)}

        with viewer._activate_object(obj_id):
            out = [
                (position[int(a)], position[int(b)], viewer.bond_order(a, b))
                for a, b in viewer.bond_list()
                if int(a) in position and int(b) in position
            ]
        return out

    def _one_atom_each(
        self, viewer, atom1: str, atom2: str
    ) -> tuple[str, int, int] | None:
        """Resolve two one-atom selections in the same object to their indices.

        Returns None and reports why when either selection is not exactly one
        atom, or when the two land in different objects.
        """
        resolved = []
        for text in (atom1, atom2):
            try:
                obj_id, obj_name, mask = self._resolve_selection_to_atom_mask(
                    viewer, str(text)
                )
            except Exception as exc:
                self._emit_error(f"bond: {exc}")
                return None
            hits = np.nonzero(np.asarray(mask, dtype=bool))[0]
            if hits.size != 1:
                self._emit_error(
                    f"bond: '{text}' matched {hits.size} atoms; "
                    "each selection must name exactly one"
                )
                return None
            resolved.append((obj_id, obj_name, int(hits[0])))

        (id1, name1, i), (id2, name2, j) = resolved
        if id1 != id2:
            self._emit_error(
                f"bond: '{name1}' and '{name2}' are different objects; "
                "both atoms must be in the same one"
            )
            return None
        return name1, i, j

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
