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

HDF5 is written with pandas ``HDFStore`` under key ``"results"`` (the key ndX's
reader looks for first); CSV is a comma-delimited header + numeric rows.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import numpy as np

from .h2mm import BurstPhotons
from .photons import PhotonMeta

NDX_HDF5_KEY = "results"


@dataclass
class H2mmTables:
    """The per-photon and per-burst result tables (as pandas DataFrames)."""

    photons: object  # pandas.DataFrame — one row per photon
    bursts: object   # pandas.DataFrame — one row per burst


def build_tables(
    data: BurstPhotons,
    meta: PhotonMeta,
    path: np.ndarray,
    fret: np.ndarray,
    base_time_s: float,
    *,
    stream_groups=None,
    micro_time_ns: float | None = None,
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
        Per-photon Viterbi state (length ``N``, from :func:`~.h2mm.viterbi`).
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

    Returns
    -------
    H2mmTables
        ``photons`` (one row per photon) and ``bursts`` (one row per burst).
    """
    import pandas as pd

    macro_s = meta.macro_time.astype(np.float64) * float(base_time_s)
    photons = pd.DataFrame(
        {
            "Mean Macro Time (s)": macro_s,   # ndX auto-axis name
            "Macro Time": meta.macro_time,
            "Micro Time": meta.micro_time,
            "Channel": meta.channel,
            "Stream": data.streams.astype(np.int64),
            "State": path.astype(np.int64),
            "Burst": meta.burst_id,
        }
    )

    if stream_groups is None:
        stream_groups = [("green", (0,))]
        if int(data.n_streams) > 1:
            stream_groups.append(("red", (1,)))
    groups = [(str(name), np.atleast_1d(np.asarray(idx, dtype=int)))
              for name, idx in stream_groups]

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
                    float(micro[mask].mean()) * float(micro_time_ns))
            else:
                cols[f"Mean Microtime ({name})"].append(np.nan)
        d = int(np.count_nonzero(np.isin(strm, donor_idx)))
        a = int(np.count_nonzero(np.isin(strm, acceptor_idx)))
        pr = a / (d + a) if (d + a) > 0 else np.nan
        cols["FRET efficiency"].append(pr)   # measured apparent E (uncorrected)
        cols["Proximity ratio"].append(pr)
        cols["Dominant State"].append(int(np.argmax(occ)))
        cols["Number of Transitions"].append(int(np.count_nonzero(np.diff(seg))))
        cols["Mean FRET E"].append(
            float((occ * fret_arr).sum() / occ.sum()) if occ.sum() > 0 else np.nan)

    bursts = pd.DataFrame(cols)
    return H2mmTables(photons=photons, bursts=bursts)


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
    pandas.DataFrame
        One row per dwell.
    """
    import pandas as pd

    if stream_groups is None:
        stream_groups = [("green", (0,))]
        if int(data.n_streams) > 1:
            stream_groups.append(("red", (1,)))
    groups = [(str(name), np.atleast_1d(np.asarray(idx, dtype=int)))
              for name, idx in stream_groups]

    offsets = np.asarray(data.burst_offsets)
    macro = np.asarray(meta.macro_time, dtype=np.float64)
    micro = np.asarray(meta.micro_time, dtype=np.float64)
    streams_all = np.asarray(data.streams)

    cols: dict[str, list] = {
        "Dwell": [], "Burst": [], "State": [], "Number of Photons": [],
        "Dwell Time (ms)": [], "Mean Macro Time (s)": [],
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
            float(macro[s0:s1].mean()) * base_time_s if s1 > s0 else np.nan)
        for name, idx in groups:
            mask = np.isin(streams_all[s0:s1], idx)
            if micro_time_ns is not None and mask.any():
                cols[f"Mean Microtime ({name})"].append(
                    float(micro[s0:s1][mask].mean()) * float(micro_time_ns))
            else:
                cols[f"Mean Microtime ({name})"].append(np.nan)
        cols["FRET efficiency"].append(float(d.e))
        cols["Proximity ratio"].append(float(d.e))
        cols["Stoichiometry"].append(float(d.s))
        cols["Is Edge"].append(int(s0 == burst_start or s1 == burst_end))

    return pd.DataFrame(cols)


def write_hdf5(df, path: str | pathlib.Path, key: str = NDX_HDF5_KEY) -> str:
    """Write a table to an ndX-openable HDF5 file (``key='results'``)."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_hdf(str(path), key=key, format="table", mode="w")
    return str(path)


def write_csv(df, path: str | pathlib.Path) -> str:
    """Write a table to an ndX-openable CSV file."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(str(path), index=False)
    return str(path)
