"""Every fitting parameter in the session: as rows, as a network, as a factor graph.

Three views of one thing, built here from one enumeration so they cannot drift:

* :func:`parameter_rows` -- one :class:`ParameterRow` per parameter, owner by
  owner: every fit (a :class:`~chisurf.core.fitting.fit.FitGroup` by its local
  fits), then every registered out-of-fit parameter group (a plugin's working
  model). The aggregate global-fit model is left out: its parameters are its
  members' parameters, and listing them twice lists every link twice.
* :func:`build_parameter_network` -- owners and parameters as nodes, and three
  kinds of edge that make three different claims: *ownership* (a parameter
  belongs to its fit), *link* (a parameter follows another), *base* (two
  owners, drawn only when asked, to say what links can run between).
* :func:`build_session_factor_graph` -- the same parameters as a posterior: one
  likelihood factor per owner over the parameters it reads **resolved through
  their links**, so two datasets that share a lifetime are two factors over one
  variable. Its queries (shared variables, independent blocks) are the ones a
  global analysis is about.

There used to be three builders of the network -- the Global View window's,
its RPC backend's and the server's ``graph.build`` service -- each a copy of
the last with its own bug fixed, and a fourth enumeration of the rows in the
Global View's parameter table, which descended into fit groups when the
network did not. They all read this module now.

Nothing here imports Qt or talks over a socket; the objects are live.
"""

from __future__ import annotations

import dataclasses
import typing

__all__ = [
    "EDGE_BASE",
    "EDGE_LINK",
    "EDGE_OWNERSHIP",
    "NetworkEdge",
    "NetworkNode",
    "Owner",
    "ParameterNetwork",
    "ParameterRow",
    "build_parameter_network",
    "build_session_factor_graph",
    "parameter_rows",
    "session_owners",
]

#: A parameter belongs to its owner. Scaffolding.
EDGE_OWNERSHIP = "ownership"
#: A parameter follows another: the relation a global fit is made of.
EDGE_LINK = "link"
#: Two owners, joined only when asked (``connect_owners``). Visual only.
EDGE_BASE = "base"


def _uid(obj: typing.Any) -> str:
    return str(getattr(obj, "unique_identifier", "") or "")


def _float(value: typing.Any) -> typing.Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flag(obj: typing.Any, name: str) -> bool:
    try:
        return bool(getattr(obj, name, False))
    except Exception:  # noqa: BLE001 - a property that raises reads as unset
        return False


@dataclasses.dataclass(eq=False)
class Owner:
    """What parameters belong to: a fit, one local fit of a group, or a group.

    Attributes
    ----------
    kind : str
        ``"fit"`` or ``"group"`` (an out-of-fit registered group).
    label : str
        The fit's (or group's) name.
    local_label : str
        ``"[i]"`` for the *i*-th local fit of a :class:`FitGroup`, else empty.
    parameters : list
        The live parameters, in the model's order.
    fit_index : int or None
        Position of the fit in the session's fit list; ``None`` for a group.
    local_idx : int or None
        Position inside a :class:`FitGroup`.
    fit_uid, owner_uid, owner_id : str
        The fit's identifier, its model's (or the group's), and a group's
        registry id -- what an RPC addresses the owner by.
    data_filename, model : str
        Where the data came from and the model's dotted class name.
    """

    kind: str
    label: str
    local_label: str = ""
    parameters: list = dataclasses.field(default_factory=list)
    fit_index: typing.Optional[int] = None
    local_idx: typing.Optional[int] = None
    fit_uid: str = ""
    owner_uid: str = ""
    owner_id: str = ""
    data_filename: str = ""
    model: str = ""

    @property
    def title(self) -> str:
        """The label with its local index: ``"global fit [1]"``."""
        return f"{self.label} {self.local_label}".strip()


