r"""Render data for the posterior's graph structure — layout without a toolkit.

A global fit's structure is currently reported as text
(:meth:`~chisurf.core.fitting.factorgraph.FactorGraph.describe`), and the
questions it answers are exactly the ones text answers badly: *which* datasets
constrain *which* parameters, whether the problem separates into independent
pieces, and which parameters are so correlated that they are really one
measurement. Probabilistic-graphical-model toolkits solve this by drawing the
graph, and the useful part of their vocabulary transfers directly:

======================  ==============================================
their idea              here
======================  ==============================================
the network             :func:`structure_view` — parameters against the
                        datasets that constrain them
node shaded by entropy  node shaded by *relative uncertainty*, the
                        fluorescence analogue of "how much is known"
arc weighted by mutual  edge weighted by :func:`posterior_correlation`,
information             which for a Gaussian posterior *is* the mutual
                        information up to a monotone transform
the junction tree       :func:`junction_tree_view` — cliques and the
                        separators they share
======================  ==============================================

Everything here returns plain dataclasses carrying coordinates, weights and
labels. Nothing imports Qt or a plotting library, so the layout is testable
headlessly and the same description can be drawn by any front end.

Notes
-----
Layout uses the in-tree graph layer :mod:`chisurf.core.graph`. The correlation view
lays out with Kamada-Kawai on :math:`1 - |r|` distances, so strongly correlated
parameters are placed close together and the geometry itself carries the
message.
"""
from __future__ import annotations

import dataclasses
import math

import numpy as np

from chisurf.core import graph as cg

from chisurf import typing

__all__ = [
    "GraphNode",
    "GraphEdge",
    "GraphView",
    "posterior_correlation",
    "structure_view",
    "correlation_view",
    "junction_tree_view",
    "STRONG_CORRELATION",
]

#: Absolute correlation at or above which two parameters are reported as
#: carrying the same information. At 0.95 a pair is not two measurements with
#: independent error bars; it is one measurement and a direction the data does
#: not constrain.
STRONG_CORRELATION = 0.95


@dataclasses.dataclass
class GraphNode:
    """One drawable node.

    Attributes
    ----------
    key : str
        Stable identifier, unique within a view.
    label : str
        Short text to draw.
    kind : str
        ``parameter``, ``dataset``, ``clique`` or ``separator``. A front end
        maps this to a shape.
    x, y : float
        Position in layout coordinates, roughly ``[-1, 1]``.
    value : float or None
        The quantity the node's shade encodes, normalised to ``[0, 1]``; ``None``
        when it is unknown and the node should be drawn neutral.
    size : float
        Relative marker size, ``1.0`` being ordinary.
    detail : str
        Longer text for a tooltip or a status line.
    """

    key: str
    label: str
    kind: str
    x: float = 0.0
    y: float = 0.0
    value: typing.Optional[float] = None
    size: float = 1.0
    detail: str = ""


@dataclasses.dataclass
class GraphEdge:
    """One drawable edge.

    Attributes
    ----------
    source, target : str
        Node keys.
    weight : float
        Strength in ``[0, 1]``; a front end maps it to width and shade.
    kind : str
        ``constrains``, ``correlation``, ``dependence`` (coupled, but not
        linearly -- a correlation coefficient understates the pair) or
        ``separator``.
    label : str
        Optional text drawn at the midpoint.
    """

    source: str
    target: str
    weight: float = 1.0
    kind: str = "constrains"
    label: str = ""


