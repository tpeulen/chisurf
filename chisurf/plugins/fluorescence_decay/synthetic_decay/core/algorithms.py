"""Transport-agnostic core for the synthetic decay generator.

A thin, JSON-serializable wrapper over the single canonical generator
:func:`chisurf.core.fluorescence.decay.synthetic_decay` /
:func:`~chisurf.core.fluorescence.decay.synthetic_component_decay`. No decay
mathematics lives here — the API/CLI/RPC/GUI all funnel through this module,
which funnels through core, so there is exactly one decay generator in ChiSurf.
"""

from __future__ import annotations

import pathlib
from typing import Any

import numpy as np

from chisurf.core.fluorescence.decay import synthetic_component_decay, synthetic_decay


def _load_irf(irf: Any) -> np.ndarray | None:
    """Resolve an IRF given as a vector, a list, or a file path (text / .npy)."""
    if irf is None:
        return None
    if isinstance(irf, (str, pathlib.Path)):
        path = pathlib.Path(irf)
        if not path.is_file():
            raise ValueError(f"IRF file does not exist: {path}")
        if path.suffix.lower() == ".npy":
            return np.load(path).astype(float).ravel()
        return np.loadtxt(path).astype(float).ravel()
    return np.asarray(irf, dtype=float).ravel()


def compute_decay(
    *,
    n_bins: int,
    lifetimes: Any,
    amplitudes: Any | None = None,
    bin_width: float = 1.0,
    start_bin: int = 0,
    irf: Any | None = None,
    normalize: bool = True,
    photon_count: float | None = None,
    seed: int | None = None,
) -> dict:
    """Generate a decay from lifetimes/amplitudes; return a JSON-serializable result.

    Returns ``{"x": [...], "y": [...], "n_bins": int, "bin_width": float}`` where
    ``x`` is the micro-time axis (ns) and ``y`` the (optionally noisy, optionally
    normalized) decay histogram.
    """
    y = synthetic_decay(
        int(n_bins),
        lifetimes,
        amplitudes=amplitudes,
        bin_width=float(bin_width),
        start_bin=int(start_bin),
        irf=_load_irf(irf),
        normalize=bool(normalize),
        photon_count=photon_count,
        seed=seed,
    )
    x = np.arange(int(n_bins), dtype=float) * float(bin_width)
    return {
        "x": x.tolist(),
        "y": np.asarray(y, dtype=float).tolist(),
        "n_bins": int(n_bins),
        "bin_width": float(bin_width),
    }


def compute_component_decay(*, n_bins: int, component: dict, irf: Any | None = None) -> dict:
    """Generate a decay from a component definition (see ``synthetic_component_decay``)."""
    y = synthetic_component_decay(int(n_bins), dict(component), irf=_load_irf(irf))
    bin_width = float(component.get("bin_width", 1.0))
    x = np.arange(int(n_bins), dtype=float) * bin_width
    return {
        "x": x.tolist(),
        "y": np.asarray(y, dtype=float).tolist(),
        "n_bins": int(n_bins),
        "bin_width": bin_width,
    }
