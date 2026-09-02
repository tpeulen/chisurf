"""A TCSPC lifetime fit on the bff graph, against the one in numpy.

A parse model has run entirely in C++ since 2026-09-01, but a parse model is
not what anyone fits. This is the first *instrument* model on the graph: the
curve is `IMP.bff.TcspcDecay`, which reconvolves the lifetime spectrum with
the measured response using **tttrlib's own** kernels, and the misfit is the
same `ChiSquared` a parse model uses. bff builds the network, tttrlib
computes the curve, and ChiSurf is not between them.

What is checked here is what makes the speed allowed: the same minimum, the
same reduced chi-square, the same error estimates, and a model carrying a
term the node does not have being *refused* rather than approximated.
"""
import numpy as np
import pytest

import chisurf as cs
import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as F
import chisurf.core.fitting.minimizer as M
from chisurf.core.models.tcspc.lifetime import LifetimeModel

pytestmark = pytest.mark.skipif(
    not M.have_minimizer() or not hasattr(M._bff, "TcspcDecay"),
    reason="IMP.bff carries no TcspcDecay")

N = 512
DT = 0.032
REP_RATE = 80.0


def simulated(lifetime=3.1, counts=4000.0, background=2.0, seed=7):
    """A decay, its response, and Poisson counts -- the shape of real data."""
    import tttrlib
    x = np.arange(N) * DT
    irf = 1000.0 * np.exp(-0.5 * ((x - 1.0) / 0.08) ** 2)
    irf_y = irf / irf.sum()
    clean = np.zeros(N)
    tttrlib.fconv_per_cs(clean, irf_y, np.array([1.0, lifetime]),
                         1000.0 / REP_RATE, N - 1, N - 1, DT)
    clean = clean / clean.max() * counts + background
    y = np.random.default_rng(seed).poisson(clean).astype(float)
    return x, irf, y, np.sqrt(np.maximum(y, 1.0))


def make_fit(start_lifetime=4.0, model_class=LifetimeModel, **kwargs):
    x, irf, y, ey = simulated(**kwargs)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=ey)
    fit = F.Fit(model_class=model_class, data=data)
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    model.convolve._irf = chisurf.core.curve.Curve(x=x, y=irf.copy())
    model.convolve.dt = DT
    model.convolve.rep_rate = REP_RATE
    model.convolve.stop = N * DT
    model.find_parameters()
    model.parameters_all_dict["tL1"].value = start_lifetime
    return fit


def run_with_scipy(fit):
    """Run *fit* with the graph refused, i.e. down the numpy path."""
    original = M.graph_objective
    M.graph_objective = lambda *a, **k: None
    try:
        fit.run()
    finally:
        M.graph_objective = original
    return fit


def test_the_graph_is_taken_for_a_lifetime_model():
    fit = make_fit()
    assert M.graph_objective(fit, fit.model) is not None


def test_the_curve_is_the_same_curve():
    """Before any fitting: the node and `update_model` must agree.

    This is the test that would catch a term applied in the wrong order --
    the response normalised before the shift rather than after, say, which
    moves the model by a fraction of a percent and would otherwise surface
    as a slightly different lifetime.
    """
    fit = make_fit()
    fit.model.update()
    built = M.graph_objective(fit, fit.model)
    node = built[0]._decay
    node.update()
    graph = np.asarray(node.get_output_port("decay").value, dtype=float)
    python = np.asarray(fit.model.y, dtype=float)
    np.testing.assert_allclose(graph, python, rtol=1e-10)


def test_the_answer_does_not_move():
    """Compared in units of the uncertainty, which is the meaningful one.

    A blanket relative tolerance asks the wrong question of a *loose*
    parameter: this fit's background is determined to about 0.8, so the two
    optimisers stopping 1e-4 apart on it is them agreeing, not disagreeing.
    Both stop at their shared `xtol`, which is relative to the step, so what
    has to be small is the gap measured against what the data can resolve.
    """
    graph, scipy = make_fit(), make_fit()
    graph.run()
    run_with_scipy(scipy)
    a = np.array([p.value for p in graph.model.parameters], float)
    b = np.array([p.value for p in scipy.model.parameters], float)
    sigma = np.array([p.error_estimate for p in scipy.model.parameters], float)
    np.testing.assert_array_less(np.abs(a - b), 0.01 * sigma)
    # And the real proof that it is the same minimum, not a nearby one.
    assert graph.chi2r == pytest.approx(scipy.chi2r, rel=1e-6)


