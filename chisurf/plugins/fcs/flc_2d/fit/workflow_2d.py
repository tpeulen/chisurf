"""The 2D-MEM workflow drivers of the original 2D-FLC code: one fit, the IRF-rise scan, the average.

Ports of the MATLAB scripts (T. Kondo, Schlau-Cohen lab, MIT):

* ``TK_MyMain_Fit_2DMEM_04`` + ``TK_MyMain_GFit_2DMEM`` -> :func:`fit_2d_mem_workflow`.
  At one IRF rise point: the basis (:func:`~.exp_curve.create_exp_curve`), Gaussian
  start amplitudes scaled to the data, a 2D-MEM on the shortest-lag matrix, a fit of
  each lag's ``G`` and ``y0`` with those amplitudes fixed, then the global fit of all
  lags, reproduced on the linear and the log axis.
* ``TK_MyMain_Search_RiseIRF_2DMEM`` -> :func:`search_irf_rise_2d`. That workflow at
  each IRF rise point in turn, keeping the global amplitudes, the linear model at the
  first lag and the last ``[Q, chi2, S]``. The reference keeps them for the user to
  pick the lowest chi2 (P. Manna's technical note, "2D Search"); ``best`` is that
  choice made explicit.
* ``TK_MyMain_Run_Ave2DMEM`` -> :func:`average_2d_mem`. The workflow at ``n`` rise
  points centred on a chosen one, and the element-wise mean of the global results.

Both scans use the reference's rise-point sequence ``center - n//2 + 0..n-1``
(``RisePoint_IRF_start = 310 - floor(20/2)``, ``RisePoint_IRF = start - 1 + testI``;
``(Icenter - 1) - floor(Imax/2) + I``). All matrix and axis conventions are the
reference's (``TK_Create2DFDC_04``): axes in ns, ``y0`` reported per linear bin.

The reference's defaults are the defaults here, including two worth knowing: the fits
run on the **log** matrices from bin 30 on (``Linear0orLog1 = 1``, ``FitStartI = 30``)
against the raw, not the background-subtracted, matrices (``UseCor1orNot0 = 0``); and
the averaging driver fixes the amplitudes at the scaled start distribution
(``Fix1orNot0orAbs2orAmp3_Mat_A = 1``, "changed from 2 to 1 on 190117"), so only
``G`` and ``y0`` are fitted there. The local minimizer is not the reference's (see
:mod:`~.minimize_q`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from .exp_curve import ExpCurves, create_exp_curve, matlab_lin_axis_ns, matlab_log_axis_ns
from .minimize_q import (
    MinimizeQResult,
    gaussian_initial_distribution,
    minimize_q,
    scale_initial_distribution,
)
from .reproduct import reproduce_global_2d

__all__ = [
    "Mem2DWorkflowResult",
    "RiseSearch2DResult",
    "Average2DResult",
    "rise_points",
    "fit_2d_mem_workflow",
    "search_irf_rise_2d",
    "average_2d_mem",
]


def rise_points(center: int, n: int) -> np.ndarray:
    """The reference's scan: ``center - n//2 + 0..n-1`` (1-based IRF rise channels)."""
    return int(center) - int(n) // 2 + np.arange(int(n))


@dataclass
class Mem2DWorkflowResult:
    """One run of ``TK_MyMain_Fit_2DMEM_04`` + ``TK_MyMain_GFit_2DMEM``."""

    rise_point_irf: int
    tau_ns: np.ndarray
    lin_axis_ns: np.ndarray
    log_axis_ns: np.ndarray
    basis: ExpCurves
    short: MinimizeQResult  # shortest lag, amplitudes free
    per_lag: list[MinimizeQResult]  # G, y0 per lag with the short amplitudes fixed
    global_fit: MinimizeQResult  # all lags, shared amplitudes
    amplitudes: np.ndarray  # (n_comp, n_states), the global fit's
    correlations: np.ndarray  # (n_lags, n_states, n_states)
    y0: np.ndarray  # (n_lags,), per linear bin (GResult_y0_dTfun)
    flc_maps: np.ndarray  # (n_lags, n_comp, n_comp)
    model_lin: np.ndarray  # (n_lags, n_lin, n_lin)
    model_log: np.ndarray  # (n_lags, n_log, n_log)
    q_table: np.ndarray  # the global fit's trial table: regulator, Q, chi2, S

    @property
    def final_q(self) -> np.ndarray:
        """``[Q, chi2, S]`` of the last global trial (what the rise scan records)."""
        return self.q_table[-1, 1:]


