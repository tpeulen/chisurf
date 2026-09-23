r"""The factor structure of a fit's posterior, as an explicit graph.

A ChiSurf posterior factorises exactly:

.. math::

    p(\theta \mid D) \;\propto\; \prod_k L_k(\theta_{S_k})
                                 \;\cdot\; \prod_i \pi_i(\theta_i)

where :math:`S_k` is the set of free parameters that dataset *k*'s model
actually reads and :math:`\pi_i` is parameter *i*'s prior. Until this module
that factorisation was implicit: :class:`~chisurf.core.models.global_model.globalfit.GlobalFitModel`
flattened every local model's free parameters plus the globals into one dense
vector and recomputed **all** local models on **every** objective evaluation, so
a proposal touching one parameter of one dataset cost N model evaluations
instead of one.

This module materialises the factorisation as a :class:`FactorGraph` --
variable nodes are free parameters, factor nodes are per-dataset likelihoods and
per-parameter priors -- and uses it for three things:

**Relevance.** :meth:`FactorGraph.affected_fits` answers "which local models
must be recomputed when *these* parameters change?". That is the query that
turns the global objective from O(N) into O(1) per local-parameter move.

**Structure.** Moralising the graph, eliminating variables in a greedy
`min_fill` order and building a junction tree exposes the cliques, the
separators and the **treewidth** of the fit. Cliques are the blocks a sampler or
a scan should move jointly; the separator is the set of parameters the datasets
actually share.

**Identifiability.** Treewidth and :meth:`FactorGraph.connected_components` are
a user-facing result, not just an implementation detail: "these datasets are
conditionally independent given :math:`R_0` and :math:`\tau_D`" is precisely the
statement a global fit exists to make.

The design follows the architecture of mature probabilistic graphical-model
toolkits -- a model object separate from any inference engine, moralisation plus
triangulation to expose blocks, and relevance pruning per query. Every one of
those algorithms runs in ``IMP.bff`` (``InferenceFactorGraph``); this module
says what the variables and factors *are* and hands the graph over.

Their *discrete-table* kernels do not transfer, since a fluorescence posterior
is continuous; their linear-Gaussian kernel does, exactly. Represent each factor
by its canonical form ``(K, h, g)`` and multiplication is addition on aligned
scopes, conditioning is a slice, and marginalisation is the Schur complement
``K_xx - K_xy K_yy^-1 K_yx``, so variable elimination over this graph runs in
closed form. That kernel is ``IMP.bff.InferenceCanonicalForm`` and
``IMP.bff.InferenceGaussianElimination``; the engines in
:mod:`chisurf.core.fitting.engine` condition through it. The comparison with
the toolkit it came from is ``okf/references/agrum-mining.md``.

Notes
-----
A plain :class:`~chisurf.core.fitting.fit.Fit` yields a single likelihood factor
over all of its free parameters -- one clique, treewidth ``n_free - 1``. That is
the honest answer: a single dataset has no dataset-level structure to exploit.
Structure appears with :class:`~chisurf.core.fitting.fit.FitGroup`.
"""

from __future__ import annotations

import contextlib
import dataclasses
import functools
import inspect

from chisurf import typing
from chisurf.core import graph as cg

__all__ = [
    "VariableNode",
    "FactorNode",
    "FactorGraph",
    "build_factor_graph",
    "structure_version",
    "bump_structure_version",
    "window_version",
    "bump_window_version",
    "frozen_structure",
    "frozen_epoch",
    "frozen",
    "LIKELIHOOD",
    "PRIOR",
]

#: ``kind`` tag of a factor standing for one dataset's likelihood.
LIKELIHOOD = "likelihood"

#: ``kind`` tag of a factor standing for one parameter's prior.
PRIOR = "prior"

#: Monotonic counter bumped whenever something that can change the *shape* of a
#: factor graph happens -- a parameter is linked or unlinked, a parameter is
#: fixed or freed, a local fit is added or removed, a global parameter is
#: declared, or a model rediscovers its parameters. Cached graphs record the
#: value they were built at and rebuild when it no longer matches. Values are
#: never compared for order, only for equality, so wrap-around is irrelevant.
_STRUCTURE_VERSION = 0


def structure_version() -> int:
    """Return the current structural version counter.

    Returns
    -------
    int
        The counter's present value. A cached :class:`FactorGraph` is still
        valid exactly while this is unchanged.
    """
    return _STRUCTURE_VERSION


#: Monotonic counter bumped whenever a fit *window* changes -- ``xmin``,
#: ``xmax``, ``fit_range`` or ``mask``. Residual lengths and point counts depend
#: on these but the parameter structure does not, so they get their own counter:
#: bumping the structural one would needlessly rebuild every factor graph.
_WINDOW_VERSION = 0


