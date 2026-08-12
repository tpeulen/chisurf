"""The wizard panel, and the mutagenesis wizard that uses it.

PyMOL's wizards are the simplest GUI it has: a block of rows in the internal
GUI column -- a banner, some pop-ups, a couple of buttons -- plus a prompt in
the top-left of the viewport saying what it is waiting for. No dialog, no
window, nothing to arrange; `Wizard.get_panel()` returns
`[[1, 'Mutagenesis', ''], [3, 'Mutate to LYS', 'mode'], [2, 'Apply', '...']]`
and the viewport draws it.

That shape is transcribed here (:class:`~chimol.renderer.internal_gui.WizardRow`
is the row, with PyMOL's three codes spelled out as names) and the mutagenesis
wizard is the first user of it, because it is the one feature where a command
is genuinely the wrong surface: choosing a rotamer means *looking* at each one.

What the wizard adds over `mutate` as a command, and it is PyMOL's own design:

* every rotamer is built **once**, into an object called `mutation` with one
  **state per rotamer** -- `cmd.create(obj_name, frag_name, 1, state)` in a
  loop. Stepping is then a frame change and costs nothing. Rebuilding the
  residue inside the source object instead, which is what this did first, ran
  `set_structure` over the whole molecule per step: 2.2 s on a 1363-atom
  protein, two thirds of it recomputing ambient occlusion for atoms that had
  not moved;
* the strain and the frequency are on screen while you step, which is the whole
  content of PyMOL's panel;
* **the source structure is not touched until Apply.** Not "restored on
  cancel" -- untouched, because the preview is a different object. That is what
  makes Clear and Done free.

The measurement wizard is the second user, and it is here for the same reason:
``distance sele1, sele2`` requires already knowing which two atoms you mean,
which is exactly what you do not know when you want to measure something you
are looking at. It keeps almost no state -- a mode and the atoms picked so far
-- because each completed group is handed to the measurement machinery, which
is what the scene actually holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .object_menus import MenuEntry
from .renderer.internal_gui import WizardRow

__all__ = [
    "Wizard",
    "MutagenesisWizard",
    "MeasurementWizard",
    "MEASUREMENT_MODES",
    "RESIDUE_CHOICES",
]

#: PyMOL's measurement modes, and how many atoms each one waits for. The order
#: is PyMOL's own pop-up order, which is also increasing arity.
MEASUREMENT_MODES: tuple[tuple[str, str, int], ...] = (
    ("distance", "Distances", 2),
    ("angle", "Angles", 3),
    ("dihedral", "Dihedrals", 4),
)

#: The residues offered, in the order PyMOL's own menu lists them: by class,
#: not alphabetically, because that is how anyone thinks about a substitution.
RESIDUE_CHOICES: tuple[tuple[str, ...], ...] = (
    ("ALA", "GLY", "PRO", "VAL", "LEU", "ILE", "MET"),
    ("PHE", "TRP", "TYR"),
    ("SER", "THR", "CYS", "ASN", "GLN"),
    ("ASP", "GLU", "LYS", "ARG", "HIS"),
)


class Wizard:
    """What the viewport needs from a wizard: rows, a prompt, and menus."""

    #: Shown in the banner row.
    title = "Wizard"

    def panel(self) -> list[WizardRow]:
        """Return the rows to draw. PyMOL's ``get_panel``."""
        return [WizardRow("title", self.title)]

    def prompt(self) -> list[str]:
        """Return the instruction shown in the viewport. PyMOL's ``get_prompt``."""
        return []

    def menu(self, tag: str):
        """Return the entries for a pop-up row. PyMOL's ``get_menu``."""
        return ()

    def cleanup(self) -> None:
        """Undo anything not committed. PyMOL's ``cleanup``."""


