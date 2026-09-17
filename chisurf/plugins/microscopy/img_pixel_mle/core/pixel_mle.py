"""Pixel-wise FLIM maximum-likelihood lifetime fitting (Qt-free).

Reads a confocal TTTR image (`tttrlib.CLSMImage`), builds a per-pixel
polarisation-resolved micro-time histogram in the "VV/VH" layout, and fits a
single fluorescence lifetime + anisotropy per pixel by Poisson maximum
likelihood through the shared :class:`chisurf.core.fluorescence.mle.Fit2x`
harness (tttrlib `Fit23`, the Maus-2001 ``2I*`` estimator).

Two throughput optimisations over the naive per-pixel Python loop:

* **Vectorised extraction** -- ``CLSMImage.get_fluorescence_decay`` builds the
  whole per-pixel micro-time histogram stack in one C++ call, replacing the
  per-pixel Python ``tttr_indices`` + ``np.bincount`` loop.
* **Threaded batch fits** -- the per-pixel ``Fit23`` calls (the dominant cost)
  are run through tttrlib's batch entry point, which fits a whole chunk of
  pixels in one call with the GIL released, distributed across a thread pool
  (``fluorescence/mle/parallel.py``). No multiprocessing, so no fork/spawn
  fragility and safe inside the Qt GUI.

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

from chisurf.core.datastore import store_from_arrays
from chisurf.core.fluorescence.mle import Fit2xModel, Fit2xSettings
from chisurf.core.fluorescence.mle.fit2x import parameter_names_of
from chisurf.core.fluorescence.mle.parallel import fit_matrix_threaded

logger = logging.getLogger(__name__)

#: Callback signature ``(frame, n_frames, line, n_lines)`` for progress reporting.
ProgressCallback = Callable[[int, int, int, int], None]

#: Minimum number of pixels to fit before spreading across threads is worthwhile.
_MIN_ROWS_FOR_THREADS = 512

#: Loaded once; ``result_columns.yaml`` beside this module is the schema
#: authority for models whose export layout is fixed by history (fit23).
_RESULT_SCHEMAS = None


def result_column_schemas() -> dict:
    """Return the declared per-model result schemas (``result_columns.yaml``).

    Models without an entry take the generic registry route -- their schema
    *is* the tttrlib parameter registry and needs no file. The declared
    ones exist for byte-compatible legacy layouts; the file's own header
    documents the source vocabulary.

    Returns
    -------
    dict
        Model key (``Fit2xModel.name.lower()``) -> ``{"columns": [...]}``.
    """
    global _RESULT_SCHEMAS
    if _RESULT_SCHEMAS is None:
        import pathlib

        import yaml

        path = pathlib.Path(__file__).with_name("result_columns.yaml")
        with open(path, encoding="utf-8") as fh:
            _RESULT_SCHEMAS = yaml.safe_load(fh)
    return _RESULT_SCHEMAS


@dataclasses.dataclass
class PixelMleSettings:
    """Settings for a pixel-wise FLIM maximum-likelihood fit.

    Parameters
    ----------
    channels_parallel, channels_perpendicular : sequence of int
        TTTR routing channels forming the parallel (VV) and perpendicular (VH)
        detection channels of the confocal image.
    irf : numpy.ndarray
        Instrument-response histogram in VV/VH layout, length ``2 * window``
        where ``window = micro_time_stop - micro_time_start``.
    period : float
        Excitation period of the light source (nanoseconds).
    dt : float, optional
        Width of one (binned) micro-time channel in nanoseconds.  When omitted
        it is derived from the TTTR header as
        ``micro_time_resolution * 1e9 * binning_factor``.
    background : numpy.ndarray, optional
        Background histogram in VV/VH layout (same length as ``irf``).
    binning_factor : int, optional
        Integer down-binning applied to the micro-time axis before fitting.
    micro_time_start, micro_time_stop : int, optional
        Fit window on the (binned) micro-time axis.  ``micro_time_stop=None``
        uses the full binned range.
    min_photons : int, optional
        Pixels with fewer than this many photons (parallel + perpendicular in
        the fit window) are not fitted and yield NaN parameters.
    roi : ROI or dict, optional
        Region of the frame to fit — a :class:`chisurf.core.roi.ROI` or its
        serialised form. Pixels outside it are left unfitted, so a per-pixel
        FLIM fit can be confined to one cell instead of paying for the empty
        field around it.
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
    #: Which fit2x estimator to run per pixel (``"fit23"``/``"fit24"``/``"fit25"``).
    fit_model: str = "fit23"
    #: Model-generic start vector / fixed mask, ordered as the estimator's free
    #: parameters (:func:`parameter_names_of`). When ``None`` the fit23 ``tau``/``gamma``/
    #: ``r0``/``rho`` fields below are used (back-compat for fit23 callers).
    initial_values: Sequence[float] | None = None
    fixed_flags: Sequence[int] | None = None
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
    #: Region of the frame to fit — a :class:`chisurf.core.roi.ROI` or its
    #: serialised form (so it survives the trip through RPC). Pixels outside it
    #: are left unfitted, exactly as if they were below ``min_photons``.
    roi: Any = None

    def analysis_roi(self):
        """Return :attr:`roi` as a :class:`chisurf.core.roi.ROI`, or ``None``.

        Returns
        -------
        chisurf.core.roi.ROI or None
            The region, rebuilt from its serialised form when the settings
            arrived over RPC.
        """
        from chisurf.core.roi import as_roi

        return as_roi(self.roi)