def window_version() -> int:
    """Return the current fit-window version counter.

    Returns
    -------
    int
        The counter's present value. Caches of anything derived from the fit
        windows (residual arrays, point counts) are valid while it is unchanged.
    """
    return _WINDOW_VERSION


def bump_window_version() -> int:
    """Invalidate caches derived from the fit windows.

    Called from the ``xmin`` / ``xmax`` / ``fit_range`` / ``mask`` setters of
    :class:`~chisurf.core.fitting.fit.Fit`.

    Returns
    -------
    int
        The new counter value.
    """
    global _WINDOW_VERSION
    _WINDOW_VERSION += 1
    return _WINDOW_VERSION


def bump_structure_version() -> int:
    """Invalidate every cached factor graph.

    Called from the seams that can change a fit's factor structure: the
    ``link`` and ``fixed`` setters of
    :class:`~chisurf.core.parameter.Parameter`, the fit- and
    global-parameter mutators of
    :class:`~chisurf.core.models.global_model.globalfit.GlobalFitModel`, and
    :meth:`~chisurf.core.fitting.parameter.FittingParameterGroup.find_parameters`.

    Returns
    -------
    int
        The new counter value.
    """
    global _STRUCTURE_VERSION
    _STRUCTURE_VERSION += 1
    return _STRUCTURE_VERSION


#: Incremented on entering and on leaving :func:`frozen_structure`, so a value
#: identifies one uninterrupted run. ``None`` outside a freeze.
_FROZEN_EPOCH = 0
_FROZEN_DEPTH = 0


def frozen_epoch() -> typing.Optional[int]:
    """Return a token identifying the current run, or ``None`` outside one.

    Anything a run cannot change may be memoised against this: the token is
    stable for exactly as long as the freeze lasts and differs afterwards, so a
    cache keyed on it can never outlive the contract that justifies it. Used for
    inputs that are expensive to *check* rather than to compute -- an instrument
    response whose cache key hashes the whole array, for instance.

    Returns
    -------
    int or None
        The current epoch, or ``None`` when no freeze is active.
    """
    return _FROZEN_EPOCH if _FROZEN_DEPTH > 0 else None


@contextlib.contextmanager
def frozen_structure(*targets):
    """Hold the parameter structure fixed for the duration of a run.

    **Nothing about a fit's structure changes while it is being optimised or
    sampled.** Parameters are not linked, freed, fixed or rediscovered between
    two objective evaluations -- the whole point of an objective is that it is a
    function of the *values* alone. Yet deciding which parameters are free costs
    three attribute reads each, two of them crossing into the underlying bff
    port, and that decision was being re-derived several times per evaluation.

    Inside this context each model's free-parameter list, bounds and parameter
    names are computed once and served directly, with no version check and no
    per-access allocation. On exit the structural and window counters are
    compared against their values on entry, so a run that *did* change the
    structure is reported rather than silently returning stale lists.

    Parameters
    ----------
    *targets : object
        Fits, fit groups or models to freeze. A group freezes its global model
        and every member model; a fit freezes its model.

    Re-entrant: a model already frozen by an enclosing context is left alone,
    so a sampler that internally calls another sampler does not release the
    outer freeze.

    Yields
    ------
    None

    Warns
    -----
    The structure changing inside the context is a contract violation and is
    logged; the frozen views are dropped on exit either way.

    Examples
    --------
    >>> from chisurf.core.fitting import factorgraph
    >>> with factorgraph.frozen_structure():   # nothing to freeze
    ...     pass
    """
    models = []
    for target in targets:
        for model in _models_of(target):
            if model is not None and model not in models:
                models.append(model)

    global _FROZEN_EPOCH, _FROZEN_DEPTH
    _FROZEN_EPOCH += 1
    _FROZEN_DEPTH += 1
    entered = []
    frozen_parameters = []
    structure_at_entry = structure_version()
    window_at_entry = window_version()
    try:
        for model in models:
            if model.__dict__.get("_frozen_structure") is not None:
                # Already frozen by an enclosing run. Freezing again would be a
                # no-op, but *releasing* it on exit would break the outer
                # context, so leave it entirely to whoever froze it.
                continue
            try:
                free = list(model.parameters)
                names = list(model.parameter_names)
                bounds = list(model.parameter_bounds)
            except Exception:
                continue
            model.__dict__["_frozen_structure"] = {
                "parameters": free,
                "parameter_names": names,
                "parameter_bounds": bounds,
                "n_free": len(free),
            }
            entered.append(model)
            # Reading a parameter costs six property dispatches, three of them
            # into the backing port, purely to decide how to read it -- and none
            # of those answers can change during the run either. Stamp them so a
            # read is one dict lookup and one port access.
            #
            # `fixed` is stamped for the *write* path, which is the same
            # argument applied to the other direction and was missing for a
            # long time. An optimiser writes every free parameter on every
            # iteration, and each write re-read `_port.fixed`, cleared it,
            # wrote the value and restored it -- four calls across the binding
            # where one will do, because a parameter's fixedness is exactly as
            # constant during a run as its linkage is. Reads had been brought
            # down to 0.224 us this way while writes still cost 3.191 us.
            for q in _freezable_parameters(model):
                try:
                    lb, ub = q.bounds if q.bounds_on else (float("nan"), float("nan"))
                    q.__dict__["_frozen_flags"] = (
                        bool(q.is_linked),
                        getattr(q, "_callable", None),
                        bool(q.bounds_on),
                        float(lb) if lb is not None else float("nan"),
                        float(ub) if ub is not None else float("nan"),
                        bool(q.fixed),
                    )
                    frozen_parameters.append(q)
                except Exception:
                    continue
        yield
    finally:
        _FROZEN_DEPTH -= 1
        _FROZEN_EPOCH += 1
        for model in entered:
            model.__dict__.pop("_frozen_structure", None)
        for q in frozen_parameters:
            q.__dict__.pop("_frozen_flags", None)
            q.__dict__.pop("_frozen_value", None)
        if structure_version() != structure_at_entry:
            import chisurf.logging

            chisurf.logging.warning(
                "frozen_structure: the parameter structure changed during a "
                "run that declared it fixed; cached parameter lists were stale."
            )
        if window_version() != window_at_entry:
            import chisurf.logging

            chisurf.logging.warning(
                "frozen_structure: a fit window changed during a run that declared it fixed."
            )


