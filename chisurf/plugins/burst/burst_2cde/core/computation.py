"""FRET-2CDE / ALEX-2CDE computation functions.

2CDE (Tomov et al., Biophys. J. 2012) is a per-burst *feature* that flags
within-burst dynamics from per-photon kernel-density estimates of two photon
streams.  The heavy lifting is done by the tttrlib ``TwoCDE`` burst feature
(parallel, bit-exact port of the FRETBursts reference); a pure-NumPy fallback
reproduces the same reference when that class is unavailable.
"""

from __future__ import annotations

import pathlib

import numpy as np

from chisurf.core.datastore import numeric_column, row_count

try:
    from chisurf import logging
except ImportError:  # pragma: no cover - standalone use
    import logging

import tttrlib

# Column names written into the burst dataframe.
COLUMN_FRET_2CDE = "FRET-2CDE"
COLUMN_ALEX_2CDE = "ALEX-2CDE"


def column_for_variant(variant: str) -> str:
    """Return the dataframe column a 2CDE *variant* is written to.

    A computed frame carries **only** the column of the variant it was computed
    for, so every consumer has to derive the name from the variant that ran —
    never from a live control that may have moved since. One mapping, so the
    core, the service, the CLI and the GUI cannot drift apart.

    Parameters
    ----------
    variant : str
        ``"fret"`` (FRET-2CDE) or ``"alex"`` (ALEX-2CDE).

    Returns
    -------
    str
        ``COLUMN_ALEX_2CDE`` for ``"alex"``, ``COLUMN_FRET_2CDE`` otherwise.
    """
    return COLUMN_ALEX_2CDE if variant == "alex" else COLUMN_FRET_2CDE


# The burst-analysis reader is shared with the BVA plugin (identical file
# layout: First File / First Photon / Last Photon columns).


def _to_pairs(ranges) -> list[tuple[int, int]]:
    return [(int(a), int(b)) for a, b in ranges]


def compute_2cde(
    df,
    tttrs: dict[str, tttrlib.TTTR],
    donor_channels: list[int] = (0, 8),
    donor_micro_time_ranges: list[tuple[int, int]] = ((0, 32768),),
    acceptor_channels: list[int] = (1, 9),
    acceptor_micro_time_ranges: list[tuple[int, int]] = ((0, 32768),),
    tau: float = 100e-6,
    kernel: str = "laplace",
    variant: str = "fret",
    acceptor_excitation_channels: list[int] | None = None,
    acceptor_excitation_micro_time_ranges: list[tuple[int, int]] | None = None,
    progress_window=None,
):
    """Compute the per-burst 2CDE feature and add it as a dataframe column.

    Parameters
    ----------
    df : pandas.DataFrame
        Burst table with ``First File`` / ``First Photon`` / ``Last Photon``.
    tttrs : dict
        Mapping of ``First File`` value to its :class:`tttrlib.TTTR`.
    donor_channels, acceptor_channels : list of int
        Routing channels for the donor / acceptor streams.  For ``variant ==
        "alex"`` these are the donor-excitation and acceptor-excitation streams.
    donor_micro_time_ranges, acceptor_micro_time_ranges : list of (int, int)
        Inclusive micro-time windows per stream.
    tau : float
        Kernel time constant in seconds.
    kernel : str
        ``"laplace"`` (Tomov original) or ``"gaussian"`` (smooth variant).
    variant : str
        ``"fret"`` (FRET-2CDE) or ``"alex"`` (ALEX-2CDE).
    acceptor_excitation_channels, acceptor_excitation_micro_time_ranges
        Explicit ALEX acceptor-excitation stream; when ``None`` the
        ``acceptor_*`` arguments are reused (FRET naming).
    progress_window : object, optional
        Object with ``set_value`` for progress reporting.

    Returns
    -------
    pandas.DataFrame
        ``df`` with a ``FRET-2CDE`` or ``ALEX-2CDE`` column added.
    """
    column = column_for_variant(variant)
    n = row_count(df)
    values = np.full(n, np.nan)

    # The three columns once, as arrays, rather than a tuple per burst.
    files = np.asarray(df["First File"])
    firsts = numeric_column(df, "First Photon")
    lasts = numeric_column(df, "Last Photon")

    per_file: dict[str, tuple[list[int], list[tuple[int, int]]]] = {}
    for i in range(n):
        ff = files[i]
        if ff not in tttrs:
            continue
        rows_idx, bursts = per_file.setdefault(ff, ([], []))
        rows_idx.append(i)
        bursts.append((int(firsts[i]), int(lasts[i])))

    a_ex_ch = (
        acceptor_channels if acceptor_excitation_channels is None else acceptor_excitation_channels
    )
    a_ex_mtr = (
        acceptor_micro_time_ranges
        if acceptor_excitation_micro_time_ranges is None
        else acceptor_excitation_micro_time_ranges
    )

    if not hasattr(tttrlib, "TwoCDE"):
        raise RuntimeError(
            "2CDE needs tttrlib's TwoCDE engine, which this build does not "
            "have. The in-tree NumPy path that used to stand in for it was "
            "removed: it silently ignored the kernel argument for ALEX-2CDE "
            "(always Laplace), so it answered a different question than the "
            "one asked. Rebuild tttrlib."
        )
    done = 0
    for ff, (rows_idx, bursts) in per_file.items():
        tttr = tttrs[ff]
        burst_pairs = np.asarray(bursts, dtype=np.int64).reshape(-1, 2)
        vals = _compute_file_cpp(
            tttr,
            burst_pairs,
            tau,
            kernel,
            variant,
            donor_channels,
            donor_micro_time_ranges,
            acceptor_channels,
            acceptor_micro_time_ranges,
            a_ex_ch,
            a_ex_mtr,
        )
        for k, ri in enumerate(rows_idx):
            values[ri] = vals[k]
        done += len(rows_idx)
        if progress_window:
            progress_window.set_value(done)

    df[column] = values
    return df


