"""Crystallographic symmetry commands: ``symexp``, ``get_symmetry``, ``set_symmetry``.

``symexp`` builds the neighbouring copies of a molecule in its crystal, so a
lattice contact can be looked at and told apart from a biological interface.

The cell comes from the file's ``CRYST1`` record, and the operators from **PyMOL's
own space-group table** -- transcribed into ``analysis/space_groups.py``, all 547
names it ships -- or from the file, or from ``set_symmetry``. When none of those
has them the space group is **named** and the command declines: a symmetry mate
built from guessed operators looks entirely plausible and would be believed.
"""

from __future__ import annotations

import numpy as np

from ..analysis.symmetry import (
    UnitCell,
    normalise_space_group,
    operators_for,
    parse_symmetry_operator,
    read_cryst1,
    read_file_operators,
    symmetry_mates,
)
from .base import BaseCmd
from .registry import command


class SymmetryMixin(BaseCmd):
    """The crystal cell, its symmetry operators, and the mates they generate."""

    def _symmetry_for(self, viewer, object_id: str):
        """Return ``(cell, space group, operators, source)`` for an object.

        Looked up in order of trust: what was set explicitly, then the file, then
        PyMOL's table. ``source`` names which one answered, so a message can say
        where the operators came from -- which matters when they might be a table
        lookup rather than the depositor's own.
        """
        entry = viewer._objects.get(object_id)
        state = getattr(entry, "state", None)

        explicit = getattr(state, "symmetry", None)
        if isinstance(explicit, dict) and explicit.get("operators"):
            cell = explicit.get("cell")
            return (
                cell,
                explicit.get("space_group", ""),
                list(explicit["operators"]),
                "set_symmetry",
            )

        path = getattr(entry, "source_path", None)
        cell = space_group = None
        if isinstance(explicit, dict):
            cell = explicit.get("cell")
            space_group = explicit.get("space_group")
        if cell is None and path:
            found = read_cryst1(path)
            if found is not None:
                cell, space_group = found
        if cell is None:
            return None, space_group or "", [], "none"

        if path:
            from_file = read_file_operators(path)
            if from_file:
                return cell, space_group or "", from_file, "the file"

        tabulated = operators_for(space_group or "")
        if tabulated:
            return cell, space_group or "", list(tabulated), "PyMOL's space-group table"
        return cell, space_group or "", [], "none"

    @command("get_symmetry", aliases=("symmetry",))
    def get_symmetry(self, selection: str = "all") -> None:
        """Report the crystal cell and space group (PyMOL ``get_symmetry``).

        Parameters
        ----------
        selection : str, optional
            Which object to report on.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        try:
            obj_id, obj_name, _mask = self._resolve_selection_to_atom_mask(
                viewer, selection or "all"
            )
        except Exception as exc:
            self._emit_error(f"get_symmetry: {exc}")
            return

        cell, space_group, operators, source = self._symmetry_for(viewer, obj_id)
        if cell is None:
            self._emit_error(
                f"get_symmetry: {obj_name} carries no unit cell "
                "(no CRYST1 record, and none set)"
            )
            return

        self._emit_message(
            f"get_symmetry: {obj_name} "
            f"a={cell.a:.3f} b={cell.b:.3f} c={cell.c:.3f} "
            f"alpha={cell.alpha:.2f} beta={cell.beta:.2f} gamma={cell.gamma:.2f} "
            f"'{space_group}' volume={cell.volume:.0f}"
        )
        if operators:
            self._emit_message(
                f"get_symmetry: {len(operators)} operators from {source}"
            )
        else:
            self._emit_message(
                f"get_symmetry: no operators for '{space_group}' -- not in "
                "PyMOL's space-group table and not in the file; supply them with "
                "set_symmetry"
            )

    @command("set_symmetry")
    def set_symmetry(
        self,
        selection: str = "all",
        a: str = "",
        b: str = "",
        c: str = "",
        alpha: str = "90",
        beta: str = "90",
        gamma: str = "90",
        space_group: str = "",
    ) -> None:
        """Set the crystal cell and space group (PyMOL ``set_symmetry``).

        Parameters
        ----------
        selection : str, optional
            Object to set it on.
        a, b, c : str
            Cell edges in Angstrom.
        alpha, beta, gamma : str, optional
            Cell angles in degrees; right angles by default.
        space_group : str, optional
            Space-group name. Its operators are looked up in PyMOL's table.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        if not str(a).strip() or not str(b).strip() or not str(c).strip():
            self._emit_error(
                "Usage: set_symmetry <selection>, a, b, c [, alpha, beta, gamma "
                "[, space_group]]"
            )
            return
        try:
            cell = UnitCell(
                a=float(a), b=float(b), c=float(c),
                alpha=float(alpha or 90), beta=float(beta or 90),
                gamma=float(gamma or 90),
            )
        except ValueError as exc:
            self._emit_error(f"set_symmetry: {exc}")
            return

        try:
            obj_id, obj_name, _mask = self._resolve_selection_to_atom_mask(
                viewer, selection or "all"
            )
        except Exception as exc:
            self._emit_error(f"set_symmetry: {exc}")
            return

        name = str(space_group).strip()
        operators = list(operators_for(name) or ())
        entry = viewer._objects.get(obj_id)
        entry.state.symmetry = {
            "cell": cell,
            "space_group": name,
            "operators": operators,
        }
        self._emit_message(
            f"set_symmetry: {obj_name} cell set, "
            + (
                f"'{name}' with {len(operators)} operators"
                if operators
                else f"'{name}' is not in PyMOL's space-group table"
            )
        )

    @command("symexp")
    def symexp(
        self,
        prefix: str = "sym",
        selection: str = "all",
        cutoff: str = "5.0",
        shells: str = "1",
    ) -> None:
        """Build the symmetry mates near a selection (PyMOL ``symexp``).

        One new object per mate, named ``prefix`` plus the operator index and the
        lattice translation, so a contact can be traced back to the operator that
        made it.

        Parameters
        ----------
        prefix : str, optional
            Name prefix for the created objects.
        selection : str, optional
            Atoms to expand around.
        cutoff : str, optional
            Keep a mate only if some atom comes within this distance, in
            Angstrom. ``0`` keeps every mate.
        shells : str, optional
            Lattice translations to try in each direction; 1 gives the 27
            surrounding cells, which is what PyMOL uses.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        try:
            distance = float(str(cutoff).strip() or 5.0)
            n_shells = int(str(shells).strip() or 1)
        except ValueError as exc:
            self._emit_error(f"symexp: {exc}")
            return

        try:
            obj_id, obj_name, mask = self._resolve_selection_to_atom_mask(
                viewer, selection or "all"
            )
        except Exception as exc:
            self._emit_error(f"symexp: {exc}")
            return

        cell, space_group, operators, source = self._symmetry_for(viewer, obj_id)
        if cell is None:
            self._emit_error(
                f"symexp: {obj_name} carries no unit cell (no CRYST1 record); "
                "set one with set_symmetry"
            )
            return
        if not operators:
            self._emit_error(
                f"symexp: no symmetry operators for '{space_group}'. It is not "
                "in PyMOL's space-group table and the file does not carry them -- "
                "supply them rather than have mates built from a guess"
            )
            return

        entry = viewer._objects.get(obj_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None:
            self._emit_error(f"symexp: {obj_name} carries no atoms")
            return
        coords = np.asarray(atoms["xyz"], dtype=float)
        # The frame every mate has to be drawn in, taken before any are made.
        parent_centre = getattr(entry.state, "raw_center", None)
        if parent_centre is not None:
            parent_centre = np.asarray(parent_centre, dtype=float)

        try:
            mates = symmetry_mates(
                coords, cell, operators,
                cutoff=distance, shells=n_shells,
                selection=np.asarray(mask, dtype=bool),
            )
        except ValueError as exc:
            self._emit_error(f"symexp: {exc}")
            return

        if not mates:
            self._emit_message(
                f"symexp: no symmetry mate comes within {distance:g} A of "
                f"{obj_name}"
            )
            return

        made = []
        for mate in mates:
            i, j, k = mate["translation"]
            name = f"{prefix}{mate['operator']:02d}_{i}{j}{k}".replace("-", "m")
            new_atoms = atoms.copy()
            new_atoms["xyz"] = mate["coords"]

            class _Structure:
                """The shape ``set_structure`` reads."""

            structure = _Structure()
            structure.atoms = new_atoms
            structure.xyz = mate["coords"]
            structure.n_atoms = len(new_atoms)

            new_entry = viewer._create_object(name=name)
            viewer.set_active_object(new_entry.object_id)
            viewer.set_structure(structure)
            # In the PARENT's frame, not its own. Every object is otherwise
            # drawn centred on its own centroid, so each mate landed at the
            # render origin -- measured, all six and the original had distinct
            # centroids in Angstrom and were drawn at (0, 0, 0). They were
            # stacked on top of one another, which makes `symexp` useless for
            # the one thing it is for: seeing how the molecules pack. `create`
            # already solved this; the mates never got it.
            if parent_centre is not None:
                viewer._reframe_to(new_entry.object_id, parent_centre)
            made.append(name)

        # Leave the original active: `symexp` adds context around a molecule, it
        # does not change which molecule is being worked on.
        viewer.set_active_object(obj_id)
        if window is not None and hasattr(window, "_refresh_objects_from_viewer"):
            window._refresh_objects_from_viewer()
        self._emit_message(
            f"symexp: {len(made)} mates within {distance:g} A of {obj_name} "
            f"('{space_group}', {len(operators)} operators from {source})"
        )

    @command("cell")
    def cell(self, selection: str = "all", state: str = "") -> None:
        """Draw or hide the unit cell as a wireframe box (PyMOL ``cell``).

        The mates ``symexp`` builds are hard to read without the box they tile,
        which is what this is for: twelve edges around the crystallographic cell,
        drawn in the object's own frame so it sits on the molecule rather than
        at the scene origin.

        Parameters
        ----------
        selection : str, optional
            Which object's cell. ``all`` is every object that has one.
        state : str, optional
            ``on`` / ``off`` / ``toggle``. Toggles when omitted, so ``cell`` on
            its own switches the box the way clicking a check box would.

        Notes
        -----
        A cell is not a representation of the atoms, so it is not part of
        ``show``/``hide``: an object with no ``CRYST1`` record has no cell to
        draw, and saying so is more use than an empty ``show cell``.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        wanted = str(state).strip().lower()
        if wanted not in ("", "on", "off", "toggle", "1", "0", "true", "false"):
            self._emit_error(f"cell: expected on/off/toggle, got {state!r}")
            return

        target = str(selection).strip() or "all"
        if target in ("all", "*", "everything"):
            object_ids = list(getattr(viewer, "_objects", {}))
        else:
            try:
                obj_id, _name, _mask = self._resolve_selection_to_atom_mask(viewer, target)
            except Exception as exc:
                self._emit_error(f"cell: {exc}")
                return
            object_ids = [obj_id]

        shown, without = [], []
        for object_id in object_ids:
            entry = getattr(viewer, "_objects", {}).get(object_id)
            if entry is None or getattr(entry, "placeholder", False):
                continue
            cell_state = entry.state
            symmetry = getattr(cell_state, "symmetry", None) or {}
            if symmetry.get("cell") is None:
                # Ask the resolver, which reads the file's CRYST1 and the
                # space-group table. Reading `state.symmetry` alone was the
                # whole test here, so `cell` only ever worked after an explicit
                # `set_symmetry` while `symexp` -- which does resolve -- worked
                # straight from the file. Two paths to one answer, and the
                # message from the wrong one said the record was missing when
                # it was in the file being displayed. The result is written
                # back, because the renderer reads `state.symmetry` too.
                found_cell, group, operators, _source = self._symmetry_for(
                    viewer, object_id
                )
                if found_cell is None:
                    without.append(entry.name)
                    continue
                symmetry = dict(symmetry)
                symmetry.update(
                    cell=found_cell, space_group=group, operators=operators
                )
                cell_state.symmetry = symmetry
            if wanted in ("on", "1", "true"):
                value = True
            elif wanted in ("off", "0", "false"):
                value = False
            else:
                value = not bool(getattr(cell_state, "show_cell", False))
            cell_state.show_cell = value
            if value:
                shown.append(entry.name)

        viewer._update_view()
        if shown:
            self._emit_message(f"cell: drawn for {', '.join(shown)}")
        elif without and not shown:
            self._emit_error(
                "cell: "
                + ", ".join(without)
                + " carries no unit cell (no CRYST1 record); set one with set_symmetry"
            )
        else:
            self._emit_message("cell: hidden")
