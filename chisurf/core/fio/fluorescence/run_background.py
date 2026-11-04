"""The background of a burst run: one rate per detector, stored with the run.

A burst's background is a **rate** (kHz) times that burst's **duration** in the
detector (ms): kHz x ms = photons. So what the pipeline hands on is a rate per
detector of the setup, and it belongs to the run whose bursts it corrects --
the bursts of one search, the time it took outside them, the selection of the
background photons around them.

The record is a table ``<run>/background`` in the measurement's container,
derived from the run's burst table, one row per detector:

========== ===================================================================
Detector   the setup's detector name (``G|G``, ``R|G``, ``R|R``, ``A|A`` ...)
Rate       kHz
Source     ``buffer`` (a buffer measurement of Data Selection), ``strict
           selection`` (the photons the strict background selection kept,
           :func:`~chisurf.core.fluorescence.burst.irf_bg.strict_background_mask`)
           or ``model`` (the flat + scatter model of Burst MLE)
Seconds    the time the rate was measured over (the buffer's, or what the
           strict selection kept)
========== ===================================================================

ndX reads it (``Bg_<detector>``, :mod:`ndxplorer.analysis.fret_background`),
before the container-wide ``background`` table of the Background step (the
inter-photon tail of all photons) and after a buffer rate of the container's
calibration report. Whoever computes a run's background writes it with
:func:`write_run_background`; writing again replaces it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

__all__ = [
    "RUN_BACKGROUND",
    "SOURCES",
    "read_run_background",
    "strict_selection_rates",
    "write_run_background",
    "write_strict_background",
]

#: The table's name inside a run (``<run>/background``).
RUN_BACKGROUND = "background"

#: What a rate can come from, in the order a reader prefers them.
SOURCES = ("buffer", "strict selection", "model")


def _burst_mask(measurement, burst_table: str, n_photons: int) -> np.ndarray:
    """``True`` for every photon inside a burst of *burst_table* (``First``/``Last Photon``)."""
    import tttrlib

    store = tttrlib.deinterleave_burst_rows(measurement.get_store(burst_table))
    names = [store.column(i).name() for i in range(store.n_columns())]
    first = np.asarray(store.column(names.index("First Photon")).numpy(), dtype=np.int64)
    last = np.asarray(store.column(names.index("Last Photon")).numpy(), dtype=np.int64)
    good = (first >= 0) & (last >= first) & (last < n_photons)
    edges = np.zeros(n_photons + 1, dtype=np.int64)
    np.add.at(edges, first[good], 1)
    np.add.at(edges, last[good] + 1, -1)
    return np.cumsum(edges[:-1]) > 0


def strict_selection_rates(
    tttr: Any, burst_mask: np.ndarray, detectors: Mapping[str, Mapping[str, Any]], **strict: Any
) -> tuple[dict[str, float], dict[str, Any]]:
    """Every detector's background rate (kHz) from the strict background selection.

    One selection over the photons of all *detectors* (the bursts widened by their flanks, then
    only the stretches at the background's local count rate,
    :func:`~chisurf.core.fluorescence.burst.irf_bg.strict_background_mask`); a detector's rate is
    its photons in that selection (its channels, inside its gates) over the time kept, corrected
    for the background's own fast stretches the local-rate cut dropped (``rate_scale``) -- as Burst
    MLE takes it.

    Parameters
    ----------
    tttr : tttrlib.TTTR
    burst_mask : ndarray of bool
        ``True`` inside a burst, one per photon.
    detectors : mapping
        ``{name: {"chs": [...], "micro_time_ranges": [...]}}`` with the gates in *tttr*'s
        micro-time channels (``background._applied_detectors``).
    **strict
        Passed to :func:`strict_background_mask`.

    Returns
    -------
    tuple
        ``({detector: kHz}, {"seconds", "total_seconds", "warning", "rate_scale"})``; no rates
        when nothing was kept.
    """
    from tttrlib import micro_time_mask

    from chisurf.core.fluorescence.burst.irf_bg import strict_background_mask
    from chisurf.core.fluorescence.channels import channel_mask

    chs = sorted({int(c) for d in detectors.values() for c in d.get("chs", [])})
    selection = strict_background_mask(tttr, burst_mask, channels=chs or None, **strict)
    info = {
        "seconds": float(selection.seconds),
        "total_seconds": float(selection.total_seconds),
        "warning": str(selection.warning),
        "rate_scale": float(selection.rate_scale),
    }
    if selection.seconds <= 0 or not selection.photons:
        return {}, info
    routing = np.asarray(tttr.routing_channel)
    micro = np.asarray(tttr.micro_times)
    seconds = float(selection.seconds) / float(selection.rate_scale or 1.0)
    rates = {}
    for name, det in detectors.items():
        det_chs = np.asarray(det.get("chs", []), dtype=int)
        if det_chs.size == 0:
            continue
        mine = channel_mask(routing, det_chs) & micro_time_mask(micro, det.get("micro_time_ranges"))
        rates[str(name)] = float(np.count_nonzero(selection.mask & mine)) / seconds / 1e3
    return rates, info


def write_run_background(
    measurement,
    run: str,
    rates: Mapping[str, float],
    sources: Mapping[str, str] | str,
    *,
    seconds: Mapping[str, float] | float | None = None,
    parameters: Mapping[str, Any] | None = None,
) -> int:
    """Write *rates* as ``<run>/background``, derived from the run's burst table; its UID.

    Parameters
    ----------
    measurement : chisurf.core.fio.pto.Measurement
        Open for writing.
    run : str
        The burst run (``m.pto/<run>``).
    rates : mapping
        ``{detector: kHz}``; a rate that is not finite is left out.
    sources : mapping or str
        ``{detector: source}`` (one of :data:`SOURCES`), or one source for all.
    seconds : mapping or float, optional
        The time each rate was measured over.
    parameters : mapping, optional
        The settings of the estimate (its run hash).
    """
    from chisurf.core.datastore import store_from_arrays
    from chisurf.core.fio.analysis_path import artifact_name
    from chisurf.core.fio.fluorescence.burst_container import burst_table_name, units_for

    names = [d for d, v in rates.items() if v is not None and np.isfinite(float(v))]

    def each(value, det, default):
        return value.get(det, default) if isinstance(value, Mapping) else (default if value is None else value)

    table = store_from_arrays(
        {
            "Detector": np.array(names, dtype=object),
            "Rate": np.array([float(rates[d]) for d in names], dtype=float),
            "Source": np.array([str(each(sources, d, "")) for d in names], dtype=object),
            "Seconds": np.array([float(each(seconds, d, np.nan)) for d in names], dtype=float),
        }
    )
    name = artifact_name(run, RUN_BACKGROUND)
    for obj in list(measurement._f.objects()):
        if str(getattr(obj, "name", "")) == name:
            measurement._f.remove(obj.uid)
    parent = burst_table_name(measurement, run)
    parent_uid = measurement._f.find(parent) if parent else 0
    return measurement.put_table(
        name,
        table,
        artifact_kind="background_data",
        operation_type="background_correction",
        row_grain="channel",
        parameters=dict(parameters or {}),
        derived_from=parent_uid or measurement.instrument_uids or measurement.instrument_uid,
        units=units_for(table, {"Rate": "kilohertz", "Seconds": "seconds"}),
    )


def read_run_background(container: str | Path, run: str) -> dict[str, dict[str, Any]]:
    """``{detector: {"rate_khz", "source", "seconds"}}`` of ``<run>/background``; ``{}``: none."""
    import tttrlib

    from chisurf.core.fio.analysis_path import artifact_name
    from chisurf.core.fio.pto import Measurement

    with Measurement.open(container) as m:
        uid = m._f.find(artifact_name(run, RUN_BACKGROUND))
        if not uid:
            return {}
        store = tttrlib.pto_store(m._f, uid)
    names = [store.column(i).name() for i in range(store.n_columns())]

    def column(name):
        return store.column(names.index(name)) if name in names else None

    detectors, rates = column("Detector"), column("Rate")
    source, seconds = column("Source"), column("Seconds")
    out = {}
    for row in range(store.n_rows()):
        out[detectors.string_at(row)] = {
            "rate_khz": float(rates.numpy()[row]),
            "source": source.string_at(row) if source is not None else "",
            "seconds": float(seconds.numpy()[row]) if seconds is not None else float("nan"),
        }
    return out


def write_strict_background(
    measurement, tttr: Any, detectors: Mapping[str, Mapping[str, Any]], *, run: str = "",
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """The strict-selection rates of *run*'s bursts (the newest search when empty), written as
    ``<run>/background``; the rates (``{}``: the container has no burst run, or nothing was
    kept).

    *tttr* is the measurement's photon stream the run's ``First``/``Last Photon`` index, and
    *detectors* the setup's detectors with their gates in its micro-time channels.
    """
    from chisurf.core.fio.analysis_path import split_artifact_name
    from chisurf.core.fio.fluorescence.burst_container import burst_table_name

    table = burst_table_name(measurement, run)
    if not table:
        return {}
    run = split_artifact_name(table)[0]
    mask = _burst_mask(measurement, table, len(tttr))
    rates, info = strict_selection_rates(tttr, mask, detectors)
    if not rates:
        return {}
    write_run_background(
        measurement, run, rates, "strict selection", seconds=info["seconds"],
        parameters={**dict(parameters or {}), "warning": info["warning"]},
    )
    return rates
