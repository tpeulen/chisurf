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
