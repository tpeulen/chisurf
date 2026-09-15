"""The fit that runs entirely in C++, against the one that does not.

``fit.run()`` takes ``Expression -> ChiSquared -> Minimizer`` when the model
is one ``IMP.bff`` can compile: the parameters are ports the optimiser writes
in C++, the curve is computed in C++, the data live in the node, and nothing
crosses the SWIG boundary per iteration. On a 512-point three-parameter parse
fit that is 0.47 ms against 1.38 ms.

Speed is not what these tests check. They check the two things that make the
speed *allowed*: that the answer does not move, and that a model the graph
cannot represent is refused rather than approximated.
"""
import numpy as np
import pytest

import chisurf as cs
import chisurf.core.data
import chisurf.core.fitting.fit as F
import chisurf.core.fitting.minimizer as M
from chisurf.core.models.parse import ParseModel


pytestmark = pytest.mark.skipif(not M.have_minimizer(),
                                reason="IMP.bff carries no Minimizer")

N = 512


def make_fit(equation="a*exp(-x/t)+b", start=(("a", 1.0), ("t", 1.0), ("b", 0.0)),
             sigma=0.02, seed=3, ey=None):
    x = np.linspace(0.1, 20.0, N)
    y = 2.5 * np.exp(-x / 3.1) + 0.4
    y = y + np.random.default_rng(seed).normal(0, sigma, N)
    errors = np.full(N, sigma) if ey is None else ey
    data = cs.core.data.DataCurve(x=x, y=y, ey=errors)
    fit = F.Fit(model_class=ParseModel, data=data)
    fit.model.func = equation
    for name, value in start:
        fit.model.parameters_all_dict[name].value = value
    fit.xmin, fit.xmax = 0, N - 1
    return fit


def covariance_the_graph_offered(fit):
    """Run *fit*, and return what the C++ path offered beside the numpy answer.

    **This exists because the obvious comparison proves nothing.**
    `test_the_error_estimates_do_not_move` runs the fit twice, once on the
    graph and once through scipy, and compares the error bars. That
    discriminates only where the C++ covariance is actually *used*: until
    2026-09-01 a TCSPC fit refused it on both paths and fell back to the same
    numpy `covariance_matrix`, so the test was comparing numpy against numpy
    and would have passed against an arbitrarily wrong C++ Jacobian.

    So this asks the honest question instead -- what matrix did the C++ side
    hand over, and is it the one `covariance_matrix` would have computed? --
    by spying on the reader rather than on the writer. `_optimiser_covariance`
    *pops* the stash, so it is read exactly once and only the reader sees
    what was really used.

    Returns
    -------
    ((cpp, used), (numpy, used_numpy))
        Both matrices and the parameter indices each is over. The indices are
        part of the answer: a parameter that does not move the objective is
        *dropped* rather than inverted, and the two paths have to drop the
        same ones.
    """
    seen = {}
    original = F.Fit._optimiser_covariance

    def spy(self):
        cov, used = original(self)
        seen["offered"] = (None if cov is None else np.asarray(cov, float),
                           None if used is None else list(used))
        return cov, used

    F.Fit._optimiser_covariance = spy
    try:
        fit.run()
    finally:
        F.Fit._optimiser_covariance = original
    cov, used = seen.get("offered", (None, None))
    assert cov is not None, (
        "the C++ path offered no covariance, so this test is comparing "
        "numpy against numpy again")
    numpy_cov, numpy_used = F.covariance_matrix(fit)
    return (cov, used), (np.asarray(numpy_cov, float), list(numpy_used))


def minimizer_of(fit):
    """Run *fit* and keep the `IMP.bff.FitMinimizer` that did it.

    `minimize` builds one per run and drops it, which is right -- it holds
    the graph, and the graph is private to the fit. A test that wants to ask
    the optimiser what it thought (its own QR covariance, the vector it
    stopped at, the `epsfcn` it used) has to catch it on the way past.
    """
    caught = {}
    original = M._covariance_at_the_solution

    def spy(m, free, x, options):
        caught["minimizer"] = m
        caught["x"] = np.asarray(x, dtype=float)
        caught["options"] = dict(options)
        return original(m, free, x, options)

    M._covariance_at_the_solution = spy
    try:
        fit.run()
    finally:
        M._covariance_at_the_solution = original
    assert "minimizer" in caught, "the fit did not take the graph path"
    return caught


