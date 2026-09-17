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

from chisurf.core.fluorescence.anisotropy.decay import anisotropy_rt
from chisurf.core.fluorescence.decay import (
    synthetic_aniso_decay,
    synthetic_component_decay,
    synthetic_decay,
)


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


def compute_aniso_decay(
    *,
    n_bins: int,
    lifetimes: Any,
    amplitudes: Any | None = None,
    rotation_rows: Any | None = None,
    g_factor: float = 1.0,
    l1: float = 0.0,
    l2: float = 0.0,
    bin_width: float = 1.0,
    start_bin: int = 0,
    irf: Any | None = None,
    normalize: bool = True,
    photon_count: float | None = None,
    seed: int | None = None,
) -> dict:
    """Generate a polarized VV/VH channel pair plus the anisotropy decay r(t).

    Delegates to the canonical
    :func:`chisurf.core.fluorescence.decay.synthetic_aniso_decay` (lifetime
    spectrum, IRF convolution, per-channel Poisson shot noise with a shared
    photon budget) and evaluates the ideal anisotropy r(t) on the returned
    time axis from ``rotation_rows`` (``[{"b": ..., "rho": ...}, ...]``, the
    rows of the GUI rotation table).

    Returns ``{"x": [...], "vv": [...], "vh": [...], "r": [...], "n_bins": int,
    "bin_width": float}`` — the two polarized channels and the ideal anisotropy,
    all on the same micro-time axis.
    """
    rotation = _rotation_spectrum_from_rows(rotation_rows)
    vv, vh = synthetic_aniso_decay(
        int(n_bins),
        lifetimes,
        amplitudes=amplitudes,
        anisotropy_spectrum=rotation,
        g_factor=float(g_factor),
        l1=float(l1),
        l2=float(l2),
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
        "vv": np.asarray(vv, dtype=float).tolist(),
        "vh": np.asarray(vh, dtype=float).tolist(),
        "r": anisotropy_rt(x, rotation).tolist(),
        "n_bins": int(n_bins),
        "bin_width": float(bin_width),
    }


def compute_rt(
    *,
    n_bins: int,
    bin_width: float = 1.0,
    start_bin: int = 0,
    rotation_rows: Any | None = None,
) -> dict:
    """Ideal anisotropy r(t) from rotation rows, on the decay time axis.

    The VM-mode companion to :func:`compute_aniso_decay`: the magic-angle decay
    itself carries no anisotropy, but the sample's r(t) is still defined, and
    the plot shows it alongside the decay.
    """
    rotation = _rotation_spectrum_from_rows(rotation_rows)
    x = np.arange(int(n_bins), dtype=float) * float(bin_width)
    return {"x": x.tolist(), "r": anisotropy_rt(x, rotation).tolist()}


def _rotation_spectrum_from_rows(rotation_rows: Any | None) -> np.ndarray:
    """Flatten ``[{"b": ..., "rho": ...}, ...]`` rows into an interleaved spectrum."""
    rows = list(rotation_rows or [])
    rotation = np.empty(2 * len(rows), dtype=float)
    for i, row in enumerate(rows):
        rotation[2 * i] = float(row.get("b", 0.0))
        rotation[2 * i + 1] = float(row.get("rho", 1.0))
    return rotation


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
