from __future__ import annotations

from math import exp

import numpy as np

_trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))

from . import distributions


def gaussian_chain_ree(segment_length: float, number_of_segments: int) -> float:
    """Calculates the root mean square end-to-end distance of a Gaussian chain

    :param segment_length: float
        The length of a segment
    :param number_of_segments: int
        The number of segments
    :return:
    """
    from IMP.bff import gaussian_chain_ree as _f

    return float(_f(segment_length, int(number_of_segments)))


def gaussian_chain(r, segment_length: float, number_of_segments: int) -> float:
    """Calculates the radial distribution function of a Gaussian chain in three dimensions

    :param number_of_segments: int
        The number of segments
    :param segment_length: float
        The segment length
    :param r: numpy-array
        values of r should be in range [0, 1) - not including 1

    ..plot:: plots/rdf-gauss.py

    """
    from IMP.bff import gaussian_chain as _f

    return _f(np.asarray(r, dtype=float), segment_length, int(number_of_segments))


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
    from IMP.bff import saw_nu as _f

    return _f(np.asarray(r, dtype=float), r_rms, nu, gamma_exp)


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

    **Moved to IMP.bff** -- what is left here is a thin forwarder.
    The transfer-matrix product is a Python loop over ``n_k`` k-points,
    each stepping a 2-vector through ``number_of_residues`` 2x2 multiplies,
    so the interpreter ran ~80k iterations of arithmetic numpy cannot
    vectorise away. It measured **55 ms per curve**, which at ten free
    parameters is 0.6 s per Levenberg-Marquardt iteration -- more than half
    of all the model compute ChiSurf still held in Python
    (``imp.bff test/minimizer/bench_models.py``). The C++ kernel is the
    same arithmetic in the same order, agrees to 6e-17, and is **61x**
    faster.
    """
    from IMP.bff import ising_chain as _f

    return _f(
        np.asarray(r, dtype=float),
        int(number_of_residues),
        b_structured,
        b_unstructured,
        coupling,
        field,
        n_k,
    )


# TODO: needs docstring
def Qd(r, kappa) -> float:
    return (
        pow((3.0 / (4.0 * 3.14159265359 * kappa)), (3.0 / 2.0))
        * exp(-3.0 / 4.0 * r * r / kappa)
        * (1.0 - 5.0 / 4.0 * kappa + 2.0 * r * r - 33.0 / 80.0 * r * r * r * r / kappa)
    )


def worm_like_chain(
    distances: np.array,
    kappa: float,
    chain_length: float = 0.0,
    normalize: bool = True,
    distance=True,
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
    from IMP.bff import worm_like_chain as _f

    # `distance` is passed as False, always. This function has never
    # applied the r^2 factor its own signature advertises -- the flag was
    # accepted and dropped on the floor -- and every fit in the stack was
    # made against that behaviour. bff implements the flag properly, so
    # honouring it here would silently change results; preserving the
    # existing answer is this port's contract. See okf/log.md 2026-09-02.
    return _f(np.asarray(distances, dtype=float), kappa, chain_length, normalize, False)


def distance_between_gaussian(
    distances: np.array, separation_distance: float, sigma: float, normalize: bool = False
) -> np.array:
    """Calculates the distance distribution between two separated Gaussians a distance

    :param distances:
    :param separation_distance:
    :param sigma:
    :param normalize:
    :return:
    """
    separation_distance = np.asarray(separation_distance, dtype=float)
    if separation_distance.ndim == 0:
        # The scalar case is bff's. The broadcasting case is NOT: it builds a
        # 2-D kernel from a column of separations against a row of distances,
        # which the C++ signature (one scalar separation) cannot express. Its
        # only caller was `worm_like_chain_linker`, which is now bff's
        # wholesale, so this branch is kept for external callers rather than
        # for us -- see okf/log.md 2026-09-02.
        from IMP.bff import distance_between_gaussian as _f

        return _f(np.asarray(distances, dtype=float), float(separation_distance), sigma, normalize)
    positive = separation_distance > 0.0
    safe_separation = np.where(positive, separation_distance, 1.0)
    separated = (
        distances
        / safe_separation
        * (
            distributions.normal_distribution(
                x=distances, loc=safe_separation, scale=sigma, norm=False
            )
            - distributions.normal_distribution(
                x=distances, loc=-safe_separation, scale=sigma, norm=False
            )
        )
    )
    coincident = (
        2.0
        * distances**2
        / sigma**2
        * distributions.normal_distribution(x=distances, loc=0.0, scale=sigma, norm=False)
    )
    pr = np.where(positive, separated, coincident)
    if normalize:
        pr = pr / pr.sum()
    return pr


def worm_like_chain_linker(
    distances: np.array,
    kappa: float,
    chain_length: float = 0.0,
    sigma: float = 6.0,
    normalize: bool = True,
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
    from IMP.bff import worm_like_chain_linker as _f

    return _f(np.asarray(distances, dtype=float), kappa, chain_length, sigma, normalize)