def fit_2d_mem_workflow(
    matrices: dict[str, np.ndarray],
    *,
    irf: np.ndarray,
    xdata_ns: np.ndarray,
    estimates: Sequence[float],
    t_min_ns: float,
    t_max_ns: float,
    t_step_ns: float,
    lint_bin_factor: int,
    logt_imax: int,
    rise_point_irf: int,
    rise_point_fl: int = 300,
    irf_range: tuple[int, int] | None = None,
    tau_ns: np.ndarray | None = None,
    fix_amplitudes: int = 2,
    fix_correlations: int = 3,
    fix_y0: int = 2,
    y0: float = 5000.0,
    use_log: bool = True,
    fit_start: int = 30,
    mi_type: int = 0,
    regulator: float = 0.1,
    regulator_factor: float = 1.4,
    n_short_trials: int = 100,
    n_lag_trials: int = 10,
    n_global_trials: int = 100,
    break_factor: float = 100.0,
    max_evaluations: int = 10_000,
) -> Mem2DWorkflowResult:
    """Fit a lag stack of 2D-FDC matrices the way the reference's 2D-MEM drivers do.

    Parameters
    ----------
    matrices
        ``short_lin``, ``short_log`` (``n x n``) and ``lin``, ``log``
        (``n_lags x n x n``) on the reference axes -- what
        :meth:`chisurf.plugins.fcs.flc_2d.bootstrap.SeparateDataFDC.total` returns.
    irf, xdata_ns
        IRF per TCSPC channel and the channel times (ns).
    estimates
        ``Hozzon_estimates``: ``[0, amp_1, tau_1, width_1, amp_2, ...]``.
    t_min_ns, t_max_ns, t_step_ns, lint_bin_factor, logt_imax
        The 2D-FDC gate and axes the matrices were built with.
    rise_point_irf, rise_point_fl, irf_range
        IRF placement (1-based channels); ``irf_range`` defaults to the reference's
        ``(50, len(xdata) - 90)``.
    tau_ns
        Lifetime grid; default the reference's ``0.05:0.05:5.05``.
    fix_amplitudes, fix_correlations, fix_y0
        Fix flags of the shortest-lag and global fits (the per-lag fits fix ``A``).
    y0, use_log, fit_start, mi_type, regulator, regulator_factor, break_factor
        The reference's settings (``y0``, ``Linear0orLog1``, ``FitStartI``,
        ``mi_TypeSelect``, ``RegulatorConst``, ``RegulatorFactor``, ``BreakFactor``).
    n_short_trials, n_lag_trials, n_global_trials
        Regulator trials of the three stages (``TrialNumFor_RegulatorConst`` 100 in
        ``Fit_2DMEM_04``, 10 per lag and ``G_TrialNumFor_RegulatorConst`` 100 in
        ``GFit_2DMEM``).
    max_evaluations
        Function evaluations per trial.
    """
    x = np.asarray(xdata_ns, dtype=float)
    tau = (np.arange(0.05, 5.05 + 1e-9, 0.05) if tau_ns is None
           else np.asarray(tau_ns, dtype=float))
    if irf_range is None:
        irf_range = (50, x.size - 70 - 20)
    lin_axis = matlab_lin_axis_ns(t_min_ns, t_max_ns, t_step_ns, lint_bin_factor)
    log_axis = matlab_log_axis_ns(t_min_ns, t_max_ns, t_step_ns, lint_bin_factor, logt_imax)
    basis = create_exp_curve(
        tau, x, irf, t_min_ns=t_min_ns, t_max_ns=t_max_ns, t_step_ns=t_step_ns,
        lint_bin_factor=lint_bin_factor, log_axis_ns=log_axis, rise_point_fl=rise_point_fl,
        rise_point_irf=rise_point_irf, irf_range=irf_range,
    )
    lags_lin = np.asarray(matrices["lin"], dtype=float)
    lags_log = np.asarray(matrices["log"], dtype=float)
    if lags_lin.ndim == 2:
        lags_lin, lags_log = lags_lin[None], lags_log[None]
    n_lin = min(lags_lin.shape[-1], basis.binned_lin.shape[0], lin_axis.size)
    E_lin, lin_axis = basis.binned_lin[:n_lin], lin_axis[:n_lin]
    lags_lin = lags_lin[:, :n_lin, :n_lin]
    short_lin = np.asarray(matrices["short_lin"], dtype=float)[:n_lin, :n_lin]
    short_log = np.asarray(matrices["short_log"], dtype=float)
    E_fit, axis_fit = (basis.binned_log, log_axis) if use_log else (E_lin, lin_axis)
    short_fit = short_log if use_log else short_lin
    lags_fit = lags_log if use_log else lags_lin

    A0 = gaussian_initial_distribution(tau, estimates)
    A0 = scale_initial_distribution(A0, E_fit, float(np.max(lags_fit)))
    width = float(lin_axis[1] - lin_axis[0])
    common = dict(tau_ns=tau, mi_type=mi_type, t_min_ns=t_min_ns, t_max_ns=t_max_ns,
                  break_factor=break_factor, fit_start=fit_start,
                  max_evaluations=max_evaluations, regulator=regulator,
                  regulator_factor=regulator_factor)

    short = minimize_q(short_fit, axis_fit, E_fit, initial_amplitudes=A0,
                       initial_y0=y0 / width, fix_amplitudes=fix_amplitudes,
                       fix_correlations=fix_correlations, fix_y0=fix_y0,
                       n_regulator_trials=n_short_trials, **common)
    short_y0 = float(short.y0[0]) * width

    per_lag, G_init, y_init = [], [], []
    for t in range(lags_fit.shape[0]):
        r = minimize_q(lags_fit[t], axis_fit, E_fit, initial_amplitudes=short.amplitudes,
                       initial_y0=short_y0 / width, fix_amplitudes=1,
                       fix_correlations=fix_correlations, fix_y0=fix_y0,
                       n_regulator_trials=n_lag_trials, **common)
        per_lag.append(r)
        G_init.append(r.correlations[0])
        y_init.append(r.y0[0])

    glob = minimize_q(lags_fit, axis_fit, E_fit, initial_amplitudes=short.amplitudes,
                      initial_correlations=np.stack(G_init), initial_y0=np.asarray(y_init),
                      fix_amplitudes=fix_amplitudes, fix_correlations=fix_correlations,
                      fix_y0=fix_y0, n_regulator_trials=n_global_trials, **common)
    kw = dict(floor_zeros=False, mi=glob.mi, regulator=glob.regulator)
    rep_lin = reproduce_global_2d(glob.amplitudes, glob.correlations, E_lin, lin_axis,
                                  y0=glob.y0, data=lags_lin, **kw)
    rep_log = reproduce_global_2d(glob.amplitudes, glob.correlations, basis.binned_log,
                                  log_axis, y0=glob.y0, data=lags_log, **kw)
    return Mem2DWorkflowResult(
        rise_point_irf=int(rise_point_irf), tau_ns=tau, lin_axis_ns=lin_axis,
        log_axis_ns=log_axis, basis=basis, short=short, per_lag=per_lag, global_fit=glob,
        amplitudes=glob.amplitudes, correlations=glob.correlations, y0=glob.y0 * width,
        flc_maps=rep_lin.flc_map, model_lin=rep_lin.model, model_log=rep_log.model,
        q_table=glob.q_table,
    )


