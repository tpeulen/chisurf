"""Structure of a fit's posterior as a factor graph (PRD-68, phase 2).

A global fit's posterior factorises over its datasets, but the fitting engine
represented it as one dense parameter vector and recomputed every local model on
every evaluation. These tests pin the graph that makes the factorisation
explicit: which datasets a parameter touches (relevance), how the fit decomposes
into blocks and separators, and what its treewidth is.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting import factorgraph
from chisurf.core.fitting.factorgraph import (
    LIKELIHOOD,
    PRIOR,
    build_factor_graph,
    posterior_model,
)
from chisurf.core.fitting.priors import NormalPrior

SIGMA = 0.05
N_POINTS = 32


def _global_fit(n_datasets: int = 4, seed: int = 0):
    """Return a converged global fit of ``c + a*x**2`` over several datasets.

    Parameters
    ----------
    n_datasets : int, optional
        Number of local fits in the group.
    seed : int, optional
        Seed of the random-number generator used to draw the noise.

    Returns
    -------
    chisurf.core.fitting.fit.FitGroup
        The group, with parameters discovered but not yet optimised.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, N_POINTS)
    curves = []
    for k in range(n_datasets):
        y = 3.1 + (1.0 + 0.1 * k) * x ** 2 + rng.normal(0.0, SIGMA, x.size)
        curves.append(
            chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * SIGMA)
        )
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for f in fit:
        f.fit_range = 0, len(f.model.y)
        f.model.func = 'c+a*x**2'
        f.model.find_parameters()
    fit._model.find_parameters()
    return fit


def _link_across(fit, name: str = 'a'):
    """Link the named parameter of every local fit to the first fit's copy."""
    master = [p for p in fit[0].model.parameters_all if p.name == name][0]
    for local in list(fit)[1:]:
        target = [p for p in local.model.parameters_all if p.name == name][0]
        target.link = master
    for local in fit:
        local.model.find_parameters()
    fit._model.find_parameters()
    return master


def _named(graph, keys):
    """Map variable keys to their display names."""
    return tuple(graph.variables[k].name for k in keys)


def test_posterior_model_is_the_global_model_not_the_selected_one():
    """``FitGroup.model`` is the selected local model; the graph needs the global."""
    fit = _global_fit(3)
    assert posterior_model(fit) is fit._model
    assert posterior_model(fit) is not fit.model
    assert len(posterior_model(fit).parameters) == 6


def test_unlinked_group_decomposes_into_independent_datasets():
    """Without links each dataset is its own component and its own block."""
    fit = _global_fit(4)
    g = build_factor_graph(fit)

    assert len(g) == 8
    assert len(g.likelihood_factors()) == 4
    assert len(g.connected_components()) == 4
    # Each clique is one dataset's (c, a): treewidth 1 whatever the dataset count.
    assert g.treewidth == 1
    assert sorted(len(b) for b in g.blocks()) == [2, 2, 2, 2]
    # Nothing is shared, so the junction forest has no separator.
    assert [s for s in g.separators() if s] == []


def test_linking_a_parameter_creates_a_star_with_one_separator():
    """A shared parameter couples the datasets through a single separator."""
    fit = _global_fit(4)
    _link_across(fit, 'a')
    g = build_factor_graph(fit)

    # The three linked copies are no longer free.
    assert len(g) == 5
    assert len(g.connected_components()) == 1

    seps = [s for s in g.separators() if s]
    assert len(seps) == 1
    assert _named(g, seps[0]) == ('1:a',)

    # Every block is one dataset's local parameter plus the shared one.
    blocks = g.blocks()
    assert len(blocks) == 4
    for b in blocks:
        names = set(_named(g, b))
        assert '1:a' in names
        assert len(names) == 2
    # A star stays cheap however many datasets hang off it.
    assert g.treewidth == 1


def test_relevance_maps_parameters_to_the_datasets_they_touch():
    """A local parameter must reach one dataset, a shared one must reach all."""
    fit = _global_fit(4)
    _link_across(fit, 'a')
    g = build_factor_graph(fit)

    shared = [v for v in g.variables.values() if v.name == '1:a'][0]
    assert g.affected_fits_from_indices([shared.index]) == [0, 1, 2, 3]

    for v in g.variables.values():
        if v.name == '1:a':
            continue
        # '2:c' belongs to local fit index 1, and so on.
        expected = int(v.name.split(':')[0]) - 1
        assert g.affected_fits_from_indices([v.index]) == [expected]