@dataclasses.dataclass
class GraphView:
    """A complete drawable description.

    Attributes
    ----------
    nodes : list of GraphNode
        The nodes, already laid out.
    edges : list of GraphEdge
        The edges, referring to node keys.
    title : str
        What this view shows.
    legend : str
        What the shading and widths mean.
    notes : list of str
        Statements worth putting in front of the user -- an unidentifiable
        parameter, a pair that is really one measurement, a fit that separates.
    """

    nodes: typing.List[GraphNode] = dataclasses.field(default_factory=list)
    edges: typing.List[GraphEdge] = dataclasses.field(default_factory=list)
    title: str = ""
    legend: str = ""
    notes: typing.List[str] = dataclasses.field(default_factory=list)

    def node(self, key: str) -> typing.Optional[GraphNode]:
        """Return the node with ``key``, or ``None``."""
        for n in self.nodes:
            if n.key == key:
                return n
        return None

    def __len__(self) -> int:
        """Return the number of nodes."""
        return len(self.nodes)


def short_labels(
        names: typing.Sequence[str],
) -> typing.Dict[str, str]:
    """Return a display label per name, short but never ambiguous.

    A group prefixes its parameters with the member that owns them (``2:c``).
    Dropping that prefix reads better -- until a global fit puts three ``c``
    nodes on the same picture, at which point the drawing says the fit has one
    parameter three times over, which is precisely the misreading the picture
    exists to prevent. So the prefix is dropped only where the short form is
    already unique, and otherwise reattached as ``c(2)``.

    Parameters
    ----------
    names : sequence of str
        Full parameter names.

    Returns
    -------
    dict
        Full name to display label.
    """
    names = [str(n) for n in names]
    shorts = [n.split(":")[-1] for n in names]
    seen: typing.Dict[str, int] = {}
    for s in shorts:
        seen[s] = seen.get(s, 0) + 1
    out = {}
    for full, short in zip(names, shorts):
        if seen[short] > 1 and ":" in full:
            out[full] = f"{short}({full.split(':')[0]})"
        elif seen[short] > 1:
            out[full] = full
        else:
            out[full] = short
    return out


def _layout(graph: cg.Graph, seed: int = 0, **kw) -> typing.Dict[str, np.ndarray]:
    """Return positions for ``graph``, rescaled to ``[-1, 1]`` in both axes.

    Kamada-Kawai gives the most readable result for the small, sparse graphs a
    fit produces, but it needs a connected graph and can fail; spring layout is
    the fallback, and a single node is placed by hand because both would divide
    by zero.

    Parameters
    ----------
    graph : chisurf.core.graph.Graph
        Graph to lay out.
    seed : int, optional
        Seed for the fallback layout, so a redraw does not reshuffle the picture.
    **kw
        Passed to the layout function (e.g. ``weight``).

    Returns
    -------
    dict
        Node to ``(x, y)``.
    """
    if graph.number_of_nodes() == 0:
        return {}
    if graph.number_of_nodes() == 1:
        return {next(iter(graph.nodes)): np.zeros(2)}
    try:
        pos = cg.kamada_kawai_layout(graph, **kw)
    except Exception:
        pos = cg.spring_layout(graph, seed=seed)
    return _rescale(_orient(pos))


def _orient(pos: typing.Dict) -> typing.Dict:
    """Rotate a layout so its widest direction is horizontal.

    A chain of cliques is genuinely one-dimensional, and a force layout is right
    to draw it as a line -- but it may draw that line vertically, down the middle
    of a canvas that is wider than it is tall, using a twentieth of the space and
    stacking the labels on top of each other. Rotating onto the principal axis
    costs nothing and is never wrong: it preserves every distance in the layout.

    Parameters
    ----------
    pos : dict
        Node to ``(x, y)``.

    Returns
    -------
    dict
        The same layout, rotated.
    """
    if len(pos) < 2:
        return pos
    keys = list(pos)
    points = np.array([pos[k] for k in keys], dtype=float)
    centred = points - points.mean(axis=0)
    try:
        # Principal axis of the point cloud; the eigenvector for the larger
        # eigenvalue is the direction the layout actually extends in.
        _, vectors = np.linalg.eigh(centred.T @ centred)
        principal = vectors[:, -1]
        angle = math.atan2(principal[1], principal[0])
    except np.linalg.LinAlgError:
        return pos
    cos_a, sin_a = math.cos(-angle), math.sin(-angle)
    rotation = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    rotated = centred @ rotation.T
    return {k: rotated[i] for i, k in enumerate(keys)}


