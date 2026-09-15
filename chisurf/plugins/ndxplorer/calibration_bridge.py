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

from chisurf.core.fluorescence.fret.calibration import calibration_to_ndx_constants

__all__ = [
    "push_calibration_to_ndx",
    "push_unmixed_columns_to_ndx",
    "optimize_calibration_from_ndx",
    "measured_background",
    "fitted_background",
    "calibration_from_container",
    "background_from_container",
    "saved_constants_from_container",
    "restore_calibration_from_container",
    "refresh_stored_parameters",
    "CALIBRATION_ARTIFACT",
    "refresh_column_selectors",
    "find_ndx_windows",
]


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

    # The parameter *table* is the source of truth, not ``ndx.constants``.
    # ndxplorer's recompute throttle resets ``constants`` from
    # ``parameter_control.dict`` on every parameter event, so a calibration
    # written only into the mapping is reverted the moment the event loop turns
    # — the values were correct for as long as nothing happened, which is why
    # this looked like it worked outside a running GUI.
    editor = getattr(ndx, "parameter_control", None)
    applied_to_table = False
    apply_values = getattr(editor, "apply_values", None)
    if callable(apply_values):
        apply_values(mapping)
        applied_to_table = True

    # ``constants`` is a plain dict in the legacy path and a live
    # ``ConstantsMapping`` over the fitting-parameter group when the chisurf
    # table is in use. The latter is a Mapping, *not* a dict, and writing
    # through it is what keeps Global-View crosslinks alive — so update it in
    # place and never replace it.
    constants = getattr(ndx, "constants", None)
    update = getattr(constants, "update", None)
    if callable(update):
        update(mapping)
    else:
        constants = dict(constants or {})
        constants.update(mapping)
        ndx.constants = constants

    if applied_to_table:
        # Keep the throttle's diff baseline consistent with what the table now
        # holds, so the push does not read back as an edit of every constant.
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
        update = getattr(ndx, "update_plots", None)
        if callable(update):
            try:
                update()
            except Exception:
                pass

    return mapping


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