def test_relevance_of_an_unlinked_group_is_one_dataset_each():
    """Every parameter of an unlinked group touches exactly its own dataset."""
    fit = _global_fit(3)
    g = build_factor_graph(fit)
    for v in g.variables.values():
        expected = int(v.name.split(':')[0]) - 1
        assert g.affected_fits_from_indices([v.index]) == [expected]
    # And the union of all of them is every dataset.
    all_idx = [v.index for v in g.variables.values()]
    assert g.affected_fits_from_indices(all_idx) == [0, 1, 2]


def test_fixed_parameters_leave_the_graph():
    """Fixing a parameter removes it as a variable but keeps the dataset."""
    fit = _global_fit(2)
    p = [q for q in fit[0].model.parameters_all if q.name == 'c'][0]
    p.fixed = True
    for local in fit:
        local.model.find_parameters()
    fit._model.find_parameters()

    g = build_factor_graph(fit)
    assert len(g) == 3
    assert '1:c' not in {v.name for v in g.variables.values()}
    # The dataset still has a likelihood factor, now over one variable.
    like = [f for f in g.likelihood_factors() if f.fit_index == 0][0]
    assert len(like.scope) == 1


def test_informative_priors_become_factors_but_bounds_do_not():
    """A bare box is a support constraint; only a real prior adds a factor."""
    fit = _global_fit(2)

    g_plain = build_factor_graph(fit)
    assert [f for f in g_plain.factors.values() if f.kind == PRIOR] == []

    p = [q for q in fit[0].model.parameters_all if q.name == 'c'][0]
    p.prior = NormalPrior(mu=3.1, sigma=0.1)
    g_prior = build_factor_graph(fit)
    priors = [f for f in g_prior.factors.values() if f.kind == PRIOR]
    assert len(priors) == 1
    assert len(priors[0].scope) == 1
    assert g_prior.variables[priors[0].scope[0]].name == '1:c'
    # A prior is a unary factor: it constrains but does not couple, so it must
    # not change which datasets a parameter reaches.
    assert g_prior.affected_fits(priors[0].scope) == [0]


def test_likelihood_factor_size_is_the_dataset_length():
    """Factor ``size`` must report the residual count it contributes."""
    fit = _global_fit(3)
    g = build_factor_graph(fit)
    for f in g.likelihood_factors():
        assert f.kind == LIKELIHOOD
        assert f.size == fit[f.fit_index].model.n_points


def _single_fit(seed: int = 1):
    """Return a single-dataset fit of ``c + a*x**2``.

    One likelihood over every free parameter, i.e. a complete Markov graph —
    the shape the structural queries are slowest on.

    Parameters
    ----------
    seed : int, optional
        Seed of the random-number generator used to draw the noise.

    Returns
    -------
    chisurf.core.fitting.fit.Fit
        The fit, with parameters discovered but not yet optimised.
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, N_POINTS)
    y = 3.1 + 1.2 * x ** 2 + rng.normal(0.0, SIGMA, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) * SIGMA)
    fit = chisurf.core.fitting.fit.Fit(
        data=data, model_class=chisurf.core.models.parse.ParseModel
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()
    return fit


def test_single_fit_is_one_clique():
    """A single dataset has no dataset-level structure, and says so."""
    g = build_factor_graph(_single_fit())
    assert len(g.likelihood_factors()) == 1
    assert g.treewidth == len(g) - 1
    assert len(g.blocks()) == 1


def test_elimination_orders_are_deterministic_and_validated():
    """Both heuristics must be reproducible; an unknown one must be refused."""
    fit = _global_fit(4)
    _link_across(fit, 'a')
    g = build_factor_graph(fit)

    assert g.elimination_order() == g.elimination_order()
    assert sorted(g.elimination_order('min_degree')) == sorted(g.variables)
    with pytest.raises(ValueError):
        g.elimination_order('cheapest')


def test_junction_tree_edges_carry_their_separator():
    """Every clique-tree edge must expose the variables its cliques share."""
    fit = _global_fit(3)
    _link_across(fit, 'a')
    g = build_factor_graph(fit)
    tree = g.junction_tree()

    assert tree.number_of_nodes() == 3
    assert tree.number_of_edges() == 2
    for a, b, data in tree.edges(data=True):
        sep = data['separator']
        assert set(sep) == set(a) & set(b)
        assert _named(g, sep) == ('1:a',)


def test_structure_version_invalidates_a_cached_graph():
    """The counter must move whenever the graph's shape could have changed."""
    before = factorgraph.structure_version()
    after = factorgraph.bump_structure_version()
    assert after != before
    assert factorgraph.structure_version() == after

    fit = _global_fit(2)
    g = build_factor_graph(fit)
    assert g.version == factorgraph.structure_version()
    factorgraph.bump_structure_version()
    assert g.version != factorgraph.structure_version()


