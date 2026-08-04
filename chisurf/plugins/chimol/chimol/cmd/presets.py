"""PyMOL's ``preset`` family, transcribed from ``modules/pymol/preset.py``.

A preset is the one-click path from "a structure is loaded" to "this looks like
a figure", and it is the most-used entry in PyMOL's object menu. Each one is a
short recipe of ordinary commands -- hide, show, colour, a couple of settings --
so the value is entirely in *which* recipe, and that is what makes approximating
them pointless: four hand-rolled entries reading ``hide everything; show
cartoon`` share PyMOL's labels while producing a different picture, which is
worse than not having them.

So the recipes here are transcribed, in PyMOL's order, with PyMOL's names. Where
chimol has no equivalent for a step the step is **skipped and named** rather
than approximated -- :meth:`PresetMixin._preset_note` collects them and the
command reports them once, so a preset never quietly does less than it says.
The mapping decisions worth knowing:

* PyMOL's ``ribbon`` is a thinner representation than its cartoon; chimol draws
  one cartoon, so ``show ribbon`` here means ``show cartoon``.
* polar contacts are PyMOL's ``dist ... mode=2``, which chimol now has
  (:mod:`~chimol.analysis.hbonds`); the presets draw them for real.
* ``cartoon_fancy_helices`` and ``cartoon_highlight_color`` are not implemented
  by chimol's cartoon, so they are not registered as settings (a setting that
  reads nothing is exactly what the settings table exists to prevent) and the
  presets that set them say so. ``cartoon_side_chain_helper`` *is* implemented
  and the presets set it for real.
* PyMOL scopes a setting to a selection (``set stick_radius, 0.14, sele``);
  chimol's settings are one global display config. A preset that changes a
  setting therefore changes it for everything, and says so once rather than
  leaving the difference to be discovered on the second object.

The colour helpers are PyMOL's ``util`` functions of the same names: ``cbc``
colours each chain from :data:`~chimol.colors.CHAIN_COLOR_CYCLE`, ``cnc``
colours everything *except* carbon by element, ``cbac``/``cbag`` do that and
then set carbon to one colour, and ``chainbow`` runs a spectrum along each chain.
"""

from __future__ import annotations

import numpy as np

from ..colors import CHAIN_COLOR_CYCLE, _build_element_color_array
from .base import BaseCmd
from .registry import command

# --------------------------------------------------------------------------- #
# The selections preset.py builds its recipes from, transcribed verbatim.
# --------------------------------------------------------------------------- #
#: Residues PyMOL treats as the polymer for preset purposes. Spelled out rather
#: than using chimol's `polymer` class because the two differ at the edges --
#: MSE, the non-standard histidine names -- and a preset that picks a different
#: set of atoms draws a different picture.
PROT_AND_DNA = (
    "resn ALA+CYS+CYX+ASP+GLU+PHE+GLY+HIS+HID+HIE+HIP+HISE+HISD+HISP+ILE+LYS+"
    "LEU+MET+MSE+ASN+PRO+GLN+ARG+SER+THR+VAL+TRP+TYR+A+C+T+G+U+DA+DC+DT+DG+DU+DI"
)
WAT_SELE = "solvent"
ION_SELE = "resn CA+HG+K+NA+ZN+MG+CL"
SOLV_SELE = f"(({WAT_SELE}) or ({ION_SELE}))"
LIG_EXCL = "resn MSE"
LIG_SELE = (
    f"((hetatm or not ({PROT_AND_DNA})) and not "
    f"(({SOLV_SELE}) or ({ION_SELE}) or ({LIG_EXCL})))"
)
LIG_AND_SOLV = f"(({LIG_SELE}) or ({SOLV_SELE}))"