@dataclass
class RiseSearch2DResult:
    """``TK_MyMain_Search_RiseIRF_2DMEM``: one row per IRF rise point."""

    rise_point_fl: int
    rise_points_irf: np.ndarray  # (n,)
    q: np.ndarray  # (n, 3): Q, chi2, S of the last global trial
    amplitudes: np.ndarray  # (n, n_comp, n_states)
    model_lin_first_lag: np.ndarray  # (n, n_lin, n_lin)
    runs: list[Mem2DWorkflowResult] = field(default_factory=list)

    @property
    def best(self) -> int:
        """The rise point with the lowest chi2 (the choice the reference leaves to you)."""
        return int(self.rise_points_irf[int(np.argmin(self.q[:, 1]))])


def search_irf_rise_2d(
    matrices: dict[str, np.ndarray],
    *,
    center: int = 310,
    n_points: int = 20,
    rise_points_irf: Sequence[int] | None = None,
    keep_runs: bool = False,
    **workflow,
) -> RiseSearch2DResult:
    """Run :func:`fit_2d_mem_workflow` at each IRF rise point (``TK_MyMain_Search_RiseIRF_2DMEM``).

    ``rise_points_irf`` defaults to :func:`rise_points` ``(center, n_points)`` -- the
    reference's 300..319. Every other keyword goes to the workflow; the reference runs
    this with amplitudes ``abs`` (2) and symmetric ``G`` (3).
    """
    points = rise_points(center, n_points) if rise_points_irf is None else np.asarray(
        rise_points_irf, dtype=int)
    runs = [fit_2d_mem_workflow(matrices, rise_point_irf=int(p), **workflow) for p in points]
    return RiseSearch2DResult(
        rise_point_fl=int(workflow.get("rise_point_fl", 300)),
        rise_points_irf=points,
        q=np.stack([r.final_q for r in runs]),
        amplitudes=np.stack([r.amplitudes for r in runs]),
        model_lin_first_lag=np.stack([r.model_lin[0] for r in runs]),
        runs=runs if keep_runs else [],
    )


