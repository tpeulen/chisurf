"""Independent forward/inverse checks before exposing polarization estimates.

Ströhl et al., Methods Appl Fluoresc 6 (2018), DOI 10.1088/2050-6120/aa872e,
Eq. 3 uses the G multiplying the perpendicular signal. Objective mixing is
independently constructed from the explicit equation, not measured here.
"""
import numpy as np
import pytest

from chisurf.core.fluorescence.anisotropy.rt import rt_curves
from chisurf.plugins.core.acq.live.calibration.measurements import g_factor


def test_reference_g_recovers_known_sensitivity_and_matches_decay_convention():
    true_g = 1.7
    reference_r = 0.12
    # Forward intensities for known r, with the perpendicular detector response
    # lower by G; the common intensity scale cancels.
    parallel = 1200 * (1 + 2 * reference_r)
    perpendicular = 1200 * (1 - reference_r) / true_g
    measured_g, _ = g_factor(i_par=parallel, i_perp=perpendicular,
                              r_assumed=reference_r)
    assert measured_g == pytest.approx(true_g)
    _, _, corrected = rt_curves([0], [parallel], [perpendicular], g=measured_g)
    assert corrected[0] == pytest.approx(reference_r)


def test_known_time_dependent_anisotropy_with_configured_mixing_is_recovered():
    time = np.arange(4, dtype=float)
    expected = np.array([.35, .24, .12, .03])
    g, l1, l2 = 1.6, .05, .03
    perpendicular = np.array([100., 80., 50., 30.])
    # Solve r=(P-GS)/((1-3l2)P+(2-3l1)GS) for P.
    parallel = (g * perpendicular * (1 + expected * (2 - 3*l1)) /
                (1 - expected * (1 - 3*l2)))
    returned_time, _, recovered = rt_curves(time, parallel, perpendicular, g, l1, l2)
    np.testing.assert_array_equal(returned_time, time)
    np.testing.assert_allclose(recovered, expected, atol=1e-12)
