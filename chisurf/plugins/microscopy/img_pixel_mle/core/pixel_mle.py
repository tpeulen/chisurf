"""Pixel-wise FLIM maximum-likelihood lifetime fitting (Qt-free).

Reads a confocal TTTR image (`tttrlib.CLSMImage`), builds a per-pixel
polarisation-resolved micro-time histogram in the "Jordi" layout, and fits a
single fluorescence lifetime + anisotropy per pixel by Poisson maximum
likelihood through the shared :class:`chisurf.core.fluorescence.mle.Fit2x`
harness (tttrlib `Fit23`, the Maus-2001 ``2I*`` estimator).

Two throughput optimisations over the naive per-pixel Python loop:

* **Vectorised extraction** -- ``CLSMImage.get_fluorescence_decay`` builds the
  whole per-pixel micro-time histogram stack in one C++ call, replacing the
  per-pixel Python ``tttr_indices`` + ``np.bincount`` loop.
* **Multiprocessing fits** -- the per-pixel ``Fit23`` calls (the dominant cost)
  are distributed across worker processes over a shared-memory copy of the
  per-pixel histogram matrix. (Threading does not help: the C++ fit is
  correct under threads but does not scale in-process; separate processes do.)

Both are controlled by :class:`PixelMleSettings` (``engine`` and ``n_workers``)
and default to the fast path.  The module contains no Qt: it is the single
computational core shared by the `img_pixel_mle` GUI wizard, its RPC backend
service, and its CLI, and it is directly testable headlessly from a FLIM file.
"""
from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import pandas as pd

from chisurf.core.fluorescence.mle import Fit2x, Fit2xModel, Fit2xSettings
from chisurf.core.fluorescence.mle.parallel import fit_matrix_parallel

logger = logging.getLogger(__name__)

#: Callback signature ``(frame, n_frames, line, n_lines)`` for progress reporting.
ProgressCallback = Callable[[int, int, int, int], None]

#: Minimum number of pixels to fit before multiprocessing is worth its overhead.
_MIN_PIXELS_FOR_MP = 512

_RESULT_COLUMNS = (
    "Y pixel", "X pixel", "Pixel Number", "Number of Photons (fit window)",
    "tau", "gamma", "r0", "rho", "BIFL scatter fit?", "2I*: P+2S?",
    "rS", "rE", "2I*",
)


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
    engine : {"auto", "fast", "loop"}, optional
        Histogram-extraction engine.  ``"fast"`` uses the vectorised
        ``get_fluorescence_decay`` C++ call; ``"loop"`` uses the exact
        per-pixel ``np.bincount`` path (reference / used automatically as a
        fallback when the fast uint8 histograms saturate).  ``"auto"`` picks
        ``"fast"`` and falls back to ``"loop"`` on saturation.
    n_workers : int, optional
        Number of worker processes for the per-pixel fits.  ``None``/``0`` →
        auto (``cpu_count - 1``); ``1`` → serial (no multiprocessing).
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
    engine: str = "auto"
    n_workers: int | None = None


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


def _fit2x_settings_kwargs(s: PixelMleSettings, dt: float) -> dict:
    """Picklable kwargs to reconstruct the :class:`Fit2xSettings` in a worker."""
    return dict(
        dt=float(dt),
        period=float(s.period),
        irf=np.ascontiguousarray(s.irf, dtype=np.float64),
        background=(
            None if s.background is None
            else np.ascontiguousarray(s.background, dtype=np.float64)
        ),
        g_factor=s.g_factor,
        l1=s.l1,
        l2=s.l2,
        convolution_stop=s.convolution_stop,
        p2s_twoIstar=bool(s.p2s_twoIstar),
        soft_bifl_scatter=bool(s.soft_bifl_scatter),
    )


def _initial_and_fixed(s: PixelMleSettings) -> tuple[np.ndarray, np.ndarray]:
    x0 = np.array([s.tau, s.gamma, s.r0, s.rho], dtype=np.float64)
    fixed = np.array(
        [int(s.fix_tau), int(s.fix_gamma), int(s.fix_r0), int(s.fix_rho)],
        dtype=np.int16,
    )
    return x0, fixed