def _rescale(pos: typing.Dict) -> typing.Dict[str, np.ndarray]:
    """Rescale positions into ``[-1, 1]`` on both axes, preserving aspect.

    Note that leaving a margin *here* would achieve nothing: the front end fits
    its frame to the node extent, so scaling every position by a constant is
    invisible. Room for labels is the painter's business.
    """
    if not pos:
        return pos
    points = np.array(list(pos.values()), dtype=float)
    lo, hi = points.min(axis=0), points.max(axis=0)
    span = np.maximum(hi - lo, 1e-12)
    scale = 2.0 / span.max()
    centre = 0.5 * (hi + lo)
    return {k: (np.asarray(v, dtype=float) - centre) * scale for k, v in pos.items()}


def posterior_correlation(
        fit,
        model=None,
) -> typing.Tuple[typing.List[str], typing.Optional[np.ndarray]]:
    r"""Return ``(names, correlation)`` for a fit's free parameters.

    Prefers a stored sampling chain, because that is the real posterior
    correlation rather than a quadratic approximation to it; falls back to the
    curvature at the optimum, which is what error bars already use. Returns
    ``None`` for the matrix when neither is available.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit to describe.
    model : chisurf.core.models.Model, optional
        Model whose parameters are meant. Defaults to ``fit.model``.

    Returns
    -------
    tuple
        Parameter names and a ``(k, k)`` correlation matrix, or ``(names, None)``.
    """
    import chisurf.core.fitting.fit as fit_module

    if model is None:
        model = getattr(fit, "model", None)
    names = [str(n) for n in getattr(model, "parameter_names", [])]

    chain = getattr(fit, "sampling_chain", None)
    if isinstance(chain, dict) and chain.get("parameter_values") is not None:
        draws = np.atleast_2d(np.asarray(chain["parameter_values"], dtype=float))
        chain_names = [str(n) for n in chain.get("parameter_names", [])]
        if draws.shape[0] > 2 and len(chain_names) == draws.shape[1]:
            with np.errstate(invalid="ignore", divide="ignore"):
                corr = np.corrcoef(draws, rowvar=False)
            corr = np.atleast_2d(corr)
            if np.all(np.isfinite(corr)):
                return chain_names, corr

    try:
        cov, used = fit_module.covariance_matrix(fit, model=model)
        cov = np.atleast_2d(np.asarray(cov, dtype=float))
        used = list(used)
    except Exception:
        return names, None
    if cov.size == 0 or cov.shape[0] != len(used):
        return names, None
    sd = np.sqrt(np.maximum(np.diag(cov), 0.0))
    if not np.all(sd > 0.0):
        return names, None
    corr = cov / np.outer(sd, sd)
    kept = [names[i] if i < len(names) else str(i) for i in used]
    return kept, corr


