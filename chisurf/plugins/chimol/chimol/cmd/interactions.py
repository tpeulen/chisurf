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

from contextlib import contextmanager

import numpy as np

from ..analysis.clashes import ClashCriteria, clash_color, find_clashes
from ..analysis.hbond_networks import NetworkOptions, find_hbond_networks, network_colors
from .registry import command

#: How `hbond_network`'s water argument is spelled. PyMOL has no equivalent, so
#: the words are chosen to say what they do rather than to match anything.
WATER_MODES = ("bridge", "exclude", "only")


def _angle_between(a, b, c) -> float | None:
    """The angle a-b-c in degrees, or ``None`` when a leg has no length."""
    u = np.asarray(a, dtype=float) - np.asarray(b, dtype=float)
    v = np.asarray(c, dtype=float) - np.asarray(b, dtype=float)
    nu = float(np.linalg.norm(u))
    nv = float(np.linalg.norm(v))
    if nu <= 0.0 or nv <= 0.0:
        return None
    cosine = float(np.dot(u, v) / (nu * nv))
    return float(np.degrees(np.arccos(min(1.0, max(-1.0, cosine)))))


def _dihedral_between(a, b, c, d) -> float | None:
    """The torsion a-b-c-d in degrees, signed, or ``None`` when it is undefined.

    The ``atan2`` form rather than an ``arccos`` of the plane normals: the sign
    is the whole point of a torsion, and an ``arccos`` cannot produce one.
    """
    p0, p1, p2, p3 = (np.asarray(p, dtype=float) for p in (a, b, c, d))
    b0 = p0 - p1
    b1 = p2 - p1
    b2 = p3 - p2
    norm = float(np.linalg.norm(b1))
    if norm <= 0.0:
        return None
    b1 = b1 / norm
    v = b0 - np.dot(b0, b1) * b1
    w = b2 - np.dot(b2, b1) * b1
    if float(np.linalg.norm(v)) <= 0.0 or float(np.linalg.norm(w)) <= 0.0:
        return None
    x = float(np.dot(v, w))
    y = float(np.dot(np.cross(b1, v), w))
    return float(np.degrees(np.arctan2(y, x)))


