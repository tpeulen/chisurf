"""Per-molecule 2D-FDC and the molecule bootstrap of the original 2D-FLC workflow.

Port of ``TK_MyMain_Create2DFDC_cor_SeparateData_BootStrap_v02.m`` (T. Kondo,
Schlau-Cohen lab, MIT), the data-preparation driver the published 2D-FLC fits start
from.

**Separate data.** A single-molecule data set is many short photon streams, one per
molecule. A photon pair must never span two molecules, so every matrix is built per
molecule and the molecules are summed. For each molecule the driver builds

* the matrix at each lag ``dT`` and at the longest lag, whose difference is the
  *correlated* matrix (``cor``: the longest lag stands in for the uncorrelated
  background),
* the same pair at the shortest lag ``ddT/2`` (``short``, ``short_cor``),
* the zero-lag 1D-FDC (``fdc_1d``: the decay),

on a linear and a logarithmic micro-time axis, and symmetrizes every 2D matrix
(``(M + M^T)/2``, "to eliminate anti-symmetric noise") unless the sample is out of
equilibrium. All lags of a molecule use the **same reference photons**: the reference
window ends ``max(dT)`` before the molecule's end (``min(Tend, last photon)``), so the
lag matrices are comparable and the subtraction is meaningful. The uncorrelated matrix
ends a further ``ddT/2`` earlier -- a quirk of the reference kept as is.

**Bootstrap.** The driver draws the molecules to sum rather than taking each once:
``randperm(N * group_factor)`` mapped onto molecule ``(v - 1) mod N``, taken in that
order until the drawn photon count reaches ``photon_factor`` times the total. With
both factors 1 it is the plain sum. The MATLAB produces *one* replicate per run and
leaves the error bars to repeating the whole analysis on several; here
:func:`bootstrap_2d_fdc` draws the replicates and reports their mean and standard
deviation per element, which is what those repetitions estimate.

Faithfulness notes, each checked against the original run in Octave:

* The reference counts a partner photon only **after** the reference in stream
  order. The photon library counts every photon in the window, so at the shortest
  lag (window starting at the reference itself) it adds each reference's self-pair
  and pairs with earlier photons of the same macro time; the zero-lag 1D-FDC adds the
  latter. Both are subtracted here.
* The ``dT +/- ddT/2`` window is in integer macro ticks, so ``ddT`` must be even.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from .core import earlier_same_time_pairs, fdc_bin_index

__all__ = [
    "MATRIX_KEYS",
    "SeparateDataFDC",
    "BootstrapFDC",
    "separate_data_2d_fdc",
    "bootstrap_order",
    "bootstrap_2d_fdc",
]

#: Names of the summed quantities, as in the MATLAB workspace (``Mat_2DFDC_cor_log``
#: is ``cor_log``). Lag-resolved ones are ``(n_lags, n, n)``.
MATRIX_KEYS = (
    "fdc_1d_lin",
    "fdc_1d_log",
    "short_lin",
    "short_log",
    "short_cor_lin",
    "short_cor_log",
    "lin",
    "log",
    "cor_lin",
    "cor_log",
)


@dataclass
class SeparateDataFDC:
    """Raw per-molecule pair counts; summed and normalized on demand.

    Counts are kept unsymmetrized and uncorrected (all linear operations), so any
    multiset of molecules can be summed first and processed once.
    """

    dT_ticks: np.ndarray
    ddT_ticks: int
    lin_t: np.ndarray  # linear-axis bin starts (micro ticks above tMin)
    log_t: np.ndarray  # log-axis bin edges (micro ticks above tMin)
    photon_counts: np.ndarray  # (n_molecules,) all photons of each stream
    measurement_times: np.ndarray  # (n_molecules,) span of photons in [t_start, t_end]
    raw: dict[str, np.ndarray]  # per molecule: lags/unc/short (lin, log) and 1D
    symmetrize: bool = True
    use_cor: bool = True

    @property
    def n_molecules(self) -> int:
        """Number of molecules."""
        return int(self.photon_counts.size)

    def total(self, order: Sequence[int] | None = None) -> dict[str, np.ndarray]:
        """Sum the molecules in ``order`` (repeats allowed) into the driver's matrices."""
        idx = np.arange(self.n_molecules) if order is None else np.asarray(order, dtype=int)
        s = {k: v[idx].sum(axis=0) for k, v in self.raw.items()}
        sym = (
            (lambda m: (m + np.swapaxes(m, -1, -2)) / 2.0)
            if self.symmetrize
            else (lambda m: m.astype(float))
        )
        out = {
            "fdc_1d_lin": s["fdc_1d_lin"].astype(float),
            "fdc_1d_log": s["fdc_1d_log"].astype(float),
        }
        for axis in ("lin", "log"):
            if f"lags_{axis}" not in s:
                continue
            lags, unc, short = s[f"lags_{axis}"], s[f"unc_{axis}"], s[f"short_{axis}"]
            out[f"short_{axis}"] = sym(short)
            out[axis] = sym(lags)
            if self.use_cor:
                out[f"short_cor_{axis}"] = sym(short - unc)
                out[f"cor_{axis}"] = sym(lags - unc[None])
        return out


