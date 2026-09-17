"""Qt-free compute for the N&B imaging plugin (delegates to the shared core)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from chisurf.core.fluorescence.imaging import (
    add_maps_to_hdf5,
    build_clsm,
    nb_pipeline,
)


def compute_nb(
    filename: str, channels=(0,), params: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Compute per-pixel N&B maps from a TTTR imaging file.

    Parameters
    ----------
    filename : str
        Path to a TTTR imaging file (PTU/HT3/...); CLSM markers are auto-detected.
    channels : sequence of int
        Detector channel(s) to include.
    params : mapping, optional
        N&B settings with the keys of
        :data:`chisurf.core.fluorescence.imaging.NB_PIPELINE_DEFAULTS` (stack
        corrections, detrending, dead time, analog gain/offset, γ, smoothing).

    Returns
    -------
    dict
        ``{"maps": {mean, variance, B, N, epsilon, n, intensity}, "shape": (ny, nx)}``.
    """
    import tttrlib

    tttr = tttrlib.TTTR(filename)
    clsm = build_clsm(tttr, channels=tuple(channels))
    intensity = np.asarray(clsm.get_intensity(), dtype=float)
    maps = nb_pipeline(intensity, params)
    maps["intensity"] = intensity.sum(axis=0) if intensity.ndim == 3 else intensity
    return {"maps": maps, "shape": maps["N"].shape}


def add_nb_to_hdf5(maps: dict[str, np.ndarray], path: str) -> list[str]:
    """Add the N / B / ε / n fields to a standard imaging HDF5 in place.

    Merges the per-pixel N&B columns into the ``results`` table of an existing
    imaging HDF5 (e.g. a pixel-wise-MLE lifetime map), or creates the file if it
    does not yet exist. Returns the added column names.
    """
    keep = {k: maps[k] for k in ("N", "B", "epsilon", "n") if k in maps}
    return add_maps_to_hdf5(path, keep)