def fitted_background(i_dd, i_da, i_aa, split, *, durations=None,
                      min_population: int = 20) -> dict:
    """Channel background **rates** estimated from the reference populations.

    Often nobody knows the background. But the measurement contains two
    populations that are *defined* by a missing fluorophore, and in each of them
    one channel is measuring background and nothing else:

    * an **acceptor-only** burst has no donor, so what appears in the donor
      channel under donor excitation is background — that is ``bg_dd``;
    * a **donor-only** burst has no acceptor, so what appears under acceptor
      excitation is background — that is ``bg_aa``;
    * ``bg_da`` comes from the leakage relation on the donor-only bursts,
      ``I_DA = alpha * I_DD + bg_da * T``. Fitting the duration term explicitly
      is what separates leakage from background at all; taking the ratio of the
      means, which is the usual shortcut, silently folds the background into
      alpha and then subtracts it from every burst as if it scaled with donor
      brightness.

    **The answer is a rate (kHz), not a count.** What these populations give
    directly is counts, and counts are not a property of the measurement: a 4 ms
    burst carries four times the background of a 1 ms one. Dividing by the burst
    duration is what makes the number comparable with the measured background
    from the inter-photon-time fit -- and it is what the consumer expects, since
    ndX's ``Bg``/``Br``/``By`` are rates (``Fg = Sg - Bg`` with ``Sg`` in kHz).
    Returning counts here is what made a fitted background over-correct: a
    median of 8 photons per burst arrived in the window as 8 kHz, against a real
    background of about 3.

    Medians, not means: these populations are the ones a mixture model is least
    certain about, so a handful of misassigned bright bursts would otherwise set
    the background for the whole measurement.

    Parameters
    ----------
    i_dd, i_da, i_aa : array_like
        The three channels. ``i_aa`` may be ``None``.
    split : object
        The population split from
        :func:`~chisurf.core.fluorescence.fret.accurate.auto_calibrate`, with
        boolean ``donor_only`` / ``acceptor_only`` masks.
    durations : array_like, optional
        Per-burst durations in ms. Without them no rate can be formed and the
        result is empty — better than returning counts labelled as rates.
    min_population : int, optional
        Smallest population accepted for an estimate. Below it the channel is
        left out rather than guessed — an absent key means "not determined",
        and the caller keeps whatever it had.

    Returns
    -------
    dict
        ``{"bg_dd": float, "bg_da": float, "bg_aa": float}`` in kHz, for the
        channels that could be estimated. Never negative.
    """
    out: dict[str, float] = {}
    if split is None or durations is None:
        return out
    dt = np.asarray(durations, dtype=float)
    donor_only = np.asarray(getattr(split, "donor_only", []), dtype=bool)
    acceptor_only = np.asarray(getattr(split, "acceptor_only", []), dtype=bool)
    dd = np.asarray(i_dd, dtype=float)
    da = np.asarray(i_da, dtype=float)
    aa = None if i_aa is None else np.asarray(i_aa, dtype=float)

    if dt.size != dd.size:
        return out

    def rate(counts, mask):
        """Median of the per-burst rate — a median of ratios, not a ratio of
        medians, so one long dim burst cannot stand in for the population."""
        good = mask & np.isfinite(counts) & np.isfinite(dt) & (dt > 0)
        if int(good.sum()) < min_population:
            return None
        return float(max(0.0, np.median(counts[good] / dt[good])))

    if acceptor_only.size == dd.size:
        value = rate(dd, acceptor_only)
        if value is not None:
            out["bg_dd"] = value
    if aa is not None and donor_only.size == aa.size:
        value = rate(aa, donor_only)
        if value is not None:
            out["bg_aa"] = value

    if donor_only.size == dd.size and int(donor_only.sum()) >= min_population:
        # I_DA = alpha * I_DD + bg_da * T, solved for both at once. The duration
        # is a *regressor*, not a constant offset: fitting an intercept instead
        # says every burst carries the same background whatever its length.
        x, y, t = dd[donor_only], da[donor_only], dt[donor_only]
        finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(t) & (t > 0)
        if int(finite.sum()) >= min_population and np.ptp(x[finite]) > 0 \
                and np.ptp(t[finite]) > 0:
            design = np.column_stack([x[finite], t[finite]])
            solution, *_ = np.linalg.lstsq(design, y[finite], rcond=None)
            # solution[0] is a leakage slope; alpha is determined by the
            # calibration, not here, so only the rate is kept.
            out["bg_da"] = float(max(0.0, solution[1]))
    return out



#: Detector name in a measurement's background artifact → the channel it is the
#: background of. The Seidel vocabulary, the same one the burst tables use.
_BACKGROUND_ROLES = {"green": "i_dd", "red": "i_da", "yellow": "i_aa"}


#: Artifact ndX's "Save calibration" writes: a JSON blob whose ``constants``
#: block is this window's own constant names, gG/gR included.
SAVED_CALIBRATION_ARTIFACT = "fret_calibration"


def _artifacts(measurement):
    """Every artifact, newest first, skipping any that cannot be described.

    Newest first because a container *keeps* what it is given: pressing Save
    calibration a second time adds beside the first rather than replacing it.
    """
    try:
        return list(reversed(list(measurement.artifacts())))
    except Exception:
        return []


def saved_constants_from_container(source) -> dict:
    """The constants of the most recent explicitly saved calibration.

    ndX's *Save calibration* writes a JSON artifact holding this window's own
    constants -- ``gG/gR``, ``PhiA``, ``PhiD``, the backgrounds -- which is a
    different thing from the ``accurate fret calibration`` table the Accurate
    FRET step writes, and the only one that carries the detection-efficiency
    ratio directly. Reading only the table meant a user who had pressed Save got
    nothing back.

    Returns
    -------
    dict
        ndX constant names to values, empty when the measurement has no saved
        calibration.
    """
    import json

    from chisurf.core.fio.pto import Measurement

    path = _container_of(source)
    if path is None:
        return {}
    try:
        with Measurement.open(path, writable=False) as measurement:
            # By the timestamp in the payload, because the container reuses the
            # slots of removed objects: once the saved-calibration history has
            # been pruned even once, position no longer says which is newest.
            candidates = []
            for index, obj in enumerate(_artifacts(measurement)):
                if getattr(obj, "name", "") != SAVED_CALIBRATION_ARTIFACT:
                    continue
                try:
                    blob = measurement.get_blob(obj.uid)
                except Exception:
                    continue
                try:
                    if isinstance(blob, (bytes, bytearray)):
                        blob = blob.decode("utf-8")
                    payload = json.loads(blob)
                except Exception:
                    continue
                constants = payload.get("constants")
                if isinstance(constants, dict) and constants:
                    candidates.append((
                        str(payload.get("saved_utc", "")), -index,
                        {str(k): float(v) for k, v in constants.items()
                         if isinstance(v, (int, float)) and np.isfinite(float(v))},
                    ))
            if candidates:
                candidates.sort(key=lambda entry: (entry[0], entry[1]))
                return candidates[-1][2]
    except Exception:
        logging.debug("could not read a saved calibration from %s", path,
                      exc_info=True)
    return {}


