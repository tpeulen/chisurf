"""RICS, STICS, TICS and iMSD are readings of one correlation carpet.

These tests pin the claim the ICS subsystem is built on: there is a single
object :math:`G(\\xi, \\psi, \\Delta)`, and the four named methods are ways of
slicing it plus the lag time the scanner assigns to each slice. If any of these
identities breaks, the subsystem has quietly become four methods again.
"""
from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.experiments.ics.data import IcsSettings, IcsTiming, lag_time
from chisurf.core.experiments.ics.ics_core import compute_ics_carpet, frame_pairs
from chisurf.core.models.ics.models import image_correlation, mean_square_displacement


# --- the lag-time identity -------------------------------------------------
def test_lag_time_is_additive_over_the_three_axes():
    """tau = |xi*tp + psi*tl + Delta*tf| holds term by term and jointly."""
    kw = dict(pixel_duration_us=10.0, line_duration_ms=3.0, frame_duration_ms=600.0)
    assert lag_time(1, 0, 0, **kw) == pytest.approx(1e-5)
    assert lag_time(0, 1, 0, **kw) == pytest.approx(3e-3)
    assert lag_time(0, 0, 1, **kw) == pytest.approx(0.6)
    assert lag_time(2, 3, 4, **kw) == pytest.approx(2 * 1e-5 + 3 * 3e-3 + 4 * 0.6)


def test_lag_time_spans_six_decades_within_one_frame():
    """One RICS map alone covers µs to ms, which is why it sees diffusion."""
    fast = float(lag_time(1, 0, 0, pixel_duration_us=10.0, line_duration_ms=3.0))
    slow = float(lag_time(0, 100, 0, pixel_duration_us=10.0, line_duration_ms=3.0))
    assert slow / fast == pytest.approx(3e4)


def test_frame_pairs_shrink_with_lag():
    """A stack of n frames realises n - Delta pairs at lag Delta."""
    assert frame_pairs(5, 0) == [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]
    assert frame_pairs(5, 2) == [(0, 2), (1, 3), (2, 4)]
    assert frame_pairs(5, 5) == []


# --- the carpet is one object ---------------------------------------------
@pytest.fixture(scope="module")
def stack() -> np.ndarray:
    """Return a small synthetic image stack with spatial correlation."""
    rng = np.random.default_rng(20260725)
    base = rng.poisson(20.0, size=(12, 32, 32)).astype(float)
    # Smooth each frame so neighbouring pixels correlate.
    for k in range(base.shape[0]):
        base[k] = (
            base[k]
            + np.roll(base[k], 1, axis=0)
            + np.roll(base[k], 1, axis=1)
        ) / 3.0
    return base


def test_rics_map_is_the_zero_frame_lag_slice(stack):
    """Correlating only lag 0 gives exactly the lag-0 slice of a bigger carpet."""
    rics_only = compute_ics_carpet(stack, IcsSettings(frame_lags=(0,)))
    carpet = compute_ics_carpet(stack, IcsSettings(frame_lags=(0, 1, 2)))

    assert rics_only.shape[0] == 1
    assert carpet.shape[0] == 3
    np.testing.assert_allclose(carpet.rics_map(), rics_only.rics_map())


def test_stics_slices_are_addressable_by_lag(stack):
    """stics_map(d) selects the slice whose frame lag is d."""
    carpet = compute_ics_carpet(stack, IcsSettings(frame_lags=(0, 1, 3)))
    np.testing.assert_array_equal(carpet.frame_lags, [0, 1, 3])
    for k, d in enumerate(carpet.frame_lags):
        np.testing.assert_allclose(carpet.stics_map(int(d)), carpet.correlation[k])
    # An unavailable lag resolves to the nearest one rather than failing.
    np.testing.assert_allclose(carpet.stics_map(2), carpet.correlation[1])


def test_tics_curve_is_the_zero_spatial_lag_column(stack):
    """TICS is the carpet read down the Delta axis at xi = psi = 0."""
    timing = IcsTiming(pixel_duration_us=5.0, line_duration_ms=1.0,
                       frame_duration_ms=50.0, pixel_size_nm=50.0)
    carpet = compute_ics_carpet(
        stack, IcsSettings(frame_lags=(0, 1, 2, 3), timing=timing)
    )
    tau, g = carpet.tics_curve()

    iy, ix = carpet.zero_lag_index()
    assert carpet.pixel_shift[iy, ix] == 0.0
    assert carpet.line_shift[iy, ix] == 0.0
    np.testing.assert_allclose(g, carpet.correlation[:, iy, ix])
    np.testing.assert_allclose(tau, np.array([0.0, 0.05, 0.10, 0.15]))


def test_carpet_ravel_matches_the_flattened_correlation(stack):
    """The fit vector is the carpet in C order, so a fit sees every lag."""
    carpet = compute_ics_carpet(stack, IcsSettings(frame_lags=(0, 1)))
    flat = carpet.ravel()
    assert flat.size == np.prod(carpet.shape)
    np.testing.assert_allclose(flat.reshape(carpet.shape), carpet.correlation)


