"""Three-colour PDA: a model that cannot evaluate must say so.

The residual vector and ``n_points`` are read together to form chi2r. A model
that answers an evaluation failure with an *empty* residual therefore reports
``chi2r = 0`` — the best fit the GUI can show — and only fails later, inside the
optimiser, with a message naming neither the model nor the cause. These tests
pin the honest behaviour instead.
"""

from __future__ import annotations

import numpy as np
import pytest


def _model(n_bursts: int = 100, seed: int = 3):
    """Return a PDA3c model fitted to a simulated three-colour burst set."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.pda3c import Pda3cModel

    data = Pda3cSimulatorReader(n_bursts=n_bursts, seed=seed).read()[0]
    return fit_mod.Fit(model_class=Pda3cModel, data=data).model


def test_the_healthy_residual_has_one_entry_per_collapsed_burst():
    """The reference behaviour the failure cases are measured against."""
    model = _model()
    counts = model.burst_counts()
    wres = model.get_wres(model.fit)

    assert wres.size == counts.blue.shape[0]
    assert np.all(np.isfinite(wres))
    assert model.fit.chi2r > 0.0


def test_a_failing_likelihood_raises_instead_of_reporting_a_perfect_fit():
    """The residual must not collapse to length zero when evaluation fails.

    ``n_points`` keeps counting the bursts whatever the likelihood does, so an
    empty residual divides zero by a positive number of observations and shows
    a perfect fit.
    """
    model = _model()

    def explode(counts):
        raise ValueError("the rate matrix does not match the species list")

    model._per_burst_log_likelihood = explode

    assert model.n_points > 0  # the disagreement that hid it
    with pytest.raises(ValueError, match="rate matrix"):
        model.get_wres(model.fit)


def test_an_unusable_burst_payload_is_not_read_as_no_data():
    """A malformed payload is an error; only a *missing* one means "no data"."""
    model = _model()
    model._counts_cache = None
    model.fit.data.meta_data["pda3c"]["green"] = np.zeros((3, 2))  # wrong burst count

    with pytest.raises(ValueError, match="pda3c burst payload"):
        model.burst_counts()
