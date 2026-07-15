"""Physics tests for the two-focus FCS (2fFCS) model in the FCS catalogue.

Complements the numerical A/B check in ``test_fcs_pam_ab.py`` (which verifies the
equation against PAM's exact fit lambda). Here we assert the physical hallmarks
of the Dertinger two-focus model on the ported ``Two-focus 3D diffusion`` entry:
with two foci a known distance ``diam`` apart the cross-correlation peaks at a
finite lag, and with ``diam = 0`` it reduces to the single-focus 3D-diffusion
model. The known ``diam`` is what makes the fitted ``D`` absolute.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
import yaml

MODELS_YAML = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf"
    / "core"
    / "models"
    / "fcs"
    / "models.yaml"
)
TWO_FOCUS = "Two-focus 3D diffusion (D, triplet)"
SINGLE_FOCUS = "3D diffusion (D, triplet)"


@pytest.fixture(scope="module")
def models():
    with open(MODELS_YAML) as handle:
        return yaml.safe_load(handle)


def _eval(equation, values, x):
    """Evaluate a models.yaml equation through the real ParseModel scanner."""
    from numpy import abs, exp, sin, sqrt  # noqa: F401 — referenced in eval scope

    from chisurf.core.models.parse.parse import ParseModel

    m = ParseModel.__new__(ParseModel)
    m._func = equation
    m._keys = []
    m._count = 0
    m._parameters_equation = []
    m.find_parameters = lambda: None
    m.parse_code()
    a = [values[k] for k in m._keys]  # noqa: F841 — referenced by eval(code)
    return eval(m.code)


def test_two_focus_present(models):
    """The two-focus model exists with the expected parameters."""
    assert TWO_FOCUS in models
    assert set(models[TWO_FOCUS]["initial"]) == {
        "N", "D", "w_r", "w_z", "tau_T", "Trip", "diam", "y_0"
    }


def test_cross_correlation_peaks_at_finite_lag(models):
    """With diam > 0 (two foci) the correlation peaks at a non-zero lag."""
    x = np.logspace(-7, -1, 500)  # seconds
    # No triplet, so the two-focus diffusion term governs the shape.
    p = dict(N=1, D=50, w_r=0.25, w_z=1.0, tau_T=1, Trip=0.0, diam=0.4, y_0=0.0)
    g = _eval(models[TWO_FOCUS]["equation"], p, x)
    peak = int(np.argmax(g))
    assert peak > 0
    assert g[peak] > g[0]  # genuinely rises to a maximum


def test_reduces_to_single_focus_at_zero_distance(models):
    """Diam = 0 makes the two-focus model equal the single-focus model."""
    x = np.logspace(-7, 0, 300)
    p = dict(N=1.7, D=120.0, w_r=0.22, w_z=1.1, tau_T=2.0, Trip=0.08, y_0=0.01)
    single = _eval(models[SINGLE_FOCUS]["equation"], p, x)
    two = _eval(models[TWO_FOCUS]["equation"], dict(p, diam=0.0), x)
    assert np.allclose(two, single, rtol=1e-9, atol=0.0)
