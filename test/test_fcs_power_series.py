"""A global fit of an FCS power series must recover the scheme that made it.

One saturated curve does not determine a photochemical scheme: its distortion is
a product of the rates, the excitation rate and the optics, and several
combinations reproduce one curve about equally well. A power series breaks the
degeneracy because the scheme and the instrument are shared while the power is
known. These tests hold that claim to account -- simulate a series from a scheme
that is known exactly, then require the fit to find it again.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fcs.power_series import (
    LOCAL_PARAMETERS,
    build_power_series_fit,
    scheme_parameter_names,
    series_relaxation_times,
    simulate_power_series,
)
from chisurf.plugins.calculator.fcs_saturation_calc.api import triplet_scheme

POWERS = [0.05, 0.5, 5.0, 20.0]
TRUTH = dict(k2_3=2.5, k3_1=0.5, D=400.0)


def _series(noise: float = 2e-3, seed: int = 1):
    """Simulate the reference power series."""
    dark, exc, brightness = triplet_scheme(
        lifetime_ns=4.0, isc_yield=0.01, triplet_lifetime_us=2.0
    )
    curves = simulate_power_series(
        POWERS, dark, exc, brightness, w_r_nm=200.0, w_z_nm=1000.0,
        D_um2s=TRUTH["D"], extinction=1e5, noise=noise, seed=seed,
    )
    return curves


def _chi2r(group) -> float:
    """Reduced chi-square over the whole group."""
    group.update()
    total = sum(
        float(np.sum(np.asarray(f.model.weighted_residuals) ** 2))
        for f in group.grouped_fits
    )
    n = sum(np.asarray(f.model.weighted_residuals).size for f in group.grouped_fits)
    return total / max(n, 1)


def test_the_series_recovers_the_scheme_it_was_made_from():
    """The point of the whole exercise, checked end to end."""
    group = build_power_series_fit(
        _series(), POWERS,
        initial={"extinction": 1e5, "w_r": 200.0, "w_z": 1000.0,
                 "D": 250.0, "k2_3": 6.0, "k3_1": 1.5},
        free=("k2_3", "k3_1", "D"),
    )
    parameters = group.grouped_fits[0].model.parameters_all_dict
    assert _chi2r(group) > 50.0, "the starting point must be genuinely wrong"

    group.run()

    assert _chi2r(group) < 1.5, "a correct model on noisy data should reach chi2r ~ 1"
    for name, truth in TRUTH.items():
        assert parameters[name].value == pytest.approx(truth, rel=0.05), name


def test_the_power_is_measured_not_fitted():
    """Fitting it would give the optimiser a second route to the same distortion."""
    group = build_power_series_fit(_series(noise=0.0), POWERS)
    for fit, power_mW in zip(group.grouped_fits, POWERS):
        power = fit.model.parameters_all_dict["power"]
        assert power.value == pytest.approx(power_mW)
        assert power.fixed


def test_what_is_shared_and_what_is_not():
    """Sample and instrument are linked; concentration and power are per curve."""
    group = build_power_series_fit(_series(noise=0.0), POWERS)
    reference, *rest = group.grouped_fits
    shared = ["D", "w_r", "w_z", "extinction", "wavelength"]
    shared += scheme_parameter_names(reference.model)
    for fit in rest:
        for name in shared:
            assert fit.model.parameters_all_dict[name].is_linked, f"{name} must be shared"
        for name in LOCAL_PARAMETERS:
            assert not fit.model.parameters_all_dict[name].is_linked, f"{name} is per curve"

    # Changing the reference must move every follower: that is what "global" means.
    reference.model.parameters_all_dict["D"].value = 123.0
    assert all(
        f.model.parameters_all_dict["D"].value == pytest.approx(123.0) for f in rest
    )


def test_the_brightness_scale_is_not_offered_to_the_optimiser():
    """It cancels out of a normalised correlation curve, so it is unidentifiable."""
    group = build_power_series_fit(_series(noise=0.0), POWERS)
    for fit in group.grouped_fits:
        for parameter in fit.model.saturation.brightness._brightness:
            assert parameter.fixed


def test_the_scheme_predicts_a_different_relaxation_time_at_every_power():
    """It is an eigenvalue of a generator containing k_exc, not a fitted constant."""
    group = build_power_series_fit(_series(noise=0.0), POWERS)
    times = [t for _, t in series_relaxation_times(group)]
    assert all(a > b for a, b in zip(times, times[1:])), "more light, faster relaxation"


def test_a_series_needs_more_than_one_curve():
    """And the powers must match the curves."""
    curves = _series(noise=0.0)
    with pytest.raises(ValueError, match="at least two"):
        build_power_series_fit(curves[:1], POWERS[:1])
    with pytest.raises(ValueError, match="curves but"):
        build_power_series_fit(curves, POWERS[:2])
    with pytest.raises(ValueError, match="no parameter named"):
        build_power_series_fit(curves, POWERS, initial={"not_a_parameter": 1.0})
