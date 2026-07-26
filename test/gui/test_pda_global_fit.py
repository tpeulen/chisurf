"""Joint two-colour + three-colour PDA fitting (PRD-65 stage 5).

A three-colour construct shares a dye pair with the two-colour measurement of
the same pair, so the two datasets constrain a common distance. Fitting them
together is what turns "two experiments that roughly agree" into one number with
one uncertainty.

Nothing here is c3PDA-specific machinery: ChiSurf's global fit concatenates the
weighted residuals of its member fits and its parameter linking is generic, so
this is a check that the PDA models are ordinary enough to use both — not a new
implementation.
"""

from __future__ import annotations

import numpy as np
import pytest

TRUTH_GR = 52.0


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _three_colour_fit(n_bursts=2500, seed=31):
    """A c3PDA fit over simulated bursts, only R(GR) free."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.c3pda import C3PdaSimulatorReader
    from chisurf.core.models.c3pda.c3pda import C3PdaModel

    reader = C3PdaSimulatorReader(
        n_bursts=n_bursts, seed=seed, r_gr=TRUTH_GR, r_bg=46.0, r_br=68.0, sigma=6.0
    )
    fit = fit_mod.Fit(model_class=C3PdaModel, data=reader.read()[0])
    model = fit.model
    model.find_parameters()
    for parameter in model.parameters_all:
        parameter.fixed = True
    for parameter, value in zip(model.species.means_of(0), (TRUTH_GR, 46.0, 68.0)):
        parameter.value = value
    mean = model.species.means_of(0)[0]
    mean.fixed = False
    model.find_parameters()
    return fit, model, mean


def _two_colour_fit(seed=7):
    """A two-colour Gaussian PDA fit whose distance is the same dye pair."""
    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.models.pda.pdagauss import PdaGaussianDistanceModel

    from test.gui.test_pda_model_editor import _make_pda_fit  # noqa: PLC0415

    fit = _make_pda_fit(PdaGaussianDistanceModel)
    model = fit.model
    model.distances._means[0].value = TRUTH_GR
    model.distances._sigmas[0].value = 6.0
    model.update()
    _ = model.get_wres(fit)

    s1s2 = np.asarray(model.pda.get_S1S2_matrix(), dtype=float)
    ny, nx = fit.data.pda["shape"]
    s1s2 = s1s2[:ny, :nx]
    s1s2 = s1s2 / max(s1s2.sum(), 1e-12) * 5e4
    noisy = np.random.default_rng(seed).poisson(s1s2).astype(float)
    fit.data.pda["s1s2"] = noisy
    fit.data.y = noisy.ravel(order="C")
    fit.data.ey = tcspc.counting_noise(fit.data.y)

    model.find_parameters()
    for parameter in model.parameters_all:
        parameter.fixed = True
    mean = model.distances._means[0]
    mean.fixed = False
    model.find_parameters()
    return fit, model, mean


def test_a_global_model_accepts_both_pda_families(qapp):
    """The residual vector is the two datasets' residuals, end to end."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.global_model.globalfit import GlobalFitModel

    three, three_model, _ = _three_colour_fit()
    two, two_model, _ = _two_colour_fit()
    three_model.update()
    two_model.update()

    host = fit_mod.Fit(model_class=GlobalFitModel, data=two.data)
    host.model.fits = [two, three]

    residuals = host.model.weighted_residuals
    assert residuals.ndim == 1
    expected = (
        two_model.weighted_residuals.size + three_model.weighted_residuals.size
    )
    assert residuals.size == expected
    assert np.all(np.isfinite(residuals))

    # The point counts add up too, so chi2r has a sane denominator.
    assert host.model.n_points == two_model.n_points + three_model.n_points


def test_linking_makes_one_distance_serve_both_datasets(qapp):
    """A linked parameter must follow its target, not drift independently."""
    three, _, three_mean = _three_colour_fit()
    two, _, two_mean = _two_colour_fit()

    three_mean.link = two_mean
    assert three_mean.is_linked
    for value in (44.0, 57.5):
        two_mean.value = value
        assert float(three_mean.value) == pytest.approx(value)

    # A linked follower must not be offered to the optimiser twice.
    three.model.find_parameters()
    assert three_mean.name not in [p.name for p in three.model.parameters]

    three_mean.link = None
    assert not three_mean.is_linked


@pytest.mark.slow
def test_the_joint_fit_recovers_the_shared_distance(qapp):
    """PRD-65 stage 5: one distance, both datasets, one number out.

    The two-colour and three-colour measurements see the same dye pair, so the
    shared distance is over-determined — which is the point of fitting them
    together rather than averaging two answers afterwards.
    """
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.global_model.globalfit import GlobalFitModel

    three, _, three_mean = _three_colour_fit()
    two, _, two_mean = _two_colour_fit()

    three_mean.link = two_mean          # one free distance across both
    two_mean.value = 46.0               # start well away from the truth
    two.model.find_parameters()
    three.model.find_parameters()

    host = fit_mod.Fit(model_class=GlobalFitModel, data=two.data)
    host.model.fits = [two, three]
    host.model.find_parameters()

    free = [p.name for p in host.model.parameters]
    assert two_mean.name in free, free
    host.run()

    assert float(two_mean.value) == pytest.approx(TRUTH_GR, abs=1.5)
    assert float(three_mean.value) == pytest.approx(float(two_mean.value))