def run_with_scipy(fit):
    """Run *fit* with the graph refused, i.e. down the numpy path."""
    original = M.graph_objective
    M.graph_objective = lambda *a, **k: None
    try:
        fit.run()
    finally:
        M.graph_objective = original
    return fit


def test_the_graph_is_taken_for_a_parse_model():
    fit = make_fit()
    assert M.graph_objective(fit, fit.model) is not None


def test_the_answer_does_not_move():
    """The whole justification: same minimum, same reduced chi-square."""
    graph, scipy = make_fit(), make_fit()
    graph.run()
    run_with_scipy(scipy)
    np.testing.assert_allclose([p.value for p in graph.model.parameters],
                               [p.value for p in scipy.model.parameters],
                               rtol=1e-6)
    assert graph.chi2r == pytest.approx(scipy.chi2r, rel=1e-9)


def test_the_error_estimates_do_not_move():
    """The optimiser's own covariance replaces a second Jacobian.

    That saves a third of a fit, and is only allowed because the two agree:
    measured at 5e-4 relative on the parameter standard deviations, against
    the four significant figures the parameter table displays.
    """
    graph, scipy = make_fit(), make_fit()
    graph.run()
    run_with_scipy(scipy)
    a = np.array([p.error_estimate for p in graph.model.parameters], dtype=float)
    b = np.array([p.error_estimate for p in scipy.model.parameters], dtype=float)
    assert np.all(np.isfinite(a))
    np.testing.assert_allclose(a, b, rtol=5e-3)


def test_the_offered_covariance_is_the_finite_difference_one():
    """What the C++ side hands over is what numpy would have computed.

    A parse fit is the case where the *QR* matrix is accepted -- its
    parameters are all of one order, so `lmdif`'s relative step resolves
    every one of them -- and this is what says that matrix may be trusted.
    The tolerance is looser than the TCSPC one for a real reason: the QR
    matrix comes from a Jacobian taken at `sqrt(epsfcn)` = 1e-3, five orders
    coarser than `approx_grad`'s step, so agreeing to a part in a thousand is
    as much as it can do -- and four significant figures is what the
    parameter table shows.
    """
    fit = make_fit()
    (cpp, used), (numpy_cov, numpy_used) = covariance_the_graph_offered(fit)
    assert used == numpy_used
    np.testing.assert_allclose(np.sqrt(np.diag(cpp)),
                               np.sqrt(np.diag(numpy_cov)), rtol=2e-3)


def test_the_model_curve_is_the_fitted_one():
    """The graph is private, so the answer has to be published.

    If the write-back were missing, the parameters would read correctly (they
    are set from the answer) while the *curve* still belonged to the starting
    values -- and the residuals plot would be of a fit that never happened.
    """
    fit = make_fit()
    fit.run()
    parameters = {p.name: p.value for p in fit.model.parameters}
    x = np.asarray(fit.data.x, dtype=float)
    expected = (parameters["a"] * np.exp(-x / parameters["t"])
                + parameters["b"])
    np.testing.assert_allclose(np.asarray(fit.model.y, dtype=float), expected,
                               rtol=1e-10)


def test_a_stale_covariance_is_never_reused():
    """A second run must not report the first run's error bars."""
    fit = make_fit()
    fit.run()
    first = [p.error_estimate for p in fit.model.parameters]
    assert "_cpp_covariance" not in fit.__dict__, "the stash outlived its run"
    for name, value in (("a", 1.0), ("t", 1.0), ("b", 0.0)):
        fit.model.parameters_all_dict[name].value = value
    fit.run()
    second = [p.error_estimate for p in fit.model.parameters]
    np.testing.assert_allclose(second, first, rtol=1e-6)


