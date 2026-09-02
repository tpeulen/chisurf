"""A FRET decay on the bff graph, against the one in numpy.

The third model family to leave Python, and the one that shows what the
arrangement was for. A FRET decay is not a new *kind* of fit -- it is the
same instrument, the same nuisances and the same misfit as a lifetime decay,
with a producer in front of it:

    GaussianDistances -> FretSpectrum -> [AnisotropySpectrum] -> TcspcDecay

Each link is a spectrum transform, because that is what the physics is: a
distance is a transfer rate, rates add, so a quenched species is still an
exponential. Nothing downstream of a link has to know the link happened, and
nothing in the chain returns to the interpreter.

What is checked here is what makes the speed allowed -- the same curve, the
same minimum, the same error estimates -- plus the refusal discipline, which
matters more in this family than in any other: `FRETModel` has eight
subclasses and each *is* a distance distribution. A subclass whose
distribution has no node must fall back, not be quietly fitted with the base
model's constant distance.
"""
import numpy as np
import pytest

import chisurf as cs
import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as F
import chisurf.core.fitting.minimizer as M
from chisurf.core.models.tcspc.fret import (
    FRETModel,
    FRETrateModel,
    GaussianModel,
    SawNuModel,
    SingleDistanceModel,
    WormLikeChainModel,
)

pytestmark = pytest.mark.skipif(
    not M.have_minimizer() or not hasattr(M._bff, "FretSpectrum"),
    reason="IMP.bff carries no FretSpectrum")

N = 512
DT = 0.032
REP_RATE = 80.0


def instrument(model, x, irf):
    model.convolve._irf = chisurf.core.curve.Curve(x=x, y=irf.copy())
    model.convolve.dt = DT
    model.convolve.rep_rate = REP_RATE
    model.convolve.stop = N * DT


def make_fit(model_class=GaussianModel, polarization="vm", distance=45.0,
             sigma=6.0, donor_lifetime=4.0, x_donly=0.2, seed=17):
    """A FRET fit whose data come from the FRET model itself.

    Generated rather than reused from a lifetime fixture, and with the donor
    lifetime and the distribution width **fixed**, for a reason worth stating
    once: a Gaussian distance distribution fitted against an unconstrained
    donor lifetime is nearly unidentifiable -- both make the decay faster,
    and the fit reports standard deviations in the thousands. Two optimisers
    on such a surface stop at different points while evaluating the identical
    objective, so a parity test there measures conditioning rather than
    correctness. The objective itself is pinned to machine precision by
    :func:`test_the_curve_is_the_same_curve`, which needs no fit at all.
    """
    x = np.arange(N) * DT
    irf = 1000.0 * np.exp(-0.5 * ((x - 1.0) / 0.08) ** 2)
    blank = np.ones(N)
    data = chisurf.core.data.DataCurve(x=x, y=blank, ey=np.ones(N))
    fit = F.Fit(model_class=model_class, data=data)
    fit.xmin, fit.xmax = 0, N
    model = fit.model
    instrument(model, x, irf)

    model.anisotropy.polarization_type = polarization
    if polarization != "vm":
        model.anisotropy.add_rotation(b=0.2, rho=2.0)
        # Redundant against `r0`, which is what normalises them.
        for parameter in model.anisotropy._bs:
            parameter.fixed = True
        model.anisotropy._g.value = 1.3

    model.fret_parameters.xDOnly = x_donly
    model.lifetimes._lifetimes[0].value = donor_lifetime
    model.lifetimes._lifetimes[0].fixed = True
    if hasattr(model, "gaussians"):
        model.gaussians._gaussianMeans[0].value = distance
        model.gaussians._gaussianSigma[0].value = sigma
        model.gaussians._gaussianSigma[0].fixed = True
        # The weights are normalised to sum to one, so a single component's
        # weight is redundant *by construction* -- a flat direction, on which
        # two optimisers stop wherever their step tolerance puts them.
        for parameter in model.gaussians._gaussianAmplitudes:
            parameter.fixed = True
    model.find_parameters()

    # The data: Poisson counts from this very model, so the distance the fit
    # is asked to recover is genuinely in them.
    model.update_model()
    clean = np.maximum(np.asarray(model.y, dtype=float), 1e-9)
    counts = np.random.default_rng(seed).poisson(clean).astype(float)
    fit.data.y = counts
    fit.data.ey = np.sqrt(np.maximum(counts, 1.0))
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


