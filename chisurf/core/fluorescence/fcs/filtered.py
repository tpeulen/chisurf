import numpy as np


def calc_lifetime_filter(
        decays,
        experimental_decay,
        normalize_patterns: bool = True
) -> np.array:
    """
    Calculate lifetime filters for fluorescence lifetime correlation spectroscopy.

    This function computes filter coefficients for lifetime‐filtered correlations
    following the method described by Enderlein and co‐workers [1]. Given a list
    of fluorescence decay patterns (representing different decay components) and
    an experimental decay curve (assumed to be a linear combination of the patterns),
    the algorithm derives a filter matrix that can be used to extract the individual
    component contributions from the experimental decay.

    The procedure is as follows:

      1. Optionally normalize each decay pattern so that its sum equals one.
      2. Stack the (normalized) decay patterns into a matrix M.
      3. Form a diagonal matrix D with elements given by the inverse of the
         experimental decay (zero bins are guarded to avoid division by zero).
      4. Compute the pseudo-inverse of the product M · D · Mᵀ.
      5. Multiply the pseudo-inverse with M and D to obtain the filter matrix R.

    The filters satisfy the defining fluorescence-lifetime-filter relation
    ``sum_t R_k(t) · p_j(t) = delta_kj`` for the normalized patterns ``p_j`` (no
    additional global rescaling is applied).

    Parameters
    ----------
    decays : list of np.array
        A list of 1D arrays representing fluorescence decay curves for different
        components.
    experimental_decay : np.array
        A 1D array representing the experimental fluorescence decay (a linear
        combination of the decay patterns).
    normalize_patterns : bool, optional
        If True (default), each decay curve is normalized such that its sum equals one
        before computing the filters.

    Returns
    -------
    np.array
        A 2D array of filter coefficients. Each row corresponds to a filter for one
        decay component.

    Examples
    --------
    >>> import numpy as np
    >>> lifetime_1 = 1.0
    >>> lifetime_2 = 3.0
    >>> times = np.linspace(0, 20, num=10)
    >>> d1 = np.exp(-times/lifetime_1)
    >>> d2 = np.exp(-times/lifetime_2)
    >>> decays = [d1, d2]
    >>> w1 = 0.8  # weight of the first component
    >>> experimental_decay = w1 * d1 + (1.0 - w1) * d2
    >>> filters = calc_lifetime_filter(decays, experimental_decay)
    >>> filters  # doctest: +SKIP
    array([[ 1.19397553, -0.42328685, -1.94651679, -2.57788423, -2.74922322,
            -2.78989942, -2.79923872, -2.80136643, -2.80185031, -2.80196031],
           [-0.19397553,  1.42328685,  2.94651679,  3.57788423,  3.74922322,
             3.78989942,  3.79923872,  3.80136643,  3.80185031,  3.80196031]])

    References
    ----------
    [1] Kapusta, P., Wahl, M., Benda, A., Hof, M., & Enderlein, J. (2007).
        Fluorescence Lifetime Correlation Spectroscopy. Journal of Fluorescence,
        17, 43-48.
    [2] Enderlein, J., & Erdmann, R. (1997). Fast fitting of multi-exponential decay
        curves. Optics Communications, 134, 371-378.
    [3] Bohmer, M., Wahl, M., Rahn, H.-J., Erdmann, R., & Enderlein, J. (2002).
        Time-resolved fluorescence correlation spectroscopy. Chemical Physics Letters,
        353, 439-445.
    """
    # Normalize the fluorescence decays serving as references.
    if normalize_patterns:
        decay_patterns = [decay / decay.sum() for decay in decays]
    else:
        decay_patterns = decays
    # Guard against zero bins in the total decay before forming 1 / I; a zero
    # would otherwise produce inf/nan weights (PAM sets such bins to 1).
    experimental_safe = np.asarray(experimental_decay, dtype=float).copy()
    experimental_safe[experimental_safe == 0.0] = 1.0
    d = np.diag(1.0 / experimental_safe)
    m = np.stack(decay_patterns)
    iv = np.linalg.pinv(np.dot(m, np.dot(d, m.T)))
    r = np.dot(np.dot(iv, m), d)
    return r


