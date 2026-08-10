"""Deconvolution: undoing the blur the microscope added.

A microscope does not record the sample, it records the sample convolved with
the instrument's point spread function. Deconvolution inverts that, and the
reason it is not simply a division is noise: the PSF suppresses high spatial
frequencies, so dividing them back out amplifies whatever sits there — which,
above the cut-off, is only noise.

:func:`richardson_lucy` is the estimator to reach for. It is the maximum
likelihood solution under **Poisson** statistics, which is what photon counting
actually obeys, and it keeps the estimate non-negative by construction, which is
the other thing a count owes reality. It carries no explicit regularisation:
the iteration count is the regulariser, and running it too far turns noise into
texture that looks like structure. On a noisy frame the error against the truth
traces a **U** — on the fixture in the tests it bottoms out at 20 iterations and
is four times worse by 400 — so "more iterations" is not "more converged", it is
"more confident about noise". Tens, not thousands, and the number is a property
of the data rather than a default worth trusting.

The arithmetic is in the photon library, over its vendored FFT — each iteration
is two convolutions with the PSF, and doing them by transform makes the cost
independent of the PSF size. What is here is the part that knows about
microscopes: turning a measured or specified PSF into a kernel.

Where the PSF comes from
------------------------
Three routes, in decreasing order of how much they are to be trusted:

1. **Measured**, from sub-resolution beads — the ``psf_determination`` plugin
   fits a 3-D Gaussian to each bead and reports σ per axis in pixels. Feed those
   to :func:`gaussian_psf` and the kernel matches the instrument that took the
   data.
2. **Computed from the optics**, via :func:`psf_sigma_from_optics`. A Gaussian
   approximation to the diffraction-limited PSF, good to a few percent for
   NA below about 1.0 and progressively optimistic above it.
3. **Guessed.** Deconvolving with the wrong width does not fail, it produces a
   confident wrong answer — too narrow leaves the image blurred, too wide rings.
"""

from __future__ import annotations

from typing import Optional, Sequence, Union

import numpy as np

__all__ = [
    "gaussian_psf",
    "psf_sigma_from_optics",
    "richardson_lucy",
    "wiener_deconvolve",
]

#: Gaussian approximations to the diffraction-limited PSF, from Zhang et al.,
#: *Applied Optics* **46**, 1819 (2007). The lateral constant is the one worth
#: remembering: σ ≈ 0.21 λ / NA, which for green emission at NA 1.4 is about
#: 80 nm — three pixels at a typical 25 nm sampling.
_LATERAL_COEFFICIENT = 0.21
_AXIAL_COEFFICIENT = 0.66


def psf_sigma_from_optics(
    wavelength_nm: float,
    numerical_aperture: float,
    pixel_size_nm: float,
    z_step_nm: Optional[float] = None,
    refractive_index: float = 1.518,
) -> Union[tuple[float, float], tuple[float, float, float]]:
    """Return the Gaussian PSF width in **pixels**, from the optics.

    Parameters
    ----------
    wavelength_nm : float
        Emission wavelength. Use the emission maximum of the dye; the
        excitation wavelength describes the illumination PSF instead, and for a
        confocal the effective PSF sits between the two.
    numerical_aperture : float
        Objective NA.
    pixel_size_nm : float
        Lateral sampling, in the sample plane.
    z_step_nm : float, optional
        Axial step. Given, the return is 3-D ``(σ_z, σ_y, σ_x)``; omitted, 2-D
        ``(σ_y, σ_x)``.
    refractive_index : float
        Immersion medium. 1.518 for oil, 1.33 for water, 1.0 for air. Only the
        axial width depends on it.

    Returns
    -------
    tuple of float
        Widths in pixels, slowest axis first, matching NumPy's index order.

    Notes
    -----
    These are the paraxial Gaussian approximations of {cite}`zhang2007`, not a
    scalar or vectorial diffraction model. They are within a few percent up to
    about NA 1.0 and increasingly optimistic beyond it — at NA 1.4 the true PSF
    has structure a Gaussian cannot represent. When the answer matters, measure
    the PSF from beads instead.
    """
    if wavelength_nm <= 0 or numerical_aperture <= 0 or pixel_size_nm <= 0:
        raise ValueError("wavelength, numerical aperture and pixel size must be positive")

    lateral_nm = _LATERAL_COEFFICIENT * wavelength_nm / numerical_aperture
    lateral = lateral_nm / pixel_size_nm
    if z_step_nm is None:
        return (lateral, lateral)
    if z_step_nm <= 0:
        raise ValueError("z_step_nm must be positive")
    axial_nm = (
        _AXIAL_COEFFICIENT * wavelength_nm * refractive_index / numerical_aperture**2
    )
    return (axial_nm / z_step_nm, lateral, lateral)


