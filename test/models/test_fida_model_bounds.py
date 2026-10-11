"""``FidaModel``'s brightness, occupancy and background are bounded at zero by default.

Unbounded, the guide-04 fit drove both N negative, which switches the species off and
leaves a pure background (χ²ᵣ = 407); the guide told users to tick every *Bounds* box by
hand (found 2026-10-11).
"""

import numpy as np

import chisurf.core.fitting.fit as fit_mod
from chisurf.core.data import DataCurve
from chisurf.core.models.pch import fida
from chisurf.core.models.pch.fida_model import FidaModel


def _fit(counts):
    k = np.arange(counts.size, dtype=float)
    total = counts.sum()
    data = DataCurve(
        name="synthetic PCH", load_filename_on_init=False, x=k, y=counts / total,
        ey=np.sqrt(np.maximum(counts, 1.0)) / total,
    )
    fit = fit_mod.Fit(model_class=FidaModel, data=data)
    fit.fit_range = (0, counts.size)
    return fit


def test_every_physical_parameter_is_bounded_at_zero():
    fit = _fit(np.ones(20))
    physical = [p for p in fit.model.parameters_all if p.name[0] in "qN" or p.name == "bg"]
    assert physical and all(p.bounds_on and p.bounds[0] == 0.0 for p in physical)


def test_a_default_fit_keeps_the_numbers_positive():
    p = np.asarray(fida.fida_pch(30, species=[(1.0, 4.0), (8.0, 0.3)], background=0.05))
    counts = np.random.default_rng(2).multinomial(2_000_000, p / p.sum()).astype(float)
    fit = _fit(counts)
    start = {"q1": 0.5, "N1": 1.0, "q2": 5.0, "N2": 0.01}
    for par in fit.model.parameters_all:
        if par.name in ("q3", "N3"):
            par.fixed = True
        if par.name in start:
            par.value = start[par.name]
    fit.run()
    values = {par.name: par.value for par in fit.model.parameters_all}
    assert min(values["N1"], values["N2"], values["q1"], values["q2"]) > 0, values
    assert fit.chi2r < 5.0, fit.chi2r