def posterior_dependence(
        fit,
        model=None,
        n_permutations: int = 32,
) -> typing.Tuple[typing.List[str], typing.Optional[np.ndarray], typing.Optional[np.ndarray]]:
    r"""Return ``(names, dependence, nonlinear)`` from a fit's stored draws.

    The companion to :func:`posterior_correlation`, and the reason it is not
    enough. A correlation coefficient is zero for two parameters lying on a
    banana or a ring, which is the ordinary posterior shape when a lifetime
    trades against an amplitude near a bound -- yet those two determine each
    other almost completely. Mutual information is zero only for genuine
    independence, and :mod:`chisurf.core.fitting.dependence` puts it on the
    correlation scale so the two can be compared directly.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit to describe.
    model : chisurf.core.models.Model, optional
        Model whose parameters are meant.
    n_permutations : int, optional
        Permutations per pair used to measure the estimator's null. Lower than
        the module default because this runs over every pair of a possibly wide
        model on a path that draws a picture.

    Returns
    -------
    tuple
        Names, a ``(k, k)`` dependence matrix on the correlation scale, and a
        boolean matrix flagging pairs a correlation coefficient understates.
        The matrices are ``None`` when the fit carries no usable chain -- which
        is not evidence of independence and must not be drawn as such.
    """
    from chisurf.core.fitting import dependence as dep
    from chisurf.core.fitting import derived as _derived

    if model is None:
        model = getattr(fit, "model", None)

    chain = getattr(fit, "sampling_chain", None)
    if not isinstance(chain, dict) or chain.get("parameter_values") is None:
        return [], None, None
    # The same gate every other consumer of the draws applies. A chain R-hat or
    # the effective sample size rejected cannot support a claim that two
    # parameters are coupled along a curve -- an unmixed chain looks exactly
    # like one, which is precisely why the claim must not be made from it.
    if _derived.chain_verdict(fit) is False:
        return [], None, None
    draws = np.atleast_2d(np.asarray(chain["parameter_values"], dtype=np.float64))
    names = [str(n) for n in chain.get("parameter_names", [])]
    if draws.shape[0] < 64 or len(names) != draws.shape[1]:
        return names, None, None

    values, flags = dep.dependence_matrix(
        draws, n_permutations=n_permutations)
    return names, values, flags


def _relative_uncertainty(model) -> typing.Dict[str, float]:
    """Return each parameter's ``sd / |value|``, the shade of a node.

    The analogue of the entropy a graphical-model tool shades its nodes by: how
    much the data has *not* pinned down. Scale-free, so parameters in
    nanoseconds and parameters in counts are comparable at a glance.
    """
    out = {}
    for p in getattr(model, "parameters", []) or []:
        try:
            value = float(p.value)
            err = float(p.error_estimate)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(err) or err <= 0.0:
            continue
        denominator = abs(value) if abs(value) > 1e-30 else 1.0
        out[str(p.name)] = err / denominator
    return out


def _shade(values: typing.Dict[str, float]) -> typing.Dict[str, float]:
    """Map raw values to ``[0, 1]`` on a log scale, robust to outliers.

    Relative uncertainties span orders of magnitude, so a linear map puts every
    well-determined parameter in the same bucket. The 5th-95th percentile range
    is used so one unconstrained parameter cannot flatten the rest.
    """
    if not values:
        return {}
    raw = np.array(list(values.values()), dtype=float)
    raw = raw[np.isfinite(raw) & (raw > 0.0)]
    if raw.size == 0:
        return {k: 0.0 for k in values}
    logs = np.log10(raw)
    lo, hi = np.percentile(logs, 5), np.percentile(logs, 95)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi - lo < 1e-9:
        return {k: 0.5 for k in values}
    out = {}
    for k, v in values.items():
        if not np.isfinite(v) or v <= 0.0:
            out[k] = 1.0
            continue
        out[k] = float(np.clip((math.log10(v) - lo) / (hi - lo), 0.0, 1.0))
    return out


