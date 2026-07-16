"""A/B verification of the PCF (pair-correlation) distribution models vs PAM.

The PCF experiment type's catalogue (`chisurf/core/models/pcf/models.yaml`) is
ported from PAM's `Models/fcs/PCF_*.m`. Each ChiSurf equation is evaluated
through the real `ParseModel` scanner and asserted equal to a verbatim
transcription of PAM's `fit` lambda, at PAM's default parameters and over random
draws. The gamma model folds PAM's x-independent `1/gamma(alpha)` normaliser into
the amplitude, so its A/B check compares against PAM's exact lambda times
`gamma(alpha)`.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest
import yaml
from scipy.special import gamma as gamma_fn

PCF_YAML = (
    pathlib.Path(__file__).resolve().parents[2]
    / "chisurf" / "core" / "models" / "pcf" / "models.yaml"
)


@pytest.fixture(scope="module")
def models():
    with open(PCF_YAML) as handle:
        return yaml.safe_load(handle)


def _parse_and_eval(equation, values, x):
    """Evaluate a models.yaml equation through the real ParseModel scanner."""
    from numpy import exp, log, sqrt  # noqa: F401 — referenced in eval scope

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


# PAM reference lambdas (verbatim from junk/PAM/Models/fcs/PCF_*.m).
def _pcf_lognormal(x, A, Mode, sigma):
    # PAM's y0 is unused in its fit function, so it is omitted from the port.
    return A / sigma / np.sqrt(2 * np.pi) / x * np.exp(
        -(np.log(x / Mode * 1000) - sigma ** 2) ** 2 / (2 * sigma ** 2))


def _pcf_loggaussian(x, A, Mode, sigma, y_0):
    return A * np.exp(-(np.log(x / Mode * 1000)) ** 2 / (2 * sigma ** 2)) + y_0


def _pcf_gamma_pam(x, A, alpha, beta):
    return A * beta ** alpha * x ** (alpha - 1) * np.exp(-x * beta) / gamma_fn(alpha)


CASES = {
    "PCF Log-Normal": (
        _pcf_lognormal,
        dict(A=(0.2, 5), Mode=(1, 100), sigma=(0.3, 2)),
        dict(A=1, Mode=20, sigma=1)),  # PAM defaults
    "PCF Log-Gaussian": (
        _pcf_loggaussian,
        dict(A=(0.2, 5), Mode=(1, 100), sigma=(0.3, 2), y_0=(-0.5, 0.5)),
        dict(A=1, Mode=20, sigma=1, y_0=0)),
}


def test_models_present(models):
    assert set(models) == {"PCF Log-Normal", "PCF Log-Gaussian", "PCF Gamma"}


@pytest.mark.parametrize("name", list(CASES))
def test_pcf_ab_matches_reference(models, name):
    """The PCF equation matches PAM's fit lambda at PAM defaults and random draws."""
    ref_fn, ranges, defaults = CASES[name]
    entry = models[name]
    assert set(entry["initial"]) == set(ranges)
    x = np.logspace(-4, 1, 200)  # lag times (s); Mode is in ms
    rng = np.random.default_rng(7)
    param_sets = [defaults] + [
        {k: float(rng.uniform(lo, hi)) for k, (lo, hi) in ranges.items()} for _ in range(6)
    ]
    for params in param_sets:
        a = ref_fn(x=x, **params)
        b = _parse_and_eval(entry["equation"], params, x)
        assert np.all(np.isfinite(a)) and np.all(np.isfinite(b)), name
        assert np.allclose(a, b, rtol=1e-6, atol=1e-12), (name, params)


def test_pcf_gamma_matches_pam_shape(models):
    """PCF Gamma equals PAM's gamma distribution (normaliser folded into A)."""
    entry = models["PCF Gamma"]
    assert set(entry["initial"]) == {"A", "alpha", "beta"}
    x = np.logspace(-4, 1, 200)
    rng = np.random.default_rng(11)
    for params in [dict(A=1, alpha=2, beta=1)] + [
        dict(A=float(rng.uniform(0.2, 5)), alpha=float(rng.uniform(1.1, 6)),
             beta=float(rng.uniform(0.2, 5))) for _ in range(6)
    ]:
        b = _parse_and_eval(entry["equation"], params, x)
        # PAM includes /gamma(alpha); the port folds it into A, so B == PAM * gamma(alpha).
        pam = _pcf_gamma_pam(x, **params)
        assert np.allclose(b, pam * gamma_fn(params["alpha"]), rtol=1e-6, atol=1e-12), params
