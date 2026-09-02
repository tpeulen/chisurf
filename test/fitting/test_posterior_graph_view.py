"""Drawable descriptions of the posterior's structure.

A global fit's structure was reported only as text, and the questions it answers
-- which dataset constrains which parameter, whether the fit separates, which
parameters are really one measurement -- are the ones text answers worst. These
tests pin the *render data*: the layout is Qt-free and deterministic, so the
things that go wrong in a picture (colliding labels, ambiguous names, edges
drawn through nodes) are assertable here rather than only visible in a screenshot.
"""
import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.fitting.fit
import chisurf.core.models.parse
from chisurf.core.fitting import graphview as gv


def _single(seed=0, func='c+a*x+b*x**2'):
    """Return a converged single-dataset fit."""
    rng = np.random.default_rng(seed)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x ** 2 + rng.normal(0.0, 0.02, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.02))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = func
    fit.model.find_parameters()
    fit.run()
    return fit


def _group(n_datasets=3, seed=0, link=True):
    """Return a converged group of ``c + a*x**2`` fits, optionally sharing ``a``."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 5.0, 48)
    curves = [
        chisurf.core.data.DataCurve(
            x=x, y=(3.0 + 0.3 * k) + 1.2 * x ** 2 + rng.normal(0, 0.05, x.size),
            ey=np.full_like(x, 0.05))
        for k in range(n_datasets)
    ]
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup(curves),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    for f in fit:
        f.fit_range = 0, len(f.model.y)
        f.model.func = 'c+a*x**2'
        f.model.find_parameters()
    if link:
        master = [p for p in fit[0].model.parameters_all if p.name == 'a'][0]
        for f in list(fit)[1:]:
            [p for p in f.model.parameters_all if p.name == 'a'][0].link = master
    fit._model.find_parameters()
    fit.run(local_first=True)
    return fit


# -- labelling ------------------------------------------------------------

def test_labels_are_short_but_never_ambiguous():
    """Three parameters drawn as ``c`` would say the fit has one, three times."""
    labels = gv.short_labels(['1:c', '2:c', '3:c', '1:a'])
    assert labels['1:a'] == 'a', "unique short names keep the short form"
    assert len({labels['1:c'], labels['2:c'], labels['3:c']}) == 3
    assert all('c' in labels[k] for k in ('1:c', '2:c', '3:c'))


def test_every_node_label_in_a_group_is_distinct():
    """End to end, on the fit that motivates it."""
    fit = _group()
    for build in (gv.structure_view, gv.correlation_view):
        view = build(fit)
        labels = [n.label for n in view.nodes if n.kind == 'parameter']
        assert len(set(labels)) == len(labels), f"{build.__name__}: {labels}"


def test_datasets_are_numbered_like_the_parameters_that_belong_to_them():
    """The factor keys are 0-based and the parameter prefixes 1-based.

    Drawing both raw puts ``c(1)`` next to a node called ``L1`` when ``c(1)``
    belongs to ``L0`` -- an off-by-one the eye makes instantly and never
    questions, because both labels look authoritative.
    """
    fit = _group()
    view = gv.structure_view(fit)
    datasets = [n for n in view.nodes if n.kind == 'dataset']
    assert len(datasets) == 3
    assert not any(n.label.startswith('L') and n.label[1:].isdigit()
                   for n in datasets), [n.label for n in datasets]


# -- structure ------------------------------------------------------------

def test_the_structure_view_links_each_parameter_to_its_datasets():
    """A shared parameter reaches every dataset; a private one reaches one."""
    fit = _group()
    view = gv.structure_view(fit)
    by_key = {n.key: n for n in view.nodes}
    datasets = {n.key for n in view.nodes if n.kind == 'dataset'}

    degree = {}
    for e in view.edges:
        assert e.source in by_key and e.target in by_key
        degree[e.source] = degree.get(e.source, 0) + 1

    shared = [k for k, d in degree.items() if d == len(datasets)]
    private = [k for k, d in degree.items() if d == 1]
    assert len(shared) == 1, "one linked parameter"
    assert len(private) == 3, "one private parameter per dataset"
    assert by_key[shared[0]].label == 'a'


def test_no_edge_is_drawn_through_a_node():
    """The failure that makes a correct graph unreadable.

    An edge passing through an unrelated node reads as a connection that is not
    there (``a -> c(2) -> data 2`` rather than two independent constraints), and
    an edge crossing a *label* hides the name. Both are invisible to a
    construction test and obvious in the picture, so they are asserted here.
    """
    fit = _group()
    view = gv.structure_view(fit)
    positions = {n.key: (n.x, n.y) for n in view.nodes}

    for edge in view.edges:
        x0, y0 = positions[edge.source]
        x1, y1 = positions[edge.target]
        for node in view.nodes:
            if node.key in (edge.source, edge.target):
                continue
            # Distance from the node to the segment.
            px, py = node.x - x0, node.y - y0
            dx, dy = x1 - x0, y1 - y0
            length_sq = dx * dx + dy * dy
            t = 0.0 if length_sq == 0 else max(0.0, min(1.0, (px * dx + py * dy) / length_sq))
            near_x, near_y = x0 + t * dx, y0 + t * dy
            distance = float(np.hypot(node.x - near_x, node.y - near_y))
            assert distance > 0.08, (
                f"edge {edge.source}->{edge.target} passes through {node.label}"
            )


def test_a_parameter_the_model_ignores_is_reported():
    """A parameter the data says nothing about must be called out.

    The factor graph cannot see this on its own: a likelihood factor's scope is
    the model's whole parameter list, not the subset it actually depends on. The
    curvature has already discovered it, though -- that is exactly why the
    parameter has no error estimate -- so the view says so and draws it neutral
    rather than at either end of the uncertainty ramp.
    """
    fit = _single(func='c+a*x+b*x**2+0*d')
    fit.model.find_parameters()
    fit.model.update_model()
    view = gv.structure_view(fit)
    assert any('no error estimate' in n for n in view.notes), view.notes
    ignored = [n for n in view.nodes if n.label == 'd']
    assert ignored and ignored[0].value is None, "must be drawn neutral, not extreme"


def test_independent_components_are_reported():
    """Several components are several fits, and sampling them jointly is waste."""
    fit = _group(link=False)
    view = gv.structure_view(fit)
    assert any('independent components' in n for n in view.notes), view.notes


# -- correlation ----------------------------------------------------------

def test_the_correlation_view_weights_edges_by_r():
    """Edge weight is |r|, and the label carries its sign."""
    fit = _group()
    view = gv.correlation_view(fit, threshold=0.1)
    assert view.edges
    for e in view.edges:
        assert e.kind == 'correlation'
        assert 0.0 <= e.weight <= 1.0
        assert e.label.startswith(('+', '-'))
        # The label is rounded for display; it must still agree with the weight.
        assert abs(float(e.label)) == pytest.approx(e.weight, abs=0.005)


def test_a_strong_correlation_is_called_one_measurement():
    """The statement a global fit is usually really being asked for."""
    # A cubic on a short span makes the coefficients nearly degenerate.
    fit = _single(func='c+a*x+b*x**2+d*x**3')
    view = gv.correlation_view(fit)
    strong = [e for e in view.edges if e.weight >= gv.STRONG_CORRELATION]
    assert strong, [e.weight for e in view.edges]
    assert any('one measurement, not two' in n for n in view.notes), view.notes


def test_strongly_correlated_parameters_are_placed_close_together():
    """The geometry has to carry the message too, not only the edge width."""
    fit = _single(func='c+a*x+b*x**2+d*x**3')
    view = gv.correlation_view(fit, threshold=0.0)
    pos = {n.key: np.array([n.x, n.y]) for n in view.nodes}
    pairs = [(e, float(np.linalg.norm(pos[e.source] - pos[e.target])))
             for e in view.edges]
    strongest = max(pairs, key=lambda p: p[0].weight)
    weakest = min(pairs, key=lambda p: p[0].weight)
    assert strongest[1] < weakest[1], "the most correlated pair must be nearest"


def test_the_correlation_view_says_so_when_it_has_nothing():
    """Silence would read as 'no correlations', which is a different claim."""
    fit = _single()
    names, corr = gv.posterior_correlation(fit)
    assert corr is not None, "a converged fit has a curvature to use"
    # And with neither a chain nor a curvature it must not invent one.
    view = gv.correlation_view(fit, threshold=1.01)
    assert view.edges == []


def test_a_stored_chain_is_preferred_over_the_curvature():
    """A chain is the real posterior; the curvature is a quadratic guess at it."""
    fit = _single()
    names = list(fit.model.parameter_names)
    rng = np.random.default_rng(0)
    # A chain whose correlation is unmistakably not the curvature's.
    draws = rng.normal(size=(4000, len(names)))
    draws[:, 1] = draws[:, 0]
    fit.sampling_chain = {
        'parameter_names': names,
        'parameter_values': draws,
        'chains': draws[np.newaxis, :, :],
        'burn_in': 0,
    }
    got_names, corr = gv.posterior_correlation(fit)
    assert list(got_names) == names
    assert corr[0, 1] == pytest.approx(1.0, abs=1e-9)


# -- junction tree --------------------------------------------------------

def test_the_junction_tree_labels_edges_with_the_separator():
    """An edge is what has to pass between two cliques."""
    fit = _group()
    view = gv.junction_tree_view(fit)
    assert len(view.nodes) == 3
    assert view.edges
    for e in view.edges:
        assert e.kind == 'separator'
        assert e.label == 'a', "the linked parameter is what they share"
    assert any('treewidth' in n for n in view.notes)


def test_a_single_fit_still_produces_every_view():
    """The degenerate case must not need special handling by a caller."""
    fit = _single()
    for build in (gv.structure_view, gv.correlation_view, gv.junction_tree_view):
        view = build(fit)
        assert view.nodes, build.__name__
        assert view.title and view.legend


# -- layout ---------------------------------------------------------------

def test_every_node_is_laid_out_inside_the_frame():
    """A node outside the coordinate range is a node clipped out of the picture."""
    for fit in (_single(), _group()):
        for build in (gv.structure_view, gv.correlation_view,
                      gv.junction_tree_view):
            view = build(fit)
            for n in view.nodes:
                assert np.isfinite(n.x) and np.isfinite(n.y), n.label
                assert -1.001 <= n.x <= 1.001, (build.__name__, n.label, n.x)
                assert -1.001 <= n.y <= 1.001, (build.__name__, n.label, n.y)


def test_no_two_nodes_land_on_the_same_point():
    """Overlapping nodes are one node as far as the reader is concerned."""
    for fit in (_single(), _group()):
        for build in (gv.structure_view, gv.correlation_view,
                      gv.junction_tree_view):
            view = build(fit)
            points = [(round(n.x, 3), round(n.y, 3)) for n in view.nodes]
            assert len(set(points)) == len(points), (build.__name__, points)


def test_a_one_dimensional_layout_is_turned_to_lie_horizontally():
    """A chain drawn down a wide canvas wastes it and stacks the labels."""
    from chisurf.core import graph as cg
    path = cg.path_graph(6)
    pos = gv._layout(path)
    xs = np.array([p[0] for p in pos.values()])
    ys = np.array([p[1] for p in pos.values()])
    # ``ndarray.ptp()`` was removed in numpy 2; the free function works on both.
    assert np.ptp(xs) > np.ptp(ys), "the long axis must be horizontal"


def test_the_layout_is_stable_across_calls():
    """A redraw that reshuffles the picture makes it unreadable to a human."""
    fit = _group()
    first = gv.structure_view(fit)
    second = gv.structure_view(fit)
    for a, b in zip(first.nodes, second.nodes):
        assert a.key == b.key
        assert (a.x, a.y) == pytest.approx((b.x, b.y))
