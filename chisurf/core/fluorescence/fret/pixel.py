"""Per-pixel (FLIM / imaging) FRET calibration.

Applies the general crosstalk-matrix FRET correction
(:func:`chisurf.core.fluorescence.burst.es.corrected_es_general`) to **images**:
the per-pixel photon-count channels of a FLIM/PIE/ALEX acquisition are corrected
into per-pixel accurate FRET-efficiency maps. The burst cores are already
array-safe (they broadcast over trailing axes), so this module is a thin, ergonomic
imaging wrapper that assembles the intensity tensor, masks photon-starved pixels,
and (optionally) returns integer, Poisson-preserving per-source photon images.

All functions are Qt-free and run head-less.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.burst.es import corrected_es_general
from chisurf.core.fluorescence.crosstalk import invert_mixing, photon_shuffle_unmix

__all__ = ["corrected_es_image", "pixel_source_photons"]


def corrected_es_image(
    intensity, excitation, emission, *, unmix="naive", ridge=0.0, pairs=None, min_counts=0.0
):
    """Per-pixel accurate FRET-efficiency maps from the crosstalk matrices.

    Parameters
    ----------
    intensity : array_like
        ``(n_laser, n_detector, H, W)`` (or any trailing image shape) measured
        photon-count images ``I[laser, detector]`` per pixel.
    excitation : array_like
        ``(n_laser, n_source)`` excitation crosstalk matrix.
    emission : array_like
        ``(n_source, n_detector)`` emission/detection crosstalk matrix.
    unmix : {"naive", "stable"}, optional
        Emission-unmixing method (see ``corrected_es_general``). ``"stable"`` uses
        non-negative least squares per pixel — robust to spectral overlap.
    ridge : float, optional
        Tikhonov damping for the un-mixing.
    pairs : sequence of tuple, optional
        Donor→acceptor index pairs; defaults to all ordered pairs.
    min_counts : float, optional
        Pixels whose total photon count (summed over all lasers/detectors) is below
        this threshold are masked to ``NaN`` in the efficiency maps, so
        photon-starved pixels do not contribute noise.

    Returns
    -------
    dict
        ``{(donor, acceptor): {"E": H×W array, "fc": H×W array}}`` per pair. ``E``
        is ``NaN`` where masked by ``min_counts``.
    """
    intensity = np.asarray(intensity, dtype=float)
    res = corrected_es_general(
        intensity, excitation, emission, unmix=unmix, ridge=ridge, pairs=pairs
    )
    if min_counts and min_counts > 0:
        total = intensity.sum(axis=(0, 1))
        mask = total < float(min_counts)
        for key in res:
            e = np.array(res[key]["E"], dtype=float)
            e[mask] = np.nan
            res[key]["E"] = e
    return res


def pixel_source_photons(counts, emission, *, unmix="shuffle", seed=None):
    """Per-pixel per-source photon images (integer, Poisson-preserving, or NNLS).

    Un-mixes the per-pixel detector photon counts into per-source photon images.

    Parameters
    ----------
    counts : array_like
        ``(n_detector, H, W)`` (or any trailing image shape) per-pixel detector
        photon counts.
    emission : array_like
        ``(n_source, n_detector)`` emission/detection crosstalk matrix.
    unmix : {"shuffle", "stable"}, optional
        ``"shuffle"`` (default) reassigns each photon to a source by a multinomial
        draw, giving **integer**, count-preserving, Poisson-faithful per-source
        images. ``"stable"`` returns the continuous non-negative least-squares
        estimate.
    seed : int, optional
        Seed for the ``"shuffle"`` reassignment.

    Returns
    -------
    numpy.ndarray
        ``(n_source, H, W)`` per-source photon images (integer for ``"shuffle"``).
    """
    counts = np.asarray(counts)
    emission = np.asarray(emission, dtype=float)
    if str(unmix).lower() == "shuffle":
        return photon_shuffle_unmix(np.rint(counts).astype(np.int64), emission, seed=seed)
    return np.clip(invert_mixing(emission, counts.astype(float), nonneg=True), 0.0, None)