def _freezable_parameters(model) -> typing.List:
    """Return every parameter of a model whose read-path flags can be frozen.

    All of them, not just the free ones: a fixed or linked parameter is still
    *read* on every model evaluation (its value feeds the forward model), it
    simply is not varied.
    """
    out = list(getattr(model, "parameters_all", None) or [])
    if not out:
        out = list(getattr(model, "parameters", None) or [])
    return out


def frozen(*argument_names):
    """Decorate a function so its run holds the parameter structure fixed.

    Parameters
    ----------
    *argument_names : str
        Names of the decorated function's arguments that identify what to
        freeze (a fit, a group, or a model).

    Returns
    -------
    callable
        The decorator.
    """

    def decorate(function):
        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            bound = inspect.signature(function).bind_partial(*args, **kwargs)
            targets = [bound.arguments.get(name) for name in argument_names]
            with frozen_structure(*[t for t in targets if t is not None]):
                return function(*args, **kwargs)

        return wrapper

    return decorate


def _models_of(target) -> typing.List:
    """Return the models a freeze target covers (global model plus members)."""
    if target is None:
        return []
    out = []
    model = getattr(target, "model", None)
    global_model = getattr(target, "_model", None)
    if global_model is not None and getattr(global_model, "fits", None) is not None:
        out.append(global_model)
        for local in list(getattr(global_model, "fits", []) or []):
            local_model = getattr(local, "model", None)
            if local_model is not None:
                out.append(local_model)
    elif getattr(target, "fits", None) is not None:
        # A global model was passed directly.
        out.append(target)
        for local in list(getattr(target, "fits", []) or []):
            local_model = getattr(local, "model", None)
            if local_model is not None:
                out.append(local_model)
    elif model is not None:
        out.append(model)
    elif hasattr(target, "parameters"):
        out.append(target)
    return out


def parameter_key(parameter) -> str:
    """Return a stable string key identifying a parameter.

    Prefers the parameter's ``unique_identifier`` so that a key survives
    pickling and can be written to a chain's metadata; falls back to an
    ``id()``-derived key for objects that predate the identifier (test doubles,
    bare parameters).

    Parameters
    ----------
    parameter : chisurf.core.parameter.Parameter
        Parameter to key.

    Returns
    -------
    str
        The key.
    """
    uid = getattr(parameter, "unique_identifier", None)
    if uid:
        return str(uid)
    meta = getattr(parameter, "meta_data", None)
    if isinstance(meta, dict) and meta.get("unique_identifier"):
        return str(meta["unique_identifier"])
    return f"obj:{id(parameter):x}"


def resolve_root(parameter):
    """Follow a parameter's link chain to the parameter that actually varies.

    A linked parameter is not free: its value is that of its link target, so it
    is the *target* that appears in the objective's parameter vector and the
    target that a factor depends on. Cycles cannot normally occur
    (``Parameter.link`` rejects them) but are broken defensively.

    Parameters
    ----------
    parameter : chisurf.core.parameter.Parameter
        Parameter to resolve.

    Returns
    -------
    chisurf.core.parameter.Parameter
        The free root of the link chain, or ``parameter`` itself when unlinked.
    """
    seen = {id(parameter)}
    current = parameter
    while getattr(current, "is_linked", False):
        nxt = getattr(current, "link", None)
        if nxt is None or id(nxt) in seen:
            break
        seen.add(id(nxt))
        current = nxt
    return current


