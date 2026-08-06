"""Hydrogen-bond networks and steric clashes, as commands.

Two things a viewer is asked for constantly and PyMOL answers only halfway:

* it finds polar contacts (`distance ... mode=2`) and draws them as one
  undifferentiated bundle of dashes. Which of them form a **network** -- the
  triad, the water wire, the ladder holding two strands together -- is left to
  the eye, and the eye misses a four-bond water-mediated path every time. The
  contacts here are PyMOL's, atom for atom (:mod:`~chimol.analysis.hbonds`);
  the grouping and the colouring are the part that is new.
* it has no clash command at all. What it has is the bump check inside the
  mutagenesis wizard: sculpting's van der Waals term, one iteration, with
  `sculpt_vdw_vis_mode` on. That is transcribed in
  :mod:`~chimol.analysis.clashes` and exposed here as `clashes`, so the check
  can be run on anything rather than only on a residue being mutated.
"""

from __future__ import annotations

import numpy as np

from ..analysis.clashes import ClashCriteria, clash_color, find_clashes
from ..analysis.hbond_networks import NetworkOptions, find_hbond_networks, network_colors
from .registry import command

#: How `hbond_network`'s water argument is spelled. PyMOL has no equivalent, so
#: the words are chosen to say what they do rather than to match anything.
WATER_MODES = ("bridge", "exclude", "only")