@dataclasses.dataclass
class PixelMleResult:
    """Result of a pixel-wise FLIM maximum-likelihood fit.

    Attributes
    ----------
    dataframe : tttrlib.DataStore
        One row per fitted (or skipped) pixel, with coordinates and fit
        parameters (`tau`, `gamma`, `r0`, `rho`, `2I*`, ...).  This is the
        per-pixel table consumed by the imaging result maps / exporters.
    tau, rho : numpy.ndarray
        Lifetime and rotational-correlation-time maps of shape
        ``(n_frames, n_lines, n_pixels)`` (float32; 0 where unfitted).
    n_pixels_fit : int
        Number of pixels that passed the ``min_photons`` threshold.
    """

    dataframe: Any
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
            None if s.background is None else np.ascontiguousarray(s.background, dtype=np.float64)
        ),
        g_factor=s.g_factor,
        l1=s.l1,
        l2=s.l2,
        convolution_stop=s.convolution_stop,
        p2s_twoIstar=bool(s.p2s_twoIstar),
        soft_bifl_scatter=bool(s.soft_bifl_scatter),
    )


def _initial_and_fixed(s: PixelMleSettings) -> tuple[np.ndarray, np.ndarray]:
    """Start vector + fixed mask for the selected model.

    Uses the model-generic ``initial_values``/``fixed_flags`` when given;
    otherwise falls back to the fit23 ``tau``/``gamma``/``r0``/``rho`` fields so
    existing fit23 callers keep working unchanged.
    """
    names = parameter_names_of(Fit2xModel(s.fit_model))
    if s.initial_values is not None:
        x0 = np.asarray(s.initial_values, dtype=np.float64)
        fixed = (
            np.zeros(x0.size, dtype=np.int16)
            if s.fixed_flags is None
            else np.asarray(s.fixed_flags, dtype=np.int16)
        )
    else:
        x0 = np.array([s.tau, s.gamma, s.r0, s.rho], dtype=np.float64)
        fixed = np.array(
            [int(s.fix_tau), int(s.fix_gamma), int(s.fix_r0), int(s.fix_rho)],
            dtype=np.int16,
        )
    if x0.size != len(names):
        raise ValueError(
            f"{s.fit_model} expects {len(names)} initial values {names}, got {x0.size}"
        )
    return x0, fixed