@dataclasses.dataclass(frozen=True)
class VariableNode:
    """One free parameter of a fit — a variable of the posterior.

    Attributes
    ----------
    key : str
        Stable identifier (see :func:`parameter_key`).
    name : str
        Human-readable parameter name, as shown in ``parameter_names``.
    index : int
        Position in the model's flat free-parameter vector, so the graph and
        ``model.parameter_values`` stay aligned.
    fit_index : int or None
        Index of the local fit the parameter belongs to, or ``None`` for a
        global parameter (and for a plain, ungrouped fit).
    """

    key: str
    name: str
    index: int
    fit_index: typing.Optional[int] = None


@dataclasses.dataclass(frozen=True)
class FactorNode:
    """One factor of the posterior — a dataset likelihood or a prior.

    Attributes
    ----------
    key : str
        Stable identifier of the factor.
    kind : str
        :data:`LIKELIHOOD` or :data:`PRIOR`.
    scope : tuple of str
        Keys of the variables this factor depends on.
    fit_index : int or None
        Index of the local fit for a likelihood factor; ``None`` for a prior.
    size : int
        Number of residuals the factor contributes — a model's ``n_points`` for
        a likelihood, ``1`` for a prior. Used to weight cost estimates.
    """

    key: str
    kind: str
    scope: typing.Tuple[str, ...]
    fit_index: typing.Optional[int] = None
    size: int = 0


