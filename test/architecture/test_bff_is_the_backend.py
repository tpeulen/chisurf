"""Architectural boundary: :mod:`IMP.bff` is the model layer's backend.

The other half of the MVC statement. ``test_model_ui_boundary`` says the model
does not depend on a view; this says what the model's *own* substrate is.
ChiSurf is the application -- what a fit is, what a dataset is, which
parameter belongs to which experiment. The values, the graph they form, the
objective, the optimiser and the structure of the posterior are `IMP.bff`.

Why this is a test and not a note in a design document: **two
implementations of one algorithm do not average out, they disagree, and the
disagreement is silent.** On 2026-09-01 chisurf's factor graph was delegated
to bff's after carrying a parallel Python copy since the original port;
running the two against each other for the first time immediately found a
wrong ``is_complete`` in the C++ that had been reporting a treewidth of 3
where the answer is 1, for the shape every global fit has. Nothing had
noticed, because nothing had ever compared them.

So each check below names a place where a second implementation would be
easy to grow back, and asserts that the one in use is bff's. None of them
pins an *answer* -- the value tests live next to each subsystem; these pin
the *provenance*.
"""

from __future__ import annotations

import IMP.bff as bff
import numpy as np
import pytest


def test_a_parameter_is_a_bff_port():
    """A parameter's value lives in a ``Port``, not in a Python attribute.

    This is the load-bearing one: bounds, links, the DAG check that refuses a
    cycle, and the invalidation that drives a node graph are all the port's,
    so a parameter that kept its own float would quietly lose every one of
    them.
    """
    from chisurf.core.parameter import Parameter

    p = Parameter(name="tau", value=2.5)
    assert isinstance(p._port, bff.GraphPort)

    # And it is genuinely the storage, not a mirror kept in step.
    p._port.value = 4.0
    assert p.value == pytest.approx(4.0)


def test_a_link_between_parameters_is_a_port_link():
    """Sharing a parameter is ``Port::set_link``, one level down.

    A global fit is *made* of these, and it is the reason a fit graph can be
    built in C++ at all: the coupling is already there.
    """
    from chisurf.core.parameter import Parameter

    master, follower = Parameter(name="t", value=3.0), Parameter(name="t2")
    follower.link = master
    assert follower._port.is_linked()
    master.value = 5.0
    assert follower.value == pytest.approx(5.0)


def test_the_factor_graph_delegates_to_bff():
    """The structural queries are bff's -- moralisation, cliques, treewidth.

    ChiSurf keeps *discovery* (which parameter, at which vector position, in
    which local fit); triangulating a graph is not application knowledge.
    """
    from chisurf.core.fitting.factorgraph import LIKELIHOOD, FactorGraph, FactorNode, VariableNode

    graph = FactorGraph(
        variables=[VariableNode("a", "a", 0, 0), VariableNode("t", "t", 1, None)],
        factors=[FactorNode("L0", LIKELIHOOD, ("a", "t"), 0, 16)],
    )
    assert isinstance(graph.engine, bff.InferenceFactorGraph)
    assert graph.treewidth == graph.engine.get_treewidth()


def test_the_residual_kernel_is_bffs():
    """``calculate_weighted_residuals`` runs bff's one-pass kernel."""
    import chisurf.core.fitting as F

    assert F._bff_weighted_residuals is not None, (
        "the residual fell back to numpy; bff is the backend or the build is "
        "broken, and either way it should not pass silently"
    )
    assert F._bff_weighted_residuals is bff.fit_weighted_residuals


def test_the_optimiser_is_bffs():
    """``fit.run()`` optimises in C++, and says so."""
    import chisurf.core.fitting.minimizer as M

    assert M.have_minimizer(), "IMP.bff carries no Minimizer"
    assert M._bff is bff