def _extract_vv_vh_fast(clsm_p, clsm_s, tttr, binning, start, stop):
    """Per-pixel VV/VH histograms via the vectorised ``get_fluorescence_decay``.

    Returns ``(vv_vh, n_frames, n_lines, n_pixel, saturated)`` where ``vv_vh``
    is an ``(n_pixels, 2*window)`` int64 matrix in (frame, line, pixel) order.
    """
    dec_p = np.asarray(
        clsm_p.get_fluorescence_decay(tttr, micro_time_coarsening=binning, stack_frames=False)
    )
    dec_s = np.asarray(
        clsm_s.get_fluorescence_decay(tttr, micro_time_coarsening=binning, stack_frames=False)
    )
    # get_fluorescence_decay returns uint8 counts; detect saturation before cast.
    saturated = bool(dec_p.max() >= 255 or dec_s.max() >= 255)
    n_frames, n_lines, n_pixel, _ = dec_p.shape
    hp = dec_p.reshape(-1, dec_p.shape[-1])[:, start:stop].astype(np.int64)
    hs = dec_s.reshape(-1, dec_s.shape[-1])[:, start:stop].astype(np.int64)
    vv_vh = np.ascontiguousarray(np.concatenate([hp, hs], axis=1))
    return vv_vh, n_frames, n_lines, n_pixel, saturated


def _extract_vv_vh_loop(clsm_p, clsm_s, tttr, binning, start, stop, n_channels):
    """Exact per-pixel VV/VH histograms via ``np.bincount`` (reference path)."""
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
    vv_vh = np.ascontiguousarray(np.asarray(rows, dtype=np.int64))
    return vv_vh, n_frames, n_lines, n_pixel


# --- per-pixel fitting: threaded batch ---------------------------------------