def _refuses(fit):
    return M.graph_objective(fit, fit.model) is None


# ------------------------------------------------------- the same objective

@pytest.mark.parametrize("model_class", [FRETModel, GaussianModel])
@pytest.mark.parametrize("polarization", ["vm", "vv", "vh"])
@pytest.mark.parametrize("x_donly", [0.0, 0.25])
def test_the_curve_is_the_same_curve(model_class, polarization, x_donly):
    """Before any fitting, and to machine precision.

    This is the test the family stands on. Every link in the chain is an
    arithmetic identity -- a Cartesian product of two spectra, a rate from a
    distance, a mixture of quenched and unquenched species -- and each has an
    ordering and a length that no chi-square would report if they were wrong.
    A relative tolerance of 1e-10 is not generosity; it is what says the two
    are the same arithmetic rather than two arithmetics that happen to fit.
    """
    fit = make_fit(model_class, polarization=polarization, x_donly=x_donly)
    fit.model.update_model()
    built = M.graph_objective(fit, fit.model)
    assert built is not None, f"{model_class.__name__} no longer builds a graph"
    node = built[0]._decay
    node.update()
    graph = np.asarray(node.get_output_port("decay").value, dtype=float)
    python = np.asarray(fit.model.y, dtype=float)
    np.testing.assert_allclose(graph, python, rtol=1e-10, atol=1e-10)


def test_the_donor_only_fraction_is_a_mixture_and_reaches_the_curve():
    """`xDOnly` is fitted, so a graph that dropped it would still converge.

    The failure this guards is a builder that never wires the port: every
    curve then comes back at `xDOnly = 0`, the parameter sits wherever it
    started, and the fit reports a donor-only fraction it never used.
    """
    curves = []
    for x_donly in (0.0, 0.4):
        fit = make_fit(x_donly=x_donly)
        built = M.graph_objective(fit, fit.model)
        built[0]._decay.update()
        curves.append(np.asarray(built[0]._decay.get_curve(), dtype=float))
    assert not np.allclose(curves[0], curves[1])


def test_the_forster_radius_reaches_the_curve():
    """And so does every other constant of the FRET parameter group.

    `R0`, `tau0` and `kappa2` ship *fixed*, which is exactly why they are
    easy to leave unwired: nothing in a fit would move them, so nothing in a
    fit would notice. They still set where the transfer rate is.
    """
    curves = []
    for forster_radius in (45.0, 60.0):
        fit = make_fit()
        fit.model.fret_parameters.forster_radius = forster_radius
        built = M.graph_objective(fit, fit.model)
        built[0]._decay.update()
        curves.append(np.asarray(built[0]._decay.get_curve(), dtype=float))
    assert not np.allclose(curves[0], curves[1])


# ------------------------------------------------------------ the same fit

def test_the_answer_does_not_move():
    graph, scipy = make_fit(), make_fit()
    graph.run()
    run_with_scipy(scipy)
    a = np.array([p.value for p in graph.model.parameters], float)
    b = np.array([p.value for p in scipy.model.parameters], float)
    sigma = np.array([p.error_estimate for p in scipy.model.parameters], float)
    finite = np.isfinite(sigma) & (sigma > 0)
    np.testing.assert_array_less(np.abs(a - b)[finite], 0.05 * sigma[finite])
    assert graph.chi2r == pytest.approx(scipy.chi2r, rel=1e-5)


def test_the_distance_is_recovered():
    """A fit that agrees with a wrong fit is not worth having."""
    fit = make_fit(distance=45.0)
    fit.model.gaussians._gaussianMeans[0].value = 55.0
    fit.run()
    assert fit.model.gaussians._gaussianMeans[0].value == pytest.approx(
        45.0, abs=3.0)