def test_a_fixed_parameter_stays_fixed_and_is_a_constant_in_the_graph():
    fit = make_fit()
    fit.model.parameters_all_dict["b"].value = 0.4
    fit.model.parameters_all_dict["b"].fixed = True
    fit.model.find_parameters()
    assert [p.name for p in fit.model.parameters] == ["a", "t"]
    fit.run()
    assert fit.model.parameters_all_dict["b"].value == pytest.approx(0.4)
    assert fit.chi2r < 2.0


def test_bounds_are_honoured():
    fit = make_fit()
    t = fit.model.parameters_all_dict["t"]
    t.bounds = (0.01, 1.5)
    t.bounds_on = True
    fit.run()
    assert 0.01 - 1e-9 <= t.value <= 1.5 + 1e-9


# ------------------------------------------------------- what is refused

def test_a_prior_refuses_the_graph():
    """A prior appends rows to the residual, so the graph would be
    optimising a different objective -- not a slightly different one."""
    from chisurf.core.fitting.priors import NormalPrior
    fit = make_fit()
    fit.model.parameters_all_dict["t"].prior = NormalPrior(mu=3.0, sigma=0.1)
    assert M.graph_objective(fit, fit.model) is None


def test_a_prior_actually_changes_the_answer_it_is_refused_for():
    """The guard is only worth having if the objectives really differ.

    A tight prior away from the least-squares optimum must pull the fit;
    if it did not, refusing the graph for it would be superstition.
    """
    from chisurf.core.fitting.priors import NormalPrior
    plain, with_prior = make_fit(), make_fit()
    plain.run()
    with_prior.model.parameters_all_dict["t"].prior = NormalPrior(mu=2.0,
                                                                 sigma=0.01)
    with_prior.run()
    t_plain = plain.model.parameters_all_dict["t"].value
    t_prior = with_prior.model.parameters_all_dict["t"].value
    assert abs(t_prior - t_plain) > 1e-3, (
        "the prior did not move the fit, so refusing the graph for it is "
        "guarding nothing")


def test_a_bounded_parameter_is_not_mistaken_for_a_prior():
    """Bounds synthesise a uniform prior that contributes no residual rows;
    treating that as a prior would refuse the graph for every bounded fit."""
    fit = make_fit()
    t = fit.model.parameters_all_dict["t"]
    t.bounds = (0.01, 20.0)
    t.bounds_on = True
    assert M.graph_objective(fit, fit.model) is not None


def test_an_equation_the_engine_cannot_compile_refuses_the_graph():
    fit = make_fit()
    # `eval()` reaches numpy; the expression engine does not implement every
    # name it does, and an equation it cannot compile must fall back rather
    # than be approximated.
    try:
        fit.model.func = "a*np.i0(x/t)+b"
    except Exception:
        pytest.skip("the equation is rejected before a model exists")
    built = M.graph_objective(fit, fit.model)
    assert built is None or fit.model._expression is not None


def test_a_non_parse_model_refuses_the_graph():
    class NotAParseModel:
        parameters = []
    assert M.graph_objective(make_fit(), NotAParseModel()) is None


def test_a_refused_graph_still_fits():
    """The fallback is scipy, and it is the definition of the behaviour."""
    fit = make_fit()
    run_with_scipy(fit)
    assert fit.chi2r == pytest.approx(1.0, abs=0.2)
    assert all(np.isfinite(p.error_estimate)
               for p in fit.model.parameters)


def test_the_fallback_is_the_director_and_it_still_fits():
    """A refused graph lands on bff's optimiser too, not on a second one.

    **This test used to assert the opposite**, and the reason was a
    measurement: the C++ optimiser driving a Python residual through a
    director came out at 1.54 ms against scipy's 1.33 on this fixture, so
    wrapping a Python callback in a C++ loop looked like it bought nothing
    over wrapping it in a Fortran one. Re-measured on the current build it is
    **1.11x** -- still slower, by a few per cent rather than a fifth -- and
    at that size the argument the other way wins on its own terms: ChiSurf
    carried a 794-line second implementation of the same bounded
    Levenberg-Marquardt, and a plugin carried a third, and two
    implementations of one algorithm disagree rather than average. They are
    deleted; the reference survives as
    `imp.bff/test/minimizer/reference_leastsqbound.py`, imported by nothing
    and used only to assert the port is still 1:1.

    So what is checked is that the refusal still *fits*: the answer a refused
    model gets must be the answer it got before.
    """
    graph_fit, refused = make_fit(), make_fit()
    graph_fit.run()

    seen = {}
    original = M.director_objective

    def spy(*a, **kw):
        seen["called"] = True
        return original(*a, **kw)

    M.director_objective = spy
    graph = M.graph_objective
    M.graph_objective = lambda *a, **k: None
    try:
        refused.run()
    finally:
        M.director_objective = original
        M.graph_objective = graph
    assert seen.get("called"), "a refused graph did not fall back to the director"

    a = np.array([p.value for p in refused.model.parameters], dtype=float)
    b = np.array([p.value for p in graph_fit.model.parameters], dtype=float)
    np.testing.assert_allclose(a, b, rtol=1e-6)
    assert refused.chi2r == pytest.approx(graph_fit.chi2r, rel=1e-9)


