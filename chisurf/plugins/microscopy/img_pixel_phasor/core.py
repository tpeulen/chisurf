"""Qt-free compute for the phasor imaging plugin (delegates to the shared core)."""

from __future__ import annotations

from typing import Any

import numpy as np

from chisurf.core.fluorescence.imaging import (
    add_maps_to_hdf5,
    build_clsm,
    phasor_maps,
)

from . import analysis

#: Per-pixel derived-map field names produced by :func:`derived_phasor_maps`.
DERIVED_MAP_FIELDS = ("tau_phi", "tau_m")


def compute_phasor(
    filename: str,
    channels=(0,),
    frequency: float = -1.0,
    irf_filename: str | None = None,
    n_ph_min: int = 2,
) -> dict[str, Any]:
    """Compute per-pixel phasor maps from a TTTR imaging file.

    Parameters
    ----------
    filename : str
        TTTR imaging file (PTU/HT3/...); CLSM markers auto-detected.
    channels : sequence of int
        Detector channel(s).
    frequency : float
        Modulation frequency; ``-1`` auto-derives from the TTTR header.
    irf_filename : str, optional
        Reference/IRF TTTR file for phasor calibration.
    n_ph_min : int
        Minimum photons per pixel.

    Returns
    -------
    dict
        ``{"maps": {g, s, n_photons, intensity}, "shape": (ny, nx)}``.
    """
    import tttrlib

    tttr = tttrlib.TTTR(filename)
    clsm = build_clsm(tttr, channels=tuple(channels))
    irf = tttrlib.TTTR(irf_filename) if irf_filename else None
    maps = phasor_maps(clsm, tttr, frequency=frequency, tttr_irf=irf, n_ph_min=n_ph_min)
    intensity = np.asarray(clsm.get_intensity(), dtype=float)
    maps["intensity"] = intensity.sum(axis=0) if intensity.ndim == 3 else intensity
    return {"maps": maps, "shape": maps["g"].shape}


def derived_phasor_maps(
    maps: dict[str, np.ndarray],
    frequency_mhz: float,
) -> dict[str, np.ndarray]:
    """Return ``maps`` augmented with per-pixel apparent-lifetime maps.

    Adds ``tau_phi`` and ``tau_m`` (phase and modulation apparent lifetimes, ns)
    computed from the ``g`` / ``s`` phasor coordinates at the given modulation
    frequency via :func:`analysis.phasor_to_apparent_lifetime`. The input dict is
    not mutated.

    Parameters
    ----------
    maps : dict of numpy.ndarray
        Per-pixel phasor maps; must contain ``g`` and ``s``.
    frequency_mhz : float
        Modulation frequency in MHz (must be > 0).

    Returns
    -------
    dict of numpy.ndarray
        A new dict: the original maps plus ``tau_phi`` and ``tau_m``.
    """
    if frequency_mhz <= 0.0:
        raise ValueError("frequency_mhz must be > 0 to derive lifetime maps")
    tau_phi, tau_m = analysis.phasor_to_apparent_lifetime(maps["g"], maps["s"], frequency_mhz)
    return {**maps, "tau_phi": tau_phi, "tau_m": tau_m}


def add_phasor_to_hdf5(maps: dict[str, np.ndarray], path: str) -> list[str]:
    """Add the phasor fields to a standard imaging HDF5 in place.

    Merges the per-pixel phasor columns into the ``results`` table of an
    existing imaging HDF5, or creates the file if it does not yet exist. Always
    writes ``g`` / ``s``; also writes the derived ``tau_phi`` / ``tau_m`` maps
    when present. Returns the added column names.
    """
    fields = ("g", "s", *DERIVED_MAP_FIELDS)
    keep = {k: maps[k] for k in fields if k in maps}
    return add_maps_to_hdf5(path, keep)
