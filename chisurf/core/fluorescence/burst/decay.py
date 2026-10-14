"""The TCSPC decay of a sub-ensemble of bursts.

Selecting bursts -- by a histogram range, a mixture component, a lifetime gate --
is only half the point; the other half is the decay *of those bursts*, which is
what a lifetime fit then takes. This pools the micro times of the selected
bursts' photons into one histogram and writes it back into the measurement's
container as a ``tcspc_decay`` beside the burst run it was selected from, with
that run recorded as its parent, so ``lineage()`` chains the decay to the
selection to the primary photons.

Photon counts are exact: the histogram sums to the number of photons the stream
assigns inside the selected bursts, which the tests pin.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from chisurf.core.fluorescence.burst.photons import (
    StreamDef,
    extract_burst_photons,
    streams_from_dicts,
)

__all__ = ["DECAY_NAME", "sub_ensemble_decay", "write_sub_ensemble_decay_container"]

#: What the decay is called inside a run.
DECAY_NAME = "sub-ensemble decay"


def _as_stream(stream) -> StreamDef:
    """Accept a :class:`StreamDef`, its dict form, or a plain list of channels."""
    if isinstance(stream, StreamDef):
        return stream
    if isinstance(stream, Mapping):
        return streams_from_dicts([dict(stream)])[0]
    return StreamDef("stream", [int(c) for c in stream], [])


def _micro_time_channels(tttrs: Mapping[str, Any], default: int) -> tuple[int, float]:
    """Return ``(channels, seconds per channel)`` of the first photon stream."""
    for tttr in tttrs.values():
        header = tttr.header
        channels = 0
        resolution = 0.0
        try:
            channels = int(header.number_of_micro_time_channels)
        except Exception:  # noqa: BLE001 - header attributes differ by vendor
            channels = 0
        try:
            resolution = float(header.micro_time_resolution)
        except Exception:  # noqa: BLE001
            resolution = 0.0
        return (channels if channels > 0 else default), (resolution if resolution > 0 else 0.0)
    return default, 0.0


def sub_ensemble_decay(
    run_path,
    stream,
    n_bins: int = 0,
    mask: Sequence[bool] | None = None,
):
    """Return the pooled micro-time histogram of the bursts of a run.

    Parameters
    ----------
    run_path : str or pathlib.Path
        A burst run in a container (``m000.pto/countrate_All 0.1000#60``), or the
        container for its most recent run.
    stream : StreamDef, dict or sequence of int
        Which photons count: a detector category -- routing channels and an
        optional micro-time window. A dict is ``{"channels": [...],
        "micro_time_ranges": [[lo, hi]]}``.
    n_bins : int, optional
        Histogram channels. ``0`` keeps the instrument's own micro-time
        channels; a smaller number sums neighbouring channels (an integer
        rebin: ``channel * n_bins // n_channels``), so no photon is lost.
    mask : sequence of bool, optional
        One entry per burst of the run's table (in order): ``True`` keeps it.
        ``None`` keeps every burst.

    Returns
    -------
    tttrlib.DataStore
        Columns ``Channel``, ``Time (ns)`` (when the resolution is known) and
        ``Counts``; ``Counts`` sums to the number of selected photons.

    Raises
    ------
    ValueError
        If *mask* does not have one entry per burst, or selects no burst.
    FileNotFoundError
        If *run_path* names no burst table.
    """
    import pathlib

    from chisurf.core.datastore import row_count, store_from_arrays
    from chisurf.core.fio.fluorescence.burst import _read_burst_analysis_from_container

    frame, tttrs = _read_burst_analysis_from_container(pathlib.Path(run_path))
    n_bursts = row_count(frame)
    if mask is None:
        keep = np.ones(n_bursts, dtype=bool)
    else:
        keep = np.asarray(mask, dtype=bool)
        if keep.shape != (n_bursts,):
            raise ValueError(f"mask has {keep.size} entries for {n_bursts} bursts")
    if not keep.any():
        raise ValueError("the selection contains no burst")

    _times, _streams, micro, _channel, _index, rows = extract_burst_photons(
        frame,
        tttrs,
        [_as_stream(stream)],
        min_photons=1,
        with_meta=True,
        with_rows=True,
    )
    chosen = [m for m, r in zip(micro, rows) if keep[int(r)]]
    pooled = np.concatenate(chosen) if chosen else np.zeros(0, dtype=np.int64)

    top = int(pooled.max()) + 1 if pooled.size else 1
    n_channels, resolution = _micro_time_channels(tttrs, top)
    n_channels = max(n_channels, top)
    bins = int(n_bins) if int(n_bins) > 0 else n_channels
    bins = min(bins, n_channels)
    index = (pooled.astype(np.int64) * bins) // n_channels
    counts = np.bincount(index, minlength=bins).astype(np.float64)

    columns = {"Channel": np.arange(bins, dtype=np.float64)}
    if resolution > 0:
        # Time of the channel's left edge, in ns, for whichever rebinning.
        columns["Time (ns)"] = (
            np.arange(bins, dtype=np.float64) * (n_channels / bins) * resolution * 1e9
        )
    columns["Counts"] = counts
    return store_from_arrays(columns)


def write_sub_ensemble_decay_container(
    run_path, store, parameters: Mapping[str, Any] | None = None
) -> str:
    """Write a sub-ensemble decay into the container, as a child of its burst run.

    Parameters
    ----------
    run_path : str or pathlib.Path
        The burst run the decay was selected from.
    store : tttrlib.DataStore
        The result of :func:`sub_ensemble_decay`.
    parameters : mapping, optional
        What identifies this selection (stream, bins, the gate). Their hash is
        the run's identity: pass the real selection, or two different selections
        replace each other.

    Returns
    -------
    str
        Path of the container written.
    """
    import pathlib

    from chisurf.core.fio.analysis_path import (
        artifact_name,
        split_artifact_name,
        split_container_path,
    )
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact
    from chisurf.core.fio.pto import Measurement

    container, run = split_container_path(pathlib.Path(run_path))
    if container is None:
        raise FileNotFoundError(f"{run_path} does not name a .pto container")
    parent = ""
    with Measurement.open(container, writable=False) as m:
        for obj in m.artifacts():
            name = str(obj.name)
            if m.tag(obj.uid, "_mmfdb_operation.operation_type") != "burst_selection":
                continue
            if run and split_artifact_name(name)[0] != run:
                continue
            parent = name  # the most recent burst table of the run
    return write_burst_artifact(
        container,
        store,
        name=artifact_name(run, DECAY_NAME),
        deinterleave=False,
        artifact_kind="tcspc_decay",
        operation_type="tcspc_histogram_computation",
        row_grain="histogram_bin",
        parameters=dict(parameters or {}),
        derived_from=[parent] if parent else "bursts",
        units={"Time (ns)": "nanoseconds", "Counts": "counts", "Channel": "dimensionless"},
    )