def test_a_refused_graph_still_gets_a_covariance_without_numpy():
    """The director path is a graph too, so the error bars come off it.

    Before the fallback was bff's, a refused model paid twice: once for the
    fit in scipy, and again for `covariance_matrix` to rebuild a Jacobian
    through `Model.update()`. Now the same `Minimizer` that fitted it
    differences it, so `update_error_estimates` finds a covariance waiting
    and evaluates the Python model no more times than a graph fit does.
    """
    fit = make_fit()
    original = F.Fit._optimiser_covariance
    seen = {}

    def spy(self):
        cov, used = original(self)
        seen["offered"] = cov is not None
        return cov, used

    F.Fit._optimiser_covariance = spy
    graph = M.graph_objective
    M.graph_objective = lambda *a, **k: None
    try:
        fit.run()
    finally:
        F.Fit._optimiser_covariance = original
        M.graph_objective = graph
    assert seen.get("offered"), "a refused graph fell back to numpy for its errors"
    assert np.all(np.isfinite(
        [p.error_estimate for p in fit.model.parameters]))


def test_a_parameter_linked_inside_one_model_follows_its_master():
    """A link does not need two datasets to exist, and used to be dropped.

    A free parameter is one that is not fixed, not redundant and **not
    linked**, so a linked parameter gets no port of the optimiser's. The
    graph used to leave it a constant at its start value while the numpy path
    had it follow its master -- a different objective, silently. It is now a
    ``Port`` link, the same relation one level down.
    """
    def build():
        fit = make_fit()
        # The offset *is* the amplitude: one number, twice in the equation.
        fit.model.parameters_all_dict["b"].link = \
            fit.model.parameters_all_dict["a"]
        fit.model.find_parameters()
        return fit

    graph, scipy = build(), build()
    assert [p.name for p in graph.model.parameters] == ["a", "t"]
    graph.run()
    run_with_scipy(scipy)
    for name in ("a", "t", "b"):
        assert (graph.model.parameters_all_dict[name].value
                == pytest.approx(scipy.model.parameters_all_dict[name].value,
                                 rel=1e-4))
    assert (graph.model.parameters_all_dict["b"].value
            == graph.model.parameters_all_dict["a"].value)


# ------------------------------------------------------------- the group