def structure_view(fit, model=None) -> GraphView:
    """Return the bipartite view: parameters against the datasets that see them.

    The picture a global fit is usually being asked about. A parameter touching
    several datasets is a shared one; a parameter touching none is not
    constrained by any data at all, which is worth saying out loud; and a graph
    that falls apart into pieces is several independent fits wearing one name.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit to describe.
    model : chisurf.core.models.Model, optional
        Model whose free parameters are the variable nodes.

    Returns
    -------
    GraphView
        Nodes shaded by relative uncertainty, edges to the datasets.
    """
    from chisurf.core.fitting import factorgraph as fg

    if model is None:
        model = fg.posterior_model(fit)
    graph = fg.build_factor_graph(fit, model)
    uncertainty = _relative_uncertainty(model)
    shade = _shade(uncertainty)
    labels = short_labels([v.name for v in graph.variables.values()])

    nodes: typing.List[GraphNode] = []
    edges: typing.List[GraphEdge] = []
    bipartite = cg.Graph()

    for key, var in graph.variables.items():
        short = str(var.name).split(":")[-1]
        nodes.append(GraphNode(
            key=key, label=labels.get(str(var.name), short), kind="parameter",
            value=shade.get(str(var.name), shade.get(short)),
            detail=f"{var.name}",
        ))
        bipartite.add_node(key, bipartite=0)

    members = list(fit) if hasattr(fit, "__iter__") else []
    for factor in graph.likelihood_factors():
        key = factor.key
        # The factor keys are ``L0, L1, ...`` while a group prefixes its
        # parameters ``1:c, 2:c, ...``. Drawing both raw puts ``c(1)`` next to
        # ``L1`` when ``c(1)`` in fact belongs to ``L0`` -- an off-by-one the
        # eye makes instantly and never questions. Datasets are therefore
        # labelled on the parameters' 1-based convention, and by their real name
        # where they have one.
        index = getattr(factor, "fit_index", None)
        label = None
        if index is not None and 0 <= index < len(members):
            name = str(getattr(members[index], "name", "") or "").strip()
            if name:
                label = name if len(name) <= 18 else name[:17] + "…"
        if label is None:
            label = f"data {1 if index is None else index + 1}"
        points = int(getattr(factor, "size", 0) or 0)
        nodes.append(GraphNode(
            key=key, label=label, kind="dataset",
            # A dataset that contributes more points constrains more, and the
            # picture may as well say so.
            size=1.3 + (0.4 if points >= 512 else 0.0),
            detail=f"{label} — {points} points" if points else str(label),
        ))
        bipartite.add_node(key, bipartite=1)
        for var_key in graph.variables_of(key):
            if var_key in graph.variables:
                bipartite.add_edge(key, var_key)
                edges.append(GraphEdge(source=var_key, target=key))

    # Three columns rather than a generic bipartite layout, because the columns
    # mean something: private parameters | datasets | shared parameters. A
    # library layout orders each side by whatever the graph dict happens to
    # yield, which drew c(2), c(1), a, c(3) against data 2, data 3, data 1 --
    # every edge crossing every other, in a picture whose whole job is to show
    # which dataset constrains which parameter. Placing each private parameter
    # on its own dataset's row makes those edges short and horizontal, and
    # leaves the shared ones as the only long diagonals, which is exactly the
    # thing worth noticing.
    #
    # The datasets go in the *middle*, not on one side. With parameters on both
    # sides no edge ever has to cross a column of nodes: put the shared ones on
    # the far side of the private ones and every shared-parameter edge is drawn
    # straight through the private parameters' labels.
    dataset_nodes = [n for n in nodes if n.kind == "dataset"]
    order = {}
    for n in dataset_nodes:
        factor = graph.factors.get(n.key)
        order[n.key] = getattr(factor, "fit_index", None)
    dataset_nodes.sort(key=lambda n: (order.get(n.key) is None,
                                      order.get(n.key) or 0, n.label))
    rows = {n.key: i for i, n in enumerate(dataset_nodes)}

    def _row_y(row: int, total: int) -> float:
        """Return the vertical position of row ``row`` of ``total``."""
        if total <= 1:
            return 0.0
        return 1.0 - 2.0 * row / (total - 1)

    n_rows = max(1, len(dataset_nodes))
    for n in dataset_nodes:
        n.x, n.y = 0.0, _row_y(rows[n.key], n_rows)

    # A parameter is "private" when exactly one dataset uses it.
    private: typing.Dict[int, typing.List[GraphNode]] = {}
    shared: typing.List[GraphNode] = []
    for n in nodes:
        if n.kind != "parameter":
            continue
        touching = [f for f in graph.factors_of(n.key)
                    if f in {d.key for d in dataset_nodes}]
        if len(touching) == 1:
            private.setdefault(rows[touching[0]], []).append(n)
        else:
            shared.append(n)

    for row, members in private.items():
        base = _row_y(row, n_rows)
        span = 0.9 / max(1, n_rows)
        for k, n in enumerate(sorted(members, key=lambda m: m.label)):
            offset = 0.0 if len(members) == 1 else (
                span * (k - 0.5 * (len(members) - 1))
            )
            n.x, n.y = -1.0, base + offset
    # Half a row down, so a shared parameter sits in the *gap* between two
    # dataset rows. On a row it lines up with that row's private parameter and
    # its edge is drawn straight through it, which reads as a chain
    # (a -> c(2) -> data 2) instead of two independent constraints.
    for k, n in enumerate(sorted(shared, key=lambda m: m.label)):
        n.x = 1.0
        n.y = (_row_y(k + 0.5, n_rows) if n_rows > 1
               else _row_y(k, max(1, len(shared))))

    notes = []
    # A parameter with no usable error estimate is one the data says nothing
    # about -- most often because the model does not respond to it at all, which
    # the factor graph cannot see: a likelihood factor's scope is the model's
    # whole parameter list, not the subset the model actually depends on. The
    # curvature *has* already discovered it (that is why the estimate is
    # missing), so the note costs nothing to make.
    without_estimate = sorted(
        labels.get(str(v.name), str(v.name).split(":")[-1])
        for v in graph.variables.values()
        if str(v.name) not in uncertainty
        and str(v.name).split(":")[-1] not in uncertainty
    )
    if without_estimate:
        notes.append(
            f"no error estimate: {', '.join(without_estimate)} — the data does "
            f"not constrain these, and the model may not respond to them at all"
        )
    unexplained = graph.unexplained_variables()
    if unexplained:
        pretty = ", ".join(sorted(
            labels.get(str(graph.variables[k].name),
                       str(graph.variables[k].name).split(":")[-1])
            for k in unexplained if k in graph.variables
        ))
        notes.append(
            f"not constrained by any dataset: {pretty} — free to take any value"
        )
    components = graph.connected_components()
    if len(components) > 1:
        notes.append(
            f"{len(components)} independent components — this is "
            f"{len(components)} separate fits, and sampling them jointly is waste"
        )
    return GraphView(
        nodes=nodes, edges=edges,
        title="Posterior structure",
        legend="parameter shade = relative uncertainty (pale = well determined)",
        notes=notes,
    )


