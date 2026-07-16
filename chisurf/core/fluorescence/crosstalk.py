"""General spectral crosstalk / linear-mixing utilities.

Crosstalk (spectral bleed-through, direct acceptor excitation, detector
mixing) is a single linear-algebra problem shared across ChiSurf: the light-path
calculator *builds* a forward mixing matrix
(:meth:`...lightpath_simulator...get_crosstalk_matrices`), ratiometric /
sensitized-emission FRET needs to *invert* it to recover true fluorophore
signals, and phasor-FLIM spectral unmixing solves the same constrained inverse.
This module is the Qt-free, array-based core those consumers share.

Conventions
-----------
A mixing matrix ``M`` has shape ``(n_sources, n_detectors)`` with
``M[i, j]`` = contribution of source ``i`` to detector ``j``. The forward model
is ``measured_j = sum_i source_i * M[i, j]`` (i.e. ``measured = Mᵀ @ sources``),
and the inverse recovers the sources from the measured detector signals.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "matrix_from_payload",
    "apply_mixing",
    "invert_mixing",
    "photon_shuffle_unmix",
    "correct_three_cube",
    "three_cube_fret_efficiency",
]


def matrix_from_payload(payload, rows=None, columns=None):
    """Build an ordered NumPy mixing matrix from a light-path crosstalk payload.

    Parameters
    ----------
    payload : dict
        A matrix payload as returned by ``get_crosstalk_matrices()`` — a mapping
        with ``"rows"`` (source labels), ``"columns"`` (detector labels) and a
        dense row-major ``"values"`` list (``values[row][col]``).
    rows, columns : sequence of str, optional
        Label subset/ordering to select. Defaults to the payload's own order.
        Requested labels missing from the payload contribute a zero row/column.

    Returns
    -------
    matrix : numpy.ndarray
        ``(len(rows), len(columns))`` mixing matrix.
    rows : list of str
        The row (source) labels, in the returned order.
    columns : list of str
        The column (detector) labels, in the returned order.
    """
    payload_rows = list(payload["rows"])
    payload_cols = list(payload["columns"])
    values = np.asarray(payload["values"], dtype=float)
    row_index = {label: i for i, label in enumerate(payload_rows)}
    col_index = {label: j for j, label in enumerate(payload_cols)}

    out_rows = list(rows) if rows is not None else payload_rows
    out_cols = list(columns) if columns is not None else payload_cols
    matrix = np.zeros((len(out_rows), len(out_cols)), dtype=float)
    for i, r in enumerate(out_rows):
        if r not in row_index:
            continue
        for j, c in enumerate(out_cols):
            if c in col_index:
                matrix[i, j] = values[row_index[r], col_index[c]]
    return matrix, out_rows, out_cols


def apply_mixing(matrix, sources):
    """Forward mixing: predict detector signals from source signals.

    Parameters
    ----------
    matrix : array_like
        ``(n_sources, n_detectors)`` mixing matrix.
    sources : array_like
        ``(n_sources,)`` or ``(n_sources, ...)`` source signals (per pixel/burst
        along trailing axes).

    Returns
    -------
    numpy.ndarray
        ``(n_detectors, ...)`` predicted detector signals.
    """
    m = np.asarray(matrix, dtype=float)
    s = np.asarray(sources, dtype=float)
    flat = s.reshape(s.shape[0], -1)
    out = m.T @ flat
    return out.reshape((m.shape[1],) + s.shape[1:])


def invert_mixing(matrix, measured, *, nonneg: bool = False, rcond=None, ridge: float = 0.0):
    """Inverse mixing: recover source signals from measured detector signals.

    Parameters
    ----------
    matrix : array_like
        ``(n_sources, n_detectors)`` mixing matrix.
    measured : array_like
        ``(n_detectors,)`` or ``(n_detectors, ...)`` measured signals.
    nonneg : bool, optional
        If True, solve a non-negative least squares per column
        (``scipy.optimize.nnls``) — the physically-constrained unmixing (sources
        cannot be negative) that stays stable when the mixing matrix is
        ill-conditioned (strong spectral overlap). Otherwise a (pseudo-)inverse
        least-squares solution, which is faster but can return negative sources
        and amplifies noise for near-singular ``matrix``.
    rcond : float, optional
        Cut-off passed to :func:`numpy.linalg.pinv` for the unconstrained solve.
    ridge : float, optional
        Tikhonov (ridge) regularization strength ``λ``. When ``> 0`` the solve
        minimises ``||Mᵀx − y||² + λ||x||²``, which damps the noise amplification
        of an ill-conditioned ``matrix`` at the cost of a small bias. Applies to
        both the unconstrained solve (closed form) and the non-negative solve (via
        an augmented system). ``0`` (default) is the plain least-squares inverse.

    Returns
    -------
    numpy.ndarray
        ``(n_sources, ...)`` recovered source signals.
    """
    m = np.asarray(matrix, dtype=float)
    y = np.asarray(measured, dtype=float)
    a = m.T  # detectors x sources
    n_src = a.shape[1]
    flat = y.reshape(y.shape[0], -1)
    if nonneg:
        from scipy.optimize import nnls

        if ridge and ridge > 0:
            # augmented rows sqrt(λ)·I with zero targets == ridge penalty
            a_solve = np.vstack([a, np.sqrt(ridge) * np.eye(n_src)])
            flat = np.vstack([flat, np.zeros((n_src, flat.shape[1]))])
        else:
            a_solve = a
        out = np.empty((n_src, flat.shape[1]), dtype=float)
        for k in range(flat.shape[1]):
            out[:, k], _ = nnls(a_solve, flat[:, k])
        return out.reshape((n_src,) + y.shape[1:])
    if ridge and ridge > 0:
        # Tikhonov closed form: x = (AᵀA + λI)⁻¹ Aᵀ y
        gram = a.T @ a + ridge * np.eye(n_src)
        solve = np.linalg.solve(gram, a.T)  # (n_src, n_det)
        out = solve @ flat
        return out.reshape((n_src,) + y.shape[1:])
    pinv = np.linalg.pinv(a, rcond=rcond) if rcond is not None else np.linalg.pinv(a)
    out = pinv @ flat
    return out.reshape((pinv.shape[0],) + y.shape[1:])


def photon_shuffle_unmix(counts, matrix, *, abundances=None, seed=None, rng=None):
    """Integer, statistics-preserving spectral unmixing by photon reassignment.

    The least-squares inverses (:func:`invert_mixing`) return *fractional* — and,
    unconstrained, negative — source estimates, which destroys the integer /
    Poisson nature of photon-counting data. This instead **reassigns each detected
    photon to a source**: every one of the ``counts[m]`` photons in detector ``m``
    is attributed to exactly one source ``k`` by a multinomial draw, so the result
    is a non-negative **integer** per-source photon stream.

    The assignment probability that a photon detected in channel ``m`` originated
    from source ``k`` is, by Bayes,

        P(k | m) ∝ a_k · B[k, m],   B[k, m] = matrix[k, m] / Σ_m matrix[k, m],

    where ``B`` is the row-normalised mixing matrix (each source's spectral shape,
    a probability distribution over detectors) and ``a_k`` the source abundance
    (from a non-negative least-squares fit if not supplied). The per-detector
    photons are then split across sources by a multinomial draw with these
    probabilities.

    Properties. The total photon count is preserved exactly (every detected photon
    is assigned once), the output is non-negative and integer, and — because a
    multinomial thinning of a Poisson count yields independent Poisson counts per
    bin — the shot-noise statistics are preserved, so downstream burst-variance /
    BVA / maximum-likelihood analyses see genuine photon-counting data. The
    expected assignment equals the soft (Richardson–Lucy / EM) unmixing, so the
    method is unbiased on average; the draw is the stochastic realisation of it.

    Parameters
    ----------
    counts : array_like
        ``(n_detectors,)`` or ``(n_detectors, ...)`` **integer** photon counts per
        detector (trailing axes are pixels/bursts).
    matrix : array_like
        ``(n_sources, n_detectors)`` mixing matrix (as elsewhere in this module).
    abundances : array_like, optional
        ``(n_sources, ...)`` source abundances used as the assignment prior. If
        omitted, they are estimated by ``invert_mixing(matrix, counts,
        nonneg=True)``.
    seed : int, optional
        Seed for a fresh ``numpy.random.default_rng`` when ``rng`` is not given.
    rng : numpy.random.Generator, optional
        Explicit random generator (takes precedence over ``seed``).

    Returns
    -------
    numpy.ndarray
        ``(n_sources, ...)`` non-negative integer per-source photon counts, with
        the same trailing shape as ``counts`` and ``sum_k out[k] == sum_m counts[m]``
        elementwise.
    """
    m = np.asarray(matrix, dtype=float)
    y = np.asarray(counts)
    n_src, n_det = m.shape
    generator = rng if rng is not None else np.random.default_rng(seed)

    # spectral shape B[k, m] = P(detector m | photon from source k)
    row = m.sum(axis=1, keepdims=True)
    b = np.divide(m, row, out=np.zeros_like(m), where=row > 0)

    yf = y.reshape(n_det, -1)  # (n_det, n_col)
    n_col = yf.shape[1]

    if abundances is None:
        a = invert_mixing(m, y, nonneg=True).reshape(n_src, -1)
    else:
        a = np.asarray(abundances, dtype=float).reshape(n_src, -1)
    a = np.clip(a, 0.0, None)

    out = np.zeros((n_src, n_col), dtype=np.int64)
    for det in range(n_det):
        # posterior over sources for photons in this detector: p[k] ∝ a_k B[k,det]
        w = a * b[:, det][:, None]  # (n_src, n_col)
        tot = w.sum(axis=0)  # (n_col,)
        # fall back to the spectral shape where no abundance mass is present
        spectral = b[:, det]
        sp_tot = spectral.sum()
        for k in range(n_src):
            p_k = np.where(tot > 0, w[k] / np.where(tot > 0, tot, 1.0),
                           (spectral[k] / sp_tot) if sp_tot > 0 else 0.0)
            w[k] = p_k
        # split the integer detector counts across sources via a binomial chain
        remaining = yf[det].astype(np.int64).copy()
        cum = np.zeros(n_col)
        for k in range(n_src):
            if k == n_src - 1:
                out[k] += remaining  # last source takes the rest -> exact preservation
                break
            denom = 1.0 - cum
            cond = np.divide(w[k], denom, out=np.zeros(n_col), where=denom > 1e-12)
            cond = np.clip(cond, 0.0, 1.0)
            draw = generator.binomial(remaining, cond)
            out[k] += draw
            remaining = remaining - draw
            cum = cum + w[k]
    return out.reshape((n_src,) + y.shape[1:])


def correct_three_cube(idd, ida, iaa, *, donor_leak: float, direct_excitation: float,
                       gamma: float = 1.0):
    """Three-cube ratiometric FRET correction (Gordon/Nagy).

    Corrects the measured raw FRET (acceptor-under-donor-excitation) channel for
    donor spectral bleed-through and direct acceptor excitation, using the
    donor-only (IDD) and acceptor-only (IAA) reference channels:

    ``Fc = IDA - donor_leak * IDD - direct_excitation * IAA``.

    Parameters
    ----------
    idd : array_like
        Donor emission under donor excitation (scalar or per-pixel/burst array).
    ida : array_like
        Raw FRET channel: acceptor emission under donor excitation.
    iaa : array_like
        Acceptor emission under acceptor excitation.
    donor_leak : float
        Donor bleed-through coefficient (``d``, donor signal fraction leaking
        into the FRET channel), calibrated from a donor-only sample.
    direct_excitation : float
        Direct acceptor-excitation coefficient (``a``), calibrated from an
        acceptor-only sample.
    gamma : float, optional
        Detection/quantum-yield correction factor (used by the efficiency).

    Returns
    -------
    dict
        ``{"fc": ..., "efficiency": ..., "ratio": ...}`` — the corrected
        sensitized emission ``Fc``, the apparent FRET efficiency
        ``Fc / (Fc + gamma * IDD)`` and the acceptor/donor ratio ``Fc / IDD``.
    """
    idd = np.asarray(idd, dtype=float)
    ida = np.asarray(ida, dtype=float)
    iaa = np.asarray(iaa, dtype=float)
    fc = ida - donor_leak * idd - direct_excitation * iaa
    efficiency = three_cube_fret_efficiency(fc, idd, gamma=gamma)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(idd != 0, fc / idd, 0.0)
    return {"fc": fc, "efficiency": efficiency, "ratio": ratio}


def three_cube_fret_efficiency(fc, idd, *, gamma: float = 1.0):
    """Apparent FRET efficiency ``Fc / (Fc + gamma * IDD)`` from corrected signals.

    Parameters
    ----------
    fc : array_like
        Corrected sensitized emission.
    idd : array_like
        Donor emission under donor excitation.
    gamma : float, optional
        Detection/quantum-yield correction factor.

    Returns
    -------
    numpy.ndarray
        Apparent FRET efficiency; zero where the denominator vanishes.
    """
    fc = np.asarray(fc, dtype=float)
    idd = np.asarray(idd, dtype=float)
    denom = fc + gamma * idd
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denom != 0, fc / denom, 0.0)