def make_group(n_members=2, lifetimes=(3.1, 3.1), amplitudes=(2.0, 3.0),
               shared=True, sigma=0.02, seed=7, equation="a*exp(-x/t)"):
    """A `FitGroup` of decays, optionally sharing one lifetime.

    The sharing is the ordinary ChiSurf one -- each follower's
    :attr:`Parameter.link` points at the first member's copy -- which is a
    port link underneath, and therefore the same relation the graph builds.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0.1, 20.0, N)
    curves = []
    for k in range(n_members):
        y = amplitudes[k] * np.exp(-x / lifetimes[k]) + rng.normal(0, sigma, N)
        curves.append(cs.core.data.DataCurve(x=x, y=y, ey=np.full(N, sigma)))
    group = F.FitGroup(data=cs.core.data.DataGroup(curves),
                       model_class=ParseModel)
    for member in group:
        member.model.func = equation
        member.xmin, member.xmax = 0, N - 1
        member.model.find_parameters()
    if shared and n_members > 1:
        master = group[0].model.parameters_all_dict["t"]
        for member in list(group)[1:]:
            member.model.parameters_all_dict["t"].link = master
        for member in group:
            member.model.find_parameters()
    group._model.find_parameters()
    for member in group:
        for name in ("a", "t"):
            member.model.parameters_all_dict[name].value = 1.0
    return group


def run_group_with_scipy(group):
    """Run *group* with the graph refused, i.e. down the numpy path."""
    original = M.graph_objective
    M.graph_objective = lambda *a, **k: None
    try:
        group.run(local_first=False)
    finally:
        M.graph_objective = original
    return group


def test_the_graph_is_taken_for_a_group():
    group = make_group()
    assert M.graph_objective(group, group._model) is not None


def test_the_group_answer_does_not_move():
    """A group is what the GUI builds, so this is the case that matters."""
    graph, scipy = make_group(), make_group()
    graph.run(local_first=False)
    run_group_with_scipy(scipy)
    np.testing.assert_allclose(
        [p.value for p in graph._model.parameters],
        [p.value for p in scipy._model.parameters], rtol=1e-5)
    assert graph.chi2r == pytest.approx(scipy.chi2r, rel=1e-6)


def test_the_group_error_estimates_do_not_move():
    graph, scipy = make_group(), make_group()
    graph.run(local_first=False)
    run_group_with_scipy(scipy)
    a = np.array([p.error_estimate for p in graph.model.parameters], dtype=float)
    b = np.array([p.error_estimate for p in scipy.model.parameters], dtype=float)
    assert np.all(np.isfinite(a))
    np.testing.assert_allclose(a, b, rtol=5e-3)


def test_a_one_member_group_agrees_with_the_numpy_path():
    graph = make_group(n_members=1, shared=False)
    scipy = make_group(n_members=1, shared=False)
    graph.run(local_first=False)
    run_group_with_scipy(scipy)
    np.testing.assert_allclose(
        [p.value for p in graph._model.parameters],
        [p.value for p in scipy._model.parameters], rtol=1e-5)


def test_the_group_is_not_two_separate_fits():
    """The point of a global fit, stated as a test.

    Give the two datasets *different* true lifetimes. Fitted separately each
    recovers its own; fitted together the shared parameter has to land
    between them, at the compromise both datasets force. A group that
    quietly optimised its members one at a time would report one of the two
    and pass every other test here.

    Mirrors ``test_the_group_is_not_two_separate_fits`` in imp.bff's
    ``test/minimizer/test_joint.py``, which makes the same claim about the
    C++ underneath.
    """
    alone = make_group(lifetimes=(2.6, 3.4), shared=False)
    alone.run(local_first=False)
    t1 = alone[0].model.parameters_all_dict["t"].value
    t2 = alone[1].model.parameters_all_dict["t"].value
    assert t1 == pytest.approx(2.6, abs=0.05)
    assert t2 == pytest.approx(3.4, abs=0.05)

    group = make_group(lifetimes=(2.6, 3.4), shared=True)
    group.run(local_first=False)
    t = group[0].model.parameters_all_dict["t"].value
    assert min(t1, t2) + 1e-3 < t < max(t1, t2) - 1e-3


def test_a_shared_parameter_is_one_number_after_the_run():
    """The follower is not fitted separately and then made to agree."""
    group = make_group(lifetimes=(2.6, 3.4))
    group.run(local_first=False)
    values = [m.model.parameters_all_dict["t"].value for m in group]
    assert values[0] == values[1]
    # And it is not in the free vector twice.
    assert len(group._model.parameters) == 3


def test_the_member_curves_are_the_fitted_ones():
    """The graph is private, so every member's answer has to be published."""
    group = make_group()
    group.run(local_first=False)
    for member in group:
        p = member.model.parameters_all_dict
        x = np.asarray(member.data.x, dtype=float)
        expected = p["a"].value * np.exp(-x / p["t"].value)
        np.testing.assert_allclose(np.asarray(member.model.y, dtype=float),
                                   expected, rtol=1e-10)


