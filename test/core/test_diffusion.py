"""Temperature, viscosity and observation-volume relations for diffusion.

These relations were living inside the FCS calculator plugin, where the imaging
side could not reach them — so image-correlation calibration would have grown a
second copy. The plugin now delegates here, so the tests below both fix the
behaviour of the shared version and pin it against values the plugin produced
*before* the move: a silent disagreement about "D of a dye at 23 °C" between two
tools is exactly the failure this centralisation exists to prevent, and a silent
*change* to existing FCS results would be just as bad.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.core.fluorescence.diffusion import (
    celsius_to_kelvin,
    combined_waist,
    diffusion_at_temperature,
    diffusion_from_volume,
    diffusion_time,
    effective_volume,
    lateral_waist,
    stokes_einstein_diffusion,
    stokes_einstein_radius,
    temperature_sensitivity,
    water_viscosity,
)


# --- viscosity and temperature ---------------------------------------------
def test_water_viscosity_matches_the_textbook_value_at_25c():
    """Water is ~0.89 mPa·s at 25 °C."""
    assert water_viscosity(celsius_to_kelvin(25.0)) == pytest.approx(0.89e-3, rel=0.01)


def test_viscosity_falls_monotonically_with_temperature():
    """Warmer water is thinner, across the whole usable range."""
    temps = [celsius_to_kelvin(t) for t in range(5, 60, 5)]
    etas = [water_viscosity(t) for t in temps]
    assert all(b < a for a, b in zip(etas, etas[1:]))


def test_viscosity_model_refuses_temperatures_where_it_diverges():
    """Below its pole the expression is meaningless, so it raises."""
    with pytest.raises(ValueError):
        water_viscosity(120.0)


def test_the_reference_temperature_is_a_fixed_point():
    """A 25 °C value corrected to 25 °C comes back unchanged."""
    assert diffusion_at_temperature(470.0, 25.0) == pytest.approx(470.0, rel=2e-3)


def test_diffusion_rises_with_temperature_at_about_2_to_3_percent_per_degree():
    """The sensitivity that makes the correction non-optional.

    Near room temperature D changes by a few percent per °C, so an assumed
    temperature two degrees off biases every calibrated quantity by ~5 %.
    """
    per_degree = temperature_sensitivity(25.0)
    assert 0.02 < per_degree < 0.035

    warm = diffusion_at_temperature(470.0, 27.0)
    cold = diffusion_at_temperature(470.0, 23.0)
    assert warm > cold
    assert (cold / diffusion_at_temperature(470.0, 25.0) - 1.0) == pytest.approx(-0.05, abs=0.01)


def test_viscosity_overrides_the_water_default():
    """A non-aqueous sample scales inversely with its own viscosity."""
    eta = water_viscosity(celsius_to_kelvin(25.0))
    doubled = diffusion_at_temperature(470.0, 25.0, viscosity=2 * eta)
    assert doubled == pytest.approx(diffusion_at_temperature(470.0, 25.0) / 2, rel=1e-9)


def test_unusable_conditions_give_nan_not_an_exception():
    """A zero viscosity is meaningless but must not crash a calibration."""
    assert math.isnan(diffusion_at_temperature(470.0, 25.0, viscosity=0.0))


# --- Stokes-Einstein -------------------------------------------------------
def test_stokes_einstein_round_trips():
    """Radius from D returns the radius D was computed from."""
    t = celsius_to_kelvin(25.0)
    eta = water_viscosity(t)
    d = stokes_einstein_diffusion(t, eta, 1e-9)
    assert stokes_einstein_radius(t, eta, d) == pytest.approx(1e-9, rel=1e-12)


def test_stokes_einstein_gives_a_sane_size_for_a_small_dye():
    """A dye diffusing at 470 µm²/s has a hydrodynamic radius of ~0.5 nm."""
    t = celsius_to_kelvin(25.0)
    r = stokes_einstein_radius(t, water_viscosity(t), 470e-12)  # µm²/s -> m²/s
    assert 0.3e-9 < r < 0.8e-9


# --- observation volume ----------------------------------------------------
def test_effective_volume_round_trips_through_the_diffusion_coefficient():
    """Volume from D and D from volume are inverses."""
    tau, d, s = 30e-6, 470e-12, 5.0
    v = effective_volume(tau, d, s)
    assert diffusion_from_volume(tau, v, s) == pytest.approx(d, rel=1e-12)


def test_effective_volume_is_femtolitre_scale_for_a_confocal_focus():
    """A confocal volume is a fraction of a femtolitre; a wrong power shows here.

    1 fL = 1e-18 m³, so the plausible 0.1–10 fL window is 1e-19 to 1e-17 m³.
    A free dye with a 30 µs diffusion time gives ~0.37 fL.
    """
    v = effective_volume(30e-6, 470e-12, 5.0)
    assert 1e-19 < v < 1e-17
    assert v * 1e18 == pytest.approx(0.37, abs=0.05)  # in fL


def test_waist_and_diffusion_time_are_inverses():
    """W = sqrt(4 D tau) and tau = w^2 / 4D agree."""
    assert diffusion_time(lateral_waist(30e-6, 470.0), 470.0) == pytest.approx(30e-6, rel=1e-12)


def test_waist_of_a_typical_confocal_focus():
    """A 30 µs diffusion time for a free dye implies a ~0.24 µm waist."""
    assert lateral_waist(30e-6, 470.0) == pytest.approx(0.237, abs=0.005)


def test_waist_units_follow_the_diffusion_coefficient():
    """µm²/s in gives µm out, so a calibration cannot silently change units."""
    in_um = lateral_waist(30e-6, 470.0)  # µm²/s -> µm
    in_m = lateral_waist(30e-6, 470e-12)  # m²/s  -> m
    assert in_m == pytest.approx(in_um * 1e-6, rel=1e-9)


def test_degenerate_inputs_give_nan():
    """Zero or negative D leaves the waist undefined rather than imaginary."""
    assert math.isnan(lateral_waist(30e-6, 0.0))
    assert math.isnan(diffusion_time(0.2, 0.0))
    assert math.isnan(diffusion_from_volume(0.0, 1e-15, 5.0))


def test_combined_waist_lies_between_the_two_channels():
    """A cross-correlation samples the overlap, so its waist is intermediate."""
    a, b = 0.20, 0.28
    w = combined_waist(a, b)
    assert a < w < b
    assert w == pytest.approx(math.sqrt(0.5 * (a * a + b * b)), rel=1e-12)
    # identical channels give back the same waist
    assert combined_waist(0.22, 0.22) == pytest.approx(0.22, rel=1e-12)


# --- agreement with the implementation it replaced -------------------------
#: Values produced by the FCS calculator *before* it was re-pointed at this
#: module (commit b4bb8bc8's parent). Frozen here rather than computed from the
#: plugin, which now delegates and would make the comparison vacuous.
_FROZEN = {
    # temperature (°C): (water viscosity Pa·s, D of a 470 µm²/s dye at that T)
    5.0: (0.0015012041732283725, 259.9515145686295),
    20.0: (0.0010017487594089526, 410.56709156248945),
    25.0: (0.0008904389816146542, 469.768292535314),
    37.0: (0.0006903976417629262, 630.2684055878373),
    50.0: (0.0005441600052149268, 833.1641842854701),
}


@pytest.mark.parametrize("t_c", sorted(_FROZEN))
def test_matches_the_values_the_fcs_calculator_produced_before_centralisation(t_c):
    """Centralising must not move a single existing FCS number.

    These are the plugin's own outputs from before it delegated here. Comparing
    against the live plugin would prove nothing now that it forwards to this
    module, so the reference is frozen instead.
    """
    eta_expected, d_expected = _FROZEN[t_c]
    t_k = celsius_to_kelvin(t_c)
    assert water_viscosity(t_k) == pytest.approx(eta_expected, rel=1e-12)
    assert diffusion_at_temperature(470.0, t_c) == pytest.approx(d_expected, rel=1e-12)


def test_the_plugin_now_forwards_here():
    """The FCS calculator keeps its API but no longer owns the physics."""
    plugin = pytest.importorskip(
        "chisurf.plugins.fcs.fcs_calculator.core.algorithms",
        reason="FCS calculator plugin not importable",
    )
    t_k = celsius_to_kelvin(25.0)
    assert plugin.water_viscosity_Pa_s(t_k) == water_viscosity(t_k)
    assert plugin.veff_from_tau_D_S(30e-6, 470e-12, 5.0) == effective_volume(30e-6, 470e-12, 5.0)
    assert plugin.scale_D_from_25C(470.0, t_k, water_viscosity(t_k)) == pytest.approx(
        diffusion_at_temperature(470.0, 25.0), rel=1e-12
    )


# --- the dye join ----------------------------------------------------------
def test_reference_diffusion_joins_the_dye_store_to_the_correction():
    """A named dye plus a temperature is the one call a calibration needs."""
    from chisurf.core.fluorescence import dyes
    from chisurf.core.fluorescence.diffusion import reference_diffusion

    names = dyes.dye_names()
    if not names:
        pytest.skip("no reference dyes available")

    name = names[0]
    d25 = dyes.diffusion_coefficient_25C(name)
    if not np.isfinite(d25):
        pytest.skip(f"{name} carries no diffusion coefficient")

    assert reference_diffusion(name, 25.0) == pytest.approx(
        diffusion_at_temperature(d25, 25.0), rel=1e-12
    )
    # colder is slower, and the join respects it
    assert reference_diffusion(name, 20.0) < reference_diffusion(name, 30.0)


def test_an_unknown_dye_gives_nan_rather_than_a_wrong_number():
    """A typo in the species name must not silently calibrate against garbage."""
    from chisurf.core.fluorescence.diffusion import reference_diffusion

    assert math.isnan(reference_diffusion("not-a-real-dye-xyz", 25.0))
