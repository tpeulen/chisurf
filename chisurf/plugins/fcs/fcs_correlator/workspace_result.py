"""The correlation the correlator computed goes back into the workspace, ready to fit.

A correlation that only lives in the tool's plot cannot be fitted without the user saving a file
and opening it again. After a correlation the chunks' curves are averaged (their standard error
is the curve's uncertainty, which the fit uses as weights), written as a Kristine ``.cor`` file
beside the source's analysis data, read back with ChiSurf's own FCS reader -- so the dataset
carries the FCS experiment and its models -- and added to the Datasets workspace as a child of
the photon stream it was computed from.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np

_log = logging.getLogger(__name__)

__all__ = ["averaged", "register_correlation"]

#: The FCS reader that reads what :func:`register_correlation` writes.
KRISTINE_READER = "Seidel Kristine"


def averaged(correlations: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """The chunks' mean curve: lag time (ms), G(tau) (baseline 1) and its standard error.

    One chunk has no spread to measure: its error is the Koppel-free floor of a curve's own
    scatter (the RMS of successive differences), so the fit still has finite weights.
    """
    curves = [c for c in correlations if len(c.get("x", ())) and len(c.get("y", ()))]
    if not curves:
        return None
    n = min(len(c["x"]) for c in curves)
    x = np.asarray(curves[0]["x"][:n], dtype=float)
    ys = np.asarray([np.asarray(c["y"][:n], dtype=float) for c in curves])
    y = ys.mean(axis=0)
    if len(curves) > 1:
        ey = ys.std(axis=0, ddof=1) / np.sqrt(len(curves))
    else:
        scatter = np.abs(np.diff(y, prepend=y[0]))
        ey = np.full_like(y, max(float(np.sqrt(np.mean(scatter**2))), 1e-6))
    ey = np.where(np.isfinite(ey) & (ey > 0), ey, np.nanmax(ey[np.isfinite(ey)], initial=1e-3))
    keep = (x > 0) & np.isfinite(y)
    return x[keep], y[keep], np.maximum(ey[keep], 1e-9)


def _fcs_reader():
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    ensure_experiments_registered()
    import chisurf

    experiment = chisurf.cs.experiment.get("FCS") if hasattr(chisurf.cs, "experiment") else None
    if experiment is None:
        from chisurf.core.experiments import types

        experiment = types.get("fcs")
    for reader in getattr(experiment, "readers", []) or []:
        if getattr(reader, "name", "") == KRISTINE_READER:
            return reader
    return None


def register_correlation(
    correlations: list[dict],
    *,
    source_uid: str = "",
    source_name: str = "",
    acquisition_s: float = 0.0,
    count_rate_khz: float = 0.0,
    out_dir: str | Path | None = None,
):
    """Average *correlations*, store them as a ``.cor`` file and add them to the workspace.

    Parameters
    ----------
    correlations : list of dict
        The correlator's curves (``x`` in ms, ``y`` = G(tau) with baseline 1).
    source_uid : str
        The photon dataset they were computed from: the curve becomes its child.
    source_name : str
        Its name, for the curve's name.
    acquisition_s, count_rate_khz : float
        Written into the file's metadata column.
    out_dir : str or Path, optional
        Where the file goes; the source's analysis folder by default.

    Returns
    -------
    The added dataset, or ``None`` when there was nothing to add or no workspace.
    """
    curve = averaged(correlations)
    if curve is None:
        return None
    x, y, ey = curve
    if out_dir is None:
        from chisurf.core.project.analysis import container_dir

        out_dir = container_dir(source_uid)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", Path(source_name).stem or "correlation")
    path = out / f"{stem}_correlation.cor"
    from chisurf.core.fio.fluorescence.fcs.kristine import write_kristine

    write_kristine(
        filename=str(path),
        correlation_amplitude=y,
        correlation_time=x,
        mean_countrate=float(count_rate_khz),
        acquisition_time=float(acquisition_s),
        correlation_amplitude_uncertainty=ey,
        verbose=False,
    )
    reader = _fcs_reader()
    if reader is None:
        _log.warning("no FCS reader: the correlation stays in %s", path)
        return None
    group = reader.read(filename=str(path))
    dataset = getattr(group, "current_dataset", None) or group
    dataset.data_reader = reader
    from chisurf.core.plugin.workspace_input import register_result

    name = f"FCS · {Path(source_name).stem}" if source_name else "FCS correlation"
    return register_result(dataset, result_of=source_uid, name=name)
