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


# ---------------------------------------------------------------------------
# Single-photon data: the pixel is a sweep, not a sample
# ---------------------------------------------------------------------------


def _has_event_mode():
    import tttrlib

    return hasattr(tttrlib, "richardson_lucy_events_2d")


events_only = pytest.mark.skipif(
    not _has_event_mode(), reason="the photon library has no event-mode deconvolution"
)


def marginal_width(psf, axis):
    """Second moment of a PSF's marginal along one axis, in pixels."""
    marginal = psf.sum(axis=1 - axis)
    coordinates = np.arange(len(marginal)) - len(marginal) // 2
    mean = (marginal * coordinates).sum() / marginal.sum()
    return float(
        np.sqrt((marginal * (coordinates - mean) ** 2).sum() / marginal.sum())
    )


@pytest.mark.parametrize("sigma", [0.9, 1.3, 2.0])
def test_the_scan_sweep_widens_the_psf_by_exactly_one_rectangle(sigma):
    """The dwell adds variance 1/12 on the fast axis and nothing on the other.

    This is the number the whole single-photon correction rests on: a pixel is
    the interval the beam swept, so the effective PSF is the optical one
    convolved with a unit rectangle, and a rectangle of width 1 has variance
    1/12.
    """
    from chisurf.core.fluorescence.imaging.restoration import effective_psf

    optical = gaussian_psf(sigma, (21, 21))
    effective = effective_psf(optical, dwell_seconds=1e-6)

    expected = np.sqrt(sigma**2 + 1.0 / 12.0)
    assert abs(marginal_width(effective, 1) - expected) < 5e-3
    assert abs(marginal_width(effective, 0) - marginal_width(optical, 0)) < 1e-6
    assert abs(effective.sum() - 1.0) < 1e-12


def test_effective_psf_is_not_a_no_op():
    """Guards the trap the implementation exists to avoid.

    A one-pixel rectangle *sampled at one-pixel spacing* is a delta, so
    convolving the two sampled kernels does nothing whatsoever — and leaves the
    caller believing the sweep was corrected for. This asserts the PSF actually
    changed.
    """
    from chisurf.core.fluorescence.imaging.restoration import effective_psf

    optical = gaussian_psf(1.3, (15, 15))
    effective = effective_psf(optical, dwell_seconds=1e-6)
    assert not np.allclose(effective, optical, atol=1e-6)
    assert marginal_width(effective, 1) > marginal_width(optical, 1) + 0.02


