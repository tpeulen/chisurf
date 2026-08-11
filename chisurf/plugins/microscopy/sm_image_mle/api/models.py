"""Transport dataclasses for molecule-wise MLE analysis (no Qt).

The analysis settings live in the Qt-free core (:class:`MoleculeMleSettings`
in :mod:`..core.molecule_mle`); this module re-exports them and adds the
request/result envelopes used by the CLI and RPC backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.molecule_mle import MoleculeMleSettings

__all__ = ["MoleculeMleSettings", "MoleculeMleRequest", "MoleculeMleResult"]


@dataclass
class MoleculeMleRequest:
    """A full molecule-wise MLE analysis request.

    Parameters
    ----------
    files : list of str
        CLSM TTTR image files to analyse.
    irf_file : str
        IRF TTTR measurement (shared by all files).
    output_dir : str, optional
        Directory for the merged joint TSV; defaults to the first file's parent.
    settings : MoleculeMleSettings, optional
        Analysis settings (segmentation, channels, estimator).
    shift_sp, shift_ss : float, optional
        Circular IRF shifts (parallel / perpendicular).
    irf_threshold_fraction : float, optional
        IRF denoising threshold fraction.
    """

    files: list[str]
    irf_file: str
    output_dir: str = ""
    settings: MoleculeMleSettings = field(default_factory=MoleculeMleSettings)
    shift_sp: float = 0.0
    shift_ss: float = 0.0
    irf_threshold_fraction: float = 0.08


@dataclass
class MoleculeMleResult:
    """Result of a molecule-wise MLE analysis run.

    Attributes
    ----------
    processed_files : list of str
        Files that produced molecule data.
    output_paths : list of str
        Per-file molecule-data TSV paths.
    joint_tsv : str
        Path to the merged joint TSV (empty when nothing was produced).
    n_molecules : int
        Total number of molecules fitted across all files.
    warnings : list of str
        Non-fatal problems encountered per file.
    """

    processed_files: list[str]
    output_paths: list[str]
    joint_tsv: str = ""
    n_molecules: int = 0
    warnings: list[str] = field(default_factory=list)