def test_the_error_estimates_do_not_move():
    graph, scipy = make_fit(), make_fit()
    graph.run()
    run_with_scipy(scipy)
    a = np.array([p.error_estimate for p in graph.model.parameters], float)
    b = np.array([p.error_estimate for p in scipy.model.parameters], float)
    assert np.all(np.isfinite(a))
    np.testing.assert_allclose(a, b, rtol=5e-3)


def test_the_lifetime_is_recovered():
    """A fit that agrees with a wrong fit is not worth having.

    The tolerance is loose on purpose. These are Poisson counts fitted with
    ``ey = sqrt(y)``, i.e. Neyman weighting, which is *biased*: an
    under-counted channel gets an over-large weight, so the fitted lifetime
    comes out about 1.5% high here. That bias is the estimator's and the
    numpy path shows it too -- `test_the_answer_does_not_move` is what says
    the graph did not add one of its own.
    """
    fit = make_fit()
    fit.run()
    assert fit.model.parameters_all_dict["tL1"].value == pytest.approx(
        3.1, abs=0.1)


def test_the_model_curve_is_the_fitted_one():
    """The graph is private, so the answer has to be published.

    Since T-20260901-11's expensive half the published curve is the
    *graph's* (read off the node's output port), so re-running ChiSurf's
    own pipeline reproduces it to the two paths' pinned parity (~1e-10),
    not to machine precision -- they are one set of kernels composed twice,
    and 1e-10 is the documented bound of that composition."""
    fit = make_fit()
    fit.run()
    before = np.asarray(fit.model.y, dtype=float).copy()
    fit.model.update()
    np.testing.assert_allclose(np.asarray(fit.model.y, dtype=float), before,
                               rtol=2e-9)


def test_the_autoscaled_amplitude_is_published():
    """`n0` is computed from the data, in C++, and is not a free parameter.

    ChiSurf's own `update_model` recomputes it during the write-back, so the
    displayed value belongs to the fitted parameters rather than to the last
    trial the optimiser happened to take.
    """
    fit = make_fit()
    assert fit.model.convolve._n0.fixed, "autoscale is ChiSurf's default"
    fit.run()
    assert fit.model.convolve.n0 > 0.0
    assert "n0" not in [p.name for p in fit.model.parameters]


# ------------------------------------------------------- what is refused

def _refuses(fit):
    return M.graph_objective(fit, fit.model) is None


def test_pile_up_joins_the_graph_with_the_same_curve():
    """Coates' correction runs in the node since 2026-09-02 (T-20260902-10).

    tttrlib's kernel with chisurf's edge-case semantics, applied between
    the scatter term and the scaling -- the same slot `Corrections.pileup`
    occupies in the Python pipeline. The graph must produce the *same*
    piled-up curve as `update_model`, and the correction must actually do
    something (a fixture whose pile-up is a no-op proves nothing).
    """
    fit = make_fit(counts=40000.0)
    corrections = fit.model.corrections
    corrections.correct_pile_up = True
    corrections.dead_time = 120.0
    # A measurement time that leaves about twice as many excitation pulses
    # as detected photons *after* the dead time: Coates stays well defined
    # and the per-pulse detection probability is large enough that the
    # correction visibly reshapes the decay. (A time the dead time alone
    # exceeds triggers the unscaled-model guard and proves nothing.)
    total = float(np.sum(fit.data.y))
    corrections.measurement_time = total * (
        corrections.dead_time * 1e-9 + 2.0 / (REP_RATE * 1e6))

    fit.model.update()
    built = M.graph_objective(fit, fit.model)
    assert built is not None, "pile-up must not refuse the graph any more"
    node = built[0]._decay
    node.update()
    graph = np.asarray(node.get_output_port("decay").value, dtype=float)
    # A *copy*: model.y hands back its own buffer, which the next
    # update_model overwrites in place.
    python = np.array(fit.model.y, dtype=float)
    np.testing.assert_allclose(graph, python, rtol=1e-10)

    # The correction did something: the same fixture without it differs.
    corrections.correct_pile_up = False
    fit.model.update()
    plain = np.array(fit.model.y, dtype=float)
    assert np.max(np.abs(python - plain)) / np.max(plain) > 1e-4


