"""Defined, portable H2MM result tables — openable directly in ndxplorer (ndX).

The analysis produces a Viterbi state per photon; joined with the per-photon
metadata (:class:`~.photons.PhotonMeta`) this becomes a **per-photon table** and,
aggregated, a **per-burst table**. Both are written as plain **numeric** tables
(one row per point) that ndX opens through its generic CSV / MFD-HDF5 readers:

* the time axis is named ``"Mean Macro Time (s)"`` — the column ndX auto-selects
  as an axis;
* ``State`` (the H2MM Viterbi assignment) is an integer column that ndX reads as
  a categorical colour / Z axis;
* everything is numeric, so nothing is dropped on import.

HDF5 is written as one dataset per column at the file root, which is what ndX's
reader takes straight into a store; CSV is a comma-delimited header + numeric
rows.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import numpy as np

from chisurf.core.datastore import column_names, store_from_arrays
from chisurf.core.fio.fluorescence.burst_companion import write_companion

from .h2mm import BurstPhotons
from .photons import PhotonMeta

NDX_HDF5_KEY = "results"


@dataclass
class H2mmTables:
    """The per-photon and per-burst result tables, as columnar stores."""

    photons: object  # tttrlib.DataStore — one row per photon
    bursts: object  # tttrlib.DataStore — one row per burst


def build_tables(
    data: BurstPhotons,
    meta: PhotonMeta,
    path: np.ndarray,
    fret: np.ndarray,
    base_time_s: float,
    *,
    stream_groups=None,
    micro_time_ns: float | None = None,
    burst_sources=None,
) -> H2mmTables:
    """Assemble the per-photon and per-burst ndX tables.

    The per-burst table is written so it opens directly onto ndxplorer's
    static/dynamic **FRET-line** plot (efficiency vs donor micro time): a per-colour
    ``Mean Microtime (<name>)`` column (the mean TCSPC micro time of that stream's
    photons — an IRF-uncorrected donor-lifetime proxy, ndX's FRET-line X axis) plus
    ``FRET efficiency`` / ``Proximity ratio`` (measured apparent E, its Y axis) and
    the H2MM ``Dominant State`` / ``Number of Transitions`` for colouring and
    dynamics.

    Parameters
    ----------
    data : BurstPhotons
        Engine-layout photon data (provides ``streams``/burst offsets).
    meta : PhotonMeta
        Per-photon macro/micro/channel/burst arrays aligned with ``data``.
    path : numpy.ndarray
        Per-photon Viterbi state (length ``N``, from :func:`~.engines.viterbi`).
    fret : numpy.ndarray
        Per-state apparent FRET efficiency (for the model ``Mean FRET E`` column).
    base_time_s : float
        Seconds per base time unit (macro-time → seconds).
    stream_groups : sequence of (str, sequence of int), optional
        Named base-stream roles ``(name, stream_indices)`` in role order — donor
        first, acceptor second, then any acceptor-excitation. Each yields a
        ``Mean Microtime (<name>)`` column; the first two define the measured E /
        proximity ratio. Several indices per role support nanotime divisors.
        Defaults to ``[("green", (0,)), ("red", (1,))]`` limited to what exists.
    micro_time_ns : float, optional
        Nanoseconds per micro-time channel. When given the ``Mean Microtime``
        columns are in ns; otherwise they are ``NaN``.
    burst_sources : array_like, optional
        Source index of each analysed burst — which measurement it came from.
        Written as a per-photon ``Source`` column, because ``Photon`` numbers
        restart in every measurement and are ambiguous without it.

    Returns
    -------
    H2mmTables
        ``photons`` (one row per photon) and ``bursts`` (one row per burst).
    """
    macro_s = meta.macro_time.astype(np.float64) * float(base_time_s)
    photon_columns = {
        "Mean Macro Time (s)": macro_s,  # ndX auto-axis name
        "Macro Time": meta.macro_time,
        "Micro Time": meta.micro_time,
        "Channel": meta.channel,
        "Stream": data.streams.astype(np.int64),
        "State": path.astype(np.int64),
        "Burst": meta.burst_id,
    }
    # Where each photon sits in its measurement's raw arrays. ``Burst`` counts
    # only the bursts that survived extraction, so it cannot take a per-photon
    # result back to the file; this can, which is what lets another analysis
    # (the state-split MLE) slice the same photons this table describes.
    if getattr(meta, "photon_index", None) is not None:
        photon_columns["Photon"] = np.asarray(meta.photon_index, dtype=np.int64)
    if burst_sources is not None:
        # ``Photon`` restarts at 0 in every measurement, so on its own it points
        # at several photons at once. The source index disambiguates it.
        sources = np.asarray(burst_sources, dtype=np.int64)
        ids = np.asarray(meta.burst_id, dtype=np.int64)
        if sources.size and ids.max(initial=-1) < sources.size:
            photon_columns["Source"] = sources[ids]
    photons = store_from_arrays(photon_columns)

    if stream_groups is None:
        stream_groups = [("green", (0,))]
        if int(data.n_streams) > 1:
            stream_groups.append(("red", (1,)))
    groups = [(str(name), np.atleast_1d(np.asarray(idx, dtype=int))) for name, idx in stream_groups]

    # Per-burst aggregation.
    offsets = data.burst_offsets
    n_bursts = data.n_bursts
    n_states = int(fret.shape[0])
    streams_all = np.asarray(data.streams)
    micro_all = np.asarray(meta.micro_time, dtype=np.float64)
    fret_arr = np.asarray(fret, dtype=np.float64)

    cols: dict[str, list] = {"Burst": [], "Number of Photons": [], "Mean Macro Time (s)": []}
    for name, _ in groups:
        cols[f"Mean Microtime ({name})"] = []
    cols["FRET efficiency"] = []
    cols["Proximity ratio"] = []
    cols["Dominant State"] = []
    cols["Number of Transitions"] = []
    cols["Mean FRET E"] = []

    donor_idx = groups[0][1]
    acceptor_idx = groups[1][1] if len(groups) > 1 else np.array([], dtype=int)
    for b in range(n_bursts):
        s = int(offsets[b])
        e = int(offsets[b + 1])
        seg = path[s:e]
        strm = streams_all[s:e]
        micro = micro_all[s:e]
        occ = np.bincount(seg, minlength=n_states).astype(np.float64)

        cols["Burst"].append(b)
        cols["Number of Photons"].append(e - s)
        cols["Mean Macro Time (s)"].append(float(meta.macro_time[s]) * base_time_s)
        for name, idx in groups:
            mask = np.isin(strm, idx)
            if micro_time_ns is not None and mask.any():
                cols[f"Mean Microtime ({name})"].append(
                    float(micro[mask].mean()) * float(micro_time_ns)
                )
            else:
                cols[f"Mean Microtime ({name})"].append(np.nan)
        d = int(np.count_nonzero(np.isin(strm, donor_idx)))
        a = int(np.count_nonzero(np.isin(strm, acceptor_idx)))
        pr = a / (d + a) if (d + a) > 0 else np.nan
        cols["FRET efficiency"].append(pr)  # measured apparent E (uncorrected)
        cols["Proximity ratio"].append(pr)
        cols["Dominant State"].append(int(np.argmax(occ)))
        cols["Number of Transitions"].append(int(np.count_nonzero(np.diff(seg))))
        cols["Mean FRET E"].append(
            float((occ * fret_arr).sum() / occ.sum()) if occ.sum() > 0 else np.nan
        )

    return H2mmTables(photons=photons, bursts=store_from_arrays(cols))


def build_dwell_table(
    data: BurstPhotons,
    meta: PhotonMeta,
    dwells,
    base_time_s: float,
    *,
    stream_groups=None,
    micro_time_ns: float | None = None,
) -> object:
    """Assemble a **per-dwell** ndX table (one row per Viterbi dwell).

    A dwell is a maximal same-state run within a burst — the natural unit for
    dwell-level filtering in ndxplorer (min photons, drop burst-edge dwells,
    select by state/duration). Each row carries the dwell's state, photon count,
    duration, measured E / S, per-colour ``Mean Microtime (<name>)`` (so a per-dwell
    FRET-line plot lands cleanly on the static line, each dwell being a single
    state), an ``Is Edge`` flag (1 if the dwell touches its burst's first or last
    photon) and ``Mean Macro Time (s)`` for the time axis.

    Parameters
    ----------
    data : BurstPhotons
        Engine-layout photon data (burst offsets + per-photon streams).
    meta : PhotonMeta
        Per-photon macro/micro arrays aligned with ``data``.
    dwells : sequence of Dwell
        The analysis dwell records (``H2mmAnalysis.dwells``).
    base_time_s : float
        Seconds per base time unit.
    stream_groups : sequence of (str, sequence of int), optional
        Named base-stream roles (see :func:`build_tables`).
    micro_time_ns : float, optional
        Nanoseconds per micro-time channel for the ``Mean Microtime`` columns.

    Returns
    -------
    tttrlib.DataStore
        One row per dwell.
    """
    if stream_groups is None:
        stream_groups = [("green", (0,))]
        if int(data.n_streams) > 1:
            stream_groups.append(("red", (1,)))
    groups = [(str(name), np.atleast_1d(np.asarray(idx, dtype=int))) for name, idx in stream_groups]

    offsets = np.asarray(data.burst_offsets)
    macro = np.asarray(meta.macro_time, dtype=np.float64)
    micro = np.asarray(meta.micro_time, dtype=np.float64)
    streams_all = np.asarray(data.streams)

    cols: dict[str, list] = {
        "Dwell": [],
        "Burst": [],
        "State": [],
        "Number of Photons": [],
        "Dwell Time (ms)": [],
        "Mean Macro Time (s)": [],
    }
    for name, _ in groups:
        cols[f"Mean Microtime ({name})"] = []
    cols["FRET efficiency"] = []
    cols["Proximity ratio"] = []
    cols["Stoichiometry"] = []
    cols["Is Edge"] = []

    for k, d in enumerate(dwells):
        s0, s1 = int(d.start), int(d.stop)
        burst_start = int(offsets[d.burst])
        burst_end = int(offsets[d.burst + 1])
        cols["Dwell"].append(k)
        cols["Burst"].append(int(d.burst))
        cols["State"].append(int(d.state))
        cols["Number of Photons"].append(int(d.n_photons))
        cols["Dwell Time (ms)"].append(float(d.dur) * base_time_s * 1e3)
        cols["Mean Macro Time (s)"].append(
            float(macro[s0:s1].mean()) * base_time_s if s1 > s0 else np.nan
        )
        for name, idx in groups:
            mask = np.isin(streams_all[s0:s1], idx)
            if micro_time_ns is not None and mask.any():
                cols[f"Mean Microtime ({name})"].append(
                    float(micro[s0:s1][mask].mean()) * float(micro_time_ns)
                )
            else:
                cols[f"Mean Microtime ({name})"].append(np.nan)
        cols["FRET efficiency"].append(float(d.e))
        cols["Proximity ratio"].append(float(d.e))
        cols["Stoichiometry"].append(float(d.s))
        # The dwell record already carries this (it is what the dwell-time
        # histogram filters on); recomputing it here is how the two could come
        # to disagree about which dwells are censored.
        edge = getattr(d, "is_edge", None)
        if edge is None:
            edge = s0 == burst_start or s1 == burst_end
        cols["Is Edge"].append(int(bool(edge)))

    return store_from_arrays(cols)


def write_hdf5(df, path: str | pathlib.Path, key: str = NDX_HDF5_KEY) -> str:
    """Write a table to an ndX-openable HDF5 file, one dataset per column.

    The columns go at the file root, which is the first thing ndX's reader looks
    at -- it takes such a file straight into a store, with no DataFrame in
    between and no second copy of the table at the moment it is largest. It also
    needs no optional HDF5 package, where the frame writer this replaces did.

    Parameters
    ----------
    df : tttrlib.DataStore or mapping of str to array
        The table to write.
    path : str or pathlib.Path
        Target file.
    key : str
        Kept for callers that pass it. The columns are written at the root, so
        a non-default key is a group beside them rather than the table.

    Returns
    -------
    str
        The path written.
    """
    from chisurf.core.datastore import write_table

    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_table(path, df, group="/" if key == NDX_HDF5_KEY else f"/{key}")
    return str(path)


def write_csv(df, path: str | pathlib.Path) -> str:
    """Write a table to an ndX-openable CSV file.

    Comma-delimited, header first, which is the shape ndX's threaded reader
    takes straight into a store.
    """
    from chisurf.core.datastore import write_csv_table

    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv_table(path, df, delimiter=",")
    return str(path)


#: Companion folder/extension for the per-burst H2MM results. Ends in ``4`` so
#: ndX's burst-folder reader discovers it with no code change: it merges
#: ``<ending>/<stem>.<ending>`` beside each ``.bur`` for any sibling directory
#: whose name ends in ``4``, exactly as it already does for ``bv4`` and ``2c4``.
H2MM_COMPANION = "bh4"

#: The columns a ``.bh4`` carries. ``H2MM Fitted`` is 0 for a burst H2MM skipped
#: (too few photons), so "not fitted" is a value rather than an absence.
H2MM_COMPANION_COLUMNS = [
    "H2MM State",
    "H2MM Transitions",
    "H2MM Mean E",
    "H2MM Photons",
    "H2MM Fitted",
]


def write_h2mm_container(
    source,
    burst_df,
    dwell_df=None,
    *,
    parameters: dict | None = None,
) -> str:
    """Write the H2MM result into the measurement's container, at both grains.

    H2MM is the analysis the burst-companion format could not hold, and its own
    docstring says why: ``h2mm_bursts.csv`` is indexed by a *compacted* burst
    number — the bursts H2MM kept — and "one dropped burst shifts every later
    row", so it cannot be joined back to the burst table at all. The `bh4`
    companion exists to work around that, and the dwells, the state decays and
    the state-annotated photons live in four more files outside the format
    because a dwell is not a burst.

    Here a dwell table is simply *finer*: it declares `dwell` grain and carries
    the burst key it already has, so the join is stated rather than counted and
    a compacted index is no longer a problem to be avoided.

    Parameters
    ----------
    source : str or Path
        The instrument file, or the container.
    burst_df : table
        Per-burst H2MM results.
    dwell_df : table, optional
        Per-dwell results from :func:`build_dwell_table`, carrying ``Burst``.
    parameters : dict, optional
        The model settings; their hash is the identity of the run.

    Returns
    -------
    str
        Path of the container written.
    """
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    written = write_burst_artifact(
        source,
        burst_df,
        name="h2mm",
        artifact_kind="burst_table",
        operation_type="photon_hmm",
        row_grain="burst",
        parameters=parameters,
        derived_from="bursts",
    )
    if dwell_df is not None and len(dwell_df):
        write_burst_artifact(
            source,
            dwell_df,
            name="h2mm dwells",
            artifact_kind="dwell_table",
            operation_type="photon_hmm",
            row_grain="dwell",
            parameters=parameters,
            derived_from="h2mm",
            source_row_column="Burst",
            units={
                "Dwell Time (ms)": "milliseconds",
                "Mean Macro Time (s)": "seconds",
                "FRET efficiency": "dimensionless",
                "Proximity ratio": "dimensionless",
                "Number of Photons": "photons",
            },
        )
    return written


def write_burst_companions(
    burst_df,
    burst_rows,
    data: BurstPhotons,
    path: np.ndarray,
    fret: np.ndarray,
    out_root,
) -> list:
    """Write per-measurement H2MM results, one row per burst, ndX-mergeable.

    ``h2mm_bursts.csv`` is one table for the whole folder indexed by a
    *compacted* burst number — the bursts H2MM kept. That cannot be joined back
    to a burst folder: one dropped burst shifts every later row. These companions
    are the shape the folder already speaks: one file per measurement, one row
    per burst **of that measurement**, in the same zero-interleaved layout as
    ``bv4``/``2c4``, with zeros and ``H2MM Fitted = 0`` for a burst that was not
    analysed. ndX merges them beside each ``.bur`` with no change to ndX at all,
    so bursts can be gated by H2MM state.

    Parameters
    ----------
    burst_df : tttrlib.DataStore
        The burst table the analysis was built from (needs ``First File``).
    burst_rows : array_like
        Row position in *burst_df* of each analysed burst, from
        ``extract_burst_photons(..., with_rows=True)``. This is the mapping that
        makes the rows line up.
    data : BurstPhotons
        Engine-layout photons (for the per-burst offsets).
    path : numpy.ndarray
        Per-photon Viterbi state.
    fret : numpy.ndarray
        Per-state apparent FRET efficiency.
    out_root : path-like
        The burst-analysis folder; ``bh4/`` is created inside it.

    Returns
    -------
    list of pathlib.Path
        Every file written — empty when the row mapping is unavailable, which is
        the honest outcome for an analysis that cannot say which burst is which.
    """
    if burst_rows is None or burst_df is None:
        return []
    if "First File" not in column_names(burst_df):
        return []
    rows = np.asarray(burst_rows, dtype=np.int64)
    if rows.size == 0:
        return []

    offsets = np.asarray(data.burst_offsets)
    n_states = int(np.asarray(fret).shape[0])
    fret_arr = np.asarray(fret, dtype=np.float64)

    # Per analysed burst: dominant state, transitions, occupancy-weighted E.
    n_analysed = min(rows.size, len(offsets) - 1)
    dominant = np.zeros(n_analysed, dtype=np.float64)
    transitions = np.zeros(n_analysed, dtype=np.float64)
    mean_e = np.zeros(n_analysed, dtype=np.float64)
    photons = np.zeros(n_analysed, dtype=np.float64)
    for b in range(n_analysed):
        seg = path[int(offsets[b]) : int(offsets[b + 1])]
        if seg.size == 0:
            continue
        occ = np.bincount(seg, minlength=n_states).astype(np.float64)
        dominant[b] = float(np.argmax(occ))
        transitions[b] = float(np.count_nonzero(np.diff(seg)))
        mean_e[b] = float((occ * fret_arr).sum() / occ.sum()) if occ.sum() else np.nan
        photons[b] = float(seg.size)

    files = np.asarray(burst_df["First File"]).astype(str)
    written = []
    for name in dict.fromkeys(files.tolist()):
        # ``.bur`` tables are zero-interleaved, and the loader keeps those
        # padding rows: their "First File" reads as "0". They are not a
        # measurement and must not become a companion file.
        if "." not in name:
            continue
        # Every burst of this measurement, in burst-table order — the row grid
        # the .bur file itself has, so the companion lines up positionally.
        mine = np.flatnonzero(files == name)
        table = np.zeros((mine.size, len(H2MM_COMPANION_COLUMNS)), dtype=float)
        where = {int(r): i for i, r in enumerate(rows[:n_analysed])}
        for local, global_row in enumerate(mine):
            b = where.get(int(global_row))
            if b is None:
                continue  # not analysed: zeros, and Fitted stays 0
            table[local] = (
                dominant[b],
                transitions[b],
                0.0 if np.isnan(mean_e[b]) else mean_e[b],
                photons[b],
                1.0,
            )

        written.append(
            write_companion(
                out_root,
                H2MM_COMPANION,
                pathlib.Path(str(name)).stem,
                H2MM_COMPANION_COLUMNS,
                table,
            )
        )
    return written