class FactorGraph:
    """The variables and factors of a fit's posterior, with graph queries.

    Construct via :func:`build_factor_graph` rather than directly.

    Parameters
    ----------
    variables : sequence of VariableNode
        The free parameters, in the order of the model's parameter vector.
    factors : sequence of FactorNode
        The likelihood and prior factors.
    version : int, optional
        Value of :func:`structure_version` this graph was built at.
    """

    def __init__(
        self,
        variables: typing.Sequence[VariableNode],
        factors: typing.Sequence[FactorNode],
        version: int = 0,
    ):
        """Initialise the graph from its variable and factor nodes."""
        self.variables: typing.Dict[str, VariableNode] = {v.key: v for v in variables}
        self.factors: typing.Dict[str, FactorNode] = {f.key: f for f in factors}
        self.version = int(version)

        #: variable key -> position in the flat parameter vector
        self._index_of: typing.Dict[str, int] = {v.key: v.index for v in variables}
        #: position in the flat parameter vector -> variable key
        self._key_at: typing.Dict[int, str] = {v.index: v.key for v in variables}
        #: variable key -> keys of the factors it appears in
        incidence: typing.Dict[str, typing.List[str]] = {v.key: [] for v in variables}
        for f in factors:
            for key in f.scope:
                if key in incidence:
                    incidence[key].append(f.key)
        self._incidence = {k: tuple(v) for k, v in incidence.items()}

        #: The graph queries themselves, in C++ -- see :attr:`engine`.
        self._engine = None
        self.fit_graph = None

    # -- the engine -------------------------------------------------------

    @property
    def engine(self):
        """The same graph, as an :class:`IMP.bff.InferenceFactorGraph`.

        **Every structural query below is answered here rather than in
        Python.** Moralisation, greedy elimination, the cliques, the junction
        tree, the separators, the sampling blocks and the relevance queries
        are one implementation, in C++, ported from the Python this module
        used to carry (`IMP/bff/FactorGraph.h`). What stays on this side is
        what is genuinely ChiSurf's: *what a variable is* -- which parameter,
        at which position of which model's vector -- and *what a factor is*.
        Discovery is the application's knowledge; triangulating a graph is
        not, and two implementations of it would be two answers to
        "are these datasets independent?".

        Built on first use and dropped by :meth:`invalidate`. The engine
        caches its own derived structure, so this property is the whole of
        the caching this class needs. The same graph carries exact
        linear-Gaussian inference: ``IMP.bff.InferenceGaussianElimination``
        runs variable elimination over it.
        """
        if self._engine is None:
            self._engine = _build_engine(self.variables, self.factors)
        return self._engine

    # -- basic accessors --------------------------------------------------

    def __len__(self) -> int:
        """Return the number of variables (free parameters)."""
        return len(self.variables)

    def __repr__(self) -> str:
        """Return a compact summary of the graph's size and difficulty."""
        n_like = sum(1 for f in self.factors.values() if f.kind == LIKELIHOOD)
        n_prior = sum(1 for f in self.factors.values() if f.kind == PRIOR)
        return (
            f"FactorGraph({len(self.variables)} variables, "
            f"{n_like} likelihood + {n_prior} prior factors, "
            f"treewidth={self.treewidth})"
        )

    def key_at(self, index: int) -> typing.Optional[str]:
        """Return the variable key at a position of the flat parameter vector."""
        return self._key_at.get(int(index))

    def index_of(self, key: str) -> typing.Optional[int]:
        """Return the flat-parameter-vector position of a variable key."""
        return self._index_of.get(key)

    def factors_of(self, key: str) -> typing.Tuple[str, ...]:
        """Return the keys of the factors a variable appears in."""
        return self._incidence.get(key, ())

    def variables_of(self, factor_key: str) -> typing.Tuple[str, ...]:
        """Return the scope (variable keys) of a factor."""
        factor = self.factors.get(factor_key)
        return factor.scope if factor is not None else ()

    def likelihood_factors(self) -> typing.List[FactorNode]:
        """Return the likelihood factors, ordered by local-fit index."""
        out = [f for f in self.factors.values() if f.kind == LIKELIHOOD]
        out.sort(key=lambda f: f.fit_index if f.fit_index is not None else -1)
        return out

    # -- structure --------------------------------------------------------

    def invalidate(self) -> None:
        """Drop every cached derived structure.

        The moral graph, the elimination orders and the cliques derived from
        them are cached by :attr:`engine` for the lifetime of an unmutated
        graph; dropping the engine drops all of them together.
        """
        self._engine = None

    def connected_components(self) -> typing.List[typing.Set[str]]:
        """Return the independent sub-problems of the fit.

        Variables in different components share no factor, so their posteriors
        are independent and they can be optimised, scanned or sampled entirely
        separately. Components are returned largest first.

        Returns
        -------
        list of set of str
            One set of variable keys per component.
        """
        return [set(c) for c in self.engine.connected_components()]

    def elimination_order(self, heuristic: str = "min_fill") -> typing.List[str]:
        """Return a greedy variable-elimination order.

        Parameters
        ----------
        heuristic : {"min_fill", "min_degree", "weighted"}, optional
            ``min_fill`` repeatedly eliminates the variable whose elimination
            adds the fewest new edges; ``min_degree`` the one with the fewest
            neighbours; ``weighted`` is a mature toolkit's default
            triangulation (simplicial variables first, then the smallest clique
            dimension). ``min_fill`` gives narrower decompositions in practice
            and is the default; ties break on the variable's vector index so the
            order is deterministic.

        Returns
        -------
        list of str
            Variable keys in elimination order.

        Raises
        ------
        ValueError
            If ``heuristic`` is not recognised.
        """
        if heuristic not in ("min_fill", "min_degree", "weighted"):
            raise ValueError(
                f"unknown elimination heuristic {heuristic!r}; "
                "expected 'min_fill', 'min_degree' or 'weighted'"
            )
        return list(self.engine.get_elimination_order(heuristic))

    def cliques(self) -> typing.List[typing.Tuple[str, ...]]:
        """Return the maximal cliques induced by the elimination order.

        Each eliminated variable together with its then-remaining neighbours
        forms a clique of the triangulated graph. Non-maximal cliques (those
        contained in another) are dropped, which is what makes the result a
        valid clique set for a junction tree.

        Returns
        -------
        list of tuple of str
            Maximal cliques, each a sorted tuple of variable keys, largest
            first.
        """
        # Sorted by *key*, which is this class's documented contract and what
        # a caller using a clique as a dict key or a graph node relies on. The
        # engine orders a clique's members by their flat-vector position
        # instead -- also canonical, and the more useful of the two for a C++
        # caller lining a clique up against a parameter array.
        return [tuple(sorted(c)) for c in self.engine.get_cliques()]

    def junction_tree(self) -> cg.Graph:
        """Return a junction (clique) tree of the fit.

        Nodes are the maximal cliques of :meth:`cliques` (as sorted tuples);
        each edge carries a ``separator`` attribute holding the variables the
        two cliques share. The tree is the maximum-weight spanning tree of the
        clique graph weighted by separator size, which is the standard
        construction guaranteeing the running-intersection property.

        Returns
        -------
        chisurf.core.graph.Graph
            One node per maximal clique. Disconnected fits give a forest.
        """
        cliques = self.cliques()
        tree = cg.Graph()
        tree.add_nodes_from(cliques)
        # Edges index into the engine's clique list, so they are read against
        # it rather than against the key-sorted one above.
        engine_cliques = [tuple(sorted(c)) for c in self.engine.get_cliques()]
        for edge in self.engine.get_junction_tree_edges():
            a = engine_cliques[edge.first]
            b = engine_cliques[edge.second]
            tree.add_edge(a, b, weight=len(edge.separator))
            tree[a][b]["separator"] = tuple(sorted(edge.separator))
        return tree

    @property
    def treewidth(self) -> int:
        """Return ``max clique size - 1`` -- the fit's structural difficulty.

        The cost of exact marginalisation is exponential in this number, and it
        is also the dimension a blocked sampler would have to move jointly. A
        star-shaped global fit (many datasets, a few shared globals) has a small
        treewidth however many datasets it holds; a single dataset whose
        likelihood couples all its parameters has ``n_free - 1``.
        """
        return int(self.engine.get_treewidth())

    def blocks(self) -> typing.List[typing.Tuple[str, ...]]:
        """Return clique-derived blocks for joint sampling or scanning.

        Alias of :meth:`cliques` kept as the name a sampler should reach for:
        moving a whole clique at once is what turns a badly-mixing
        high-dimensional random walk into a set of low-dimensional ones.
        """
        return self.cliques()

    def sampling_blocks(self) -> typing.List[typing.Tuple[str, ...]]:
        """Return a partition of the variables for block-wise sampling.

        Variables are grouped by their **likelihood-factor neighbourhood**: two
        variables land in the same block exactly when the same set of datasets
        depends on both. Unlike :meth:`cliques` this is a true partition, which
        is what a block sampler needs, and it is the right one on two counts at
        once:

        *Cost.* Every block move costs exactly the datasets in its shared
        neighbourhood, so under the selective update of
        :class:`~chisurf.core.models.global_model.globalfit.GlobalFitModel` a
        star-shaped global fit yields one cheap block per dataset (one local
        model each) plus one expensive block for the shared parameters, instead
        of every proposal paying for every dataset.

        *Statistics.* Variables constrained by the same data are the ones that
        are actually correlated, and are therefore the ones that should move
        together.

        A single :class:`~chisurf.core.fitting.fit.Fit` has one neighbourhood
        and so one block, and a block sampler over it degenerates gracefully to
        an ordinary full-vector random walk.

        Returns
        -------
        list of tuple of str
            Disjoint blocks covering every variable, cheapest (fewest datasets)
            first so that a sweep front-loads the inexpensive moves. Variables
            no likelihood touches are grouped last.
        """
        # Block *members* keep the engine's order, which is flat-vector
        # position -- unlike a clique, a sampling block is consumed as a slice
        # of the parameter vector, so that is the order its callers want.
        return [tuple(b) for b in self.engine.get_sampling_blocks()]

    def block_cost(self, block: typing.Iterable[str]) -> int:
        """Return how many local fits a move of *block* must recompute.

        Parameters
        ----------
        block : iterable of str
            Variable keys moved together.

        Returns
        -------
        int
            Number of likelihood factors that would have to be re-evaluated.
        """
        return int(self.engine.block_cost([str(k) for k in block]))

    def separators(self) -> typing.List[typing.Tuple[str, ...]]:
        """Return the distinct separators of the junction tree.

        The separator of a global fit is the set of parameters its datasets
        genuinely share: condition on it and the datasets become independent.
        """
        return [tuple(sorted(sep)) for sep in self.engine.get_separators()]

    # -- relevance --------------------------------------------------------

    def affected_factors(self, changed: typing.Iterable[str]) -> typing.Set[str]:
        """Return the factors that must be re-evaluated for a set of changes.

        Parameters
        ----------
        changed : iterable of str
            Keys of the variables whose values changed.

        Returns
        -------
        set of str
            Keys of the factors whose scope intersects ``changed``.
        """
        return set(self.engine.affected_factors([str(k) for k in changed]))

    def affected_fits(self, changed: typing.Iterable[str]) -> typing.List[int]:
        """Return the local fits that must be recomputed for a set of changes.

        This is the query that makes a global objective proportional to what
        actually moved rather than to the number of datasets.

        Parameters
        ----------
        changed : iterable of str
            Keys of the variables whose values changed.

        Returns
        -------
        list of int
            Sorted indices of the local fits whose likelihood factor depends on
            at least one changed variable.
        """
        return [int(i) for i in self.engine.affected_fits([str(k) for k in changed])]

    def unexplained_variables(self) -> typing.Set[str]:
        """Return the variables no likelihood factor depends on.

        Such a variable is free but, as far as the graph can tell, reaches no
        data. Either it genuinely does nothing, or a model couples it to its
        datasets by some route the graph does not model (something other than
        parameter links). A caller using :meth:`affected_fits` to *skip* work
        must treat a change to one of these conservatively and recompute
        everything, rather than trusting an empty answer.

        Returns
        -------
        set of str
            Keys of the variables absent from every likelihood scope.
        """
        return set(self.engine.get_unexplained_variables())

    def affected_fits_from_indices(self, indices: typing.Iterable[int]) -> typing.List[int]:
        """Like :meth:`affected_fits`, but keyed by parameter-vector position.

        Parameters
        ----------
        indices : iterable of int
            Positions in the model's flat free-parameter vector.

        Returns
        -------
        list of int
            Sorted indices of the local fits that must be recomputed.
        """
        keys = [self._key_at[i] for i in indices if i in self._key_at]
        return self.affected_fits(keys)

    # -- reporting --------------------------------------------------------

    def describe(self) -> str:
        """Return a short human-readable structure report.

        Renders the counts, the treewidth, the separators and the independent
        components — the identifiability statement a global fit exists to make.

        Returns
        -------
        str
            A multi-line report.
        """
        names = {k: v.name for k, v in self.variables.items()}
        lines = [
            f"variables      : {len(self.variables)}",
            f"likelihoods    : {len(self.likelihood_factors())}",
            f"treewidth      : {self.treewidth}",
        ]
        comps = self.connected_components()
        lines.append(f"components     : {len(comps)}")
        seps = [s for s in self.separators() if s]
        if seps:
            shared = ", ".join("{" + ", ".join(names.get(k, k) for k in s) + "}" for s in seps)
            lines.append(f"separators     : {shared}")
        else:
            lines.append("separators     : (none — no shared parameters)")
        return "\n".join(lines)