def _artifact_age(source, name: str) -> int:
    """How far back an artifact sits, newest first; ``-1`` when absent.

    A container keeps everything it is given, so "which of these two is current"
    is a question about *position*, not about type. Deciding it by type instead
    meant a calibration saved last week overrode a background measured this
    morning.
    """
    from chisurf.core.fio.pto import Measurement

    path = _container_of(source)
    if path is None:
        return -1
    try:
        with Measurement.open(path, writable=False) as measurement:
            for index, obj in enumerate(_artifacts(measurement)):
                if getattr(obj, "name", "") == name:
                    return index
    except Exception:
        return -1
    return -1


def _container_of(source):
    """Walk a run path up to the ``.pto`` it lives in, or ``None``."""
    path = pathlib.Path(str(source))
    while path.suffix.lower() != ".pto" and path.parent != path:
        path = path.parent
    return path if path.suffix.lower() == ".pto" and path.is_file() else None


#: Detector in a measurement's background artifact -> the ndX constant that
#: holds its rate. ndX's Bg/Br/By are subtracted from the **kHz** stream columns
#: (``Fg(PIE) = Sg(PIE) - Bg`` where ``Sg(PIE)`` is ``S prompt green (kHz)``),
#: so a stored rate goes in as it stands -- no duration, no unit factor.
_BACKGROUND_CONSTANTS = {"green": "Bg", "red": "Br", "yellow": "By"}


def background_from_container(source) -> dict:
    """The per-detector background **rates** stored in a measurement.

    Returns
    -------
    dict
        ``{"Bg": kHz, "Br": kHz, "By": kHz}`` for the detectors the measurement
        has an estimate for; empty when it carries none. A detector whose rate
        is not finite is left out rather than written as zero -- "not measured"
        and "measured as nothing" are different claims, and only one of them is
        safe to subtract.
    """
    from chisurf.core.fio.pto import Measurement

    path = pathlib.Path(str(source))
    while path.suffix.lower() != ".pto" and path.parent != path:
        path = path.parent
    if path.suffix.lower() != ".pto" or not path.is_file():
        return {}

    rates: dict[str, float] = {}
    try:
        with Measurement.open(path, writable=False) as measurement:
            # The LAST matching artifact, not the first: a container keeps the
            # estimates it has been given, so re-running the background step
            # leaves an older one in front of the newer. Reading the first meant
            # a corrected estimate was ignored in favour of the one it replaced.
            for obj in _artifacts(measurement):
                if getattr(obj, "name", "") != "background":
                    continue
                try:
                    store = measurement.get_store(obj.uid)
                except Exception:
                    # A container holds artifacts of several encodings, and
                    # ``get_store`` raises on anything that is not a dstore.
                    # Guarding the *loop* instead of each artifact meant one
                    # JSON blob stopped every later artifact from being read --
                    # which is exactly what a saved calibration is.
                    continue
                names = [store.column(i).name() for i in range(store.n_columns())]
                if "Detector" not in names or "Rate" not in names:
                    continue
                detectors = store.column(names.index("Detector"))
                values = np.asarray(
                    store.column(names.index("Rate")).numpy(), dtype=float)
                for row in range(store.n_rows()):
                    detector = str(detectors.string_at(row)).lower()
                    constant = _BACKGROUND_CONSTANTS.get(detector)
                    if constant and np.isfinite(values[row]):
                        rates[constant] = float(values[row])
                break
    except Exception:
        logging.debug("could not read a background from %s", path, exc_info=True)
        return {}
    return rates


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
            # The most recent calibration, for the reason given in
            # ``background_from_container``: a re-run adds, it does not replace.
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
                    factor_for_column, is_derived,
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
    from chisurf.core.fluorescence.fret.calibration import (
        calibration_from_ndx_constants,
    )

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
    rates = background_from_container(source)
    # An explicitly saved calibration is ndX's own constants -- gG/gR included,
    # which is the one thing neither of the other two carries: the factor table
    # stores gamma, and gG/gR is only recoverable from it together with both
    # quantum yields.
    saved = saved_constants_from_container(source)
    if saved and rates:
        # Both name Bg/Br/By, so one has to win, and it is the *newer* of the
        # two artifacts -- not the saved one by fiat. Re-measuring the
        # background after saving a calibration is the ordinary order of work,
        # and the newer estimate is the one meant.
        saved_age = _artifact_age(source, SAVED_CALIBRATION_ARTIFACT)
        background_age = _artifact_age(source, "background")
        if 0 <= background_age < saved_age:
            saved = {k: v for k, v in saved.items() if k not in rates}
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
                    constants=ndx.constants,
                    equations=getattr(ndx, "equations", None))
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
            + ([f"saved calibration ({len(saved)} constants, "
                f"gG/gR={saved['gG/gR']:.4g})"] if "gG/gR" in saved else
               [f"saved calibration ({len(saved)} constants)"] if saved else [])
        ) or "nothing",
    )
    return applied