def test_the_dnl_table_joins_the_graph_with_the_same_curve():
    """The linearization runs in the node since 2026-09-02 (PRD-105 phase 3).

    `Corrections.linearize` multiplies the finished curve by a measured
    channel-width table, after the constant background and before the
    non-negativity clamp; the node applies the same table in the same slot.
    The table must be a real one (a flat table of ones is a no-op and
    proves nothing) and the `reverse` orientation must ride along, because
    `lintable` resolves it at read time and the builder reads it once.
    """
    fit = make_fit()
    corrections = fit.model.corrections
    corrections.correct_dnl = True
    # A visibly non-flat table, deterministic, mean ~1 -- the shape a real
    # DNL calibration has.
    channels = np.arange(N, dtype=float)
    corrections._lintable = 1.0 + 0.05 * np.sin(2.0 * np.pi * channels / 37.0)

    for reverse in (False, True):
        corrections.reverse = reverse
        fit.model.update()
        built = M.graph_objective(fit, fit.model)
        assert built is not None, "a DNL table must not refuse the graph"
        node = built[0]._decay
        node.update()
        graph = np.asarray(node.get_output_port("decay").value, dtype=float)
        python = np.array(fit.model.y, dtype=float)
        np.testing.assert_allclose(graph, python, rtol=1e-12)

    # The correction did something: the same fixture without it differs.
    with_table = np.array(fit.model.y, dtype=float)
    corrections.correct_dnl = False
    fit.model.update()
    plain = np.array(fit.model.y, dtype=float)
    assert np.max(np.abs(with_table - plain)) / np.max(plain) > 1e-3


def test_the_dnl_answer_does_not_move():
    """With the table armed, the graph fit and the numpy fit agree."""
    fit_graph = make_fit()
    fit_scipy = make_fit()
    channels = np.arange(N, dtype=float)
    table = 1.0 + 0.05 * np.sin(2.0 * np.pi * channels / 37.0)
    for fit in (fit_graph, fit_scipy):
        fit.model.corrections.correct_dnl = True
        fit.model.corrections._lintable = table.copy()
    fit_graph.run()
    run_with_scipy(fit_scipy)
    a = fit_graph.model.parameters_all_dict["tL1"].value
    b = fit_scipy.model.parameters_all_dict["tL1"].value
    assert a == pytest.approx(b, rel=1e-4)
    assert a == pytest.approx(3.1, abs=0.1)


def test_a_background_curve_refuses_the_graph():
    """A measured background is a second curve, mixed by photon counts."""
    fit = make_fit()
    x = np.asarray(fit.data.x, dtype=float)
    fit.model.generic.background_curve = chisurf.core.curve.Curve(
        x=x, y=np.ones_like(x))
    assert _refuses(fit)




def test_switching_the_convolution_off_refuses_the_graph():
    fit = make_fit()
    fit.model.convolve.do_convolution = False
    assert _refuses(fit)


def test_a_non_periodic_mode_refuses_the_graph():
    fit = make_fit()
    fit.model.convolve.mode = "exp"
    assert _refuses(fit)


def test_a_refused_model_still_fits():
    """The fallback is the numpy path, and it is the definition."""
    fit = make_fit()
    fit.model.corrections.correct_pile_up = True
    fit.run()
    assert fit.model.parameters_all_dict["tL1"].value == pytest.approx(
        3.1, abs=0.1)


# --------------------------------------- the covariance the optimiser has

def test_the_offered_covariance_is_the_finite_difference_one():
    """The matrix the C++ side hands over is `covariance_matrix`'s own.

    **The trap this closes.** `test_the_error_estimates_do_not_move` above
    compares the graph path against the scipy path -- and for a TCSPC fit
    both used to refuse the C++ covariance and fall back to the same numpy
    `covariance_matrix`, so it was comparing numpy against numpy and passed
    against any C++ Jacobian whatsoever. This one asks what was actually
    handed over.

    Tighter than the parse fit's version of it, and that is the point: this
    matrix is not MINPACK's QR (which the guard still refuses here, see
    below) but the same forward differences at the same step, taken over the
    graph instead of over the Python model. It should agree to the last few
    digits the two curves share, not merely to the four the table shows.
    """
    from test.fitting.test_graph_fit import covariance_the_graph_offered
    fit = make_fit()
    (cpp, used), (numpy_cov, numpy_used) = covariance_the_graph_offered(fit)
    assert used == numpy_used
    np.testing.assert_allclose(np.sqrt(np.diag(cpp)),
                               np.sqrt(np.diag(numpy_cov)), rtol=1e-5)


