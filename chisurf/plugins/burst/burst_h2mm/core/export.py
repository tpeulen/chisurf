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
    donor_streams=(0,),
    acceptor_streams=(1,),
    micro_time_ns: float | None = None,
) -> H2mmTables:
    """Assemble the per-photon and per-burst ndX tables.

    The per-burst table uses the MFD column names ndxplorer recognises so it opens
    directly onto ndX's static/dynamic **FRET-line** plot (E vs donor lifetime):
    ``Tau (green)`` (donor lifetime, its default X axis), ``Proximity ratio`` (its
    default Y axis) and ``FRET efficiency`` — plus the H2MM ``Dominant State`` /
    ``Number of Transitions`` for colouring and dynamics.

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
    donor_streams, acceptor_streams : sequence of int
        Stream indices of the donor / acceptor role (several each with nanotime
        divisors); used for the measured per-burst E and donor lifetime.
    micro_time_ns : float, optional
        Nanoseconds per micro-time channel. When given, ``Tau (green)`` is the
        per-burst mean donor micro time in ns (an IRF-uncorrected lifetime proxy);
        otherwise that column is ``NaN``.

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

    # Per-burst aggregation.
    offsets = data.burst_offsets
    n_bursts = data.n_bursts
    n_states = int(fret.shape[0])
    streams_all = np.asarray(data.streams)
    micro_all = np.asarray(meta.micro_time, dtype=np.float64)
    donor_streams = np.atleast_1d(np.asarray(donor_streams, dtype=int))
    acceptor_streams = np.atleast_1d(np.asarray(acceptor_streams, dtype=int))
    rows = []
    fret_arr = np.asarray(fret, dtype=np.float64)
    for b in range(n_bursts):
        s = int(offsets[b])
        e = int(offsets[b + 1])
        seg = path[s:e]
        occ = np.bincount(seg, minlength=n_states).astype(np.float64)
        dominant = int(np.argmax(occ))
        n_trans = int(np.count_nonzero(np.diff(seg)))
        mean_e = float((occ * fret_arr).sum() / occ.sum()) if occ.sum() > 0 else np.nan
        t0 = float(meta.macro_time[s]) * base_time_s

        strm = streams_all[s:e]
        donor_mask = np.isin(strm, donor_streams)
        d = int(np.count_nonzero(donor_mask))
        a = int(np.count_nonzero(np.isin(strm, acceptor_streams)))
        pr = a / (d + a) if (d + a) > 0 else np.nan
        if micro_time_ns is not None and d > 0:
            tau_green = float(micro_all[s:e][donor_mask].mean()) * float(micro_time_ns)
        else:
            tau_green = np.nan
        rows.append((b, e - s, t0, tau_green, pr, pr, dominant, n_trans, mean_e))
    bursts = pd.DataFrame(
        rows,
        columns=[
            "Burst",
            "Number of Photons",     # ndX auto-uses this as a histogram weight
            "Mean Macro Time (s)",
            "Tau (green)",           # ndX FRET-line default X axis (donor lifetime, ns)
            "FRET efficiency",       # measured apparent E (uncorrected)
            "Proximity ratio",       # ndX FRET-line default Y axis (= apparent E here)
            "Dominant State",
            "Number of Transitions",
            "Mean FRET E",           # model-derived per-state mean (Viterbi-weighted)
        ],
    )
    return H2mmTables(photons=photons, bursts=bursts)


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
