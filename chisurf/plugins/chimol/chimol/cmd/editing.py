from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from ..analysis.labels import evaluate_labels
from .base import BaseCmd
from .registry import command

if TYPE_CHECKING:
    pass

class EditingMixin(BaseCmd):
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

        if not pos:
             pos = [0.0, 0.0, 0.0]

        # In ChiMol, we often want to add this to a new object or an existing one.
        # PyMOL adds it to 'name' object. If 'name' exists, it appends an atom.

        obj_info = self._find_object_by_name(viewer, name)
        if obj_info is None:
             # Create new object with one atom
             @dataclass
             class DummyStructure:
                  atoms: np.ndarray
                  xyz: np.ndarray

             atom_dtype = [
                 ('xyz', 'f4', (3,)),
                 ('atom_name', 'S10'),
                 ('res_id', 'i4'),
                 ('res_name', 'S10'),
                 ('chain_id', 'S4'),
                 ('element', 'S2'),
                 ('b_factor', 'f4'),
                 ('occupancy', 'f4')
             ]

             data = np.zeros(1, dtype=atom_dtype)
             data[0]['xyz'] = pos
             data[0]['atom_name'] = b'PS1'
             data[0]['res_id'] = 1
             data[0]['res_name'] = b'PSD'
             data[0]['chain_id'] = b' '
             data[0]['element'] = b'Ps'
             data[0]['b_factor'] = b_factor
             data[0]['occupancy'] = occupancy

             struct = DummyStructure(atoms=data, xyz=data['xyz'])

             # Need to create object via window if possible to get registry/etc.
             if window is not None and hasattr(window, "_load_structure_from_path"):
                  # This is a bit hacky, but MolView doesn't easily create objects from memory via commands yet.
                  # Let's use viewer directly and hope the window refreshes.
                  oid = viewer._create_object(name=name)
                  viewer.set_active_object(oid)
                  viewer.set_structure(struct)
                  window._refresh_objects_from_viewer()
             else:
                  oid = viewer._create_object(name=name)
                  viewer.set_active_object(oid)
                  viewer.set_structure(struct)
        else:
             # Append to existing object
             oid = str(obj_info['id'])
             entry = viewer._objects.get(oid)
             if entry and entry.state.atoms is not None:
                  old_atoms = entry.state.atoms
                  new_atom = np.zeros(1, dtype=old_atoms.dtype)
                  for f in old_atoms.dtype.names:
                       if f == 'xyz': new_atom[0][f] = pos
                       elif f == 'atom_name': new_atom[0][f] = b'PS1'
                       elif f == 'res_id':
                            if len(old_atoms) > 0:
                                 new_atom[0][f] = np.max(old_atoms['res_id']) + 1
                            else:
                                 new_atom[0][f] = 1
                       elif f == 'res_name': new_atom[0][f] = b'PSD'
                       elif f == 'b_factor': new_atom[0][f] = b_factor
                       elif f == 'occupancy': new_atom[0][f] = occupancy
                       else:
                            # default to what's in first atom or zero/empty
                            if len(old_atoms) > 0:
                                 new_atom[0][f] = old_atoms[0][f]

                  entry.state.atoms = np.concatenate([old_atoms, new_atom])
                  entry.state.all_atom_coords = entry.state.atoms['xyz'].copy()

                  # Re-run set_structure logic to update trace/masks
                  viewer.set_structure(entry.state)

        self._emit_message(f"Created pseudoatom {name} at {pos}")


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
        """Evaluate a read-only Python expression per selected atom."""
        self._alter_or_iterate(selection, expression, read_only=True)

    @command("alter", mode="raw1")
    def alter(self, selection: str = "", expression: str = "") -> None:
        """Evaluate a Python expression per selected atom, writing changes back."""
        self._alter_or_iterate(selection, expression, read_only=False)

    def _alter_or_iterate(
        self, sele_expr: str, python_expr: str, read_only: bool
    ) -> None:
        cmd = "iterate" if read_only else "alter"
        if not sele_expr or not python_expr:
            self._emit_error(f"Usage: {cmd} selection, expression")
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        try:
            obj_id, obj_name, atom_mask = self._resolve_selection_to_atom_mask(
                viewer, sele_expr
            )
        except Exception as exc:
            self._emit_error(str(exc))
            return

        entry = viewer._objects.get(obj_id)
        if entry is None or entry.state.atoms is None:
            self._emit_error(f"Object {obj_name} has no atoms")
            return

        atoms = entry.state.atoms
        indices = np.nonzero(atom_mask)[0]
        if indices.size == 0:
            return

        # Prepare namespace
        # We need to map field names to friendly names
        field_map = {
            "atom_name": "name",
            "res_name": "resn",
            "res_id": "resi",
            "chain_id": "chain",
            "element": "elem",
            "b_factor": "b",
            "occupancy": "q",
        }

        # Reverse map for alter
        reverse_map = {v: k for k, v in field_map.items()}

        count = 0
        try:
            # Compiled expression for speed if many atoms
            code = compile(python_expr, "<string>", "exec")

            for idx in indices:
                atom = atoms[idx]
                namespace = {}

                # Load current values
                for f, alias in field_map.items():
                    if f in atoms.dtype.names:
                        val = atom[f]
                        if isinstance(val, (bytes, np.bytes_)):
                             val = val.decode()
                        namespace[alias] = val

                xyz = atom["xyz"]
                namespace["x"] = float(xyz[0])
                namespace["y"] = float(xyz[1])
                namespace["z"] = float(xyz[2])

                exec(code, {}, namespace)

                if not read_only:
                    # Save changed values
                    for alias, f in reverse_map.items():
                        if alias in namespace and f in atoms.dtype.names:
                            val = namespace[alias]
                            # Handle types (int, float, string)
                            target_dtype = atoms.dtype[f]
                            if target_dtype.kind in ('S', 'U'):
                                if isinstance(val, str):
                                    atom[f] = val.encode() if target_dtype.kind == 'S' else val
                            else:
                                atom[f] = val

                    # Coordinates
                    new_x = namespace.get("x", xyz[0])
                    new_y = namespace.get("y", xyz[1])
                    new_z = namespace.get("z", xyz[2])
                    atom["xyz"] = [new_x, new_y, new_z]

                count += 1

        except Exception as exc:
            self._emit_error(f"Error during execution: {exc}")
            return

        if not read_only:
            # If we altered, we need to notify the viewer to rebuild
            # Actually, the 'atoms' array in state might be the same object
            # but we should re-trigger updates.
            # We might also need to update all_atom_coords if that was cached separately
            if "xyz" in atoms.dtype.names:
                 entry.state.all_atom_coords = atoms["xyz"].copy()

            viewer._update_view()

        verb = "Iterated over" if read_only else "Altered"
        self._emit_message(f"{verb} {count} atoms")

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

        if not np.any(keep_mask):
            # Remove entire object? Or just clear it?
            # PyMOL usually keeps the object but it's empty.
            # Here we'll just clear atoms.
            entry.state.atoms = np.array([], dtype=entry.state.atoms.dtype)
            entry.state.all_atom_coords = None
        else:
            entry.state.atoms = entry.state.atoms[keep_mask].copy()
            entry.state.all_atom_coords = entry.state.atoms["xyz"].copy()

        # Update masks if they exist
        if entry.state.ball_mask is not None:
             if len(entry.state.ball_mask) == len(keep_mask):
                  entry.state.ball_mask = entry.state.ball_mask[keep_mask].copy()

        if entry.state.sticks_mask is not None:
             if len(entry.state.sticks_mask) == len(keep_mask):
                  entry.state.sticks_mask = entry.state.sticks_mask[keep_mask].copy()

        # Rebuild trace if needed? MolView.set_structure does a lot of work.
        # For now, just trigger view update.
        # NOTE: Full re-processing might be needed if CA atoms were removed.
        # We might want to call a method like viewer.update_from_atoms(obj_id)

        # A hack for now: tell MolView to re-process the atoms
        viewer.set_structure(entry.state)

        self._emit_message(f"Removed {np.sum(atom_mask)} atoms from {obj_name}")
