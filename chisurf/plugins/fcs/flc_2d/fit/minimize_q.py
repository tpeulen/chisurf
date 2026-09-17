"""The regulator-ramped MEM minimization of the original 2D-FLC fits.

Port of ``TK_FitF_MinimizeQ_09.m`` (one matrix) and ``TK_GFitF_MinimizeQ_04.m`` (a lag
stack sharing the lifetime amplitudes), with ``TK_mi_ModelFunction.m`` (the entropy
prior) and the start-value preparation of ``TK_MyMain_Fit_2DMEM_04.m``.

The schedule is the reference's, trial for trial:

1. ``regulator_k = regulator * regulator_factor**(k - 1)`` for ``k = 1..n_trials``;
2. the prior ``mi`` is recomputed from the current amplitudes at the start of each trial;
3. ``Q = chi2 - 2 S / regulator_k`` is minimized from the current parameters, which
   then carry over; each trial appends ``[regulator, Q, chi2, S]`` to ``q_table``;
4. the loop stops early when ``|chi2 / (2 S / regulator)| > 10**break_factor``.

The objective is :func:`~chisurf.plugins.fcs.flc_2d.fit.reproduct.reproduce_global_2d`
exactly (the MATLAB ``expfun`` of ``TK_FitF_2DMEM_07`` / ``TK_GFitF_2DMEM_05`` is the
same code as its ``Reproduct``), on the fit window ``fit_start..end`` of the chosen
axis, with the same fix flags and parameter order.

**What is not the reference's:** the local minimizer. The MATLAB calls ``fminsearch``
(Nelder-Mead, 10^4 function evaluations) on ~200 parameters, which does not converge
inside one trial; the ramp of 100 trials is what moves it. Here each trial runs
L-BFGS-B with the analytic gradient (``abs()`` parameters become bounds at zero, which
has the same minimizers), so a trial goes further than the reference's and the
numbers after a trial differ even though the objective does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .reproduct import _floor_zeros, bin_widths, unpack_estimates_global_2d

__all__ = [
    "MinimizeQResult",
    "mi_model",
    "gaussian_initial_distribution",
    "scale_initial_distribution",
    "minimize_q",
]


def mi_model(
    amplitudes: np.ndarray, tau_ns: np.ndarray, t_max_ns: float, t_min_ns: float, mi_type: int = 0
) -> np.ndarray:
    """Entropy prior per state (``TK_mi_ModelFunction``), ``amplitudes`` ``n_comp x n_states``.

    ``0``: the grand mean over each state's mean, weighted by the lifetime resolution
    ``(1 - exp(-(t_max - t_min)/tau))^2``; ``1``: each state normalized to unit mean;
    ``2``: ``(type0 + 3 type1)/4``; ``3``: a Gaussian in grid-index space with each
    state's mean and width, scaled to its sum.
    """
    A = np.atleast_2d(np.asarray(amplitudes, dtype=float).T).T
    tau = np.asarray(tau_ns, dtype=float).ravel()
    res_w = (1.0 - np.exp(-(float(t_max_ns) - float(t_min_ns)) / tau)) ** 2

    def type0():
        mi = np.full_like(A, A.mean())
        return mi / A.mean(axis=0)[None, :] * res_w[:, None]

    def type1():
        return A / A.mean(axis=0)[None, :]

    if mi_type == 0:
        return type0()
    if mi_type == 1:
        return type1()
    if mi_type == 2:
        return (type0() + type1() * 3.0) / 4.0
    if mi_type == 3:
        ivec = np.arange(1, A.shape[0] + 1, dtype=float)
        out = np.empty_like(A)
        for k in range(A.shape[1]):
            total = A[:, k].sum()
            ave = ivec @ A[:, k] / total
            std = np.sqrt(((ivec - ave) ** 2) @ A[:, k] / total)
            out[:, k] = (
                1.0 / std / np.sqrt(2 * np.pi) * np.exp(-((ivec - ave) ** 2) / (2 * std * std))
            ) * total
        return out
    raise ValueError(f"unknown mi_type {mi_type}")


def gaussian_initial_distribution(tau_ns: np.ndarray, estimates) -> np.ndarray:
    """Start amplitudes from ``Hozzon_estimates`` (``TK_MyMain_Fit_2DMEM_04``, ``Tau_Select = 0``).

    ``estimates = [y0_placeholder, amp_1, tau_1, width_1, amp_2, ...]``; state ``k`` is
    ``amp_k exp(-((tau - tau_k) / width_k)^2)``. The first entry is skipped, as there.
    """
    h = np.asarray(estimates, dtype=float).ravel()
    tau = np.asarray(tau_ns, dtype=float).ravel()
    n_states = h.size // 3
    A = np.zeros((tau.size, n_states))
    for k in range(n_states):
        amp, tau0, width = h[1 + 3 * k : 4 + 3 * k]
        A[:, k] = amp * np.exp(-1 * ((tau - tau0) / width) ** 2)
    return A


def scale_initial_distribution(
    amplitudes: np.ndarray, basis: np.ndarray, data_max: float, *, power: int = 2
) -> np.ndarray:
    """Scale start amplitudes to the data: ``A sqrt(max(M) / (sum(A) max(E))^power)``.

    ``power = 2`` is the 2D driver (the model is quadratic in ``A``), ``1`` the 1D one.
    """
    A = np.asarray(amplitudes, dtype=float)
    denom = (A.sum() ** power) * (np.max(basis) ** power)
    return A * np.sqrt(float(data_max) / denom)


@dataclass
class MinimizeQResult:
    """Parameters after the ramp, with its trial table."""

    amplitudes: np.ndarray  # (n_comp, n_states)
    correlations: np.ndarray  # (n_lags, n_states, n_states)
    y0: np.ndarray  # (n_lags,), per unit bin width of the fit axis (the MATLAB's Var_y0)
    estimates: np.ndarray  # parameter vector in the MATLAB order
    q_table: np.ndarray  # (n_trials, 4): regulator, Q, chi2, S
    regulator: float
    mi: np.ndarray = field(default_factory=lambda: np.empty(0))


def _as_stack(m):
    m = np.asarray(m, dtype=float)
    return m[None] if m.ndim == 2 else m


class _Objective:
    """Q and its gradient over the free parameters, MATLAB order and flags."""

    def __init__(self, data, cor, axis, basis, A0, G0, y00, fix_A, fix_G, fix_y0):
        self.D, self.C = data, cor
        self.E = basis
        self.W = np.outer(bin_widths(axis), bin_widths(axis))
        self.A0, self.G0, self.y00 = A0, G0, y00
        self.fix_A, self.fix_G, self.fix_y0 = fix_A, fix_G, fix_y0
        self.n_comp, self.n_states = A0.shape
        self.n_lags = G0.shape[0]
        self.inv_w = 1.0 / (data + data.mean(axis=(1, 2), keepdims=True))
        self._layout()

    def _layout(self):
        """Parameter slots: (kind, index, absolute) in the MATLAB order."""
        slots = []
        for k in range(self.n_states):
            f = self.fix_A[k]
            if f == 1:
                continue
            if f == 3:
                slots.append(("Aamp", k, True))
            else:
                for i in range(self.n_comp):
                    slots.append(("A", (i, k), f == 2))
        for t in range(self.n_lags):
            for k in range(self.n_states):
                for i in range(self.n_states):
                    f = self.fix_G[t, i, k]
                    if f in (0, 2):
                        slots.append(("G", (t, i, k), f == 2))
                    elif f == 3 and i <= k:
                        slots.append(("Gsym", (t, i, k), True))
            if self.fix_y0[t] != 1:
                slots.append(("y0", t, self.fix_y0[t] == 2))
        self.slots = slots

    def start(self):
        x = []
        for kind, idx, absolute in self.slots:
            if kind == "Aamp":
                v = 1.0
            elif kind == "A":
                v = self.A0[idx]
            elif kind in ("G", "Gsym"):
                v = self.G0[idx]
            else:
                v = self.y00[idx]
            x.append(abs(v) if absolute else v)
        return np.asarray(x, dtype=float)

    def bounds(self):
        return [(0.0, None) if absolute else (None, None) for _, _, absolute in self.slots]

    def unpack(self, x):
        return unpack_estimates_global_2d(
            x,
            self.n_comp,
            self.n_states,
            self.n_lags,
            initial_amplitudes=self.A0,
            initial_correlations=self.G0,
            initial_y0=self.y00,
            fix_amplitudes=self.fix_A,
            fix_correlations=self.fix_G,
            fix_y0=self.fix_y0,
        )

    def __call__(self, x, mi, regulator):
        A_raw, G, y0 = self.unpack(x)
        A = _floor_zeros(A_raw)
        E = self.E
        B = E @ A
        n = self.D.shape[1]
        chi2 = 0.0
        dB = np.zeros_like(B)
        dG = np.zeros_like(G)
        dy0 = np.zeros(self.n_lags)
        for t in range(self.n_lags):
            model = B @ G[t] @ B.T + y0[t] * self.W
            r = self.C[t] - model
            chi2 += float(np.sum(r * r * self.inv_w[t])) / (n * n)
            R = -2.0 * r * self.inv_w[t] / (n * n * self.n_lags)
            dB += R @ B @ G[t].T + R.T @ B @ G[t]
            dG[t] = B.T @ R @ B
            dy0[t] = float(np.sum(R * self.W))
        chi2 /= self.n_lags
        eA = A.max(axis=0) * 1e-10
        em = mi.max(axis=0) * 1e-10
        ratio = (A + eA) / (mi + em)
        # 0 log 0 = 0: an all-zero state (reachable at the bound) would otherwise be NaN
        with np.errstate(divide="ignore", invalid="ignore"):
            alogr = np.where(A > 0, A * np.log(ratio), 0.0)
        S = float(np.sum(A.sum(axis=0) - mi.sum(axis=0) - alogr.sum(axis=0)))
        Q = chi2 - 2.0 * S / regulator
        tiny = np.finfo(float).tiny  # a state that is all zero has eA = 0
        dS = 1.0 - np.log(np.maximum(ratio, tiny)) - A / np.maximum(A + eA, tiny)
        dA = E.T @ dB - (2.0 / regulator) * dS

        grad = np.empty_like(x)
        for j, (kind, idx, absolute) in enumerate(self.slots):
            if kind == "Aamp":
                g = float(dA[:, idx] @ self.A0[:, idx])
            elif kind == "A":
                g = dA[idx]
            elif kind == "G":
                g = dG[idx]
            elif kind == "Gsym":
                t, i, k = idx
                g = dG[t, i, k] + (dG[t, k, i] if i != k else 0.0)
            else:
                g = dy0[idx]
            grad[j] = g * (np.sign(x[j]) if absolute and x[j] != 0 else 1.0)
        return Q, grad, (chi2, S)


def minimize_q(
    data: np.ndarray,
    axis_ns: np.ndarray,
    basis: np.ndarray,
    tau_ns: np.ndarray,
    initial_amplitudes: np.ndarray,
    *,
    cor: np.ndarray | None = None,
    initial_correlations: np.ndarray | None = None,
    initial_y0=0.0,
    fix_amplitudes=0,
    fix_correlations=3,
    fix_y0=2,
    regulator: float = 0.1,
    regulator_factor: float = 1.4,
    n_regulator_trials: int = 100,
    n_q_trials: int = 1,
    mi_type: int = 0,
    t_min_ns: float,
    t_max_ns: float,
    break_factor: float = 100.0,
    fit_start: int = 30,
    max_evaluations: int = 10_000,
) -> MinimizeQResult:
    """Run the reference's regulator ramp on one matrix or a lag stack.

    Parameters
    ----------
    data, cor
        ``(n, n)`` or ``(n_lags, n, n)`` matrices on ``axis_ns``; ``cor`` is what the
        model is compared with (defaults to ``data``, the drivers' ``UseCor1orNot0 = 0``).
    axis_ns, basis
        The full bin axis and the basis binned on it (``create_exp_curve``); both are
        cut to ``fit_start..end`` (1-based ``FitStartI``) here.
    tau_ns, initial_amplitudes
        Lifetime grid and start ``A`` (``n_comp x n_states``).
    initial_correlations, initial_y0
        Start ``G`` (default identity, as ``TK_FitF_MinimizeQ_09``) and ``y0`` per lag.
    fix_amplitudes, fix_correlations, fix_y0
        MATLAB fix flags; scalars broadcast over states / elements / lags.
    regulator, regulator_factor, n_regulator_trials, n_q_trials, break_factor
        The ramp (``RegulatorConst``, ``RegulatorFactor``, ``TrialNumFor_*``,
        ``BreakFactor``).
    mi_type, t_min_ns, t_max_ns
        Prior (:func:`mi_model`).
    max_evaluations
        Function evaluations per trial (the reference's ``MaxFunEvals``).
    """
    from scipy.optimize import minimize

    D = _as_stack(data)
    C = D if cor is None else _as_stack(cor)
    n_lags = D.shape[0]
    s = int(fit_start) - 1
    D, C = D[:, s:, s:], C[:, s:, s:]
    axis = np.asarray(axis_ns, dtype=float)[s:]
    E = np.asarray(basis, dtype=float)[s:]
    A0 = np.atleast_2d(np.asarray(initial_amplitudes, dtype=float).T).T
    n_states = A0.shape[1]
    G0 = (
        np.tile(np.eye(n_states), (n_lags, 1, 1))
        if initial_correlations is None
        else _as_stack(initial_correlations).copy()
    )
    y00 = np.broadcast_to(np.asarray(initial_y0, dtype=float), (n_lags,)).copy()
    fix_A = (
        np.broadcast_to(np.asarray(fix_amplitudes).ravel(), (n_states,))
        if np.size(fix_amplitudes) in (1, n_states)
        else np.asarray(fix_amplitudes).ravel()
    )
    fix_G = (
        np.broadcast_to(np.asarray(fix_correlations), (n_lags, n_states, n_states))
        if np.ndim(fix_correlations) < 3
        else np.asarray(fix_correlations)
    )
    fix_y = (
        np.broadcast_to(np.asarray(fix_y0).ravel(), (n_lags,))
        if np.size(fix_y0) in (1, n_lags)
        else np.asarray(fix_y0).ravel()
    )

    A_cur, G_cur, y_cur = A0, G0, y00
    x = None
    table = []
    lam = float(regulator)
    mi = None
    for trial in range(int(n_regulator_trials)):
        lam = float(regulator) * float(regulator_factor) ** trial
        mi = mi_model(A_cur, tau_ns, t_max_ns, t_min_ns, mi_type)
        check = 0.0
        for _ in range(int(n_q_trials)):
            obj = _Objective(D, C, axis, E, A_cur, G_cur, y_cur, fix_A, fix_G, fix_y)
            x0 = obj.start()
            if x0.size:
                res = minimize(
                    lambda v: obj(v, mi, lam)[:2],
                    x0,
                    jac=True,
                    method="L-BFGS-B",
                    bounds=obj.bounds(),
                    options={"maxfun": int(max_evaluations)},
                )
                x = res.x
            else:
                x = x0
            A_raw, G_new, y_new = obj.unpack(x)
            q, _, (chi2, S) = obj(x, mi, lam)
            A_cur, G_cur, y_cur = _floor_zeros(A_raw), G_new, y_new
            table.append([lam, q, chi2, S])
            converged = abs(check - q) <= abs(q) * 1e-10
            check = q
            if converged:
                break
        if abs(chi2 / (2.0 * S / lam)) > 10.0**break_factor:
            break
    return MinimizeQResult(
        amplitudes=A_cur,
        correlations=G_cur,
        y0=y_cur,
        estimates=np.asarray(x if x is not None else [], dtype=float),
        q_table=np.asarray(table, dtype=float),
        regulator=lam,
        mi=mi,
    )
