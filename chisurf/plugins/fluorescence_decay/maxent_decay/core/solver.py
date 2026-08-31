from typing import Any, Callable, Dict, Optional, Sequence, Tuple

import numpy as np

from chisurf.core.progress import trange as _mem_trange


MIN_PROB = 1e-12


def load_tcspc_two_column(path: str) -> np.ndarray:
    """Load a two-column TCSPC text file ("Chan  Data") like extract2c.c.

    This function scans all lines, attempts to parse two numbers from the
    beginning of each line, and returns the second column (counts) as a
    1D float array. Header/comment lines are ignored.
    """
    chan = []
    data = []
    with open(path, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            try:
                x = float(parts[0])
                y = float(parts[1])
            except ValueError:
                continue
            chan.append(x)
            data.append(y)
    if not data:
        return np.zeros(0, dtype=float)
    return np.asarray(data, dtype=float)


def autofitrange(lamp: np.ndarray, decay: np.ndarray, threshold: float = 10.0) -> Tuple[int, int]:
    """Port of gfit/autofitrange.m.

    Parameters
    ----------
    lamp, decay : array_like
        1D arrays of instrument response and decay counts.
    threshold : float
        Intensity threshold for the decay tail (default 100, as in MATLAB).

    Returns
    -------
    start, stop : int
        0-based inclusive indices defining the fit range.
    """
    lamp = np.asarray(lamp, dtype=float).ravel()
    decay = np.asarray(decay, dtype=float).ravel()
    if lamp.size == 0 or decay.size == 0:
        return 0, max(0, min(lamp.size, decay.size) - 1)

    start = int(np.argmax(lamp))
    peak = int(np.argmax(decay))

    below = np.nonzero(decay < threshold)[0]
    if below.size == 0:
        candidates = np.array([decay.size - 1], dtype=int)
    else:
        candidates = np.concatenate((below, np.array([decay.size - 1], dtype=int)))

    greater = candidates[candidates > peak]
    if greater.size == 0:
        stop = int(candidates[-1])
    else:
        stop = int(greater[0])

    if stop < start:
        stop = start
    return start, stop


def auto_fit_range_tcspc(
    decay: np.ndarray,
    count_threshold: float = 10.0,
    area: float = 0.999,
    start_fraction: float = 0.9,
    start_at_peak: bool = True,
    skip_first: int = 0,
    skip_last: int = 0,
) -> Tuple[int, int]:
    """Auto fit range similar to chisurf.core.fluorescence.tcspc.initial_fit_range.

    Parameters
    ----------
    decay : array_like
        1D decay counts.
    count_threshold : float
        Minimum counts to consider a channel as part of the fit.
    area : float
        Fraction of total counts (from the start index onward) to include.
    start_fraction : float
        Fraction of the peak at which to start when ``start_at_peak`` is True.
    start_at_peak : bool
        If True, start where ``decay > start_fraction * max(decay)``; otherwise
        start where ``decay > count_threshold``.
    skip_first, skip_last : int
        Extra channels to skip at the beginning / end of the fit range.
    """

    decay = np.asarray(decay, dtype=float).ravel()
    n = decay.size
    if n == 0:
        return 0, 0

    if start_at_peak and decay.max() > 0.0:
        lvl = start_fraction * float(decay.max())
        idx = np.nonzero(decay > lvl)[0]
    else:
        idx = np.nonzero(decay > count_threshold)[0]
    if idx.size == 0:
        start = 0
    else:
        start = int(idx[0])

    if start >= n - 1:
        return max(0, n - 1), max(0, n - 1)

    tail = decay[start:]
    s_total = float(np.sum(tail))
    if s_total <= 0.0:
        stop = n - 1
    else:
        cumsum = np.cumsum(tail, dtype=float)
        area_idx = np.nonzero(cumsum >= area * s_total)[0]
        if area_idx.size == 0:
            stop = n - 1
        else:
            stop = int(start + area_idx[0])

    stop = min(max(stop, start), n - 1)

    if decay[stop] < count_threshold:
        rev = np.nonzero(decay[::-1] >= count_threshold)[0]
        if rev.size > 0:
            stop = n - int(rev[0]) - 1

    while (stop + 1) < n and decay[stop] >= count_threshold:
        stop += 1

    start = min(start + int(skip_first), n - 1)
    stop = min(max(stop - int(skip_last), start), n - 1)
    return start, stop


def _require_design_builders():
    """Return the photon library's design-matrix builders, or say why not.

    The maximum-entropy TCSPC engine lives in the photon library
    (``MaxEntTcspc``); ChiSurf holds the workflow around it and no second copy
    of the maths. The builders were exposed with the four output vectors as
    *arguments*, which no Python caller can supply, so a checkout older than
    that fix has the names but not the functions -- detected here rather than
    at the call site, where it surfaces as an unreadable ``TypeError``.

    Returns
    -------
    tuple of callable
        ``(tcspc_build_fi_lifetimes, tcspc_build_fi_distances)``.

    Raises
    ------
    RuntimeError
        If the photon library is missing or predates the NumPy bindings.
    """
    try:
        import tttrlib
    except ImportError as exc:  # pragma: no cover - tttrlib is a hard dependency
        raise RuntimeError(
            "the maximum-entropy TCSPC engine is provided by tttrlib, which "
            "could not be imported"
        ) from exc
    try:
        return tttrlib.tcspc_build_fi_lifetimes, tttrlib.tcspc_build_fi_distances
    except AttributeError as exc:
        raise RuntimeError(
            "tttrlib does not expose tcspc_build_fi_lifetimes / "
            "tcspc_build_fi_distances; rebuild it (the design-matrix builders "
            "carry the maximum-entropy convolution)"
        ) from exc


def _tttrlib():
    """Return the photon library, or say what is missing.

    MEM compute lives there; ChiSurf keeps the design matrices and the nuisance
    search around it.
    """
    try:
        import tttrlib
    except ImportError as error:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "MaxEnt needs the photon library, which is not importable"
        ) from error
    if not hasattr(tttrlib, "tcspc_run_mem"):
        raise RuntimeError(
            "the installed photon library has no MEM optimiser "
            "(tcspc_run_mem); rebuild it"
        )
    return tttrlib