@dataclass
class BootstrapFDC:
    """Molecule-bootstrap replicates of the driver's matrices."""

    replicates: dict[str, np.ndarray]  # key -> (n_replicates, ...)
    orders: list[np.ndarray]  # molecules drawn per replicate
    photon_totals: np.ndarray  # photons drawn per replicate
    measurement_times: np.ndarray  # summed measurement time per replicate (ticks)
    mean: dict[str, np.ndarray] = field(default_factory=dict)
    std: dict[str, np.ndarray] = field(default_factory=dict)


# --------------------------------------------------------------------- photon pass


def _axes(t_min: int, t_max: int, lint_bin_factor: int, logt_imax: int):
    import tttrlib

    f = int(lint_bin_factor)
    t_imax = int(tttrlib.fdc_t_imax(int(t_max) - int(t_min), f))
    log_ticks = np.zeros(int(logt_imax) + 1, dtype=np.int64)
    tttrlib.fdc_log_ticks(t_imax, log_ticks)
    lin_ticks = np.concatenate([[-1], np.arange(0, t_imax + f, f)]).astype(np.int64)
    return t_imax, f, log_ticks, lin_ticks


def _pairs(
    macro,
    micro,
    lag,
    ddT,
    t_start,
    cap,
    t_min,
    t_max,
    axes,
    build_lin,
    n_chunks,
    *,
    forward_only: bool,
):
    """Pair matrices (lin, log; untrimmed) for one lag with the reference's window rules.

    Reference photons are those at ``t >= t_start`` whose window ends at or before
    ``cap``; ``forward_only`` removes what the library counts and the reference does
    not (self-pairs and earlier same-time photons, for a window starting at ``t``).
    """
    import tttrlib

    t_imax, _f, log_ticks, lin_ticks = axes
    keep = (macro >= t_start) & (macro <= cap)
    mac, mic = macro[keep], micro[keep]
    n_log, n_lin = log_ticks.size - 1, lin_ticks.size - 1
    out_log = np.zeros(n_log * n_log, dtype=np.int64)
    out_lin = np.zeros(n_lin * n_lin, dtype=np.int64)
    if mac.size:
        # A sentinel at the cap makes the library's "window past the last photon"
        # rule the reference's "window past Tend" rule; its micro time is out of gate.
        smac = np.ascontiguousarray(np.append(mac, cap), dtype=np.int64)
        smic = np.ascontiguousarray(np.append(mic, t_min), dtype=np.int64)
        lags = np.array([int(lag)], dtype=np.int64)
        if build_lin:
            tttrlib.fdc_scan_two_axes(
                smac,
                smic,
                lags,
                int(ddT),
                int(t_min),
                int(t_max),
                log_ticks,
                lin_ticks,
                int(n_chunks),
                out_log,
                out_lin,
                t_imax,
            )
        else:
            tttrlib.fdc_scan_axis(
                smac,
                smic,
                lags,
                int(ddT),
                int(t_min),
                int(t_max),
                log_ticks,
                int(n_chunks),
                out_log,
                t_imax,
            )
    mat_log = out_log.reshape(n_log, n_log)
    mat_lin = out_lin.reshape(n_lin, n_lin)
    if mac.size and forward_only:
        half = int(ddT) // 2
        tau = mic.astype(np.int64) - int(t_min)
        in_gate = (tau > 0) & (tau < t_imax)
        is_ref = in_gate & (mac + int(lag) + half <= cap)
        q, p = earlier_same_time_pairs(mac)
        self_pairs = int(lag) - half <= 0
        for ticks, mat, on in ((log_ticks, mat_log, True), (lin_ticks, mat_lin, build_lin)):
            if not on:
                continue
            b = np.where(in_gate, fdc_bin_index(tau, ticks), -1)
            if self_pairs:
                sel = is_ref & (b >= 0)
                np.subtract.at(mat, (b[sel], b[sel]), 1)
            if q.size:
                sel = is_ref[q] & (b[q] >= 0) & (b[p] >= 0)
                np.subtract.at(mat, (b[q][sel], b[p][sel]), 1)
    return mat_lin, mat_log


