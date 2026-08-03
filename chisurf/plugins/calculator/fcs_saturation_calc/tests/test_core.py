"""Contract tests for the calculator's unit conversions and curve assembly.

The physics itself is guarded in ``test/test_fcs_saturation_physics.py``; what
is tested here is that this layer converts mW/nm/um^2 s^-1 correctly and does
not quietly substitute a different scheme or power than it was given.
"""

import numpy as np
import pytest

from chisurf.core.fluorescence.fcs.saturation import gaussian_g_diff
from chisurf.plugins.calculator.fcs_saturation_calc.api import (
    isomerisation_scheme,
    triplet_scheme,
    two_state_scheme,
)
from chisurf.plugins.calculator.fcs_saturation_calc.core import (
    calculate_fcs_curves,
    compute_power_sweep_curves,
    compute_volume_profile,
    volume_expansion,
)

W_R, W_Z, D = 250.0, 1000.0, 10.0


def _curves(**kwargs):
    """Run the calculator on the triplet scheme with the given overrides."""
    dark, exc, q = kwargs.pop("scheme", triplet_scheme())
    params = dict(
        power_mW=1.0,
        extinction=100000.0,
        dark_matrix=dark,
        exc_matrix=exc,
        brightness=q,
        w_r_nm=W_R,
        w_z_nm=W_Z,
        D_um2s=D,
        N=1.0,
    )
    params.update(kwargs)
    return calculate_fcs_curves(**params)


def test_unperturbed_curve_is_the_analytical_gaussian():
    """The reference curve must be the analytical Gaussian in the right units."""
    tau_ms, g_unpert, _ = _curves()
    expected = gaussian_g_diff(tau_ms * 1e-3, W_R * 1e-9, W_Z * 1e-9, D * 1e-12)
    np.testing.assert_allclose(g_unpert, expected, rtol=1e-12)


def test_saturation_lowers_the_amplitude():
    """Volume expansion under power shows up as a smaller G(0)."""
    _, g_unpert, g_sat = _curves(power_mW=5.0, include_bunching=False)
    assert g_sat[0] < g_unpert[0]


def test_zero_power_reproduces_the_unperturbed_curve_exactly():
    """No excitation is not 'a little excitation': the two curves must coincide."""
    _, g_unpert, g_sat = _curves(power_mW=0.0)
    np.testing.assert_allclose(g_sat, g_unpert, rtol=1e-12)


def test_n_and_baseline_scale_the_curve():
    """1/N scales the amplitude and b offsets it, in both curves."""
    _, g1, s1 = _curves(N=1.0, b=0.0)
    _, g2, s2 = _curves(N=4.0, b=0.5)
    np.testing.assert_allclose(g2, 0.5 + g1 / 4.0, rtol=1e-9)
    np.testing.assert_allclose(s2, 0.5 + s1 / 4.0, rtol=1e-9)


def test_wavelength_changes_the_result():
    """A red dye excited in the blue is not the same measurement."""
    _, _, blue = _curves(power_mW=2.0, wavelength_nm=488.0)
    _, _, red = _curves(power_mW=2.0, wavelength_nm=650.0)
    assert not np.allclose(blue, red)


def test_volume_expansion_is_one_without_power_and_grows_with_it():
    """V_eff/V_0 is a ratio against the unsaturated Gaussian volume."""
    dark, exc, q = triplet_scheme()
    shared = dict(
        extinction=100000.0,
        dark_matrix=dark,
        exc_matrix=exc,
        brightness=q,
        w_r_nm=W_R,
        w_z_nm=W_Z,
    )
    assert volume_expansion(power_mW=0.0, **shared) == 1.0
    low = volume_expansion(power_mW=0.01, **shared)
    high = volume_expansion(power_mW=10.0, **shared)
    assert 1.0 <= low < high


def test_power_sweep_is_monotonic():
    """Both reported curves must rise with power."""
    dark, exc, q = triplet_scheme()
    powers, v_rel, tau_d = compute_power_sweep_curves(
        power_mW=2.0,
        extinction=100000.0,
        dark_matrix=dark,
        exc_matrix=exc,
        brightness=q,
        w_r_nm=W_R,
        w_z_nm=W_Z,
        D_um2s=D,
    )
    assert np.all(np.diff(powers) > 0)
    assert np.all(np.diff(v_rel) > 0)
    assert np.all(np.diff(tau_d) > 0)