def correlation_view(
        fit,
        model=None,
        threshold: float = 0.3,
) -> GraphView:
    r"""Return the parameter-only view, edges weighted by dependence.

    The analogue of a graphical-model tool shading its arcs by mutual
    information. For a *Gaussian* posterior a correlation coefficient says the
    same thing, since :math:`I = -\tfrac12\ln(1 - r^2)` is monotone in
    :math:`|r|` -- but only then. On a banana or a ring, the ordinary shape when
    a lifetime trades against an amplitude near a bound, :math:`r \approx 0`
    while the two parameters determine each other almost completely, and an
    edge drawn from :math:`|r|` alone is simply absent.

    So whenever the fit carries draws, the mutual information is measured from
    them (:func:`posterior_dependence`) and the stronger of the two is used. A
    pair the correlation coefficient understates is drawn as its own kind of
    edge and labelled with both numbers, because "coupled, but not along a
    straight line" is a different fact about a fit than "correlated" and calls
    for a different response.

    This is the view that answers what a global fit is usually really being
    asked: a pair at :math:`|r| \approx 1` is **one** measurement and a direction
    the data does not constrain, not two parameters with independent error bars.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit to describe.
    model : chisurf.core.models.Model, optional
        Model whose parameters are shown.
    threshold : float, optional
        Draw an edge only above this absolute correlation, so the picture shows
        structure rather than a complete graph.

    Returns
    -------
    GraphView
        Nodes shaded by relative uncertainty, edges by ``|r|``. Empty of edges
        when no correlation is available at all.
    """
    from chisurf.core.fitting import factorgraph as fg

    if model is None:
        model = fg.posterior_model(fit)
    names, corr = posterior_correlation(fit, model=model)
    shade = _shade(_relative_uncertainty(model))

    # Dependence measured from the draws, reindexed onto the order the
    # correlation matrix uses. The two name the same parameters differently --
    # a chain is written with the sampled model's plain names while this view
    # uses the group's ``fit:``-prefixed ones -- so requiring the lists to match
    # exactly silently disabled the measurement on every global fit. Matching on
    # the short name is what actually lines them up; anything still unmatched is
    # dropped rather than paired by position.
    dep = nonlinear = None
    dep_names, dep_raw, flags_raw = posterior_dependence(fit, model=model)
    if dep_raw is not None:
        short_of = {str(n).split(":")[-1]: i for i, n in enumerate(dep_names)}
        index = [short_of.get(str(n).split(":")[-1]) for n in names]
        if all(i is not None for i in index):
            take = np.asarray(index, dtype=int)
            dep = dep_raw[np.ix_(take, take)]
            nonlinear = flags_raw[np.ix_(take, take)]

    labels = short_labels(names)
    nodes = []
    for name in names:
        short = str(name).split(":")[-1]
        nodes.append(GraphNode(
            key=str(name), label=labels.get(str(name), short), kind="parameter",
            value=shade.get(str(name), shade.get(short)),
            detail=str(name),
        ))

    edges = []
    notes = []
    curved = []
    graph = cg.Graph()
    graph.add_nodes_from(str(n) for n in names)
    if corr is not None and corr.shape[0] == len(names):
        strong = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                r = float(corr[i, j])
                if not np.isfinite(r):
                    continue
                d = float(dep[i, j]) if dep is not None else float("nan")
                # nan means the pair could not be measured, which is not a
                # licence to treat it as unbent.
                bent = bool(
                    nonlinear is not None and np.isfinite(d) and nonlinear[i, j]
                )
                # The strength of the edge is whichever measure found more. An
                # |r| below the threshold is not a reason to hide a pair the
                # draws show to be tightly coupled -- that omission is the exact
                # failure this view existed with.
                strength = abs(r)
                if bent and np.isfinite(d):
                    strength = max(strength, d)
                if strength < threshold:
                    continue
                edges.append(GraphEdge(
                    source=str(names[i]), target=str(names[j]),
                    weight=float(min(1.0, strength)),
                    kind="dependence" if bent else "correlation",
                    label=(f"r={r:+.2f}  I={d:.2f}" if bent else f"{r:+.2f}"),
                ))
                if bent:
                    curved.append((names[i], names[j], r, d))
                # Distance shrinks with |r|, so the layout places a strongly
                # correlated pair together and the geometry says it too. The
                # raw 1 - |r| is rescaled below: when every pair sits above 0.99
                # the distances are all ~0.005 and differ only in the third
                # decimal, which leaves Kamada-Kawai ill-conditioned and
                # collapses the whole graph onto a line -- true in spirit,
                # unreadable in practice.
                graph.add_edge(str(names[i]), str(names[j]),
                               weight=max(1e-3, 1.0 - strength))
                if strength >= STRONG_CORRELATION:
                    strong.append((names[i], names[j], r, bent))
        for a, b, r, bent in strong:
            if bent:
                continue    # said better by the note below
            notes.append(
                f"{labels.get(str(a), a)} and {labels.get(str(b), b)} are "
                f"correlated at {r:+.3f} — one measurement, not two"
            )
        for a, b, r, d in curved:
            notes.append(
                f"{labels.get(str(a), a)} and {labels.get(str(b), b)} constrain "
                f"each other at {d:.2f} while their correlation is only "
                f"{r:+.2f} — coupled along a curve, so a correlation matrix "
                f"and every error bar derived from one understate it"
            )
    else:
        notes.append(
            "no posterior correlation available — run a fit or a sampling job"
        )

    # Spread the distances over a well-conditioned range before laying out. The
    # *ordering* is what carries meaning -- the most correlated pair stays the
    # closest -- while the absolute values only have to be numerically sane.
    if graph.number_of_edges():
        raw = np.array([d["weight"] for _, _, d in graph.edges(data=True)])
        lo, hi = float(raw.min()), float(raw.max())
        for _, _, d in graph.edges(data=True):
            fraction = 0.0 if hi - lo < 1e-12 else (d["weight"] - lo) / (hi - lo)
            d["weight"] = 0.35 + 0.65 * fraction
        pos = _layout(graph, weight="weight")
    else:
        pos = _layout(
            cg.complete_graph(list(graph.nodes))
            if graph.number_of_nodes() > 1 else graph
        )

    # Too many edges to label without the numbers landing on top of each other.
    # The notes below the plot already name every strong pair, so the values are
    # moved there rather than dropped.
    crowded = len(edges) > 8
    if crowded:
        for e in edges:
            e.label = ""
    for n in nodes:
        if n.key in pos:
            n.x, n.y = float(pos[n.key][0]), float(pos[n.key][1])

    legend = (f"edge = dependence above {threshold:g}; "
              f"close together = tightly coupled")
    if curved:
        legend += " — warm edges are coupled along a curve, where |r| understates"
    if crowded:
        legend += " — values omitted, too many edges to label"
    return GraphView(
        nodes=nodes, edges=edges,
        title="Posterior dependence",
        legend=legend,
        notes=notes,
    )