def _build_engine(variables, factors):
    """Mirror the variables and factors onto an :class:`IMP.bff.InferenceFactorGraph`.

    One direction only, and once: the engine is rebuilt rather than mutated,
    because :meth:`FactorGraph.invalidate` drops it and a graph whose
    structure changed is a different graph. Keys, names, vector positions and
    factor scopes cross verbatim -- ``None`` becoming ``-1`` for a fit index
    is the only translation, and it is the same convention the C++ documents.

    A factor's scope is filtered to variables the graph actually holds. The
    engine refuses a scope naming an unknown variable, and rightly; the
    Python builders have always tolerated one (a prior on a parameter that is
    not free, say), so they are filtered here.
    """
    import IMP.bff as _bff

    engine = _bff.InferenceFactorGraph()
    for v in variables.values():
        engine.add_variable(
            v.key, v.name, int(v.index), -1 if v.fit_index is None else int(v.fit_index)
        )
    for f in factors.values():
        scope = [k for k in f.scope if k in variables]
        engine.add_factor(
            f.key,
            _bff.INFERENCE_FACTOR_LIKELIHOOD
            if f.kind == LIKELIHOOD
            else _bff.INFERENCE_FACTOR_PRIOR,
            scope,
            -1 if f.fit_index is None else int(f.fit_index),
            int(f.size),
        )
    return engine