@dataclasses.dataclass(eq=False)
class ParameterRow:
    """One parameter and everything needed to address it.

    The positional order is the one the Global View's parameter table built
    its rows in, so that code reads this unchanged.
    """

    kind: str
    owner_label: str
    local_label: str
    param: typing.Any
    param_uid: str
    owner_uid: str = ""
    fit_uid: str = ""
    fit_index: typing.Optional[int] = None
    local_idx: typing.Optional[int] = None
    owner: typing.Optional[Owner] = None


def _parameters_of(model: typing.Any) -> list:
    try:
        return list(getattr(model, "parameters_all", []) or [])
    except Exception:  # noqa: BLE001
        return []


def _model_name(model: typing.Any) -> str:
    cls = type(model)
    return f"{getattr(cls, '__module__', '')}.{getattr(cls, '__name__', '')}"


def session_owners(
    fits: typing.Sequence[typing.Any],
    groups: typing.Sequence[tuple] = (),
    indices: typing.Optional[typing.Sequence[int]] = None,
) -> list[Owner]:
    """Every owner of fitting parameters, fits first, then registered groups.

    Parameters
    ----------
    fits : sequence
        The session's fits, in order: their positions are the ``fit_index``
        an RPC addresses them by.
    groups : sequence of (owner_id, label, group)
        Registered out-of-fit groups, as
        :func:`~chisurf.core.registry.parameter_groups.iter_registered_parameter_groups`
        returns them.
    indices : sequence of int, optional
        The session position of each of *fits*, when they are a selection;
        their own positions otherwise.

    Returns
    -------
    list of Owner
    """
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.global_model import GlobalFitModel

    owners: list[Owner] = []
    positions = list(indices) if indices is not None else list(range(len(fits)))
    for index, fit in zip(positions, fits):
        members = getattr(fit, "grouped_fits", None) if isinstance(fit, FitGroup) else None
        model = getattr(fit, "model", None)
        if not members and isinstance(model, GlobalFitModel):
            continue
        label = str(getattr(fit, "name", f"Fit {index}"))
        try:
            filename = str(getattr(getattr(fit, "data", None), "filename", "") or "")
        except Exception:  # noqa: BLE001
            filename = ""
        if members:
            for local, member in enumerate(members):
                local_model = getattr(member, "model", None)
                owners.append(
                    Owner(
                        "fit",
                        label,
                        f"[{local}]",
                        _parameters_of(local_model),
                        index,
                        local,
                        _uid(fit),
                        _uid(local_model),
                        "",
                        filename,
                        _model_name(local_model),
                    )
                )
            continue
        owners.append(
            Owner(
                "fit",
                label,
                "",
                _parameters_of(model),
                index,
                None,
                _uid(fit),
                _uid(model),
                "",
                filename,
                _model_name(model),
            )
        )
    for owner_id, label, group in groups or ():
        owners.append(
            Owner(
                "group",
                str(label),
                "",
                _parameters_of(group),
                None,
                None,
                "",
                _uid(group),
                str(owner_id),
            )
        )
    return owners


def parameter_rows(owners: typing.Sequence[Owner]) -> list[ParameterRow]:
    """One row per parameter, owner by owner."""
    return [
        ParameterRow(
            owner.kind,
            owner.label,
            owner.local_label,
            param,
            _uid(param),
            owner.owner_uid,
            owner.fit_uid,
            owner.fit_index,
            owner.local_idx,
            owner,
        )
        for owner in owners
        for param in owner.parameters
    ]


@dataclasses.dataclass
class NetworkNode:
    """An owner or a parameter, as the network draws it.

    ``node_idx`` numbers the nodes in order; ``node_id`` is what stays the same
    when the network is rebuilt -- ``"owner:<n>"`` or ``"param:<uid>"`` -- and
    what a selection is kept by.
    """

    node_idx: int
    node_type: str  # "fit", "group" or "parameter"
    name: str
    fit_idx: int
    node_id: str = ""
    value: typing.Optional[float] = None
    fixed: bool = False
    is_linked: bool = False
    link_name: str = ""
    link_uid: str = ""
    fit_name: str = ""
    data_filename: str = ""
    model: str = ""
    param_uid: str = ""
    owner_uid: str = ""
    owner_id: str = ""
    #: The owner's node index (parameters), for "which fit is this ``tau1``".
    owner_idx: int = -1
    #: The live object: the owner record, or the parameter.
    obj: typing.Any = dataclasses.field(default=None, repr=False, compare=False)


