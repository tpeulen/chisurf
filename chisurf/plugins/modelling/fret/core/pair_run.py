"""One pair-selection run, Qt-free: trajectory + candidate sites in, the informative pairs and the RMSD decay out.

Both windows of the pair selection (the Qt ``FRETPairSelectionWindow`` and the native one) call :func:`run_pair_selection`
with the same :class:`PairParams`; nothing of the run lives in a widget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from chisurf.core.structure import trajectory_data as md

from .olga_greedy import select_informative_pairs
from .trajectory import (
    build_atom_pairs,
    build_sites,
    candidate_pairs_from_fps_json,
    compute_efficiencies,
    compute_efficiencies_from_fps_av,
    compute_efficiencies_per_pair_r0,
    load_fps_json,
    parse_residue_ranges,
    positions_from_fps_json,
    rmsd_matrix,
)

ATTACHMENT_ATOMS = ("CB", "CA")


@dataclass
class PairParams:
    """What the user chose (the Qt window's fields, same names and defaults)."""

    trajectory: str = ""
    topology: str = ""
    fps_json: str = ""
    use_av: bool = True
    av_samples: int = 5000
    av_max_points: int = 20000
    chain: str = "A"
    residues: str = "35-50,85-95,115-120"
    atom: str = "CB"
    r0: float = 52.0
    err: float = 0.06
    max_pairs: int = 10
    unique_only: bool = True
    stride: int = 1
    rmsd_selection: str = "name CA"


@dataclass
class PairResult:
    """The pairs chosen, in the order they were added, and the mean RMSD after each."""

    pair_names: list[str]
    selected: np.ndarray
    decay: np.ndarray
    warnings: list[str] = field(default_factory=list)

    def rows(self) -> list[tuple[int, str, float]]:
        """``(number, pair, <<RMSD>>)`` per chosen pair, as the Qt table lists them."""
        return [(i + 1, self.pair_names[int(self.selected[i])], float(self.decay[i]))
                for i in range(int(self.selected.shape[0]))]

    def export_text(self) -> str:
        """The text file the Qt Export button writes."""
        lines = ["#\tPair_added\t<<RMSD>>/A\n"]
        lines += [f"{n}\t{pair}\t{rmsd:.2f}\n" for n, pair, rmsd in self.rows()]
        return "".join(lines)

    def export(self, path: str | Path) -> None:
        Path(path).write_text(self.export_text(), encoding="utf-8")


def load_trajectory(params: PairParams) -> md.Trajectory:
    """Read the trajectory (with the topology when it exists), every ``stride``-th frame."""
    traj_text = params.trajectory.strip()
    traj_path = Path(traj_text)
    if not traj_text or not traj_path.exists():       # Path("") is the working directory, which exists
        raise ValueError("Trajectory file does not exist")
    top_text = params.topology.strip()
    top_path = Path(top_text) if top_text else None
    stride = int(params.stride)
    if top_path and top_path.exists():
        return md.load(str(traj_path), top=str(top_path), stride=stride)
    return md.load(str(traj_path), stride=stride)


def run_pair_selection(params: PairParams, warn: Callable[[str, str], None] | None = None) -> PairResult:
    """Run the selection; *warn(title, text)* hears of the AV backend falling back to attachment-atom distances."""
    warnings: list[str] = []
    traj = load_trajectory(params)
    fps_text = params.fps_json.strip()
    fps_path = Path(fps_text) if fps_text else None
    default_r0 = float(params.r0)
    if fps_path is not None and fps_path.exists():
        fps = load_fps_json(fps_path)
        positions = positions_from_fps_json(traj, fps)
        if len(positions) < 2:
            raise ValueError("fps.json did not yield at least 2 valid labeling positions")
        atom_pairs, pair_names, r0s, pair_position_names = candidate_pairs_from_fps_json(
            positions=positions, fps=fps, default_r0_angstrom=default_r0)
        if atom_pairs.shape[0] == 0:
            raise ValueError("No candidate pairs found in fps.json")
        if params.use_av:
            try:
                effs = compute_efficiencies_from_fps_av(
                    traj=traj, fps=fps, pair_position_names=pair_position_names, r0s_angstrom=r0s,
                    n_samples=int(params.av_samples), max_points_per_av=int(params.av_max_points))
            except Exception as av_exc:  # noqa: BLE001 - the Qt tool falls back the same way
                text = ("Failed to compute AV-based efficiencies (falling back to attachment-atom distances)."
                        f"\n\n{av_exc}")
                warnings.append(text)
                if warn is not None:
                    warn("AV backend unavailable", text)
                effs = compute_efficiencies_per_pair_r0(traj, atom_pairs, r0s)
        else:
            effs = compute_efficiencies_per_pair_r0(traj, atom_pairs, r0s)
    else:
        residue_numbers = parse_residue_ranges(params.residues)
        if not residue_numbers:
            raise ValueError("No residues specified")
        atom_name = str(params.atom)
        sites = build_sites(traj, chain_spec=params.chain.strip(), residue_numbers=residue_numbers,
                            atom_name=atom_name, fallback_atom_name="CA" if atom_name == "CB" else None)
        if len(sites) < 2:
            raise ValueError("Need at least 2 valid residues with an attachment atom")
        atom_pairs, pair_names = build_atom_pairs(sites)
        effs = compute_efficiencies(traj, atom_pairs, r0_angstrom=default_r0)

    rmsds = rmsd_matrix(traj, atom_selection=params.rmsd_selection.strip() or None)
    selected, decay = select_informative_pairs(
        effs=effs, rmsds=rmsds, err=float(params.err), max_pairs=int(params.max_pairs),
        unique_only=bool(params.unique_only))
    return PairResult(list(pair_names), selected, decay, warnings)


__all__ = ["ATTACHMENT_ATOMS", "PairParams", "PairResult", "load_trajectory", "run_pair_selection"]