def _free_variables(model) -> typing.List[VariableNode]:
    """Build the variable nodes from a model's free-parameter vector."""
    variables: typing.List[VariableNode] = []
    parameters = list(getattr(model, "parameters", []))
    names = list(getattr(model, "parameter_names", []))
    for i, p in enumerate(parameters):
        name = names[i] if i < len(names) else str(getattr(p, "name", i))
        variables.append(
            VariableNode(
                key=parameter_key(p),
                name=str(name),
                index=i,
                fit_index=None,
            )
        )
    return variables


def _prior_factors(model, known: typing.Set[str]) -> typing.List[FactorNode]:
    """Build one factor per free parameter carrying more than its bounds."""
    from chisurf.core.fitting.fit import _smooth_prior

    factors: typing.List[FactorNode] = []
    for p in getattr(model, "parameters", []):
        key = parameter_key(p)
        if key not in known:
            continue
        if _smooth_prior(p) is None:
            # A bare box is a support constraint, not a coupling: it adds no
            # edge and no factor the relevance query needs to know about.
            continue
        factors.append(
            FactorNode(
                key=f"prior:{key}",
                kind=PRIOR,
                scope=(key,),
                fit_index=None,
                size=1,
            )
        )
    return factors


def _local_scope(local_fit, known: typing.Set[str]) -> typing.Tuple[str, ...]:
    """Return the free variables one local fit's likelihood depends on.

    Every non-fixed parameter of the local model is resolved through its link
    chain to the parameter that actually varies — which may be a global
    parameter or a parameter owned by another local fit. That resolved set,
    intersected with the global model's free-parameter vector, is the factor's
    scope.
    """
    model = getattr(local_fit, "model", None)
    if model is None:
        return ()
    scope: typing.Set[str] = set()
    for p in getattr(model, "parameters_all", []):
        if getattr(p, "fixed", False):
            continue
        root = resolve_root(p)
        if getattr(root, "fixed", False):
            continue
        key = parameter_key(root)
        if key in known:
            scope.add(key)
    return tuple(sorted(scope))


def posterior_model(fit):
    """Return the model whose parameter vector *is* the posterior's.

    :attr:`~chisurf.core.fitting.fit.FitGroup.model` is the model of the
    currently *selected* local fit, not the global one — the global model lives
    on ``_model`` and is the thing that owns the joint parameter vector a global
    optimisation or sampling run moves. Picking the wrong one silently describes
    a single dataset instead of the group.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        The fit (or fit group).

    Returns
    -------
    chisurf.core.models.Model or None
        The global model for a group holding local fits, else the fit's own.
    """
    global_model = getattr(fit, "_model", None)
    if global_model is not None and getattr(global_model, "fits", None):
        return global_model
    return getattr(fit, "model", None)


