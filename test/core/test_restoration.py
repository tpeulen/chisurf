"""Deconvolution: parity, the PSF bridge, and what the iteration count means.

The arithmetic lives in the photon library; what is tested here is that it
agrees with the reference implementation exactly, that the PSF builders produce
the kernel the optics imply, and — the part that is easy to get wrong in use
rather than in code — that the iteration count behaves as a regulariser rather
than as a convergence knob.

That last one is why this suite maps the whole error-versus-iterations curve
instead of checking one call: on noisy data the curve is a **U**, and a caller
who reads "more iterations, more converged" will walk straight past the optimum
into confidently reconstructed noise.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from chisurf.core.fluorescence.imaging.restoration import (
    gaussian_psf,
    psf_sigma_from_optics,
    richardson_lucy,
    wiener_deconvolve,
)

pytest.importorskip("tttrlib")


def _engine_available():
    import tttrlib

    return hasattr(tttrlib, "richardson_lucy_2d")


pytestmark = pytest.mark.skipif(
    not _engine_available(), reason="the photon library has no deconvolution engine"
)


def spots(shape=(256, 256), n_spots=60, seed=1):
    """Sparse bright objects — a fluorescence frame, not a natural image."""
    rng = np.random.default_rng(seed)
    truth = np.zeros(shape)
    y, x = np.indices(shape)
    for centre_y, centre_x, amplitude in rng.uniform(
        [10, 10, 40], [shape[0] - 10, shape[1] - 10, 300], (n_spots, 3)
    ):
        truth += amplitude * np.exp(
            -((x - centre_x) ** 2 + (y - centre_y) ** 2) / 6.0
        )
    return truth


def blurred_and_counted(truth, psf, seed=1):
    """Blur by the PSF and draw Poisson counts, as a detector would."""
    rng = np.random.default_rng(seed)
    blurred = ndimage.convolve(truth, psf, mode="constant")
    return rng.poisson(np.clip(blurred, 0, None)).astype(float)


def relative_error(estimate, truth):
    return float(np.abs(estimate - truth).sum() / truth.sum())


# ---------------------------------------------------------------------------
# Parity with the reference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "psf_shape,sigma", [((7, 7), 1.5), ((5, 9), (1.0, 2.0)), ((11, 11), 2.5)]
)
@pytest.mark.parametrize("n_iter", [1, 5, 30])
def test_richardson_lucy_matches_skimage_2d(psf_shape, sigma, n_iter):
    """Same numbers as scikit-image, to the last few bits."""
    pytest.importorskip("skimage")
    import skimage.restoration as sk_restoration

    image = np.random.default_rng(0).random((48, 52))
    psf = gaussian_psf(sigma, psf_shape)
    np.testing.assert_allclose(
        richardson_lucy(image, psf, n_iter),
        sk_restoration.richardson_lucy(image, psf, num_iter=n_iter, clip=False),
        atol=1e-12,
    )


def test_richardson_lucy_matches_skimage_3d():
    """A stack goes through the same path, with the same answer."""
    pytest.importorskip("skimage")
    import skimage.restoration as sk_restoration

    volume = np.random.default_rng(0).random((16, 20, 22))
    psf = gaussian_psf((1.0, 1.5, 1.5))
    np.testing.assert_allclose(
        richardson_lucy(volume, psf, 10),
        sk_restoration.richardson_lucy(volume, psf, num_iter=10, clip=False),
        atol=1e-12,
    )


def test_clip_matches_the_reference():
    pytest.importorskip("skimage")
    import skimage.restoration as sk_restoration

    image = np.random.default_rng(2).random((32, 32))
    psf = gaussian_psf(1.2, (7, 7))
    np.testing.assert_allclose(
        richardson_lucy(image, psf, 20, clip=True),
        sk_restoration.richardson_lucy(image, psf, num_iter=20, clip=True),
        atol=1e-12,
    )


# ---------------------------------------------------------------------------
# What it is for
# ---------------------------------------------------------------------------


def test_it_recovers_a_known_object_from_a_known_blur():
    """The end-to-end claim, on data with no noise: the blur comes back out."""
    truth = np.zeros((64, 64))
    truth[20, 20] = 1.0
    truth[20, 26] = 0.7
    truth[40, 35] = 0.5
    psf = gaussian_psf(1.2, (7, 7))
    blurred = ndimage.convolve(truth, psf, mode="constant")

    before = relative_error(blurred, truth)
    after = relative_error(richardson_lucy(blurred, psf, 200), truth)
    assert after < before / 5, f"{after:.3f} is not much better than {before:.3f}"


def test_flux_is_conserved():
    """Richardson-Lucy redistributes photons; it must not invent or lose them.

    Over the *whole frame*, exactly — the update multiplies the estimate by a
    correlation with a normalised kernel, which is flux-preserving by
    construction. Not over a sub-window: restoring pulls flux back in from the
    blurred halo, so any interior box gains a few percent, and a test written on
    one would be asserting the opposite of the property.
    """
    truth = spots((96, 96), n_spots=12)
    psf = gaussian_psf(2.0, (13, 13))
    blurred = ndimage.convolve(truth, psf, mode="constant")
    restored = richardson_lucy(blurred, psf, 40)
    assert abs(restored.sum() / blurred.sum() - 1.0) < 1e-9


def test_the_estimate_never_goes_negative():
    """A count cannot be negative, and the estimator must respect that."""
    truth = spots((96, 96), n_spots=12)
    psf = gaussian_psf(2.0, (13, 13))
    restored = richardson_lucy(blurred_and_counted(truth, psf), psf, 50)
    assert restored.min() >= 0.0


def test_the_iteration_count_is_a_regulariser_not_a_convergence_knob():
    """On noisy data the error against the truth is a U, not a decreasing curve.

    This is the property a caller most needs to know and the one a single-call
    test would hide: past the optimum, more iterations make the restoration
    *worse* while making it look sharper.
    """
    truth = spots()
    psf = gaussian_psf(2.0, (13, 13))
    noisy = blurred_and_counted(truth, psf)

    errors = {
        n_iter: relative_error(richardson_lucy(noisy, psf, n_iter), truth)
        for n_iter in (5, 20, 100, 400)
    }
    assert errors[20] < errors[5], "too few iterations leaves it blurred"
    assert errors[20] < errors[100] < errors[400], "too many amplifies noise"


def test_acceleration_walks_the_same_path_faster():
    """Biggs-Andrews is a step-size change, not a better estimator.

    Pinned because the tempting reading — "acceleration converges better" — is
    wrong in a way that costs image quality: it arrives at the *same* place
    sooner, including the places past the optimum.
    """
    truth = spots()
    psf = gaussian_psf(2.0, (13, 13))
    noisy = blurred_and_counted(truth, psf)

    accelerated = relative_error(richardson_lucy(noisy, psf, 30, acceleration=True), truth)
    plain_400 = relative_error(richardson_lucy(noisy, psf, 400), truth)
    assert abs(accelerated - plain_400) < 0.05, (
        f"30 accelerated ({accelerated:.3f}) should land near 400 plain "
        f"({plain_400:.3f})"
    )
    # And it reaches the optimum in far fewer iterations.
    best_accelerated = min(
        relative_error(richardson_lucy(noisy, psf, n, acceleration=True), truth)
        for n in (3, 5, 10)
    )
    assert best_accelerated < relative_error(richardson_lucy(noisy, psf, 5), truth)


def test_noiseless_deconvolution_converges_to_the_truth():
    """With no noise the maximum likelihood solution *is* the object."""
    truth = np.zeros((48, 52))
    truth[20, 20] = 1.0
    truth[30, 35] = 0.5
    psf = gaussian_psf(1.2, (7, 7))
    blurred = ndimage.convolve(truth, psf, mode="constant")
    restored = richardson_lucy(blurred, psf, 60, acceleration=True)
    np.testing.assert_allclose(restored, truth, atol=1e-3)


# ---------------------------------------------------------------------------
# The PSF
# ---------------------------------------------------------------------------


def test_gaussian_psf_is_normalised_and_centred():
    for sigma, shape in ((1.5, (9, 9)), ((1.0, 2.0), (7, 11)), ((1.0, 1.5, 1.5), None)):
        psf = gaussian_psf(sigma, shape)
        assert abs(psf.sum() - 1.0) < 1e-12
        assert all(extent % 2 == 1 for extent in psf.shape)
        centre = tuple(extent // 2 for extent in psf.shape)
        assert psf[centre] == psf.max(), "the maximum must sit on the centre pixel"


def test_gaussian_psf_refuses_an_even_extent():
    """An even kernel has no centre pixel and shifts the result by half of one."""
    with pytest.raises(ValueError, match="odd"):
        gaussian_psf(1.5, (8, 8))


def test_gaussian_psf_width_is_the_width_asked_for():
    """The second moment of the kernel must be the sigma that was requested."""
    psf = gaussian_psf(2.5, (33, 33))
    coordinates = np.arange(33) - 16
    marginal = psf.sum(axis=0)
    variance = float((marginal * coordinates**2).sum() / marginal.sum())
    assert abs(np.sqrt(variance) - 2.5) < 0.02


def test_psf_sigma_from_optics_is_the_textbook_value():
    """0.21 lambda / NA laterally, 0.66 lambda n / NA^2 axially."""
    sigma_y, sigma_x = psf_sigma_from_optics(520, 1.4, 25)
    assert sigma_x == sigma_y
    assert abs(sigma_x * 25 - 0.21 * 520 / 1.4) < 1e-9

    sigma_z, _, _ = psf_sigma_from_optics(520, 1.4, 25, z_step_nm=100)
    assert abs(sigma_z * 100 - 0.66 * 520 * 1.518 / 1.4**2) < 1e-9
    # Axial resolution is much worse than lateral; a PSF that says otherwise is
    # a sign the arguments were swapped.
    assert sigma_z * 100 > sigma_x * 25


def test_psf_sigma_from_optics_refuses_nonsense():
    for bad in ((0, 1.4, 25), (520, 0, 25), (520, 1.4, 0)):
        with pytest.raises(ValueError):
            psf_sigma_from_optics(*bad)


def test_a_measured_sigma_can_be_used_directly():
    """The bridge from the bead-fitting tool: its sigma is this sigma."""
    measured = {"sigma_z_px": 2.2, "sigma_y_px": 1.4, "sigma_x_px": 1.35}
    psf = gaussian_psf(
        (measured["sigma_z_px"], measured["sigma_y_px"], measured["sigma_x_px"])
    )
    assert psf.ndim == 3
    assert abs(psf.sum() - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# Refusals and the linear alternative
# ---------------------------------------------------------------------------


def test_a_psf_larger_than_the_image_is_refused():
    with pytest.raises(Exception, match="larger than the image|same"):
        richardson_lucy(np.ones((8, 8)), gaussian_psf(2.0, (11, 11)), 5)


def test_mismatched_rank_is_refused():
    with pytest.raises(ValueError, match="must match"):
        richardson_lucy(np.ones((16, 16)), gaussian_psf(1.0, (5, 5, 5)), 5)


def test_wiener_sharpens_but_rings():
    """The linear alternative, and why it is not the default.

    It does sharpen — on this frame the peak goes from 125 back towards the true
    286 — but it pays for that with ringing, so the *total* error is worse than
    the blurred image it started from even while the peaks look better. That is
    the shape of a Gaussian-noise estimator applied to non-negative sparse data,
    and it is the argument for Richardson-Lucy being the default here.
    """
    truth = spots((128, 128), n_spots=20)
    psf = gaussian_psf(2.0, (13, 13))
    blurred = ndimage.convolve(truth, psf, mode="constant")
    restored = wiener_deconvolve(blurred, psf, balance=0.001)

    assert restored.max() > 1.8 * blurred.max(), "it should sharpen the peaks"
    assert restored.min() < 0.0, "and ring negative between them"
    assert relative_error(restored, truth) > relative_error(blurred, truth), (
        "the ringing costs more than the sharpening gains, in total error"
    )