def burst_durations_ms(table, detector: str):
    """That detector's per-burst durations in ms, else the burst's, else ``None``.

    Both background routes need this and they must agree: a background is a
    *rate*, and it becomes counts only through the length of the burst it fell
    into.
    """
    for name in (f"Duration ({detector}) (ms)", "Duration (ms)"):
        if name in table:
            return np.asarray(table[name], dtype=float)
    return None


def measured_background(ndx, table) -> dict:
    """Per-burst background **counts** from the measurement's own estimate.

    Backgrounds are not fitted by the calibration — they are an input to it, and
    every corrected quantity is a count *minus* one. Leaving them as three
    numbers somebody typed puts the least-checked part of the correction in the
    place where it changes E most: a background error moves the dim bursts and
    leaves the bright ones, which looks exactly like a real sub-population.

    The measurement already carries the answer. The background step writes a
    ``background`` artifact into the container — one rate per detector, fitted
    from that file's own inter-photon-time distribution — and a rate becomes the
    counts *in a burst* when multiplied by how long the burst lasted. That is
    the difference between a constant and a background: a 4 ms burst carries
    four times the background of a 1 ms one, and subtracting the same number
    from both is wrong in opposite directions.

    Parameters
    ----------
    ndx : object
        The ndX window; its data source's provenance names the container.
    table : mapping of str to array
        The burst columns, for the durations.

    Returns
    -------
    dict
        ``{role: array}`` for the roles that could be resolved, empty when the
        measurement has no stored background (nothing is assumed).
    """
    from chisurf.core.fio.pto import Measurement

    data_source = getattr(ndx, "data_source", None)
    provenance = getattr(data_source, "provenance", None) or {}
    container = provenance.get("container_path") or ""
    if not container:
        metadata = getattr(data_source, "metadata", None) or {}
        container = (metadata.get("provenance") or {}).get("container_path", "")
    if not container:
        return {}

    rates: dict[str, float] = {}
    try:
        with Measurement.open(container, writable=False) as measurement:
            for obj in measurement.artifacts():
                if getattr(obj, "name", "") != "background":
                    continue
                store = measurement.get_store(obj.uid)
                names = [store.column(i).name() for i in range(store.n_columns())]
                if "Detector" not in names or "Rate" not in names:
                    continue
                detectors = store.column(names.index("Detector"))
                values = np.asarray(store.column(names.index("Rate")).numpy(), dtype=float)
                for row in range(store.n_rows()):
                    rates[str(detectors.string_at(row)).lower()] = float(values[row])
                break
    except Exception:
        return {}
    if not rates:
        return {}

    out: dict[str, np.ndarray] = {}
    for detector, role in _BACKGROUND_ROLES.items():
        rate = rates.get(detector)
        durations = burst_durations_ms(table, detector)
        if rate is None or durations is None:
            continue
        # kHz x ms = counts, which is why no unit factor appears here.
        out[role] = np.clip(rate * durations, 0.0, None)
        # The rate is what the *window* holds (its Bg/Br/By are rates), so it
        # travels beside the counts rather than being re-read from the file.
        out.setdefault("rates", {})[_ROLE_TO_BG[role]] = float(rate)
    return out


