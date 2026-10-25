"""Ported from the script-style test_anisotropy_to_kappa.py: the
AnisotropyToKappaModel against the closed-form k2dfun reference."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fitting.fit import Fit
from chisurf.core.models.anisotropy_to_kappa import AnisotropyToKappaModel
from chisurf.plugins.calculator.kappa2_dist.k2dfun import kappasq, s2delta


@pytest.fixture()
def model() -> AnisotropyToKappaModel:
    fit = Fit()
    return AnisotropyToKappaModel(fit=fit, r0=0.38)


def _reference(model: AnisotropyToKappaModel, r_d: float, r_a: float, r_s: float) -> float:
    s2_donor = -np.sqrt(r_d / model.r0)
    s2_acceptor = np.sqrt(r_a / model.r0)
    _, delta = s2delta(
        s2_donor=s2_donor, s2_acceptor=s2_acceptor, r_inf_AD=r_s, r_0=model.r0
    )
    return kappasq(delta=delta, sD2=s2_donor, sA2=s2_acceptor, beta1=0.0, beta2=0.0)


@pytest.mark.parametrize(
    "r_donor,r_acceptor,r_sensitized",
    [(0.10, 0.15, 0.02), (0.05, 0.05, 0.01), (0.15, 0.20, 0.03), (0.25, 0.10, 0.05)],
)
def test_kappa_squared_matches_the_closed_form(
    model, r_donor, r_acceptor, r_sensitized
):
    model.r_donor.value = r_donor
    model.r_acceptor.value = r_acceptor
    model.r_sensitized.value = r_sensitized
    model._update_model()
    expected = _reference(model, r_donor, r_acceptor, r_sensitized)
    assert model.kappa_squared.value == pytest.approx(expected, abs=1e-9)
    # NB: the closed form itself goes negative for these inputs (kappasq with
    # beta1 = beta2 = 0); the port pins model-vs-reference equality, the sign
    # question is recorded as a known issue against k2dfun's domain.
