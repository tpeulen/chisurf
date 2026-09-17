import logging

import numpy as np

from chisurf import typing

logger = logging.getLogger(__name__)


def _new_engine_seed() -> int:
    """Draw a seed for an ``IMP.bff`` Monte-Carlo call from the caller's RNG state.

    ``IMP.bff``'s kappa^2 samplers take an explicit integer seed and draw
    through tttrlib's centralized ``Random`` (see
    ``IMP.bff``'s ``include/internal/Random.h``, a vendored copy of
    ``tttrlib``'s ``include/Random.h``) rather than reading global state
    themselves. Chisurf's callers reproduce a run the way they always have --
    ``np.random.seed(...)`` before calling -- so one draw from that state
    turns into the engine's seed: seed numpy once, get the same engine
    stream every time; call twice without reseeding, get two different
    streams, matching the "fresh draw" a caller expects from an unseeded
    call.
    """
    return int(np.random.randint(0, 2 ** 31 - 1))


def kappasq_dwt(
        sD2: float,
        sA2: float,
        fret_efficiency: float,
        n_samples: int = 10000,
        n_bins: int = 31,
        k2_min: float = 0.0,
        k2_max: float = 4.0,
        seed: typing.Optional[int] = None,
):
    """
    Diffusion with traps.

    This function simulates a kappa² distribution in the presence of donor and
    acceptor dye trapping. It generates random donor and acceptor orientations,
    computes the orientation factor kappa² for each pair, and returns a histogram
    over the generated kappa² values.

    The Monte-Carlo sampling itself runs in ``IMP.bff``
    (``sample_kappa2_diffusion_with_traps``), which draws through tttrlib's
    centralized RNG rather than a locally-seeded generator; see
    :func:`_new_engine_seed` for how a caller's ``np.random.seed(...)``
    still makes a run reproducible.

    Parameters
    ----------
    sD2 : float
        Second rank order parameter S² of the donor dye (can correspond to the
        fraction of trapped donor dye).
    sA2 : float
        Second rank order parameter S² of the acceptor dye (can correspond to the
        fraction of trapped acceptor dye).
    fret_efficiency : float
        FRET efficiency.
    n_samples : int, optional
        Number of random vector pairs to generate (default: 10000).
    n_bins : int, optional
        Number of bins in the generated kappa² histogram (default: 31).
    k2_min : float, optional
        Lower bound of kappa² values for the histogram (default: 0.0).
    k2_max : float, optional
        Upper bound of kappa² values for the histogram (default: 4.0).
    seed : int, optional
        Seed for the engine's Monte-Carlo draw. When ``None`` (default), a
        seed is drawn from numpy's global RNG state, so seeding that state
        (``np.random.seed(...)``) before the call still makes the result
        reproducible.

    Returns
    -------
    tuple
        A tuple containing:
          - k2_scale (np.ndarray): The linear kappa² scale (bin edges).
          - k2hist (np.ndarray): The histogram counts of kappa².
          - k2s (np.ndarray): Array of computed kappa² values for each sample.

    Examples
    --------
    >>> import numpy as np
    >>> np.random.seed(42)  # Set seed for reproducibility in this example
    >>> k2_scale, k2hist, k2s = kappasq_dwt(sD2=0.3, sA2=0.4, fret_efficiency=0.5, n_samples=100, n_bins=11)
    >>> k2_scale  # doctest: +SKIP
    array([0. , 0.4, 0.8, 1.2, 1.6, 2. , 2.4, 2.8, 3.2, 3.6, 4. ])
    >>> k2hist.sum()  # doctest: +SKIP
    100
    """
    from IMP.bff import sample_kappa2_diffusion_with_traps as _f

    if seed is None:
        seed = _new_engine_seed()

    n_edges = n_bins
    n_counts = n_bins - 1
    buf = np.asarray(
        _f(sD2, sA2, fret_efficiency, n_samples, n_bins, k2_min, k2_max, seed),
        dtype=np.float64,
    )
    k2_scale = buf[:n_edges]
    k2hist = buf[n_edges:n_edges + n_counts]
    k2s = buf[n_edges + n_counts:n_edges + n_counts + n_samples]
    return k2_scale, k2hist, k2s


