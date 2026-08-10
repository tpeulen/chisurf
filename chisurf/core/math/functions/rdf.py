from __future__ import annotations

from math import exp, gamma, log

import numpy as np

_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))

from chisurf.core.math.functions.special import i0
from . import distributions


def gaussian_chain_ree(
        segment_length: float,
        number_of_segments: int
) -> float:
    """Calculates the root mean square end-to-end distance of a Gaussian chain

    :param segment_length: float
        The length of a segment
    :param number_of_segments: int
        The number of segments
    :return:
    """
    return segment_length * np.sqrt(number_of_segments)


def gaussian_chain(
        r,
        segment_length: float,
        number_of_segments: int
) -> float:
    """Calculates the radial distribution function of a Gaussian chain in three dimensions

    :param number_of_segments: int
        The number of segments
    :param segment_length: float
        The segment length
    :param r: numpy-array
        values of r should be in range [0, 1) - not including 1

    ..plot:: plots/rdf-gauss.py

    """
    r2_mean = gaussian_chain_ree(segment_length, number_of_segments) ** 2
    return 4*np.pi*r**2/(2./3. * np.pi*r2_mean)**(3./2.) * np.exp(-3./2. * r**2 / r2_mean)


def saw_nu(
        r,
        r_rms: float,
        nu: float = 0.588,
        gamma_exp: float = 1.1615,
):
    """Radial distribution of a self-avoiding walk with Flory exponent ``nu``.

    The SAW-ν inter-monomer distance distribution (des Cloizeaux form; Zheng
    et al., J. Am. Chem. Soc. 2018), the standard model for disordered/unfolded
    chains in single-molecule FRET:

    .. math::

        P(r) \\propto r^{2+\\theta}\\,\\exp[-(r/r_0)^{\\delta}], \\quad
        \\theta = (\\gamma-1)/\\nu, \\quad \\delta = 1/(1-\\nu),

    with the scale :math:`r_0` fixed so that :math:`\\sqrt{\\langle r^2\\rangle}
    = r_\\mathrm{rms}`.  With ``nu = 0.5`` and ``gamma_exp = 1`` it reduces to the
    :func:`gaussian_chain`.  Complements :func:`worm_like_chain`.

    :param r: numpy-array of inter-dye distances (> 0).
    :param r_rms: target root-mean-square inter-dye distance.
    :param nu: Flory scaling exponent (``~0.588`` expanded, ``0.5`` theta,
        ``< 0.4`` collapsed); ``0 < nu < 1``.
    :param gamma_exp: SAW susceptibility exponent (default 1.1615; 1.0 = ideal).
    :return: the (analytically normalised) radial distribution ``P(r)``.
    """
    r = np.asarray(r, dtype=float)
    if not (0.0 < nu < 1.0) or r_rms <= 0.0:
        return np.zeros_like(r)
    theta = (gamma_exp - 1.0) / nu
    delta = 1.0 / (1.0 - nu)
    # <r^2> = r0^2 * Gamma((5+theta)/delta) / Gamma((3+theta)/delta)
    ratio = gamma((5.0 + theta) / delta) / gamma((3.0 + theta) / delta)
    r0 = r_rms / np.sqrt(ratio)
    norm = delta / (r0 ** (3.0 + theta) * gamma((3.0 + theta) / delta))
    with np.errstate(over="ignore", invalid="ignore"):
        pr = norm * r ** (2.0 + theta) * np.exp(-((r / r0) ** delta))
    return np.nan_to_num(pr, nan=0.0, posinf=0.0, neginf=0.0)


