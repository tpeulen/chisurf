"""Headless tests for the Qt-free pixel-wise FLIM MLE core.

Driven by a real confocal FLIM TTTR image from the ``tttr-data`` collection.
Skips cleanly when tttrlib or the external test image is unavailable.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.mle import assemble_jordi
from chisurf.plugins.microscopy.img_pixel_mle.core import (
    PixelMleResult,
    PixelMleSettings,
    fit_pixel_lifetimes_from_file,
)

_FLIM_PTU = pathlib.Path(
    "/Users/tpeulen/dev/tttr-data/imaging/pq/Microtime200_HH400/beads.ptu"
)

pytestmark = pytest.mark.skipif(
    not _FLIM_PTU.exists(), reason="tttr-data FLIM image not available"
)

_BINNING = 8


def _settings(**overrides) -> PixelMleSettings:
    n_ch = 2048 // _BINNING
    window = n_ch
    irf1 = np.exp(-0.5 * ((np.arange(window) - 8) / 2.0) ** 2)
    irf1 /= irf1.sum()
    irf = assemble_jordi(irf1, irf1)
    kwargs = dict(
        channels_parallel=[0],
        channels_perpendicular=[1],
        irf=irf,
        period=1000.0 / 26.0,
        binning_factor=_BINNING,
        min_photons=20,
        tau=2.0,
        fix_gamma=True,
        fix_r0=True,
        fix_rho=True,
    )
    kwargs.update(overrides)
    return PixelMleSettings(**kwargs)


def test_core_fits_flim_image_headlessly():
    result = fit_pixel_lifetimes_from_file(str(_FLIM_PTU), _settings())
    assert isinstance(result, PixelMleResult)

    df = result.dataframe
    # One row per pixel of the 50x50 image.
    assert len(df) == 50 * 50
    assert result.tau.shape == (1, 50, 50)

    expected_cols = {
        "Y pixel", "X pixel", "Pixel Number", "Number of Photons (fit window)",
        "tau", "gamma", "r0", "rho", "BIFL scatter fit?", "2I*: P+2S?",
        "rS", "rE", "2I*",
    }
    assert expected_cols.issubset(set(df.columns))

    fitted = df[df["Number of Photons (fit window)"] > 0]
    assert result.n_pixels_fit == len(fitted)
    assert result.n_pixels_fit > 50  # a meaningful number of pixels were fit

    # Fitted lifetimes are finite and physically plausible for the image.
    tau = fitted["tau"].to_numpy()
    assert np.all(np.isfinite(tau))
    assert np.all(tau > 0.0)
    assert 0.1 < np.median(tau) < 30.0
    # tau map is nonzero exactly on the fitted pixels.
    assert int((result.tau > 0).sum()) == result.n_pixels_fit


def test_min_photons_threshold_controls_fit_count():
    few = fit_pixel_lifetimes_from_file(str(_FLIM_PTU), _settings(min_photons=200))
    many = fit_pixel_lifetimes_from_file(str(_FLIM_PTU), _settings(min_photons=20))
    assert few.n_pixels_fit < many.n_pixels_fit


def test_irf_length_mismatch_raises():
    bad = _settings()
    bad.irf = np.zeros(10)  # not 2*window
    with pytest.raises(ValueError):
        fit_pixel_lifetimes_from_file(str(_FLIM_PTU), bad)


def test_backend_analyze_writes_csv(tmp_path):
    from chisurf.plugins.microscopy.img_pixel_mle.backend.services import _handle_analyze

    params = {
        "files": [str(_FLIM_PTU)],
        "irf_file": str(_FLIM_PTU),
        "output_dir": str(tmp_path),
        "settings": {
            "detector_chs_p": [0],
            "detector_chs_s": [1],
            "micro_time_start": 0,
            "micro_time_stop": 2048 // _BINNING,
            "micro_time_binning": _BINNING,
            "min_photons": 20,
            "tau": 2.0,
            "fix_r0": True,
        },
    }
    resp = _handle_analyze(params)
    assert resp.get("ok", resp.get("success", True)) is not False
    payload = resp.get("result", resp.get("data", resp))
    out_paths = payload["output_paths"]
    assert len(out_paths) == 1
    out = pathlib.Path(out_paths[0])
    assert out.exists()
    import pandas as pd

    df = pd.read_csv(out)
    assert "tau" in df.columns
    assert len(df) == 50 * 50