class InteractionMixin:
    """`hbond_network` and `clashes`."""

    # ------------------------------------------------------------------ #
    # Hydrogen-bond networks
    # ------------------------------------------------------------------ #
    @command("hbond_network", aliases=("hbnet",))
    def hbond_network(
        self,
        selection: str = "all",
        waters: str = "bridge",
        min_size: str | int = 1,
        name: str = "hbnet",
    ) -> None:
        """Group polar contacts into networks and draw each in its own colour.

        Parameters
        ----------
        selection : str
            What to search. Contacts are found *within* it, both directions,
            using the same criteria as ``distance ..., mode=2``.
        waters : {"bridge", "exclude", "only"}
            Whether an ordered water joins two halves of a network
            (``bridge``, the default), is ignored (``exclude``), or is the only
            thing looked at (``only``, the water wire alone).
        min_size : int
            Drop networks with fewer bonds than this. Every structure has
            dozens of lone surface contacts and they bury the ones that matter.
        name : str
            Prefix for the measurement objects: ``hbnet_1`` is the largest.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        mode = str(waters).strip().lower()
        if mode not in WATER_MODES:
            self._emit_error(
                f"hbond_network: waters must be one of {', '.join(WATER_MODES)}"
            )
            return
        try:
            floor = max(int(min_size), 1)
        except (TypeError, ValueError):
            self._emit_error("hbond_network: min_size must be a whole number")
            return

        try:
            combined = self._combined_atom_table(viewer, selection, selection)
        except ValueError as exc:
            self._emit_error(str(exc))
            return
        if combined is None:
            self._emit_error("hbond_network: selection matched no atoms")
            return
        atoms, bond_pairs, mask, _mask2, _names = combined

        networks = find_hbond_networks(
            atoms, bond_pairs, mask, mask,
            options=NetworkOptions(waters=mode, min_size=floor),
        )
        self._clear_measurement_group(viewer, name)
        if not networks:
            self._emit_message("hbond_network: no networks found")
            viewer._update_view()
            return

        xyz = np.asarray(atoms["xyz"], dtype=float)
        colours = network_colors(len(networks))
        measurements = dict(viewer._measurements)
        for index, (network, colour) in enumerate(zip(networks, colours), start=1):
            pairs = np.empty((network.size * 2, 3), dtype=float)
            pairs[0::2] = xyz[[bond.donor for bond in network.bonds]]
            pairs[1::2] = xyz[[bond.acceptor for bond in network.bonds]]
            measurements[f"{name}_{index}"] = {
                "kind": "dashes",
                "positions": pairs,
                "label": "",
                "labels": [],
                "color": list(self._colour_rgba(colour)),
            }
        viewer._measurements = measurements
        viewer._update_view()

        self._emit_message(
            f"hbond_network: {len(networks)} networks over "
            f"{sum(n.size for n in networks)} contacts"
        )
        for index, (network, colour) in enumerate(zip(networks, colours), start=1):
            self._emit_message(f"  {name}_{index} ({colour}): {network.describe()}")

    # ------------------------------------------------------------------ #
    # Clashes
    # ------------------------------------------------------------------ #
    @command("clashes", aliases=("bump_check",))
    def clashes(
        self,
        selection: str = "all",
        against: str = "",
        name: str = "clashes",
    ) -> None:
        """Report and draw van der Waals overlaps, as PyMOL's bump check does.

        Parameters
        ----------
        selection : str
            The atoms to check. Every overlap involving one of them is
            reported.
        against : str, optional
            Restrict the other side. Defaults to everything loaded, which is
            what the mutagenesis wizard does with the residue's surroundings.
        name : str
            The measurement object the bumps are drawn into.

        Notes
        -----
        The colour is PyMOL's: green at the edge of contact, red once the pair
        is `sculpt_vdw_vis_max` (0.3 A) inside itself, and nothing at all until
        the pair is closer than the sum of its radii plus
        `sculpt_vdw_vis_min` -- which is negative, so a comfortable contact is
        still drawn, in green. Hydrogen bonds are *not* clashes: the cutoff
        drops by `sculpt_hb_overlap` for the hydrogen and
        `sculpt_hb_overlap_base` for the heavy-atom pair, without which every
        hydrogen bond in the structure reports as an overlap.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        other = against.strip() or "all"
        try:
            combined = self._combined_atom_table(viewer, selection, other)
        except ValueError as exc:
            self._emit_error(str(exc))
            return
        if combined is None:
            self._emit_error("clashes: selection matched no atoms")
            return
        atoms, bond_pairs, subject, _partner, _names = combined

        report = self._clash_report(atoms, bond_pairs, subject)
        criteria = ClashCriteria.from_config()
        self._draw_clashes(viewer, name, atoms, report, criteria)

        overlapping = [c for c in report.clashes if c.overlap > 0]
        self._emit_message(
            f"clashes: {len(overlapping)} overlapping of {len(report.clashes)} "
            f"contacts, strain {report.strain:.2f}"
        )
        labels = self._atom_labels(atoms)
        for clash in report.worst(8):
            if clash.overlap <= 0:
                break
            self._emit_message(
                f"  {labels[clash.i]} -- {labels[clash.j]}: {clash.distance:.2f} A"
                f" ({clash.overlap:.2f} A overlap)"
            )

    # ------------------------------------------------------------------ #
    # Mutagenesis
    # ------------------------------------------------------------------ #
    @command("mutate")
    def mutate(
        self,
        selection: str = "",
        residue_name: str = "",
        rotamer: str | int = "",
    ) -> None:
        """Mutate one residue, PyMOL's mutagenesis wizard as a command.

        Parameters
        ----------
        selection : str
            Anything that resolves to a **single residue** -- ``resi 54``,
            ``sele``, a picked atom.
        residue_name : str
            The three-letter code it becomes.
        rotamer : int, optional
            Which conformation, 1-based as the report lists them. Omitted, the
            least strained is taken -- the wizard's `state_best`.

        Notes
        -----
        The backbone stays where it is and the side chain is built onto it from
        an idealised fragment, then set to each rotamer of PyMOL's library in
        turn and scored by the bump check. `mutate resi 54, TRP` with no
        rotamer prints the table and applies the best; run it again with a
        number to take another one.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        if not selection or not residue_name:
            self._emit_error("Usage: mutate <selection>, <residue name> [, rotamer]")
            return

        from ..analysis.mutate import mutate_residue

        try:
            hits = self._resolve_selection_to_atom_masks(viewer, selection)
        except Exception as exc:
            self._emit_error(str(exc))
            return
        picked = [(oid, name, mask) for oid, name, mask in hits if mask.any()]
        if not picked:
            self._emit_error("mutate: selection matched no atoms")
            return
        if len(picked) > 1:
            self._emit_error("mutate: the selection spans more than one object")
            return

        obj_id, obj_name, mask = picked[0]
        entry = viewer._objects.get(obj_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None or not len(atoms):
            self._emit_error(f"mutate: {obj_name} has no atoms")
            return

        residue = self._single_residue(atoms, mask)
        if residue is None:
            return

        index = None
        if str(rotamer).strip():
            try:
                index = int(rotamer) - 1
            except ValueError:
                self._emit_error("mutate: the rotamer must be a number")
                return

        try:
            result = mutate_residue(atoms, residue, residue_name, rotamer=index)
        except KeyError:
            self._emit_error(
                f"mutate: no fragment for {residue_name.upper()} -- "
                "the twenty standard residues are available"
            )
            return
        except ValueError as exc:
            self._emit_error(f"mutate: {exc}")
            return

        self._report_rotamers(result)
        self._apply_mutation(viewer, obj_id, obj_name, atoms, result)

    def _single_residue(self, atoms, mask) -> list[int] | None:
        """Every atom of the one residue the selection picks, or an error.

        PyMOL's wizard works on one residue at a time and takes the *whole*
        residue however few of its atoms were picked -- clicking a side-chain
        carbon mutates the residue, not the atom.
        """
        names = atoms.dtype.names or ()
        chain = (
            np.array([str(c) for c in atoms["chain"]]) if "chain" in names
            else np.array([""] * len(atoms))
        )
        resid = (
            np.asarray(atoms["res_id"], dtype=int) if "res_id" in names
            else np.zeros(len(atoms), dtype=int)
        )
        keys = {(chain[i], int(resid[i])) for i in np.nonzero(mask)[0]}
        if not keys:
            self._emit_error("mutate: selection matched no atoms")
            return None
        if len(keys) > 1:
            self._emit_error(
                f"mutate: the selection spans {len(keys)} residues -- pick one"
            )
            return None
        key = keys.pop()
        return [
            i for i in range(len(atoms))
            if (chain[i], int(resid[i])) == key
        ]

    def _report_rotamers(self, result) -> None:
        """The wizard's panel, as console lines: frequency and strain."""
        site = result.site
        self._emit_message(
            f"mutate: {result.residue_name}, {len(site.rotamers)} rotamers "
            f"(taking #{result.chosen + 1})"
        )
        order = sorted(
            range(len(site.rotamers)),
            key=lambda k: -site.rotamers[k].frequency,
        )[:8]
        for k in order:
            rot = site.rotamers[k]
            mark = "*" if k == result.chosen else " "
            chis = ", ".join(
                f"{'-'.join(quad)}={angle:.0f}" for quad, angle in rot.chis.items()
            )
            self._emit_message(
                f" {mark}{k + 1:3d}  {rot.frequency * 100:5.1f}%  "
                f"strain {rot.strain:6.2f}  {chis}"
            )

    def _apply_mutation(self, viewer, obj_id, obj_name, atoms, result) -> None:
        """Replace the residue's rows with the built ones, in place.

        In place, not appended: the atom table is in file order and a residue
        that jumps to the end of it breaks every reader of that order -- the
        sequence strip, the backbone trace, the bond inference that walks
        neighbouring residues.
        """
        site = result.site
        rotamer = result.rotamer
        indices = sorted(site.indices)
        first = indices[0]
        template = atoms[first]
        names = atoms.dtype.names or ()

        rows = []
        for position, (atom_name, element) in enumerate(zip(site.names, site.elements)):
            row = np.array(template, dtype=atoms.dtype).copy()
            if "atom_name" in names:
                row["atom_name"] = atom_name
            if "element" in names:
                row["element"] = element
            if "res_name" in names:
                row["res_name"] = result.residue_name
            if "radius" in names:
                from ..analysis.clashes import VDW_RADII, DEFAULT_VDW

                row["radius"] = VDW_RADII.get(str(element).upper(), DEFAULT_VDW)
            row["xyz"] = rotamer.coords[position]
            rows.append(row)

        keep = np.ones(len(atoms), dtype=bool)
        keep[indices] = False
        rebuilt = np.concatenate([
            atoms[keep][:first],
            np.array(rows, dtype=atoms.dtype),
            atoms[keep][first:],
        ])

        entry = viewer._objects.get(obj_id)
        entry.state.atoms = rebuilt
        entry.state.all_atom_coords = None
        entry.state.coords = None
        # Everything else indexed by atom -- colours, masks, per-atom overrides
        # -- is now the wrong length, and the load path re-derives all of it.
        for field_name in (
            "colors_per_atom_override", "protected_mask", "masked_mask",
            "all_atom_res_ids", "all_atom_radii",
        ):
            if hasattr(entry.state, field_name):
                setattr(entry.state, field_name, None)
        self._rebuild_after_coordinate_change(viewer, obj_id)
        # The residue is a different residue now, so every view of the sequence
        # is stale -- the strip, the docked list and the object row. The viewer
        # re-derives its own arrays through `set_structure`; the window has to
        # be told, or the strip goes on showing the letter of the residue that
        # is no longer there.
        window = getattr(self, "_window", None) or self._require_window_and_viewer()[0]
        for refresh in ("_refresh_objects_from_viewer", "_update_sequence_view",
                        "sync_internal_gui"):
            method = getattr(window, refresh, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
        self._emit_message(
            f"mutate: {obj_name} residue is now {result.residue_name} "
            f"(strain {rotamer.strain:.2f})"
        )

    # ------------------------------------------------------------------ #
    # Shared helpers
    # ------------------------------------------------------------------ #
    def _clash_report(self, atoms, bond_pairs, subject):
        """Run the bump check over a combined atom table."""
        from ..analysis.hbonds import type_atoms

        names = atoms.dtype.names or ()
        xyz = np.asarray(atoms["xyz"], dtype=float)
        radii = (
            np.asarray(atoms["radius"], dtype=float)
            if "radius" in names
            else np.full(len(atoms), 1.7)
        )
        elements = (
            np.array([str(e).upper() for e in atoms["element"]])
            if "element" in names
            else np.array([""] * len(atoms))
        )
        typing = type_atoms(atoms, bond_pairs)
        return find_clashes(
            xyz, radii, bond_pairs,
            subject=subject,
            donors=typing.donor,
            acceptors=typing.acceptor,
            is_hydrogen=np.isin(elements, ("H", "D")),
            criteria=ClashCriteria.from_config(),
        )

    def _draw_clashes(self, viewer, name, atoms, report, criteria) -> None:
        """Put the bumps on screen, one solid segment per pair, colour by depth.

        PyMOL's `sculpt_vdw_vis_mode` 2 draws a line whose width grows with the
        severity and draws nothing below `vis_mid`; mode 1 draws a cylinder for
        every pair, including the comfortable ones. This takes mode 2's line
        and mode 1's coverage: a green line for a contact that is fine is worth
        seeing, and a chimol overlay line cannot vary its width per segment.
        """
        xyz = np.asarray(atoms["xyz"], dtype=float)
        measurements = dict(viewer._measurements)
        for suffix in ("", "_ok"):
            measurements.pop(f"{name}{suffix}", None)

        # Two objects, not one: PyMOL widens the line with the severity
        # (`CGOLinewidth(1 + color_factor * 3)`) and a chimol overlay carries
        # one width per geometry. Splitting at `vis_mid` -- where the colour
        # starts leaving green -- keeps the distinction that matters, which is
        # that a red line is a problem and a green one is reassurance.
        buckets = {
            f"{name}_ok": ([c for c in report.clashes if c.overlap < criteria.vis_mid], 1.0),
            name: ([c for c in report.clashes if c.overlap >= criteria.vis_mid], 3.0),
        }
        for key, (group, width) in buckets.items():
            if not group:
                continue
            pairs = np.empty((len(group) * 2, 3), dtype=float)
            colours = np.empty((len(group) * 2, 4), dtype=float)
            for k, clash in enumerate(group):
                pairs[2 * k] = xyz[clash.i]
                pairs[2 * k + 1] = xyz[clash.j]
                rgb = clash_color(clash.overlap, criteria)
                colours[2 * k] = (*rgb, 1.0)
                colours[2 * k + 1] = (*rgb, 1.0)
            measurements[key] = {
                "kind": "contacts",
                "positions": pairs,
                "colors": colours,
                "width": width,
                "label": "",
                "labels": [],
                "color": [1.0, 0.2, 0.2, 1.0],
            }
        viewer._measurements = measurements
        viewer._update_view()

    @staticmethod
    def _atom_labels(atoms) -> list[str]:
        """``LYS`128/NZ`` per atom, PyMOL's own way of naming one."""
        names = atoms.dtype.names or ()
        out = []
        for index in range(len(atoms)):
            resn = str(atoms["res_name"][index]) if "res_name" in names else ""
            resi = atoms["res_id"][index] if "res_id" in names else ""
            atom = str(atoms["atom_name"][index]) if "atom_name" in names else ""
            out.append(f"{resn}`{resi}/{atom}".strip())
        return out

    @staticmethod
    def _clear_measurement_group(viewer, prefix: str) -> None:
        """Drop every measurement named ``prefix_<n>``.

        A second run must not leave the first run's networks on screen: the
        numbering is by size and it changes with the selection, so the stale
        ones would be indistinguishable from the new ones.
        """
        keep = {
            key: value for key, value in viewer._measurements.items()
            if not (key.startswith(f"{prefix}_") and key[len(prefix) + 1:].isdigit())
        }
        viewer._measurements = keep

    def _colour_rgba(self, colour: str) -> tuple[float, float, float, float]:
        """Resolve a colour name through the shared reader."""
        from ..colors import as_rgba

        try:
            rgba = as_rgba(colour)
        except Exception:
            rgba = None
        if rgba is None:
            return (1.0, 1.0, 0.0, 1.0)
        values = [float(c) for c in rgba]
        while len(values) < 4:
            values.append(1.0)
        return tuple(values[:4])