def _ffcs_normal_matrix(experimental_decay, species_decays):
    """Build the weighted normal matrix ``G = D_norm^T W D_norm`` and its pieces.

    Parameters
    ----------
    experimental_decay : array_like
        1D total decay (one value per TAC bin).
    species_decays : sequence of array_like
        Species/pattern decays, each the same length as ``experimental_decay``.

    Returns
    -------
    y : np.ndarray
        The total decay as a float array.
    y_safe : np.ndarray
        The total decay with zero bins replaced by one.
    d_norm : np.ndarray
        Column-normalised pattern matrix, shape ``(n_bins, n_species)``.
    dw : np.ndarray
        ``D_norm^T * w`` with ``w = 1 / y_safe``, shape ``(n_species, n_bins)``.
    g : np.ndarray
        Weighted normal matrix ``D_norm^T W D_norm``, shape
        ``(n_species, n_species)``.
    """
    y = np.asarray(experimental_decay, dtype=float).copy()
    if y.ndim != 1:
        raise ValueError("experimental_decay must be a 1D array")

    d = np.column_stack([np.asarray(v, dtype=float) for v in species_decays])
    if d.ndim != 2:
        raise ValueError("species_decays must form a 2D matrix (bins × species)")

    # Normalize columns of D (Decay_par = Decay_par ./ sum(Decay_par,1))
    col_sums = d.sum(axis=0)
    col_sums[col_sums == 0.0] = 1.0
    d_norm = d / col_sums

    # Protect against zeros in the total decay before building the weights.
    y_safe = y.copy()
    y_safe[y_safe == 0.0] = 1.0
    w = 1.0 / y_safe

    dw = d_norm.T * w  # (n_species, n_bins)
    g = dw @ d_norm  # (n_species, n_species)
    return y, y_safe, d_norm, dw, g


def filter_condition_number(experimental_decay, species_decays) -> float:
    """Condition number of the fFCS weighted normal matrix ``D_norm^T W D_norm``.

    A large value (``>> 1``) signals that the reference patterns are nearly
    collinear (e.g. very similar lifetimes), so the resulting filters will be
    large and noise-amplifying; consider Tikhonov/``rcond`` conditioning in
    :func:`calc_ffcs_filters` or better-separated patterns.

    Parameters
    ----------
    experimental_decay : array_like
        1D total decay.
    species_decays : sequence of array_like
        Species/pattern decays.

    Returns
    -------
    float
        ``numpy.linalg.cond`` of the weighted normal matrix.
    """
    _, _, _, _, g = _ffcs_normal_matrix(experimental_decay, species_decays)
    return float(np.linalg.cond(g))


def uniform_pattern(n_bins: int) -> np.ndarray:
    """Return a flat (uniform) micro-time pattern of unit sum.

    Detector afterpulsing and dark counts are uncorrelated with the excitation
    pulse, so their micro-time distribution is (to first order) flat. Adding
    this pattern as an extra "species" in :func:`calc_ffcs_filters` builds a
    statistical filter that removes the afterpulsing/dark-count contribution
    from the correlation — the classic Enderlein afterpulse-free FLCS trick.

    Parameters
    ----------
    n_bins : int
        Number of micro-time (TAC) bins.

    Returns
    -------
    np.ndarray
        1D array of length ``n_bins`` with every element ``1 / n_bins``.
    """
    n = int(n_bins)
    if n <= 0:
        raise ValueError("n_bins must be positive")
    return np.full(n, 1.0 / n)


