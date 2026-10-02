"""emtk app for Trajectory→FRET: per-frame donor-acceptor distance, κ² and FRET rate of a trajectory.

Drawn from ``structure2transfer.view.json`` by the shared trajectory-tool app:
the Reference panel (trajectory and topology rows of the custom ``fret_traj_io``
section, the stride), the Dipole atoms panel (the custom ``fret_atom_pairs``
section: chain → residue → atom pickers for the two donor and two acceptor
atoms, as the Qt PDBSelectors cascade), Parameters, and Process (the custom
``fret_run`` button and the log).
"""

from __future__ import annotations

import pathlib

import numpy as np
from emtk import im

from chisurf.plugins.traj.emtk_tool import SaveAction, icon_label, TrajToolApp, topology_field, trajectory_field

from .view_model import FretTrajectoryViewModel

HERE = pathlib.Path(__file__).parent

PROCESS = SaveAction(
    key="process",
    label=icon_label("▶", "Process trajectory"),
    tooltip="Compute the FRET observables and save them to a CSV file.",
    dialog_title="Output-file",
    filters=[("CSV", ["*.csv"]), ("All files", ["*"])],
    run=lambda model, path: model.calc(output_file=path),
    missing=lambda model: None if (model.filenames or model.trajectory_file) else "Open a trajectory first.",
    suggest=lambda model: pathlib.Path(model.trajectory_file).stem + "_fret.csv",
    failure="Processing failed",
    cancelled="Process cancelled",
    done="",
)

PATHS = [
    trajectory_field(attr="trajectory_file", tooltip="The trajectory to analyse. Drop a .dcd here or press … to "
                                                     "pick one."),
    topology_field(tooltip="The structure that names the atoms of the DCD; the atom pickers list its atoms."),
]


class AtomIndex:
    """Chains, residues and atoms of a structured coordinate array, for the cascading pickers."""

    def __init__(self, pdb: np.ndarray) -> None:
        self.pdb = pdb
        self.chains = sorted({str(c) for c in pdb["chain"]})
        self.residues = {c: sorted({int(r) for r in pdb["res_id"][pdb["chain"] == c]}) for c in self.chains}
        self._atoms: dict[tuple[str, int], list[int]] = {}
        for index, (chain, residue) in enumerate(zip(pdb["chain"], pdb["res_id"])):
            self._atoms.setdefault((str(chain), int(residue)), []).append(index)

    def atoms(self, chain: str, residue: int) -> list[int]:
        return self._atoms.get((chain, residue), [])

    def where(self, index: int) -> tuple[str, int]:
        atom = self.pdb[int(index)]
        return str(atom["chain"]), int(atom["res_id"])

    def name(self, index: int) -> str:
        atom = self.pdb[int(index)]
        return f"{atom['atom_name']}"

    def label(self, index: int) -> str:
        atom = self.pdb[int(index)]
        return f"{atom['chain']}:{atom['res_name']}{atom['res_id']}:{atom['atom_name']}"


class FretTrajectoryApp(TrajToolApp):
    """The Trajectory→FRET window."""

    def __init__(self, model: FretTrajectoryViewModel | None = None) -> None:
        super().__init__(model or FretTrajectoryViewModel(), HERE, "structure2transfer.view.json",
                         "fret_traj_io", "Trajectory to FRET", PATHS, PROCESS, action_key="fret_run")
        self.form.custom["fret_atom_pairs"] = self.draw_atom_pairs
        self._atom_cache: AtomIndex | None = None

    def atom_index(self) -> AtomIndex | None:
        pdb = self.model.pdb
        if pdb is None:
            return None
        if self._atom_cache is None or self._atom_cache.pdb is not pdb:
            self._atom_cache = AtomIndex(pdb)
        return self._atom_cache

    def draw_atom_pairs(self, section, model, state, width) -> None:
        index = self.atom_index()
        if index is None:
            im.text_disabled("Choose the trajectory and its topology to pick the atoms.")
            self.remember("donor")
            self.remember("acceptor")
            return
        column = (width - im.get_style().item_spacing[0]) / 2.0
        top = im.get_cursor_screen_pos()
        bottom = top[1]
        for k, (role, attr) in enumerate((("Donor", "donor"), ("Acceptor", "acceptor"))):
            x = top[0] + k * (column + im.get_style().item_spacing[0])
            im.set_cursor_screen_pos((x, top[1]))
            im.begin_group()
            im.text(role)
            third = (column - 2 * im.get_style().item_spacing[0]) / 3.0
            for j, caption in enumerate(("Chain", "Residue", "Atom")):          # the Qt selectors' captions
                if j:
                    im.same_line(j * (third + im.get_style().item_spacing[0]))   # from the group's start
                im.text_disabled(caption)
            pair = list(getattr(model, attr))
            for slot in range(2):
                new = self._picker(index, f"{attr}{slot}", int(pair[slot]), column)
                if new != pair[slot]:
                    pair[slot] = new
                    setattr(model, attr, tuple(pair))
                    self.tour.notify_used(attr)
            im.end_group()
            self.remember(attr, (x, top[1], column, im.get_cursor_screen_pos()[1] - top[1]))
            bottom = max(bottom, im.get_cursor_screen_pos()[1])
        im.set_cursor_screen_pos((top[0], bottom))
        im.dummy(width, 1.0)

    def _picker(self, index: AtomIndex, key: str, atom: int, width: float) -> int:
        """Chain, residue and atom combos for one atom; returns the (possibly new) atom index."""
        atom = min(max(int(atom), 0), len(index.pdb) - 1)
        chain, residue = index.where(atom)
        third = (width - 2 * im.get_style().item_spacing[0]) / 3.0
        tip = "Chain, residue and atom of one dipole atom; with dipoles off only the first atom of each dye counts."
        im.set_next_item_width(third)
        changed, c = im.combo(f"##{key}.chain", index.chains.index(chain), index.chains)
        im.set_item_tooltip(tip)
        if changed:
            chain = index.chains[c]
            residue = index.residues[chain][0]
            return index.atoms(chain, residue)[0]
        im.same_line()
        residues = index.residues[chain]
        im.set_next_item_width(third)
        changed, r = im.combo(f"##{key}.residue", residues.index(residue), [str(v) for v in residues])
        im.set_item_tooltip(tip)
        if changed:
            return index.atoms(chain, residues[r])[0]
        im.same_line()
        atoms = index.atoms(chain, residue)
        im.set_next_item_width(third)
        changed, a = im.combo(f"##{key}.atom", atoms.index(atom), [index.name(i) for i in atoms])
        im.set_item_tooltip(tip)
        return atoms[a] if changed else atom

    def export_settings(self) -> dict:
        settings = super().export_settings()
        settings["donor"] = [int(v) for v in self.model.donor]
        settings["acceptor"] = [int(v) for v in self.model.acceptor]
        return settings

    def restore_settings(self, settings: dict) -> None:
        super().restore_settings(settings)
        if self.model.topology_filename:
            # Through the setter: it tells the engine the topology and loads the atoms the pickers list.
            self.model.set_topology(self.model.topology_filename)
        for attr in ("donor", "acceptor"):
            if len(settings.get(attr) or ()) == 2:
                setattr(self.model, attr, tuple(int(v) for v in settings[attr]))


def make_app(**kwargs) -> FretTrajectoryApp:
    """Construct the standalone Trajectory→FRET app."""
    from chisurf.emtk.i18n import install

    install()
    return FretTrajectoryApp()


__all__ = ["AtomIndex", "FretTrajectoryApp", "make_app"]