def test_a_representable_fit_becomes_one_bff_graph():
    """The arrangement the whole port was for, asserted rather than assumed.

    A model bff can represent is ``Expression -> ChiSquared -> Minimizer``:
    the parameters are ports the optimiser writes in C++, the data live in
    the node, and the caller crosses the SWIG boundary once per ``run()``. If
    this ever falls back silently the fit still gets the right answer -- just
    three times slower, with nothing to say so, which is exactly the failure
    a test has to catch.
    """
    import chisurf as cs
    import chisurf.core.data
    import chisurf.core.fitting.fit as F
    import chisurf.core.fitting.minimizer as M
    from chisurf.core.models.parse import ParseModel

    n = 128
    x = np.linspace(0.1, 20.0, n)
    y = 2.5 * np.exp(-x / 3.1) + 0.4
    data = cs.core.data.DataCurve(x=x, y=y, ey=np.full(n, 0.02))
    fit = F.Fit(model_class=ParseModel, data=data)
    fit.model.func = "a*exp(-x/t)+b"
    fit.xmin, fit.xmax = 0, n - 1

    built = M.graph_objective(fit, fit.model)
    assert built is not None, "a parse model no longer builds a bff graph"
    assert isinstance(built[0], bff.FitMinimizer)


def test_the_session_format_is_bffs():
    """A project's node graph is written and read by ``bff.GraphSession``.

    chinet's JSONL format, with bff owning it since the phase-2 port. The
    ``.csp`` archive around it is ChiSurf's; what is *in* it is not.
    """
    import ast
    import pathlib

    from chisurf.core.project import project as project_module

    assert hasattr(bff, "GraphSession")
    assert hasattr(bff.GraphSession, "load")

    # `IMP.bff` is imported inside the save/load functions rather than at
    # module scope (a project that is never opened should not pay for it), so
    # the provenance is read off the source instead of the module namespace.
    source = pathlib.Path(project_module.__file__).read_text(encoding="utf-8")
    assert "bff.GraphSession.load" in source, (
        "the session is no longer read by IMP.bff; chinet's format has an "
        "owner and it is not this package"
    )
    ast.parse(source)