def test_more_lags_than_frames_is_rejected_not_silently_truncated():
    """A stack too short for any requested lag raises rather than guessing."""
    tiny = np.ones((2, 8, 8), dtype=float)
    with pytest.raises(ValueError):
        compute_ics_carpet(tiny, IcsSettings(frame_lags=(5, 6)))


def test_lag_grids_follow_the_map_order(stack):
    """Declining the fftshift moves the maps *and* their lag grids together.

    The grids are the coordinates of the carpet: every consumer pairs a map
    element with the lag at the same index. If the maps stay in FFT order while
    the grids describe a centred map, ``zero_lag_index`` points at a lag that is
    not zero and the TICS decay is read off the wrong carpet column.
    """
    settings = IcsSettings(frame_lags=(0, 1))
    shifted = compute_ics_carpet(stack, settings, use_fftshift=True)
    unshifted = compute_ics_carpet(stack, settings, use_fftshift=False)

    # Unshifted: the zero lag sits at [0, 0] and the grids say so.
    assert unshifted.zero_lag_index() == (0, 0)
    assert unshifted.pixel_shift[0, 0] == 0.0
    assert unshifted.line_shift[0, 0] == 0.0
    # Shifted: the zero lag sits at the centre and the grids say so.
    iy, ix = shifted.zero_lag_index()
    assert (iy, ix) == (shifted.shape[1] // 2, shifted.shape[2] // 2)

    # Same carpet either way: the value at the zero lag, and the whole map up to
    # the shift, agree.
    np.testing.assert_allclose(unshifted.correlation[:, 0, 0], shifted.correlation[:, iy, ix])
    np.testing.assert_allclose(
        np.fft.fftshift(unshifted.correlation, axes=(1, 2)), shifted.correlation
    )
    np.testing.assert_allclose(np.fft.fftshift(unshifted.pixel_shift), shifted.pixel_shift)
    np.testing.assert_allclose(np.fft.fftshift(unshifted.line_shift), shifted.line_shift)
    # ... and so do the two readings that consume the grids.
    np.testing.assert_allclose(unshifted.tics_curve()[1], shifted.tics_curve()[1])
    np.testing.assert_allclose(
        np.fft.fftshift(unshifted.lag_time_grid(), axes=(1, 2)),
        shifted.lag_time_grid(),
    )


def test_non_contiguous_roi_slice_is_handled(stack):
    """An ROI view of a larger stack correlates without corrupting memory."""
    view = stack[:, 4:20, 4:20]
    assert not view.flags["C_CONTIGUOUS"]
    carpet = compute_ics_carpet(view, IcsSettings(frame_lags=(0, 2)))
    assert np.isfinite(carpet.correlation).all()


# --- the model spans the same three axes ----------------------------------
def test_model_zero_frame_lag_reproduces_a_rics_surface():
    """Evaluating the model at Delta = 0 is a RICS model, term for term."""
    xi, psi = np.meshgrid(np.arange(-6, 7, dtype=float),
                          np.arange(-6, 7, dtype=float))
    kw = dict(n=2.0, diffusion_coefficient=1.5, w_r=0.25, w_z=1.0,
              pixel_duration=11.1, line_duration=3.33, pixel_size=50.0)

    rics = image_correlation(xi, psi, 0.0, **kw)
    carpet = image_correlation(xi[None], psi[None], np.zeros((1, 1, 1)), **kw)
    np.testing.assert_allclose(carpet[0], rics)


def test_model_amplitude_is_gamma_over_n_at_zero_lag():
    """G(0,0,0) = gamma/N, with gamma set by the detection geometry."""
    g3d = float(image_correlation(0.0, 0.0, 0.0, n=4.0, w_r=0.25))
    assert g3d == pytest.approx(2.0 ** -1.5 / 4.0)
    g2d = float(image_correlation(0.0, 0.0, 0.0, n=4.0, w_r=0.25, two_d=True))
    assert g2d == pytest.approx(0.5 / 4.0)


def test_model_slice_width_is_the_imsd():
    """The Gaussian width of slice Delta is w_r^2 + MSD(tau): that is iMSD.

    With the pixel and line times set to zero the lag time within a slice is a
    constant ``Delta * t_frame``, so each slice is a pure Gaussian and its width
    can be read exactly. Recovering ``4*D*tau`` from the width is precisely what
    an iMSD analysis does, one slice at a time.
    """
    d_coeff, w_r, frame_ms, pixel_nm = 3.0, 0.30, 20.0, 60.0
    xi = np.array([0.0, 4.0])
    psi = np.zeros_like(xi)

    for delta in (1.0, 2.0, 5.0):
        g = image_correlation(
            xi, psi, delta, n=1.0, diffusion_coefficient=d_coeff,
            pixel_duration=0.0, line_duration=0.0, frame_duration=frame_ms,
            pixel_size=pixel_nm, w_r=w_r, w_z=1e6,
        )
        # width W from the Gaussian ratio: g(d)/g(0) = exp(-d^2 / W)
        distance_um = xi[1] * pixel_nm * 1e-3
        width = -distance_um ** 2 / np.log(g[1] / g[0])

        tau = delta * frame_ms * 1e-3
        assert width - w_r ** 2 == pytest.approx(
            float(mean_square_displacement(tau, d_coeff)), rel=1e-9
        )
        assert width - w_r ** 2 == pytest.approx(4.0 * d_coeff * tau, rel=1e-9)


def test_anomalous_exponent_bends_the_msd():
    """alpha = 1 is normal diffusion; alpha != 1 is the anomalous/iMSD case."""
    tau = np.array([0.1, 0.4, 1.6])
    np.testing.assert_allclose(mean_square_displacement(tau, 2.0, 1.0), 8.0 * tau)
    sub = mean_square_displacement(tau, 2.0, 0.5)
    np.testing.assert_allclose(sub, 8.0 * np.sqrt(tau))
    # Subdiffusion falls below normal diffusion at long lags.
    assert sub[-1] < float(mean_square_displacement(tau, 2.0, 1.0)[-1])


def test_neutral_values_switch_optional_terms_off():
    """Blinking, immobile and flow terms vanish at their neutral values."""
    xi, psi = np.meshgrid(np.arange(-4, 5, dtype=float),
                          np.arange(-4, 5, dtype=float))
    base = image_correlation(xi, psi, 0.0, n=3.0, diffusion_coefficient=2.0)
    for extra in ({"a_triplet": 0.0}, {"n_immobile": 0.0},
                  {"v_x": 0.0, "v_y": 0.0}, {"alpha": 1.0}):
        np.testing.assert_allclose(
            image_correlation(xi, psi, 0.0, n=3.0, diffusion_coefficient=2.0, **extra),
            base,
        )


def test_flow_displaces_the_peak_along_the_scan_axis():
    """Flow shifts the correlation peak; that is what a STICS drift map reads."""
    xi = np.arange(-10, 11, dtype=float)
    psi = np.zeros_like(xi)
    kw = dict(n=1.0, diffusion_coefficient=0.01, w_r=0.3, w_z=1e6,
              pixel_duration=0.0, line_duration=0.0, frame_duration=100.0,
              pixel_size=100.0)

    still = image_correlation(xi, psi, 2.0, v_x=0.0, **kw)
    flowing = image_correlation(xi, psi, 2.0, v_x=2.0, **kw)
    assert int(np.argmax(still)) == 10          # centred on zero lag
    assert int(np.argmax(flowing)) > 10         # displaced downstream


# --- regions must not change the amplitude ---------------------------------
def _g_zero(carpet) -> float:
    """Return G at zero spatial lag of the first frame-lag slice."""
    m = carpet.correlation[0]
    ny, nx = m.shape
    return float(m[ny // 2, nx // 2])


def test_a_region_does_not_change_the_particle_number(stack):
    """The same sample must report the same G(0) however much of it is analysed.

    ``G(0)`` scales as ``1/N_particles``, so an amplitude that moves with the
    size of the region is a wrong concentration. Two things used to break this:
    the normalisation took ``<I>`` and ``N`` over the enclosing rectangle rather
    than the selected pixels, and the region was applied by *zeroing* pixels,
    which leaves them in the correlator's sum and in its frame-average
    subtraction. Before the fix a half-frame region reported 1.66x the
    full-frame amplitude.
    """
    from chisurf.core.roi import RectangleROI

    settings = IcsSettings(frame_lags=(0,))
    full = _g_zero(compute_ics_carpet(stack, settings))
    ny, nx = stack.shape[1], stack.shape[2]

    for name, roi in (
        ("upper half", RectangleROI(-0.5, -0.5, nx - 0.5, ny / 2 - 0.5)),
        ("left half", RectangleROI(-0.5, -0.5, nx / 2 - 0.5, ny - 0.5)),
        ("quadrant", RectangleROI(-0.5, -0.5, nx / 2 - 0.5, ny / 2 - 0.5)),
    ):
        got = _g_zero(compute_ics_carpet(stack, settings, mask=roi))
        assert got == pytest.approx(full, rel=0.10), (
            f"{name} region moved G(0) from {full:.4f} to {got:.4f}"
        )


def test_a_rectangular_region_is_cropped_not_zeroed(stack):
    """A region shrinks the correlated field, rather than blanking part of it.

    The distinction is not cosmetic: a zeroed pixel still contributes to the
    correlation sum and to the mean that is subtracted from every other pixel.
    """
    from chisurf.core.roi import RectangleROI

    settings = IcsSettings(frame_lags=(0,))
    ny, nx = stack.shape[1], stack.shape[2]
    carpet = compute_ics_carpet(
        stack, settings, mask=RectangleROI(-0.5, -0.5, nx / 2 - 0.5, ny / 2 - 0.5)
    )
    assert carpet.correlation.shape[1:] == (ny // 2, nx // 2)


def test_an_empty_region_is_rejected(stack):
    """A region that selects nothing is an error, not an empty correlation."""
    from chisurf.core.roi import ThresholdROI

    with pytest.raises(ValueError, match="no pixels"):
        compute_ics_carpet(
            stack, IcsSettings(frame_lags=(0,)),
            mask=ThresholdROI(low=float(stack.max()) + 1.0),
        )
