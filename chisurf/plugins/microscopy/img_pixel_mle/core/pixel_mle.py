"""Pixel-wise FLIM maximum-likelihood lifetime fitting (Qt-free).

Reads a confocal TTTR image (`tttrlib.CLSMImage`), builds a per-pixel
polarisation-resolved micro-time histogram in the "Jordi" layout, and fits a
single fluorescence lifetime + anisotropy per pixel by Poisson maximum
likelihood through the shared :class:`chisurf.core.fluorescence.mle.Fit2x`
harness (tttrlib `Fit23`, the Maus-2001 ``2I*`` estimator).

This module contains no Qt: it is the single computational core shared by the
`img_pixel_mle` GUI wizard, its RPC backend service, and its CLI, and it is
directly testable headlessly from a FLIM TTTR file.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd

from chisurf.core.fluorescence.mle import Fit2x, Fit2xModel, Fit2xSettings, assemble_jordi

#: Callback signature ``(frame, n_frames, line, n_lines)`` for progress reporting.
ProgressCallback = Callable[[int, int, int, int], None]


@dataclasses.dataclass
class PixelMleSettings:
    """Settings for a pixel-wise FLIM maximum-likelihood fit.

    Parameters
    ----------
    channels_parallel, channels_perpendicular : sequence of int
        TTTR routing channels forming the parallel (VV) and perpendicular (VH)
        detection channels of the confocal image.
    irf : numpy.ndarray
        Instrument-response histogram in Jordi layout, length ``2 * window``
        where ``window = micro_time_stop - micro_time_start``.
    period : float
        Excitation period of the light source (nanoseconds).
    dt : float, optional
        Width of one (binned) micro-time channel in nanoseconds.  When omitted
        it is derived from the TTTR header as
        ``micro_time_resolution * 1e9 * binning_factor``.
    background : numpy.ndarray, optional
        Background histogram in Jordi layout (same length as ``irf``).
    binning_factor : int, optional
        Integer down-binning applied to the micro-time axis before fitting.
    micro_time_start, micro_time_stop : int, optional
        Fit window on the (binned) micro-time axis.  ``micro_time_stop=None``
        uses the full binned range.
    min_photons : int, optional
        Pixels with fewer than this many photons (parallel + perpendicular in
        the fit window) are not fitted and yield NaN parameters.
    stack_frames : bool, optional
        Sum all frames into one before fitting.
    tau, gamma, r0, rho : float
        Initial values for the ``Fit23`` parameters.
    fix_tau, fix_gamma, fix_r0, fix_rho : bool
        Whether each parameter is held fixed during optimisation.
    g_factor, l1, l2 : float
        Polarisation corrections passed to the estimator.
    convolution_stop : int, optional
        Last micro-time channel of the IRF convolution.
    p2s_twoIstar : bool, optional
        Optimise ``P + 2S`` instead of ``P`` and ``S`` individually.
    soft_bifl_scatter : bool, optional
        Reduce ``Istar`` by the background contribution.
    """

    channels_parallel: Sequence[int]
    channels_perpendicular: Sequence[int]
    irf: np.ndarray
    period: float
    dt: float | None = None
    background: np.ndarray | None = None
    binning_factor: int = 1
    micro_time_start: int = 0
    micro_time_stop: int | None = None
    min_photons: int = 20
    stack_frames: bool = False
    tau: float = 4.0
    gamma: float = 0.0
    r0: float = 0.38
    rho: float = 1.0
    fix_tau: bool = False
    fix_gamma: bool = True
    fix_r0: bool = True
    fix_rho: bool = True
    g_factor: float = 1.0
    l1: float = 0.0
    l2: float = 0.0
    convolution_stop: int | None = None
    p2s_twoIstar: bool = False
    soft_bifl_scatter: bool = False


@dataclasses.dataclass
class PixelMleResult:
    """Result of a pixel-wise FLIM maximum-likelihood fit.

    Attributes
    ----------
    dataframe : pandas.DataFrame
        One row per fitted (or skipped) pixel, with coordinates and fit
        parameters (`tau`, `gamma`, `r0`, `rho`, `2I*`, ...).  This is the
        per-pixel table consumed by the imaging result maps / exporters.
    tau, rho : numpy.ndarray
        Lifetime and rotational-correlation-time maps of shape
        ``(n_frames, n_lines, n_pixels)`` (float32; 0 where unfitted).
    n_pixels_fit : int
        Number of pixels that passed the ``min_photons`` threshold.
    """

    dataframe: pd.DataFrame
    tau: np.ndarray
    rho: np.ndarray
    n_pixels_fit: int


def _initial_and_fixed(s: PixelMleSettings) -> tuple[np.ndarray, np.ndarray]:
    x0 = np.array([s.tau, s.gamma, s.r0, s.rho], dtype=np.float64)
    fixed = np.array(
        [int(s.fix_tau), int(s.fix_gamma), int(s.fix_r0), int(s.fix_rho)],
        dtype=np.int16,
    )
    return x0, fixed


def fit_pixel_lifetimes(
    tttr: Any,
    settings: PixelMleSettings,
    progress: ProgressCallback | None = None,
) -> PixelMleResult:
    """Fit a single lifetime + anisotropy per pixel of a confocal TTTR image.

    Parameters
    ----------
    tttr : tttrlib.TTTR
        The photon stream of one confocal FLIM measurement.
    settings : PixelMleSettings
        Channel definition, fit window, IRF/background and estimator options.
    progress : callable, optional
        Called as ``progress(frame, n_frames, line, n_lines)`` after each line.

    Returns
    -------
    PixelMleResult
        Per-pixel table plus ``tau``/``rho`` maps.
    """
    import tttrlib

    binning = max(1, int(settings.binning_factor))
    ch_p = list(settings.channels_parallel)
    ch_s = list(settings.channels_perpendicular)

    n_channels = tttr.header.number_of_micro_time_channels // binning
    start = int(settings.micro_time_start)
    stop = int(settings.micro_time_stop) if settings.micro_time_stop is not None else n_channels
    window = stop - start
    if window <= 0:
        raise ValueError(f"empty micro-time window: start={start}, stop={stop}")

    irf = np.ascontiguousarray(settings.irf, dtype=np.float64)
    if irf.size != 2 * window:
        raise ValueError(
            f"irf length {irf.size} does not match 2*window (2*{window}={2 * window})"
        )

    dt = settings.dt
    if dt is None:
        dt = tttr.header.micro_time_resolution * 1e9 * binning

    fit2x_settings = Fit2xSettings(
        dt=float(dt),
        period=float(settings.period),
        irf=irf,
        background=settings.background,
        g_factor=settings.g_factor,
        l1=settings.l1,
        l2=settings.l2,
        convolution_stop=settings.convolution_stop,
        p2s_twoIstar=bool(settings.p2s_twoIstar),
        soft_bifl_scatter=bool(settings.soft_bifl_scatter),
    )
    fitter = Fit2x(fit2x_settings, model=Fit2xModel.FIT23)
    x0, fixed = _initial_and_fixed(settings)

    clsm_p = tttrlib.CLSMImage(tttr, channels=ch_p, fill=True)
    clsm_s = tttrlib.CLSMImage(tttr, channels=ch_s, fill=True)
    if settings.stack_frames:
        clsm_p.stack_frames()
        clsm_s.stack_frames()

    micro_times = tttr.micro_times // binning
    n_frames, n_lines, n_pixel = clsm_p.shape
    tau_map = np.zeros((n_frames, n_lines, n_pixel), dtype=np.float32)
    rho_map = np.zeros((n_frames, n_lines, n_pixel), dtype=np.float32)

    empty = np.zeros(window, dtype=np.int64)
    rows: list[dict] = []
    n_fit = 0

    for i in range(n_frames):
        for j in range(n_lines):
            for k in range(n_pixel):
                idx_p = clsm_p[i][j][k].tttr_indices
                idx_s = clsm_s[i][j][k].tttr_indices
                n_p = len(idx_p)
                n_s = len(idx_s)

                if n_p + n_s < settings.min_photons:
                    row = _blank_row(i, j, k, n_pixel, n_frames, settings)
                    rows.append(row)
                    continue

                if n_p > 0 and start < n_channels:
                    hist_p = np.bincount(micro_times[idx_p], minlength=n_channels)[start:stop]
                else:
                    hist_p = empty.copy()
                if n_s > 0 and start < n_channels:
                    hist_s = np.bincount(micro_times[idx_s], minlength=n_channels)[start:stop]
                else:
                    hist_s = empty.copy()

                fit_window_photons = int(hist_p.sum() + hist_s.sum())
                data = assemble_jordi(hist_p, hist_s)
                res = fitter.fit(data, initial_values=x0, fixed=fixed)

                tau_map[i, j, k] = res.x[0]
                rho_map[i, j, k] = res.x[3]
                n_fit += 1

                row = {
                    "Y pixel": j,
                    "X pixel": k,
                    "Pixel Number": j * n_pixel + k,
                    "Number of Photons (fit window)": fit_window_photons,
                    "tau": res.x[0],
                    "gamma": res.x[1],
                    "r0": res.x[2],
                    "rho": res.x[3],
                    "BIFL scatter fit?": int(settings.soft_bifl_scatter),
                    "2I*: P+2S?": int(settings.p2s_twoIstar),
                    "rS": np.nan,
                    "rE": np.nan,
                    "2I*": res.twoIstar,
                }
                if n_frames > 1:
                    row["Z pixel"] = i
                rows.append(row)

            if progress is not None:
                progress(i, n_frames, j, n_lines)

    dataframe = pd.DataFrame(rows)
    return PixelMleResult(
        dataframe=dataframe,
        tau=tau_map,
        rho=rho_map,
        n_pixels_fit=n_fit,
    )


def _blank_row(i, j, k, n_pixel, n_frames, settings) -> dict:
    row = {
        "Y pixel": j,
        "X pixel": k,
        "Pixel Number": j * n_pixel + k,
        "Number of Photons (fit window)": 0,
        "tau": np.nan,
        "gamma": np.nan,
        "r0": np.nan,
        "rho": np.nan,
        "BIFL scatter fit?": 0,
        "2I*: P+2S?": 0,
        "rS": np.nan,
        "rE": np.nan,
        "2I*": np.nan,
    }
    if n_frames > 1:
        row["Z pixel"] = i
    return row


def fit_pixel_lifetimes_from_file(
    path: str,
    settings: PixelMleSettings,
    progress: ProgressCallback | None = None,
) -> PixelMleResult:
    """Load a TTTR file and run :func:`fit_pixel_lifetimes` on it.

    Parameters
    ----------
    path : str
        Path to a confocal TTTR file (``.ptu``/``.ht3``/...).
    settings : PixelMleSettings
        Fit settings (see :class:`PixelMleSettings`).
    progress : callable, optional
        Progress callback forwarded to :func:`fit_pixel_lifetimes`.

    Returns
    -------
    PixelMleResult
    """
    import tttrlib

    tttr = tttrlib.TTTR(path)
    return fit_pixel_lifetimes(tttr, settings, progress=progress)
