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
import pandas as pd
import tttrlib

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
    df: pd.DataFrame,
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
    df : pandas.DataFrame
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
    if need_meta:
        times, stream_idx, micro, chan = extract_burst_photons(
            df, tttrs, streams, time_scale=time_scale,
            min_photons=min_photons, with_meta=True,
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
    )
    return data, meta