def gaussian_psf(sigma: Union[float, Sequence[float]], shape=None, truncate: float = 4.0):
    """Build a normalised Gaussian point spread function.

    Parameters
    ----------
    sigma : float or sequence of float
        Width in pixels per axis, slowest first. A scalar is used on every axis.
        This is what the bead-fitting tool reports and what
        :func:`psf_sigma_from_optics` returns.
    shape : sequence of int, optional
        Kernel extent. Defaults to ``2 * ceil(truncate * sigma) + 1`` per axis,
        which is odd — deliberately, because an even kernel has no centre pixel
        and shifts the image by half a pixel. Even extents are refused.
    truncate : float
        Default kernel radius, in standard deviations. Below about 3 the tails
        are cut where they still carry weight and the kernel no longer sums to
        one over its support.

    Returns
    -------
    numpy.ndarray
        The kernel, summing to 1.
    """
    sigmas = np.atleast_1d(np.asarray(sigma, dtype=float))
    if np.any(sigmas <= 0):
        raise ValueError("every sigma must be positive")

    if shape is None:
        extents = [int(2 * np.ceil(truncate * s) + 1) for s in sigmas]
    else:
        extents = [int(s) for s in np.atleast_1d(shape)]
        if sigmas.size == 1 and len(extents) > 1:
            # A scalar width means "the same on every axis", which is the usual
            # case for a lateral-only PSF.
            sigmas = np.repeat(sigmas, len(extents))
        if len(extents) != len(sigmas):
            raise ValueError(
                f"shape has {len(extents)} axes and sigma {sigmas.size}; they must match"
            )
        if any(extent % 2 == 0 for extent in extents):
            raise ValueError(
                "every PSF extent must be odd, or the kernel has no centre pixel "
                "and the restored image comes out shifted by half a pixel"
            )

    grids = np.meshgrid(
        *[np.arange(extent) - (extent - 1) / 2.0 for extent in extents], indexing="ij"
    )
    exponent = sum((grid / s) ** 2 for grid, s in zip(grids, sigmas))
    kernel = np.exp(-0.5 * exponent)
    return kernel / kernel.sum()


def _engine():
    """Return the compiled deconvolution entry points, or raise saying why not."""
    try:
        import tttrlib
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "deconvolution needs the photon library, which is not importable"
        ) from error
    if not hasattr(tttrlib, "richardson_lucy_2d"):
        raise RuntimeError(
            "the installed photon library has no deconvolution engine; rebuild it "
            "(the kernel lives in its math module)"
        )
    return tttrlib


def richardson_lucy(
    image,
    psf,
    n_iter: int = 30,
    *,
    clip: bool = False,
    filter_epsilon: float = 0.0,
    acceleration: bool = False,
):
    """Deconvolve ``image`` by Poisson maximum likelihood.

    Parameters
    ----------
    image : numpy.ndarray
        2-D frame or 3-D stack. Counts, or anything proportional to them.
    psf : numpy.ndarray
        Point spread function of the same rank, no larger than the image on any
        axis. Normalised internally, so its scale does not matter.
    n_iter : int
        Iterations. This is the regularisation: too few leaves the image
        blurred, too many amplify noise into plausible-looking texture. Start
        around 20–50 and watch the background.
    clip : bool
        Clip to ``[-1, 1]``. For an image scaled to that range; leave off for
        counts, which it would destroy.
    filter_epsilon : float
        Where the reblurred estimate falls below this, treat the ratio as zero
        rather than dividing. Guards the dark background of a sparse image,
        where the division is near 0/0 and amplifies nothing but noise.
    acceleration : bool
        Biggs–Andrews vector extrapolation. It walks the *same* path faster —
        measured on a noisy 256×256 frame, 30 accelerated iterations land where
        400 plain ones do — which is a gain and a trap in equal measure. The
        gain: the best restoration arrives at about 5 iterations instead of 20.
        The trap: "faster along the path" includes the part of the path where
        the iteration count has stopped regularising and started amplifying
        noise, so **an iteration count tuned without acceleration is badly wrong
        with it**, and the coarser step can overshoot what is a shallow optimum
        (0.13 against 0.10 relative error, on that frame). Turn it on to explore
        quickly; turn it off to settle the count.

    Returns
    -------
    numpy.ndarray
        The restored image, same shape as ``image``.
    """
    engine = _engine()
    image = np.ascontiguousarray(image, dtype=np.float64)
    psf = np.ascontiguousarray(psf, dtype=np.float64)
    if psf.ndim != image.ndim:
        raise ValueError(
            f"the PSF is {psf.ndim}-D and the image {image.ndim}-D; they must match"
        )
    if image.ndim == 2:
        return engine.richardson_lucy_2d(
            image, psf, n_iter, clip, filter_epsilon, acceleration
        )
    if image.ndim == 3:
        return engine.richardson_lucy_3d(
            image, psf, n_iter, clip, filter_epsilon, acceleration
        )
    raise ValueError(f"deconvolution is implemented for 2-D and 3-D, not {image.ndim}-D")


def wiener_deconvolve(image, psf, balance: float = 0.1):
    """Deconvolve ``image`` in one step, by the linear Wiener filter.

    The Gaussian-noise answer: one transform pair, no iteration, and a single
    knob. Faster than :func:`richardson_lucy` and worse on photon-limited data,
    because it neither knows the noise is Poisson nor keeps the result
    non-negative — a Wiener-restored image rings around bright objects and goes
    negative between them. Use it for a quick look, or when the data really is
    read-noise limited.

    Parameters
    ----------
    image : numpy.ndarray
        2-D frame.
    psf : numpy.ndarray
        Point spread function, 2-D.
    balance : float
        Noise-to-signal power ratio. Large returns the blurred image, small
        returns noise.

    Returns
    -------
    numpy.ndarray
        The restored frame.
    """
    engine = _engine()
    image = np.ascontiguousarray(image, dtype=np.float64)
    psf = np.ascontiguousarray(psf, dtype=np.float64)
    if image.ndim != 2 or psf.ndim != 2:
        raise ValueError("the Wiener filter here is 2-D only")
    return engine.wiener_deconvolve_2d(image, psf, balance)
