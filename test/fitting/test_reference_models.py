"""A lifetime fit recovers the decay that made the data.

Single exponential, Poisson counts, no response to convolve with: the
described lifetime model (BFF's ``tcspc_lifetime``) fitted through ChiSurf's
fit object must return the lifetime and the background.
"""

import numpy as np
import pytest

pytest.importorskip("IMP.bff")

import chisurf.core.data
from chisurf.core.fitting.fit import Fit
from chisurf.core.fluorescence.decay import sample_decay_shot_noise
from chisurf.core.models.description import for_family


def test_lifetime_model_convergence():
    true_tau, true_amp, true_bg, dt, n = 4.0, 1000.0, 10.0, 0.032, 1024
    time = np.arange(n) * dt
    y = sample_decay_shot_noise(true_amp * np.exp(-time / true_tau) + true_bg, seed=1).astype(float)
    data = chisurf.core.data.DataCurve(x=time, y=y, ey=np.sqrt(np.maximum(y, 1.0)))

    fit = Fit(model_class=for_family("tcspc_lifetime"), data=data)
    fit.xmin, fit.xmax = 0, n - 1
    model = fit.model
    model.set_scalar("convolve", 0.0)          # the data were not convolved
    model.set_scalar("periodic_excitation", 0.0)
    model.set_scalar("generated_response", 1.0)
    assert model.problem is not None, model.missing
    model.structure = "lifetime.components.1"
    parameters = {p.canonical_id: p for p in model.parameters_all}
    parameters["lifetime.tau.0"].value = 3.0
    parameters["instrument.background"].value = 5.0
    parameters["instrument.n0"].value = float(y.sum())
    fit.run()

    parameters = {p.canonical_id: p for p in model.parameters_all}
    assert parameters["lifetime.tau.0"].value == pytest.approx(true_tau, rel=0.05)
    assert parameters["instrument.background"].value == pytest.approx(true_bg, rel=0.3)
    assert fit.chi2r < 1.5
