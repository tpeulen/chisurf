"""Burst table → the three histograms the ALEX Suite plots and exports.

The old ALEX-Suite kept the E histogram, the S histogram and the 2-D E–S map on
its ``EvsS`` data container, recomputing all three whenever a threshold or a
correction factor changed. Here they are one pure function over a burst table, so
the titration analysis, the legacy CSV export and any headless script get the
same numbers as the interactive ndX view.

Qt-free; the channel columns are recognised with the shared conventions in
:mod:`chisurf.core.fluorescence.burst.table` and the corrections applied with
:func:`chisurf.core.fluorescence.burst.es.corrected_es`, so nothing about the
correction algebra is re-implemented here.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

import numpy as np

from chisurf.core.fluorescence.burst.es import corrected_es
from chisurf.core.fluorescence.burst.table import guess_columns, read_burst_table

__all__ = [
    "Corrections",
    "Thresholds",
    "EsHistograms",
    "burst_efficiency_stoichiometry",
    "es_histograms",
    "load_channels",
]


@dataclass(frozen=True)
class Corrections:
    """The correction factors, in the ALEX-Suite panel's own order.

    Attributes
    ----------
    bg_dd, bg_da, bg_aa : float
        Per-channel background **in counts per millisecond** — the unit the old
        *Accurate FRET* panel used. They are multiplied by each burst's duration
        before subtraction, so the burst duration column has to be present for a
        non-zero background to be applied.
    alpha : float
        Donor leakage into the acceptor channel. ALEX-Suite asked for the
        donor-only peak *position* (``E_donly``) instead; derive the factor
        with :func:`chisurf.core.fluorescence.fret.calibration.leakage_from_donor_only`,
        or let the Accurate FRET step find it — there is one implementation of
        each correction factor and it is not here.
    delta : float
        Direct acceptor excitation (ALEX-Suite's ``S_aonly``); see
        :func:`~chisurf.core.fluorescence.fret.calibration.direct_excitation_from_acceptor_only`.
    gamma, beta : float
        Detection/quantum-yield ratio and excitation-flux ratio.
    """

    bg_dd: float = 0.0
    bg_da: float = 0.0
    bg_aa: float = 0.0
    alpha: float = 0.0
    delta: float = 0.0
    gamma: float = 1.0
    beta: float = 1.0


@dataclass(frozen=True)
class Thresholds:
    """The burst filters of the old *Thresholds* panel.

    ``s_range_for_e`` and ``e_range_for_s`` are the gates that make the 1-D
    projections meaningful: the E histogram is built only from bursts inside a
    stoichiometry band (so donor-only and acceptor-only species do not leak into
    it), and the S histogram only from bursts inside an efficiency band.
    """

    total_min: float = 0.0
    total_max: float = float("inf")
    duration_min_ms: float = 0.0
    duration_max_ms: float = float("inf")
    e_range: tuple[float, float] = (-10.0, 11.0)
    s_range: tuple[float, float] = (-10.0, 11.0)
    s_range_for_e: tuple[float, float] = (0.3, 0.8)
    e_range_for_s: tuple[float, float] = (0.0, 1.0)


@dataclass
class EsHistograms:
    """The three histograms of one burst set.

    Attributes
    ----------
    e_centres, s_centres : ndarray
        Bin centres of the efficiency and stoichiometry axes.
    e_hist, s_hist : ndarray
        1-D projections, each built only from the bursts inside the *other*
        axis's gate (see :class:`Thresholds`).
    hist_2d : ndarray
        The 2-D map, shaped ``(len(s_centres), len(e_centres))`` — S down, E
        across, the orientation the old program plotted and exported.
    e, s : ndarray
        The per-burst efficiency and stoichiometry that survived the filters.
    n_bursts_total : int
        Bursts before filtering, so a panel can report how many were cut.
    """

    e_centres: np.ndarray
    s_centres: np.ndarray
    e_hist: np.ndarray
    s_hist: np.ndarray
    hist_2d: np.ndarray
    e: np.ndarray
    s: np.ndarray
    n_bursts_total: int = 0
    columns: dict[str, str] = field(default_factory=dict)


def load_channels(
    source: str | pathlib.Path | dict[str, np.ndarray],
    *,
    hints: dict | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, str]]:
    """Read a burst table and return its channel arrays plus the column map.

    Parameters
    ----------
    source : path-like or dict
        A burst table on disk (``.bur``, ``.csv``, ``.txt``, ``.npz``) or an
        already-loaded ``{column: array}`` mapping.
    hints : dict, optional
        Extra ``{role: (fragment, …)}`` naming hints, passed straight to
        :func:`~chisurf.core.fluorescence.burst.table.guess_columns` — typically
        the detector-setup window names.

    Returns
    -------
    tuple
        ``({"i_dd": …, "i_da": …, "i_aa": …, "duration": …}, {role: column})``.
        ``i_aa`` and ``duration`` are absent when the table has no such column.

    Raises
    ------
    ValueError
        If the donor or the FRET channel cannot be identified.
    """
    columns = dict(source) if isinstance(source, dict) else read_burst_table(source)
    mapping = guess_columns(columns.keys(), hints)
    missing = [role for role in ("i_dd", "i_da") if role not in mapping]
    if missing:
        raise ValueError(
            f"could not identify the {', '.join(missing)} column(s) in "
            f"{sorted(columns)[:12]}… — name the columns, or pass hints"
        )
    arrays = {
        role: np.asarray(columns[name], dtype=float)
        for role, name in mapping.items()
        if role in ("i_dd", "i_da", "i_aa")
    }
    # The whole-burst duration, never a per-detector one: the background is a
    # rate over the burst, and "Duration (green) (ms)" would charge each burst
    # the donor channel's span instead.
    lowered = {str(name).strip().lower(): name for name in columns}
    duration = next(
        (lowered[key] for key in ("duration (ms)", "duration", "tau", "duration_ms")
         if key in lowered), None)
    if duration is not None:
        arrays["duration"] = np.asarray(columns[duration], dtype=float)
        mapping["duration"] = duration
    return arrays, mapping


def _sentinel_rows(channels: dict[str, np.ndarray]) -> np.ndarray:
    """Mask of the all-zero placeholder rows of an interleaved ``.bur`` table.

    A burst with no photons in any channel and no duration is not a short burst,
    it is the zero row the legacy layout writes between real ones.
    """
    zero = np.ones_like(channels["i_dd"], dtype=bool)
    for key in ("i_dd", "i_da", "i_aa", "duration"):
        values = channels.get(key)
        if values is not None:
            zero &= values == 0
    return zero


def burst_efficiency_stoichiometry(
    channels: dict[str, np.ndarray],
    corrections: Corrections = Corrections(),
) -> tuple[np.ndarray, np.ndarray]:
    """Corrected per-burst ``E`` and ``S`` from the channel arrays.

    The backgrounds in :class:`Corrections` are rates (counts/ms), so they are
    turned into counts with the per-burst duration before
    :func:`~chisurf.core.fluorescence.burst.es.corrected_es` subtracts them. A
    table without a duration column gets no background subtraction rather than a
    wrong one — the same choice the old program made when ``Tau`` was missing.

    Returns
    -------
    tuple of ndarray
        ``(E, S)``. ``S`` is all-NaN when the table has no acceptor-excitation
        channel (a non-ALEX measurement).
    """
    i_dd = channels["i_dd"]
    i_da = channels["i_da"]
    i_aa = channels.get("i_aa")
    tau_ms = channels.get("duration")

    if tau_ms is None:
        bg_dd = bg_da = bg_aa = 0.0
    else:
        bg_dd = corrections.bg_dd * tau_ms
        bg_da = corrections.bg_da * tau_ms
        bg_aa = corrections.bg_aa * tau_ms

    result = corrected_es(
        i_dd, i_da, i_aa,
        gamma=corrections.gamma,
        alpha=corrections.alpha,
        beta=corrections.beta,
        delta=corrections.delta,
        bg_dd=bg_dd, bg_da=bg_da, bg_aa=bg_aa,
    )
    e = np.asarray(result["E"], dtype=float)
    s = result["S"]
    s = np.full_like(e, np.nan) if s is None else np.asarray(s, dtype=float)
    return e, s


def es_histograms(
    source: str | pathlib.Path | dict[str, np.ndarray],
    *,
    corrections: Corrections = Corrections(),
    thresholds: Thresholds = Thresholds(),
    bins: tuple[int, int] = (101, 101),
    e_limits: tuple[float, float] = (0.0, 1.0),
    s_limits: tuple[float, float] = (0.0, 1.0),
    weighted: bool = False,
    hints: dict | None = None,
) -> EsHistograms:
    """Build the E, S and E–S histograms of one burst table.

    Parameters
    ----------
    source : path-like or dict
        Burst table, as accepted by :func:`load_channels`.
    corrections : Corrections
        Background and α/β/γ/δ factors.
    thresholds : Thresholds
        Burst filters and the two projection gates.
    bins : tuple of int
        ``(n_e_bins, n_s_bins)``.
    e_limits, s_limits : tuple of float
        Histogram ranges.
    weighted : bool
        Weight each burst by its donor-excitation photon count instead of
        counting it once — the old *weighted* checkbox.
    hints : dict, optional
        Column-naming hints for :func:`load_channels`.

    Returns
    -------
    EsHistograms
    """
    channels, mapping = load_channels(source, hints=hints)
    e, s = burst_efficiency_stoichiometry(channels, corrections)
    n_total = int(e.size)

    green = channels["i_dd"] + channels["i_da"]
    total = green + channels.get("i_aa", np.zeros_like(green))
    keep = np.isfinite(e)
    # A `.bur` is 2n+1 interleaved: every other row is an all-zero sentinel the
    # reader keeps on purpose, because the `...4` companion files align to it by
    # position. They are not bursts, and counting them halves every histogram's
    # apparent yield while adding a spike at E = 0.
    keep &= ~_sentinel_rows(channels)
    keep &= (total >= thresholds.total_min) & (total <= thresholds.total_max)
    duration = channels.get("duration")
    if duration is not None:
        keep &= (duration >= thresholds.duration_min_ms)
        keep &= (duration <= thresholds.duration_max_ms)
    keep &= (e > thresholds.e_range[0]) & (e < thresholds.e_range[1])
    # A non-ALEX table has S = NaN everywhere, and every comparison against NaN
    # is False -- so gating on S would select nothing at all rather than
    # "no stoichiometry gate". Apply it only where S is a number.
    finite_s = np.isfinite(s)
    keep &= ~finite_s | ((s > thresholds.s_range[0]) & (s < thresholds.s_range[1]))

    e, s = e[keep], s[keep]
    weights = green[keep] if weighted else None

    n_e, n_s = int(bins[0]), int(bins[1])
    e_edges = np.linspace(e_limits[0], e_limits[1], n_e + 1)
    s_edges = np.linspace(s_limits[0], s_limits[1], n_s + 1)
    e_centres = 0.5 * (e_edges[:-1] + e_edges[1:])
    s_centres = 0.5 * (s_edges[:-1] + s_edges[1:])

    finite_s = np.isfinite(s)
    if finite_s.any():
        hist_2d, _, _ = np.histogram2d(
            s[finite_s], e[finite_s], bins=(s_edges, e_edges),
            weights=None if weights is None else weights[finite_s],
        )
    else:
        hist_2d = np.zeros((n_s, n_e))

    # The projections are gated on the *other* axis, as in the old program: the
    # E histogram over a stoichiometry band, the S histogram over an efficiency
    # band. Projecting the 2-D map rather than re-histogramming keeps the three
    # panels of one view consistent by construction.
    s_gate = (s_centres >= thresholds.s_range_for_e[0]) & (
        s_centres <= thresholds.s_range_for_e[1])
    e_gate = (e_centres >= thresholds.e_range_for_s[0]) & (
        e_centres <= thresholds.e_range_for_s[1])
    e_hist = hist_2d[s_gate].sum(axis=0) if s_gate.any() else hist_2d.sum(axis=0)
    s_hist = hist_2d[:, e_gate].sum(axis=1) if e_gate.any() else hist_2d.sum(axis=1)

    return EsHistograms(
        e_centres=e_centres,
        s_centres=s_centres,
        e_hist=e_hist,
        s_hist=s_hist,
        hist_2d=hist_2d,
        e=e,
        s=s,
        n_bursts_total=n_total,
        columns=mapping,
    )
