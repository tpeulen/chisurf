"""Headless tests for the Qt-free pixel-wise FLIM MLE core.

Driven by a real confocal FLIM TTTR image from the ``tttr-data`` collection.
Skips cleanly when tttrlib or the external test image is unavailable.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.mle import assemble_vv_vh
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
    irf = assemble_vv_vh(irf1, irf1)
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


@pytest.mark.parametrize(
    "model, init, fixed, extra_cols",
    [
        ("fit24", [2.0, 0.0, 2.0, 0.0, 0.0], [0, 1, 1, 1, 1],
         {"tau1", "gamma", "tau2", "A2", "offset"}),
        ("fit25", [0.5, 1.0, 2.0, 4.0, 0.0], [1, 1, 1, 1, 1],
         {"tau1", "tau2", "tau3", "tau4", "gamma"}),
    ],
)
def test_core_fits_non_fit23_models(model, init, fixed, extra_cols):
    # The pixel core runs every fit2x model through the threaded batch kernel,
    # not just fit23. Each non-fit23 model yields a tau map (x[0]) plus its own
    # registry parameter columns and drops the fit23-only anisotropy columns.
    settings = _settings(fit_model=model, initial_values=init, fixed_flags=fixed)
    result = fit_pixel_lifetimes_from_file(str(_FLIM_PTU), settings)

    df = result.dataframe
    assert len(df) == 50 * 50
    assert result.tau.shape == (1, 50, 50)
    assert {"tau", "2I*"} <= set(df.columns)
    assert extra_cols <= set(df.columns)
    # fit23-only columns are gone for the other models
    assert "rS" not in df.columns and "rE" not in df.columns and "r0" not in df.columns

    assert result.n_pixels_fit > 0
    tau = df[df["Number of Photons (fit window)"] > 0]["tau"].to_numpy()
    assert np.all(np.isfinite(tau))
    assert np.all(tau > 0.0)
    assert int((result.tau > 0).sum()) == result.n_pixels_fit


def test_fast_and_loop_engines_are_equivalent():
    # The vectorised (uint8 get_fluorescence_decay) and exact (bincount) paths
    # must produce identical per-pixel lifetimes.
    r_loop = fit_pixel_lifetimes_from_file(str(_FLIM_PTU), _settings(engine="loop", n_workers=1))
    r_fast = fit_pixel_lifetimes_from_file(str(_FLIM_PTU), _settings(engine="fast", n_workers=1))
    assert r_loop.n_pixels_fit == r_fast.n_pixels_fit
    tl = r_loop.dataframe["tau"].to_numpy()
    tf = r_fast.dataframe["tau"].to_numpy()
    assert np.allclose(tl, tf, equal_nan=True)


def test_threaded_matches_serial():
    # Threaded batch fitting must give bit-identical results to single-thread.
    from chisurf.plugins.microscopy.img_pixel_mle.core import pixel_mle as pm

    orig = pm._MIN_ROWS_FOR_THREADS
    pm._MIN_ROWS_FOR_THREADS = 100  # force the multi-thread path on the small image
    try:
        r_ser = fit_pixel_lifetimes_from_file(str(_FLIM_PTU), _settings(n_workers=1))
        r_par = fit_pixel_lifetimes_from_file(str(_FLIM_PTU), _settings(n_workers=2))
    finally:
        pm._MIN_ROWS_FOR_THREADS = orig
    ts = r_ser.dataframe["tau"].to_numpy()
    tp = r_par.dataframe["tau"].to_numpy()
    assert r_ser.n_pixels_fit == r_par.n_pixels_fit
    assert np.allclose(ts, tp, equal_nan=True)


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