def test_a_round_off_column_does_not_become_an_error_bar():
    """The property the refusal used to defend, and the remedy that replaced it.

    This model's free vector spans ``1e-5`` (a scatter fraction) to ``3.15``
    (a lifetime), so `lmdif` -- which differences at ``sqrt(epsfcn)|x_j|``, a
    step *relative to the parameter* -- probes the scatter at ~1e-8 and gets
    a column of round-off. Its covariance then reports a standard deviation
    orders too large. Nothing about that is wrong in the optimiser and
    *scipy's own* covariance for this fit is no better; it is what a relative
    step means.

    Until 2026-09-01 the remedy was to refuse the matrix and rebuild the
    Jacobian in numpy, at ``p + 1`` calls to `update_model` -- a third of the
    fit. Now it is differenced at a step that *resolves*, in C++ over the
    graph. What must stay true either way is that the round-off column does
    not become an error bar, so that is what is asserted: the guard still
    says the QR matrix is not usable here, the QR matrix is indeed wildly
    wrong on the small parameter, and the number actually reported is the
    finite-difference one.
    """
    from test.fitting.test_graph_fit import minimizer_of
    fit = make_fit()
    caught = minimizer_of(fit)
    x = caught["x"]
    assert np.abs(x).min() < 1e-3 * np.abs(x).max(), (
        "this fixture no longer spans the range the guard is about")
    assert not M._forward_differences_resolved(x, caught["options"].get(
        "epsfcn")), "the guard no longer refuses MINPACK's step here"

    k = int(np.argmin(np.abs(x)))
    numpy_cov, numpy_used = F.covariance_matrix(fit)
    resolved = float(np.sqrt(np.diag(numpy_cov))[numpy_used.index(k)])
    reported = float(fit.model.parameters[k].error_estimate)
    assert reported == pytest.approx(resolved, rel=1e-4), (
        "the reported error bar is not the one taken at a resolving step")

    qr = float(np.sqrt(np.diag(caught["minimizer"].covariance))[k])
    assert qr > 10.0 * resolved, (
        "the QR covariance is no longer wrong on this parameter, so this "
        "fixture no longer demonstrates what it is here to demonstrate")


def test_a_well_scaled_fit_still_uses_the_free_covariance():
    """The guard must not throw away the saving it was built to allow.

    A parse fit whose parameters are all of one order keeps *MINPACK's own*
    matrix, which costs nothing -- the optimiser ends holding the
    factorisation it comes from. Asserted as an identity against
    `Minimizer.covariance` rather than as "a stash was offered": since the
    C++ finite-difference matrix became the fallback, a stash is offered for
    every graph fit, and "something was offered" no longer distinguishes the
    free matrix from the one that costs ``p + 1`` evaluations.
    """
    from test.fitting.test_graph_fit import (make_fit as make_parse_fit,
                                             covariance_the_graph_offered,
                                             minimizer_of)
    caught = minimizer_of(make_parse_fit())
    qr = np.asarray(caught["minimizer"].covariance, dtype=float)
    (offered, used), _ = covariance_the_graph_offered(make_parse_fit())
    assert used == list(range(qr.shape[0]))
    np.testing.assert_allclose(offered, qr, rtol=1e-12)


# ------------------------------- a subclass computes its spectrum elsewhere

