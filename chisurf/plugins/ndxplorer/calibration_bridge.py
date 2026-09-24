"""Data-optimized smFRET calibration for an in-process ndxplorer window.

ndxplorer computes its derived FRET columns (efficiency, stoichiometry, R_FRET,
…) from a small set of scalar constants that are normally typed by hand. This
bridge closes that loop against the measurement ndx has open:

* :func:`optimize_calibration_from_ndx` — the whole workflow in one call. Read
  the burst columns out of the window, start from the constants it already
  carries, determine the correction factors from that data
  (:func:`~chisurf.core.fluorescence.fret.accurate.auto_calibrate`), write the
  posterior back and inject the accurate per-burst columns.
* :func:`push_calibration_to_ndx` — write factors calibrated elsewhere.
* :func:`push_unmixed_columns_to_ndx` — inject spectrally un-mixed photon columns
  for setups the scalar constants cannot describe.

ndx runs in the same process as ChiSurf, so these are direct in-memory updates —
no RPC needed.
"""

from __future__ import annotations

import logging
import pathlib
from collections.abc import Sequence

import numpy as np

from chisurf.core.fluorescence.fret.calibration import CalibrationFit, CalibrationParameters

__all__ = [
    "calibration_to_ndx_constants",
    "calibration_from_ndx_constants",
    "push_calibration_to_ndx",
    "push_unmixed_columns_to_ndx",
    "optimize_calibration_from_ndx",
    "calibration_from_container",
    "background_from_container",
    "restore_calibration_from_container",
    "refresh_stored_parameters",
    "CALIBRATION_ARTIFACT",
    "refresh_column_selectors",
    "find_ndx_windows",
]


_NDX_FACTORS = ("gamma", "alpha", "beta", "delta", "bg_dd", "bg_da", "bg_aa", "r0", "phi_a",
                "phi_d")


def calibration_to_ndx_constants(calibration) -> dict:
    """A calibration group's factors as ndX constants (``gG/gR``, ``alpha``, ``beta``, ``r``, ...).

    The name mapping is ndX's (:func:`ndxplorer.analysis.fret_backend.constants_from_factors`):
    ndX's ``beta`` is the direct excitation, ``r = 1/beta`` and
    ``gG/gR = (PhiA/PhiD)/gamma``.
    """
    from ndxplorer.analysis.fret_backend import constants_from_factors

    calib = calibration.model if isinstance(calibration, CalibrationFit) else calibration
    return constants_from_factors({name: float(getattr(calib, name)) for name in _NDX_FACTORS})


def calibration_from_ndx_constants(constants: dict, calib=None):
    """ndX constants into a calibration group; a missing constant keeps the group's value.

    The inverse of :func:`calibration_to_ndx_constants`, through ndX's own
    mapping (:func:`ndxplorer.analysis.fret_backend.factors_from_constants`).
    """
    from ndxplorer.analysis.fret_backend import factors_from_constants

    calib = calib if calib is not None else CalibrationParameters()
    start = {name: float(getattr(calib, name)) for name in _NDX_FACTORS}
    for name, value in factors_from_constants(dict(constants or {}), start).items():
        setattr(calib, name, value)
    return calib


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
    return _push_constants(ndx, calibration_to_ndx_constants(calibration), recompute=recompute)