def _derived_fit_graph(fit, model):
    """The factor graph of the objective this fit optimises, read off its nodes.

    ``IMP.bff.get_fit_factor_graph`` walks the native objective: a likelihood
    per dataset over the parameters its model actually reads, followers joined
    to their masters by link factors, held parameters kept as evidence. ``None``
    when the fit has no native objective (the director path), which then keeps
    the declared construction below.
    """
    try:
        import IMP.bff as bff

        from chisurf.core.fitting.minimizer import graph_objective
    except ImportError:
        return None
    built = graph_objective(fit, model)
    if built is None:
        return None
    minimizer, _free = built
    pairs = getattr(minimizer, "_parameter_ports", None)
    if not pairs:
        return None
    keys, ports, seen = [], [], set()
    for parameter, port in pairs:
        key = parameter_key(parameter)
        if key in seen or port is None:
            continue
        seen.add(key)
        keys.append(key)
        ports.append(port)
    graph = bff.get_fit_factor_graph(minimizer._sampler_surface[0], keys, ports)
    graph._keep = minimizer
    return graph


def build_factor_graph(fit, model=None) -> FactorGraph:
    """Build the factor graph of a fit.

    For a :class:`~chisurf.core.fitting.fit.FitGroup` this yields one likelihood
    factor per local fit, whose scope is that fit's non-fixed parameters
    resolved through their links, plus one prior factor per parameter carrying
    an informative prior. For a plain :class:`~chisurf.core.fitting.fit.Fit`
    there is a single likelihood factor over all free parameters — a single
    clique, which is the honest structure of a one-dataset problem.

    Parameters
    ----------
    fit : chisurf.core.fitting.fit.Fit
        The fit (or fit group) to describe. May be ``None`` when ``model`` is
        given.
    model : chisurf.core.models.Model, optional
        Model to describe. Defaults to :func:`posterior_model` of ``fit``; pass
        it explicitly from inside a model that is building its own graph.

    Returns
    -------
    FactorGraph
        The graph, tagged with the current :func:`structure_version`.
    """
    if model is None:
        model = posterior_model(fit)
    if model is None:
        return FactorGraph([], [], version=structure_version())

    variables = _free_variables(model)
    known = set(v.key for v in variables)
    factors: typing.List[FactorNode] = []

    local_fits = list(getattr(model, "fits", []) or [])
    derived = _derived_fit_graph(fit, model) if fit is not None else None
    if derived is not None:
        import IMP.bff as bff

        for factor_key in derived.get_factor_keys():
            if derived.get_factor_kind(factor_key) != bff.INFERENCE_FACTOR_LIKELIHOOD:
                continue
            index = len(factors)
            local_model = getattr(local_fits[index], "model", None) if local_fits else model
            factors.append(
                FactorNode(
                    key=f"L{index}",
                    kind=LIKELIHOOD,
                    scope=tuple(k for k in derived.variables_of(factor_key) if k in known),
                    fit_index=index,
                    size=int(getattr(local_model, "n_points", 0) or 0),
                )
            )
        if local_fits:
            owner: typing.Dict[str, int] = {}
            for i, local in enumerate(local_fits):
                for p in getattr(getattr(local, "model", None), "parameters", []):
                    key = parameter_key(p)
                    if key in known:
                        owner.setdefault(key, i)
            variables = [dataclasses.replace(v, fit_index=owner.get(v.key)) for v in variables]
    elif local_fits:
        # Global fit: one likelihood per dataset, and tag each variable with the
        # local fit that owns it (globals and cross-linked masters keep None).
        owner: typing.Dict[str, int] = {}
        for i, local in enumerate(local_fits):
            scope = _local_scope(local, known)
            local_model = getattr(local, "model", None)
            factors.append(
                FactorNode(
                    key=f"L{i}",
                    kind=LIKELIHOOD,
                    scope=scope,
                    fit_index=i,
                    size=int(getattr(local_model, "n_points", 0) or 0),
                )
            )
            for p in getattr(local_model, "parameters", []):
                key = parameter_key(p)
                if key in known:
                    owner.setdefault(key, i)
        variables = [dataclasses.replace(v, fit_index=owner.get(v.key)) for v in variables]
    else:
        factors.append(
            FactorNode(
                key="L0",
                kind=LIKELIHOOD,
                scope=tuple(sorted(known)),
                fit_index=0,
                size=int(getattr(model, "n_points", 0) or 0),
            )
        )

    factors.extend(_prior_factors(model, known))
    graph = FactorGraph(variables, factors, version=structure_version())
    #: The whole fit as the optimiser sees it -- held parameters and links
    #: included -- for a view; ``None`` when there is no native objective.
    graph.fit_graph = derived
    return graph
