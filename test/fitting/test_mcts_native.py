"""The classic ChiSurf lifetime model and BFF model search.

A described model (``DescriptionModel``) is searched on its own live problem;
see ``test_description_model.py``. The classic ``LifetimeModel`` is not a view on
a BFF model, so it gets parameter refinement and nothing structural.
"""

from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.fitting.mcts.native import prepare_native_model_search
from chisurf.core.fitting.mcts.dispatcher import prepare_model_search
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.tcspc.lifetime import LifetimeModel

N = 128
DT = 0.048


def _two_lifetime_fit(seed: int = 7):
    import tttrlib

    x = np.arange(N) * DT
    irf = 1000.0 * np.exp(-0.5 * ((x - 1.0) / 0.08) ** 2)
    clean = np.zeros(N)
    tttrlib.fconv_per_cs(
        clean,
        irf / irf.sum(),
        np.array([0.4, 0.9, 0.6, 3.2]),
        12.5,
        N - 1,
        N - 1,
        DT,
    )
    clean = clean / clean.max() * 4000.0 + 2.0
    y = np.random.default_rng(seed).poisson(clean).astype(float)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0)))
    fit = fitting.Fit(model_class=LifetimeModel, data=data, noise_model="poisson")
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.convolve._irf = chisurf.core.curve.Curve(x=x, y=irf.copy())
    model.convolve.dt = DT
    model.convolve.rep_rate = 80.0
    model.convolve.stop = N * DT
    # The user's instrument lock remains authoritative in every candidate.
    model.convolve._ts.fixed = True
    model.lifetimes._lifetimes[0].value = 3.0
    model.lifetimes.append(amplitude=0.3, lifetime=0.8)
    model.find_parameters()
    return fit


def _state(fit):
    def stable_value(parameter):
        value = float(parameter.value)
        return None if np.isnan(value) else value

    return tuple(
        (stable_value(p), bool(p.fixed), p.link, bool(getattr(p, "redundant", False)))
        for p in fit.model.parameters_all
    )


def test_a_classic_lifetime_model_has_no_model_search():
    """The classic class has no BFF graph any more (its description does), and
    a search is BFF's or it does not exist: refused, the fit untouched."""
    fit = _two_lifetime_fit()
    before = _state(fit)

    prepared = prepare_model_search(fit)

    assert not prepared.supported
    assert any(r.code == "native_objective_unrepresentable" for r in prepared.reasons)
    assert _state(fit) == before
