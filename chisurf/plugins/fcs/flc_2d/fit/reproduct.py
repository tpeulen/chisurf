"""Forward models of 2D-FLC, and reproduction of decays and maps from fitted parameters.

Port of the four MATLAB "reproduct" functions of the original 2D-FLC code (T. Kondo,
Schlau-Cohen lab, MIT):

* ``TK_FitF_Reproduct1DFDC`` and ``TK_FitF_Reproduct1DFDC_02`` -- the 1D-FDC (decay)
  model ``E A (+ y0 dt)`` with its chi-square, entropy and MEM estimator;
* ``TK_FitF_Reproduct2DFDCand2DFLC_03`` -- the 2D-FLC map ``A G A^T`` and the 2D-FDC
  model ``E A G A^T E^T + y0 (dt dt^T)``;
* ``TK_GFitF_Reproduct2DFDCand2DFLC_03`` -- the same for a stack of lags sharing ``A``.

In the MATLAB these functions are *both* the objective the ``fminsearch`` minimizers
evaluate and the call that rebuilds the linear- and log-binned models after a fit: the
minimizers finish by reproducing the fitted parameters on the other binning. This module
serves the second use, and the forward models it defines (:func:`decay_model`,
:func:`fdc_model`) are the ones the plugin's own fits evaluate, so a reproduction and a
fit cannot drift apart.

Conventions carried over exactly, because each changes the numbers:

* ``y0`` multiplies the **bin width** (``dt``, first bin copied from the second), outer
  product for the 2D map. On a linear axis that is a constant; on a log axis it is not.
* Exact zeros in ``A`` are lifted to ``1e-7 * (max(A) - min(A))`` before anything is
  evaluated ("just for avoiding error" in the MATLAB), so the model sees them too.
* ``chi2 = mean((cor - model)^2 / (data + mean(data)))`` -- the data matrix, not the
  correlation matrix, sets the weight. ``TK_FitF_Reproduct1DFDC`` additionally weights
  each bin by its width; ``_02`` dropped that.
* Entropy ``S = sum_k [sum A_k - sum mi_k - sum A_k log((A_k + e_A) / (mi_k + e_mi))]``
  with ``e_mi = 1e-10 max(mi_k)``; the 2D functions also add ``e_A = 1e-10 max(A_k)``
  to the numerator, the 1D ones do not. ``Q = chi2 - 2 S / regulator``.
* ``estimates`` vectors are unpacked with the MATLAB fix flags, column-major:
  ``0`` free, ``1`` fixed at the initial value, ``2`` free as ``abs()``, and ``3`` meaning
  "scale the initial column by ``abs()``" for ``A`` and "symmetric, ``abs()``" for ``G``.
  In the global form the vector is ``[A, G(lag 1), y0(lag 1), G(lag 2), y0(lag 2), ...]``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "Reproduction",
    "bin_widths",
    "decay_model",
    "fdc_model",
    "reproduce_1d",
    "reproduce_2d",
    "reproduce_global_2d",
    "reproduce_result",
    "unpack_estimates_1d",
    "unpack_estimates_2d",
    "unpack_estimates_global_2d",
]


@dataclass
class Reproduction:
    """Models rebuilt from parameters, with the MATLAB figures of merit.

    ``chi2``, ``entropy`` and ``estimator_q`` are ``None`` when the inputs they need
    (data; ``mi``; ``mi`` and ``regulator``) were not given.
    """

    model: np.ndarray  # 1D decay, 2D map, or (n_lags, n, n) stack
    amplitudes: np.ndarray  # A (n_comp, n_states), after the zero floor
    flc_map: np.ndarray | None = None  # A G A^T (2D) or its lag stack
    correlation: np.ndarray | None = None  # G (n_states, n_states) or (n_lags, s, s)
    y0: float | np.ndarray = 0.0
    chi2: float | None = None
    entropy: float | None = None
    estimator_q: float | None = None


# ------------------------------------------------------------------ forward models


def bin_widths(axis: np.ndarray) -> np.ndarray:
    """Return per-bin widths of a time axis, the first copied from the second.

    ``Dif_Mat_*_It`` of the MATLAB. A one-point axis has width 1.
    """
    t = np.asarray(axis, dtype=float).ravel()
    if t.size < 2:
        return np.ones_like(t)
    d = np.empty_like(t)
    d[1:] = np.diff(t)
    d[0] = d[1]
    return d


def decay_model(
    basis: np.ndarray,
    amplitudes: np.ndarray,
    y0: float = 0.0,
    widths: np.ndarray | None = None,
) -> np.ndarray:
    """1D decay model ``E A + y0 * widths`` (``widths`` ``None`` -> a constant ``y0``)."""
    E = np.asarray(basis, dtype=float)
    A = np.asarray(amplitudes, dtype=float)
    model = E @ (A[:, 0] if A.ndim == 2 else A)
    if widths is None:
        return model + float(y0)
    return model + float(y0) * np.asarray(widths, dtype=float)


def fdc_model(
    basis: np.ndarray,
    flc_map: np.ndarray,
    y0: float = 0.0,
    widths: np.ndarray | None = None,
) -> np.ndarray:
    """2D-FDC model ``E P E^T + y0 * outer(widths, widths)`` for a 2D-FLC map ``P``."""
    E = np.asarray(basis, dtype=float)
    model = E @ np.asarray(flc_map, dtype=float) @ E.T
    if widths is None:
        return model + float(y0)
    w = np.asarray(widths, dtype=float)
    return model + float(y0) * np.outer(w, w)


# ------------------------------------------------------------------ MATLAB pieces


def _floor_zeros(A: np.ndarray) -> np.ndarray:
    A = np.array(A, dtype=float, copy=True)
    span = float(A.max() - A.min()) if A.size else 0.0
    return A + (A == 0) * (span * 1e-7)


def _chi2(data: np.ndarray, data_cor: np.ndarray, model: np.ndarray, widths=None) -> float:
    data = np.asarray(data, dtype=float)
    resid = (np.asarray(data_cor, dtype=float) - model) ** 2 / (data + data.mean())
    if widths is not None:
        resid = resid * widths
    return float(resid.sum() / resid.size)


def _entropy(A: np.ndarray, mi: np.ndarray, *, amplitude_floor: bool) -> float:
    A = np.atleast_2d(np.asarray(A, dtype=float).T).T
    mi = np.atleast_2d(np.asarray(mi, dtype=float).T).T
    S = 0.0
    for k in range(A.shape[1]):
        a, m = A[:, k], mi[:, k]
        num = a + a.max() * 1e-10 if amplitude_floor else a
        with np.errstate(divide="ignore", invalid="ignore"):
            log_term = a * np.log(num / (m + m.max() * 1e-10))
        S += float(a.sum() - m.sum() - log_term.sum())
    return S


def _merit(model, data, data_cor, A, mi, regulator, *, widths, amplitude_floor):
    if data is None:
        return None, None, None
    cor = data if data_cor is None else data_cor
    chi2 = _chi2(data, cor, model, widths)
    if mi is None:
        return chi2, None, None
    S = _entropy(A, mi, amplitude_floor=amplitude_floor)
    Q = None if regulator is None else chi2 - 2.0 * S / float(regulator)
    return chi2, S, Q


# ------------------------------------------------------------------ reproductions


def reproduce_1d(
    amplitudes: np.ndarray,
    basis: np.ndarray,
    axis: np.ndarray,
    *,
    y0: float = 0.0,
    data: np.ndarray | None = None,
    data_cor: np.ndarray | None = None,
    mi: np.ndarray | None = None,
    regulator: float | None = None,
    area_weighted: bool = False,
    per_bin_width: bool = True,
    floor_zeros: bool = True,
) -> Reproduction:
    """Rebuild a 1D-FDC from a lifetime distribution (``TK_FitF_Reproduct1DFDC*``).

    Parameters
    ----------
    amplitudes
        Lifetime distribution ``A`` (``n_comp``).
    basis
        Exponential basis ``E`` (``n_data x n_comp``), columns in the order of ``A``.
    axis
        Time axis of the decay bins (sets the ``y0`` bin widths).
    y0
        Background amplitude per unit bin width (``_02``). The original
        ``TK_FitF_Reproduct1DFDC`` has none: pass ``0``.
    data, data_cor
        Measured 1D-FDC and the decay the model is compared against (defaults to
        ``data``).
    mi, regulator
        Entropy prior (``n_comp``) and ``RegulatorConst``.
    area_weighted
        Weight the chi-square by bin width, as the original ``TK_FitF_Reproduct1DFDC``
        did (``_02`` does not).
    per_bin_width, floor_zeros
        The MATLAB conventions (``y0`` scaled by bin width; zeros in ``A`` lifted).
        Turn both off to reproduce one of this plugin's own fits, which fit a
        constant offset on the amplitudes as given.
    """
    A = np.asarray(amplitudes, dtype=float).reshape(-1, 1)
    A = _floor_zeros(A) if floor_zeros else A
    widths = bin_widths(axis)
    model = decay_model(basis, A, y0, widths if per_bin_width else None)
    chi2, S, Q = _merit(
        model,
        data,
        data_cor,
        A,
        None if mi is None else np.reshape(mi, (-1, 1)),
        regulator,
        widths=widths if area_weighted else None,
        amplitude_floor=False,
    )
    return Reproduction(model, A, y0=float(y0), chi2=chi2, entropy=S, estimator_q=Q)


def reproduce_2d(
    amplitudes: np.ndarray,
    correlation: np.ndarray,
    basis: np.ndarray,
    axis: np.ndarray,
    *,
    y0: float = 0.0,
    data: np.ndarray | None = None,
    data_cor: np.ndarray | None = None,
    mi: np.ndarray | None = None,
    regulator: float | None = None,
    per_bin_width: bool = True,
    floor_zeros: bool = True,
) -> Reproduction:
    """Rebuild the 2D-FLC map and 2D-FDC (``TK_FitF_Reproduct2DFDCand2DFLC_03``).

    Parameters
    ----------
    amplitudes
        ``A`` (``n_comp x n_states``): lifetime distribution of each state.
    correlation
        ``G`` (``n_states x n_states``).
    basis, axis
        Exponential basis ``E`` (``n_data x n_comp``) and the bin axis of the matrix.
    y0, data, data_cor, mi, regulator, per_bin_width, floor_zeros
        As in :func:`reproduce_1d`; ``mi`` is ``n_comp x n_states``.
    """
    A = np.atleast_2d(np.asarray(amplitudes, dtype=float).T).T
    A = _floor_zeros(A) if floor_zeros else A
    G = np.asarray(correlation, dtype=float)
    flc = A @ G @ A.T
    model = fdc_model(basis, flc, y0, bin_widths(axis) if per_bin_width else None)
    chi2, S, Q = _merit(model, data, data_cor, A, mi, regulator, widths=None, amplitude_floor=True)
    return Reproduction(model, A, flc, G, float(y0), chi2, S, Q)


def reproduce_global_2d(
    amplitudes: np.ndarray,
    correlations: np.ndarray,
    basis: np.ndarray,
    axis: np.ndarray,
    *,
    y0: np.ndarray | float = 0.0,
    data: np.ndarray | None = None,
    data_cor: np.ndarray | None = None,
    mi: np.ndarray | None = None,
    regulator: float | None = None,
    per_bin_width: bool = True,
    floor_zeros: bool = True,
) -> Reproduction:
    """Rebuild a lag stack sharing ``A`` (``TK_GFitF_Reproduct2DFDCand2DFLC_03``).

    ``correlations`` is ``(n_lags, n_states, n_states)``, ``y0`` one value per lag and
    ``data``/``data_cor`` ``(n_lags, n_data, n_data)``. The chi-square is the mean of
    the per-lag chi-squares, each weighted by its own lag's mean. ``per_bin_width`` and
    ``floor_zeros`` as in :func:`reproduce_1d`.
    """
    A = np.atleast_2d(np.asarray(amplitudes, dtype=float).T).T
    A = _floor_zeros(A) if floor_zeros else A
    Gs = np.asarray(correlations, dtype=float)
    n_lags = Gs.shape[0]
    y0s = np.broadcast_to(np.asarray(y0, dtype=float), (n_lags,)).copy()
    widths = bin_widths(axis) if per_bin_width else None
    flc = np.stack([A @ Gs[t] @ A.T for t in range(n_lags)])
    model = np.stack([fdc_model(basis, flc[t], y0s[t], widths) for t in range(n_lags)])
    chi2 = S = Q = None
    if data is not None:
        data = np.asarray(data, dtype=float)
        cor = data if data_cor is None else np.asarray(data_cor, dtype=float)
        chi2 = float(np.mean([_chi2(data[t], cor[t], model[t]) for t in range(n_lags)]))
        if mi is not None:
            S = _entropy(A, mi, amplitude_floor=True)
            if regulator is not None:
                Q = chi2 - 2.0 * S / float(regulator)
    return Reproduction(model, A, flc, Gs, y0s, chi2, S, Q)


def reproduce_result(result, basis: np.ndarray, *, data: np.ndarray | None = None) -> Reproduction:
    """Rebuild the model of one of this plugin's fit results on a (new) basis.

    The MATLAB minimizers end by reproducing their parameters on the other binning;
    this is that step for :class:`~.ilt.ILTResult1D`, :class:`~.mem_1d.OneDMEMResult`,
    :class:`~.ilt.ILTResult2D` and :class:`~.global_mem.GlobalMEMResult`. The model is
    the fit's own (constant offset, amplitudes as fitted), so on the fit's basis it
    equals ``result.model``. ``basis`` columns must follow ``result.tau_grid``.
    ``data`` (a decay, a matrix, or the lag stack) adds the MATLAB chi-square.
    """
    E = np.asarray(basis, dtype=float)
    kw = dict(per_bin_width=False, floor_zeros=False, data=data)
    axis = np.arange(E.shape[0], dtype=float)
    if hasattr(result, "correlations"):  # global multi-lag MEM
        return reproduce_global_2d(result.amplitudes, result.correlations, E, axis, **kw)
    if hasattr(result, "spectrum"):  # 2D ILT / MEM: the map is the fitted parameter
        P = np.asarray(result.spectrum, dtype=float)
        model = fdc_model(E, P, result.offset)
        chi2 = None if data is None else _chi2(data, data, model)
        return Reproduction(model, P, flc_map=P, y0=float(result.offset), chi2=chi2)
    return reproduce_1d(result.amplitudes, E, axis, y0=result.offset, **kw)


# ------------------------------------------------------------------ estimates vectors


class _Cursor:
    """Reads an ``estimates`` vector the way the MATLAB ``Count`` walks it."""

    def __init__(self, estimates):
        self.values = np.asarray(estimates, dtype=float).ravel()
        self.count = 0

    def take(self, absolute: bool) -> float:
        value = float(self.values[self.count])
        self.count += 1
        return abs(value) if absolute else value


def _unpack_A(cur: _Cursor, initial_A, fix_A, n_comp: int, n_states: int) -> np.ndarray:
    A = np.zeros((n_comp, n_states))
    init = None if initial_A is None else np.atleast_2d(np.asarray(initial_A, float).T).T
    flags = np.broadcast_to(np.asarray(fix_A).ravel(), (n_states,))
    for k in range(n_states):
        if flags[k] == 1:
            A[:, k] = init[:, k]
        elif flags[k] == 3:
            A[:, k] = init[:, k] * cur.take(True)
        else:
            for i in range(n_comp):
                A[i, k] = cur.take(flags[k] == 2)
    return A


def _unpack_G(cur: _Cursor, initial_G, fix_G, n_states: int) -> np.ndarray:
    G = np.zeros((n_states, n_states))
    for k in range(n_states):  # column-major, as the MATLAB loops
        for i in range(n_states):
            flag = fix_G[i, k]
            if flag == 1:
                G[i, k] = initial_G[i, k]
            elif flag in (0, 2):
                G[i, k] = cur.take(flag == 2)
            elif flag == 3 and i <= k:
                G[i, k] = G[k, i] = cur.take(True)
    return G


def _unpack_y0(cur: _Cursor, initial_y0, fix_y0) -> float:
    flag = np.asarray(fix_y0).ravel()[0]
    return float(initial_y0) if flag == 1 else cur.take(flag == 2)


def unpack_estimates_1d(
    estimates, n_comp: int, *, initial_amplitudes=None, fix=0, initial_y0=0.0, fix_y0=None
):
    """Unpack ``(A, y0)`` for the 1D reproduction; ``fix_y0=None`` means no ``y0``."""
    cur = _Cursor(estimates)
    flag = np.asarray(fix).ravel()[0]
    if flag == 1:
        A = np.asarray(initial_amplitudes, dtype=float).reshape(-1)
    else:
        A = np.array([cur.take(flag == 2) for _ in range(n_comp)])
    y0 = 0.0 if fix_y0 is None else _unpack_y0(cur, initial_y0, fix_y0)
    return A, y0


def unpack_estimates_2d(
    estimates,
    n_comp: int,
    n_states: int,
    *,
    initial_amplitudes=None,
    initial_correlation=None,
    initial_y0=0.0,
    fix_amplitudes=0,
    fix_correlation=None,
    fix_y0=0,
):
    """Unpack ``(A, G, y0)`` for :func:`reproduce_2d` from a MATLAB estimates vector."""
    cur = _Cursor(estimates)
    fix_G = (
        np.zeros((n_states, n_states)) if fix_correlation is None else np.asarray(fix_correlation)
    )
    A = _unpack_A(cur, initial_amplitudes, fix_amplitudes, n_comp, n_states)
    G = _unpack_G(cur, initial_correlation, fix_G, n_states)
    return A, G, _unpack_y0(cur, initial_y0, fix_y0)


def unpack_estimates_global_2d(
    estimates,
    n_comp: int,
    n_states: int,
    n_lags: int,
    *,
    initial_amplitudes=None,
    initial_correlations=None,
    initial_y0=None,
    fix_amplitudes=0,
    fix_correlations=None,
    fix_y0=None,
):
    """Unpack ``(A, G stack, y0 per lag)`` for :func:`reproduce_global_2d`.

    ``fix_correlations`` and ``initial_correlations`` are ``(n_lags, s, s)``.
    """
    cur = _Cursor(estimates)
    fix_G = (
        np.zeros((n_lags, n_states, n_states))
        if fix_correlations is None
        else np.asarray(fix_correlations)
    )
    fix_y = np.zeros(n_lags) if fix_y0 is None else np.asarray(fix_y0).ravel()
    init_y = np.zeros(n_lags) if initial_y0 is None else np.asarray(initial_y0, float).ravel()
    A = _unpack_A(cur, initial_amplitudes, fix_amplitudes, n_comp, n_states)
    Gs = np.zeros((n_lags, n_states, n_states))
    y0s = np.zeros(n_lags)
    for t in range(n_lags):
        init_G = None if initial_correlations is None else np.asarray(initial_correlations)[t]
        Gs[t] = _unpack_G(cur, init_G, fix_G[t], n_states)
        y0s[t] = _unpack_y0(cur, init_y[t], fix_y[t])
    return A, Gs, y0s
