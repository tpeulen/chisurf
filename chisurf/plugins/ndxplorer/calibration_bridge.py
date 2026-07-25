"""Push a data-optimized smFRET calibration into an in-process ndxplorer window.

ndxplorer computes its derived FRET columns (efficiency, stoichiometry, R_FRET,
…) from a small set of scalar constants that are normally typed by hand. This
bridge writes the **posterior** calibration factors (from
``chisurf.core.fluorescence.fret.calibration``) into those constants and triggers
a recompute, so ndx shows accurate, data-optimized FRET instead of guessed
constants. ndx runs in the same process as ChiSurf, so this is a direct in-memory
update — no RPC needed.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.fret.calibration import calibration_to_ndx_constants

__all__ = ["push_calibration_to_ndx", "push_unmixed_columns_to_ndx", "find_ndx_windows"]


def push_calibration_to_ndx(ndx, calibration, *, recompute: bool = True) -> dict:
    """Write calibration factors into an ndxplorer window's constants.

    Maps the calibration to ndx's MFD constant names
    (:func:`calibration_to_ndx_constants`), merges them into ``ndx.constants``,
    and (optionally) recomputes the derived columns and refreshes the plots so
    ndx's FRET efficiency/stoichiometry use the new calibration.

    Parameters
    ----------
    ndx : object
        An in-process ``NDXplorer`` window (duck-typed: needs a ``constants``
        dict; ``data_source.compute_columns`` / ``equations`` / ``update_plots``
        are used when present).
    calibration : CalibrationParameters or CalibrationFit
        The (posterior) calibration to push.
    recompute : bool, optional
        If True (default) recompute derived columns and refresh plots.

    Returns
    -------
    dict
        The mapping of ndx constant name → value that was applied.

    See Also
    --------
    push_unmixed_columns_to_ndx : inject stable-/shuffle-unmixed per-source photon
        columns (matrix un-mixing), for setups where the scalar constants are not
        enough.
    """
    mapping = calibration_to_ndx_constants(calibration)

    constants = getattr(ndx, "constants", None)
    if not isinstance(constants, dict):
        constants = {}
        ndx.constants = constants
    constants.update(mapping)

    # Best-effort: keep the parameter-editor UI in sync if it exposes a setter.
    editor = getattr(ndx, "parameter_control", None)
    if editor is not None:
        try:
            editor.update(mapping)  # ParameterEditor accepting a dict update
        except Exception:
            pass

    if recompute:
        data_source = getattr(ndx, "data_source", None)
        if data_source is not None and hasattr(data_source, "compute_columns"):
            try:
                data_source.compute_columns(
                    constants=ndx.constants, equations=getattr(ndx, "equations", None)
                )
            except Exception:
                pass
        update = getattr(ndx, "update_plots", None)
        if callable(update):
            try:
                update()
            except Exception:
                pass

    return mapping


def find_ndx_windows() -> list:
    """Return the open in-process ndXplorer windows.

    ndXplorer runs inside the ChiSurf process, so a tool that wants to push a
    calibration (or read burst columns) only has to find the window among the
    top-level Qt widgets. Returns an empty list when Qt is not running — the
    callers stay usable head-less.

    Returns
    -------
    list
        Every ndXplorer-like top-level window, newest last.
    """
    try:
        from qtpy import QtWidgets
    except Exception:  # pragma: no cover - head-less
        return []
    app = QtWidgets.QApplication.instance()
    if app is None:
        return []
    windows = []
    for widget in app.topLevelWidgets():
        looks_like_ndx = type(widget).__name__ == "NDXplorer" or (
            hasattr(widget, "constants") and hasattr(widget, "data_source")
        )
        if looks_like_ndx:
            windows.append(widget)
    return windows


def _column(data, name):
    """Return ``data[name]`` as a float array, or ``None`` if absent."""
    try:
        if name in data:
            return np.asarray(data[name], dtype=float)
    except Exception:
        pass
    return None


def push_unmixed_columns_to_ndx(
    ndx,
    *,
    emission,
    channel_columns,
    source_labels,
    unmix: str = "stable",
    seed=None,
    rate_columns=None,
    recompute: bool = True,
) -> dict:
    """Inject stable-/shuffle-unmixed per-source photon columns into ndxplorer.

    ndxplorer's native FRET pipeline is a scalar linear correction
    (``Fr = Sr - Br - alpha*Sg``) with no matrix inversion or positivity
    constraint, so with strong spectral overlap it can produce negative,
    noise-amplified signals. This reads the per-burst measured photon counts from
    ``ndx.data_source.data`` and spectrally **un-mixes** them with the light-path
    ``emission`` matrix using either

    * ``unmix="stable"`` — non-negative least squares (continuous, robust to
      ill-conditioning), or
    * ``unmix="shuffle"`` — integer multinomial photon reassignment
      (Poisson-statistics preserving).

    The leakage-free per-source photon counts (and their rates, if the
    corresponding raw-rate columns are given) are written back as **new** columns,
    leaving ndx's native columns and equations untouched, so nothing is
    double-corrected. The new columns are then available for plotting, gating and
    export in ndx.

    Nothing about the detector/channel naming is hard-coded: the caller supplies
    the measured-channel column names, the emission matrix, and the source labels
    (all obtainable from the light-path calculator, e.g. via
    :func:`chisurf.core.fluorescence.fret.calibration.crosstalk_matrices_from_lightpath`),
    so the same bridge works for any 2-, 3- or N-colour setup.

    Parameters
    ----------
    ndx : object
        In-process ndxplorer window; needs ``data_source.data`` (a mapping /
        DataFrame of burst columns).
    emission : array_like
        ``(n_sources, n_detectors)`` emission/detection crosstalk matrix
        ``emission[k, m]`` (source ``k`` detected in channel ``m``); its columns
        are aligned with ``channel_columns`` and rows with ``source_labels``.
    channel_columns : sequence of str
        Column names in ``data`` holding the measured per-detector photon counts,
        ordered to match the columns of ``emission``.
    source_labels : sequence of str
        Names for the un-mixed sources, ordered to match the rows of ``emission``;
        used to name the injected columns.
    unmix : {"stable", "shuffle"}, optional
        Un-mixing method (default ``"stable"``).
    seed : int, optional
        Seed for the ``"shuffle"`` reassignment.
    rate_columns : sequence of str or None, optional
        Optional raw count-rate column names parallel to ``channel_columns``; when
        given, an un-mixed rate column is written per source (raw rate scaled by
        the redistributed-count ratio, i.e. the same per-burst duration).
    recompute : bool, optional
        If True recompute ndx's derived columns and refresh plots afterwards.

    Returns
    -------
    dict
        ``{injected_column_name: total_or_summary}`` for the columns written (empty
        if the required source columns were absent).
    """
    from chisurf.core.fluorescence.crosstalk import invert_mixing, photon_shuffle_unmix

    method = str(unmix).lower()
    suffix = "shuffle" if method == "shuffle" else "unmix"

    data_source = getattr(ndx, "data_source", None)
    data = getattr(data_source, "data", None)
    if data is None:
        return {}

    channel_columns = list(channel_columns)
    source_labels = list(source_labels)
    emis = np.asarray(emission, dtype=float)
    if emis.shape != (len(source_labels), len(channel_columns)):
        raise ValueError(
            "emission shape must be (len(source_labels), len(channel_columns)); "
            f"got {emis.shape} for {len(source_labels)}x{len(channel_columns)}"
        )

    measured = [_column(data, c) for c in channel_columns]
    if any(col is None for col in measured):
        return {}
    counts = np.vstack(measured)  # (n_detectors, n_burst)

    if method == "shuffle":
        src = photon_shuffle_unmix(np.rint(counts).astype(np.int64), emis, seed=seed)
        src = src.astype(float)
    else:
        src = np.clip(invert_mixing(emis, counts, nonneg=True), 0.0, None)

    injected: dict = {}
    count_cols = []
    for k, label in enumerate(source_labels):
        col = f"Number of Photons ({label}, {suffix})"
        data[col] = src[k]
        injected[col] = float(np.sum(src[k]))
        count_cols.append(col)

    # optional rate columns: convert the un-mixed per-source counts to rates using
    # the burst's measured photons-per-kHz (total rate / total counts), which is
    # the same per-burst duration for every channel.
    if rate_columns is not None:
        rate_arrays = [_column(data, r) for r in rate_columns]
        if all(r is not None for r in rate_arrays):
            raw_count_tot = counts.sum(axis=0)
            raw_rate_tot = np.sum(rate_arrays, axis=0)
            with np.errstate(divide="ignore", invalid="ignore"):
                per_photon_rate = np.where(raw_count_tot > 0,
                                           raw_rate_tot / raw_count_tot, 0.0)
            for k, label in enumerate(source_labels):
                rcol = f"{label} Count Rate {suffix} (KHz)"
                data[rcol] = src[k] * per_photon_rate
                injected[rcol] = "rate"

    if recompute:
        if data_source is not None and hasattr(data_source, "compute_columns"):
            try:
                data_source.compute_columns(
                    constants=getattr(ndx, "constants", None),
                    equations=getattr(ndx, "equations", None),
                )
            except Exception:
                pass
        update = getattr(ndx, "update_plots", None)
        if callable(update):
            try:
                update()
            except Exception:
                pass

    return injected