def kappasq_all_delta(
        delta: float,
        sD2: float,
        sA2: float,
        step: float = 0.25,
        n_bins: int = 31,
        k2_min: float = 0.0,
        k2_max: float = 4.0
) -> typing.Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Computes an orientation factor distribution for a wobbling-in-a-cone model
    for a given delta and dye order parameters.

    The function calculates the distribution p(kappa²) by sampling over beta1 and
    phi angles for a fixed delta. The result is a weighted histogram of computed
    kappa² values.

    Deterministic grid sweep, no Monte-Carlo sampling and no RNG -- the sweep
    runs in ``IMP.bff`` (``wobbling_kappa2_distribution_delta``).

    Parameters
    ----------
    delta : float
        Angle (in radians) between the symmetry axes of the dyes.
    sD2 : float
        Second rank order parameter S² of the donor dye.
    sA2 : float
        Second rank order parameter S² of the acceptor dye.
    step : float, optional
        Step size in degrees used for sampling angles (default: 0.25).
    n_bins : int, optional
        Number of bins in the resulting kappa² histogram (default: 31).
    k2_min : float, optional
        Lower bound for kappa² histogram (default: 0.0).
    k2_max : float, optional
        Upper bound for kappa² histogram (default: 4.0).

    Returns
    -------
    tuple
        A tuple containing:
          - k2scale (np.ndarray): Linear scale of kappa² values.
          - k2hist (np.ndarray): Histogram of kappa² values (weighted by sin(beta1)).
          - k2 (np.ndarray): Flat array of computed kappa² values, one per
            (beta1, phi) grid point in row-major order.
          - weights (np.ndarray): The solid-angle weight of each value. A
            moment taken over ``k2`` needs these: the grid points crowd towards
            the pole, and an unweighted mean counts that region too often.

    Notes
    -----
    The beta1 angle is sampled in the range (0, π/2) and phi in the range (0, 2π).

    Before this moved to ``IMP.bff``, ``k2`` was a 2D ``(n_beta1, n_phi)``
    array. It is flat now, matching the engine's own output: reshape it with
    ``k2.reshape(n_beta1, -1)`` if the grid shape is wanted, as the parity
    test in ``test/fitting/test_kappa2_distribution.py`` does. The 2D shape
    was silently unusable by ``compute_kappa2_dist``'s weighted-mean
    (``np.dot(weights, k2v)`` on two same-shaped 2D arrays is a matrix
    product, not a weighted sum, and raised on non-square grids) -- the
    "cone" model with ``rAD_known=True`` in the kappa2_dist plugin has been
    broken since that path was added; this incidentally fixes it.

    References
    ----------
    .. [1] Simon Sindbert, et al., "Accurate Distance Determination of Nucleic
           Acids via Foerster Resonance Energy Transfer: Implications of Dye Linker
           Length and Rigidity", J. Am. Chem. Soc., 2011.
    """
    from IMP.bff import wobbling_kappa2_distribution_delta as _f

    dist = _f(delta, sD2, sA2, step, n_bins, k2_min, k2_max)
    return (
        np.asarray(dist.scale, dtype=np.float64),
        np.asarray(dist.hist, dtype=np.float64),
        np.asarray(dist.values, dtype=np.float64),
        np.asarray(dist.weights, dtype=np.float64),
    )


def kappasq_all(
        sD2: float,
        sA2: float,
        n_bins: int = 81,
        k2_min: float = 0.0,
        k2_max: float = 4.0,
        n_samples: int = 10000,
        seed: typing.Optional[int] = None,
) -> typing.Tuple[np.array, np.array, np.array]:
    """
    Computes an orientation factor distribution for a wobbling-in-a-cone model
    based on random sampling of donor and acceptor orientations.

    This function generates random donor and acceptor vector pairs, computes
    kappa² for each pair, and returns a histogram of the kappa² values.

    The Monte-Carlo sampling runs in ``IMP.bff``
    (``wobbling_kappa2_distribution``), which draws through tttrlib's
    centralized RNG; see :func:`_new_engine_seed` for how a caller's
    ``np.random.seed(...)`` still makes a run reproducible.

    Parameters
    ----------
    sD2 : float
        Second rank order parameter S² of the donor dye.
    sA2 : float
        Second rank order parameter S² of the acceptor dye.
    n_bins : int, optional
        Number of bins in the kappa² histogram (default: 81).
    k2_min : float, optional
        Lower bound for the kappa² histogram (default: 0.0).
    k2_max : float, optional
        Upper bound for the kappa² histogram (default: 4.0).
    n_samples : int, optional
        Number of random vector pairs to generate (default: 10000).
    seed : int, optional
        Seed for the engine's Monte-Carlo draw. When ``None`` (default), a
        seed is drawn from numpy's global RNG state, so seeding that state
        (``np.random.seed(...)``) before the call still makes the result
        reproducible.

    Returns
    -------
    tuple
        A tuple containing:
          - k2scale (np.ndarray): Linear scale of kappa² values.
          - k2hist (np.ndarray): Histogram counts of kappa².
          - k2 (np.ndarray): Array of computed kappa² values.

    Examples
    --------
    >>> import numpy as np
    >>> k2_scale, k2_hist, k2 = kappasq_all(sD2=0.3, sA2=0.5, n_bins=31, n_samples=100000)
    >>> k2_scale  # doctest: +SKIP
    array([0.        , 0.13333333, 0.26666667, 0.4       , 0.53333333,
           0.66666667, 0.8       , 0.93333333, 1.06666667, 1.2       ,
           1.33333333, 1.46666667, 1.6       , 1.73333333, 1.86666667,
           2.        , 2.13333333, 2.26666667, 2.4       , 2.53333333,
           2.66666667, 2.8       , 2.93333333, 3.06666667, 3.2       ,
           3.33333333, 3.46666667, 3.6       , 3.73333333, 3.86666667,
           4.        ])
    >>> len(k2_hist)
    30
    >>> int(k2_hist.sum())  # doctest: +SKIP
    100000

    References
    ----------
    .. [1] Simon Sindbert, et al., "Accurate Distance Determination of Nucleic
           Acids via Foerster Resonance Energy Transfer: Implications of Dye Linker
           Length and Rigidity", J. Am. Chem. Soc., 2011.
    """
    from IMP.bff import wobbling_kappa2_distribution as _f

    if seed is None:
        seed = _new_engine_seed()

    dist = _f(sD2, sA2, n_bins, k2_min, k2_max, n_samples, seed)
    return (
        np.asarray(dist.scale, dtype=np.float64),
        np.asarray(dist.hist, dtype=np.float64),
        np.asarray(dist.values, dtype=np.float64),
    )


def kappa_distance(
        d1: np.array,
        d2: np.array,
        a1: np.array,
        a2: np.array
) -> typing.Tuple[float, float]:
    """
    Calculates the distance between the centers of two dipoles and the
    orientation factor kappa.

    Given the endpoints of the donor (d1 and d2) and acceptor (a1 and a2) dipoles,
    this function computes the center-to-center distance and the orientation
    factor kappa based on the dipole geometry.

    Forwards to ``IMP.bff.dipole_kappa_distance``, which takes one dipole
    pair (four length-3 vectors) per call; a degenerate dipole (coincident
    endpoints) divides by a zero length and returns ``nan`` rather than
    raising, matching the numpy behaviour this replaced.

    Parameters
    ----------
    d1 : np.array
        3D coordinates of the first point of the donor dipole.
    d2 : np.array
        3D coordinates of the second point of the donor dipole.
    a1 : np.array
        3D coordinates of the first point of the acceptor dipole.
    a2 : np.array
        3D coordinates of the second point of the acceptor dipole.

    Returns
    -------
    tuple
        A tuple (distance, kappa) where:
          - distance: The center-to-center distance between the dipoles.
          - kappa: The calculated orientation factor.

    Examples
    --------
    >>> import numpy as np
    >>> d1 = np.array([0.0, 0.0, 0.0])
    >>> d2 = np.array([1.0, 0.0, 0.0])
    >>> a1 = np.array([0.0, 0.5, 0.0])
    >>> a2 = np.array([0.0, 0.5, 1.0])
    >>> distance, k = kappa_distance(d1, d2, a1, a2)
    >>> round(distance, 5)
    0.86603
    >>> round(k, 5)
    1.0
    """
    from IMP.bff import dipole_kappa_distance as _f

    d, k = _f(
        np.asarray(d1, dtype=np.float64),
        np.asarray(d2, dtype=np.float64),
        np.asarray(a1, dtype=np.float64),
        np.asarray(a2, dtype=np.float64),
    )
    return d, k


def kappa(
        donor_dipole: np.ndarray,
        acceptor_dipole: np.ndarray
) -> typing.Tuple[float, float]:
    """
    Calculates the orientation factor kappa based on donor and acceptor dipoles.

    Parameters
    ----------
    donor_dipole : np.ndarray
        A 2x3 array representing the donor dipole endpoints.
    acceptor_dipole : np.ndarray
        A 2x3 array representing the acceptor dipole endpoints.

    Returns
    -------
    tuple
        A tuple (distance, kappa) where distance is the center-to-center distance
        and kappa is the orientation factor.

    Example
    -------
    >>> import numpy as np
    >>> donor_dipole = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
    >>> acceptor_dipole = np.array([[0.0, 0.5, 0.0], [0.0, 0.5, 1.0]], dtype=np.float64)
    >>> distance, k = kappa(donor_dipole, acceptor_dipole)
    >>> round(distance, 5)
    0.86603
    >>> round(k, 5)
    1.0
    """
    return kappa_distance(
        donor_dipole[0], donor_dipole[1],
        acceptor_dipole[0], acceptor_dipole[1]
    )


def s2delta(
        s2_donor: float,
        s2_acceptor: float,
        r_inf_AD: float,
        r_0: float = 0.38
) -> typing.Tuple[float, float]:
    """
    Calculate s2delta from the residual anisotropies of the donor and acceptor.

    Forwards to ``IMP.bff.s2_delta_from_anisotropy`` (Sindbert et al., JACS
    133:2463 (2011), eq. 10).

    Parameters
    ----------
    s2_donor : float
        Second rank order parameter of the donor dye.
    s2_acceptor : float
        Second rank order parameter of the directly excited acceptor dye.
    r_inf_AD : float
        Residual anisotropy on the acceptor excited by the donor dye.
    r_0 : float, optional
        Fundamental anisotropy at time zero (default: 0.38).

    Returns
    -------
    tuple
        A tuple (s2delta, delta) where:
          - s2delta: A computed second rank order parameter.
          - delta: The angle (in radians) between the two dipole symmetry axes.

    Examples
    --------
    >>> from chisurf.core.fluorescence.anisotropy.kappa2 import s2delta
    >>> r0 = 0.38
    >>> s2donor = 0.2
    >>> s2acceptor = 0.3
    >>> r_inf_AD = 0.01
    >>> s2d, delta = s2delta(s2_donor=s2donor, s2_acceptor=s2acceptor, r_inf_AD=r_inf_AD, r_0=r0)
    >>> round(s2d, 4)
    0.4386
    >>> bool(0.0 < delta < 1.6)
    True
    """
    from IMP.bff import s2_delta_from_anisotropy as _f

    s2_delta, delta = _f(s2_donor, s2_acceptor, r_inf_AD, r_0)
    return float(s2_delta), float(delta)


def calculate_kappa_distance(
        xyz: np.array,
        aid1: int,
        aid2: int,
        aia1: int,
        aia2: int
) -> typing.Tuple[np.ndarray, np.ndarray]:
    """
    Calculates the dipole center distance and the orientation factor kappa
    over a trajectory.

    This function extracts the coordinates corresponding to the donor
    and acceptor dipole endpoints (specified by atom indices) from a trajectory
    and computes the center-to-center distance and orientation factor for each frame.

    Parameters
    ----------
    xyz : np.array
        A 3D array of shape (n_frames, n_atoms, 3) containing the coordinates.
    aid1 : int
        Atom index for the first point of the donor dipole.
    aid2 : int
        Atom index for the second point of the donor dipole.
    aia1 : int
        Atom index for the first point of the acceptor dipole.
    aia2 : int
        Atom index for the second point of the acceptor dipole.

    Returns
    -------
    tuple
        A tuple (ds, ks) where:
          - ds (np.ndarray): Array of distances between dipole centers for each frame.
          - ks (np.ndarray): Array of corresponding orientation factors kappa.

        Frames whose dipoles are degenerate (coinciding endpoints, e.g. a missing
        or duplicated atom) cannot be evaluated and are reported as ``np.nan`` in
        both arrays.

    Examples
    --------
    >>> import numpy as np
    >>> # Create a simple trajectory with one frame and four atoms
    >>> xyz = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]], dtype=np.float64)
    >>> ds, ks = calculate_kappa_distance(xyz, 0, 1, 2, 3)
    >>> ds.shape, ks.shape  # doctest: +SKIP
    ((1,), (1,))
    """
    n_frames = xyz.shape[0]
    # NaN, not np.empty: a frame that raises below is never written, and an
    # uninitialized buffer is indistinguishable from a real kappa2/distance.
    ks = np.full(n_frames, np.nan, dtype=np.float32)
    ds = np.full(n_frames, np.nan, dtype=np.float32)

    for i_frame in range(n_frames):
        try:
            # A degenerate dipole divides by a zero separation, which
            # IMP.bff's dipole_kappa_distance -- like the numpy arithmetic it
            # replaced -- returns as nan rather than raising. Testing the
            # result is what the caller actually means, and it does not
            # depend on which layer does the arithmetic.
            with np.errstate(invalid='ignore', divide='ignore'):
                d, k = kappa_distance(
                    xyz[i_frame, aid1], xyz[i_frame, aid2],
                    xyz[i_frame, aia1], xyz[i_frame, aia2]
                )
            if not (np.isfinite(d) and np.isfinite(k)):
                raise ValueError("degenerate dipole")
            ks[i_frame] = k
            ds[i_frame] = d
        except Exception:
            logger.warning("Frame %d skipped: degenerate dipole, kappa2 is NaN", i_frame)
    return ds, ks


def kappasq(
        delta: float,
        sD2: float,
        sA2: float,
        beta1: float,
        beta2: float
) -> float:
    """
    Calculates kappa² given a set of order parameters and angles.

    This function implements eq. 9 from [1]_, computing the orientation factor
    based on the dye order parameters and the angles between the dye symmetry axes
    and the donor–acceptor vector.

    Forwards to ``IMP.bff.wobbling_kappa2``, a scalar C++ function -- the
    distribution-producing callers that used to sweep or sample this in a
    Python loop (``kappasq_all_delta``, ``kappasq_all``, ``kappasq_dwt``) now
    call their own ``IMP.bff`` engine functions directly instead, so this is
    only reached with scalar angles (as :mod:`anisotropy_to_kappa` does).

    Parameters
    ----------
    delta : float
        Angle (in radians) between the symmetry axes of the dyes.
    sD2 : float
        Second rank order parameter of the donor.
    sA2 : float
        Second rank order parameter of the acceptor.
    beta1 : float
        Angle (in radians) between the donor dye's symmetry axis and the
        donor–acceptor vector.
    beta2 : float
        Angle (in radians) between the acceptor dye's symmetry axis and the
        donor–acceptor vector.

    Returns
    -------
    float
        The computed kappa² value.

    Notes
    -----
    See eq. 9 in [1]_ for details.

    References
    ----------
    .. [1] Simon Sindbert, et al., "Accurate Distance Determination of Nucleic
           Acids via Foerster Resonance Energy Transfer: Implications of Dye Linker
           Length and Rigidity", J. Am. Chem. Soc., 2011.
    """
    from IMP.bff import wobbling_kappa2 as _f

    return float(_f(delta, sD2, sA2, beta1, beta2))


def p_isotropic_orientation_factor(
        k2: np.ndarray,
        normalize: bool = True
) -> np.ndarray:
    """
    Calculates the probability distribution of kappa² for isotropically oriented dipoles.

    Given an array of kappa² values, this function computes the corresponding
    probability distribution assuming an isotropic orientation factor distribution.

    Forwards to ``IMP.bff.isotropic_kappa2_density`` for the closed-form
    density; the normalization stays here, since it is a plotting/reporting
    convenience callers may or may not want.

    Parameters
    ----------
    k2 : np.ndarray
        Array of kappa² values.
    normalize : bool, optional
        If True (default), the output distribution is normalized to unity.

    Returns
    -------
    np.ndarray
        The probability distribution for the provided kappa² values.

    Example
    -------
    >>> import numpy as np
    >>> k2 = np.linspace(0.1, 4, 32)
    >>> p_k2 = p_isotropic_orientation_factor(k2=k2)
    >>> p_k2  # doctest: +SKIP
    array([0.17922824, 0.11927194, 0.09558154, 0.08202693, 0.07297372,
           0.06637936, 0.06130055, 0.05723353, 0.04075886, 0.03302977,
           0.0276794 , 0.02359627, 0.02032998, 0.01763876, 0.01537433,
           0.01343829, 0.01176177, 0.01029467, 0.00899941, 0.00784718,
           0.00681541, 0.00588615, 0.00504489, 0.0042798 , 0.0035811 ,
           0.00294063, 0.00235153, 0.001808  , 0.00130506, 0.00083845,
           0.0004045 , 0.        ])
    Notes
    -----
    For more details on isotropic kappa² distributions, see:
    http://www.fretresearch.org/kappasquaredchapter.pdf
    """
    from IMP.bff import isotropic_kappa2_density as _f

    k2 = np.asarray(k2, dtype=np.float64)
    r = np.asarray(_f(k2), dtype=np.float64)
    if normalize:
        r = r / max(1.0, r.sum())
    return r