@dataclasses.dataclass
class NetworkEdge:
    """``source`` → ``target``: follower → master for a link, parameter → owner."""

    source: int
    target: int
    kind: str = EDGE_OWNERSHIP


@dataclasses.dataclass
class ParameterNetwork:
    """The parameter network: owners, parameters, and the edges between them."""

    nodes: list = dataclasses.field(default_factory=list)
    edges: list = dataclasses.field(default_factory=list)

    def by_id(self) -> dict:
        """``node_id -> node``."""
        return {n.node_id: n for n in self.nodes}

    def signature(self) -> tuple:
        """What decides where nodes go: ids, kinds, flags and edges -- not values.

        A running fit changes values every iteration and nothing else; a
        layout re-run for each of those moves nothing and costs a lot.
        """
        return (
            tuple((n.node_id, n.node_type, n.fixed, n.is_linked) for n in self.nodes),
            tuple(sorted((e.source, e.target, e.kind) for e in self.edges)),
        )

    def to_dict(self) -> dict:
        """The JSON the ``graph.build`` services answer with."""
        keys = (
            "node_idx",
            "node_type",
            "name",
            "fit_idx",
            "value",
            "fixed",
            "is_linked",
            "link_name",
            "link_uid",
            "fit_name",
            "data_filename",
            "model",
            "param_uid",
            "owner_uid",
            "owner_id",
        )
        return {
            "nodes": [{k: getattr(n, k) for k in keys} for n in self.nodes],
            "edges": [{"source": e.source, "target": e.target, "kind": e.kind} for e in self.edges],
        }

    def to_graph(self):
        """A :class:`chisurf.core.graph.Graph` of the network, for the layouts."""
        from chisurf.core import graph as cg

        graph = cg.Graph()
        for n in self.nodes:
            graph.add_node(
                n.node_idx,
                **{
                    "node.idx": n.node_idx,
                    "node.type": n.node_type,
                    "node.name": n.name,
                    "fit.idx": n.fit_idx,
                    "value": n.value,
                    "fixed": n.fixed,
                    "name": n.name,
                    "param.uid": n.param_uid,
                    "owner.uid": n.owner_uid,
                    "owner.id": n.owner_id,
                },
            )
        for e in self.edges:
            graph.add_edge(e.source, e.target)
        return graph