#: Burst-table role → the calibration's background attribute for that channel.
_ROLE_TO_BG = {"i_dd": "bg_dd", "i_da": "bg_da", "i_aa": "bg_aa"}


#: The Hellenkamp correction factors this bridge can write, in the order the
#: paper introduces them. ``r0`` is not a correction but is carried with them
#: because the distance columns depend on it.
_FACTOR_NAMES = ("alpha", "beta", "gamma", "delta", "r0")


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
    """Optimize ndxplorer's correction constants against the data it has loaded.

    The end of the workflow: ndxplorer loads a burst measurement, and its
    correction constants — normally typed by hand — should follow from *that*
    measurement. This reads the per-burst channel columns out of the open window,
    starts from the constants the window already carries (so backgrounds, quantum
    yields, Förster radius and tau_D(0) are the user's own settings, not
    defaults), runs the automatic calibration
    (:func:`chisurf.core.fluorescence.fret.accurate.auto_calibrate` — populations
    found by a Gaussian mixture, alpha/delta from the reference populations,
    gamma/beta from the E-S fit or the static FRET line), and writes the
    posterior back into ``ndx.constants``.

    It also injects the **accurate** per-burst columns. This is not redundant:
    ndxplorer's own efficiency equation corrects leakage but has no
    direct-excitation term, so pushing the constants alone cannot make its native
    ``FRET efficiency`` column accurate. The injected columns are new names —
    ndx's own columns and equations are untouched, nothing is corrected twice.

    Parameters
    ----------
    ndx : object
        In-process ndX window (needs a ``data_source`` holding the burst
        columns, and ``constants``).
    columns : dict, optional
        Explicit ``{role: column_name}`` overrides for ``i_dd``/``i_da``/
        ``i_aa``/``tau_f``; the rest are recognised automatically
        (:func:`chisurf.core.fluorescence.burst.table.guess_columns`).
    donor_lifetime : float, optional
        Donor-only lifetime tau_D(0) in ns for the FRET lines; taken from the
        window's ``tauD0`` constant when omitted.
    linker_sigma : float, optional
        Linker width (Å) shaping the static FRET line.
    gamma_source : str, optional
        ``"auto"``, ``"es"``, ``"lifetime"`` or ``"combined"``.
    n_bootstrap : int, optional
        Bootstrap resamples for the factor uncertainties.
    lightpath : dict, optional
        Optics prior (see
        :func:`chisurf.plugins.burst.accurate_fret.core.lightpath_prior`).
    use_priors : bool, optional
        Combine the data estimates with the optics priors.
    background : str, optional
        Where the channel backgrounds come from. ``"constants"`` (the default)
        uses the three numbers the window carries — the previous behaviour.
        ``"measurement"`` uses the rates the background step stored in the
        container, scaled by each burst's duration, which makes the background a
        *per-burst* quantity rather than one number for a file. ``"none"`` sets
        them to zero.

        ``"fit"`` estimates them from the reference populations themselves (see
        :func:`fitted_background`) — for when nobody knows the background, which
        is most of the time.

        It is the input whose error is hardest to see: it moves the dim bursts
        and leaves the bright ones, which looks like a sub-population.
    min_population : int, optional
        Smallest reference population accepted when fitting the backgrounds.
    factors : sequence of str, optional
        Which correction factors the calibration is allowed to change —
        any of ``"alpha"``, ``"beta"``, ``"gamma"``, ``"delta"``, ``"r0"``.
        ``None`` (the default) applies all of them.

        The others keep the value the window already had. That is the point of
        the option: γ from a measurement's own populations is only as good as
        the populations, and someone who has determined γ properly on a
        reference sample wants α and δ fitted *around* it rather than replaced
        by a worse estimate. The calibration is still run in full — the report
        shows what each factor came out as — but only the named ones are
        written.
    inject_columns : bool, optional
        Also write the accurate per-burst ``E``/``S``/``R_DA``/population columns.
    recompute : bool, optional
        Recompute ndx's derived columns and refresh its plots afterwards.
    progress : callable, optional
        ``progress(step, total, message)``, forwarded to
        :func:`~chisurf.core.fluorescence.fret.accurate.auto_calibrate` so a
        caller can drive a bar. Return ``False`` from it to stop early. With
        ``background="fit"`` the calibration runs twice, so the steps restart;
        the message says which pass is running.

    Returns
    -------
    dict
        ``{"ok", "constants", "before", "factors", "uncertainties", "report",
        "columns", "injected", "populations"}``, or ``{"ok": False, "error": …}``
        when the window carries no usable burst columns.
    """
    from chisurf.core.fluorescence.burst.table import guess_columns
    from chisurf.core.fluorescence.fret.accurate import accurate_fret, auto_calibrate
    from chisurf.core.fluorescence.fret.calibration import calibration_from_ndx_constants
    from chisurf.core.fluorescence.fret.lines import static_fret_line

    data_source = getattr(ndx, "data_source", None)
    table = ndx_columns(data_source)
    if not table:
        return {"ok": False, "error": "the ndX window holds no burst columns"}

    mapping = {**guess_columns(table), **{k: v for k, v in (columns or {}).items() if v}}
    for role in ("i_dd", "i_da"):
        if mapping.get(role) not in table:
            return {
                "ok": False,
                "error": (f"could not identify the {role} column among "
                          f"{', '.join(list(table)[:12])}…; pass it explicitly"),
            }

    def pick(role):
        name = mapping.get(role)
        return table[name] if name in table else None

    # Backgrounds first: everything below is computed from counts that already
    # have them subtracted.
    per_burst_background: dict = {}
    background_rates: dict = {}
    if background == "measurement":
        per_burst_background = measured_background(ndx, table)
        background_rates = dict(per_burst_background.pop("rates", {}) or {})

    constants = dict(getattr(ndx, "constants", {}) or {})
    calib = calibration_from_ndx_constants(constants)
    if background in ("none", "fit") or per_burst_background:
        # Subtracting per burst and zeroing the scalars is *identical* algebra --
        # the background only ever enters as ``counts - background`` -- and it is
        # the only way to carry a per-burst value through a calibration object
        # whose backgrounds are single numbers.
        #
        # Only when there is something to subtract, though: asking for the
        # measured background on a container that never had one would otherwise
        # zero the window's own numbers as well, and subtract nothing in their
        # place -- strictly worse than the setting it replaced.
        calib.bg_dd = calib.bg_da = calib.bg_aa = 0.0

    # ``auto_calibrate`` refines ``calib`` in place, so anything the caller wants
    # kept has to be remembered before the call, not read back after it.
    kept = {name: float(getattr(calib, name)) for name in _FACTOR_NAMES}
    tau_d0 = donor_lifetime
    if tau_d0 is None:
        tau_d0 = float(constants.get("tauD0", 4.0) or 4.0)

    tau_f = pick("tau_f")
    line = None
    if tau_f is not None:
        line = static_fret_line(float(tau_d0), r0=float(calib.r0), sigma=float(linker_sigma))

    def counts(role):
        """That channel's counts, with any per-burst background removed."""
        values = pick(role)
        if values is None:
            return None
        offset = per_burst_background.get(role)
        if offset is None:
            return values
        return np.clip(np.asarray(values, dtype=float) - offset, 0.0, None)

    def calibrate(bootstrap: int):
        return auto_calibrate(
            counts("i_dd"), counts("i_da"), counts("i_aa"), calibration=calib,
            lightpath=lightpath, tau_f=tau_f, line=line,
            donor_lifetime=float(tau_d0), linker_sigma=float(linker_sigma),
            gamma_source=gamma_source, n_bootstrap=bootstrap, use_priors=use_priors,
            progress=(None if progress is None else
                      (lambda step, total, message: progress(step, total, prefix + message))),
        )

    fitted: dict = {}
    prefix = ""
    if background == "fit":
        # Two passes, and they are not the same pass twice. The backgrounds are
        # read off the *reference populations*, so the populations have to exist
        # before they can be estimated -- and once they are subtracted, the
        # classification that found those populations is no longer the one the
        # data supports, so it is made again. The first pass skips the bootstrap:
        # its factors are thrown away, only its split is used.
        prefix = "pass 1 of 2 (backgrounds): "
        first = calibrate(0)
        fitted = fitted_background(
            pick("i_dd"), pick("i_da"), pick("i_aa"), first.split,
            durations=burst_durations_ms(table, "green"),
            min_population=int(min_population),
        )
        # A rate becomes counts through each burst's own duration -- the same
        # conversion the measured route makes, and the reason the fit is worth
        # anything: subtracting one number from every burst is wrong in opposite
        # directions at the two ends of the duration distribution.
        for role, detector in (("i_dd", "green"), ("i_da", "red"), ("i_aa", "yellow")):
            rate = fitted.get(_ROLE_TO_BG.get(role, ""))
            durations = burst_durations_ms(table, detector)
            if rate is None or durations is None:
                continue
            per_burst_background[role] = np.clip(rate * durations, 0.0, None)
        background_rates = dict(fitted)

    prefix = "pass 2 of 2: " if background == "fit" else ""
    result = calibrate(int(n_bootstrap))

    # Restore whatever the caller did not ask to have calibrated, *before* the
    # accurate columns below are computed from ``calib`` — otherwise the columns
    # would be corrected with factors the window is not going to carry.
    selected = _FACTOR_NAMES if factors is None else [
        name for name in _FACTOR_NAMES if name in set(factors)
    ]
    determined = {name: float(getattr(calib, name)) for name in _FACTOR_NAMES}
    for name in _FACTOR_NAMES:
        if name not in selected:
            setattr(calib, name, kept[name])

    injected: list[str] = []
    if inject_columns:
        split = result.split
        labels = np.zeros(np.asarray(counts("i_dd")).shape, dtype=int)
        if split is not None:
            labels = np.where(split.fret, split.fret_labels, -1)
            labels = np.where(split.acceptor_only, -2, labels)
        accurate = accurate_fret(
            counts("i_dd"), counts("i_da"), counts("i_aa"), calibration=calib, tau_f=tau_f,
            line=line, uncertainties=result.uncertainties, labels=labels,
        )
        data_source.set_column("FRET efficiency (accurate)", np.asarray(accurate["E"], dtype=float))
        injected.append("FRET efficiency (accurate)")
        if accurate["S"] is not None:
            data_source.set_column("Stoichiometry (accurate)", np.asarray(accurate["S"], dtype=float))
            injected.append("Stoichiometry (accurate)")
        data_source.set_column("R_DA (accurate)", np.asarray(accurate["distance"], dtype=float))
        injected.append("R_DA (accurate)")
        data_source.set_column("Population", labels.astype(float))
        injected.append("Population")
        if accurate["deviation"] is not None:
            data_source.set_column("Off static FRET line", np.asarray(accurate["deviation"], dtype=float))
            injected.append("Off static FRET line")
        refresh_column_selectors(ndx)

    # The window's Bg/Br/By are **rates** (``Fg = Sg - Bg``, Sg in kHz), while
    # the calibration carried the per-burst counts as zeros because the
    # subtraction happened per burst. Push the rates, so ndX's own equation
    # columns are corrected with the same background the accurate columns were.
    # Neither route did: "fit" wrote a per-burst *count* into a rate constant
    # (a median of 8 photons arriving as 8 kHz, against a real background near
    # 3), and "measurement" wrote the zeros, leaving the equations uncorrected.
    for attribute, value in background_rates.items():
        setattr(calib, attribute, float(value))
    applied = push_calibration_to_ndx(ndx, calib, recompute=recompute)
    return {
        "ok": True,
        "constants": applied,
        "before": {k: constants.get(k) for k in applied},
        "factors": result.factors,
        "uncertainties": result.uncertainties,
        "report": result.report(),
        "columns": mapping,
        "injected": injected,
        "populations": result.populations,
        # What the calibration determined, and which of those were written.
        # A factor the caller held fixed still appears here, so the report can
        # show "gamma would have been 0.91; kept 1.00".
        "determined": determined,
        "applied_factors": list(selected),
        "background": background,
        "background_per_burst": sorted(per_burst_background),
        "background_fitted": fitted,
        "held": {n: kept[n] for n in _FACTOR_NAMES if n not in selected},
    }


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
                per_photon_rate = np.where(raw_count_tot > 0,
                                           raw_rate_tot / raw_count_tot, 0.0)
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