def photon_filter_weights(filters, micro_times) -> np.ndarray:
    """Map per-photon micro-times to their filter weights for each species.

    This is the per-photon weighting step used to feed lifetime filters into a
    weighted correlator: photon ``i`` with micro-time bin ``micro_times[i]``
    gets weight ``filters[s, micro_times[i]]`` for species ``s``. The returned
    rows are the weight streams passed to a correlator for every species
    auto-/cross-correlation pair.

    Parameters
    ----------
    filters : array_like
        2D filter matrix, shape ``(n_species, n_bins)``.
    micro_times : array_like
        1D integer micro-time (TAC) index per photon. Values are clipped into
        the valid ``[0, n_bins - 1]`` range.

    Returns
    -------
    np.ndarray
        2D array of shape ``(n_species, n_photons)`` with per-photon weights.
    """
    f = np.asarray(filters, dtype=float)
    if f.ndim != 2:
        raise ValueError("filters must be a 2D (n_species, n_bins) array")
    mt = np.asarray(micro_times).astype(int)
    mt = np.clip(mt, 0, f.shape[1] - 1)
    return f[:, mt]


def calc_ffcs_filters(
        experimental_decay,
        species_decays,
        rcond: float | None = None,
        tikhonov: float = 0.0,
):
    """Compute fFCS-style lifetime filters and reconstruction.

    This helper mirrors the weighted least-squares scheme used in PAM's
    ``Calc_fFCS_Filters`` implementation for filtered FCS/FLCS: with the
    column-normalized pattern matrix ``D_norm`` and the diagonal weight
    ``W = diag(1 / I)`` (``I`` the total decay), the filters are
    ``F = (D_norm^T W D_norm)^{-1} D_norm^T W``.

    Parameters
    ----------
    experimental_decay : array_like
        1D array with the total fluorescence decay (one value per TAC bin).
    species_decays : sequence of array_like
        Sequence of 1D arrays with species- (or pattern-) specific decays.
        Each element must have the same length as ``experimental_decay``. Add a
        :func:`uniform_pattern` as one entry to obtain afterpulsing-free filters.
    rcond : float, optional
        If given, invert the normal matrix with a truncated-SVD pseudo-inverse
        (``numpy.linalg.pinv(G, rcond=rcond)``) instead of a plain inverse. Use
        this when the patterns are near-collinear (see
        :func:`filter_condition_number`) to suppress noise amplification.
    tikhonov : float, optional
        Non-negative Tikhonov (ridge) regularisation added to the diagonal of
        the normal matrix (``G + tikhonov * I``) before inversion. ``0`` (the
        default) reproduces the unregularised PAM result.

    Returns
    -------
    filters : np.ndarray
        2D array with shape ``(n_species, n_bins)`` containing the filters
        (one row per species / pattern).
    reconstruction : np.ndarray
        1D array with the reconstructed total decay, obtained from the
        normalized patterns and filter matrix.
    weighted_residuals : np.ndarray
        1D array with weighted residuals,

        ``(experimental_decay - reconstruction) / sqrt(experimental_decay_safe)``.
    """
    y, y_safe, d_norm, dw, g = _ffcs_normal_matrix(experimental_decay, species_decays)

    if tikhonov:
        g = g + float(tikhonov) * np.eye(g.shape[0])

    # Invert G. A truncated-SVD pseudo-inverse (rcond) is used when requested or
    # as a fall-back if the plain inverse is singular.
    if rcond is not None:
        g_inv = np.linalg.pinv(g, rcond=rcond)
    else:
        try:
            g_inv = np.linalg.inv(g)
        except np.linalg.LinAlgError:
            g_inv = np.linalg.pinv(g)

    filters = g_inv @ dw  # (n_species, n_bins)

    # Reconstruction and weighted residuals as in the PAM implementation:
    # reconstruction = sum( (D^T W D)^{-1} D^T , 1)
    a = g_inv @ d_norm.T
    reconstruction = a.sum(axis=0)
    weighted_residuals = (y - reconstruction) / np.sqrt(y_safe)

    return filters, reconstruction, weighted_residuals
