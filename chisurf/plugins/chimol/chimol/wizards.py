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

What the wizard adds over `mutate` as a command:

* the rotamer is **stepped and seen**. PyMOL puts each rotamer in a state of a
  preview object and you scrub the states; chimol applies them in place and
  offers `<` and `>`, which is the same loop with one less object to explain;
* the strain and the frequency are on screen while you step, which is the whole
  content of PyMOL's panel;
* **nothing is committed until Apply.** The original residue's rows are kept
  and put back by Clear or by leaving -- a preview that cannot be undone is not
  a preview.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .object_menus import MenuEntry
from .renderer.internal_gui import WizardRow

__all__ = ["Wizard", "MutagenesisWizard", "RESIDUE_CHOICES"]

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
    #: The residue's original rows, kept so Clear and leaving can put them back.
    original: np.ndarray | None = None
    original_at: int = -1

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