def test_a_subclass_that_overrides_the_spectrum_refuses_the_graph():
    """The builder reads the ``lifetimes`` group; a subclass may not.

    `MaxEntLifetimeModel` derives its (amplitude, lifetime) pairs from a
    maximum-entropy inversion and `LifetimeMixtureModel` from other fits'
    spectra, so neither is the multi-exponential this graph builds -- but
    both offer the *same four free parameters* the plain model does, because
    their extra ones ship fixed. Refusing on the free parameters alone
    therefore let them through: measured before the check existed, the
    graph's curve and MaxEnt's were 793.8 counts apart at identical
    parameters, and the fit reported no such thing.
    """
    from chisurf.core.models.tcspc.lifetime import LifetimeMixtureModel
    from chisurf.core.models.tcspc.maxent import MaxEntLifetimeModel

    for model_class in (MaxEntLifetimeModel, LifetimeMixtureModel):
        fit = make_fit(model_class=model_class)
        assert M.graph_objective(fit, fit.model) is None, (
            f"{model_class.__name__} overrides lifetime_spectrum, so the "
            f"plain multi-exponential graph is a different objective")


def test_the_refusal_is_about_the_spectrum_and_not_the_class():
    """Stated as the property, so a new subclass inherits the protection.

    What disqualifies a model is that ``lifetime_spectrum`` is not
    `LifetimeModel`'s -- not that it appears on a list of known subclasses,
    which the next one added would not be on.
    """
    from chisurf.core.models.tcspc.lifetime import LifetimeModel

    fit = make_fit()
    assert M._is_lifetime_model(fit.model)

    class OverridingModel(LifetimeModel):
        @property
        def lifetime_spectrum(self):
            return np.array([1.0, 2.0])

    fit.model.__class__ = OverridingModel
    assert not M._is_lifetime_model(fit.model)
    assert M.graph_objective(fit, fit.model) is None


# --------------------------------------------- the polarised decay families

def polarised_fit(polarization="vv", n_rotations=1, rho=2.5, seed=13,
                  **kwargs):
    """A VV, VH or VV/VH model, fitted to data that **has** an anisotropy.

    Two things about the fixture are deliberate.

    `g` is 1.3 rather than 1. At `g = 1` the place the sensitivity ratio
    enters is unobservable, which is exactly how a forward model ends up a
    factor `g**2` off without a test noticing.

    And the data are generated *from the polarised model itself* rather than
    reused from the magic-angle fixture. A rotational correlation time fitted
    to a decay that carries no depolarisation is a flat direction: the two
    optimisers then stop at different points of one valley and disagree by a
    whole sigma while evaluating the identical objective. That is a
    degenerate fixture, not a disagreement worth pinning -- the objective is
    pinned to machine precision by `test_a_polarised_model_is_the_same_curve`
    instead.

    The rotational *amplitudes* stay fixed for the same reason and it is a
    property of the model rather than of the test: `b` is normalised to `r0`,
    so with one rotation the amplitude is redundant by construction and its
    error estimate comes back `nan`.
    """
    fit = make_fit(**kwargs)
    model = fit.model
    model.anisotropy.polarization_type = polarization
    while len(model.anisotropy) < n_rotations:
        model.anisotropy.add_rotation(b=0.2, rho=rho)
    for i, parameter in enumerate(model.anisotropy._rhos):
        parameter.value = rho * (i + 1)
    for parameter in model.anisotropy._bs:
        parameter.fixed = True
    model.anisotropy._g.value = 1.3
    model.find_parameters()

    # Poisson counts from this very model, so the anisotropy the fit is
    # asked to recover is genuinely in the data.
    model.update()
    clean = np.maximum(np.asarray(model.y, dtype=float), 1e-9)
    counts = np.random.default_rng(seed).poisson(clean).astype(float)
    fit.data.y = counts
    fit.data.ey = np.sqrt(np.maximum(counts, 1.0))
    return fit


@pytest.mark.parametrize("polarization", ["vv", "vh", "vv/vh"])
@pytest.mark.parametrize("n_rotations", [1, 2])
def test_a_polarised_model_is_the_same_curve(polarization, n_rotations):
    """The graph and `update_model` agree channel for channel.

    A polarisation is a *spectrum* transform -- the product of two sums of
    exponentials is a sum of exponentials -- so the instrument node
    downstream never learns that one happened. What has to be identical is
    the spectrum reaching it, and a mixed channel is the union of two scaled
    spectra: its length and its ordering are both observable, and neither is
    something a chi-square would report.
    """
    fit = polarised_fit(polarization, n_rotations)
    fit.model.update()
    built = M.graph_objective(fit, fit.model)
    assert built is not None, "a polarised decay no longer builds a graph"
    node = built[0]._decay
    node.update()
    graph = np.asarray(node.get_output_port("decay").value, dtype=float)
    np.testing.assert_allclose(graph, np.asarray(fit.model.y, dtype=float),
                               rtol=1e-10, atol=1e-10)


