"""Physics guardrails for the numerical FCS saturation path.

Every assertion here compares the numerical machinery in
:mod:`chisurf.core.fluorescence.fcs.saturation` against a result that is known
independently of it — the analytical 3D-Gaussian FCS curve, Parseval's theorem,
the closed-form Widengren triplet-bunching expression, or the half-decay time of
the numerically integrated curve itself. Construction tests would have passed
while the k-space quadrature carried a four-orders-of-magnitude scale error, so
these compare numbers, not shapes of arrays.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fcs.saturation import (
    DEFAULT_N_R,
    DEFAULT_N_Z,
    absorption_cross_section_m2,
    compute_bunching_factor,
    compute_power_sweep,
    effective_volume,
    emission_profile,
    excitation_rate,
    excitation_rate_peak,
    fcs_numerical_g_diff,
    fit_single_component,
    gaussian_g_diff,
    photon_flux,
    saturated_curve_shape,
    steady_state_full_populations,
)

W0 = 250e-9
Z0 = 1000e-9
D_R6G = 400e-12
V_0 = np.pi**1.5 * W0**2 * Z0

# Rhodamine 6G-like 3-state scheme (S0, S1, T1) with rates in Hz.
DARK_R6G = np.zeros((3, 3))
DARK_R6G[0, 1] = 2.5e8  # S1 -> S0, tau_F = 4 ns
DARK_R6G[2, 1] = 2.5e6  # S1 -> T1, phi_ISC = 1 %
DARK_R6G[0, 2] = 5.0e5  # T1 -> S0, tau_T = 2 us
EXC_R6G = np.zeros((3, 3))
EXC_R6G[1, 0] = 1.0
Q_R6G = np.array([0.0, 1.0, 0.0])


def _grid(n_r: int = DEFAULT_N_R, n_z: int = DEFAULT_N_Z):
    """Return the shipped five-waist (r, z) grid and its meshgrid."""
    r = np.linspace(0.0, 5.0 * W0, n_r)
    z = np.linspace(-5.0 * Z0, 5.0 * Z0, n_z)
    return r, z, np.meshgrid(r, z, indexing="ij")


def test_gaussian_profile_reproduces_analytical_fcs_curve():
    """The numerical autocorrelation of a Gaussian must be the analytical curve.

    The error is stated as a fraction of the amplitude G(0), not as a relative
    error per point: deep in the tail G is 1e-4 of the amplitude, where a large
    relative error is numerically irrelevant and physically unmeasurable.
    """
    r, z, (R, Z) = _grid()
    profile = np.exp(-2.0 * R**2 / W0**2) * np.exp(-2.0 * Z**2 / Z0**2)
    tau = np.logspace(-8, -1, 60)
    numerical = fcs_numerical_g_diff(tau, r, z, profile, D_R6G, v_ref=V_0)
    analytical = gaussian_g_diff(tau, W0, Z0, D_R6G)
    assert np.max(np.abs(numerical - analytical)) < 1e-3


def test_numerical_accuracy_improves_with_radial_sampling():
    """The radial grid is the accuracy knob -- a claim the defaults rely on."""
    tau = np.logspace(-8, -1, 60)
    analytical = gaussian_g_diff(tau, W0, Z0, D_R6G)

    def error(n_r, n_z):
        r = np.linspace(0.0, 5.0 * W0, n_r)
        z = np.linspace(-5.0 * Z0, 5.0 * Z0, n_z)
        R, Z = np.meshgrid(r, z, indexing="ij")
        profile = np.exp(-2.0 * R**2 / W0**2) * np.exp(-2.0 * Z**2 / Z0**2)
        g = fcs_numerical_g_diff(tau, r, z, profile, D_R6G, v_ref=V_0)
        return np.max(np.abs(g - analytical))

    assert error(240, 40) < error(60, 40) < error(30, 40)
    # Doubling the axial sampling changes nothing: the FFT is already converged.
    assert error(120, 80) == pytest.approx(error(120, 40), rel=1e-6)


def test_cross_correlation_of_identical_channels_is_the_autocorrelation():
    """G_ab with the same profile twice must reduce to G_aa."""
    r, z, (R, Z) = _grid()
    profile = np.exp(-2.0 * R**2 / W0**2) * np.exp(-2.0 * Z**2 / Z0**2)
    tau = np.logspace(-7, -3, 20)
    auto = fcs_numerical_g_diff(tau, r, z, profile, D_R6G, v_ref=V_0)
    cross = fcs_numerical_g_diff(tau, r, z, profile, D_R6G, v_ref=V_0, profile_b=profile.copy())
    np.testing.assert_allclose(cross, auto, rtol=1e-12)


def test_cross_correlation_of_narrower_channel_decays_faster():
    """A channel pair overlapping on a smaller volume correlates over shorter lags."""
    r, z, (R, Z) = _grid()
    wide = np.exp(-2.0 * R**2 / W0**2) * np.exp(-2.0 * Z**2 / Z0**2)
    narrow = np.exp(-2.0 * R**2 / (0.6 * W0) ** 2) * np.exp(-2.0 * Z**2 / Z0**2)
    tau = np.logspace(-7, -3, 40)
    cross = fcs_numerical_g_diff(tau, r, z, wide, D_R6G, profile_b=narrow)
    auto = fcs_numerical_g_diff(tau, r, z, wide, D_R6G)
    assert np.all(cross <= auto + 1e-12)
    assert cross[-1] < auto[-1]


def test_channel_resolved_brightness_returns_one_profile_per_channel():
    """A (n_channels, N) brightness matrix yields one emission profile each."""
    _, _, (R, Z) = _grid(20, 20)
    k_exc = excitation_rate(R, Z, W0, Z0, 1e-3, 1e5)
    q = np.array([[0.0, 1.0, 0.0], [0.0, 0.3, 0.0]])
    profiles = emission_profile(k_exc, DARK_R6G, EXC_R6G, q)
    assert profiles.shape == (2,) + R.shape
    np.testing.assert_allclose(profiles[1], 0.3 * profiles[0], rtol=1e-9)


def test_cross_bunching_matches_the_autocorrelation_when_channels_agree():
    """X_ab with equal brightness vectors is X_aa."""
    tau = np.logspace(-7, -4, 20)
    auto = compute_bunching_factor(1e7, DARK_R6G, EXC_R6G, Q_R6G, tau)
    cross = compute_bunching_factor(1e7, DARK_R6G, EXC_R6G, Q_R6G, tau, brightness_b=Q_R6G.copy())
    np.testing.assert_allclose(cross, auto, rtol=1e-12)


def test_gaussian_effective_volume_is_pi_three_halves_w0_squared_z0():
    """V_eff of a 3D Gaussian is pi^(3/2) w0^2 z0 -- the textbook result."""
    r, z, (R, Z) = _grid()
    profile = np.exp(-2.0 * R**2 / W0**2) * np.exp(-2.0 * Z**2 / Z0**2)
    assert effective_volume(r, z, profile) == pytest.approx(V_0, rel=1e-3)


def test_amplitude_is_the_volume_expansion_ratio():
    """G(0) must equal v_ref / V_eff, computed independently in real space."""
    r, z, (R, Z) = _grid()
    k_exc = excitation_rate(R, Z, W0, Z0, 2e-3, 1e5)
    profile = emission_profile(k_exc, DARK_R6G, EXC_R6G, Q_R6G)
    g = fcs_numerical_g_diff(np.array([0.0]), r, z, profile, D_R6G, v_ref=V_0)
    assert g[0] == pytest.approx(V_0 / effective_volume(r, z, profile), rel=1e-9)


def test_shape_normalisation_gives_unit_amplitude():
    """Without a reference volume the shape is normalised to G(0) = 1."""
    r, z, (R, Z) = _grid()
    k_exc = excitation_rate(R, Z, W0, Z0, 5e-3, 1e5)
    profile = emission_profile(k_exc, DARK_R6G, EXC_R6G, Q_R6G)
    g = fcs_numerical_g_diff(np.array([0.0, 1e-5]), r, z, profile, D_R6G)
    assert g[0] == pytest.approx(1.0, rel=1e-9)


def test_correlation_decays_to_zero_at_long_lag():
    """The DC component carries no correlation: G(tau -> inf) -> 0."""
    r, z, (R, Z) = _grid()
    profile = np.exp(-2.0 * R**2 / W0**2) * np.exp(-2.0 * Z**2 / Z0**2)
    g = fcs_numerical_g_diff(np.array([1e2]), r, z, profile, D_R6G, v_ref=V_0)
    assert g[0] == pytest.approx(0.0, abs=1e-9)


def test_zero_power_is_the_analytical_gaussian_not_a_fabricated_power():
    """P = 0 must return the analytical Gaussian exactly (PRD-74 contract)."""
    tau = np.logspace(-7, -2, 40)
    g = saturated_curve_shape(
        tau, 0.0, 1e5, DARK_R6G, EXC_R6G, Q_R6G, W0, Z0, D_R6G, include_bunching=True
    )
    np.testing.assert_allclose(g, gaussian_g_diff(tau, W0, Z0, D_R6G), rtol=1e-12)


def test_weak_power_converges_to_the_zero_power_limit():
    """The numerical path must approach the analytical curve as P -> 0."""
    tau = np.logspace(-7, -2, 40)
    g = saturated_curve_shape(
        tau, 1e-9, 1e5, DARK_R6G, EXC_R6G, Q_R6G, W0, Z0, D_R6G, include_bunching=False
    )
    assert np.max(np.abs(g - gaussian_g_diff(tau, W0, Z0, D_R6G))) < 1e-3


def test_saturation_expands_the_volume_monotonically():
    """V_eff/V_0 grows monotonically with power and the amplitude falls with it."""
    tau = np.array([0.0])
    powers = [1e-8, 1e-5, 1e-3, 1e-1]
    amplitudes = [
        saturated_curve_shape(
            tau, p, 1e5, DARK_R6G, EXC_R6G, Q_R6G, W0, Z0, D_R6G, include_bunching=False
        )[0]
        for p in powers
    ]
    assert all(a > b for a, b in zip(amplitudes, amplitudes[1:]))
    assert amplitudes[0] == pytest.approx(1.0, rel=1e-2)
    assert amplitudes[-1] < 0.5


def test_reported_diffusion_time_tracks_the_numerical_half_decay():
    """compute_power_sweep's tau_D must match the curve's own half-decay time."""
    powers, v_rel, tau_d_ms = compute_power_sweep(
        power_mW=5.0,
        extinction=1e5,
        dark_matrix=DARK_R6G,
        exc_matrix=EXC_R6G,
        brightness=Q_R6G,
        w_r_nm=W0 * 1e9,
        w_z_nm=Z0 * 1e9,
        D_um2s=D_R6G * 1e12,
        n_points=6,
    )
    assert np.all(np.diff(v_rel) > 0.0)
    tau = np.logspace(-8, -1, 400)
    for p_mW, reported_ms in zip(powers, tau_d_ms):
        g = saturated_curve_shape(
            tau,
            p_mW * 1e-3,
            1e5,
            DARK_R6G,
            EXC_R6G,
            Q_R6G,
            W0,
            Z0,
            D_R6G,
            include_bunching=False,
        )
        half = np.interp(0.5, (g / g[0])[::-1], tau[::-1])
        assert reported_ms * 1e-3 == pytest.approx(half, rel=0.15)


def test_bunching_factor_matches_the_analytical_triplet_expression():
    """X(tau) must reproduce 1 + T/(1-T) exp(-tau/tau_T) beyond the singlet lag."""
    k_exc = 1e7
    x = None
    k_f = DARK_R6G[0, 1]
    k_isc = DARK_R6G[2, 1]
    k_t = DARK_R6G[0, 2]
    p_eq = steady_state_full_populations(np.array([k_exc]), DARK_R6G, EXC_R6G)[:, 0]
    triplet = p_eq[2]
    # Singlet-manifold excited fraction, i.e. the fraction of the S0/S1 subsystem in S1.
    f_s1 = p_eq[1] / (p_eq[0] + p_eq[1])
    tau_t = 1.0 / (k_t + k_isc * f_s1)

    tau = np.logspace(-7, -4, 60)
    x = compute_bunching_factor(k_exc, DARK_R6G, EXC_R6G, Q_R6G, tau)
    expected = 1.0 + triplet / (1.0 - triplet) * np.exp(-tau / tau_t)
    assert np.max(np.abs(x / expected - 1.0)) < 0.02


def test_bunching_factor_limits():
    """X(0) = sum Q^2 p / (sum Q p)^2 and X(inf) = 1."""
    k_exc = 1e8
    p_eq = steady_state_full_populations(np.array([k_exc]), DARK_R6G, EXC_R6G)[:, 0]
    x = compute_bunching_factor(k_exc, DARK_R6G, EXC_R6G, Q_R6G, np.array([0.0, 1.0]))
    expected_0 = float(np.sum(Q_R6G**2 * p_eq) / np.sum(Q_R6G * p_eq) ** 2)
    assert x[0] == pytest.approx(expected_0, rel=1e-9)
    assert x[1] == pytest.approx(1.0, rel=1e-9)


def test_bunching_is_unity_without_excitation():
    """No excitation means no bright state, hence no photokinetic bunching."""
    x = compute_bunching_factor(0.0, DARK_R6G, EXC_R6G, Q_R6G, np.logspace(-7, -3, 10))
    np.testing.assert_allclose(x, 1.0)


def test_steady_state_populations_are_normalised_and_positive():
    """Populations sum to one everywhere and never go negative."""
    _, _, (R, Z) = _grid(20, 20)
    k_exc = excitation_rate(R, Z, W0, Z0, 5e-3, 1e5)
    p = steady_state_full_populations(k_exc, DARK_R6G, EXC_R6G)
    np.testing.assert_allclose(p.sum(axis=0), 1.0, rtol=1e-9)
    assert p.min() >= -1e-12


def test_steady_state_matches_closed_form_three_level_solution():
    """Compare against the hand-solved S0 <-> S1 -> T1 -> S0 steady state."""
    k_exc = np.array([1e7, 1e9])
    k_f, k_isc, k_t = DARK_R6G[0, 1], DARK_R6G[2, 1], DARK_R6G[0, 2]
    p = steady_state_full_populations(k_exc, DARK_R6G, EXC_R6G)
    # P_T1 = (k_ISC/k_T) P_S1 and P_S0 = ((k_F + k_ISC)/k_exc) P_S1.
    p_s1 = 1.0 / ((k_f + k_isc) / k_exc + 1.0 + k_isc / k_t)
    np.testing.assert_allclose(p[1], p_s1, rtol=1e-9)
    np.testing.assert_allclose(p[2], (k_isc / k_t) * p_s1, rtol=1e-9)
    np.testing.assert_allclose(p[0], ((k_f + k_isc) / k_exc) * p_s1, rtol=1e-9)


def test_ground_state_brightness_warns_about_an_unconfined_profile():
    """A state that emits without being excited makes V_eff grid-dependent."""
    _, _, (R, Z) = _grid(20, 20)
    k_exc = excitation_rate(R, Z, W0, Z0, 1e-3, 1e5)
    with pytest.warns(RuntimeWarning, match="does not vanish"):
        emission_profile(k_exc, DARK_R6G, EXC_R6G, np.array([1.0, 0.0, 0.0]))


def test_photophysics_units():
    """Cross section and photon flux against hand-computed reference values."""
    # eps = 1e5 M^-1 cm^-1 -> sigma = ln(10) * 1e5 * 1e3 / N_A cm^2 = 3.82e-16 cm^2.
    assert absorption_cross_section_m2(1e5) == pytest.approx(3.824e-20, rel=1e-3)
    # 1 mW at 488 nm -> 1e-3 / (hc/lambda) = 2.456e15 photons/s.
    assert photon_flux(1e-3, 488e-9) == pytest.approx(2.456e15, rel=1e-3)
    # Peak rate = sigma * 2 Phi / (pi w0^2).
    expected = 3.824e-20 * 2.0 * 2.456e15 / (np.pi * W0**2)
    assert excitation_rate_peak(1e-3, 1e5, W0, 488e-9) == pytest.approx(expected, rel=2e-3)


def test_wavelength_changes_the_excitation_rate():
    """The excitation rate scales with photon energy -- 488 nm is not a constant."""
    blue = excitation_rate_peak(1e-3, 1e5, W0, 488e-9)
    red = excitation_rate_peak(1e-3, 1e5, W0, 650e-9)
    assert red / blue == pytest.approx(650.0 / 488.0, rel=1e-9)


def test_brightness_changes_the_saturated_curve():
    """The state brightness must reach the curve (the historical invisible-Q bug)."""
    tau = np.logspace(-7, -3, 30)
    args = (2e-3, 1e5, DARK_R6G, EXC_R6G)
    g_dark_triplet = saturated_curve_shape(
        tau, *args, np.array([0.0, 1.0, 0.0]), W0, Z0, D_R6G
    )
    g_bright_triplet = saturated_curve_shape(
        tau, *args, np.array([0.0, 1.0, 0.5]), W0, Z0, D_R6G
    )
    assert not np.allclose(g_dark_triplet, g_bright_triplet)


def test_mismatched_brightness_length_is_an_error():
    """A brightness vector that does not match the scheme must not be broadcast."""
    with pytest.raises(ValueError, match="brightness"):
        emission_profile(np.array([1e7]), DARK_R6G, EXC_R6G, np.array([0.0, 1.0]))


def test_no_absorption_at_the_excitation_wavelength_is_the_unsaturated_limit():
    """eps = 0 is 'the dye does not absorb here', not 'the curve is zero'.

    Reading eps off a real spectrum makes this reachable: excite a dye far from
    its maximum and eps goes to zero, at which point the scheme cannot be
    populated and the analytical Gaussian is the exact limit.
    """
    tau = np.logspace(-7, -2, 30)
    g = saturated_curve_shape(
        tau, 5e-3, 0.0, DARK_R6G, EXC_R6G, Q_R6G, W0, Z0, D_R6G, include_bunching=True
    )
    np.testing.assert_allclose(g, gaussian_g_diff(tau, W0, Z0, D_R6G), rtol=1e-12)


def test_the_axial_half_spectrum_is_the_whole_one():
    """rfft + mirror weights must equal the full complex transform, exactly.

    The speed of this module rests on two identities -- a real profile needs
    only half its axial spectrum, and exp(-D(kr^2+kz^2)tau) factorises -- so
    they are checked against a direct evaluation rather than trusted.
    """
    r, z, (R, Z) = _grid(60, 32)
    profile = np.exp(-2.0 * R**2 / W0**2) * np.exp(-2.0 * Z**2 / Z0**2)
    tau = np.logspace(-7, -3, 25)
    fast = fcs_numerical_g_diff(tau, r, z, profile, D_R6G, v_ref=V_0)

    # Direct: full complex FFT, full (kr, kz) grid, no factorisation.
    from scipy.special import j0

    dr, dz = float(r[1] - r[0]), float(z[1] - z[0])
    kr = np.linspace(0.0, 30.0 / float(r[-1]), min(len(r), 64))
    kz = np.fft.fftfreq(len(z), d=dz) * 2.0 * np.pi
    weights = np.full(len(r), dr)
    weights[0] *= 0.5
    weights[-1] *= 0.5
    matrix = 2.0 * np.pi * (r * weights)[None, :] * j0(kr[:, None] * r[None, :])
    f_k = matrix @ (np.fft.fft(profile, axis=1) * dz)
    psd = (np.abs(f_k) ** 2) * kr[:, None]
    k2 = kr[:, None] ** 2 + kz[None, :] ** 2
    direct = np.array([np.sum(psd * np.exp(-D_R6G * k2 * t)) for t in tau])
    direct *= (V_0 * float(np.trapezoid(np.trapezoid(profile**2 * 2 * np.pi * r[:, None],
                                                     r, axis=0), z))
               / float(np.trapezoid(np.trapezoid(profile * 2 * np.pi * r[:, None],
                                                 r, axis=0), z)) ** 2) / psd.sum()
    np.testing.assert_allclose(fast, direct, rtol=1e-10)


def test_the_hankel_matrix_is_cached_and_never_handed_out_writable():
    """It is shared between calls, so a caller must not be able to corrupt it."""
    from chisurf.core.fluorescence.fcs.saturation import _hankel_matrix

    first = _hankel_matrix(64, 1e-6, 3e7, 32)
    again = _hankel_matrix(64, 1e-6, 3e7, 32)
    assert first is again, "the same grid must reuse the same matrix"
    assert not first.flags.writeable
    with pytest.raises(ValueError):
        first[0, 0] = 1.0


def test_saturation_adds_a_second_apparent_diffusion_time():
    """A saturated curve is not one Gaussian diffusion component any more.

    Widengren & Rigler's point: flattening the emission profile turns its
    autocorrelation into a *broader mixture* of decay rates than any single 3D
    Gaussian can produce. Fitting one component therefore returns an inflated
    apparent diffusion time and leaves a systematic residual -- which is how the
    distortion is recognised on real data.
    """
    tau = np.logspace(-7, -1, 300)
    true_tau_d = W0**2 / (4.0 * D_R6G)
    args = (1e5, DARK_R6G, EXC_R6G, Q_R6G, W0, Z0, D_R6G)

    unsaturated = saturated_curve_shape(tau, 0.0, *args, include_bunching=False)
    tau_d0, _, _, rms0 = fit_single_component(tau, unsaturated, W0, Z0, D_R6G)
    assert tau_d0 == pytest.approx(true_tau_d, rel=0.05)

    apparent, residuals = [], []
    for power_W in (2e-4, 2e-3, 3.08e-2):
        g = saturated_curve_shape(tau, power_W, *args, include_bunching=False)
        tau_d, _, fitted, rms = fit_single_component(tau, g, W0, Z0, D_R6G)
        apparent.append(tau_d)
        residuals.append(rms)

    # The apparent diffusion time grows with power, well past the true one ...
    assert all(a < b for a, b in zip(apparent, apparent[1:]))
    assert apparent[0] > true_tau_d
    assert apparent[-1] > 3.0 * true_tau_d
    # ... and one component describes the curve ever less well.
    assert residuals[-1] > 2.0 * rms0

    # The residual is not noise: it changes sign, the signature of a missing
    # faster component (fit too slow early, too fast late).
    g = saturated_curve_shape(tau, 3.08e-2, *args, include_bunching=False)
    _, _, fitted, _ = fit_single_component(tau, g, W0, Z0, D_R6G)
    residual = g / g[0] - fitted
    assert residual.min() < -1e-3 and residual.max() > 1e-3


def test_a_second_component_actually_fits_what_one_cannot():
    """Two components describe the saturated curve where one fails."""
    from scipy.optimize import curve_fit

    tau = np.logspace(-7, -1, 300)
    g = saturated_curve_shape(
        tau, 3.08e-2, 1e5, DARK_R6G, EXC_R6G, Q_R6G, W0, Z0, D_R6G,
        include_bunching=False,
    )
    y = g / g[0]
    _, _, _, rms_one = fit_single_component(tau, g, W0, Z0, D_R6G)

    def one(t, tau_d, s):
        return 1.0 / (1.0 + t / tau_d) / np.sqrt(1.0 + t / (s**2 * tau_d))

    def two(t, frac, tau_1, tau_2, s):
        return frac * one(t, tau_1, s) + (1.0 - frac) * one(t, tau_2, s)

    guess = [0.2, W0**2 / (4.0 * D_R6G), 4.0 * W0**2 / (4.0 * D_R6G), 5.0]
    params, _ = curve_fit(two, tau, y, p0=guess,
                          bounds=([0, 1e-9, 1e-9, 0.5], [1, 1e-1, 1e-1, 50]),
                          maxfev=200000)
    rms_two = float(np.sqrt(np.mean((two(tau, *params) - y) ** 2)))
    assert rms_two < 0.5 * rms_one, "a second component must earn its place"
    fast, slow = sorted(params[1:3])
    assert slow > 2.0 * fast, "the two components must be genuinely distinct"


def test_a_saturated_curve_is_fitted_by_a_triplet_times_two_diffusion_times():
    """The established analysis of saturated FCS data must be expressible.

    Widengren & Rigler fit optically saturated curves with a global triplet term
    times *two* diffusion times. Diffusion terms add while bunching terms
    multiply, so this needs a summed multi-component diffusion -- which is what
    ``DiffusionSpecies`` provides. Here the whole chain is exercised: simulate a
    saturated measurement including its triplet, then fit it the way the data
    would be fitted, and require that it beats one component decisively.
    """
    from scipy.optimize import curve_fit

    from chisurf.core.models.fcs.general import DiffusionSpecies

    tau_s = np.logspace(-7, -1, 300)
    tau_ms = tau_s * 1e3
    g = saturated_curve_shape(
        tau_s, 3.08e-2, 1e5, DARK_R6G, EXC_R6G, Q_R6G, W0, Z0, D_R6G, include_bunching=True
    )
    y = g / g[0]

    species = DiffusionSpecies()
    species._w_r.value = W0 * 1e9
    species._w_z.value = Z0 * 1e9

    def model(t_ms, x1, d1, d2, triplet, tau_t):
        species._x_1.value, species._x_2.value = x1, 1.0 - x1
        species._D_1.value, species._D_2.value = d1, d2
        bunch = 1.0 + triplet / (1.0 - triplet) * np.exp(-t_ms * 1e-3 / tau_t)
        out = species.g_diff(t_ms) * bunch
        return out / out[0]

    params, _ = curve_fit(
        model, tau_ms, y, p0=[0.1, 900.0, 100.0, 0.5, 2e-6],
        bounds=([0, 1, 1, 0.01, 1e-8], [1, 1e5, 1e5, 0.95, 1e-3]), maxfev=200000,
    )
    rms_two = float(np.sqrt(np.mean((model(tau_ms, *params) - y) ** 2)))

    # Against one diffusion component with the same triplet freedom.
    def model_one(t_ms, d, triplet, tau_t):
        return model(t_ms, 1.0, d, d, triplet, tau_t)

    params_one, _ = curve_fit(
        model_one, tau_ms, y, p0=[300.0, 0.5, 2e-6],
        bounds=([1, 0.01, 1e-8], [1e5, 0.95, 1e-3]), maxfev=200000,
    )
    rms_one = float(np.sqrt(np.mean((model_one(tau_ms, *params_one) - y) ** 2)))

    # Three times better, not the ten one might expect -- and the shortfall is
    # informative. Given a free triplet, one diffusion component partly hides the
    # distortion in it: a shortened tau_T mimics a fast diffusion component over
    # part of the range. The two are therefore somewhat degenerate, which is why
    # Widengren's triplet is a *global* parameter across a power series rather
    # than fitted per curve.
    assert rms_two < 0.4 * rms_one, "two diffusion times must clearly beat one"
    fast, slow = sorted(params[1:3], reverse=True)   # D, so fast D = short tau_D
    assert fast > 3.0 * slow, "the two transit times must be genuinely distinct"

    # The fitted triplet time is the *apparent* one, shortened by the excitation:
    # 1/(k_T + k_ISC * f_S1), not the scheme's 1/k_T.
    k_exc = excitation_rate_peak(3.08e-2, 1e5, W0)
    populations = steady_state_full_populations(np.array([k_exc]), DARK_R6G, EXC_R6G)[:, 0]
    f_s1 = populations[1] / (populations[0] + populations[1])
    expected_tau_t = 1.0 / (DARK_R6G[0, 2] + DARK_R6G[2, 1] * f_s1)
    assert params[4] == pytest.approx(expected_tau_t, rel=0.15)