def ising_chain(
        r,
        number_of_residues: int,
        b_structured: float,
        b_unstructured: float,
        coupling: float = 1.5,
        field: float = 0.0,
        n_k: int = 2000,
):
    r"""Inter-dye distance distribution of an Ising two-state Gaussian chain.

    The tractable form of the Ising-worm-like-chain FRET model for partially
    structured / folded-unfolded chains (cf. Fretica ``FIsingWLCFRET*``): every
    residue is either **structured** (``S``) or **unstructured** (``U``) with a
    nearest-neighbour Ising Hamiltonian (cooperativity ``coupling`` J, field
    ``field`` h biasing towards S), and each residue contributes a Gaussian bond
    whose mean-square extension is :math:`b_S^2` (S) or :math:`b_U^2` (U).

    For a Gaussian-segment chain the characteristic function factorises per
    residue, so the Boltzmann-weighted end-to-end characteristic function is an
    exact 2x2 **transfer-matrix product** in Fourier (``k``) space,

    .. math::

        \varphi(k) = \frac{\mathbf{1}^\top \big[\prod_i M_i(k)\big]\,\mathbf{1}}
                          {\varphi(0)}, \quad
        M(k)_{\sigma\sigma'} = W(\sigma,\sigma')\,
        e^{-k^2 b_{\sigma'}^2/6},

    and the radial distribution is recovered by the isotropic inverse transform
    :math:`P(R) = (2R/\pi)\int_0^\infty k\,\sin(kR)\,\varphi(k)\,dk`.  With
    ``b_S = b_U`` (or all residues in one state) it reduces to the
    :func:`gaussian_chain`.

    :param r: numpy-array of inter-dye distances (> 0).
    :param number_of_residues: number of residues (bonds) between the dyes.
    :param b_structured: RMS bond contribution per structured residue.
    :param b_unstructured: RMS bond contribution per unstructured residue.
    :param coupling: Ising nearest-neighbour coupling ``J`` (cooperativity).
    :param field: Ising field ``h`` (positive biases towards structured).
    :param n_k: number of ``k`` grid points for the inverse transform.
    :return: the (numerically normalised) radial distribution ``P(R)``.
    """
    r = np.asarray(r, dtype=float)
    n = int(number_of_residues)
    if n < 1:
        return np.zeros_like(r)

    vS = b_structured * b_structured / 6.0
    vU = b_unstructured * b_unstructured / 6.0

    # Ising nearest-neighbour weights W(sigma, sigma'), states 0 = S, 1 = U.
    # Energy: -J*delta(sigma,sigma') - (h/2)*(is_S(sigma)+is_S(sigma')).
    W = np.array([
        [np.exp(coupling + field), np.exp(-coupling + 0.5 * field)],
        [np.exp(-coupling + 0.5 * field), np.exp(coupling)],
    ], dtype=float)

    # k grid: cover up to where phi has decayed (set by the smallest bond var).
    r_max = float(np.max(r)) if r.size else 1.0
    k_max = 30.0 / max(np.sqrt(min(vS, vU) * n), r_max / n, 1e-6)
    k = np.linspace(1e-6, k_max, n_k)

    phi = np.empty_like(k)
    for j, kk in enumerate(k):
        g = np.array([np.exp(-kk * kk * vS), np.exp(-kk * kk * vU)])  # per-residue bond factor
        M = W * g[np.newaxis, :]                                      # M[s,s'] = W[s,s'] g[s']
        # phi(k) = 1^T M^n 1 (bonds); start vector uniform over the first state.
        v = np.array([1.0, 1.0])
        for _ in range(n):
            v = v @ M
        phi[j] = v.sum()
    phi /= phi[0]  # normalise phi(0) = 1

    # Isotropic inverse transform: P(R) = (2 R / pi) * int k sin(kR) phi(k) dk.
    kr = np.outer(r, k)
    integrand = k[np.newaxis, :] * np.sin(kr) * phi[np.newaxis, :]
    pr = (2.0 * r / np.pi) * _trapz(integrand, k, axis=1)
    pr = np.clip(np.nan_to_num(pr, nan=0.0), 0.0, None)
    area = _trapz(pr, r)
    return pr / area if area > 0 else pr


# TODO: needs docstring
def Qd(
        r,
        kappa
) -> float:
    return pow((3.0 / (4.0 * 3.14159265359 * kappa)), (3.0 / 2.0)) * \
           exp(-3.0 / 4.0 * r * r / kappa) * \
           (1.0 - 5.0 / 4.0 * kappa + 2.0 * r * r - 33.0 / 80.0 * r * r * r * r / kappa)


def worm_like_chain(
        distances: np.array,
        kappa: float,
        chain_length: float = 0.0,
        normalize: bool = True,
        distance=True
):
    """Calculates the radial distribution function of a worm-like-chain given the multiple piece-solution
    according to:

    The radial distribution function of worm-like chain
    Eur Phys J E, 32, 53-69 (2010)

    Parameters
    ----------
    distances: a vector at which the pdf is evaluated.
    kappa: a parameter describing the stiffness (details see publication)
    chain_length: the total length of the chain.
    normalize: If this is True the sum of the returned pdf vector is normalized to one.
    distance: If this is False, the end-to-end vector distribution is calculated. If True the distribution 
    the pdf is integrated over a sphere, i.e., the pdf of the end-to-end distribution function 
    is multiplied with 4*pi*r**2.

    Returns
    -------
    An array of the pdf

    Examples
    --------

    >>> import chisurf.core.math.functions.rdf as rdf
    >>> import numpy as np
    >>> r = np.linspace(0, 0.99, 50)
    >>> kappa = 1.0
    >>> rdf.worm_like_chain(r, kappa)
    array([  4.36400392e-06,   4.54198260e-06,   4.95588702e-06,
             5.64882576e-06,   6.67141240e-06,   8.09427111e-06,
             1.00134432e-05,   1.25565315e-05,   1.58904681e-05,
             2.02314725e-05,   2.58578047e-05,   3.31260228e-05,
             4.24918528e-05,   5.45365051e-05,   7.00005025e-05,
             8.98266752e-05,   1.15215138e-04,   1.47693673e-04,
             1.89208054e-04,   2.42238267e-04,   3.09948546e-04,
             3.96381668e-04,   5.06711496e-04,   6.47572477e-04,
             8.27491272e-04,   1.05745452e-03,   1.35165891e-03,
             1.72850634e-03,   2.21192991e-03,   2.83316807e-03,
             3.63314697e-03,   4.66568936e-03,   6.00184475e-03,
             7.73573198e-03,   9.99239683e-03,   1.29382877e-02,
             1.67949663e-02,   2.18563930e-02,   2.85090497e-02,
             3.72510109e-02,   4.86977611e-02,   6.35415230e-02,
             8.23790455e-02,   1.05199154e-01,   1.30049143e-01,
             1.49953168e-01,   1.47519190e-01,   9.57787954e-02,
             1.45297018e-02,   1.53180248e-08])

    References
    ----------

    .. [1] Becker NB, Rosa A, Everaers R, Eur Phys J E Soft Matter, 2010 May;32(1):53-69,
       The radial distribution function of worm-like chains.

    """
    if chain_length == 0.0:
        chain_length = np.max(distances)

    k = kappa
    a = 14.054
    b = 0.473
    c = 1.0 - (1.0+(0.38*k**(-0.95))**(-5.))**(-1./5.)
    pr = np.zeros_like(distances, dtype=np.float64)

    if k < 0.125:
        d = k + 1.0
    else:
        d = 1.0 - 1.0/(0.177/(k-0.111)+6.4 * exp(0.783 * log(k-0.111)))

    # The loop this replaces `break`s at the first distance that reaches the
    # chain length, so everything past that point stays zero *whether or not*
    # the remaining distances are shorter. That is a prefix, not a mask: with an
    # unsorted axis the two differ, and `distances` is not required to be sorted
    # anywhere. Reproduce the prefix.
    reached = np.asarray(distances) >= chain_length
    limit = int(np.argmax(reached)) if reached.any() else len(distances)

    if limit:
        r = np.asarray(distances[:limit], dtype=np.float64) / chain_length

        pri = ((1.0 - c * r**2.0) / (1.0 - r**2.0))**(5.0 / 2.0)
        pri *= np.exp(-d * k * a * b * (1.0 + b) / (1.0 - (b*r)**2.0) * r**2.0)

        g = (((-3./4.) / k - 1./2.) * r**2. + ((-23./64.) / k + 17./16.) * r**4. + ((-7./64.) / k - 9./16.) * r**6.)
        pri *= np.exp(g / (1.0 - r**2.0))
        pri *= i0(-d*k*a*(1+b)*r/(1-(b*r)**2))
        pr[:limit] = pri

    if normalize:
        pr /= pr.sum()

    return pr


