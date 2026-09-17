from dataclasses import dataclass, field

import numpy as np


@dataclass
class SpeciesFilteredCorrelation:
    """Species-resolved lifetime-filtered correlation curves.

    Attributes
    ----------
    lag_s : numpy.ndarray
        Correlation lag times (seconds).
    auto : dict[int, numpy.ndarray]
        ``{species_index: G(tau)}`` species auto-correlations.
    cross : dict[tuple[int, int], numpy.ndarray]
        ``{(i, j): G(tau)}`` species cross-correlations (``i < j``).
    labels : list[str]
        Per-species labels, parallel to the species indices.
    """

    lag_s: np.ndarray
    auto: dict
    cross: dict
    labels: list = field(default_factory=list)


def _normalise_filter_table(filters):
    """Coerce a filter specification into a channel-aware table or a 2-D matrix.

    Parameters
    ----------
    filters : array_like or dict
        One of: a 2-D ``(n_species, n_bins)`` matrix (channel-agnostic); a 3-D
        ``(n_channels, n_species, n_bins)`` table; or a mapping
        ``{routing_channel: (n_species, n_bins)}``.

    Returns
    -------
    table : numpy.ndarray
        3-D ``(n_channels, n_species, n_bins)`` if channel-aware, else the 2-D
        matrix.
    channel_aware : bool
    n_species : int
    n_bins : int
    """
    if isinstance(filters, dict):
        n_ch = max(filters) + 1
        n_species, n_bins = np.asarray(next(iter(filters.values()))).shape
        table = np.zeros((n_ch, n_species, n_bins), dtype=float)
        for ch, f in filters.items():
            table[int(ch)] = np.asarray(f, dtype=float)
        return table, True, n_species, n_bins
    arr = np.asarray(filters, dtype=float)
    if arr.ndim == 3:
        return arr, True, arr.shape[1], arr.shape[2]
    if arr.ndim == 2:
        return arr, False, arr.shape[0], arr.shape[1]
    raise ValueError("filters must be 2-D, 3-D, or a {channel: 2-D} mapping")


def species_weight_streams(filters, micro_times, routing_channels=None):
    """Per-photon weight streams for every species (the correlator input).

    Channel-aware: when ``filters`` carries a per-channel dimension, photon
    ``i`` is weighted by ``filters[routing_channel[i], species, micro_time[i]]``
    (mirroring PAM's par/perp filter application); otherwise the single filter
    set is indexed by micro-time only.

    Parameters
    ----------
    filters : array_like or dict
        See :func:`_normalise_filter_table`.
    micro_times : array_like
        Per-photon micro-time (TAC) indices.
    routing_channels : array_like, optional
        Per-photon routing channel indices. Required for channel-aware filters.

    Returns
    -------
    list of numpy.ndarray
        One ``(n_photons,)`` float weight stream per species.
    """
    table, channel_aware, n_species, n_bins = _normalise_filter_table(filters)
    micro_idx = np.clip(np.asarray(micro_times), 0, n_bins - 1).astype(np.int64)
    if not channel_aware:
        return [np.ascontiguousarray(table[s, micro_idx], dtype=np.float64) for s in range(n_species)]

    if routing_channels is None:
        raise ValueError("routing_channels is required for channel-aware filters")

    ch = np.clip(np.asarray(routing_channels), 0, table.shape[0] - 1).astype(np.int64)
    return [
        np.ascontiguousarray(table[ch, s, micro_idx], dtype=np.float64)
        for s in range(n_species)
    ]