def find_ndx_windows() -> list:
    """Return the open in-process ndX windows.

    ndX runs inside the ChiSurf process, so a tool that wants to push a
    calibration (or read burst columns) only has to find the window among the
    top-level Qt widgets. Returns an empty list when Qt is not running — the
    callers stay usable head-less.

    Returns
    -------
    list
        Every ndX-like top-level window, newest last.
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


def _artifacts(measurement):
    """Every artifact, newest first, skipping any that cannot be described.

    Newest first because a container *keeps* what it is given: pressing Save
    calibration a second time adds beside the first rather than replacing it.
    """
    try:
        return list(reversed(list(measurement.artifacts())))
    except Exception:
        return []


def _container_of(source):
    """Walk a run path up to the ``.pto`` it lives in, or ``None``."""
    path = pathlib.Path(str(source))
    while path.suffix.lower() != ".pto" and path.parent != path:
        path = path.parent
    return path if path.suffix.lower() == ".pto" and path.is_file() else None


def background_from_container(source) -> dict:
    """The per-detector background **rates** stored in a measurement, as ndX constants.

    ``{"Bg": kHz, "Br": kHz, "By": kHz}`` for the detectors the measurement has
    an estimate for; empty when it carries none. *source* is the container or a
    run path inside one. ndX reads it (with tttrlib alone): see
    :func:`ndxplorer.analysis.fret_background.stored_background_constants`.
    """
    from ndxplorer.analysis.fret_background import stored_background_constants

    path = _container_of(source)
    return stored_background_constants(str(path)) if path is not None else {}


#: Artifact the Accurate FRET step writes into a measurement. Its rows are the
#: populations; the factor columns are constant across them on purpose, so any
#: row carries the whole calibration.
CALIBRATION_ARTIFACT = "accurate fret calibration"


def calibration_from_container(source) -> dict:
    """The correction factors stored in a measurement, or ``{}``.

    A calibration belongs to the measurement it was determined on, and the
    Accurate FRET step already writes it there — one ``parameter_table``
    artifact whose ``alpha`` / ``beta`` / ``gamma`` / ``delta`` / ``r0`` columns
    are constant over the populations. Nothing read it back, so opening the
    container in ndX gave a window with the *previous* measurement's constants
    still in it: numbers that look determined, belong to another file, and
    correct every burst by the wrong amounts.

    Parameters
    ----------
    source : path-like
        The container, or a run path inside one.

    Returns
    -------
    dict
        ``{factor: value}`` in **Hellenkamp** names (the ones
        :class:`~chisurf.core.fluorescence.fret.calibration.CalibrationParameters`
        uses), empty when the measurement carries no calibration. Values that
        are not finite are left out rather than applied.
    """
    from chisurf.core.fio.pto import Measurement

    path = pathlib.Path(str(source))
    while path.suffix.lower() != ".pto" and path.parent != path:
        path = path.parent
    if path.suffix.lower() != ".pto" or not path.is_file():
        return {}

    factors: dict[str, float] = {}
    try:
        with Measurement.open(path, writable=False) as measurement:
            # The most recent calibration: a re-run adds, it does not replace.
            for obj in _artifacts(measurement):
                if getattr(obj, "name", "") != CALIBRATION_ARTIFACT:
                    continue
                try:
                    store = measurement.get_store(obj.uid)
                except Exception:
                    continue
                names = [store.column(i).name() for i in range(store.n_columns())]
                # By the declared schema, not by guessing the headers: the same
                # file the writer emits from, so the two cannot drift. It also
                # understands what older containers were written with.
                from chisurf.plugins.burst.accurate_fret.calibration_columns import (
                    factor_for_column,
                    is_derived,
                )

                for index, column in enumerate(names):
                    factor = factor_for_column(str(column))
                    # A derived column is written for readers of the file and
                    # never applied: restoring gG/gR on top of the gamma and the
                    # yields it derives from is how the two stop agreeing.
                    if factor is None or is_derived(str(column)):
                        continue
                    values = np.asarray(store.column(index).numpy(), dtype=float)
                    finite = values[np.isfinite(values)]
                    if finite.size:
                        factors[factor] = float(finite[0])
                break
    except Exception:
        logging.debug("could not read a calibration from %s", path, exc_info=True)
        return {}
    return factors


def restore_calibration_from_container(ndx, source=None) -> dict:
    """Apply a measurement's stored calibration to an ndX window.

    Called when a container is opened, so the constants in the window are the
    ones determined *on the data now loaded*.

    Returns
    -------
    dict
        The ndX constants actually written, empty when there was nothing to
        restore.
    """
    if source is None:
        data_source = getattr(ndx, "data_source", None)
        provenance = getattr(data_source, "provenance", None) or {}
        source = provenance.get("container_path") or ""
    if not source:
        return {}

    # Everything the measurement carries about how to correct it -- the factors
    # *and* the backgrounds. A measurement that has had its background measured
    # but not its factors determined (the ordinary state, since the background
    # step comes first) still has something to restore, and it is the part the
    # equations use most directly.
    factors = calibration_from_container(source)
    # ndX's own reading of the container: the background step's rates and the
    # newest explicitly saved calibration (ndX's constants, gG/gR included --
    # the one thing the factor table does not carry), with the newer of the two
    # winning Bg/Br/By.
    from ndxplorer.io.fret_calibration_io import restorable

    path = _container_of(source)
    kept = restorable(str(path)) if path is not None else {"saved": {}, "background": {}}
    rates, saved = kept["background"], kept["saved"]
    if not factors and not rates and not saved:
        return {}

    # Applied once per *value*, not once per open. Re-running the background
    # step writes a new estimate into the container while this window is up, and
    # the window should follow it -- but a window whose stored parameters have
    # not moved must be left exactly as it is, because anything the user tuned
    # in the meantime is theirs. So the comparison is against what was last
    # restored from this container, not against what the window now holds.
    stored = {**factors, **rates, **{f"saved:{k}": v for k, v in saved.items()}}
    key = str(pathlib.Path(str(source)).resolve())
    seen = getattr(ndx, "_restored_parameters", None)
    if not isinstance(seen, dict):
        seen = {}
    if seen.get(key) == stored:
        return {}

    constants = dict(getattr(ndx, "constants", {}) or {})
    # Start from what the window holds, so quantum yields and anything else it
    # carries survive; only what the measurement stores is replaced.
    calib = calibration_from_ndx_constants(constants)
    for name, value in factors.items():
        setattr(calib, name, float(value))
    # The backgrounds travel on the calibration too -- ``calibration_to_ndx_constants``
    # already maps bg_dd/bg_da/bg_aa onto Bg/Br/By -- so one push carries both.
    # That matters more than it looks: writing constants directly leaves the
    # *parameter table* holding the old values, and ndX's recompute throttle
    # resets ``constants`` from that table on the next parameter event. A value
    # written the short way is correct only until something happens.
    for attribute, constant in (("bg_dd", "Bg"), ("bg_da", "Br"), ("bg_aa", "By")):
        if constant in rates:
            setattr(calib, attribute, float(rates[constant]))
    applied = push_calibration_to_ndx(ndx, calib, recompute=not saved)

    if saved:
        # Written through the same seam, so the parameter table follows and the
        # recompute throttle cannot revert them on the next event.
        editor = getattr(ndx, "parameter_control", None)
        apply_values = getattr(editor, "apply_values", None)
        if callable(apply_values):
            apply_values(saved)
        constants_map = getattr(ndx, "constants", None)
        update = getattr(constants_map, "update", None)
        if callable(update):
            update(saved)
        elif constants_map is not None:
            merged = dict(constants_map)
            merged.update(saved)
            ndx.constants = merged
        if callable(apply_values):
            try:
                ndx._prev_constants = dict(editor.dict)
            except Exception:
                pass
        applied.update(saved)
        data_source = getattr(ndx, "data_source", None)
        if data_source is not None and hasattr(data_source, "compute_columns"):
            try:
                data_source.compute_columns(
                    constants=ndx.constants, equations=getattr(ndx, "equations", None)
                )
            except Exception:
                pass
        for refresh in ("update_plots", "refresh_column_selectors"):
            method = getattr(ndx, refresh, None)
            if callable(method):
                try:
                    method()
                except Exception:
                    pass
    seen[key] = stored
    try:
        ndx._restored_parameters = seen
    except Exception:
        pass

    logging.info(
        "restored from %s: %s",
        pathlib.Path(str(source)).name,
        ", ".join(
            [f"{k}={v:.4g}" for k, v in factors.items()]
            + [f"{k}={v:.4g} kHz" for k, v in rates.items()]
            + (
                [f"saved calibration ({len(saved)} constants, gG/gR={saved['gG/gR']:.4g})"]
                if "gG/gR" in saved
                else [f"saved calibration ({len(saved)} constants)"]
                if saved
                else []
            )
        )
        or "nothing",
    )
    return applied


def _push_constants(ndx, mapping: dict, *, recompute: bool = True) -> dict:
    """Write ndX constants into a window: its parameter table, then its mapping.

    The parameter *table* is the source of truth, not ``ndx.constants``:
    ndxplorer's recompute throttle resets ``constants`` from
    ``parameter_control.dict`` on every parameter event, so a value written only
    into the mapping is reverted the moment the event loop turns. A live
    ``ConstantsMapping`` is updated in place, which keeps Global-View links.
    """
    editor = getattr(ndx, "parameter_control", None)
    apply_values = getattr(editor, "apply_values", None)
    if callable(apply_values):
        apply_values(mapping)
    constants = getattr(ndx, "constants", None)
    update = getattr(constants, "update", None)
    if callable(update):
        update(mapping)
    else:
        constants = dict(constants or {})
        constants.update(mapping)
        ndx.constants = constants
    if callable(apply_values):
        try:
            ndx._prev_constants = dict(editor.dict)
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
        update_plots = getattr(ndx, "update_plots", None)
        if callable(update_plots):
            try:
                update_plots()
            except Exception:
                pass
    return mapping


def optimize_calibration_from_ndx(
    ndx,
    *,
    columns: dict | None = None,
    donor_lifetime: float | None = None,
    linker_sigma: float = 6.0,
    gamma_source: str = "auto",
    n_bootstrap: int = 50,
    lightpath: dict | None = None,
    use_priors: bool = True,
    factors: Sequence[str] | None = None,
    background: str = "constants",
    min_population: int = 20,
    inject_columns: bool = True,
    recompute: bool = True,
    progress=None,
) -> dict:
    """Calibrate an open ndX window's constants against its bursts, in place.

    The calibration is ndX's own
    (:func:`ndxplorer.analysis.fret_backend.calibrate_columns`, computed by
    tttrlib); this adds what only ChiSurf has -- the light-path priors
    (``lightpath``, keyword arguments of
    :func:`~chisurf.core.fluorescence.fret.calibration.set_priors_from_lightpath`,
    which also seed gamma/alpha/delta at the optics values) -- and writes the
    result into the Qt window: the constants through its parameter table, the
    accurate columns into its data source.

    Parameters are the options of the calibration (see ``calibrate_columns``);
    ``columns`` overrides the channel mapping (``{role: column}``), ``factors``
    names the factors written (all by default), ``recompute`` refreshes the
    window's derived columns and plots.

    Returns
    -------
    dict
        The calibration's result (``ok``, ``constants``, ``before``, ``factors``,
        ``uncertainties``, ``report``, ``columns``, ``injected``,
        ``populations``, ``species``, ``vectors``, ...), or ``{"ok": False,
        "error": ...}``.
    """
    from ndxplorer.analysis.fret_backend import calibrate_columns

    data_source = getattr(ndx, "data_source", None)
    table = ndx_columns(data_source)
    if not table:
        return {"ok": False, "error": "the ndX window holds no burst columns"}
    constants = dict(getattr(ndx, "constants", {}) or {})
    start, priors, notes = dict(constants), None, []
    if lightpath:
        from chisurf.core.fluorescence.fret.accurate import calibration_constants
        from chisurf.core.fluorescence.fret.calibration import set_priors_from_lightpath

        calib = calibration_from_ndx_constants(constants)
        optics = set_priors_from_lightpath(calib, **lightpath)
        priors = calibration_constants(calib)["priors"]
        start.update(calibration_to_ndx_constants(calib))
        notes.append(
            "light path: gamma {gamma:.4f}, alpha {alpha:.4f}, delta {delta:.4f} "
            "(prior means)".format(**optics)
        )
    provenance = getattr(data_source, "provenance", None) or {}
    options = {
        "columns": dict(columns or {}), "donor_lifetime": donor_lifetime,
        "linker_sigma": float(linker_sigma), "gamma_source": gamma_source,
        "n_bootstrap": int(n_bootstrap), "use_priors": bool(use_priors),
        "factors": None if factors is None else list(factors), "background": background,
        "min_population": int(min_population), "inject_columns": bool(inject_columns),
    }
    result = calibrate_columns(table, start, options,
                               container=str(provenance.get("container_path") or ""),
                               progress=progress, priors=priors)
    if not result.get("ok"):
        return result
    result["before"] = {k: constants.get(k) for k in result["constants"]}
    if notes:
        result["report"] = "\n".join(f"  ! {n}" for n in notes) + "\n" + result["report"]
    for name, values in result.get("new_columns", {}).items():
        data_source.set_column(name, np.asarray(values, dtype=float))
    if result.get("new_columns"):
        refresh_column_selectors(ndx)
    result["constants"] = _push_constants(ndx, result["constants"], recompute=recompute)
    return result


def refresh_column_selectors(ndx) -> None:
    """Make newly injected columns selectable in ndxplorer's axis pickers.

    Writing a column into the data source does not tell the window about it,
    so an injected column would exist but be unplottable until the next reload.
    Best-effort and silent: a window that does not expose the hook simply keeps
    its current selectors.

    Parameters
    ----------
    ndx : object
        In-process ndX window.
    """
    data_source = getattr(ndx, "data_source", None)
    for name in ("update_parameter_names", "refresh_axis_comboboxes_preserving_selection"):
        hook = getattr(ndx, name, None)
        if callable(hook):
            try:
                hook()
            except Exception:
                pass
    # Some builds cache the names on the data source itself.
    refresh = getattr(data_source, "update_parameter_names", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:
            pass


def ndx_columns(data_source) -> dict:
    """The numeric columns of an ndX data source, as ``{name: float array}``.

    A column holding no finite value (a text column reads as all NaN) is left
    out.
    """
    if data_source is None:
        return {}
    columns: dict = {}
    for name in data_source.parameter_names:
        values = data_source.column_values(name)
        if values is not None and values.size and np.any(np.isfinite(values)):
            columns[str(name)] = values
    return columns


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
    ``ndx.data_source`` and spectrally **un-mixes** them with the light-path
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
        In-process ndxplorer window; needs a ``data_source`` holding the burst
        columns.
    emission : array_like
        ``(n_sources, n_detectors)`` emission/detection crosstalk matrix
        ``emission[k, m]`` (source ``k`` detected in channel ``m``); its columns
        are aligned with ``channel_columns`` and rows with ``source_labels``.
    channel_columns : sequence of str
        Column names in the data source holding the measured per-detector photon counts,
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
    if data_source is None:
        return {}

    channel_columns = list(channel_columns)
    source_labels = list(source_labels)
    emis = np.asarray(emission, dtype=float)
    if emis.shape != (len(source_labels), len(channel_columns)):
        raise ValueError(
            "emission shape must be (len(source_labels), len(channel_columns)); "
            f"got {emis.shape} for {len(source_labels)}x{len(channel_columns)}"
        )

    measured = [data_source.column_values(c) for c in channel_columns]
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
        data_source.set_column(col, src[k])
        injected[col] = float(np.sum(src[k]))
        count_cols.append(col)

    # optional rate columns: convert the un-mixed per-source counts to rates using
    # the burst's measured photons-per-kHz (total rate / total counts), which is
    # the same per-burst duration for every channel.
    if rate_columns is not None:
        rate_arrays = [data_source.column_values(r) for r in rate_columns]
        if all(r is not None for r in rate_arrays):
            raw_count_tot = counts.sum(axis=0)
            raw_rate_tot = np.sum(rate_arrays, axis=0)
            with np.errstate(divide="ignore", invalid="ignore"):
                per_photon_rate = np.where(raw_count_tot > 0, raw_rate_tot / raw_count_tot, 0.0)
            for k, label in enumerate(source_labels):
                rcol = f"{label} Count Rate {suffix} (KHz)"
                data_source.set_column(rcol, src[k] * per_photon_rate)
                injected[rcol] = "rate"

    refresh_column_selectors(ndx)
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


def refresh_stored_parameters(ndx) -> dict:
    """Re-read the open measurement's stored parameters and apply any change.

    Called when a step that owns an ndX window is revisited. The container is
    the shared surface between the steps: the background step writes into it,
    the calibration step writes into it, and a window opened before either of
    them ran is holding numbers that have since been superseded on disk.

    Cheap enough to call on every revisit -- one container open and two small
    artifact reads -- and a no-op when nothing has changed, which is what keeps
    it from overwriting values the user tuned themselves.
    """
    return restore_calibration_from_container(ndx)
