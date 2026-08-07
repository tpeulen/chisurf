"""Slice a burst table and its TTTR files into per-burst photon streams.

A burst is stored as a ``.bur`` table row carrying ``First File`` /
``First Photon`` / ``Last Photon`` — integer photon indices into the raw
``tttrlib.TTTR`` object. Turning those rows back into photons, and assigning
each photon to a *stream* from its routing channel and micro-time window, is the
first step of every photon-by-photon analysis: H2MM, the Gopich-Szabo
likelihood, 2CDE, BVA and burst-wise lifetime fitting all start here.

It lives in core rather than in whichever plugin needed it first because the
step is genuinely shared and the alternative — each plugin re-deriving the same
index arithmetic — is how the channel and micro-time conventions drift apart.
What stays in a plugin is only the packing into that engine's own layout.

A *stream* is a detector category (green, red, an ALEX excitation window, a
nanotime slice), defined by :class:`StreamDef`. Photons matching no stream are
dropped, which is how acceptor-after-acceptor-excitation photons are excluded
from a two-colour kinetic fit.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from chisurf.core.datastore import concat_stores, numeric_column, row_count
import tttrlib

__all__ = [
    "PhotonMeta",
    "StreamDef",
    "default_streams",
    "extract_burst_photons",
    "is_sentinel_file_reference",
    "load_bur_dataframe",
    "load_tttrs_for_dataframe",
    "stream_index_arrays",
    "streams_from_dicts",
]


@dataclass
class StreamDef:
    """Definition of one photon stream (a detector category).

    Attributes
    ----------
    name : str
        Human-readable stream name (e.g. ``"green"``, ``"red"``).
    channels : list of int
        TCSPC routing channel numbers assigned to this stream.
    micro_time_ranges : list of tuple[int, int]
        Inclusive micro-time windows (``[]`` accepts any micro time). This is
        how a pulsed-interleaved excitation window is expressed: the same
        detector channel becomes two streams by splitting on nanotime.
    """

    name: str
    channels: list[int]
    micro_time_ranges: list[tuple[int, int]] = field(default_factory=list)


def default_streams() -> list[StreamDef]:
    """Return the canonical 2-colour donor/acceptor stream definition."""
    return [
        StreamDef("green", [0, 8], []),
        StreamDef("red", [1, 9], []),
    ]


def streams_from_dicts(items: Sequence[dict]) -> list[StreamDef]:
    """Build :class:`StreamDef` objects from JSON-compatible dictionaries.

    Parameters
    ----------
    items : sequence of dict
        Each with ``name``, ``channels`` and optional ``micro_time_ranges``.

    Returns
    -------
    list of StreamDef
    """
    out: list[StreamDef] = []
    for it in items:
        ranges = [(int(a), int(b)) for a, b in (it.get("micro_time_ranges") or [])]
        out.append(
            StreamDef(
                name=str(it.get("name", f"stream{len(out)}")),
                channels=[int(c) for c in it.get("channels", [])],
                micro_time_ranges=ranges,
            )
        )
    return out


def stream_index_arrays(
    channels: np.ndarray,
    micro_times: np.ndarray,
    streams: Sequence[StreamDef],
) -> np.ndarray:
    """Map each photon to a stream index (``-1`` where no stream matches).

    Parameters
    ----------
    channels : numpy.ndarray
        Per-photon routing channel.
    micro_times : numpy.ndarray
        Per-photon TCSPC micro time.
    streams : sequence of StreamDef
        Stream definitions; earlier definitions win where they overlap.

    Returns
    -------
    numpy.ndarray
        ``(n_photons,)`` int32 stream index, ``-1`` for unassigned photons.
    """
    idx = np.full(channels.shape[0], -1, dtype=np.int32)
    # Assign in reverse so earlier stream definitions take precedence.
    for s_i in range(len(streams) - 1, -1, -1):
        s = streams[s_i]
        mask = np.isin(channels, np.asarray(s.channels, dtype=channels.dtype))
        if s.micro_time_ranges:
            mt_mask = np.zeros(channels.shape[0], dtype=bool)
            for lo, hi in s.micro_time_ranges:
                mt_mask |= (micro_times >= lo) & (micro_times <= hi)
            mask &= mt_mask
        idx[mask] = s_i
    return idx


@dataclass
class PhotonMeta:
    """Per-photon metadata aligned with the concatenated photon layout.

    Each array has length ``N`` (total analysed photons) in the same photon
    order as the extracted stream arrays, so a decoded state path can be joined
    column-wise to build a per-photon result table.

    Attributes
    ----------
    macro_time : numpy.ndarray
        Per-photon (time-scaled) integer macro time.
    micro_time : numpy.ndarray
        Per-photon TCSPC micro time.
    channel : numpy.ndarray
        Per-photon routing channel.
    burst_id : numpy.ndarray
        Zero-based index of the burst each photon belongs to. A *compacted*
        index over the bursts that survived extraction — not a row in the burst
        table (see ``with_rows``).
    photon_index : numpy.ndarray
        Position of the photon in its measurement's raw TTTR arrays. This is the
        only key that joins an extracted photon back to the file it came from:
        ``burst_id`` counts survivors and the concatenated order counts nothing
        at all, so without it a per-photon result (a Viterbi state, say) cannot
        be handed to any other analysis that slices the raw arrays itself.
    """

    macro_time: np.ndarray
    micro_time: np.ndarray
    channel: np.ndarray
    burst_id: np.ndarray
    photon_index: np.ndarray | None = None


def extract_burst_photons(
    df,
    tttrs: dict[str, tttrlib.TTTR],
    streams: Sequence[StreamDef],
    time_scale: int = 1,
    min_photons: int = 3,
    with_meta: bool = False,
    with_rows: bool = False,
):
    """Slice bursts into per-burst ``(times, stream_index)`` arrays.

    Parameters
    ----------
    df : pandas.DataFrame
        Burst table with ``First File`` / ``First Photon`` / ``Last Photon``.
        ``Last Photon`` is **inclusive**, as written by
        :mod:`chisurf.core.fio.fluorescence.burst`.
    tttrs : dict
        Maps the ``First File`` value to a ``tttrlib.TTTR`` object.
    streams : sequence of StreamDef
        Photon-stream definitions; photons matching no stream are dropped.
    time_scale : int
        Optional integer down-scaling of macro times (coarser base unit).
    min_photons : int
        Bursts with fewer assigned photons than this are skipped.
    with_meta : bool
        Also return per-photon ``(micro_time, channel)`` arrays (same filter and
        order as the stream arrays) for building a per-photon result table.
    with_rows : bool
        Also return the **positions in** ``df`` **of the bursts that survived**.
        Bursts too short, too empty, or from a file that is not loaded are
        skipped here, so the returned lists are a *compacted* sequence and their
        index is not a row index into the burst table. Anything that has to write
        a result back beside the ``.bur`` files — one row per burst, aligned —
        needs this mapping; without it a dropped burst silently shifts every
        later row.

    Returns
    -------
    times : list of numpy.ndarray
        Per-burst monotonically non-decreasing integer macro times.
    stream_idx : list of numpy.ndarray
        Per-burst photon stream indices in ``[0, len(streams))``.
    micro, channel, index : list of numpy.ndarray
        Only when ``with_meta`` — matching per-burst micro-time / channel arrays,
        and the photons' positions in the measurement's raw TTTR arrays.
    rows : numpy.ndarray
        Only when ``with_rows`` — the ``df`` row position of each kept burst.
    """
    # The three columns once, as arrays, rather than a tuple per row: this
    # loop runs over every burst of a measurement.
    files = np.asarray(df["First File"])
    firsts = numeric_column(df, "First Photon")
    lasts = numeric_column(df, "Last Photon")

    cache: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for ff, tttr in tttrs.items():
        cache[ff] = (
            np.asarray(tttr.macro_times),
            np.asarray(tttr.routing_channels),
            np.asarray(tttr.micro_times),
        )

    times_out: list[np.ndarray] = []
    streams_out: list[np.ndarray] = []
    micro_out: list[np.ndarray] = []
    chan_out: list[np.ndarray] = []
    index_out: list[np.ndarray] = []
    rows_out: list[int] = []
    for position in range(row_count(df)):
        ff = files[position]
        if ff not in cache:
            continue
        first = int(firsts[position])
        last = int(lasts[position])
        # ``Last Photon`` is the burst's last photon *inclusive* (that is what
        # the ``.bur`` writer stores: ``Number of Photons == last - first + 1``),
        # so every slice runs to ``last + 1`` and ``last == first`` is a legal
        # one-photon burst rather than an empty one.
        if last < first:
            continue
        macro, chan, micro = cache[ff]

        mt = macro[first : last + 1]
        ch = chan[first : last + 1]
        mi = micro[first : last + 1]

        s_idx = stream_index_arrays(ch, mi, streams)
        keep = s_idx >= 0
        if keep.sum() < min_photons:
            continue

        t = mt[keep].astype(np.int64)
        if time_scale > 1:
            t = t // time_scale
        s = s_idx[keep].astype(np.int32)

        # Enforce monotonicity (macro times are already sorted, but guard).
        order = np.argsort(t, kind="stable")
        times_out.append(t[order])
        streams_out.append(s[order])
        rows_out.append(position)
        if with_meta:
            micro_out.append(mi[keep][order])
            chan_out.append(ch[keep][order])
            # Where these photons sit in the measurement's own arrays: the burst
            # starts at ``first``, ``keep`` selects the stream-assigned ones, and
            # ``order`` is the sort applied above.
            index_out.append((first + np.nonzero(keep)[0][order]).astype(np.int64))

    rows = np.asarray(rows_out, dtype=np.int64)
    if with_meta and with_rows:
        return times_out, streams_out, micro_out, chan_out, index_out, rows
    if with_meta:
        return times_out, streams_out, micro_out, chan_out, index_out
    if with_rows:
        return times_out, streams_out, rows
    return times_out, streams_out


def load_bur_dataframe(paths: Sequence[str | pathlib.Path]):
    """Read and stack one or more ``.bur`` files into one burst table.

    Parameters
    ----------
    paths : sequence of path-like
        ``.bur`` burst tables.

    Returns
    -------
    tttrlib.DataStore
        The rows of every file, stacked. Columns line up by name, so tables
        written by different runs combine even when their column order differs.

    Raises
    ------
    ValueError
        If no paths were given.
    """
    from chisurf.core.fio.fluorescence.burst import read_bur_file

    frames = [read_bur_file(p) for p in paths]
    if not frames:
        raise ValueError("no .bur files provided")
    return concat_stores(frames)


def is_sentinel_file_reference(value: object) -> bool:
    """Return ``True`` for the ``First File`` value of an empty ``.bur`` row.

    A Seidel/PARIS ``.bur`` table is ``2n+1`` interleaved: every other row is an
    all-zero sentinel that :func:`chisurf.core.fio.fluorescence.burst.read_bur_file`
    keeps on purpose, because the ``…4`` companion files align to it by position.
    Those rows carry ``"0"`` (or an empty cell) instead of a measurement name, and
    ``tttrlib`` does *not* raise on the resulting non-existent path — it returns an
    empty object — so a caller that reads the header of "the first file" silently
    reads the header of nothing.

    Parameters
    ----------
    value : object
        A ``First File`` cell.

    Returns
    -------
    bool
    """
    text = str(value).strip()
    return text in {"", "0"} or text.lower() == "nan"


def load_tttrs_for_dataframe(
    df,
    data_dir: str | pathlib.Path,
    file_type: str = "SPC-130",
) -> dict[str, tttrlib.TTTR]:
    """Load the TTTR object referenced by each unique ``First File`` value.

    Sentinel rows (see :func:`is_sentinel_file_reference`) are skipped, so the
    returned mapping contains real measurements only and the *first* entry is a
    real measurement — which is what callers deriving the macro-time resolution
    from a header depend on.

    Parameters
    ----------
    df : pandas.DataFrame
        Burst table with a ``First File`` column.
    data_dir : path-like
        Directory the relative ``First File`` names resolve against.
    file_type : str
        TTTR container type, or ``"auto"`` (the default in spirit) to let the
        library identify it from the file. Names ``tttrlib`` does not accept are
        resolved rather than passed through — see
        :func:`chisurf.core.fio.staging.resolve_container_type`.

    Returns
    -------
    dict
        Maps each ``First File`` value to its loaded ``tttrlib.TTTR``.

    Notes
    -----
    Opens through :func:`chisurf.core.fio.staging.open_tttr`, the single seam that
    stages slow storage and applies the active setup's per-channel TAC-linearization
    LUTs and micro-time shifts. Reading these files with a bare ``tttrlib.TTTR``
    would silently produce *un-linearized* micro times here while every other reader
    in the tree produced linearized ones — a discrepancy that shows up as a lifetime
    shift, not as an error.
    """
    from chisurf.core.fio.staging import open_tttr

    data_dir = pathlib.Path(data_dir)
    tttrs: dict[str, tttrlib.TTTR] = {}
    for ff in df["First File"].unique():
        if ff in tttrs or is_sentinel_file_reference(ff):
            continue
        candidate = pathlib.Path(ff)
        path = candidate if candidate.is_absolute() and candidate.exists() else data_dir / ff
        routine = None if (not file_type or str(file_type).lower() == "auto") else file_type
        tttrs[ff] = open_tttr(path, routine)
    return tttrs
