"""The public API must expose schemes, not a hard-wired triplet."""

import numpy as np
import pytest

from chisurf.plugins.calculator.fcs_saturation_calc.api import (
    calculate_fcs_curves,
    isomerisation_scheme,
    simulate_saturation,
    triplet_scheme,
    two_state_scheme,
)


@pytest.mark.parametrize("builder", [two_state_scheme, triplet_scheme, isomerisation_scheme])
def test_scheme_builders_are_valid_generators(builder):
    """Every shipped scheme must be square, non-negative and have one emitter."""
    dark, exc, q = builder()
    assert dark.shape == exc.shape == (q.size, q.size)
    assert np.all(dark >= 0) and np.all(exc >= 0)
    assert np.all(np.diag(dark) == 0) and np.all(np.diag(exc) == 0)
    assert q[0] == 0.0, "the state the molecule rests in cannot emit"
    assert q.max() > 0.0


def test_branching_yields_are_respected():
    """The scheme builders must split the decay rate, not add to it."""
    dark, _, _ = triplet_scheme(lifetime_ns=4.0, isc_yield=0.01)
    total = dark[0, 1] + dark[2, 1]
    assert total == pytest.approx(1e9 / 4.0)
    assert dark[2, 1] / total == pytest.approx(0.01)


def test_simulate_saturation_defaults_and_bunching():
    """The convenience entry point runs and the bunching term adds amplitude."""
    tau_ms, g_unpert, g_sat = simulate_saturation(power_mW=2.0)
    assert len(tau_ms) == 300
    dark, exc, q = triplet_scheme()
    _, g_unpert_nb, g_sat_nb = calculate_fcs_curves(
        power_mW=2.0,
        extinction=250000.0,
        dark_matrix=dark,
        exc_matrix=exc,
        brightness=q,
        w_r_nm=250.0,
        w_z_nm=1000.0,
        D_um2s=10.0,
        N=1.0,
        include_bunching=False,
    )
    # Without bunching the amplitude carries only the volume expansion.
    assert g_sat_nb[0] < g_unpert_nb[0]
    assert g_sat[0] > g_sat_nb[0]