def _compute_file_cpp(
    tttr,
    burst_pairs,
    tau,
    kernel,
    variant,
    d_ch,
    d_mtr,
    a_ch,
    a_mtr,
    aex_ch,
    aex_mtr,
) -> np.ndarray:
    """Fast path: tttrlib.TwoCDE burst feature (parallel over bursts)."""
    eng = tttrlib.TwoCDE(tttr)
    k = tttrlib.TwoCDE.GAUSSIAN if kernel == "gaussian" else tttrlib.TwoCDE.LAPLACE
    if variant == "alex":
        eng.set_donor_excitation(list(d_ch), _to_pairs(d_mtr))
        eng.set_acceptor_excitation(list(aex_ch), _to_pairs(aex_mtr))
        eng.compute(burst_pairs, float(tau), tttrlib.TwoCDE.ALEX_2CDE, k)
    else:
        eng.set_donor(list(d_ch), _to_pairs(d_mtr))
        eng.set_acceptor(list(a_ch), _to_pairs(a_mtr))
        eng.compute(burst_pairs, float(tau), tttrlib.TwoCDE.FRET_2CDE, k)
    return np.asarray(eng.two_cde)


def write_2cde_container(
    df,
    variant: str = "fret",
    *,
    parameters: dict | None = None,
    progress_window=None,
) -> list[str]:
    """Write the 2CDE result into each measurement's own container.

    One row per burst, joined to the burst table by declared key. The `2n+1`
    grid and the nameless trailing column the `.2c4` needed are not reproduced:
    they exist so a positional merge has something to count against, and nothing
    here counts.

    Parameters
    ----------
    df : pandas.DataFrame
        Computed 2CDE values, carrying ``First File`` per row.
    variant : str
        ``"fret"`` or ``"alex"``. Decides the column, and is part of the run's
        settings, so recomputing the other variant adds an artifact rather than
        overwriting this one.
    parameters : dict, optional
        The analysis settings, which used to be dropped into the companion
        directory as ``2cde_settings.json`` and then skipped on purpose by every
        reader of that directory.
    progress_window : optional
        Anything with ``set_value``.

    Returns
    -------
    list of str
        The containers written.
    """
    from chisurf.core.fio.fluorescence.burst_container import write_per_source

    column = column_for_variant(variant)
    settings = {"variant": variant, **(parameters or {})}
    written = write_per_source(
        df[["First File", column]],
        name=f"2cde {variant}",
        artifact_kind="burst_table",
        operation_type="burst_2cde",
        row_grain="burst",
        parameters=settings,
        derived_from="bursts",
        units={column: "dimensionless"},
    )
    if progress_window:
        progress_window.set_value(len(written))
    logging.info("2CDE (%s) written to %d container(s)", variant, len(written))
    return written


def write_2cde_analysis(
    df, analysis_folder: str, variant: str = "fret", progress_window=None
) -> None:
    """Write per-burst 2CDE values to companion files under a ``2c4/`` subfolder.

    One tab-separated file per source TTTR named after the ``.bur`` stem
    (``<stem>.2c4``), part of the ``…4`` burst-companion family (``bg4`` / ``bv4``
    / ``2c4`` …). Per-stem consumers — ndX and the burst browser — join it
    to the burst table by stem, so it must match the ``.bur`` name (no ``_0``).
    """
    from chisurf.core.fio.fluorescence.burst_companion import write_companion

    column = column_for_variant(variant)
    files = np.asarray(df["First File"])
    values = numeric_column(df, column)
    # write_companion owns the layout -- the "…4" directory, the %.6f, and the
    # zero interleaving. This used to build all three by hand, one measurement
    # at a time, which is how a companion drifts from the contract that merges
    # it.
    for i, tttr_file in enumerate(dict.fromkeys(files), start=1):
        stem = pathlib.Path(str(tttr_file)).stem
        rows = values[files == tttr_file].reshape(-1, 1)
        write_companion(analysis_folder, "2c4", stem, [column], rows)
        if progress_window:
            progress_window.set_value(i)
    logging.info("2CDE results written beside %s", analysis_folder)
