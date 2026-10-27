"""A plane of beads (a 2-D image, a confocal scan) is detected and fitted laterally.

The z-scan of the detection started half a z-ROI into the stack, so a 2-D image -- which
``load_stack`` turns into a one-slice stack -- never had a slice to search and no bead was ever
found in it.
"""

from __future__ import annotations

import math

import numpy as np

from chisurf.plugins.microscopy.psf_determination.api import psf


def _plane(sigma_px: float = 1.3) -> np.ndarray:
    rng = np.random.default_rng(3)
    y, x = np.indices((64, 64))
    image = np.full(y.shape, 2.0)
    for cy, cx in ((16, 18), (40, 44), (20, 46), (46, 16)):
        image += 400.0 * np.exp(-((y - cy) ** 2 + (x - cx) ** 2) / (2 * sigma_px**2))
    return rng.poisson(image).astype(np.float32)[np.newaxis]


def test_a_plane_is_detected_and_fitted_laterally():
    stack = _plane()
    beads = psf.detect_beads(stack, roi_xy=15, roi_z=15, pixels_per_frame=40)
    assert len(beads) == 4, beads
    fits = psf.fit_all_beads(stack, beads, 15, 15, pixel_nm=100.0, z_step_nm=300.0)
    fwhm = [f["fwhm_xy_nm"] for f in fits if not f.get("error")]
    assert len(fwhm) == 4
    assert abs(np.median(fwhm) - 2.355 * 1.3 * 100.0) < 25.0, fwhm
    assert all(math.isnan(f["fwhm_z_nm"]) for f in fits)  # no axial profile in one plane