class InteractionMixin:
    """`hbond_network`, `clashes` and the `wizard`."""

    #: What PyMOL calls the preview object the rotamers live in, one state each.
    PREVIEW_OBJECT = "mutation"
    #: And the bump geometry drawn for the state on screen. PyMOL's own name is
    #: `_bump_check`; the leading underscore is its convention for an object the
    #: user did not make, and it is kept.
    BUMP_OBJECT = "_bump_check"

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
        """Print the wizard's panel as console lines: frequency and strain."""
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
                from ..analysis.clashes import DEFAULT_VDW, VDW_RADII

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
    # The wizard, PyMOL's simplest GUI
    # ------------------------------------------------------------------ #
    @command("wizard")
    def wizard(self, name: str = "", argument: str = "") -> None:
        """Run a wizard, or drive the one that is running.

        ``wizard mutagenesis`` starts it, ``wizard done`` ends it, and the
        panel's own rows send the rest -- ``wizard target, LYS``,
        ``wizard rotamer, next``, ``wizard apply``. PyMOL's is the same
        command with the same first argument.

        Parameters
        ----------
        name : str
            The wizard to start, or an action for the running one.
        argument : str, optional
            What the action needs: a residue name, a rotamer number or
            ``next``.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        action = str(name).strip().lower()

        if action in ("", "mutagenesis", "mutate"):
            self._wizard_start(viewer)
            return
        if action in ("measurement", "measure"):
            self._measure_start(viewer)
            return
        if action == "done":
            self._wizard_finish(viewer, keep=False)
            return

        state = getattr(viewer, "_wizard", None)
        if state is None:
            self._emit_error("wizard: no wizard is running")
            return

        from ..wizards import MeasurementWizard

        if isinstance(state, MeasurementWizard):
            if action == "mode":
                self._measure_set_mode(viewer, state, argument)
            elif action == "pick":
                self._measure_pick(viewer, state, argument)
            elif action == "unpick":
                self._measure_unpick(viewer, state)
            elif action == "delete":
                self._measure_delete(viewer, state, argument)
            else:
                self._emit_error(f"wizard: unknown action {action!r}")
            return

        if action == "target":
            self._wizard_set_target(viewer, state, argument)
        elif action == "rotamer":
            self._wizard_step(viewer, state, argument)
        elif action == "bump":
            state.bump_check = not state.bump_check
            self._wizard_show_state(viewer, state)
        elif action == "apply":
            self._wizard_finish(viewer, keep=True)
        elif action == "clear":
            self._wizard_delete_preview(viewer, state)
            state.target = ""
            state.scores = []
            state.site = None
            self._wizard_bumps(viewer, state)
            self._wizard_refresh(viewer, state)
        else:
            self._emit_error(f"wizard: unknown action {action!r}")

    def _wizard_gui(self, viewer):
        """Return the in-viewport panel, or ``None`` without a renderer."""
        renderer = getattr(viewer, "_renderer", None)
        return getattr(renderer, "_internal_gui", None)

    def _wizard_start(self, viewer) -> None:
        """Install the mutagenesis wizard and pick up whatever is selected."""
        from ..wizards import MutagenesisWizard

        state = MutagenesisWizard()
        viewer._wizard = state
        # A selection already made is the residue: starting the wizard with a
        # residue picked and then being asked to pick one is the sort of thing
        # that makes a panel feel like it is not listening.
        selected = list(getattr(viewer, "_selected_residues", []) or [])
        if selected:
            self._wizard_adopt_selection(viewer, state)
        self._wizard_refresh(viewer, state)
        self._emit_message("wizard: mutagenesis -- pick a residue")

    def _wizard_adopt_selection(self, viewer, state) -> None:
        """Take the current selection's residue as the wizard's subject."""
        object_id = viewer.get_active_object_id()
        entry = viewer._objects.get(object_id) if object_id else None
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None or not len(atoms):
            return
        selected = list(getattr(viewer, "_selected_residues", []) or [])
        if not selected:
            return
        residue_ids = getattr(viewer, "_residue_ids", None)
        if residue_ids is None:
            return
        try:
            resi = int(np.asarray(residue_ids)[selected[0]])
        except Exception:
            return
        names = atoms.dtype.names or ()
        chains = (
            np.array([str(c) for c in atoms["chain"]]) if "chain" in names
            else np.array([""] * len(atoms))
        )
        rows = [
            i for i in range(len(atoms))
            if int(atoms["res_id"][i]) == resi
        ]
        if not rows:
            return
        state.object_id = object_id
        state.object_name = getattr(entry, "name", object_id)
        state.residue = (
            chains[rows[0]], resi, str(atoms["res_name"][rows[0]]).strip()
        )

    def _wizard_set_target(self, viewer, state, residue_name: str) -> None:
        """Choose what the residue becomes, and preview the best rotamer."""
        if not state.residue:
            self._emit_error("wizard: pick a residue first")
            return
        state.target = str(residue_name).strip().upper()
        state.rotamer = 0
        self._wizard_preview(viewer, state, choose_best=True)

    def _wizard_step(self, viewer, state, argument: str) -> None:
        """Move to another rotamer -- ``next`` or a 1-based number."""
        if not state.scores:
            return
        text = str(argument).strip().lower()
        if text in ("", "next", "+"):
            state.rotamer = (state.rotamer + 1) % len(state.scores)
        elif text in ("prev", "previous", "-"):
            state.rotamer = (state.rotamer - 1) % len(state.scores)
        else:
            try:
                state.rotamer = max(0, min(int(text) - 1, len(state.scores) - 1))
            except ValueError:
                self._emit_error("wizard: rotamer must be a number or 'next'")
                return
        # A state change, not a rebuild: the rotamers are already there.
        self._wizard_show_state(viewer, state)

    def _wizard_preview(self, viewer, state, choose_best: bool = False) -> None:
        """Build every rotamer once, as **states of a preview object**.

        PyMOL's `do_library`, 1:1: it creates an object called `mutation` with
        one state per rotamer -- `cmd.create(obj_name, frag_name, 1, state)` in
        a loop, each state titled with the rotamer's frequency -- scores every
        state once, and leaves the source structure **untouched** until Apply.
        Stepping a rotamer is then a *frame change*, not a rebuild.

        Which is also why it is fast. Rebuilding the residue inside the source
        object, as this did before, re-ran `set_structure` on the whole
        molecule for every step: 2.2 s per rotamer on a 1363-atom protein, of
        which 0.97 s was recomputing ambient occlusion for atoms that had not
        moved. A separate object with the states already in it costs that once.
        """
        from ..analysis.mutate import build_rotamers, score_rotamers

        if not state.residue or not state.target:
            self._wizard_refresh(viewer, state)
            return
        entry = viewer._objects.get(state.object_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None or not len(atoms):
            return

        chain, resi, _resn = state.residue
        rows = self._wizard_residue_rows(atoms, chain, resi)
        if not rows:
            self._emit_error("wizard: the residue is no longer there")
            return

        xyz = np.asarray(atoms["xyz"], dtype=float)
        atom_names = np.array([str(n).strip() for n in atoms["atom_name"]])
        elements = np.array([str(e).strip() for e in atoms["element"]])
        backbone = {
            atom_names[i]: xyz[i] for i in rows if atom_names[i] in ("N", "CA", "C", "O")
        }
        hydrogens = bool(np.any(np.isin(np.char.upper(elements), ("H", "D"))))
        try:
            site = build_rotamers(state.target, backbone, hydrogens=hydrogens)
        except (KeyError, ValueError) as exc:
            self._emit_error(f"wizard: {exc}")
            return

        # Scored against the neighbourhood once, for every state, exactly as
        # the wizard scores every state before showing you any of them.
        centre = xyz[rows].mean(axis=0)
        near = np.linalg.norm(xyz - centre, axis=1) <= 12.0
        near[rows] = False
        site = score_rotamers(site, xyz[near], elements[near])

        state.site = site
        state.scores = [(rot.frequency, rot.strain) for rot in site.rotamers]
        if choose_best:
            state.rotamer = int(min(
                range(len(site.rotamers)),
                key=lambda k: (site.rotamers[k].strain, -site.rotamers[k].frequency),
            ))
        state.rotamer = max(0, min(state.rotamer, len(site.rotamers) - 1))

        self._wizard_show_states(viewer, state, site)
        self._wizard_show_state(viewer, state)

    def _wizard_residue_rows(self, atoms, chain, resi) -> list[int]:
        """Every row of one residue, by chain and number."""
        names = atoms.dtype.names or ()
        chains = (
            np.array([str(c) for c in atoms["chain"]]) if "chain" in names
            else np.array([""] * len(atoms))
        )
        return [
            i for i in range(len(atoms))
            if int(atoms["res_id"][i]) == int(resi) and chains[i] == chain
        ]

    def _wizard_show_states(self, viewer, state, site) -> None:
        """Create the `mutation` object, one state per rotamer.

        PyMOL names it `mutation` and so does this: it appears in the object
        list, it can be switched off, and `delete mutation` gets rid of it --
        the preview is an object like any other rather than a mode the panel
        owns.
        """
        from ..io.structure import StructurePayload

        self._wizard_delete_preview(viewer, state)
        keep_camera = self._wizard_keeps_the_camera(viewer)
        keep_camera.__enter__()

        frames = np.stack([rot.coords for rot in site.rotamers])
        first = frames[0]
        dtype = np.dtype([
            ("atom_name", "U4"), ("res_name", "U4"), ("res_id", "i4"),
            ("chain", "U2"), ("element", "U2"), ("xyz", "f8", 3),
        ])
        chain, resi, _resn = state.residue
        rows = np.array(
            [
                (name, state.target, int(resi), chain, element, tuple(xyz))
                for name, element, xyz in zip(site.names, site.elements, first)
            ],
            dtype=dtype,
        )
        payload = StructurePayload(
            coords=first,
            atoms=rows,
            bonds=np.asarray(site.bonds, dtype=int) if site.bonds else None,
            frames=frames,
            reader="mutation",
        )
        state.preview_id = viewer.add_payload(
            payload, name=self.PREVIEW_OBJECT, fit_camera=False
        )
        # In the source's frame, not its own. An object centred on its own
        # centroid is drawn at the middle of the scene, so a fourteen-atom
        # residue previewed that way appears nowhere near the residue it
        # replaces -- and the camera refits to it on top of that.
        viewer.set_frames(
            frames,
            object_id=state.preview_id,
            active_frame=state.rotamer,
            share_frame_with=state.object_id,
        )
        # Sticks and lines, which is what PyMOL shows a mutation object as
        # (`cmd.show(self.rep, obj_name)` with `rep` defaulting to lines, plus
        # `cmd.show('lines', obj_name)` unconditionally). Left at the default a
        # fourteen-atom residue is drawn as a *cartoon*, which splines a ribbon
        # through one residue and is the blob this first produced.
        with viewer._activate_object(state.preview_id):
            viewer._show_cartoon = False
            viewer._show_trace = False
            viewer._show_atoms = False
            viewer._show_surface = False
            viewer._show_sticks = True
            viewer._show_lines = True
            viewer._show_nonbonded = False
        window = self._require_window_and_viewer()[0]
        if window is not None and hasattr(window, "_refresh_objects_from_viewer"):
            try:
                window._refresh_objects_from_viewer()
            except Exception:
                pass
        keep_camera.__exit__(None, None, None)

    @contextmanager
    def _wizard_keeps_the_camera(self, viewer):
        """Hold the framing across a wizard update.

        PyMOL sets `auto_zoom 0` around `do_library` for this reason: you have
        framed the residue you are mutating, and creating an object beside it
        must not take that away. chimol has more ways to move the camera than
        one flag covers -- a new object shifts the scene centre, a state change
        re-derives the radius -- so the view is saved and put back, which is
        the same promise made where it cannot be missed.
        """
        try:
            view = viewer.get_view_state()
        except Exception:
            view = None
        try:
            yield
        finally:
            if view is not None:
                try:
                    viewer.set_view_state(view)
                except Exception:
                    pass

    def _wizard_show_state(self, viewer, state) -> None:
        """Show one rotamer: the frame, the bumps for it, and the panel.

        **One redraw**, and a draft one. Stepping used to cost three full
        rebuilds of every visible object -- the frame change, the bumps and the
        panel each asked for their own -- with an ambient-occlusion bake of the
        whole protein inside each. The molecule has not moved; only which state
        of a fourteen-atom object is shown has.
        """
        # No draft mode here, deliberately. Stepping a rotamer is not
        # scrubbing a trajectory: you are *looking* at each one to judge it,
        # and the draft path drops the occlusion bake, which is most of what
        # makes the picture readable. One suspended redraw is enough -- the
        # step costs about as much as a single rebuild rather than three.
        with self._wizard_keeps_the_camera(viewer), viewer.suspend_updates():
            if state.preview_id and state.site is not None:
                # The preview's own state, not the global timeline. PyMOL's
                # states *are* global; chimol's drive trajectory playback for
                # every object at once, and asking the whole scene for state
                # seven to step a nine-state rotamer re-derives the scene
                # bounds from a fourteen-atom object -- measured: the protein
                # shrinks to a speck and the camera cannot be put back, because
                # the zoom is derived rather than stored. Stepping the preview's
                # own state renders correctly and costs 32 ms. The panel says
                # which rotamer is on screen; the movie transport stays the
                # movie transport.
                with viewer._activate_object(state.preview_id):
                    preview_state = viewer._get_active_state()
                    viewer._select_state_frame(preview_state, state.rotamer)
            self._wizard_bumps(viewer, state)
            self._wizard_refresh(viewer, state)

    def _wizard_bumps(self, viewer, state) -> None:
        """Draw the bump check for the state on screen, or clear it.

        PyMOL builds a `_bump_check` object out of the side chain and its
        surroundings and lets sculpting draw into it. The drawing is the same
        (:func:`~chimol.analysis.clashes.find_clashes` and PyMOL's own colour);
        what is different is that chimol has an overlay to draw into and does
        not need a second object to hang the geometry off.
        """
        from ..analysis.clashes import ClashCriteria, find_clashes, radii_for
        from ..analysis.mutate import BACKBONE

        measurements = {
            key: value for key, value in viewer._measurements.items()
            if key not in (self.BUMP_OBJECT, f"{self.BUMP_OBJECT}_ok")
        }
        viewer._measurements = measurements
        if not state.bump_check or state.site is None:
            viewer._update_view()
            return

        entry = viewer._objects.get(state.object_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None:
            return
        chain, resi, _resn = state.residue
        rows = self._wizard_residue_rows(atoms, chain, resi)
        xyz = np.asarray(atoms["xyz"], dtype=float)
        elements = np.array([str(e).strip() for e in atoms["element"]])
        centre = xyz[rows].mean(axis=0) if rows else xyz.mean(axis=0)
        near = np.linalg.norm(xyz - centre, axis=1) <= 12.0
        near[rows] = False

        site = state.site
        rotamer = site.rotamers[state.rotamer]
        side_chain = [
            index for index, name in enumerate(site.names) if name not in BACKBONE
        ]
        combined = np.vstack([rotamer.coords[side_chain], xyz[near]])
        radii = np.concatenate([
            radii_for([site.elements[i] for i in side_chain]),
            radii_for(elements[near]),
        ])
        position = {atom: row for row, atom in enumerate(side_chain)}
        bonds = [
            (position[i], position[j]) for i, j in site.bonds
            if i in position and j in position
        ]
        subject = np.zeros(len(combined), dtype=bool)
        subject[: len(side_chain)] = True
        criteria = ClashCriteria.from_config()
        report = find_clashes(
            combined, radii, bonds, subject=subject, criteria=criteria
        )
        self._draw_clashes(
            viewer, self.BUMP_OBJECT, None, report, criteria,
            coords=combined, radii=radii,
        )

    def _wizard_delete_preview(self, viewer, state) -> None:
        """Remove the `mutation` object, if there is one."""
        preview = getattr(state, "preview_id", "")
        if not preview:
            return
        try:
            viewer.remove_object(preview)
        except Exception:
            try:
                viewer._objects.pop(preview, None)
            except Exception:
                pass
        state.preview_id = ""

    def _wizard_finish(self, viewer, keep: bool) -> None:
        """End the wizard: Apply writes the state in, anything else drops it.

        The source structure is only ever touched here. Everything before this
        was a separate object, which is what makes Clear and Done free -- there
        is nothing to undo, only an object to delete.
        """
        from ..wizards import MeasurementWizard

        state = getattr(viewer, "_wizard", None)
        if state is None:
            return

        # The measurement wizard has nothing to commit and nothing to undo:
        # every completed measurement is already a scene object, and PyMOL
        # leaves them behind too. All that ends is the picking.
        if isinstance(state, MeasurementWizard):
            self._measure_stop_listening(viewer)
            state.picks = []
            self._measure_mark_picks(viewer, state)
            viewer._wizard = None
            gui = self._wizard_gui(viewer)
            if gui is not None:
                gui.wizard_rows = []
                gui.wizard_prompt = []
                gui.wizard_menu = None
            viewer._update_view()
            self._emit_message("wizard: done")
            return

        if keep:
            self._wizard_commit(viewer, state)
        self._wizard_delete_preview(viewer, state)
        for group in (self.BUMP_OBJECT, "clashes"):
            self._clear_measurement_group(viewer, group)
        viewer._measurements = {
            k: v for k, v in viewer._measurements.items()
            if k not in (
                "clashes", "clashes_ok", self.BUMP_OBJECT, f"{self.BUMP_OBJECT}_ok",
            )
        }
        viewer._wizard = None
        # Leaving is not a scrub: whatever is on screen now is what the user
        # will be looking at, so it is drawn at full quality.
        viewer._draft_quality = False
        gui = self._wizard_gui(viewer)
        if gui is not None:
            gui.wizard_rows = []
            gui.wizard_prompt = []
            gui.wizard_menu = None
        viewer._update_view()
        self._emit_message(
            "wizard: applied" if keep else "wizard: done"
        )

    def _wizard_commit(self, viewer, state) -> None:
        """Write the state on screen into the source residue -- PyMOL's Apply."""
        from ..analysis.mutate import MutationResult

        if state.site is None or not state.residue:
            return
        entry = viewer._objects.get(state.object_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None:
            return
        chain, resi, _resn = state.residue
        rows = self._wizard_residue_rows(atoms, chain, resi)
        if not rows:
            self._emit_error("wizard: the residue is no longer there")
            return
        state.site.indices = rows
        result = MutationResult(
            site=state.site, chosen=state.rotamer, residue_name=state.target
        )
        self._apply_mutation(
            viewer, state.object_id, state.object_name, atoms, result
        )

    def _wizard_refresh(self, viewer, state) -> None:
        """Push the wizard's rows and prompt into the viewport panel."""
        gui = self._wizard_gui(viewer)
        if gui is None:
            return
        gui.wizard_rows = state.panel()
        gui.wizard_prompt = state.prompt()
        gui.wizard_menu = state.menu
        viewer._update_view()

    # ------------------------------------------------------------------ #
    # The measurement wizard: pick atoms, get distances
    # ------------------------------------------------------------------ #
    #: Prefix for the measurement objects the wizard creates, so `Delete All`
    #: can tell its own from a `distance` typed at the prompt.
    MEASURE_OBJECT = "measure"

    def _measure_start(self, viewer) -> None:
        """Install the measurement wizard and start listening for picks."""
        from ..wizards import MeasurementWizard

        state = MeasurementWizard()
        viewer._wizard = state
        self._measure_listen(viewer, state)
        self._wizard_refresh(viewer, state)
        self._emit_message("wizard: measurement -- pick two atoms")

    def _measure_listen(self, viewer, state) -> None:
        """Route viewport picks to the wizard instead of the selection.

        `MolView` knows nothing about wizards and must not: it exposes a single
        hook and calls it with the atom it picked, and a truthy return means the
        click was consumed -- so a measurement pick does not also toggle the
        residue in and out of `sele`, which is what PyMOL's wizard does too.
        """
        def _picked(atom_index: int) -> bool:
            current = getattr(viewer, "_wizard", None)
            if current is not state:
                return False
            try:
                self._measure_pick(viewer, state, str(int(atom_index)))
            except Exception as exc:
                self._emit_error(f"measurement: {exc}")
            return True

        viewer._wizard_pick = _picked

    def _measure_stop_listening(self, viewer) -> None:
        """Give clicks back to the selection."""
        try:
            viewer._wizard_pick = None
        except Exception:
            pass

    def _measure_set_mode(self, viewer, state, argument: str) -> None:
        """Switch between distances, angles and dihedrals."""
        from ..wizards import MEASUREMENT_MODES

        wanted = str(argument).strip().lower()
        names = [name for name, _label, _count in MEASUREMENT_MODES]
        if wanted not in names:
            self._emit_error(
                f"wizard: unknown measurement mode {argument!r}; "
                f"use one of {', '.join(names)}"
            )
            return
        state.mode = wanted
        # Picks belong to the mode that was running: three atoms half-way to a
        # dihedral are not the start of a distance.
        state.picks = []
        self._wizard_refresh(viewer, state)
        self._emit_message(f"wizard: measuring {state.mode_label.lower()}")

    def _measure_atom_label(self, viewer, object_id: str, atom_index: int) -> str:
        """Name one atom the way a measurement's report should read."""
        entry = viewer._objects.get(object_id)
        obj_name = getattr(entry, "name", object_id)
        atoms = getattr(getattr(entry, "state", None), "atoms", None)
        if atoms is None or atom_index >= len(atoms):
            return f"{obj_name}/{atom_index}"
        names = atoms.dtype.names or ()
        parts = [str(obj_name)]
        if "chain" in names:
            chain = str(atoms["chain"][atom_index]).strip()
            if chain:
                parts.append(chain)
        resn = str(atoms["res_name"][atom_index]).strip() if "res_name" in names else ""
        resi = int(atoms["res_id"][atom_index]) if "res_id" in names else atom_index
        atom = str(atoms["atom_name"][atom_index]).strip() if "atom_name" in names else ""
        parts.append(f"{resn}{resi}" if resn else str(resi))
        if atom:
            parts.append(atom)
        return "/".join(parts)

    def _measure_pick(self, viewer, state, argument: str) -> None:
        """Take one picked atom, and measure once the mode has enough of them."""
        text = str(argument).strip()
        if not text:
            return
        object_id = viewer.get_active_object_id()
        if ":" in text:
            object_id, _sep, text = text.partition(":")
        try:
            atom_index = int(text)
        except Exception:
            self._emit_error(f"wizard: {argument!r} is not an atom index")
            return

        label = self._measure_atom_label(viewer, object_id, atom_index)
        # PyMOL ignores a repeat of the atom just picked rather than measuring
        # an atom against itself, which is always zero and always a mis-click.
        if state.picks and state.picks[-1][:2] == (object_id, atom_index):
            return
        state.picks.append((object_id, atom_index, label))
        self._measure_mark_picks(viewer, state)
        if len(state.picks) < state.wanted:
            self._wizard_refresh(viewer, state)
            return

        picks = list(state.picks)
        state.picks = []
        # The marks go with them: the group has become a measurement, which is
        # its own drawing, and leaving the pick markers behind would double it.
        self._measure_mark_picks(viewer, state)
        self._measure_commit(viewer, state, picks)
        self._wizard_refresh(viewer, state)

    def _measure_mark_picks(self, viewer, state) -> None:
        """Show the atoms picked so far with the selection marker.

        Clicking an atom and getting no acknowledgement until the *second*
        click is what makes a measurement feel like it missed -- and with
        nothing drawn there is no way to tell a mis-click from a mis-aim. The
        marker is the one the selection already uses, so a picked atom looks
        picked in the way everything else in the viewer does.
        """
        setter = getattr(viewer, "set_pick_markers", None)
        if not callable(setter):
            return
        try:
            setter([atom for _obj, atom, _label in state.picks])
        except Exception:
            pass

    def _measure_unpick(self, viewer, state) -> None:
        """Take back the last picked atom.

        Every pick row is this command, not one per index: the group is
        incomplete by definition -- a complete one has already become a
        measurement -- so there is only ever a short list, and dropping from
        the end is what a mis-click needs.
        """
        if not state.picks:
            self._emit_message("measurement: no pick to take back")
            return
        _obj, _atom, label = state.picks.pop()
        self._wizard_refresh(viewer, state)
        self._emit_message(f"measurement: dropped {label}")

    def _measure_positions(self, viewer, picks) -> np.ndarray:
        """World coordinates for the picked atoms, in pick order.

        The **raw** `atoms["xyz"]`, not `all_atom_coords`: the latter is the
        scene array, centred and scaled by `_scale_factor`, and a measurement
        built from it reports ten times the Angstrom value and is drawn in the
        wrong place -- the renderer transforms what it is given into scene
        space itself.
        """
        out = np.empty((len(picks), 3), dtype=float)
        for row, (object_id, atom_index, _label) in enumerate(picks):
            entry = viewer._objects.get(object_id)
            atoms = getattr(getattr(entry, "state", None), "atoms", None)
            if atoms is None or atom_index >= len(atoms):
                raise ValueError(f"atom {atom_index} is not in {object_id}")
            out[row] = np.asarray(atoms["xyz"][atom_index], dtype=float).reshape(3)
        return out

    def _measure_commit(self, viewer, state, picks) -> None:
        """Turn a complete group of picks into a measurement on the scene."""
        try:
            points = self._measure_positions(viewer, picks)
        except ValueError as exc:
            self._emit_error(f"measurement: {exc}")
            return

        if state.mode == "distance":
            value = float(np.linalg.norm(points[0] - points[1]))
            digits = 2
        elif state.mode == "angle":
            value = _angle_between(points[0], points[1], points[2])
            digits = 1
        else:
            value = _dihedral_between(*points[:4])
            digits = 1
        if value is None:
            self._emit_error("measurement: degenerate geometry, nothing measured")
            return
        text = f"{value:.{digits}f}"

        name = f"{self.MEASURE_OBJECT}_{len(state.created):02d}"
        self._add_measurement(viewer, name, state.mode, points, text)
        state.created.append(name)
        where = " - ".join(label for _o, _a, label in picks)
        unit = "A" if state.mode == "distance" else "deg"
        self._emit_message(f"{state.mode} {name}: {where} = {text} {unit}")

    def _measure_delete(self, viewer, state, which: str) -> None:
        """Remove the last measurement, or every one this wizard made."""
        wanted = str(which).strip().lower() or "last"
        if not state.created:
            self._emit_message("measurement: nothing to delete")
            return
        if wanted == "all":
            doomed = list(state.created)
            state.created = []
        else:
            doomed = [state.created.pop()]
        remaining = {
            key: value for key, value in viewer._measurements.items()
            if key not in set(doomed)
        }
        viewer._measurements = remaining
        viewer._update_view()
        self._wizard_refresh(viewer, state)
        self._emit_message(f"measurement: deleted {len(doomed)}")

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

    def _draw_clashes(
        self, viewer, name, atoms, report, criteria, *, coords=None, radii=None
    ) -> None:
        """Draw the bumps where PyMOL draws them: **in the gap**, not atom to atom.

        `SculptCGOBump` mode 1 -- the mode the mutagenesis wizard turns on --
        does not draw a line between the two atom centres. It finds the
        *contact point*, the position dividing the pair in proportion to their
        radii, and draws a short cylinder across it whose radius is half the
        overlap. So a clash reads as a small mark sitting between two atoms,
        and a structure with fifty contacts looks like fifty marks.

        Drawing centre to centre, which is what this did, turns the same fifty
        contacts into fifty long lines crossing the molecule -- a spider's web
        with the actual overlaps somewhere inside it. Same data, unreadable
        picture, and it was the first thing anyone said about it.

        The mark is a segment rather than a cylinder because a chimol overlay
        draws lines; its **width** carries the radius, in the two buckets the
        overlay allows (PyMOL's own `CGOLinewidth(1 + color_factor * 3)` is the
        same idea with a continuous width).
        """
        from ..analysis.clashes import bump_geometry

        if coords is None:
            coords = np.asarray(atoms["xyz"], dtype=float)
        if radii is None:
            from ..analysis.clashes import radii_for

            radii = radii_for(
                [str(e) for e in atoms["element"]]
                if atoms is not None and "element" in (atoms.dtype.names or ())
                else []
            )
        coords = np.asarray(coords, dtype=float)
        radii = np.asarray(radii, dtype=float)

        measurements = dict(viewer._measurements)
        for suffix in ("", "_ok"):
            measurements.pop(f"{name}{suffix}", None)

        buckets = {
            f"{name}_ok": (
                [c for c in report.clashes if c.overlap < criteria.vis_mid], 2.0
            ),
            name: (
                [c for c in report.clashes if c.overlap >= criteria.vis_mid], 5.0
            ),
        }
        for key, (group, width) in buckets.items():
            if not group:
                continue
            pairs = np.empty((len(group) * 2, 3), dtype=float)
            colours = np.empty((len(group) * 2, 4), dtype=float)
            for k, clash in enumerate(group):
                end1, end2, _radius = bump_geometry(clash, coords, radii, criteria)
                pairs[2 * k] = end1
                pairs[2 * k + 1] = end2
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