@dataclass
class Average2DResult:
    """``TK_MyMain_Run_Ave2DMEM``: the global results averaged over the rise points."""

    rise_points_irf: np.ndarray
    amplitudes: np.ndarray
    correlations: np.ndarray
    flc_maps: np.ndarray
    model_lin: np.ndarray
    model_log: np.ndarray
    estimates: np.ndarray
    q_table: np.ndarray
    lin_axis_ns: np.ndarray
    log_axis_ns: np.ndarray
    runs: list[Mem2DWorkflowResult] = field(default_factory=list)


def average_2d_mem(
    matrices: dict[str, np.ndarray],
    *,
    center: int,
    n_points: int = 5,
    fix_amplitudes: int = 1,
    keep_runs: bool = False,
    **workflow,
) -> Average2DResult:
    """Average the workflow over ``n_points`` rise points centred on ``center`` (``TK_MyMain_Run_Ave2DMEM``).

    Averaged, element by element and with equal weight, as the reference sums and
    divides: the parameter vectors, the trial tables, both axes, ``A``, ``G``, the
    2D-FLC maps and the linear and log models. No alignment of states between runs is
    attempted (neither does the reference). ``fix_amplitudes = 1`` is the reference's
    setting for this driver.
    """
    points = rise_points(center, n_points)
    runs = [fit_2d_mem_workflow(matrices, rise_point_irf=int(p), fix_amplitudes=fix_amplitudes,
                                **workflow) for p in points]

    def mean(attr):
        return np.mean(np.stack([np.asarray(attr(r), dtype=float) for r in runs]), axis=0)

    return Average2DResult(
        rise_points_irf=points,
        amplitudes=mean(lambda r: r.amplitudes),
        correlations=mean(lambda r: r.correlations),
        flc_maps=mean(lambda r: r.flc_maps),
        model_lin=mean(lambda r: r.model_lin),
        model_log=mean(lambda r: r.model_log),
        estimates=mean(lambda r: r.global_fit.estimates),
        q_table=mean(lambda r: r.q_table),
        lin_axis_ns=mean(lambda r: r.lin_axis_ns),
        log_axis_ns=mean(lambda r: r.log_axis_ns),
        runs=runs if keep_runs else [],
    )