def _extract_jordi_fast(clsm_p, clsm_s, tttr, binning, start, stop):
    """Per-pixel Jordi histograms via the vectorised ``get_fluorescence_decay``.

    Returns ``(jordi, n_frames, n_lines, n_pixel, saturated)`` where ``jordi``
    is an ``(n_pixels, 2*window)`` int64 matrix in (frame, line, pixel) order.
    """
    dec_p = np.asarray(
        clsm_p.get_fluorescence_decay(tttr, micro_time_coarsening=binning,
                                      stack_frames=False)
    )
    dec_s = np.asarray(
        clsm_s.get_fluorescence_decay(tttr, micro_time_coarsening=binning,
                                      stack_frames=False)
    )
    # get_fluorescence_decay returns uint8 counts; detect saturation before cast.
    saturated = bool(dec_p.max() >= 255 or dec_s.max() >= 255)
    n_frames, n_lines, n_pixel, _ = dec_p.shape
    hp = dec_p.reshape(-1, dec_p.shape[-1])[:, start:stop].astype(np.int64)
    hs = dec_s.reshape(-1, dec_s.shape[-1])[:, start:stop].astype(np.int64)
    jordi = np.ascontiguousarray(np.concatenate([hp, hs], axis=1))
    return jordi, n_frames, n_lines, n_pixel, saturated


def _extract_jordi_loop(clsm_p, clsm_s, tttr, binning, start, stop, n_channels):
    """Exact per-pixel Jordi histograms via ``np.bincount`` (reference path)."""
    micro = tttr.micro_times // binning
    n_frames, n_lines, n_pixel = clsm_p.shape
    window = stop - start
    empty = np.zeros(window, dtype=np.int64)
    rows = []
    for i in range(n_frames):
        for j in range(n_lines):
            for k in range(n_pixel):
                idx_p = clsm_p[i][j][k].tttr_indices
                idx_s = clsm_s[i][j][k].tttr_indices
                if len(idx_p) > 0 and start < n_channels:
                    hp = np.bincount(micro[idx_p], minlength=n_channels)[start:stop]
                else:
                    hp = empty
                if len(idx_s) > 0 and start < n_channels:
                    hs = np.bincount(micro[idx_s], minlength=n_channels)[start:stop]
                else:
                    hs = empty
                rows.append(np.concatenate([hp, hs]))
    jordi = np.ascontiguousarray(np.asarray(rows, dtype=np.int64))
    return jordi, n_frames, n_lines, n_pixel


# --- per-pixel fitting: serial + multiprocessing -----------------------------


def _fit_rows_serial(jordi, rows, settings, dt):
    fitter = Fit2x(Fit2xSettings(**_fit2x_settings_kwargs(settings, dt)),
                   model=Fit2xModel.FIT23)
    x0, fixed = _initial_and_fixed(settings)
    out = np.empty((len(rows), 5), dtype=np.float64)
    for m, r in enumerate(rows):
        res = fitter.fit(jordi[r].astype(np.float64), x0, fixed)
        out[m] = (res.x[0], res.x[1], res.x[2], res.x[3], res.twoIstar)
    return out


def _fit_rows_parallel(jordi, rows, settings, dt, n_workers):
    """Fit rows across worker processes; fall back to serial on any failure."""
    x0, fixed = _initial_and_fixed(settings)
    fit_settings = Fit2xSettings(**_fit2x_settings_kwargs(settings, dt))
    try:
        return fit_matrix_parallel(
            jordi, rows, fit_settings, x0, fixed, n_workers, model=Fit2xModel.FIT23
        )
    except Exception:
        logger.exception(
            "img_pixel_mle: parallel fit failed; falling back to serial fitting"
        )
        return _fit_rows_serial(jordi, rows, settings, dt)


