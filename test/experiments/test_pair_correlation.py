"""Pair correlation and velocity fields: does the arrow point the right way?

Everything here is built on phantoms with a *known* velocity, because the one
error a correlation analysis makes silently is a mirrored direction. Every
number stays plausible -- the speed is right, the peak is sharp, the fit is
good -- and the physics is backwards. Two conventions are pinned by name:

* the STICS correlation peak moves **against** the flow, because the carpet
  correlates frame ``i`` with frame ``i+lag``;
* the pair correlation peaks at **+delta** for flow towards ``+x``, and does
  not peak at ``-delta``.

The barrier test is the one with the most diagnostic value in the file: it is
what fails if the carpet is secretly an autocorrelation map, which every other
test here would happily pass.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.experiments.ics.data import IcsSettings, IcsTiming
from chisurf.core.experiments.ics.flow_map import (
    pcf_flow_map,
    stics_flow_map,
    tile_slices,
)
from chisurf.core.experiments.ics.ics_core import compute_ics_carpet
from chisurf.core.experiments.ics.pair_correlation import (
    correct_bleaching,
    kymograph,
    log_lag_bins,
    pcf_from_kymograph,
)

#: Pixel size 100 nm, line 1 ms -- round numbers so an expected transit time can
#: be worked out in the head of whoever reads a failure.
TIMING = IcsTiming(
    pixel_duration_us=10.0,
    line_duration_ms=1.0,
    frame_duration_ms=0.0,
    pixel_size_nm=100.0,
)


def drifting_kymograph(
    velocity: float = 0.25,
    n_time: int = 4000,
    n_x: int = 64,
    n_molecules: int = 40,
    width: float = 2.0,
    brightness: float = 20.0,
    seed: int = 3,
    barrier: int = -1,
) -> np.ndarray:
    """Return a ``(n_time, n_x)`` kymograph of blobs drifting along ``+x``.

    Parameters
    ----------
    velocity : float
        Drift in pixels per time sample.
    n_time, n_x : int
        Record length and number of positions.
    n_molecules : int
        Number of emitters.
    width : float
        Gaussian width of one emitter, in pixels.
    brightness : float
        Photon rate scale; the trace is Poisson-sampled from it.
    seed : int
        Random seed.
    barrier : int
        Position of an impermeable wall. Emitters then stay on the side they
        started, wrapping within it, so no correlation can cross. ``-1``
        disables it and the whole line is one compartment.

    Returns
    -------
    numpy.ndarray
        Poisson-sampled intensity of shape ``(n_time, n_x)``.
    """
    rng = np.random.default_rng(seed)
    grid = np.arange(n_x, dtype=float)
    start = rng.uniform(0, n_x, n_molecules)
    if barrier >= 0:
        left = start < barrier
        spans = np.where(left, float(barrier), float(n_x - barrier))
        origin = np.where(left, 0.0, float(barrier))
    else:
        spans = np.full(n_molecules, float(n_x))
        origin = np.zeros(n_molecules)

    t = np.arange(n_time, dtype=float)[:, None]
    centre = origin + (start - origin + velocity * t) % spans
    dx = np.abs(grid[None, :, None] - centre[:, None, :])
    dx = np.minimum(dx, n_x - dx)
    rate = np.exp(-(dx ** 2) / (2.0 * width ** 2)).sum(axis=2)
    return rng.poisson(rate * brightness).astype(float)


def drifting_stack(
    velocity: float = 0.5,
    n: int = 32,
    n_frames: int = 200,
    n_molecules: int = 40,
    width: float = 1.6,
    brightness: float = 30.0,
    seed: int = 11,
    axis: str = "x",
) -> np.ndarray:
    """Return a ``(n_frames, n, n)`` stack of blobs drifting at *velocity*.

    Parameters
    ----------
    velocity : float
        Drift in pixels per frame.
    n : int
        Image side length.
    n_frames : int
        Number of frames.
    n_molecules : int
        Number of emitters.
    width : float
        Gaussian width of one emitter, in pixels.
    brightness : float
        Photon rate scale; the stack is Poisson-sampled from it.
    seed : int
        Random seed.
    axis : str
        ``'x'`` for the fast scan axis, ``'y'`` for the slow one.

    Returns
    -------
    numpy.ndarray
        Poisson-sampled stack of shape ``(n_frames, n, n)``.
    """
    rng = np.random.default_rng(seed)
    molecules = rng.uniform(0, n, size=(n_molecules, 2))
    ys, xs = np.indices((n, n))
    frames = []
    for f in range(n_frames):
        image = np.zeros((n, n))
        for cy, cx in molecules:
            if axis == "x":
                cx = (cx + velocity * f) % n
            else:
                cy = (cy + velocity * f) % n
            dx = np.abs(xs - cx)
            dy = np.abs(ys - cy)
            dx = np.minimum(dx, n - dx)
            dy = np.minimum(dy, n - dy)
            image += np.exp(-(dx ** 2 + dy ** 2) / (2.0 * width ** 2))
        frames.append(image)
    return rng.poisson(np.asarray(frames) * brightness).astype(float)


def scan_timing(n: int, line_ms: float = 0.32, pixel_nm: float = 100.0) -> IcsTiming:
    """Return a timing for an ``n``-line scan with a resolved frame time.

    Parameters
    ----------
    n : int
        Number of lines per frame.
    line_ms : float
        Line duration in milliseconds.
    pixel_nm : float
        Pixel size in nanometres.

    Returns
    -------
    IcsTiming
        Timing with the frame duration filled in.
    """
    return IcsTiming(
        pixel_duration_us=line_ms * 1e3 / n,
        line_duration_ms=line_ms,
        frame_duration_ms=n * line_ms,
        pixel_size_nm=pixel_nm,
    )


# ──────────────────────────────────────────────────────────────────────────────
# The plumbing
# ──────────────────────────────────────────────────────────────────────────────
def test_a_kymograph_keeps_acquisition_order():
    """Frame and line axes flatten in the order the scanner visited them."""
    stack = np.arange(2 * 3 * 4).reshape(2, 3, 4)
    flat = kymograph(stack)
    assert flat.shape == (6, 4)
    assert np.array_equal(flat[0], stack[0, 0])
    assert np.array_equal(flat[3], stack[1, 0])
    # Channels are summed, not stacked, so a two-channel stack has the same
    # shape as a one-channel one.
    assert kymograph(np.ones((2, 3, 4, 2))).shape == (6, 4)


def test_log_lag_bins_tile_the_lag_axis_without_gaps():
    """Every lag from 1 to the maximum lands in exactly one bin."""
    bins = log_lag_bins(500, n_linear=16, per_octave=8)
    assert bins[0] == (1, 2)
    assert bins[-1][1] == 501
    covered = [lag for start, stop in bins for lag in range(start, stop)]
    assert covered == list(range(1, 501))
    # The linear head is kept sample by sample -- that is where a fast transit
    # sits, and averaging there would smear the peak that is being measured.
    assert all(stop - start == 1 for start, stop in bins[:16])
    assert bins[-1][1] - bins[-1][0] > 1


def test_bleaching_correction_keeps_the_relative_fluctuation():
    """A decaying trace is flattened *and* its fluctuations are rescaled.

    Subtracting the trend alone is not enough: shot noise shrinks with the mean,
    so the second half of a bleached record has smaller fluctuations than the
    first even after the trend is gone. ``G(0) = 1/N`` is read as a
    concentration, so that leftover drift is reported as molecules
    disappearing.
    """
    rng = np.random.default_rng(0)
    n, half = 4000, 2000
    trend = 100.0 * np.exp(-np.arange(n) / 2885.0)  # decays to a quarter
    trace = rng.poisson(trend).astype(float)[:, None]

    # Shot noise scales as the square root of the rate, so the fluctuation about
    # the trend shrinks measurably as the trace decays. This is what a plain
    # high-pass leaves behind.
    residual = trace[:, 0] - trend
    assert residual[half:].std() < 0.75 * residual[:half].std()

    fixed = correct_bleaching(trace, window=401)
    assert abs(fixed.mean() - trace.mean()) < 1.0
    # No trend left: the two halves now have the same mean...
    assert abs(fixed[:half].mean() - fixed[half:].mean()) < 2.0
    # ...and, the part a plain high-pass misses, the same fluctuation size.
    ratio = fixed[half:].std() / fixed[:half].std()
    assert 0.85 < ratio < 1.2


# ──────────────────────────────────────────────────────────────────────────────
# Direction: the convention that fails silently
# ──────────────────────────────────────────────────────────────────────────────
def test_the_pair_correlation_peaks_downstream_only():
    """Flow towards ``+x`` correlates with ``+delta`` and not with ``-delta``.

    This is the whole point of a *pair* correlation, and the check that a
    mirrored axis cannot survive. At 0.25 pixels per sample a molecule needs 16
    samples to cross 4 pixels, so the ``+4`` curve must peak there; the ``-4``
    curve has no molecules arriving at all and must stay both lower and later.
    """
    intensity = drifting_kymograph(velocity=0.25)
    carpet = pcf_from_kymograph(intensity, deltas=(0, 4, -4), timing=TIMING)

    tau_f, g_f, _ = carpet.curve(+4)
    tau_b, g_b, _ = carpet.curve(-4)
    peak_f = tau_f[int(np.nanargmax(g_f))]
    expected = 4.0 / 0.25 * TIMING.line_duration_ms * 1e-3  # 16 ms

    assert peak_f == pytest.approx(expected, rel=0.25)
    assert np.nanmax(g_f) > 3.0 * np.nanmax(g_b)
    assert tau_b[int(np.nanargmax(g_b))] > peak_f

    # Zero distance is the ordinary autocorrelation, and it must decay from the
    # first lag rather than peak anywhere.
    _, g_0, _ = carpet.curve(0)
    assert int(np.nanargmax(g_0)) == 0


def test_the_transit_time_and_velocity_are_recovered():
    """The peak position is a transit time, and it gives back the drift."""
    velocity = 0.25  # pixels per sample
    intensity = drifting_kymograph(velocity=velocity)
    carpet = pcf_from_kymograph(intensity, deltas=(3, -3, 6, -6), timing=TIMING)

    dt = TIMING.line_duration_ms * 1e-3
    for distance in (3, 6):
        transit = np.nanmedian(carpet.transit_time(distance))
        assert transit == pytest.approx(distance / velocity * dt, rel=0.25)

    # Twice the distance, twice the transit time: transport is ballistic, not
    # diffusive. A diffusive sample would give four times.
    ratio = np.nanmedian(carpet.transit_time(6)) / np.nanmedian(carpet.transit_time(3))
    assert 1.6 < ratio < 2.5

    expected = velocity * TIMING.pixel_size_nm * 1e-3 / dt  # 25 um/s
    assert np.nanmedian(carpet.velocity(3)) == pytest.approx(expected, rel=0.25)


def test_the_velocity_sign_follows_the_flow():
    """Reversing the drift reverses the reported velocity, nothing else."""
    forward = pcf_from_kymograph(
        drifting_kymograph(velocity=+0.25), deltas=(4, -4), timing=TIMING
    )
    backward = pcf_from_kymograph(
        drifting_kymograph(velocity=-0.25), deltas=(4, -4), timing=TIMING
    )
    v_f = np.nanmedian(forward.velocity(4))
    v_b = np.nanmedian(backward.velocity(4))
    assert v_f > 0.0 > v_b
    assert abs(v_f) == pytest.approx(abs(v_b), rel=0.25)


# ──────────────────────────────────────────────────────────────────────────────
# The barrier: the test that catches an autocorrelation in disguise
# ──────────────────────────────────────────────────────────────────────────────
def test_a_barrier_deletes_the_pair_correlation_but_not_the_local_one():
    """Across an impermeable wall the correlation vanishes; beside it, it does not.

    A barrier is what separates a pair correlation from anything else. It does
    not slow molecules down and it does not dim the image -- both sides stay
    exactly as bright and as noisy as before, and the *auto*correlation at a
    position right next to the wall is unremarkable. Only the correlation
    *across* it disappears.

    An implementation that had quietly reduced to an autocorrelation map, or one
    that had lost its position axis to a spatial FFT, passes every other test in
    this file and fails this one.
    """
    n_x, wall, distance = 64, 32, 6
    intensity = drifting_kymograph(
        velocity=0.25, n_x=n_x, barrier=wall, n_molecules=20,
        n_time=8000, brightness=60.0, width=1.0,
    )
    carpet = pcf_from_kymograph(intensity, deltas=(0, distance), timing=TIMING)

    transit = carpet.transit_time(distance)
    expected = distance / 0.25 * TIMING.line_duration_ms * 1e-3  # 24 ms

    # Everywhere the pair lies inside one compartment the transit time is the
    # right one, to better than a percent.
    inside = np.concatenate([transit[:wall - 8], transit[wall + 4:n_x - distance]])
    assert np.all(np.isfinite(inside))
    assert np.allclose(inside, expected, rtol=0.15)

    # Straddling the wall it is not merely longer, it is absent: what the peak
    # finder lands on there is the tail of the curve, several times too late.
    # The pixel immediately against the wall is left out on purpose -- an
    # emitter one pixel from the wall still lights the pixel on the far side of
    # it, so a barrier is localized to about a spot width and no better.
    straddling = transit[wall - 4:wall - 1]
    assert np.all(straddling > 2.5 * expected)

    crossing = carpet.map(distance)[wall - 3]
    within = carpet.map(distance)[wall - 12]
    assert np.nanmax(within) > 3.0 * np.nanmax(crossing)

    # ...while the local autocorrelation on the wall is as strong as anywhere.
    auto = carpet.map(0)
    assert np.nanmax(auto[wall - 3]) > 0.8 * np.nanmax(auto[wall - 12])
    # ...and so is the intensity: nothing about the image says "wall here".
    profile = intensity.mean(axis=0)
    assert profile[wall - 3] > 0.8 * profile[wall - 12]


# ──────────────────────────────────────────────────────────────────────────────
# An independent implementation has to agree
# ──────────────────────────────────────────────────────────────────────────────
def test_the_fft_kernel_matches_a_direct_correlation():
    """A/B against the definition, evaluated as a plain loop over lags.

    The FFT route is fast and every one of its steps -- zero padding, the
    conjugation order, the overlap normalisation -- is a place a factor or a
    sign can hide. The direct sum has none of them.
    """
    intensity = drifting_kymograph(n_time=600, n_x=16, n_molecules=8, seed=5)
    carpet = pcf_from_kymograph(
        intensity, deltas=(2,), timing=TIMING, n_segments=1, n_linear=8, max_lag=8
    )

    n_time = intensity.shape[0]
    position = 4
    a = intensity[:, position]
    b = intensity[:, position + 2]
    fluctuation_a, fluctuation_b = a - a.mean(), b - b.mean()
    for k, tau in enumerate(carpet.tau[:8]):
        lag = int(round(tau / (TIMING.line_duration_ms * 1e-3)))
        if lag < 1:
            continue
        direct = float(
            (fluctuation_a[: n_time - lag] * fluctuation_b[lag:]).sum()
            / (n_time - lag)
            / (a.mean() * b.mean())
        )
        assert carpet.correlation[0, position, k] == pytest.approx(direct, rel=1e-9)


def test_a_position_without_a_partner_is_not_invented():
    """The last positions have no neighbour at ``+delta``; they stay ``NaN``."""
    carpet = pcf_from_kymograph(
        drifting_kymograph(n_time=600, n_x=16, seed=7), deltas=(3, -3), timing=TIMING
    )
    forward = carpet.map(+3)
    assert np.all(np.isnan(forward[-3:]))
    assert np.all(np.isfinite(forward[:-3]))
    backward = carpet.map(-3)
    assert np.all(np.isnan(backward[:3]))
    assert np.all(np.isfinite(backward[3:]))
    # And a transit time is not reported for them either.
    assert np.all(np.isnan(carpet.transit_time(+3)[-3:]))


def test_a_pcf_without_a_time_axis_is_refused():
    """A timing with no line duration cannot produce a transit time."""
    intensity = drifting_kymograph(n_time=400, n_x=8, seed=1)
    with pytest.raises(ValueError, match="frame duration is not set"):
        pcf_from_kymograph(intensity, (1,), IcsTiming(frame_duration_ms=0.0),
                           time_unit="frame")
    with pytest.raises(ValueError, match="n_time, n_positions"):
        pcf_from_kymograph(np.zeros((3, 4, 5)), (1,), TIMING)
    with pytest.raises(ValueError, match="segments"):
        pcf_from_kymograph(intensity[:30], (1,), TIMING, n_segments=8)


# ──────────────────────────────────────────────────────────────────────────────
# The carpet's own readings
# ──────────────────────────────────────────────────────────────────────────────
def test_the_carpet_pcf_at_zero_distance_is_the_tics_decay():
    """``pcf_curve(0)`` and ``tics_curve()`` are the same column of one carpet."""
    stack = drifting_stack(velocity=0.5, n=24, n_frames=60, seed=2)
    timing = scan_timing(24)
    carpet = compute_ics_carpet(
        stack, IcsSettings(frame_lags=tuple(range(4)), timing=timing)
    )
    tau_t, g_t = carpet.tics_curve()
    tau_p, g_p = carpet.pcf_curve(0)
    assert np.allclose(tau_t, tau_p)
    assert np.allclose(g_t, g_p)

    distances, maps = carpet.pcf_map()
    assert maps.shape == (stack.shape[2], carpet.n_lags)
    assert np.allclose(maps[int(np.argmin(np.abs(distances)))], g_p)

    with pytest.raises(ValueError, match="outside the carpet"):
        carpet.pcf_curve(10_000)
    with pytest.raises(ValueError, match="must be 'pixel' or 'line'"):
        carpet.pcf_curve(0, axis="frame")


def test_the_stics_peak_moves_against_the_flow():
    """The sign convention of the carpet, pinned to a whole-pixel displacement.

    The carpet correlates frame ``i`` with frame ``i+lag``, and with that
    conjugation order a sample drifting towards ``+x`` puts the peak at
    **negative** pixel lag. Whole-pixel drift is used so the expected answer is
    exact and no sub-pixel estimator is on trial here.
    """
    stack = drifting_stack(velocity=1.0, n=32, n_frames=120, seed=13)
    timing = scan_timing(32)
    carpet = compute_ics_carpet(
        stack, IcsSettings(frame_lags=tuple(range(5)), timing=timing)
    )
    for lag in range(5):
        xi, psi = carpet.peak_shift(lag)
        assert xi == pytest.approx(-1.0 * lag, abs=0.15)
        assert psi == pytest.approx(0.0, abs=0.15)

    flow = carpet.velocity()
    expected = 1.0 * timing.pixel_size_nm * 1e-3 / (timing.frame_duration_ms * 1e-3)
    assert flow.vx == pytest.approx(expected, rel=0.05)
    assert abs(flow.vy) < 0.05 * expected
    assert flow.quality > 0.95
    assert flow.speed == pytest.approx(expected, rel=0.05)
    assert flow.angle == pytest.approx(0.0, abs=0.05)


def test_the_slow_axis_is_not_the_fast_axis():
    """Drift along the lines shows up in ``vy``, not in ``vx``."""
    stack = drifting_stack(velocity=1.0, n=32, n_frames=120, seed=13, axis="y")
    timing = scan_timing(32)
    carpet = compute_ics_carpet(
        stack, IcsSettings(frame_lags=tuple(range(5)), timing=timing)
    )
    flow = carpet.velocity()
    assert flow.vy > 0.0
    assert abs(flow.vx) < 0.1 * abs(flow.vy)


def test_the_gaussian_peak_fit_beats_the_centroid_on_sub_pixel_drift():
    """Sub-pixel is where the two estimators part company.

    A centre of mass over a window narrower than the peak is pulled towards the
    brightest pixel, so it reports displacements quantized towards whole
    pixels -- and the velocity fitted through them comes out wrong by a fifth.
    At whole-pixel displacements both estimators agree exactly, which is what
    makes the bias easy to ship.
    """
    stack = drifting_stack(velocity=0.2, n=32, n_frames=400, seed=11)
    timing = scan_timing(32)
    carpet = compute_ics_carpet(
        stack, IcsSettings(frame_lags=tuple(range(5)), timing=timing)
    )
    expected = 0.2 * timing.pixel_size_nm * 1e-3 / (timing.frame_duration_ms * 1e-3)
    gauss = carpet.velocity(method="gauss").vx
    centroid = carpet.velocity(method="centroid", window=2).vx
    assert abs(gauss - expected) < abs(centroid - expected)
    # A fifth of a pixel per frame is a hard measurement: this many molecules
    # and frames leave ~10 % scatter on the answer, so the tolerance is what the
    # phantom supports, not what the estimator can do in principle.
    assert gauss == pytest.approx(expected, rel=0.15)

    with pytest.raises(ValueError, match="'gauss' or 'centroid'"):
        carpet.peak_shift(0, method="parabola")


def test_a_velocity_needs_a_time_and_a_length():
    """Without a frame time or a pixel size a peak shift is not a velocity."""
    stack = drifting_stack(velocity=1.0, n=24, n_frames=40, seed=4)
    one_lag = compute_ics_carpet(
        stack, IcsSettings(frame_lags=(0,), timing=scan_timing(24))
    )
    with pytest.raises(ValueError, match="at least two frame lags"):
        one_lag.velocity()

    blind = compute_ics_carpet(
        stack,
        IcsSettings(
            frame_lags=(0, 1, 2),
            timing=IcsTiming(frame_duration_ms=0.0, pixel_size_nm=0.0),
        ),
    )
    with pytest.raises(ValueError, match="frame time and a pixel size"):
        blind.velocity()


# ──────────────────────────────────────────────────────────────────────────────
# The arrows
# ──────────────────────────────────────────────────────────────────────────────
def banded_stack(
    velocities=(-0.5, 0.0, 0.5),
    n: int = 48,
    n_frames: int = 120,
    per_band: int = 30,
    width: float = 1.6,
    seed: int = 5,
) -> np.ndarray:
    """Return a stack whose horizontal bands each drift at their own speed.

    Parameters
    ----------
    velocities : sequence of float
        Drift of each band along ``+x``, in pixels per frame.
    n : int
        Image side length.
    n_frames : int
        Number of frames.
    per_band : int
        Emitters per band.
    width : float
        Gaussian width of one emitter, in pixels.
    seed : int
        Random seed.

    Returns
    -------
    numpy.ndarray
        Poisson-sampled stack of shape ``(n_frames, n, n)``.
    """
    rng = np.random.default_rng(seed)
    band = n // len(velocities)
    molecules = [
        (rng.uniform(b * band, (b + 1) * band), rng.uniform(0, n), v)
        for b, v in enumerate(velocities)
        for _ in range(per_band)
    ]
    ys, xs = np.indices((n, n))
    frames = []
    for f in range(n_frames):
        image = np.zeros((n, n))
        for cy, cx, v in molecules:
            dx = np.abs(xs - (cx + v * f) % n)
            dy = np.abs(ys - cy)
            dx = np.minimum(dx, n - dx)
            dy = np.minimum(dy, n - dy)
            image += np.exp(-(dx ** 2 + dy ** 2) / (2.0 * width ** 2))
        frames.append(image)
    return rng.poisson(np.asarray(frames) * 30.0).astype(float)


def test_tiles_cover_the_axis_and_end_on_the_edge():
    """The last tile is pulled back rather than dropped."""
    assert tile_slices(10, 4, 4) == [(0, 4), (4, 8), (6, 10)]
    assert tile_slices(16, 4, 4) == [(0, 4), (4, 8), (8, 12), (12, 16)]
    assert tile_slices(16, 8, 4) == [(0, 8), (4, 12), (8, 16)]
    assert tile_slices(4, 8, 8) == [(0, 4)]


def test_the_flow_map_finds_a_velocity_per_band():
    """Three bands, three velocities, and the middle one is genuinely still."""
    n = 48
    stack = banded_stack(n=n)
    timing = scan_timing(n)
    field = stics_flow_map(stack, tile=16, frame_lags=range(0, 5), timing=timing)

    assert field.vx.shape == (3, 3)
    scale = timing.pixel_size_nm * 1e-3 / (timing.frame_duration_ms * 1e-3)
    expected = np.asarray([-0.5, 0.0, 0.5]) * scale

    for row, want in enumerate(expected):
        got = field.vx[row]
        assert np.all(np.isfinite(got))
        if want == 0.0:
            assert np.all(np.abs(got) < 0.15 * scale)
        else:
            assert np.all(np.sign(got) == np.sign(want))
            # The bands bleed into each other by roughly one emitter width, so
            # the tiles at a boundary read a little slow; the sign and the
            # magnitude are the claim, not three digits.
            assert np.all(np.abs(got) > 0.6 * abs(want))
            assert np.all(np.abs(got) < 1.4 * abs(want))
        # No band moves across the lines.
        assert np.all(np.abs(field.vy[row]) < 0.25 * scale)

    # The whole field averages to nothing, and says so: the arrows point in
    # opposite directions, so their mean is small while their mean *speed* is
    # not.
    summary = field.summary(min_quality=0.5)
    assert summary["n_kept"] == 9.0
    assert abs(summary["mean_vx"]) < 0.3 * summary["mean_speed"]
    assert summary["coherence"] < 0.6


def test_the_quality_filter_removes_arrows_from_a_still_sample():
    """A sample that does not flow must not be drawn as one that does.

    Peak jitter fitted to a straight line always yields a slope, and a slope is
    a velocity. Without a quality threshold a diffusive sample produces a full
    field of confident little arrows.
    """
    rng = np.random.default_rng(1)
    n, n_frames = 48, 120
    still = banded_stack(velocities=(0.0, 0.0, 0.0), n=n, n_frames=n_frames)
    timing = scan_timing(n)
    field = stics_flow_map(still, tile=16, frame_lags=range(0, 5), timing=timing)

    scale = timing.pixel_size_nm * 1e-3 / (timing.frame_duration_ms * 1e-3)
    kept = field.quiver(min_quality=0.9)[0].size
    assert kept < field.vx.size
    assert np.all(np.abs(field.vx[np.isfinite(field.vx)]) < 0.2 * scale)

    # Pure noise has no peak to track at all, and no arrow survives.
    noise = rng.poisson(30.0, size=(n_frames, n, n)).astype(float)
    empty = stics_flow_map(noise, tile=16, frame_lags=range(0, 5), timing=timing)
    assert empty.quiver(min_quality=0.9)[0].size == 0


def test_a_peak_that_leaves_its_tile_is_refused_not_reported():
    """Too fast for the tile is a wrap-around, and wrap-around looks convincing.

    A correlation map is periodic. A peak driven past the tile edge reappears on
    the other side, where a straight-line fit through it returns a well-behaved
    velocity pointing the wrong way. Measured before the guard existed: R^2 of
    0.7 on a flow whose reported direction was inverted.
    """
    n = 48
    fast = banded_stack(velocities=(2.0, 2.0, 2.0), n=n, n_frames=120)
    timing = scan_timing(n)
    field = stics_flow_map(fast, tile=16, frame_lags=range(0, 5), timing=timing)

    assert field.meta["n_escaped"] > 0
    assert np.all(np.isnan(field.vx))
    assert field.quiver(min_quality=0.0)[0].size == 0

    # The same flow read with lags short enough to keep the peak inside the tile
    # is measured, and its direction is right.
    ok = stics_flow_map(fast, tile=16, frame_lags=(0, 1, 2), timing=timing)
    assert ok.meta["n_escaped"] == 0
    assert np.all(ok.vx[np.isfinite(ok.vx)] > 0.0)


def test_the_pair_correlation_flow_map_resolves_the_bands_too():
    """The second, independent route to the same arrows.

    STICS tracks a peak in space; this tracks one in time. They share no kernel
    -- one goes through the spatial correlator, the other through an FFT along
    time -- so agreeing on the sign of three bands is a real cross-check.
    """
    n = 48
    stack = banded_stack(n=n, n_frames=400)
    timing = scan_timing(n)
    field = pcf_flow_map(stack, distance=4, tile=16, timing=timing, n_segments=4)

    assert field.vx.shape == (3, n)
    assert np.all(field.vy == 0.0)
    # The interior of each band, away from the edges where the pair straddles
    # two bands or falls off the line.
    for row, want in enumerate((-1.0, 0.0, +1.0)):
        interior = field.vx[row, 8:-8]
        finite = interior[np.isfinite(interior)]
        assert finite.size > 0.5 * interior.size
        if want == 0.0:
            continue
        assert np.median(np.sign(finite)) == want