def _fit_rows(vv_vh, rows, settings, dt, n_workers):
    """Fit the selected pixel rows using the threaded batch fit2x path."""
    x0, fixed = _initial_and_fixed(settings)
    fit_settings = Fit2xSettings(**_fit2x_settings_kwargs(settings, dt))
    return fit_matrix_threaded(
        vv_vh,
        rows,
        fit_settings,
        x0,
        fixed,
        n_workers,
        model=Fit2xModel(settings.fit_model),
    )


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
        raise ValueError(f"irf length {irf.size} does not match 2*window (2*{window}={2 * window})")

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
        vv_vh, n_frames, n_lines, n_pixel, saturated = _extract_vv_vh_fast(
            clsm_p, clsm_s, tttr, binning, start, stop
        )
        if saturated and engine == "auto":
            logger.warning(
                "img_pixel_mle: micro-time histograms saturated the fast uint8 "
                "extraction; falling back to the exact bincount engine. Increase "
                "binning or set engine='loop' to silence."
            )
            vv_vh, n_frames, n_lines, n_pixel = _extract_vv_vh_loop(
                clsm_p, clsm_s, tttr, binning, start, stop, n_channels
            )
    else:
        vv_vh, n_frames, n_lines, n_pixel = _extract_vv_vh_loop(
            clsm_p, clsm_s, tttr, binning, start, stop, n_channels
        )

    totals = vv_vh.sum(axis=1)
    fit_rows = np.where(totals >= settings.min_photons)[0]

    roi = settings.analysis_roi()
    if roi is not None:
        # Restrict to a region — one cell, one illuminated patch. Photon counts
        # act as the intensity image so an intensity-dependent region (a
        # threshold) works here too. The mask is per-pixel, so it repeats across
        # frames, which is how the rows are laid out.
        photons = totals.reshape(n_frames, n_lines, n_pixel).sum(axis=0)
        inside = roi.to_mask((n_lines, n_pixel), image=photons).ravel()
        fit_rows = fit_rows[np.tile(inside, n_frames)[fit_rows]]

    # Run the fits (serial or across processes).
    model = Fit2xModel(settings.fit_model)
    names = parameter_names_of(model)
    n_workers = _resolve_workers(settings.n_workers)
    if len(fit_rows) < _MIN_ROWS_FOR_THREADS:
        n_workers = 1  # threading overhead not worth it for a handful of pixels
    if len(fit_rows):
        params = _fit_rows(vv_vh, fit_rows, settings, dt, n_workers)
    else:
        params = np.empty((0, len(names) + 1), dtype=np.float64)

    # Assemble maps + per-pixel table. ``x[0]`` is the primary lifetime for every
    # model (fit23 tau, fit24 tau1, fit25 the selected tau) → the tau map; the
    # rho map is fit23-only (its ``x[3]`` is the rotational time).
    tau_map = np.zeros((n_frames, n_lines, n_pixel), dtype=np.float32)
    rho_map = np.zeros((n_frames, n_lines, n_pixel), dtype=np.float32)
    flat_tau = tau_map.reshape(-1)
    flat_rho = rho_map.reshape(-1)
    if len(fit_rows):
        flat_tau[fit_rows] = params[:, 0]
        if model is Fit2xModel.FIT23:
            flat_rho[fit_rows] = params[:, 3]

    coords = np.indices((n_frames, n_lines, n_pixel)).reshape(3, -1)
    frame_idx, line_idx, pix_idx = coords[0], coords[1], coords[2]
    n_pix_total = n_frames * n_lines * n_pixel

    base = {
        "Y pixel": line_idx,
        "X pixel": pix_idx,
        "Pixel Number": line_idx * n_pixel + pix_idx,
        "Number of Photons (fit window)": totals.astype(np.int64),
    }

    def _column(fill=np.nan, values=None, dtype=float):
        """A per-pixel column: *fill* everywhere, *values* on the fitted rows.

        Replaces a frame of NaNs written into with ``.loc[fit_rows, name]`` --
        same result, but the column is built once rather than allocated and then
        scattered into.
        """
        out = np.full(n_pix_total, fill, dtype=dtype)
        if values is not None and len(fit_rows):
            out[fit_rows] = values
        return out

    schema = result_column_schemas().get(model.name.lower())
    if schema is not None:
        # A declared legacy layout (fit23: byte-for-byte with the
        # historical export). The schema file decides names, order and
        # sources; this walk only knows the source vocabulary.
        columns = dict(base)
        result_cols = []
        for entry in schema["columns"]:
            name_, source = entry["column"], entry["source"]
            result_cols.append(name_)
            if source == "base":
                if name_ not in base:
                    raise ValueError(f"result_columns.yaml: no base column {name_!r}")
            elif source == "blank":
                columns[name_] = _column()
            elif source.startswith("parameter:"):
                j = int(source.split(":", 1)[1])
                columns[name_] = _column(values=params[:, j] if len(fit_rows) else None)
            elif source.startswith("flag:"):
                flag = bool(getattr(settings, source.split(":", 1)[1]))
                columns[name_] = _column(0, np.full(len(fit_rows), int(flag)), dtype=np.int64)
            else:
                raise ValueError(f"result_columns.yaml: unknown source {source!r}")
    else:
        # Generic schema: ``tau`` (primary lifetime) + one column per free
        # parameter named by the registry, then ``2I*``.
        columns = {**base, "tau": _column(values=params[:, 0] if len(fit_rows) else None)}
        for j, nm in enumerate(names):
            columns[nm] = _column(values=params[:, j] if len(fit_rows) else None)
        columns["2I*"] = _column(values=params[:, -1] if len(fit_rows) else None)
        result_cols = [
            "Y pixel",
            "X pixel",
            "Pixel Number",
            "Number of Photons (fit window)",
            "tau",
            *names,
            "2I*",
        ]
    # Below-threshold pixels report zero photons in the fit window (matches the
    # historical schema, where intensity/count columns come from the Intensity
    # tool rather than the MLE).
    counts = np.array(columns["Number of Photons (fit window)"])
    counts[totals < settings.min_photons] = 0
    columns["Number of Photons (fit window)"] = counts
    if n_frames > 1:
        columns["Z pixel"] = frame_idx
        result_cols = result_cols + ["Z pixel"]
    df = store_from_arrays({name: columns[name] for name in result_cols})

    if progress is not None:
        for i in range(n_frames):
            progress(i, n_frames, n_lines - 1, n_lines)

    # documented invariant: row_count(df) == n_pix_total
    return PixelMleResult(
        dataframe=df,
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