class PresetMixin(BaseCmd):
    """The ``preset`` command and the ``util`` colour helpers it is built from."""

    #: name -> (menu label, one-line description). The order is PyMOL's menu
    #: order, which is what the object menu renders.
    PRESETS: dict[str, str] = {
        "classified": "representations by atom class, colours untouched",
        "simple": "chain colours, cartoon, ligands as sticks",
        "simple_no_solv": "simple, with the solvent hidden",
        "ball_and_stick": "everything as balls and sticks",
        "b_factor_putty": "a putty cartoon ramped by b-factor",
        "technical": "chain rainbow, lines everywhere, ligands as sticks",
        "ligands": "the ligands and what surrounds them",
        "ligand_sites": "ligand sites, with a surface on the pocket",
        "ligand_cartoon": "ligand sites, drawn as a cartoon",
        "pretty": "cartoon ramped along the sequence, ligands as sticks",
        "pretty_solv": "pretty, keeping the solvent",
        "publication": "pretty, with smoothed loops",
        "pub_solv": "publication, keeping the solvent",
        "interface": "chains coloured, interface residues as sticks",
        "default": "lines and nonbonded, coloured by element",
    }

    @command("preset")
    def preset(self, name: str = "", selection: str = "all") -> None:
        """Apply one of PyMOL's presets (PyMOL ``preset.<name>``).

        Parameters
        ----------
        name : str
            One of :attr:`PRESETS`. With no name, the available presets are
            listed.
        selection : str, optional
            What to apply it to; everything by default.
        """
        key = str(name).strip().lower().replace(" ", "_")
        if not key:
            self._emit_message(
                "preset: "
                + ", ".join(
                    f"{n} ({d})" for n, d in self.PRESETS.items()
                )
            )
            return
        if key not in self.PRESETS:
            self._emit_error(
                f"Unknown preset '{name}'. Use one of: "
                + ", ".join(self.PRESETS)
            )
            return

        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        sel = str(selection).strip() or "all"
        self._preset_skipped: list[str] = []
        try:
            getattr(self, f"_preset_{key}")(sel)
        except Exception as exc:
            self._emit_error(f"preset {key}: {exc}")
            return

        message = f"preset {key}: applied to ({sel})"
        if self._preset_skipped:
            # Named, not silently dropped: a preset that quietly does less than
            # PyMOL's is the failure this whole module exists to avoid.
            message += " -- not applied: " + "; ".join(
                dict.fromkeys(self._preset_skipped)
            )
        self._emit_message(message)

    # ------------------------------------------------------------------ #
    # Shared steps
    # ------------------------------------------------------------------ #
    def _preset_note(self, what: str) -> None:
        """Record a step chimol cannot perform, to report once at the end."""
        self._preset_skipped.append(what)

    def _preset_prepare(self, sel: str) -> None:
        """PyMOL's ``_prepare``: undo what any preset does, except the colours."""
        self._run_preset_command(f"cartoon auto, {sel}")
        self._run_preset_command(f"hide everything, {sel}")
        self._set_global("sphere_scale", 1.0, note=False)
        self._set_global("stick_radius", 0.15, note=False)
        self._set_global("cartoon_flat_sheets", "on", note=False)
        self._set_global("cartoon_smooth_loops", "off", note=False)
        self._set_global("cartoon_side_chain_helper", "off", note=False)

    def _set_global(self, name: str, value, *, note: bool = True) -> None:
        """Write a setting, noting that chimol's are not per-selection.

        PyMOL takes a third argument here and scopes the value to an object;
        chimol keeps one display config, so the change reaches everything. The
        note is what stops that being a surprise on the second object -- but it
        is only worth making when the preset is *choosing* a value. The resets
        in :meth:`_preset_prepare` pass ``note=False``: restoring a default
        everywhere is what "undo the other presets" means anyway.
        """
        self._run_preset_command(f"set {name}, {value}")
        if note:
            self._preset_note(
                f"{name} is global in chimol, so it was not scoped to the selection"
            )

    def _run_preset_command(self, line: str) -> None:
        """Run one step, letting a failure abort the preset with its message."""
        self.do(line)

    def _polar_contacts(
        self, sele1: str, sele2: str, *, name: str,
        dash_width: float | None = None, require: str | None = None,
    ) -> None:
        """PyMOL's ``dist <name>, s1, s2, mode=2, label=0, reset=1`` step.

        Unlabelled on purpose: a protein draws a few hundred contacts and a
        number over each is unreadable. PyMOL hides the labels straight after
        creating them for the same reason.

        Parameters
        ----------
        sele1, sele2 : str
            The two sides of the contact search.
        name : str
            Measurement name, so re-running a preset replaces its contacts
            rather than stacking a second set on top.
        dash_width : float, optional
            ``technical`` draws thinner dashes than the default.
        require : str, optional
            A selection that must match something first -- PyMOL's
            ``if cmd.count_atoms(lig)``. With no ligand there is nothing to
            contact, and an empty measurement object is worse than none.
        """
        if require is not None and not self._count_atoms(require):
            return
        self._run_preset_command(
            f"distance {name}, {sele1}, {sele2}, mode=2, label=0, quiet=1"
        )
        if dash_width is not None:
            self._set_global("dash_width", dash_width)

    def _count_atoms(self, sele: str) -> int:
        """How many atoms a selection reaches, across every object."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return 0
        try:
            hits = self._resolve_selection_to_atom_masks(viewer, sele)
        except ValueError:
            return 0
        return sum(int(np.count_nonzero(mask)) for _id, _name, mask in hits)

    # -- the util colour helpers ---------------------------------------- #
    def _chains_in(self, sel: str) -> list[str]:
        """Chain identifiers the selection touches, sorted as ``get_chains`` is."""
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return []
        found: set[str] = set()
        for obj_id, _name, mask in self._resolve_selection_to_atom_masks(viewer, sel):
            state = getattr(viewer._objects.get(obj_id), "state", None)
            atoms = getattr(state, "atoms", None)
            if atoms is None or "chain" not in (atoms.dtype.names or ()):
                continue
            chains = np.asarray(atoms["chain"])[np.asarray(mask, dtype=bool)]
            found.update(str(c).strip() for c in chains.tolist() if str(c).strip())
        return sorted(found)

    def _cbc(self, sel: str) -> None:
        """PyMOL ``util.cbc``: one colour per chain, from the shared cycle."""
        for index, chain in enumerate(self._chains_in(sel)):
            colour = CHAIN_COLOR_CYCLE[index % len(CHAIN_COLOR_CYCLE)]
            self._run_preset_command(f"color {colour}, chain {chain} and ({sel})")

    def _chainbow(self, sel: str) -> None:
        """PyMOL ``util.chainbow``: a rainbow along each chain separately."""
        chains = self._chains_in(sel)
        if not chains:
            self._run_preset_command(f"spectrum count, rainbow, {sel}")
            return
        for chain in chains:
            self._run_preset_command(
                f"spectrum count, rainbow, chain {chain} and ({sel})"
            )

    def _color_by_element(self, sel: str, carbon: str | None = None) -> None:
        """PyMOL's ``util.cnc`` (``carbon=None``) and ``cbac``/``cbag`` family.

        Non-carbon atoms take their element's colour; carbon takes ``carbon``
        when one is given and is left alone otherwise. Written straight as
        per-atom overrides rather than through the by-element colour *mode*,
        because a mode belongs to a whole object and this has to reach a subset.
        """
        _, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        for obj_id, _name, mask in self._resolve_selection_to_atom_masks(viewer, sel):
            state = getattr(viewer._objects.get(obj_id), "state", None)
            atoms = getattr(state, "atoms", None)
            if atoms is None or "element" not in (atoms.dtype.names or ()):
                continue
            mask = np.asarray(mask, dtype=bool)
            elements = np.char.upper(
                np.char.strip(np.asarray(atoms["element"]).astype(str))
            )
            chosen = np.nonzero(mask & (elements != "C"))[0]
            if not chosen.size:
                continue
            colours = _build_element_color_array(elements[chosen], chosen.size)
            viewer.set_atom_color_override(chosen, colours, object_id=obj_id)
        if carbon:
            self._run_preset_command(f"color {carbon}, elem C and ({sel})")

    # ------------------------------------------------------------------ #
    # The presets
    # ------------------------------------------------------------------ #
    def _preset_classified(self, sel: str) -> None:
        """Representations from the atom classes, colours untouched."""
        self._preset_prepare(sel)
        self._run_preset_command(f"show cartoon, polymer and ({sel})")
        self._run_preset_command(f"show sticks, organic and ({sel})")
        self._run_preset_command(f"show spheres, inorganic and ({sel})")

    def _preset_simple(self, sel: str) -> None:
        self._preset_prepare(sel)
        self._cbc(sel)
        self._run_preset_command(f"show cartoon, {sel}")
        self._run_preset_command(f"show sticks, ({LIG_SELE}) and ({sel})")
        self._run_preset_command(f"show nonbonded, ({LIG_AND_SOLV}) and ({sel})")
        self._run_preset_command(f"show lines, ({LIG_AND_SOLV}) and ({sel})")
        # PyMOL colours "rep lines or rep sticks or the ligands and solvent",
        # reading back which atoms it has just shown. chimol's representation
        # visibility is per object rather than per atom, so `rep lines` cannot
        # be answered here -- the set is instead named directly, which is what
        # the three lines above have just shown anyway.
        self._color_by_element(f"({LIG_AND_SOLV}) and ({sel})")

    def _preset_simple_no_solv(self, sel: str) -> None:
        self._preset_simple(sel)
        self._run_preset_command(f"hide everything, ({SOLV_SELE}) and ({sel})")

    def _preset_ball_and_stick(self, sel: str) -> None:
        self._preset_prepare(sel)
        self._set_global("stick_radius", 0.14)
        self._set_global("sphere_scale", 0.25)
        self._run_preset_command(f"show sticks, {sel}")
        self._run_preset_command(f"show spheres, {sel}")
        self._preset_note("white sticks (chimol has no per-bond stick_color)")

    def _preset_b_factor_putty(self, sel: str) -> None:
        self._preset_prepare(sel)
        self._set_global("cartoon_flat_sheets", "off")
        self._run_preset_command(f"cartoon putty, {sel}")
        self._run_preset_command(f"show cartoon, {sel}")
        self._run_preset_command(f"spectrum b, rainbow, {sel}")

    def _preset_technical(self, sel: str) -> None:
        self._preset_prepare(sel)
        self._chainbow(sel)
        self._cbc(f"({LIG_SELE}) and ({sel})")
        self._color_by_element(sel)
        self._run_preset_command(f"show nonbonded, {sel}")
        self._run_preset_command(f"show lines, (({sel}) and not ({LIG_SELE}))")
        self._run_preset_command(f"show sticks, ({LIG_SELE}) and ({sel})")
        self._run_preset_command(f"show cartoon, {sel}")
        self._polar_contacts(sel, sel, name="polar_conts", dash_width=1.5)

    def _preset_ligands(self, sel: str) -> None:
        self._preset_prepare(sel)
        host = f"({PROT_AND_DNA}) and ({sel})"
        lig = f"({LIG_SELE}) and ({sel})"
        self._chainbow(host)
        self._cbc(lig)
        self._color_by_element(sel)
        self._run_preset_command(f"hide everything, {sel}")
        self._run_preset_command(f"show cartoon, {host}")
        self._run_preset_command(f"show lines, byres (({host}) within 5 of ({lig}))")
        self._run_preset_command(f"show sticks, {lig}")
        self._run_preset_command(f"show nonbonded, {lig}")
        # PyMOL measures host-to-ligand including the waters bridging them, and
        # skips the step entirely when the selection holds no ligand -- an empty
        # contact object left behind is worse than none.
        near_solvent = f"({SOLV_SELE}) and ({sel}) and (({lig}) around 4)"
        self._polar_contacts(
            f"({host}) or ({near_solvent})",
            f"({lig}) or ({near_solvent})",
            name="polar_conts",
            require=lig,
        )

    def _preset_ligand_sites(self, sel: str) -> None:
        self._preset_ligands(sel)
        lig = f"({LIG_SELE}) and ({sel})"
        self._run_preset_command(
            f"show surface, (({sel}) and (byres (({sel}) within 6 of ({lig}))))"
        )
        self._set_global("two_sided_lighting", "on")
        self._set_global("transparency", 0.0)
        # PyMOL's fourth step here is `surface_quality 0`, and chimol's setting
        # of that name means something else: PyMOL takes a level (0-4, coarse to
        # fine) while chimol's is the grid *spacing* in Angstrom, where 0 is not
        # "coarse" but "infinitely fine". Passing it through would hang rather
        # than approximate, so it is named instead.
        self._preset_note(
            "surface_quality (PyMOL's is a level, chimol's a grid spacing)"
        )

    def _preset_ligand_cartoon(self, sel: str) -> None:
        self._preset_ligand_sites(sel)
        self._run_preset_command(f"hide surface, {sel}")
        self._run_preset_command(f"show cartoon, {sel}")
        self._set_global("cartoon_side_chain_helper", "on")

    def _preset_pretty(self, sel: str, *, solvent: bool = False) -> None:
        self._preset_prepare(sel)
        self._run_preset_command("dss")
        self._run_preset_command(f"cartoon auto, {sel}")
        self._run_preset_command(f"show cartoon, {sel}")
        lig = f"({LIG_AND_SOLV})" if solvent else f"({LIG_SELE})"
        self._run_preset_command(f"show sticks, {lig} and ({sel})")
        self._cbc(f"{lig} and ({sel})")
        self._color_by_element(f"{lig} and ({sel})")
        self._run_preset_command(
            f"spectrum count, rainbow, elem C and ({sel}) and not {lig}"
        )
        self._set_global("cartoon_flat_sheets", "on")
        self._set_global("cartoon_smooth_loops", "off")
        self._set_global("cartoon_side_chain_helper", "off")
        self._preset_note(
            "cartoon_highlight_color and cartoon_fancy_helices "
            "(not implemented by chimol's cartoon)"
        )

    def _preset_pretty_solv(self, sel: str) -> None:
        self._preset_pretty(sel, solvent=True)

    def _preset_publication(self, sel: str, *, solvent: bool = False) -> None:
        self._preset_pretty(sel, solvent=solvent)
        self._set_global("cartoon_smooth_loops", "on")
        self._set_global("cartoon_flat_sheets", "on")

    def _preset_pub_solv(self, sel: str) -> None:
        self._preset_publication(sel, solvent=True)

    def _preset_interface(self, sel: str) -> None:
        """PyMOL's protein-protein interface preset."""
        self._preset_prepare(sel)
        chains = self._chains_in(sel)
        self._cbc(sel)
        self._color_by_element(sel)
        self._run_preset_command(f"as cartoon, {sel}")
        if len(chains) < 2:
            self._preset_note("interface residues (the selection has one chain)")
            return
        around = " or ".join(f"((chain {c}) around 4.5)" for c in chains)
        interface = f"({sel}) and ({around})"
        self._run_preset_command(f"show sticks, byres ({interface})")
        self._run_preset_command(f"show nonbonded, {interface}")

    def _preset_default(self, sel: str) -> None:
        self._preset_prepare(sel)
        self._run_preset_command(f"show lines, {sel}")
        self._run_preset_command(f"show nonbonded, {sel}")
        self._color_by_element(sel, carbon="carbon")
