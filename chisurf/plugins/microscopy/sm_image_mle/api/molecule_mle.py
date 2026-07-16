"""Computation layer for molecule-wise MLE analysis.

Runs the Qt-free core (:func:`..core.molecule_mle.fit_molecules_from_files`)
in-process for each CLSM TTTR file, writes a per-file molecule-data TSV next to
each file, and merges them into a joint TSV.  No subprocess, no Qt — safe to
call from the CLI, the RPC backend, or headless tests.
"""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.molecule_mle import fit_molecules_from_files

if TYPE_CHECKING:
    from .models import MoleculeMleRequest, MoleculeMleResult

logger = logging.getLogger(__name__)


def analyze_request(request: MoleculeMleRequest) -> MoleculeMleResult:
    """Run molecule-wise MLE analysis for every file in *request*.

    Parameters
    ----------
    request : MoleculeMleRequest
        Files, IRF, output directory and analysis settings.

    Returns
    -------
    MoleculeMleResult
        Per-file TSV paths, the merged joint TSV, molecule count and warnings.
    """
    import pandas as pd

    from .models import MoleculeMleResult

    output_paths: list[str] = []
    processed: list[str] = []
    warnings: list[str] = []
    frames: list[pd.DataFrame] = []

    for file_str in request.files:
        ptu_path = Path(file_str)
        try:
            # Each file gets a fresh settings copy so the IRF (built from the
            # first run) is not carried across files with different windows.
            settings = dataclasses.replace(request.settings)
            result = fit_molecules_from_files(
                str(ptu_path),
                request.irf_file,
                settings,
                shift_sp=request.shift_sp,
                shift_ss=request.shift_ss,
                irf_threshold_fraction=request.irf_threshold_fraction,
            )
        except Exception as exc:  # noqa: BLE001 - reported per file, never fatal
            logger.debug("molecule MLE failed for %s", ptu_path, exc_info=True)
            warnings.append(f"{ptu_path.name}: {exc}")
            continue

        df = result.dataframe
        if df.empty:
            warnings.append(f"{ptu_path.name}: no molecules segmented")
            continue

        df = df.copy()
        df.insert(0, "source_ptu", str(ptu_path))
        out_dir = ptu_path.parent / f"{ptu_path.stem}_analysis"
        out_dir.mkdir(parents=True, exist_ok=True)
        tsv = out_dir / "molecule_data.tsv"
        df.to_csv(tsv, sep="\t", index=False)
        output_paths.append(str(tsv))
        processed.append(file_str)
        frames.append(df)

    joint_tsv = ""
    n_total = 0
    if frames:
        combined = pd.concat(frames, ignore_index=True)
        n_total = int(len(combined))
        out_dir = Path(request.output_dir) if request.output_dir else Path(request.files[0]).parent
        out_dir.mkdir(parents=True, exist_ok=True)
        joint_path = out_dir / "joint_output.tsv"
        combined.to_csv(joint_path, sep="\t", index=False)
        joint_tsv = str(joint_path)

    return MoleculeMleResult(
        processed_files=processed,
        output_paths=output_paths,
        joint_tsv=joint_tsv,
        n_molecules=n_total,
        warnings=warnings,
    )