def test_describe_reports_the_identifiability_statement():
    """The report must name the shared parameters, not just count things."""
    fit = _global_fit(3)
    _link_across(fit, 'a')
    text = build_factor_graph(fit).describe()
    assert 'treewidth' in text
    assert '1:a' in text
    assert 'components     : 1' in text


def _count_copies(monkeypatch, graph):
    """Count the moral-graph copies the greedy elimination makes.

    Parameters
    ----------
    monkeypatch : pytest.MonkeyPatch
        Fixture used to wrap the moral graph's ``copy``.
    graph : chisurf.core.fitting.factorgraph.FactorGraph
        Graph whose moral graph is instrumented.

    Returns
    -------
    list
        Appended to once per copy; only the greedy path copies.
    """
    calls = []
    moral = graph.markov_graph()
    original = moral.copy

    def counting_copy():
        calls.append(1)
        return original()

    monkeypatch.setattr(moral, 'copy', counting_copy)
    return calls


def test_structural_queries_are_computed_once_per_graph(monkeypatch):
    """The greedy elimination must not re-run for every caller that asks."""
    fit = _global_fit(3)
    _link_across(fit, 'a')
    g = build_factor_graph(fit)
    calls = _count_copies(monkeypatch, g)

    order = g.elimination_order()
    cliques = g.cliques()
    assert calls  # the first pair of calls does the work

    n_after_first = len(calls)
    assert g.elimination_order() == order
    assert g.cliques() == cliques
    assert g.treewidth == max(len(c) for c in cliques) - 1
    assert g.blocks() == cliques
    g.separators()
    repr(g)
    g.describe()
    assert len(calls) == n_after_first

    # ... but invalidating must drop them, so a mutated graph is recomputed.
    g.invalidate()
    recomputed = _count_copies(monkeypatch, g)
    assert g.elimination_order() == order
    assert recomputed


def test_cached_structures_are_handed_out_as_copies():
    """A caller that mutates a returned list must not corrupt the cache."""
    fit = _global_fit(3)
    _link_across(fit, 'a')
    g = build_factor_graph(fit)

    order = g.elimination_order()
    order.append('bogus')
    assert 'bogus' not in g.elimination_order()

    cliques = g.cliques()
    cliques.clear()
    assert g.cliques()


def test_a_complete_graph_skips_the_greedy_elimination(monkeypatch):
    """A single dataset couples everything, so there is nothing to decide."""
    g = build_factor_graph(_single_fit())
    calls = _count_copies(monkeypatch, g)

    assert g.treewidth == len(g) - 1
    assert g.cliques() == [tuple(sorted(g.variables))]
    assert g.elimination_order() == sorted(
        g.variables, key=lambda key: g.index_of(key)
    )
    assert calls == []


def test_the_complete_graph_shortcut_agrees_with_the_greedy_order():
    """The shortcut is an optimisation: it must return what the greedy does."""
    fit = _single_fit()
    fast = build_factor_graph(fit)
    slow = build_factor_graph(fit)
    slow._is_complete = lambda: False

    assert fast.elimination_order() == slow.elimination_order()
    assert fast.cliques() == slow.cliques()
    assert fast.treewidth == slow.treewidth


def test_an_empty_graph_has_no_cliques():
    """The complete-graph shortcut must not invent a clique out of nothing."""
    g = factorgraph.FactorGraph([], [])
    assert g.cliques() == []
    assert g.treewidth == 0