def distance_between_gaussian(
        distances: np.array,
        separation_distance: float,
        sigma: float,
        normalize: bool = False
) -> np.array:
    """Calculates the distance distribution between two separated Gaussians a distance

    :param distances:
    :param separation_distance:
    :param sigma:
    :param normalize:
    :return:
    """
    separation_distance = np.asarray(separation_distance, dtype=float)
    positive = separation_distance > 0.0

    # Elementwise in *both* arguments, so a column of separations against a row
    # of distances builds a whole kernel in one call. That means selecting the
    # two branches with `where` rather than an `if`, and feeding the zero
    # separations a substituted 1.0 so the division in the unused branch does
    # not produce a warning or a NaN that `where` would then have to discard.
    safe_separation = np.where(positive, separation_distance, 1.0)
    separated = distances / safe_separation * (
        distributions.normal_distribution(
            x=distances, loc=safe_separation, scale=sigma, norm=False
        )
        - distributions.normal_distribution(
            x=distances, loc=-safe_separation, scale=sigma, norm=False
        )
    )
    coincident = 2. * distances ** 2 / sigma ** 2 * distributions.normal_distribution(
        x=distances, loc=0.0, scale=sigma, norm=False
    )
    pr = np.where(positive, separated, coincident)

    if normalize:
        # Note this normalises over the whole array, so a 2-D kernel would be
        # normalised globally rather than per row. Every caller that passes a
        # kernel leaves `normalize` False.
        pr = pr / pr.sum()
    return pr


def worm_like_chain_linker(
        distances: np.array,
        kappa: float,
        chain_length: float = 0.0,
        sigma: float = 6.0,
        normalize: bool = True
) -> np.array:
    """
    Calculates the radial distribution function of a worm-like-chain given the multiple piece-solution
    according to:

    The radial distribution function of worm-like chain
    Eur Phys J E, 32, 53-69 (2010)

    Additionally the broadening by the dye-linkers is considered

    :param r: numpy-array
        values of r should be in range [0, 1) - not including 1
    :param kappa: float

    Examples
    --------

    .. [1] Becker NB, Rosa A, Everaers R, Eur Phys J E Soft Matter, 2010 May;32(1):53-69,
       The radial distribution function of worm-like chains.

    """
    pr = worm_like_chain(
        distances=distances,
        kappa=kappa,
        chain_length=chain_length
    )
    # sum_r pr[r] * G(distances | separation = r) as one matrix-vector product.
    # `distance_between_gaussian` is elementwise in both arguments, so giving it
    # a column of separations and a row of distances builds the whole kernel at
    # once -- the Python loop it replaces would otherwise run once per distance
    # on every model evaluation, and this is on a fit's inner loop.
    kernel = distance_between_gaussian(
        distances=np.asarray(distances, dtype=np.float64)[None, :],
        separation_distance=np.asarray(distances, dtype=np.float64)[:, None],
        sigma=sigma,
    )
    pn = pr @ kernel

    if normalize:
        pn /= pn.sum()
    return pn