def test_the_rotation_parameters_are_the_optimisers():
    """`b` and `rho` are free in a polarised fit, so they must be ports.

    ChiSurf fixes them while VM is selected and releases them otherwise; a
    builder that placed only the decay's own parameters would refuse the
    whole model rather than fit it, which is how this stays honest.
    """
    fit = polarised_fit("vv", n_rotations=2)
    # Released here rather than in the fixture: the amplitudes are redundant
    # against `r0` and make a *fit* degenerate, but they are still parameters
    # the builder has to be able to place, and a builder that cannot place
    # one refuses the whole model.
    for parameter in fit.model.anisotropy._bs:
        parameter.fixed = False
    fit.model.find_parameters()
    names = [p.name for p in fit.model.parameters]
    assert "b(1)" in names and "rho(1)" in names
    assert M.graph_objective(fit, fit.model) is not None


def test_a_polarised_answer_does_not_move():
    graph, scipy = polarised_fit("vv"), polarised_fit("vv")
    graph.run()
    run_with_scipy(scipy)
    a = np.array([p.value for p in graph.model.parameters], float)
    b = np.array([p.value for p in scipy.model.parameters], float)
    sigma = np.array([p.error_estimate for p in scipy.model.parameters], float)
    finite = np.isfinite(sigma) & (sigma > 0)
    np.testing.assert_array_less(np.abs(a - b)[finite], 0.01 * sigma[finite])
    assert graph.chi2r == pytest.approx(scipy.chi2r, rel=1e-6)


def test_g_is_not_ignored_by_the_graph():
    """The sensitivity ratio changes the VH curve, and by 1/g.

    Written as a property of the *model* rather than of the node, because
    the failure this guards is a builder that never wires `g` at all -- in
    which case both curves come back identical and every VH fit is quietly
    calibrated at `g = 1`.
    """
    one, two = polarised_fit("vh"), polarised_fit("vh")
    one.model.anisotropy._g.value = 1.0
    two.model.anisotropy._g.value = 2.0
    curves = []
    for fit in (one, two):
        built = M.graph_objective(fit, fit.model)
        built[0]._decay.update()
        curves.append(np.asarray(built[0]._decay.get_curve(), dtype=float))
    assert not np.allclose(curves[0], curves[1])


def test_the_amplitudes_are_normalised_before_the_rotation_not_after():
    """Where `normalize_amplitudes` applies, which is not where it is set.

    ChiSurf normalises inside ``Lifetimes.amplitudes`` -- on the
    *unpolarised* spectrum. Leaving the flag on the decay node instead would
    normalise the polarised amplitudes, whose sum is `1 + 2 r0` rather than
    1, and rescale the whole model curve by a few tens of percent while
    still fitting.
    """
    fit = polarised_fit("vv")
    fit.model.lifetimes.normalize_amplitudes = True
    fit.model.update()
    built = M.graph_objective(fit, fit.model)
    built[0]._decay.update()
    np.testing.assert_allclose(
        np.asarray(built[0]._decay.get_curve(), dtype=float),
        np.asarray(fit.model.y, dtype=float), rtol=1e-10, atol=1e-10)


def test_a_graph_run_never_evaluates_the_python_model():
    """T-20260901-11, both halves: the write-back publishes the parameters
    through the setters and reads the *curve off the graph's output port*
    (with the autoscaled n0 beside it -- the trap), and Fit.run no longer
    re-evaluates what was published. A decay fit's run() makes **zero**
    Python model evaluations; the answer is the graph's, not an equal
    recomputation."""
    fit = make_fit()
    calls = {'n': 0}
    original = fit.model._update_model

    def counting(*a, **kw):
        calls['n'] += 1
        return original(*a, **kw)

    fit.model._update_model = counting
    try:
        fit.run()
    finally:
        fit.model._update_model = original
    assert calls['n'] == 0
    # And the published amplitude is the node's, not a stale one: n0 is
    # positive and the curve is finite and non-trivial.
    assert fit.model.convolve.n0 > 0.0
    assert np.all(np.isfinite(np.asarray(fit.model.y, dtype=float)))