@pytest.mark.parametrize(
    "scheme,n_states",
    [(two_state_scheme(), 2), (triplet_scheme(), 3), (isomerisation_scheme(), 4)],
)
def test_any_scheme_size_works(scheme, n_states):
    """Nothing in the calculator is tied to a three-state triplet scheme."""
    dark, exc, q = scheme
    assert dark.shape == (n_states, n_states)
    _, _, g_sat = calculate_fcs_curves(
        power_mW=2.0,
        extinction=100000.0,
        dark_matrix=dark,
        exc_matrix=exc,
        brightness=q,
        w_r_nm=W_R,
        w_z_nm=W_Z,
        D_um2s=D,
    )
    assert np.all(np.isfinite(g_sat))
    assert g_sat[0] > 0

    profile = compute_volume_profile(
        power_mW=2.0,
        extinction=100000.0,
        dark_matrix=dark,
        exc_matrix=exc,
        brightness=q,
        w_r_nm=W_R,
        w_z_nm=W_Z,
    )
    assert profile["P_states"].shape[0] == n_states
    assert len(profile["labels"]) == n_states
    np.testing.assert_allclose(profile["P_states"].sum(axis=0), 1.0, rtol=1e-9)


def test_isomer_scheme_relaxes_on_its_own_timescale():
    """The millisecond isomer must show up as bunching in the millisecond range."""
    dark, exc, q = isomerisation_scheme(isomer_lifetime_ms=1.0)
    shared = dict(
        power_mW=2.0,
        extinction=250000.0,
        dark_matrix=dark,
        exc_matrix=exc,
        brightness=q,
        w_r_nm=W_R,
        w_z_nm=W_Z,
        D_um2s=D,
        wavelength_nm=650.0,
    )
    tau_ms, _, g_sat = calculate_fcs_curves(**shared)
    _, _, g_no_bunching = calculate_fcs_curves(include_bunching=False, **shared)
    ratio = g_sat / g_no_bunching
    # X(tau) decays from its short-lag value to 1: at 10 us the millisecond
    # isomer has not relaxed yet, at 100 ms it has.
    early = ratio[np.argmin(np.abs(tau_ms - 1e-2))]
    late = ratio[np.argmin(np.abs(tau_ms - 100.0))]
    assert early > late
    assert late == pytest.approx(1.0, abs=0.05)


def test_ground_state_is_depleted_in_the_focal_centre():
    """Under strong saturation S0 empties at r = 0 and is full outside the beam.

    This is the profile panel's most counter-intuitive feature and the one that
    reads as swapped labels, so it is pinned against the hand-solved three-level
    steady state rather than against the implementation.
    """
    dark, exc, q = triplet_scheme(lifetime_ns=4.0, isc_yield=0.01,
                                  triplet_lifetime_us=2.0)
    profile = compute_volume_profile(
        power_mW=30.8, extinction=8e4, dark_matrix=dark, exc_matrix=exc,
        brightness=q, w_r_nm=200.0, w_z_nm=1000.0,
        state_labels=["S0", "S1", "T1"], wavelength_nm=488.0,
    )
    p_s0, p_s1, p_t1 = profile["P_states"][:, 0]
    k_exc = 3.684e10  # the peak rate the tool reports for these settings
    k_f, k_isc, k_t = dark[0, 1], dark[2, 1], dark[0, 2]
    expected_s1 = 1.0 / ((k_f + k_isc) / k_exc + 1.0 + k_isc / k_t)
    assert p_s1 == pytest.approx(expected_s1, rel=1e-3)
    assert p_t1 == pytest.approx((k_isc / k_t) * expected_s1, rel=1e-3)
    assert p_s0 < 0.01, "the ground state must be depleted where the light is"
    # ... and completely repopulated outside the beam.
    assert profile["P_states"][0, -1] == pytest.approx(1.0, abs=1e-6)


def test_emission_shares_the_scale_of_the_populations():
    """With a single bright state the emission curve *is* that state's curve.

    Normalising it to its own peak instead put it at 1.0 in the focal centre
    while the bright state sat at 0.17 there — unreadable on a shared axis.
    """
    dark, exc, q = triplet_scheme()
    profile = compute_volume_profile(
        power_mW=30.8, extinction=8e4, dark_matrix=dark, exc_matrix=exc,
        brightness=q, w_r_nm=200.0, w_z_nm=1000.0,
    )
    np.testing.assert_allclose(profile["emission"], profile["P_states"][1], rtol=1e-12)
    assert profile["emission"].max() < 1.0
    # The excitation curve is the one normalised quantity, and says so.
    assert profile["k_exc_norm"][0] == pytest.approx(1.0)
