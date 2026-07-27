"""Fourier-Ring-Correlation resolution estimation.

Tested against images whose resolution is *known* by construction: a random
field low-pass filtered to a chosen cut-off has no reproducible structure above
it, so the FRC must cross its threshold there and nowhere else.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.imaging import frc


def _band_limited_pair(size=256, cutoff=0.15, noise=0.5, seed=1):
    """Two independent noisy views of the same band-limited random field.

    The field is white noise with every Fourier component above *cutoff*
    (cycles/pixel) removed, so the two views share structure below the cut-off
    and share nothing above it — an image whose true resolution is 1/cutoff.
    """
    rng = np.random.default_rng(seed)
    field = rng.normal(size=(size, size))
    fx = np.fft.fftfreq(size)[:, None]
    fy = np.fft.fftfreq(size)[None, :]
    mask = np.sqrt(fx**2 + fy**2) <= cutoff
    truth = np.real(np.fft.ifft2(np.fft.fft2(field) * mask))
    truth /= truth.std()
    return (
        truth + noise * rng.normal(size=truth.shape),
        truth + noise * rng.normal(size=truth.shape),
    )


def _dim_poisson_pair(size=128, cutoff=0.15, counts=1.0, seed=4):
    """Two shot-noise-limited views of the same band-limited field.

    Photon-counting rather than Gaussian noise, and dim enough that the
    count-dependent thresholds start *above* the measured correlation — the
    regime in which the crossing search has to interpolate rather than
    extrapolate.
    """
    rng = np.random.default_rng(1)
    field = rng.normal(size=(size, size))
    fx = np.fft.fftfreq(size)[:, None]
    fy = np.fft.fftfreq(size)[None, :]
    truth = np.real(np.fft.ifft2(np.fft.fft2(field) * (np.sqrt(fx**2 + fy**2) <= cutoff)))
    rate = counts * np.clip(truth / truth.std() + 3.0, 0.0, None) / 3.0
    photons = np.random.default_rng(seed)
    return photons.poisson(rate).astype(float), photons.poisson(rate).astype(float)


def test_identical_images_correlate_perfectly():
    """Two copies of one image agree at every frequency, so nothing crosses."""
    rng = np.random.default_rng(0)
    image = rng.normal(size=(64, 64))
    curve = frc.frc_curve(image, image)
    assert np.allclose(curve.correlation, 1.0, atol=1e-9)
    assert frc.resolve(curve).crossed is False


def test_independent_noise_resolves_nothing():
    """Two unrelated images correlate nowhere, so the crossing is immediate."""
    rng = np.random.default_rng(0)
    curve = frc.frc_curve(rng.normal(size=(128, 128)), rng.normal(size=(128, 128)))
    result = frc.resolve(curve)
    assert result.crossed
    # Nothing is resolved: the crossing sits in the first few rings, i.e. at a
    # resolution of the order of the whole field of view.
    assert result.resolution > 128 / 4


def test_the_crossing_finds_the_band_limit():
    """A field band-limited at 0.15 cycles/px resolves ~6.7 px, not more."""
    a, b = _band_limited_pair(cutoff=0.15)
    result = frc.resolve(frc.frc_curve(a, b))
    assert result.crossed
    assert result.resolution == pytest.approx(1 / 0.15, rel=0.15)


def test_a_finer_image_reports_a_finer_resolution():
    """Doubling the band limit must roughly halve the reported resolution."""
    coarse = frc.resolve(frc.frc_curve(*_band_limited_pair(cutoff=0.10)))
    fine = frc.resolve(frc.frc_curve(*_band_limited_pair(cutoff=0.20)))
    assert fine.resolution < coarse.resolution
    assert fine.resolution / coarse.resolution == pytest.approx(0.5, rel=0.25)


def test_pixel_size_carries_the_answer_into_length_units():
    """With a 20 nm pixel the same image resolves 20x the number of pixels."""
    a, b = _band_limited_pair(cutoff=0.15)
    in_pixels = frc.resolve(frc.frc_curve(a, b))
    in_nm = frc.resolve(frc.frc_curve(a, b, pixel_size=20.0))
    assert in_nm.resolution == pytest.approx(20.0 * in_pixels.resolution, rel=1e-9)


@pytest.mark.parametrize("criterion", frc.CRITERIA)
def test_every_criterion_gives_an_answer_of_the_same_order(criterion):
    """The three conventions disagree, but by tens of per cent, not by orders."""
    a, b = _band_limited_pair(cutoff=0.15)
    result = frc.resolve(frc.frc_curve(a, b), criterion)
    assert result.crossed
    assert 0.5 * (1 / 0.15) < result.resolution < 2.0 * (1 / 0.15)


def test_the_count_dependent_thresholds_start_at_one_and_fall():
    """Neither σ nor ½-bit is uniformly stricter — where they sit follows the rings.

    Both saturate at 1 on the innermost rings, which is why the crossing search
    skips those; as the rings fill, ½-bit tends to 0.172 and 2σ falls without
    limit, crossing the fixed 1/7 at a few hundred Fourier pixels per ring.
    """
    sparse = np.ones(3)
    assert np.allclose(frc.threshold_curve("half_bit", sparse), 1.0)
    assert np.allclose(frc.threshold_curve("two_sigma", sparse), 1.0)

    full = np.full(3, 10**10)
    assert frc.threshold_curve("half_bit", full) == pytest.approx(0.1716, abs=1e-3)
    assert np.all(frc.threshold_curve("two_sigma", full) < 0.01)
    assert np.all(frc.threshold_curve("fixed_1/7", full) == pytest.approx(1 / 7))

    # The cross-over: 2 / sqrt(n/2) == 1/7  =>  n == 392.
    assert frc.threshold_curve("two_sigma", np.array([300.0]))[0] > 1 / 7
    assert frc.threshold_curve("two_sigma", np.array([500.0]))[0] < 1 / 7


def test_rings_are_binned_by_frequency_not_by_index():
    """A non-square image is binned physically, so it resolves like a square one.

    Binning on the raw FFT index radius would stretch the short axis: the same
    band-limited field cropped to a strip would report a different resolution
    for no physical reason.
    """
    a, b = _band_limited_pair(size=256, cutoff=0.15)
    square = frc.resolve(frc.frc_curve(a, b)).resolution
    strip = frc.resolve(frc.frc_curve(a[:64], b[:64])).resolution
    assert strip == pytest.approx(square, rel=0.25)


@pytest.mark.parametrize("criterion", frc.CRITERIA)
def test_the_crossing_is_interpolated_not_extrapolated(criterion):
    """A dim image resolves its band limit under every criterion.

    On shot-noise data the count-dependent thresholds sit above the correlation
    for the first few rings. Taking the first ring that is merely *below* the
    line then extrapolates from a ring that was never above it, and the reported
    crossing lands outside the two rings it was computed from — 2σ read 45 px
    here where the band limit is 6.7 px.
    """
    a, b = _dim_poisson_pair(cutoff=0.15)
    result = frc.resolve(frc.frc_curve(a, b), criterion)
    assert result.crossed
    assert result.resolution == pytest.approx(1 / 0.15, rel=0.3)


@pytest.mark.parametrize("shape", [(65, 65), (64, 64), (127, 33), (32, 65)])
def test_every_fourier_pixel_lands_in_a_ring(shape):
    """No frequency is left out of the ring sums, odd axis lengths included.

    Every pixel of the spectrum is inside the outermost ring, so the occupancies
    must add up to the size of the image. Running the axes to ``n // 2`` instead
    of ``(n + 1) // 2`` dropped the highest positive frequency of an odd axis —
    4096 of 4225 pixels at 65x65 — and the loss falls in the outer rings, which
    are exactly the ``counts`` the 1/2-bit and 2-sigma thresholds are built from.
    """
    nx, ny = shape
    bin_width = 1.0 / max(shape)
    n_bins = int(np.sqrt(0.5**2 + 0.5**2) / bin_width) + 1
    empty = np.zeros(shape)
    *_, counts = frc._ring_sums(empty, empty, empty, nx, ny, n_bins, bin_width)
    assert counts.sum() == nx * ny

    # And they land in the *right* rings: bin the same frequencies directly.
    axes = [(np.arange(n) - n * (np.arange(n) > (n - 1) // 2)) / n for n in shape]
    radius = np.sqrt(axes[0][:, None] ** 2 + axes[1][None, :] ** 2)
    reference = np.bincount((radius / bin_width).astype(int).ravel(), minlength=n_bins)
    assert np.array_equal(counts, reference)

    # The public curve keeps the rings the sampling can report, unchanged.
    rng = np.random.default_rng(0)
    curve = frc.frc_curve(rng.normal(size=shape), rng.normal(size=shape))
    frequency = (np.arange(n_bins) + 0.5) * bin_width
    assert np.array_equal(curve.counts, reference[(reference > 0) & (frequency <= 0.5)])


@pytest.mark.parametrize("criterion", frc.CRITERIA)
@pytest.mark.parametrize("seed", range(6))
def test_a_crossing_is_never_reported_outside_the_frequency_axis(criterion, seed):
    """Halves that share nothing cross nowhere — they never report a frequency.

    Two unrelated images stay below the count-dependent thresholds from the
    innermost ring on, so there is no downward crossing to find. Reporting one
    anyway extrapolated backwards past the first ring and produced negative
    frequencies, i.e. negative resolutions, which the GUI printed verbatim.
    """
    rng = np.random.default_rng(seed)
    curve = frc.frc_curve(rng.normal(size=(128, 128)), rng.normal(size=(128, 128)))
    result = frc.resolve(curve, criterion)
    if result.crossed:
        assert curve.frequency[0] <= result.frequency <= curve.frequency[-1]
        assert result.resolution > 0.0
    else:
        assert np.isnan(result.frequency)


def test_a_stack_splits_into_two_independent_halves():
    """Even/odd is the default split; halves is there for correlated frames."""
    stack = np.arange(4 * 2 * 3, dtype=float).reshape(4, 2, 3)
    even, odd = frc.split_frames(stack)
    assert np.allclose(even, stack[0] + stack[2])
    assert np.allclose(odd, stack[1] + stack[3])
    first, second = frc.split_frames(stack, "halves")
    assert np.allclose(first, stack[0] + stack[1])
    assert np.allclose(second, stack[2] + stack[3])


def test_inputs_that_cannot_be_correlated_are_rejected():
    """Each is a mistake a caller can make; none may reach the maths."""
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError):
        frc.frc_curve(rng.normal(size=(8, 8)), rng.normal(size=(8, 16)))
    with pytest.raises(ValueError):
        frc.frc_curve(rng.normal(size=8), rng.normal(size=8))
    with pytest.raises(ValueError):
        frc.frc_curve(rng.normal(size=(8, 8)), rng.normal(size=(8, 8)), pixel_size=0.0)
    with pytest.raises(ValueError):
        frc.threshold_curve("one_bit", np.ones(3))
    with pytest.raises(ValueError):
        frc.split_frames(np.zeros((4, 4)))
    with pytest.raises(ValueError):
        frc.split_frames(np.zeros((1, 4, 4)))
