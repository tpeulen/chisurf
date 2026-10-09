"""The tail ratio G=VV/VH corrects VH consistently in anisotropy and mixing."""

import numpy as np
import pytest

from chisurf.plugins.vv_vh_g_factor.core.calculations import (
    calculate_g_factor_core,
    compute_rt,
    solve_linked_l_from_steady_state,
)


@pytest.mark.parametrize("g", [0.5, 1.0, 2.0, 3.0])
def test_isotropic_reference_has_zero_anisotropy(g):
    """A calibrated fast reference must not acquire residual polarization."""
    vh = 500 * np.exp(-np.arange(120) / 24) + 7
    vv = g * vh
    result = calculate_g_factor_core(vv, vh, [60, 100])
    assert result["g_factor"] == pytest.approx(g)
    np.testing.assert_allclose(compute_rt(vv, vh, result["g_factor"]), 0, atol=1e-15)


@pytest.mark.parametrize("g", [0.5, 2.0])
@pytest.mark.parametrize("mixing", [0.0, 0.1, 0.25])
def test_known_anisotropy_and_linked_mixing_are_recovered(g, mixing):
    """Independent polarized intensities recover their declared physical r and l."""
    target = 0.23
    vh = np.arange(1, 65, dtype=float)
    ratio = (1 + target * (2 - 3 * mixing)) / (1 - target * (1 - 3 * mixing))
    vv = g * vh * ratio
    np.testing.assert_allclose(compute_rt(vv, vh, g, mixing, mixing), target, atol=1e-14)
    found = solve_linked_l_from_steady_state(vv.sum(), vh.sum(), g, target)
    assert found == pytest.approx(mixing, abs=1e-14)


def test_swapping_channels_uses_reciprocal_calibration():
    """Flip preserves the corrected isotropic result under the reciprocal tail ratio."""
    vh = np.linspace(20, 200, 20)
    vv = 2 * vh
    forward = calculate_g_factor_core(vv, vh, [2, 18])["g_factor"]
    reverse = calculate_g_factor_core(vv, vh, [2, 18], flip=True)["g_factor"]
    assert forward * reverse == pytest.approx(1)
    np.testing.assert_allclose(compute_rt(vv, vh, forward), 0, atol=1e-15)
    np.testing.assert_allclose(compute_rt(vh, vv, reverse), 0, atol=1e-15)


def test_production_client_linked_mixing_uses_same_calibration():
    """The real in-process service returns the physically consistent solution."""
    from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient

    client = VvVhGFactorClient()
    r, g, mixing = 0.3, 2.0, 0.1
    vh = 1000.0
    vv = g * vh * (1 + r * (2 - 3 * mixing)) / (1 - r * (1 - 3 * mixing))
    assert client.solve_linked_l(vv, vh, g, r) == pytest.approx(mixing, abs=1e-14)