def _build_Fi_distances(
    decay: np.ndarray,
    lamp: np.ndarray,
    dt: float,
    R: np.ndarray,
    tau0: float,
    R0: float,
    donly: np.ndarray,
    x_donly: float,
    timeshift: float,
    background: float,
    lamp_scatter: float,
    fitstart: int,
    fitstop: int,
    period: float,
    irf_background: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build the distance-axis design matrix (me_vin4_E.m analogue).

    Column *j* is the donor decay quenched at the FRET rate of ``R[j]``,
    convolved with the shifted IRF and mixed with the unquenched donor by
    ``x_donly``, divided through by the Poisson weight. The convolution runs in
    the photon library; ``timeshift`` is in detector channels (samples), to match
    ChiSurf's ``Curve.__lshift__``, and may be fractional.

    Parameters
    ----------
    decay, lamp : numpy.ndarray
        Measured decay and the raw instrument response. ``irf_background`` is
        subtracted from ``lamp`` before the shift.
    dt : float
        Channel width, in the units of ``tau0``.
    R : numpy.ndarray
        Distance grid; every entry must be positive.
    tau0, R0 : float
        Donor lifetime without acceptor and the Foerster radius.
    donly : numpy.ndarray
        Donor-only reference as ``[c1, tau1, c2, tau2, ...]``.
    x_donly : float
        Donor-only fraction, clamped into ``[0, 1]``.
    timeshift, background, lamp_scatter : float
        IRF shift and the two additive terms.
    fitstart, fitstop : int
        Fit range, inclusive; clamped to the shorter of decay and IRF.
    period : float
        Excitation period; ``<= 0`` selects a single-shot convolution.
    irf_background : float
        Counts subtracted from the IRF before shifting.

    Returns
    -------
    Fi : numpy.ndarray
        ``(M, len(R))`` design matrix.
    y, sigma, fit_additive : numpy.ndarray
        Data, Poisson weight and the additive model term over the fit range.
    """
    decay = np.asarray(decay, dtype=float).ravel()
    lamp = np.asarray(lamp, dtype=float).ravel()
    R = np.asarray(R, dtype=float).ravel()
    donly = np.asarray(donly, dtype=float).ravel()

    if decay.size == 0 or lamp.size == 0 or R.size == 0 or donly.size == 0:
        raise ValueError("decay, lamp, R and donly must be non-empty")
    if donly.size % 2 != 0:
        raise ValueError("donly must contain amplitude/tau pairs")
    if np.any(R <= 0.0):
        raise ValueError("R grid must be positive")

    _, build_distances = _require_design_builders()
    return build_distances(
        decay, lamp, float(dt), R, float(tau0), float(R0), donly, float(x_donly),
        float(timeshift), float(background), float(lamp_scatter),
        int(fitstart), int(fitstop), float(period), float(irf_background),
    )


def _build_Fi_lifetimes(
    decay: np.ndarray,
    lamp: np.ndarray,
    dt: float,
    tau: np.ndarray,
    timeshift: float,
    background: float,
    lamp_scatter: float,
    fitstart: int,
    fitstop: int,
    period: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build the lifetime-axis design matrix (me_vin4.m analogue).

    Column *j* is a single exponential of lifetime ``tau[j]`` convolved with the
    shifted IRF, divided through by the Poisson weight. The convolution runs in
    the photon library; ``timeshift`` is in detector channels (samples) and may
    be fractional.

    Parameters
    ----------
    decay, lamp : numpy.ndarray
        Measured decay and the instrument response. Unlike the distance builder
        this one takes the IRF already background-corrected.
    dt : float
        Channel width.
    tau : numpy.ndarray
        Lifetime grid. Non-positive entries are dropped.
    timeshift, background, lamp_scatter : float
        IRF shift and the two additive terms.
    fitstart, fitstop : int
        Fit range, inclusive; clamped to the shorter of decay and IRF.
    period : float
        Excitation period; ``<= 0`` selects a single-shot convolution.

    Returns
    -------
    Fi : numpy.ndarray
        ``(M, len(tau))`` design matrix.
    y, sigma, fit_additive : numpy.ndarray
        Data, Poisson weight and the additive model term over the fit range.
    """
    decay = np.asarray(decay, dtype=float).ravel()
    lamp = np.asarray(lamp, dtype=float).ravel()
    tau = np.asarray(tau, dtype=float).ravel()

    if decay.size == 0 or lamp.size == 0 or tau.size == 0:
        raise ValueError("decay, lamp and tau must be non-empty")

    tau = tau[tau > 0.0]
    if tau.size == 0:
        raise ValueError("tau grid must contain positive values")

    build_lifetimes, _ = _require_design_builders()
    return build_lifetimes(
        decay, lamp, float(dt), tau,
        float(timeshift), float(background), float(lamp_scatter),
        int(fitstart), int(fitstop), float(period),
    )



def _quadpr_bound(C: np.ndarray, d: np.ndarray, lower_bound: float) -> np.ndarray:
    """Small bound-constrained QP solver ``min 0.5 x^T C x + d^T x``.

    The only constraints are lower bounds ``x >= lower_bound``. We use a
    simple active-set strategy: repeatedly solve the unconstrained system on
    the currently-free variables and clamp any components that violate the
    bound until the active set stops growing.
    """

    C = np.asarray(C, dtype=float)
    d = np.asarray(d, dtype=float).ravel()
    n = d.size
    if C.shape != (n, n):
        raise ValueError("C must be square with shape (n, n)")

    # Ensure symmetry; the quadratic form only depends on the symmetric part.
    C = 0.5 * (C + C.T)
    lb = float(lower_bound)

    x = np.zeros(n, dtype=float)
    active = np.zeros(n, dtype=bool)

    for _ in range(50):
        free = ~active
        if np.any(free):
            C_ff = C[np.ix_(free, free)]
            d_f = d[free]
            try:
                x_f = -np.linalg.solve(C_ff, d_f)
            except np.linalg.LinAlgError:
                x_f = -np.linalg.lstsq(C_ff, d_f, rcond=None)[0]
            x[free] = x_f

        # Enforce the bound on the active set explicitly.
        x[active] = lb

        viol = x < lb
        new_active = viol & ~active
        if not np.any(new_active):
            break
        active |= viol

    x = np.maximum(x, lb)
    return x


def _run_mem(
    H: np.ndarray,
    g0: np.ndarray,
    m: np.ndarray,
    const_chi2: float,
    nu: float,
    progress_cb: Optional[Callable[[int, float, float, float, float], None]] = None,
    max_iter: int = 200,
    tol: float = 1e-4,
    min_prob: float = MIN_PROB,
) -> Dict[str, Any]:
    """Run the MEM optimiser on a prepared quadratic form.

    The optimiser itself is :func:`tttrlib.tcspc_run_mem`. ChiSurf carried a
    NumPy transcription of it until 2026-08-31; on a 120-lifetime grid the two
    returned the same solution to the last printed digit (chi2r 1.040852,
    identical ``p``) with the compiled one **3.1x** faster (70 ms against
    222 ms), so the copy was deleted. It mattered more than 3x sounds: this is
    the *inner* solve of the nuisance search, which calls it hundreds of times.

    Parameters
    ----------
    H : numpy.ndarray
        ``(n, n)`` curvature of the chi-square term.
    g0 : numpy.ndarray
        ``(n,)`` linear term.
    m : numpy.ndarray
        ``(n,)`` prior (the "default model").
    const_chi2 : float
        The data-only constant of the chi-square.
    nu : float
        Entropy weight.
    progress_cb : callable, optional
        ``progress_cb(iteration, chisq, S, Q, dgrad)``. The compiled optimiser
        does not report per iteration, so this is called **once** with the
        converged values rather than once per map. Callers use it to drive a
        progress dialog, which a single terminal update still serves; nothing
        reads the intermediate values.
    max_iter, tol, min_prob : float
        Iteration limit, convergence tolerance and the floor on ``p``.

    Returns
    -------
    dict
        ``p``, ``chisq``, ``S``, ``Q``, ``history``, the ``*_esm`` companions,
        ``nu`` and ``niter``.
    """
    H = np.asarray(H, dtype=float)
    g0 = np.asarray(g0, dtype=float).ravel()
    m = np.asarray(m, dtype=float).ravel()

    result = _tttrlib().tcspc_run_mem(
        H.ravel().tolist(), g0.tolist(), m.tolist(),
        float(const_chi2), float(nu), int(max_iter), float(tol), float(min_prob),
    )

    chisq, S, Q = float(result.chisq), float(result.S), float(result.Q)
    niter = int(result.niter)
    # One entry, not a trace: the compiled optimiser does not hand back its
    # per-iteration path, and `dgrad` has no final value to report. The api
    # layer reads this with a default, so a one-element history is well-formed.
    history = [(chisq, S, Q, float("nan"))]
    if progress_cb is not None:
        progress_cb(niter, chisq, S, Q, float("nan"))

    return {
        "p": np.asarray(result.p, dtype=float),
        "chisq": chisq,
        "S": S,
        "Q": Q,
        "history": history,
        "p_esm": np.asarray(result.p_esm, dtype=float),
        "chisq_esm": float(result.chisq_esm),
        "S_esm": float(result.S_esm),
        "Q_esm": float(result.Q_esm),
        "nu": float(nu),
        "niter": niter,
    }


def solve_lifetime_mem(
    decay: Sequence[float],
    lamp: Sequence[float],
    dt: float,
    tau: Optional[Sequence[float]] = None,
    timeshift: float = 0.0,
    background: float = 0.0,
    lamp_scatter: float = 0.0,
    fitrange: Optional[Tuple[int, int]] = None,
    irf_background: Optional[float] = None,
    fit_start_fraction: float = 0.9,
    nu: float = 1e-5,
    progress_cb: Optional[Callable[[int, float, float, float, float], None]] = None,
    max_iter: int = 200,
    tol: float = 1e-4,
    period: Optional[float] = None,
    optimize_nuisance: bool = False,
    nuisance_max_iter: int = 20,
    nuisance_step_timeshift: Optional[float] = None,
    nuisance_step_background: Optional[float] = None,
    nuisance_step_irf_background: Optional[float] = None,
    nuisance_step_x_donly: Optional[float] = None,
    nuisance_param_tol: float = 1e-3,
    prior: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """MEM analysis of TCSPC lifetimes (Python analogue of me_vin4.m).

    The default lifetime grid spans 1.0–4.0 ns with 0.01 ns spacing, i.e.
    ``tau = np.arange(1.0, 4.0 + 1e-9, 0.01)``.

    Parameters
    ----------
    timeshift:
        IRF shift relative to the decay in detector channels (samples).
    """
    decay_arr = np.asarray(decay, dtype=float).ravel()
    lamp_arr = np.asarray(lamp, dtype=float).ravel()

    if fitrange is None:
        try:
            if isinstance(lamp_scatter, (tuple, list)) and len(lamp_scatter) == 2:
                fitrange = (int(lamp_scatter[0]), int(lamp_scatter[1]))
                lamp_scatter = 0.0
        except Exception:
            pass

    # IRF background correction: subtract constant offset from lamp and clamp
    if irf_background is None:
        tail_len_lamp = min(500, lamp_arr.size)
        if tail_len_lamp > 0:
            irf_bg_val = float(np.median(lamp_arr[-tail_len_lamp:]))
        else:
            irf_bg_val = 0.0
    else:
        irf_bg_val = float(irf_background)

    lamp_corr = lamp_arr - irf_bg_val
    lamp_corr[lamp_corr < 0.0] = 0.0

    if tau is None:
        tau_arr = np.arange(1.0, 4.0 + 1e-9, 0.01, dtype=float)
    else:
        tau_arr = np.asarray(tau, dtype=float).ravel()

    tau_arr = tau_arr[tau_arr > 0.0]
    if tau_arr.size == 0:
        raise ValueError("tau grid must contain positive values")

    if fitrange is None:
        fitstart, fitstop = auto_fit_range_tcspc(
            decay_arr,
            count_threshold=100.0,
            area=0.999,
            start_fraction=float(fit_start_fraction),
            start_at_peak=True,
        )
    else:
        fitstart, fitstop = int(fitrange[0]), int(fitrange[1])

    if period is None:
        period_val = 0.0
    else:
        period_val = float(period)

    tail_len_decay = min(500, decay_arr.size)
    if tail_len_decay > 0:
        decay_bg_median = float(np.median(decay_arr[-tail_len_decay:]))
    else:
        decay_bg_median = 0.0

    bg0 = float(background) if background > 0.0 else decay_bg_median
    ts0 = float(timeshift)
    irf_bg0 = float(irf_bg_val)

    if prior is None:
        prior_vec = np.ones_like(tau_arr, dtype=float)
        prior_vec /= float(np.sum(prior_vec))
    else:
        prior_vec = np.asarray(prior, dtype=float).ravel()
        if prior_vec.size != tau_arr.size:
            raise ValueError("prior must have same length as tau grid")
        prior_vec[prior_vec <= 0.0] = MIN_PROB
        prior_vec /= float(np.sum(prior_vec))

    def _eval_mem_lifetime_single(ts_val: float, bg_val: float, irf_bg_single: float) -> Dict[str, Any]:
        if irf_bg_single == irf_bg_val:
            lamp_corr_single = lamp_corr
        else:
            lamp_corr_single = lamp_arr - irf_bg_single
            lamp_corr_single[lamp_corr_single < 0.0] = 0.0

        Fi_single, y_single, sigma_single, fit_additive = _build_Fi_lifetimes(
            decay_arr,
            lamp_corr_single,
            float(dt),
            tau_arr,
            float(ts_val),
            float(bg_val),
            float(lamp_scatter),
            int(fitstart),
            int(fitstop),
            period_val,
        )

        y_eff = y_single - fit_additive
        y_w = y_eff / sigma_single

        M_single = float(y_single.size)
        H_single = (2.0 / M_single) * (Fi_single.T @ Fi_single)
        g0_single = (2.0 / M_single) * (y_w @ Fi_single)
        const_chi2_single = float(np.sum(y_w * y_w) / M_single)

        m_single = prior_vec

        res_single = _run_mem(
            H_single,
            g0_single,
            m_single,
            const_chi2_single,
            float(nu),
            progress_cb=progress_cb,
            max_iter=int(max_iter),
            tol=float(tol),
            min_prob=MIN_PROB,
        )

        res_single.update(
            {
                "tau": tau_arr,
                "fitrange": (int(fitstart), int(fitstop)),
                "dt": float(dt),
                "timeshift": float(ts_val),
                "background": float(bg_val),
                "lamp_scatter": float(lamp_scatter),
                "fit_additive": fit_additive,
                "irf_background": float(irf_bg_single),
                "nu_input": float(nu),
                "H": H_single,
                "g0": g0_single,
                "y": y_single,
                "sigma": sigma_single,
                "Fi": Fi_single,
                "prior": prior_vec,
            }
        )
        return res_single

    if not optimize_nuisance:
        # Fast path: delegate to tttrlib's C++ MEM engine when available.
        # Matches the Python path below exactly (same H, g0, const, m, nu);
        # see tttrlib::solve_tcspc_mem_lifetime (MaxEntTcspc.h).
        try:
            import tttrlib as _ttl
            if hasattr(_ttl, "solve_tcspc_mem_lifetime"):
                irf_bg_val_l = float(irf_bg_val)
                bg_val_used = float(background)  # NB: Python path passes the raw
                # background argument (0.0 by default), NOT bg0 (the median).
                lamp_corr_l = lamp_arr - irf_bg_val_l
                lamp_corr_l[lamp_corr_l < 0.0] = 0.0
                if prior is None:
                    prior_vec_l = np.ones_like(tau_arr, dtype=float)
                    prior_vec_l /= float(np.sum(prior_vec_l))
                else:
                    prior_vec_l = np.asarray(prior, dtype=float).ravel()
                    if prior_vec_l.size != tau_arr.size:
                        raise ValueError("prior must have same length as tau grid")
                    prior_vec_l[prior_vec_l <= 0.0] = MIN_PROB
                    prior_vec_l /= float(np.sum(prior_vec_l))
                cpp = _ttl.solve_tcspc_mem_lifetime(
                    decay_arr.tolist(), lamp_corr_l.tolist(), float(dt),
                    tau_arr.tolist(), float(ts0), float(bg_val_used), float(lamp_scatter),
                    int(fitstart), int(fitstop), float(period_val),
                    nu=float(nu), max_iter=int(max_iter), tol=float(tol),
                    min_prob=MIN_PROB, prior=prior_vec_l.tolist(),
                )
                # The C++ engine returns only the MEM solution, but every
                # consumer (the GUI plots, the sampler, the saved result) needs
                # the design matrix and the fitted segment it was solved
                # against. Rebuild them from the arguments the engine was given
                # -- the same call the Python path makes -- so both paths return
                # one contract.
                Fi_l, y_l, sigma_l, fit_additive_l = _build_Fi_lifetimes(
                    decay_arr,
                    lamp_corr_l,
                    float(dt),
                    tau_arr,
                    float(ts0),
                    bg_val_used,
                    float(lamp_scatter),
                    int(fitstart),
                    int(fitstop),
                    period_val,
                )
                M_l = float(y_l.size)
                y_w_l = (y_l - fit_additive_l) / sigma_l
                p_cpp = np.asarray(cpp.p)
                result = {
                    "p": p_cpp,
                    "chisq": float(cpp.chisq),
                    "S": float(cpp.S),
                    "Q": float(cpp.Q),
                    "p_esm": np.asarray(cpp.p_esm),
                    "chisq_esm": float(cpp.chisq_esm),
                    "S_esm": float(cpp.S_esm),
                    "Q_esm": float(cpp.Q_esm),
                    "nu": float(nu),
                    "niter": int(cpp.niter),
                    "tau": tau_arr,
                    "fitrange": (int(fitstart), int(fitstop)),
                    "dt": float(dt),
                    "timeshift": float(ts0),
                    # what the engine was actually given, not the median bg0.
                    "background": bg_val_used,
                    "lamp_scatter": float(lamp_scatter),
                    "fit_additive": fit_additive_l,
                    "irf_background": float(irf_bg_val_l),
                    "nu_input": float(nu),
                    "H": (2.0 / M_l) * (Fi_l.T @ Fi_l),
                    "g0": (2.0 / M_l) * (y_w_l @ Fi_l),
                    "y": y_l,
                    "sigma": sigma_l,
                    "Fi": Fi_l,
                    "prior": prior_vec_l,
                    "nuisance_optimized": False,
                }
                return result
        except Exception:
            pass  # fall back to the Python MEM path below

        result = _eval_mem_lifetime_single(ts0, float(background), irf_bg0)
        result["nuisance_optimized"] = False
        return result

    if nuisance_step_timeshift is None:
        # timeshift is in channels (samples)
        step_ts = 0.5
    else:
        step_ts = float(abs(nuisance_step_timeshift))

    if nuisance_step_background is None:
        step_bg = 0.5 * max(bg0, 1.0)
    else:
        step_bg = float(abs(nuisance_step_background))

    if nuisance_step_irf_background is None:
        step_irf = 0.5 * max(irf_bg0, 1.0)
    else:
        step_irf = float(abs(nuisance_step_irf_background))

    steps = np.array([step_ts, step_bg, step_irf], dtype=float)

    max_shift_channels = 20.0
    ts_min = -max_shift_channels
    ts_max = max_shift_channels
    lower_bounds = np.array([ts_min, 0.0, 0.0], dtype=float)
    upper_bounds = np.array([ts_max, np.inf, np.inf], dtype=float)

    eval_history = []

    def _objective(x_vec: np.ndarray) -> Tuple[float, Dict[str, Any]]:
        x_clipped = np.minimum(np.maximum(x_vec, lower_bounds), upper_bounds)
        res_loc = _eval_mem_lifetime_single(
            float(x_clipped[0]), float(x_clipped[1]), float(x_clipped[2])
        )
        Q_loc = float(res_loc["Q"])
        chisq_loc = float(res_loc["chisq"])
        eval_history.append(
            {
                "params": x_clipped.copy(),
                "Q": Q_loc,
                "chisq": chisq_loc,
            }
        )
        return Q_loc, res_loc

    x_best = np.array([ts0, bg0, irf_bg0], dtype=float)
    Q_best, res_best = _objective(x_best)
    steps_cur = steps.copy()
    param_tol = float(nuisance_param_tol)

    for _ in _mem_trange(int(nuisance_max_iter)):
        improved = False
        for i in range(3):
            for sign in (1.0, -1.0):
                trial = x_best.copy()
                trial[i] += sign * steps_cur[i]
                Q_trial, res_trial = _objective(trial)
                if Q_trial < Q_best:
                    Q_best = Q_trial
                    x_best = trial
                    res_best = res_trial
                    improved = True
                    break
            if improved:
                continue
        if not improved:
            steps_cur *= 0.5
            if np.all(steps_cur < param_tol):
                break

    res_best["nuisance_optimized"] = True
    res_best["nuisance_result"] = {
        "initial": np.array([ts0, bg0, irf_bg0], dtype=float),
        "best": x_best,
        "steps_final": steps_cur,
        "eval_history": eval_history,
    }
    return res_best


def solve_fret_mem(
    decay: Sequence[float],
    lamp: Sequence[float],
    dt: float,
    R: Optional[Sequence[float]] = None,
    tau0: float = 4.1,
    R0: float = 52.0,
    donly: Optional[Sequence[float]] = None,
    x_donly: float = 0.0,
    timeshift: float = 0.0,
    background: float = 0.0,
    lamp_scatter: float = 0.0,
    fitrange: Optional[Tuple[int, int]] = None,
    irf_background: Optional[float] = None,
    fit_start_fraction: float = 0.9,
    nu: float = 1e-5,
    progress_cb: Optional[Callable[[int, float, float, float, float], None]] = None,
    max_iter: int = 200,
    tol: float = 1e-4,
    period: Optional[float] = None,
    optimize_nuisance: bool = False,
    nuisance_max_iter: int = 20,
    nuisance_step_timeshift: Optional[float] = None,
    nuisance_step_background: Optional[float] = None,
    nuisance_step_irf_background: Optional[float] = None,
    nuisance_step_x_donly: Optional[float] = None,
    nuisance_param_tol: float = 1e-3,
    prior: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """Maximum-entropy inversion of a FRET decay to a distance distribution.

    The me_vin4_E.m workflow: the design matrix is built by the photon library,
    the entropy-regularised quadratic program is iterated here.

    Parameters
    ----------
    decay : array_like
        Measured decay counts vs time.
    lamp : array_like
        Instrument response function on the same time grid.
    dt : float
        Time step per channel (same units as ``tau0``).
    R : array_like, optional
        Distance grid. Default is 18:0.5:120 as in me_vin4_E.m.
    tau0 : float, optional
        Donor lifetime in the absence of FRET.
    R0 : float, optional
        Förster radius.
    donly : array_like, optional
        Donor-only decay as [c1, tau1, c2, tau2, ...]. Default [1, tau0].
    timeshift : float, optional
        IRF shift relative to the decay in detector channels (samples).
    background : float, optional
        Constant background added to the model.
    lamp_scatter : float, optional
        Lamp scatter coefficient multiplied by the IRF.
    fitrange : (int, int), optional
        0-based inclusive start/stop indices for the fit range. If None,
        use :func:`autofitrange` on ``lamp`` and ``decay``.
    nu : float, optional
        Entropy Lagrange multiplier (regularization strength).
    max_iter : int, optional
        Maximum number of MEM iterations.
    tol : float, optional
        Stopping criterion on the gradient angle (dgrad).
    period : float, optional
        Excitation period. If None or <= 0, a single-shot convolution is used.

    Returns
    -------
    result : dict
        Dictionary with keys ``p`` (distance distribution), ``R``, ``chisq``,
        ``S``, ``Q``, ``history`` and additional diagnostic information.
    """

    decay_arr = np.asarray(decay, dtype=float).ravel()
    lamp_arr = np.asarray(lamp, dtype=float).ravel()

    if R is None:
        R_arr = np.arange(18.0, 120.0 + 1e-9, 0.5, dtype=float)
    else:
        R_arr = np.asarray(R, dtype=float).ravel()

    if donly is None:
        donly_arr = np.array([1.0, float(tau0)], dtype=float)
    else:
        donly_arr = np.asarray(donly, dtype=float).ravel()

    # IRF background correction: subtract constant offset from lamp and clamp
    if irf_background is None:
        tail_len_lamp = min(500, lamp_arr.size)
        if tail_len_lamp > 0:
            irf_bg_val = float(np.median(lamp_arr[-tail_len_lamp:]))
        else:
            irf_bg_val = 0.0
    else:
        irf_bg_val = float(irf_background)

    if fitrange is None:
        fitstart, fitstop = auto_fit_range_tcspc(
            decay_arr,
            count_threshold=100.0,
            area=0.999,
            start_fraction=float(fit_start_fraction),
            start_at_peak=True,
        )
    else:
        fitstart, fitstop = int(fitrange[0]), int(fitrange[1])

    if period is None:
        period_val = 0.0
    else:
        period_val = float(period)

    if prior is None:
        prior_vec = np.ones_like(R_arr, dtype=float)
        prior_vec /= float(np.sum(prior_vec))
    else:
        prior_vec = np.asarray(prior, dtype=float).ravel()
        if prior_vec.size != R_arr.size:
            raise ValueError("prior must have same length as R grid")
        prior_vec[prior_vec <= 0.0] = MIN_PROB
        prior_vec /= float(np.sum(prior_vec))

    def _eval_mem_distance_single(
        ts_val: float,
        bg_val: float,
        irf_bg_single: float,
        x_donly_val: float,
    ) -> Dict[str, Any]:
        Fi, y, sigma, fit_additive = _build_Fi_distances(
            decay_arr,
            lamp_arr,
            float(dt),
            R_arr,
            float(tau0),
            float(R0),
            donly_arr,
            float(x_donly_val),
            float(ts_val),
            float(bg_val),
            float(lamp_scatter),
            int(fitstart),
            int(fitstop),
            period_val,
            float(irf_bg_single),
        )
        y_eff = y - fit_additive

        # Weighted data vector y/sigma for the least-squares terms.
        y_w = y_eff / sigma

        M = y.size
        H = (2.0 / M) * (Fi.T @ Fi)
        g0 = (2.0 / M) * (y_w @ Fi)
        const_chi2 = float(np.sum(y_w * y_w) / M)

        m = prior_vec

        res_single = _run_mem(
            H,
            g0,
            m,
            const_chi2,
            float(nu),
            progress_cb=progress_cb,
            max_iter=int(max_iter),
            tol=float(tol),
            min_prob=MIN_PROB,
        )

        res_single.update(
            {
                "R": R_arr,
                "tau0": float(tau0),
                "R0": float(R0),
                "donly": donly_arr,
                "x_donly": float(x_donly_val),
                "fit_additive": fit_additive,
                "fitrange": (int(fitstart), int(fitstop)),
                "dt": float(dt),
                "timeshift": float(ts_val),
                "background": float(bg_val),
                "lamp_scatter": float(lamp_scatter),
                "irf_background": float(irf_bg_single),
                "nu_input": float(nu),
                "Fi": Fi,
                "H": H,
                "g0": g0,
                "y": y,
                "sigma": sigma,
                "prior": prior_vec,
            }
        )
        return res_single

    if not optimize_nuisance:
        result = _eval_mem_distance_single(float(timeshift), float(background), float(irf_bg_val), float(x_donly))
        result["nuisance_optimized"] = False
        return result

    ts0 = float(timeshift)
    bg0 = float(background)
    if bg0 <= 0.0:
        tail_len_decay = min(500, decay_arr.size)
        if tail_len_decay > 0:
            bg0 = float(np.median(decay_arr[-tail_len_decay:]))
        else:
            bg0 = 0.0
    irf_bg0 = float(irf_bg_val)

    x0 = float(x_donly)
    if x0 < 0.0:
        x0 = 0.0
    if x0 > 1.0:
        x0 = 1.0

    if nuisance_step_timeshift is None:
        # timeshift is in channels (samples)
        step_ts = 0.5
    else:
        step_ts = float(abs(nuisance_step_timeshift))

    if nuisance_step_background is None:
        step_bg = 0.5 * max(bg0, 1.0)
    else:
        step_bg = float(abs(nuisance_step_background))

    if nuisance_step_irf_background is None:
        step_irf = 0.5 * max(irf_bg0, 1.0)
    else:
        step_irf = float(abs(nuisance_step_irf_background))

    if nuisance_step_x_donly is None:
        step_x = 0.05
    else:
        step_x = float(abs(nuisance_step_x_donly))

    steps = np.array([step_ts, step_bg, step_irf, step_x], dtype=float)

    max_shift_channels = 20.0
    ts_min = -max_shift_channels
    ts_max = max_shift_channels
    lower_bounds = np.array([ts_min, 0.0, 0.0, 0.0], dtype=float)
    upper_bounds = np.array([ts_max, np.inf, np.inf, 1.0], dtype=float)

    eval_history = []

    def _objective(x_vec: np.ndarray) -> Tuple[float, Dict[str, Any]]:
        x_clipped = np.minimum(np.maximum(x_vec, lower_bounds), upper_bounds)
        res_loc = _eval_mem_distance_single(
            float(x_clipped[0]), float(x_clipped[1]), float(x_clipped[2]), float(x_clipped[3])
        )
        Q_loc = float(res_loc["Q"])
        chisq_loc = float(res_loc["chisq"])
        eval_history.append(
            {
                "params": x_clipped.copy(),
                "Q": Q_loc,
                "chisq": chisq_loc,
            }
        )
        return Q_loc, res_loc

    x_best = np.array([ts0, bg0, irf_bg0, x0], dtype=float)
    Q_best, res_best = _objective(x_best)
    steps_cur = steps.copy()
    param_tol = float(nuisance_param_tol)

    for _ in _mem_trange(int(nuisance_max_iter)):
        improved = False
        for i in range(4):
            for sign in (1.0, -1.0):
                trial = x_best.copy()
                trial[i] += sign * steps_cur[i]
                Q_trial, res_trial = _objective(trial)
                if Q_trial < Q_best:
                    Q_best = Q_trial
                    x_best = trial
                    res_best = res_trial
                    improved = True
                    break
            if improved:
                continue
        if not improved:
            steps_cur *= 0.5
            if np.all(steps_cur < param_tol):
                break

    res_best["nuisance_optimized"] = True
    res_best["nuisance_result"] = {
        "initial": np.array([ts0, bg0, irf_bg0, x0], dtype=float),
        "best": x_best,
        "steps_final": steps_cur,
        "eval_history": eval_history,
    }
    return res_best


__all__ = [
    "MIN_PROB",
    "load_tcspc_two_column",
    "auto_fit_range_tcspc",
    "solve_lifetime_mem",
    "solve_fret_mem",
]