def separate_data_2d_fdc(
    molecules: Sequence[tuple[np.ndarray, np.ndarray]],
    dT_ticks: Sequence[int],
    ddT_ticks: int,
    *,
    tMin: int,
    tMax: int,
    t_start: int = 0,
    t_end: int | None = None,
    lint_bin_factor: int = 4,
    logt_imax: int = 100,
    symmetrize: bool = True,
    use_cor: bool = True,
    build_lin: bool = True,
    n_chunks: int = 1,
) -> SeparateDataFDC:
    """Build the per-molecule 2D-FDC set of the reference driver.

    Parameters
    ----------
    molecules
        One ``(macro_ticks, micro_ticks)`` stream per molecule, macro ascending.
    dT_ticks, ddT_ticks
        Lags and the full window width in macro ticks (``ddT`` even, every lag
        at least ``ddT/2``). The longest lag is the uncorrelated reference.
    tMin, tMax
        Micro-time gate (ticks); the axes follow ``TK_Create2DFDC_04``.
    t_start, t_end
        Macro-time window (``Tstart``/``Tend``) applied to every molecule's own clock.
    lint_bin_factor, logt_imax
        Linear bin factor and number of log bins.
    symmetrize
        ``(M + M^T)/2`` every 2D matrix (``Equi0orNonequi1 = 0``, equilibrium samples).
    use_cor
        Build the background-subtracted ``cor`` matrices (``UseCor1orNot0``).
    build_lin
        Also build the linear-axis matrices. They are
        ``((tMax - tMin)/lint_bin_factor)^2`` per lag per molecule; turn off for fine
        linear axes and many molecules.
    n_chunks
        Parallel chunks of the photon pass (never changes the counts).
    """
    lags = np.asarray(dT_ticks, dtype=np.int64).ravel()
    ddT = int(ddT_ticks)
    if ddT <= 0 or ddT % 2:
        raise ValueError("ddT_ticks must be a positive even number of ticks")
    half = ddT // 2
    if lags.size == 0 or np.any(lags < half):
        raise ValueError("every lag must be at least ddT_ticks / 2")
    axes = _axes(tMin, tMax, lint_bin_factor, logt_imax)
    t_imax, f = axes[0], axes[1]
    lint_imax = t_imax // f
    dT_longest = int(lags.max())

    per = {
        k: []
        for k in (
            "lags_lin",
            "lags_log",
            "unc_lin",
            "unc_log",
            "short_lin",
            "short_log",
            "fdc_1d_lin",
            "fdc_1d_log",
        )
    }
    counts, spans = [], []
    trim = slice(1, lint_imax)  # see core.create_2d_fdc_numba_int

    def run(macro, micro, lag, cap, forward_only):
        lin, log = _pairs(
            macro,
            micro,
            lag,
            ddT,
            t_start,
            cap,
            tMin,
            tMax,
            axes,
            build_lin,
            n_chunks,
            forward_only=forward_only,
        )
        return lin[trim, trim], log

    for macro, micro in molecules:
        macro = np.asarray(macro, dtype=np.int64)
        micro = np.asarray(micro, dtype=np.int64)
        if macro.size and np.any(np.diff(macro) < 0):
            raise ValueError("macro times must be sorted ascending within each molecule")
        counts.append(macro.size)
        last = int(macro[-1])
        end = last if t_end is None else min(int(t_end), last)
        window = np.flatnonzero((macro >= t_start) & (macro <= (last if t_end is None else t_end)))
        spans.append(int(macro[window[-1]] - macro[window[0]]) if window.size else 0)

        lin_l, log_l = zip(
            *[
                run(macro, micro, L, min(end - dT_longest + int(L) + half, last), int(L) <= half)
                for L in lags
            ]
        )
        unc = run(macro, micro, dT_longest, end, dT_longest <= half)
        short = run(macro, micro, half, min(end - dT_longest + ddT, last), True)
        # zero lag, ddT 1: the window is the reference's own macro tick
        lin0, log0 = _pairs(
            macro,
            micro,
            0,
            1,
            t_start,
            min(end - dT_longest, last),
            tMin,
            tMax,
            axes,
            True,
            n_chunks,
            forward_only=False,
        )
        _drop_earlier_same_time(
            macro, micro, lin0, log0, t_start, min(end - dT_longest, last), tMin, axes
        )
        per["lags_lin"].append(np.stack(lin_l))
        per["lags_log"].append(np.stack(log_l))
        per["unc_lin"].append(unc[0])
        per["unc_log"].append(unc[1])
        per["short_lin"].append(short[0])
        per["short_log"].append(short[1])
        per["fdc_1d_lin"].append(np.diag(lin0)[trim].copy())
        per["fdc_1d_log"].append(np.diag(log0).copy())

    raw = {
        k: np.stack(v)
        for k, v in per.items()
        if (build_lin or not k.endswith("_lin")) or k == "fdc_1d_lin"
    }
    lin_t = f * np.arange(lint_imax - 1, dtype=np.int64)
    return SeparateDataFDC(
        dT_ticks=lags,
        ddT_ticks=ddT,
        lin_t=lin_t,
        log_t=axes[2][: int(logt_imax)],
        photon_counts=np.asarray(counts, dtype=np.int64),
        measurement_times=np.asarray(spans, dtype=np.int64),
        raw=raw,
        symmetrize=bool(symmetrize),
        use_cor=bool(use_cor),
    )