def build_parameter_network(
    owners: typing.Sequence[Owner],
    include_fixed: bool = True,
    connect_owners: bool = False,
) -> ParameterNetwork:
    """The network of the given owners.

    Parameters
    ----------
    owners : sequence of Owner
        From :func:`session_owners`.
    include_fixed : bool
        Keep parameters held fixed. Leaving them out is how a large global fit
        is made readable; their links go with them.
    connect_owners : bool
        Join every owner to every other -- fits *and* groups, so a plugin's
        working model sits with the fits it can be linked to.

    Returns
    -------
    ParameterNetwork

    Notes
    -----
    A link is drawn to the **one** parameter followed, found by its unique
    identifier; the name is consulted only for a master that carries none, and
    then the first match wins. Matching by name alone drew an arrow to every
    same-named parameter in the session -- three fits of one model made one
    link into three arrows, two of them fiction.
    """
    network = ParameterNetwork()
    for owner_number, owner in enumerate(owners):
        owner_idx = len(network.nodes)
        network.nodes.append(
            NetworkNode(
                owner_idx,
                "fit" if owner.kind == "fit" else "group",
                owner.title,
                owner.fit_index if owner.fit_index is not None else -1,
                node_id=f"owner:{owner_number}",
                fit_name=owner.title,
                data_filename=owner.data_filename,
                model=owner.model,
                owner_uid=owner.owner_uid,
                owner_id=owner.owner_id,
                obj=owner,
            )
        )
        for param in owner.parameters:
            fixed = _flag(param, "fixed")
            if fixed and not include_fixed:
                continue
            try:
                link = getattr(param, "link", None)
            except Exception:  # noqa: BLE001
                link = None
            uid = _uid(param)
            index = len(network.nodes)
            network.nodes.append(
                NetworkNode(
                    index,
                    "parameter",
                    str(getattr(param, "name", "param")),
                    owner.fit_index if owner.fit_index is not None else -1,
                    node_id=f"param:{uid or id(param)}",
                    value=_float(getattr(param, "value", None)),
                    fixed=fixed,
                    is_linked=_flag(param, "is_linked"),
                    link_name=str(getattr(link, "name", "") or "") if link is not None else "",
                    link_uid=_uid(link) if link is not None else "",
                    fit_name=owner.title,
                    param_uid=uid,
                    owner_uid=owner.owner_uid,
                    owner_id=owner.owner_id,
                    owner_idx=owner_idx,
                    obj=param,
                )
            )
            network.edges.append(NetworkEdge(index, owner_idx, EDGE_OWNERSHIP))

    parameters = [n for n in network.nodes if n.node_type == "parameter"]
    by_uid = {n.param_uid: n for n in parameters if n.param_uid}
    by_name: dict = {}
    for n in parameters:
        by_name.setdefault(n.name, n)
    for n in parameters:
        if not n.is_linked:
            continue
        master = by_uid.get(n.link_uid) if n.link_uid else None
        if master is None and n.link_name and not n.link_uid:
            master = by_name.get(n.link_name)
        if master is not None and master.node_idx != n.node_idx:
            network.edges.append(NetworkEdge(n.node_idx, master.node_idx, EDGE_LINK))

    if connect_owners:
        heads = [n for n in network.nodes if n.node_type in ("fit", "group")]
        for i, a in enumerate(heads):
            for b in heads[i + 1 :]:
                network.edges.append(NetworkEdge(a.node_idx, b.node_idx, EDGE_BASE))
    return network


def build_session_factor_graph(owners: typing.Sequence[Owner]):
    """The posterior the owners' parameters make: one likelihood per owner.

    Parameters
    ----------
    owners : sequence of Owner

    Returns
    -------
    chisurf.core.fitting.factorgraph.FactorGraph
        Variables are the free parameters that are not links -- the roots
        :func:`~chisurf.core.fitting.factorgraph.resolve_root` reaches; each
        owner's likelihood is over the roots of the parameters it reads, held
        ones left out. Two datasets sharing a lifetime are two factors over one
        variable, and a follower is no variable at all.

    Notes
    -----
    An owner none of whose parameters are free still gets a factor, with an
    empty scope: the data is there, it just constrains nothing, and a picture
    that dropped it would hide a fit someone forgot to free.
    """
    from chisurf.core.fitting import factorgraph as fg

    variables: dict = {}
    factors = []
    for number, owner in enumerate(owners):
        scope: list = []
        for param in owner.parameters:
            root = fg.resolve_root(param)
            if _flag(root, "fixed"):
                continue
            key = fg.parameter_key(root)
            if key not in variables:
                variables[key] = fg.VariableNode(
                    key=key,
                    name=str(getattr(root, "name", key)),
                    index=len(variables),
                    fit_index=owner.fit_index,
                )
            if key not in scope:
                scope.append(key)
        factors.append(
            fg.FactorNode(
                key=f"likelihood:{number}",
                kind=fg.LIKELIHOOD,
                scope=tuple(scope),
                fit_index=number,
                size=max(len(owner.parameters), 1),
            )
        )
    return fg.FactorGraph(list(variables.values()), factors, version=fg.structure_version())