def test_the_error_estimates_do_not_move():
    graph, scipy = make_fit(), make_fit()
    graph.run()
    run_with_scipy(scipy)
    a = np.array([p.error_estimate for p in graph.model.parameters], float)
    b = np.array([p.error_estimate for p in scipy.model.parameters], float)
    finite = np.isfinite(b) & (b > 0)
    np.testing.assert_allclose(a[finite], b[finite], rtol=0.05)


def test_the_offered_covariance_is_the_finite_difference_one():
    """The C++ matrix is `covariance_matrix`'s own -- including what it drops.

    The columns matter more here than the numbers. `E_FRET` is free and
    neither optimiser can move it, so its partial derivative is exactly zero
    and both paths must *drop* it rather than invert a singular ``J'J``. If
    the C++ routine inverted instead, every FRET fit would come back with
    plausible-looking garbage, and comparing only the surviving standard
    deviations would not say so -- which is why the kept indices are asserted
    first.
    """
    from test.fitting.test_graph_fit import covariance_the_graph_offered
    fit = make_fit()
    (cpp, used), (numpy_cov, numpy_used) = covariance_the_graph_offered(fit)
    assert used == numpy_used
    assert len(used) < len(fit.model.parameters), (
        "no parameter was dropped, so this fixture no longer exercises the "
        "zero-column case E_FRET is here for")
    np.testing.assert_allclose(np.sqrt(np.diag(cpp)),
                               np.sqrt(np.diag(numpy_cov)), rtol=1e-5)


def test_the_derived_efficiency_is_offered_a_slot_and_moves_in_neither_path():
    """`E_FRET` is free, and neither optimiser can write it.

    Its value comes from a callable and its setter is ignored, so a write is
    a no-op in the numpy path *and* in the graph -- where its port is
    deliberately wired to nothing. Both therefore see a column of zeros and
    agree. It is stated here because the alternative reading -- that the
    graph is quietly ignoring a fitted parameter -- is the one someone will
    have when they find that port.
    """
    fit = make_fit()
    efficiency = fit.model.fret_parameters._fret_efficiency
    assert efficiency in fit.model.parameters, (
        "E_FRET no longer ships free; the dangling port can go")
    before = float(efficiency.value)
    efficiency.value = before + 0.3
    assert float(efficiency.value) == pytest.approx(before)


# ------------------------------------------------------------ what refuses

@pytest.mark.parametrize("model_class", [
    SingleDistanceModel, FRETrateModel])
def test_a_subclass_without_a_distribution_node_refuses(model_class):
    """Each `FRETModel` subclass *is* a distance distribution.

    A discrete set of distances (histogrammed, which is the part to
    reproduce exactly) and a rate spectrum given outright (which skips the
    distance-to-rate step) still have no producer. Until one has a node, the
    honest answer is the numpy path: fitting it with the base model's single
    constant distance would converge, and would be a different model.
    """
    fit = make_fit(model_class)
    assert _refuses(fit)


@pytest.mark.parametrize("model_class", [
    WormLikeChainModel, SawNuModel])
def test_a_polymer_distribution_is_a_node_with_the_same_curve(model_class):
    """The closed-form polymer models joined the graph (T-20260901-08).

    `PolymerDistances` dispatches into the same `PolymerChain` kernels the
    rdf.py forwarders call, so the node's curve and `update_model`'s must be
    the same numbers -- including the worm-like chain's `distance = false`
    contract (the flag chisurf has always dropped on the floor; honouring
    it in the node moved the curve by half a count and the census caught
    it before anything shipped).
    """
    fit = make_fit(model_class)
    fit.model.update_model()
    built = M.graph_objective(fit, fit.model)
    assert built is not None, "the polymer model must build a graph"
    node = built[0]._decay
    node.update()
    graph = np.asarray(node.get_output_port("decay").value, dtype=float)
    python = np.array(fit.model.y, dtype=float)
    np.testing.assert_allclose(graph, python, rtol=1e-8)


def test_a_kappa_squared_spectrum_refuses_the_graph():
    """Slow orientational averaging convolves before the rates are formed."""
    fit = make_fit()
    fit.model.orientation_parameter.mode = "slow"
    assert _refuses(fit)