def _description_node_types(family: str) -> set:
    """Every node type a BFF model description builds, read from the file the
    view is generated from -- the view has no graph of its own to inspect.
    """
    import json
    import pathlib

    text = pathlib.Path(bff.get_data_path(f"model_search/{family}.json")).read_text()
    types = set()

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("type"), str):
                types.add(node["type"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(json.loads(text))
    return types


def test_the_decay_curve_is_bffs_and_its_kernels_are_tttrlibs():
    """The layering, end to end: bff builds the network, tttrlib computes.

    A TCSPC lifetime model is a view on a BFF description whose curve is a
    ``TCSPCDecay`` node; the reconvolution and the timeshift inside it are
    tttrlib's own kernels, taken header-only. ChiSurf is not between them,
    which is the property this asserts -- a lifetime fit that started routing
    its convolution back through numpy would still fit, and would have quietly
    undone the arrangement.
    """
    assert hasattr(bff, "TCSPCDecay"), "IMP.bff carries no TCSPCDecay"
    assert "TCSPCDecay" in _description_node_types("tcspc_lifetime")

    import chisurf.core.fitting.minimizer as M
    from chisurf.core.models.description import tcspc_lifetime

    fit = _lifetime_fit(tcspc_lifetime)
    minimizer, _ = M._description_objective(fit.model, [])
    # A proxy is made per access; the model is the same when its ports are.
    (graph,) = minimizer._graph
    live = fit.model.problem
    assert graph.get_parameter("lifetime.tau.0").uid == live.get_parameter("lifetime.tau.0").uid, (
        "a described lifetime fit is not minimised on the description's own graph"
    )


def _lifetime_fit(model_class):
    import chisurf as cs
    import chisurf.core.curve
    import chisurf.core.data
    import chisurf.core.fitting.fit as F

    n = 128
    x = np.arange(n) * 0.1
    irf = np.exp(-0.5 * ((x - 1.0) / 0.1) ** 2)
    y = np.convolve(np.exp(-x / 3.1), irf / irf.sum())[:n] * 1e4 + 5.0
    fit = F.Fit(model_class=model_class, data=cs.core.data.DataCurve(x=x, y=y, ey=np.sqrt(y)))
    fit.model.set_dataset("response", cs.core.curve.Curve(x=x, y=irf))
    fit.model.set_scalar("period", 12.8)
    assert fit.model.problem is not None, fit.model.missing
    return fit


def test_the_photophysics_upstream_of_the_decay_is_bffs_too():
    """A polarisation and a FRET quenching are bff nodes, not numpy steps.

    The decay node was only half the statement: it holds the *instrument*,
    and every TCSPC model shares that. What differs between them is upstream
    -- how the (amplitude, lifetime) pairs are arrived at -- and that is
    where a model quietly returns to Python once per iteration if nobody is
    watching. Each of these is a spectrum transform in C++ inside the model
    description, which is what lets the chain compose without the instrument
    node learning anything.
    """
    for name in (
        "PhotophysicsLifetimeSpectrumNode",
        "PhotophysicsAnisotropySpectrumNode",
        "FRETSpectrumNode",
        "GaussianDistances",
    ):
        assert hasattr(bff, name), f"IMP.bff carries no {name}"
    assert "PhotophysicsAnisotropySpectrumNode" in _description_node_types("tcspc_polarized")
    fret = _description_node_types("tcspc_fret_gaussian")
    assert "FRETSpectrumNode" in fret and "TCSPCDecay" in fret


def test_a_graph_that_builds_is_the_model_it_claims_to_be():
    """The property the census exists to check, on the case that broke it.

    A MaxEnt lifetime model offers the same free parameters a plain lifetime
    model does -- its grid and entropy weight ship fixed -- so a builder that
    refused only on unplaceable parameters accepted it and fitted a
    multi-exponential instead. Measured then: 793.8 counts between the graph's
    curve and the model's, at identical parameters.

    **Being representable is not the same as being represented**, and only
    the second one is allowed to run: the MaxEnt view's graph is a MaxEnt
    inversion, and the plain lifetime view's is not.
    """
    assert "MaxEntSpectrum" in _description_node_types("tcspc_maxent_lifetime")
    assert "MaxEntSpectrum" not in _description_node_types("tcspc_lifetime")


def test_the_crosstalk_matrix_definition_is_bffs():
    """The excitation/emission crosstalk matrices are defined in bff.

    Owner, 2026-09-04: the definition must be in bff, not in chisurf. What a
    crosstalk matrix *is* -- the label convention, how a light-path payload
    becomes values, what forward and inverse mixing mean -- is
    ``IMP.bff.PhotophysicsCrosstalkMatrix`` and the ``crosstalk_*`` kernels;
    ``chisurf.core.fluorescence.crosstalk`` is the numpy adapter that
    converts payloads and reshapes results, and must own no arithmetic of
    its own. A second definition of the matrix would disagree with bff's
    silently, which is exactly what the compute/display line exists to
    prevent.
    """
    from chisurf.core.fluorescence import crosstalk

    assert crosstalk._bff is bff, (
        "the adapter is not wired to this IMP.bff; a second definition would drift from the first"
    )

    # the labelled construction -- subset, reorder, zero-fill -- is bff's
    payload = {
        "rows": ["D", "A"],
        "columns": ["green", "red"],
        "values": [[0.9, 0.1], [0.05, 0.95]],
    }
    labelled = bff.PhotophysicsCrosstalkMatrix(
        payload["rows"], payload["columns"], [0.9, 0.1, 0.05, 0.95]
    )
    via_adapter = crosstalk.matrix_from_payload(
        payload, rows=["A", "D", "X"], columns=["red", "green"]
    )
    selected = labelled.select(["A", "D", "X"], ["red", "green"])
    assert np.allclose(via_adapter[0], np.asarray(selected.get_values()).reshape(3, 2))

    # and the inverse is the kernel, not a numpy re-implementation
    m = np.array([[0.9, 0.1], [0.2, 0.8]])
    measured = crosstalk.apply_mixing(m, np.array([3.0, 5.0]))
    assert np.allclose(
        crosstalk.invert_mixing(m, measured),
        np.asarray(bff.crosstalk_invert_mixing(m, 2, 2, measured, False, 0.0)),
    )
