"""Client-level tests for the VV/VH G-factor RPC wrapper.

The GUI never calls :mod:`chisurf.plugins.vv_vh_g_factor.core.calculations`
directly — it goes through :class:`VvVhGFactorClient`.  These tests pin the
transport itself (RPC round-trip *and* the value the wrapper returns), which
the core-function tests cannot see.
"""

import numpy as np

from chisurf.plugins.vv_vh_g_factor.core.calculations import (
    perrin_steady_state_anisotropy,
    solve_linked_l_from_steady_state,
)
from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient


def test_client_solve_linked_l_returns_core_value():
    """The client returns the linked l1=l2 estimate, not ``None``."""
    sp, ss, g, r_target = 1000.0, 600.0, 1.5, 0.3
    client = VvVhGFactorClient()

    val = client.solve_linked_l(sp=sp, ss=ss, g_factor=g, r_target=r_target)

    assert isinstance(val, float)
    assert np.isfinite(val)
    assert np.allclose(
        val,
        solve_linked_l_from_steady_state(sp=sp, ss=ss, g_factor=g, r_target=r_target),
    )


def test_client_perrin_steady_state_returns_core_value():
    """Sibling estimator on the same transport, for symmetry."""
    client = VvVhGFactorClient()

    val = client.perrin_steady_state(tau_ns=4.0, rho_ns=16.0, r0=0.38)

    assert isinstance(val, float)
    assert np.allclose(val, perrin_steady_state_anisotropy(tau_ns=4.0, rho_ns=16.0, r0=0.38))