def species_filtered_correlation(
    macro_times,
    micro_times,
    filters,
    macro_time_resolution_s,
    *,
    routing_channels=None,
    n_bins: int = 8,
    n_casc: int = 25,
    labels=None,
    method: str = "wahl",
) -> SpeciesFilteredCorrelation:
    """Species auto-/cross-correlations weighted by lifetime filters.

    Applies the FLCS lifetime filters as per-photon weights and computes every
    species auto- and cross-correlation in ONE pass over the photon stream with
    ``tttrlib.Correlator.species_matrix_correlation``. This is the
    channel-aware generalisation of the 2D-FLC application path
    (``flc_2d.fit.dynamics.filtered_correlation``): with a per-channel filter
    table each detector's photons get that detector's filter.

    Every species pair correlates the *same* arrival times and differs only in
    the per-photon weights, so the two weight-independent halves of the
    multi-tau kernel -- coarsening the time axis and the pointer walk that
    finds each photon's partners -- are shared by all pairs and are done once
    upstream; only the innermost product carries the species dimension. The
    ``n(n+1)/2`` separate correlator passes this replaced re-did both per pair.
    The result is bit-identical to that composition single-threaded, not merely
    close (the coarsening's only weight-dependent step is a zero-drop, which
    cannot change the estimator).

    The per-photon channel-aware weighting mirrors ``tttrlib.Correlator``'s
    native ``set_filter`` (which maps ``{routing_channel: micro_time -> weight}``
    onto the photons); it is done here via weight streams so the same code path
    serves both species auto- and cross-correlations (where the two sides need
    *different* species filters, which a single ``set_filter`` map cannot express).

    Parameters
    ----------
    macro_times : array_like
        Photon macro-times in clock ticks (ascending).
    micro_times : array_like
        Per-photon micro-time (TAC) indices (same length as ``macro_times``).
    filters : array_like or dict
        Lifetime filters — 2-D ``(n_species, n_bins)``, 3-D
        ``(n_channels, n_species, n_bins)``, or ``{channel: 2-D}``.
    macro_time_resolution_s : float
        Seconds per macro-time tick (converts the lag axis to seconds).
    routing_channels : array_like, optional
        Per-photon routing channel indices (required for channel-aware filters).
    n_bins, n_casc : int, optional
        Multi-tau correlator settings.
    labels : sequence of str, optional
        Species labels.
    method : str, optional
        Correlation method (``"wahl"``, ``"felekyan"``, ``"laurence"``). Only
        ``"wahl"`` has the single-pass kernel; the others are composed pair by
        pair upstream — correct, but without the batching win.

    Returns
    -------
    SpeciesFilteredCorrelation
    """
    import tttrlib

    if not hasattr(tttrlib.Correlator, "species_matrix_correlation"):
        raise RuntimeError(
            "tttrlib.Correlator.species_matrix_correlation is missing: the installed "
            "tttrlib predates the batched species-matrix (fFCS) entry point. "
            "Rebuild tttrlib (`pixi run build-tttrlib`)."
        )

    macro = np.ascontiguousarray(macro_times, dtype=np.uint64)
    streams = species_weight_streams(filters, micro_times, routing_channels)
    n_species = len(streams)
    weight_matrix = np.ascontiguousarray(np.vstack(streams), dtype=np.float64)

    x_axis, matrix = tttrlib.Correlator.species_matrix_correlation(
        macro, weight_matrix, int(n_bins), int(n_casc), str(method)
    )
    lag = np.asarray(x_axis, dtype=float) * macro_time_resolution_s

    auto: dict = {}
    cross: dict = {}
    for i in range(n_species):
        for j in range(i, n_species):
            # packed upper-triangular, row-major: (0,0), (0,1), ..., (1,1), ...
            row = matrix[i * n_species - i * (i - 1) // 2 + (j - i)]
            if i == j:
                auto[i] = np.asarray(row, dtype=float)
            else:
                cross[(i, j)] = np.asarray(row, dtype=float)

    labels = list(labels) if labels is not None else [f"species_{i}" for i in range(n_species)]
    return SpeciesFilteredCorrelation(lag_s=lag, auto=auto, cross=cross, labels=labels)


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


_EMPTY_BIN_MODES = ("unit_weight", "exclude")


def _ffcs_normal_matrix(experimental_decay, species_decays, empty_bins="unit_weight"):
    """Build the weighted normal matrix ``G = D_norm^T W D_norm`` and its pieces.

    A bin where the total decay ``I`` is zero has no defined weight ``1 / I``.
    PAM resolves this two ways, and ``empty_bins`` selects between them:

    ``"unit_weight"``
        Replace ``I = 0`` by one and keep every bin; patterns are normalised
        over all bins, so ``sum_t F_k(t) p_j(t) = delta_kj`` holds on the whole
        micro-time axis and a species' mean filtered count rate is its
        amplitude. PAM's BurstBrowser ``Calc_fFCS_Filters.m``.
    ``"exclude"``
        Drop the empty bins; patterns are renormalised over the occupied bins
        and the filters are zero on the empty ones. The relation then holds on
        the occupied bins only, so a species' mean filtered count rate is its
        amplitude times the pattern fraction on those bins (a scale that
        cancels in normalised correlations). PAM's main-window fFCS filters
        (``PAM.m``, ``Update_fFCS_GUI``).

    The two agree exactly when no bin is empty.

    Parameters
    ----------
    experimental_decay : array_like
        1D total decay (one value per TAC bin).
    species_decays : sequence of array_like
        Species/pattern decays, each the same length as ``experimental_decay``.
    empty_bins : {"unit_weight", "exclude"}
        Treatment of bins where the total decay is zero (see above).

    Returns
    -------
    y : np.ndarray
        The total decay as a float array (all bins).
    used : np.ndarray
        Boolean mask of the bins entering the problem.
    d_norm : np.ndarray
        Pattern matrix on the used bins, column-normalised over them, shape
        ``(n_used, n_species)``.
    dw : np.ndarray
        ``D_norm^T * w`` with ``w = 1 / I`` on the used bins, shape
        ``(n_species, n_used)``.
    g : np.ndarray
        Weighted normal matrix ``D_norm^T W D_norm``, shape
        ``(n_species, n_species)``.
    """
    if empty_bins not in _EMPTY_BIN_MODES:
        raise ValueError(f"empty_bins must be one of {_EMPTY_BIN_MODES}, got {empty_bins!r}")
    y = np.asarray(experimental_decay, dtype=float).copy()
    if y.ndim != 1:
        raise ValueError("experimental_decay must be a 1D array")

    d = np.column_stack([np.asarray(v, dtype=float) for v in species_decays])
    if d.ndim != 2:
        raise ValueError("species_decays must form a 2D matrix (bins × species)")

    if empty_bins == "exclude":
        used = y != 0.0
    else:
        used = np.ones(y.size, dtype=bool)
    d_used = d[used]
    col_sums = d_used.sum(axis=0)
    col_sums[col_sums == 0.0] = 1.0
    d_norm = d_used / col_sums

    y_used = y[used]
    y_used[y_used == 0.0] = 1.0
    w = 1.0 / y_used
    dw = d_norm.T * w  # (n_species, n_used)
    g = dw @ d_norm  # (n_species, n_species)
    return y, used, d_norm, dw, g


def filter_condition_number(experimental_decay, species_decays, empty_bins="unit_weight") -> float:
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
    empty_bins : {"unit_weight", "exclude"}
        Treatment of empty total-decay bins, as in :func:`calc_ffcs_filters`.

    Returns
    -------
    float
        ``numpy.linalg.cond`` of the weighted normal matrix.
    """
    _, _, _, _, g = _ffcs_normal_matrix(experimental_decay, species_decays, empty_bins)
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
        empty_bins: str = "unit_weight",
):
    """Compute fFCS-style lifetime filters and reconstruction.

    This is PAM's weighted least-squares filter scheme: with the column-
    normalised pattern matrix ``D_norm`` and the diagonal weight
    ``W = diag(1 / I)`` (``I`` the total decay), the filters are
    ``F = (D_norm^T W D_norm)^{-1} D_norm^T W``. ``empty_bins`` chooses how a
    bin with ``I = 0`` is treated -- PAM's two filter routines differ exactly
    there (see ``_ffcs_normal_matrix``). Several detection channels (e.g.
    parallel and perpendicular) are handled jointly by passing the channels
    concatenated on one micro-time axis, PAM's stacked layout; the filter then
    also uses each species' channel ratio as contrast.

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
    empty_bins : {"unit_weight", "exclude"}
        ``"unit_weight"`` (default) sets ``I = 1`` on empty bins and keeps them,
        as PAM's BurstBrowser fFCS does; ``"exclude"`` drops them, renormalises
        the patterns over the occupied bins and zeroes the filters on the empty
        ones, as PAM's main-window fFCS does.

    Returns
    -------
    filters : np.ndarray
        2D array with shape ``(n_species, n_bins)`` containing the filters
        (one row per species / pattern).
    reconstruction : np.ndarray
        1D array ``sum_k [(D_norm^T W D_norm)^{-1} D_norm^T]_k`` per bin (PAM's
        filter-quality trace), zero on bins left out.
    weighted_residuals : np.ndarray
        1D array ``(experimental_decay - reconstruction) / sqrt(I_safe)`` with
        ``I_safe`` the total decay with zero bins replaced by one. (PAM's
        BurstBrowser puts the substituted one in the numerator as well; the
        measured zero is kept here.)
    """
    y, used, d_norm, dw, g = _ffcs_normal_matrix(experimental_decay, species_decays, empty_bins)

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

    n_species, n_bins = g.shape[0], y.size
    filters = np.zeros((n_species, n_bins))
    filters[:, used] = g_inv @ dw

    # Reconstruction and weighted residuals as in the PAM implementation:
    # reconstruction = sum( (D^T W D)^{-1} D^T , 1), zero on bins left out
    reconstruction = np.zeros(n_bins)
    reconstruction[used] = (g_inv @ d_norm.T).sum(axis=0)
    y_safe = np.where(y == 0.0, 1.0, y)
    weighted_residuals = (y - reconstruction) / np.sqrt(y_safe)

    return filters, reconstruction, weighted_residuals