@events_only
def test_the_timing_terms_are_negligible_at_a_normal_dwell():
    """Jitter and clock resolution map to position through the scan speed.

    At 100 ps jitter and a 1 µs dwell that is 1e-4 pixels. Asserted so nobody
    spends effort modelling it before checking whether it matters — and so the
    fast-scanning case, where it does, is a change this test would notice.
    """
    from chisurf.core.fluorescence.imaging.restoration import scan_blur_kernel

    without_sweep = np.asarray(
        scan_blur_kernel(1e-6, jitter_seconds=100e-12, resolution_seconds=25e-9,
                         oversampling=4, include_dwell=False)
    )
    # Everything lands in one sample: the timing blur is far below one pixel.
    assert without_sweep.max() > 0.999

    with_sweep = np.asarray(scan_blur_kernel(1e-6, oversampling=4))
    coordinates = (np.arange(len(with_sweep)) - len(with_sweep) // 2) * 0.25
    mean = (with_sweep * coordinates).sum()
    sigma = np.sqrt((with_sweep * (coordinates - mean) ** 2).sum())
    # The sweep alone, plus the quarter-pixel resampling of the kernel itself.
    assert 0.28 < sigma < 0.32


@events_only
def test_event_mode_beats_binning_at_the_same_photon_count():
    """The claim single-photon compatibility is *for*.

    Same photons, same PSF, same iterations — the only difference is whether
    each photon's sub-pixel position was kept or rounded to its pixel. Keeping
    it concentrates markedly more of the signal into the true position.
    """
    from chisurf.core.fluorescence.imaging.restoration import richardson_lucy_events

    rng = np.random.default_rng(1)
    n_photons = 200_000
    centres = np.where(rng.random(n_photons) < 0.5, 14.0, 18.0)
    rows = 16.0 + rng.normal(0, 1.3, n_photons)
    columns = centres + rng.normal(0, 1.3, n_photons)
    # 5.8 sigma of support: truncation, not interpolation, is what limits how
    # accurately a photon reconstructs to its own position.
    psf = gaussian_psf(1.3, (15, 15))

    event_wise = richardson_lucy_events(
        np.column_stack([rows, columns]), psf, (32, 32), 60
    )
    binned = richardson_lucy_events(
        np.column_stack([np.floor(rows + 0.5), np.floor(columns + 0.5)]),
        psf,
        (32, 32),
        60,
    )

    # Photons are redistributed, never created or lost, either way.
    assert abs(event_wise.sum() / n_photons - 1.0) < 1e-9
    assert abs(binned.sum() / n_photons - 1.0) < 1e-9

    peak_event = 2 * event_wise[16, 14] / n_photons
    peak_binned = 2 * binned[16, 14] / n_photons
    assert peak_event > peak_binned + 0.06, (
        f"event-wise concentrated {peak_event:.3f} against binned {peak_binned:.3f}"
    )


@events_only
def test_event_mode_conserves_photons_and_stays_non_negative():
    """What list-mode conserves is the *sensitivity-weighted* total.

    The iteration makes ``sum(f * s)`` exactly the photon count, where ``s`` is
    the fraction of each pixel's PSF that falls inside the frame. In the
    interior ``s`` is 1 and the bare sum is conserved to rounding; near the
    border ``s < 1``, so a reconstruction with mass out there sums slightly
    high — correctly, because those pixels emitted photons the frame could not
    catch. Spreading photons to within four pixels of the edge is enough to see
    it, at about one part in a million.
    """
    from chisurf.core.fluorescence.imaging.restoration import richardson_lucy_events

    rng = np.random.default_rng(4)
    coordinates = rng.uniform(4, 28, (5000, 2))
    psf = gaussian_psf(1.5, (9, 9))
    restored = richardson_lucy_events(coordinates, psf, (32, 32), 20)
    assert restored.min() >= 0.0
    assert 1.0 <= restored.sum() / 5000 < 1.0 + 1e-4

    # Well away from the border the sensitivity is one and the sum is exact.
    interior = richardson_lucy_events(
        rng.uniform(12, 20, (5000, 2)), psf, (32, 32), 20
    )
    assert abs(interior.sum() / 5000 - 1.0) < 1e-9


@events_only
def test_event_mode_can_reconstruct_finer_than_the_acquisition_grid():
    """Sub-pixel positions are only worth keeping if they can be cashed in."""
    from chisurf.core.fluorescence.imaging.restoration import richardson_lucy_events

    rng = np.random.default_rng(5)
    n_photons = 50_000
    rows = 16.0 + rng.normal(0, 1.0, n_photons)
    columns = 16.0 + rng.normal(0, 1.0, n_photons)
    # Twice the sampling: coordinates and PSF both scale.
    fine = richardson_lucy_events(
        np.column_stack([rows * 2, columns * 2]), gaussian_psf(2.0, (17, 17)), (64, 64), 30
    )
    assert fine.shape == (64, 64)
    assert abs(fine.sum() / n_photons - 1.0) < 1e-9
    peak = np.unravel_index(int(np.argmax(fine)), fine.shape)
    assert abs(peak[0] - 32) <= 1 and abs(peak[1] - 32) <= 1


@events_only
def test_event_mode_refuses_the_wrong_shape():
    from chisurf.core.fluorescence.imaging.restoration import richardson_lucy_events

    with pytest.raises(ValueError, match=r"\(n_photons, 2\)"):
        richardson_lucy_events(np.zeros((10, 3)), gaussian_psf(1.0, (5, 5)), (16, 16))


@events_only
def test_oversample_psf_preserves_the_kernel_it_refines():
    """Refining is a resampling, not a reshaping.

    The refined kernel has to describe the same optics: same total, same width,
    same centre. Cubic interpolation can overshoot into negatives at a sharp
    edge, which would put negative probability into the forward model, so that
    is clipped and asserted.
    """
    from chisurf.core.fluorescence.imaging.restoration import oversample_psf

    psf = gaussian_psf(1.5, (15, 15))
    for factor in (1, 4, 8):
        fine = oversample_psf(psf, factor)
        assert fine.shape == (14 * factor + 1,) * 2
        assert fine.min() >= 0.0
        # Sampled back at pixel spacing, it is the kernel it came from.
        phase = ((fine.shape[0] - 1) // 2) % factor
        np.testing.assert_allclose(
            fine[phase::factor, phase::factor], psf, atol=1e-12
        )


def test_oversample_psf_refuses_an_even_kernel():
    """An even kernel has no sample at its centre to resample about."""
    from chisurf.core.fluorescence.imaging.restoration import oversample_psf

    with pytest.raises(ValueError, match="odd extent"):
        oversample_psf(np.ones((4, 4)) / 16, 4)