def test_a_group_with_a_global_parameter_fits_it():
    """A global parameter appears in no equation; members reach it by link.

    In the graph it is a port of its own that the optimiser writes and every
    follower follows -- there is nothing else for it to be.
    """
    group = make_group(lifetimes=(2.6, 3.4), shared=False)
    shared = cs.core.fitting.parameter.FittingParameter(
        name="t_global", value=1.0)
    group._model.append_global_parameter(shared)
    for member in group:
        member.model.parameters_all_dict["t"].link = shared
        member.model.find_parameters()
    group._model.find_parameters()
    assert [p.name for p in group._model.parameters] == ["a", "a", "t_global"]

    group.run(local_first=False)
    t = shared.value
    assert 2.6 < t < 3.4
    for member in group:
        assert member.model.parameters_all_dict["t"].value == pytest.approx(t)


# ----------------------------------------------- what a group refuses

def test_a_group_is_refused_whole_when_one_member_cannot_be_built():
    """Half a group in C++ is not a thing `JointChiSquared` can express.

    It has one objective; a member left in Python would cross the boundary
    once per iteration, which measured *slower* than not moving at all.
    """
    group = make_group()
    group[1].model.func = "a*exp(-x/t)"
    # Make the second member's equation one the engine will not compile by
    # removing its expression, the way a non-parse model presents itself.
    group[1].model._expression = None
    assert M.graph_objective(group, group._model) is None


def test_a_masked_member_refuses_the_group():
    """`GlobalFitModel.weighted_residuals` concatenates its members
    *unmasked*, so a graph that honoured the masks would be optimising a
    different objective than the numpy path it replaces."""
    group = make_group()
    group[0].mask = np.ones(N, dtype=float)
    assert M.graph_objective(group, group._model) is None


def test_a_prior_refuses_the_group():
    from chisurf.core.fitting.priors import NormalPrior
    group = make_group()
    group[0].model.parameters_all_dict["a"].prior = NormalPrior(mu=2.0,
                                                               sigma=0.1)
    assert M.graph_objective(group, group._model) is None


def test_an_empty_group_refuses_the_graph():
    group = make_group()
    group._model.clear_local_fits()
    assert M.graph_objective(group, group._model) is None


def test_a_refused_group_still_fits():
    group = make_group()
    run_group_with_scipy(group)
    assert group.chi2r == pytest.approx(1.0, abs=0.3)


# ------------------------------------------------- the graph is built once

def test_the_graph_is_not_rebuilt_for_every_curvature():
    """Six consumers ask for a curvature; the graph is built for one of them.

    Building it constructs every node **and copies `x`/`y`/`ey` into
    `ChiSquared` again** -- measured at 70% of a TCSPC `covariance_matrix()`
    call and 53% of a FRET one. That is the half of the standing rule that
    gets forgotten: the arithmetic being in C++ does not help if the arrays
    are marshalled across to drive it, and here they were marshalled once per
    *consumer*.
    """
    fit = make_fit()
    fit.run()
    builds = {"n": 0}
    original = M.graph_objective

    def counting(*a, **kw):
        builds["n"] += 1
        return original(*a, **kw)

    M.graph_objective = counting
    try:
        first = F.covariance_matrix(fit)[0]
        after_first = builds["n"]
        for _ in range(4):
            F.covariance_matrix(fit)
        again = F.covariance_matrix(fit)[0]
    finally:
        M.graph_objective = original

    assert after_first == 1, "the first call must build one graph"
    assert builds["n"] == 1, (
        "the graph was rebuilt %d times for six curvature calls" % builds["n"])
    # A cache that returns a *different* answer is worse than no cache.
    np.testing.assert_allclose(again, first, rtol=0, atol=0)


def test_a_rerun_does_not_reuse_the_previous_graph():
    """`run()` drops it, because the fit it described is over.

    The cache is keyed on structure and window, not on the contents of the
    data -- so the guard against a stale graph outliving its data is that a
    new run starts without one.
    """
    fit = make_fit()
    fit.run()
    F.covariance_matrix(fit)
    assert "_graph_cache" in fit.__dict__
    fit.run()
    assert "_graph_cache" not in fit.__dict__, (
        "a graph cached for the previous run survived into this one")