def junction_tree_view(fit, model=None) -> GraphView:
    """Return the junction tree: cliques as nodes, separators on the edges.

    What the elimination order buys. Each node is a set of parameters that must
    be reasoned about together; each edge is labelled with the separator the two
    cliques share, which is exactly the information that has to pass between
    them. A tree of small cliques is a cheap posterior; one giant clique is a
    fit whose parameters are all entangled.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        Fit to describe.
    model : chisurf.core.models.Model, optional
        Model whose free parameters are meant.

    Returns
    -------
    GraphView
        Cliques and separators.
    """
    from chisurf.core.fitting import factorgraph as fg

    if model is None:
        model = fg.posterior_model(fit)
    graph = fg.build_factor_graph(fit, model)
    tree = graph.junction_tree()

    labels = short_labels([v.name for v in graph.variables.values()])

    def _pretty(keys) -> str:
        """Return a short comma-separated label for a set of variable keys."""
        return ", ".join(sorted(
            labels.get(str(graph.variables[k].name),
                       str(graph.variables[k].name).split(":")[-1])
            for k in keys if k in graph.variables
        ))

    nodes, edges = [], []
    for node in tree.nodes:
        key = "|".join(sorted(node))
        label = _pretty(node)
        nodes.append(GraphNode(
            key=key, label=label or "(empty)", kind="clique",
            size=1.0 + 0.25 * max(0, len(node) - 1),
            detail=f"{len(node)} parameters: {label}",
        ))
    for a, b in tree.edges:
        shared = set(a) & set(b)
        edges.append(GraphEdge(
            source="|".join(sorted(a)), target="|".join(sorted(b)),
            kind="separator", label=_pretty(shared),
            weight=float(min(1.0, 0.3 + 0.2 * len(shared))),
        ))

    relabelled = cg.Graph()
    relabelled.add_nodes_from(n.key for n in nodes)
    relabelled.add_edges_from((e.source, e.target) for e in edges)
    pos = _layout(relabelled)
    for n in nodes:
        if n.key in pos:
            n.x, n.y = float(pos[n.key][0]), float(pos[n.key][1])

    notes = [f"treewidth {graph.treewidth} — the largest clique has "
             f"{graph.treewidth + 1} parameters in it"]
    return GraphView(
        nodes=nodes, edges=edges,
        title="Junction tree",
        legend="node = parameters that must be reasoned about together; "
               "edge label = what they share",
        notes=notes,
    )