def _resolve_workers(n_workers: int | None) -> int:
    if n_workers is None or n_workers <= 0:
        return max(1, (os.cpu_count() or 2) - 1)
    return int(n_workers)


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
        Called as ``progress(frame, n_frames, line, n_lines)`` -- once per
        frame in the fast path (the heavy loop is vectorised / off-process).

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
    stop = min(stop, n_channels)
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

    clsm_p = tttrlib.CLSMImage(tttr, channels=ch_p, fill=True)
    clsm_s = tttrlib.CLSMImage(tttr, channels=ch_s, fill=True)
    if settings.stack_frames:
        clsm_p.stack_frames()
        clsm_s.stack_frames()

    engine = (settings.engine or "auto").lower()
    if engine in ("auto", "fast"):
        jordi, n_frames, n_lines, n_pixel, saturated = _extract_jordi_fast(
            clsm_p, clsm_s, tttr, binning, start, stop
        )
        if saturated and engine == "auto":
            logger.warning(
                "img_pixel_mle: micro-time histograms saturated the fast uint8 "
                "extraction; falling back to the exact bincount engine. Increase "
                "binning or set engine='loop' to silence."
            )
            jordi, n_frames, n_lines, n_pixel = _extract_jordi_loop(
                clsm_p, clsm_s, tttr, binning, start, stop, n_channels
            )
    else:
        jordi, n_frames, n_lines, n_pixel = _extract_jordi_loop(
            clsm_p, clsm_s, tttr, binning, start, stop, n_channels
        )

    totals = jordi.sum(axis=1)
    fit_rows = np.where(totals >= settings.min_photons)[0]

    # Run the fits (serial or across processes).
    n_workers = _resolve_workers(settings.n_workers)
    if len(fit_rows) and n_workers > 1 and len(fit_rows) >= _MIN_PIXELS_FOR_MP:
        params = _fit_rows_parallel(jordi, fit_rows, settings, dt, n_workers)
    elif len(fit_rows):
        params = _fit_rows_serial(jordi, fit_rows, settings, dt)
    else:
        params = np.empty((0, 5), dtype=np.float64)

    # Assemble maps + per-pixel table.
    tau_map = np.zeros((n_frames, n_lines, n_pixel), dtype=np.float32)
    rho_map = np.zeros((n_frames, n_lines, n_pixel), dtype=np.float32)
    flat_tau = tau_map.reshape(-1)
    flat_rho = rho_map.reshape(-1)
    flat_tau[fit_rows] = params[:, 0]
    flat_rho[fit_rows] = params[:, 3]

    coords = np.indices((n_frames, n_lines, n_pixel)).reshape(3, -1)
    frame_idx, line_idx, pix_idx = coords[0], coords[1], coords[2]
    n_pix_total = n_frames * n_lines * n_pixel

    df = pd.DataFrame({
        "Y pixel": line_idx,
        "X pixel": pix_idx,
        "Pixel Number": line_idx * n_pixel + pix_idx,
        "Number of Photons (fit window)": totals.astype(np.int64),
        "tau": np.nan, "gamma": np.nan, "r0": np.nan, "rho": np.nan,
        "BIFL scatter fit?": 0, "2I*: P+2S?": 0,
        "rS": np.nan, "rE": np.nan, "2I*": np.nan,
    })
    if len(fit_rows):
        df.loc[fit_rows, "tau"] = params[:, 0]
        df.loc[fit_rows, "gamma"] = params[:, 1]
        df.loc[fit_rows, "r0"] = params[:, 2]
        df.loc[fit_rows, "rho"] = params[:, 3]
        df.loc[fit_rows, "2I*"] = params[:, 4]
        df.loc[fit_rows, "BIFL scatter fit?"] = int(settings.soft_bifl_scatter)
        df.loc[fit_rows, "2I*: P+2S?"] = int(settings.p2s_twoIstar)
    # Below-threshold pixels report zero photons in the fit window (matches the
    # historical schema, where intensity/count columns come from the Intensity
    # tool rather than the MLE).
    df.loc[totals < settings.min_photons, "Number of Photons (fit window)"] = 0
    if n_frames > 1:
        df["Z pixel"] = frame_idx
    df = df[list(_RESULT_COLUMNS) + (["Z pixel"] if n_frames > 1 else [])]

    if progress is not None:
        for i in range(n_frames):
            progress(i, n_frames, n_lines - 1, n_lines)

    _ = n_pix_total  # documented invariant: len(df) == n_pix_total
    return PixelMleResult(
        dataframe=df.reset_index(drop=True),
        tau=tau_map,
        rho=rho_map,
        n_pixels_fit=int(len(fit_rows)),
    )


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