@dataclass
class MutagenesisWizard(Wizard):
    """Pick a residue, choose what it becomes, step the rotamers, apply.

    Attributes
    ----------
    object_id, object_name : str
        Which object the picked residue belongs to.
    residue : tuple
        ``(chain, resi, resn)`` of the residue being mutated.
    target : str
        The residue it would become, or ``""`` before one is chosen.
    rotamer : int
        Which conformation is being previewed, zero-based.
    bump_check : bool
        Whether the clash lines are drawn for the previewed conformation --
        PyMOL's `bump_check`, on by default, and the reason the wizard exists
        rather than a command.
    """

    title = "Mutagenesis"

    object_id: str = ""
    object_name: str = ""
    residue: tuple = ()
    target: str = ""
    rotamer: int = 0
    bump_check: bool = True
    #: ``(frequency, strain)`` per rotamer of the current target, for the panel.
    scores: list[tuple[float, float]] = field(default_factory=list)
    #: The built rotamers, scored once. PyMOL builds them into an object with a
    #: state each and never rebuilds; so does this, and stepping is a frame.
    site: object | None = None
    #: The object id of that preview -- PyMOL's `mutation`.
    preview_id: str = ""

    def panel(self) -> list[WizardRow]:
        """Return PyMOL's panel: banner, pop-up, stepper, toggle, buttons."""
        rows = [WizardRow("title", self.title)]
        if not self.residue:
            rows.append(WizardRow("menu", "No residue picked", "residue"))
            rows.append(WizardRow("button", "Done", "wizard done"))
            return rows

        chain, resi, resn = self.residue
        where = f"{resn}`{resi}" + (f"/{chain}" if chain else "")
        rows.append(WizardRow("menu", f"Mutate {where} to {self.target or '...'}",
                              "residue"))
        if self.target and self.scores:
            frequency, strain = self.scores[self.rotamer]
            rows.append(WizardRow(
                "button",
                f"< rotamer {self.rotamer + 1}/{len(self.scores)} >",
                "wizard rotamer, next",
            ))
            rows.append(WizardRow(
                "menu",
                f"   {frequency * 100:.0f}%  strain {strain:.1f}",
                "rotamer",
            ))
        rows.append(WizardRow(
            "button",
            f"Bump check: {'on' if self.bump_check else 'off'}",
            "wizard bump, toggle",
        ))
        rows.append(WizardRow("button", "Apply", "wizard apply"))
        rows.append(WizardRow("button", "Clear", "wizard clear"))
        rows.append(WizardRow("button", "Done", "wizard done"))
        return rows

    def prompt(self) -> list[str]:
        """Return one line, saying what is being waited for."""
        if not self.residue:
            return ["Mutagenesis: pick a residue"]
        if not self.target:
            return ["Mutagenesis: choose what it becomes"]
        return [
            f"Mutagenesis: {self.rotamer + 1} of {len(self.scores)} rotamers"
            " -- Apply to keep it"
        ]

    def menu(self, tag: str):
        """Return the residue chooser, or the rotamer list."""
        if tag == "residue":
            entries: list[MenuEntry] = []
            for group in RESIDUE_CHOICES:
                if entries:
                    entries.append(MenuEntry(""))
                entries.extend(
                    MenuEntry(name, f"wizard target, {name}") for name in group
                )
            return tuple(entries)
        if tag == "rotamer":
            return tuple(
                MenuEntry(
                    f"{index + 1:3d}  {freq * 100:5.1f}%  strain {strain:6.2f}",
                    f"wizard rotamer, {index + 1}",
                )
                for index, (freq, strain) in enumerate(self.scores)
            )
        return ()


@dataclass
class MeasurementWizard(Wizard):
    """Click atoms; every two, three or four of them become a measurement.

    PyMOL's measurement wizard, and the reason it is a wizard rather than the
    ``distance`` command: naming two atoms in a selection expression means
    already knowing which two they are, and the whole point of measuring
    something on screen is that you do not.

    The state is deliberately small -- a mode and a list of picked atoms. Each
    completed group is handed straight to the measurement machinery and
    forgotten here, so the wizard owns nothing that would have to be rolled
    back; ``Delete`` works on the measurement objects, which are what the
    scene actually holds.

    Attributes
    ----------
    mode : str
        ``"distance"``, ``"angle"`` or ``"dihedral"`` -- see
        :data:`MEASUREMENT_MODES`.
    picks : list of tuple
        ``(object_id, atom_index, label)`` for each atom picked since the last
        completed measurement. Never longer than the mode's arity.
    created : list of str
        Names of the measurements this wizard has made, newest last, so
        ``Delete Last`` knows what to remove.
    """

    title = "Measurement"

    mode: str = "distance"
    picks: list = field(default_factory=list)
    created: list = field(default_factory=list)

    @property
    def wanted(self) -> int:
        """How many atoms the current mode needs."""
        for name, _label, count in MEASUREMENT_MODES:
            if name == self.mode:
                return count
        return 2

    @property
    def mode_label(self) -> str:
        """The current mode's name as the panel spells it."""
        for name, label, _count in MEASUREMENT_MODES:
            if name == self.mode:
                return label
        return self.mode.title()

    def panel(self) -> list[WizardRow]:
        """Return the banner, the mode pop-up, the picks so far, the buttons."""
        rows = [WizardRow("title", self.title)]
        rows.append(WizardRow("menu", self.mode_label, "mode"))
        # Buttons, not pop-up rows: the panel's vocabulary is PyMOL's three
        # kinds, and a `menu` row draws a drop-down arrow. A pick has no menu
        # behind it, so an arrow there is a control that does nothing -- and a
        # mis-clicked atom needs taking back anyway, which is what these do.
        for index, (_obj_id, _atom, label) in enumerate(self.picks):
            rows.append(WizardRow(
                "button", f"  {index + 1}. {label}   ×", "wizard unpick"
            ))
        if self.created:
            rows.append(WizardRow("button", "Delete Last", "wizard delete, last"))
            rows.append(WizardRow("button", "Delete All", "wizard delete, all"))
        rows.append(WizardRow("button", "Done", "wizard done"))
        return rows

    def prompt(self) -> list[str]:
        """Return one line naming the atom being waited for."""
        return [
            f"{self.mode_label[:-1]}: pick atom "
            f"{len(self.picks) + 1} of {self.wanted}"
        ]

    def menu(self, tag: str):
        """Return the mode chooser."""
        if tag == "mode":
            return tuple(
                MenuEntry(label, f"wizard mode, {name}")
                for name, label, _count in MEASUREMENT_MODES
            )
        return ()