def _drop_earlier_same_time(macro, micro, lin0, log0, t_start, cap, t_min, axes):
    """Zero lag: the reference pairs a photon with itself and *later* same-time photons."""
    t_imax, _f, log_ticks, lin_ticks = axes
    keep = (macro >= t_start) & (macro <= cap)
    mac, mic = macro[keep], micro[keep]
    q, p = earlier_same_time_pairs(mac)
    if not q.size:
        return
    tau = mic - int(t_min)
    in_gate = (tau > 0) & (tau < t_imax)
    for ticks, mat in ((log_ticks, log0), (lin_ticks, lin0)):
        b = np.where(in_gate, fdc_bin_index(tau, ticks), -1)
        sel = (b[q] >= 0) & (b[p] >= 0)
        np.subtract.at(mat, (b[q][sel], b[p][sel]), 1)


# ------------------------------------------------------------------------ bootstrap


def bootstrap_order(
    photon_counts: Sequence[int],
    *,
    photon_factor: float = 1.0,
    group_factor: int = 1,
    rng: np.random.Generator | None = None,
    permutation: Sequence[int] | None = None,
) -> tuple[np.ndarray, int]:
    """Draw molecules the way the reference driver does.

    ``randperm(N * group_factor)`` (or the 0-based ``permutation`` given), mapped to
    molecule ``v mod N``, taken in order until the photon count reaches
    ``photon_factor * sum(photon_counts)``. Both factors 1 take every molecule once, in
    order, without drawing. Returns ``(molecule indices, photons drawn)``.
    """
    counts = np.asarray(photon_counts, dtype=np.int64)
    n = counts.size
    target = float(counts.sum()) * float(photon_factor)
    if photon_factor == 1 and group_factor == 1:
        pool = np.arange(n)
    else:
        if permutation is None:
            rng = np.random.default_rng() if rng is None else rng
            permutation = rng.permutation(n * int(group_factor))
        pool = np.asarray(permutation, dtype=np.int64) % n
    drawn, total = [], 0
    for idx in pool:
        drawn.append(int(idx))
        total += int(counts[idx])
        if total >= target:
            break
    return np.asarray(drawn, dtype=int), total


def bootstrap_2d_fdc(
    separate: SeparateDataFDC,
    n_replicates: int = 100,
    *,
    photon_factor: float = 1.0,
    group_factor: int = 2,
    seed: int | None = None,
    keys: Sequence[str] | None = None,
) -> BootstrapFDC:
    """Molecule-bootstrap replicates, with the per-element mean and standard deviation.

    ``group_factor = 2`` (the value the reference's comment suggests) lets each molecule
    appear up to twice per replicate; with both factors 1 every replicate is the plain
    sum and the spread is zero.
    """
    rng = np.random.default_rng(seed)
    orders, photons, spans, reps = [], [], [], {}
    for _ in range(int(n_replicates)):
        order, total = bootstrap_order(
            separate.photon_counts, photon_factor=photon_factor, group_factor=group_factor, rng=rng
        )
        mats = separate.total(order)
        for k in keys or mats.keys():
            reps.setdefault(k, []).append(mats[k])
        orders.append(order)
        photons.append(total)
        spans.append(int(separate.measurement_times[order].sum()))
    replicates = {k: np.stack(v) for k, v in reps.items()}
    ddof = 1 if n_replicates > 1 else 0
    return BootstrapFDC(
        replicates=replicates,
        orders=orders,
        photon_totals=np.asarray(photons),
        measurement_times=np.asarray(spans),
        mean={k: v.mean(axis=0) for k, v in replicates.items()},
        std={k: v.std(axis=0, ddof=ddof) for k, v in replicates.items()},
    )