def test_binning_the_lifetime_spectrum_refuses_the_graph():
    """Coarse-graining is a step of the model, not a display choice."""
    import chisurf.core.settings
    settings = chisurf.core.settings.cs_settings["fret"]
    original = settings["bin_lifetime"]
    settings["bin_lifetime"] = True
    try:
        assert _refuses(make_fit())
    finally:
        settings["bin_lifetime"] = original


def test_a_distance_between_gaussians_builds_the_graph():
    """It is a different probability density -- and the node carries it now.

    This test asserted a *refusal* until 2026-09-02: the two-cloud form is a
    different density from the generalised normal, not a reparameterisation of
    it, and `GaussianDistances` only had the latter. It has both since, sharing
    one kernel with `Gaussians.distribution`, so what needs pinning is no
    longer that the builder declines but that the graph it builds is the same
    curve the model reports.
    """
    fit = make_fit()
    fit.model.gaussians.is_distance_between_gaussians = True
    assert not _refuses(fit)

    built = M.graph_objective(fit, fit.model)
    assert built is not None
    decay = getattr(built[0], "_decay", None)
    assert decay is not None
    fit.model.update_model()
    decay.update()
    graph = np.asarray(decay.get_curve(), dtype=float)
    python = np.asarray(fit.model.y, dtype=float)
    n = min(graph.size, python.size)
    scale = max(1.0, float(np.max(np.abs(python[:n]))))
    assert np.max(np.abs(graph[:n] - python[:n])) / scale < 1e-8


def test_a_refused_model_still_fits():
    fit = make_fit(SingleDistanceModel)
    fit.run()
    assert np.all(np.isfinite(np.asarray(fit.model.y, dtype=float)))


# ------------------------------------------- the species that are not worth it

def test_pruning_negligible_species_does_not_move_the_curve():
    """The graph asks the node to skip species double precision cannot see.

    A reconvolution is one serial recursion over every channel *per species*,
    so it is linear in the species count -- and a distribution-derived
    spectrum has as many species as the distribution has bins, whatever their
    weight. `M.AMPLITUDE_THRESHOLD` is what the graph asks for.

    The tolerance here is the point: `1e-12` relative on a curve peaking near
    a thousand counts is far below the round-off of summing the same species
    in a different order. If this ever needs loosening, the threshold has
    stopped being free and has become a trade.
    """
    fit = make_fit()
    built = M.graph_objective(fit, fit.model)
    node = built[0]._decay
    node.update()
    pruned = np.asarray(node.get_curve(), dtype=float).copy()
    active = node.get_number_of_active_lifetimes()

    node.set_amplitude_threshold(0.0)
    node.update()
    exact = np.asarray(node.get_curve(), dtype=float)

    assert active < node.get_number_of_active_lifetimes(), (
        "nothing was pruned; this fixture no longer exercises the threshold")
    scale = max(1.0, float(np.abs(exact).max()))
    assert np.max(np.abs(pruned - exact)) / scale < 1e-12


def test_the_threshold_the_graph_asks_for_is_the_documented_one():
    """Stated as a fact about the built graph, not about a constant.

    A default changed in one place and not the other is exactly how a model
    ends up quietly approximated, and the table in the module docstring is
    only meaningful for the value actually used.
    """
    fit = make_fit()
    built = M.graph_objective(fit, fit.model)
    assert built[0]._decay.get_amplitude_threshold() == M.AMPLITUDE_THRESHOLD
    assert M.AMPLITUDE_THRESHOLD <= 1e-14, (
        "a looser threshold is a trade of accuracy for speed, and the tests "
        "above pin it as being free")


def test_a_plain_lifetime_model_keeps_every_species():
    """The threshold must be inert where there is nothing to prune.

    A multi-exponential has one species per fitted lifetime and they all
    carry weight; a threshold that removed one of those would be dropping a
    fitted parameter's entire contribution.
    """
    from test.fitting.test_graph_fit_tcspc import make_fit as make_lifetime_fit
    fit = make_lifetime_fit()
    built = M.graph_objective(fit, fit.model)
    node = built[0]._decay
    node.update()
    assert node.get_number_of_active_lifetimes() == \
        node.get_number_of_lifetimes()
