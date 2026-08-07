"""Pack burst photons into the layout the H2MM engine consumes.

The generic work — slicing a ``.bur`` table against its TTTR files and mapping
each photon to a stream — lives in
:mod:`chisurf.core.fluorescence.burst.photons` and is shared with every other
photon-by-photon analysis. What remains here is H2MM's own: building a
:class:`~.h2mm.BurstPhotons`, and the *divisor* scheme that splits each base
stream into equal-occupancy nanotime bins so lifetime information enters a model
that otherwise sees only colour.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import tttrlib

from chisurf.core.datastore import store_from_rows
from chisurf.core.fluorescence.burst.photons import (
    PhotonMeta,
    StreamDef,
    default_streams,
    extract_burst_photons,
    load_bur_dataframe,
    load_tttrs_for_dataframe,
    stream_index_arrays,
    streams_from_dicts,
)

from .h2mm import prepare_bursts

__all__ = [
    "PhotonMeta",
    "StreamDef",
    "bursts_from_dataframe",
    "default_streams",
    "extract_burst_photons",
    "load_bur_dataframe",
    "load_tttrs_for_dataframe",
    "pack_simulated_bursts",
    "stream_index_arrays",
    "streams_from_dicts",
]


def _divisor_edges(micro_all: np.ndarray, base_all: np.ndarray, n_base: int, divisors: int):
    """Per-base-stream micro-time quantile edges for ``divisors`` bins.

    Returns a list (one entry per base stream) of the interior bin edges, so a
    photon's nanotime bin is ``searchsorted(edges[base], micro)``. Quantiles give
    ≈equal-occupancy bins, which is the robust default for splitting a stream by
    fluorescence lifetime.
    """
    qs = np.linspace(0.0, 1.0, divisors + 1)[1:-1]  # interior quantiles
    edges: list[np.ndarray] = []
    for b in range(n_base):
        m = micro_all[base_all == b]
        edges.append(np.quantile(m, qs) if m.size else np.zeros(qs.shape))
    return edges


def _apply_divisors(stream_idx, micro, n_base: int, divisors: int):
    """Split per-burst base streams into ``divisors`` nanotime bins each.

    The expanded stream index is ``base * divisors + bin`` (contiguous blocks per
    base stream), so a caller can recover the base role as ``index // divisors``.
    """
    base_all = np.concatenate(stream_idx) if stream_idx else np.array([], dtype=np.int32)
    micro_all = np.concatenate(micro) if micro else np.array([], dtype=np.int64)
    edges = _divisor_edges(micro_all, base_all, n_base, divisors)
    out: list[np.ndarray] = []
    for base_b, micro_b in zip(stream_idx, micro):
        new = np.empty_like(base_b)
        for b in range(n_base):
            mask = base_b == b
            if mask.any():
                bins = np.searchsorted(edges[b], micro_b[mask], side="right")
                new[mask] = (b * divisors + bins).astype(new.dtype)
        out.append(new)
    return out


def bursts_from_dataframe(
    df,
    tttrs: dict[str, tttrlib.TTTR],
    streams: Sequence[StreamDef],
    time_scale: int = 1,
    min_photons: int = 3,
    return_meta: bool = False,
    divisors: int = 1,
):
    """Return engine-ready :class:`~.h2mm.BurstPhotons` from a burst DataFrame.

    With ``return_meta`` also returns a
    :class:`~chisurf.core.fluorescence.burst.photons.PhotonMeta` whose arrays
    align photon-for-photon with ``BurstPhotons.streams`` (for the per-photon
    result table). With ``divisors > 1`` each of the ``len(streams)`` base
    streams is split into ``divisors`` micro-time (nanotime) bins, giving
    ``len(streams) * divisors`` streams laid out as contiguous per-base blocks
    (so ``stream_index // divisors`` recovers the base stream).

    Parameters
    ----------
    df : tttrlib.DataStore, pandas.DataFrame or mapping of str to array
        Burst table with ``First File`` / ``First Photon`` / ``Last Photon``.
    tttrs : dict
        Maps the ``First File`` value to a ``tttrlib.TTTR`` object.
    streams : sequence of StreamDef
        Base photon-stream definitions.
    time_scale : int
        Optional integer down-scaling of macro times.
    min_photons : int
        Bursts with fewer assigned photons than this are skipped.
    return_meta : bool
        Also return the aligned per-photon metadata.
    divisors : int
        Nanotime bins per base stream.

    Returns
    -------
    BurstPhotons, or (BurstPhotons, PhotonMeta) when ``return_meta``.

    Raises
    ------
    ValueError
        If no burst has enough stream-assigned photons.
    """
    divisors = max(int(divisors), 1)
    need_meta = return_meta or divisors > 1
    rows = None
    if need_meta:
        times, stream_idx, micro, chan, index, rows = extract_burst_photons(
            df, tttrs, streams, time_scale=time_scale,
            min_photons=min_photons, with_meta=True, with_rows=True,
        )
    else:
        times, stream_idx = extract_burst_photons(
            df, tttrs, streams, time_scale=time_scale, min_photons=min_photons
        )
    if not times:
        raise ValueError("no bursts with enough stream-assigned photons")
    n_streams = len(streams)
    if divisors > 1:
        stream_idx = _apply_divisors(stream_idx, micro, len(streams), divisors)
        n_streams = len(streams) * divisors
    data = prepare_bursts(times, stream_idx, n_streams=n_streams)
    if not return_meta:
        return data
    meta = PhotonMeta(
        macro_time=np.concatenate(times).astype(np.int64),
        micro_time=np.concatenate(micro).astype(np.int64),
        channel=np.concatenate(chan).astype(np.int64),
        burst_id=np.concatenate(
            [np.full(t.shape[0], b, dtype=np.int64) for b, t in enumerate(times)]
        ),
        photon_index=np.concatenate(index).astype(np.int64) if index else None,
    )
    # Which burst-table row each kept burst came from. Bursts below
    # ``min_photons`` are skipped, so the burst index is a compacted sequence;
    # anything writing one row per burst back beside the ``.bur`` files needs
    # this to stay aligned.
    meta.burst_rows = rows
    return data, meta


def pack_simulated_bursts(times, streams, *, filename="sim.spc", gap=100_000):
    """Pack simulated per-burst photon streams into a TTTR and a burst table.

    Simulated bursts arrive as one array of macro times and one of stream labels
    per burst; every consumer of them needs the same three things — the bursts
    laid end to end on a common clock, a real ``tttrlib.TTTR`` holding them, and a
    burst table naming the span of each.

    That packing was written out at seven call sites and **they disagreed**. Five
    recorded the last photon as ``offset + len(burst)`` and two as
    ``offset + len(burst) - 1``. ``Last Photon`` is *inclusive* — the ``.bur``
    writer stores it so that ``photons == last - first + 1``, and
    :func:`bursts_from_dataframe` slices to ``last + 1`` — so the first spelling
    hands every burst the **first photon of the next one**. Nothing failed,
    because the extra photon is a single sample among dozens and the tests that
    used it asserted on fitted parameters rather than on counts.

    Parameters
    ----------
    times : sequence of array_like
        Macro times per burst, each starting near zero.
    streams : sequence of array_like
        Stream index per photon, aligned with *times*.
    filename : str
        Value written into the ``First File`` column; the key a reader uses to
        find the TTTR.
    gap : int
        Macro-time gap inserted between bursts, so a burst search or a dwell
        analysis cannot join two of them.

    Returns
    -------
    tttr, table : tttrlib.TTTR, tttrlib.DataStore
        The photons, and the burst table addressing them.
    """
    import tttrlib

    macro_parts, channel_parts, rows = [], [], []
    offset, base = 0, 0
    for burst_times, burst_streams in zip(times, streams):
        t = np.asarray(burst_times, dtype=np.int64)
        macro_parts.append((t + base).astype(np.uint64))
        channel_parts.append(np.asarray(burst_streams).astype(np.int8))
        # Inclusive, matching the .bur writer and bursts_from_dataframe.
        rows.append((filename, offset, offset + t.size - 1))
        offset += t.size
        base += int(t[-1]) + int(gap)

    macro = np.concatenate(macro_parts).astype(np.uint64)
    channel = np.concatenate(channel_parts).astype(np.int8)
    micro = np.zeros(macro.size, dtype=np.uint16)
    event = np.zeros(macro.size, dtype=np.int8)

    tttr = tttrlib.TTTR()
    tttr.append_events(macro, micro, channel, event, False, 0)
    table = store_from_rows(
        [dict(zip(("First File", "First Photon", "Last Photon"), r)) for r in rows],
        columns=["First File", "First Photon", "Last Photon"],
    )
    return tttr, table
