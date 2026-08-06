from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class GraphNode:
    node_idx: int
    node_type: str  # "fit", "group" (out-of-fit owner) or "parameter"
    name: str
    fit_idx: int
    value: Optional[float] = None
    fixed: bool = False
    is_linked: bool = False
    link_name: str = ""
    #: Global UUID of the parameter this one is linked *to*. Matching by name
    #: alone drew an edge to every same-named parameter in every fit — three
    #: fits with a ``tau1`` each produced three edges from one link — so the
    #: identity of the master is carried explicitly and the name is only a
    #: fallback for graphs read back from GraphML.
    link_uid: str = ""
    fit_name: str = ""
    data_filename: str = ""
    model: str = ""
    #: Global UUID of the parameter (parameter nodes) — lets callers resolve the
    #: live object via ``Base.find_by_uuid`` regardless of owner (fit or group).
    param_uid: str = ""
    #: Global UUID of the owning model/group (owner and parameter nodes).
    owner_uid: str = ""
    #: Stable registry id for out-of-fit group owners (empty for fits).
    owner_id: str = ""


@dataclass
class GraphEdge:
    source: int
    target: int


@dataclass
class GraphResult:
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)


def _safe_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _model_of(owner: Any) -> Any:
    """Return the parameter group of an owner (a fit's ``model`` or the group)."""
    model = getattr(owner, "model", None)
    return model if model is not None else owner


def build_graph(
    fit_list: List[Any],
    include_fixed: bool = True,
    connect_owners: bool = False,
    skip_global_fit: bool = True,
    group_list: Optional[List[Any]] = None,
) -> GraphResult:
    """Build a graph representation from fits and out-of-fit groups.

    Parameters
    ----------
    fit_list : list
        List of fit objects (Fit or FitGroup).
    include_fixed : bool
        Whether to include fixed parameters.
    connect_owners : bool
        Whether to join every **owner** node — every fit *and* every registered
        parameter group — to every other. It used to join fits only, which left
        a plugin's working model (ndX, a calculator) floating apart from the
        fits it is there to be linked against: the one relation the option
        exists to make visible was the one it did not draw.
    skip_global_fit : bool
        Whether to skip fits with GlobalFitModel.
    group_list : list, optional
        Out-of-fit owners as ``(owner_id, label, group)`` tuples (e.g. from the
        parameter-group registry). Rendered as ``"group"`` owner nodes with their
        parameters, so plugin parameters appear in the graph and their links to
        fit parameters draw as edges.

    Returns
    -------
    GraphResult
        Dataclass with nodes and edges.
    """
    from chisurf.core.models.global_model import GlobalFitModel

    result = GraphResult()
    counter = {"idx": 0}

    def _uid(obj) -> str:
        return str(getattr(obj, "unique_identifier", "") or "")

    def _add_owner(
        node_type: str, name: str, fit_idx: int, group: Any,
        *, owner_uid: str = "", owner_id: str = "",
        data_filename: str = "", model_full: str = "",
    ) -> None:
        node_id = counter["idx"]
        result.nodes.append(GraphNode(
            node_idx=node_id, node_type=node_type, name=name, fit_idx=fit_idx,
            fit_name=name, data_filename=data_filename, model=model_full,
            owner_uid=owner_uid, owner_id=owner_id,
        ))
        counter["idx"] += 1
        try:
            parameters = list(getattr(group, "parameters_all", []) or [])
        except Exception:
            parameters = []
        for param in parameters:
            try:
                fixed = bool(getattr(param, "fixed", False))
            except Exception:
                fixed = False
            if fixed and not include_fixed:
                continue
            try:
                is_linked = bool(getattr(param, "is_linked", False))
            except Exception:
                is_linked = False
            try:
                link = getattr(param, "link", None)
                link_name = str(getattr(link, "name", "") or "")
                link_uid = _uid(link) if link is not None else ""
            except Exception:
                link_name = ""
                link_uid = ""
            pid = counter["idx"]
            result.nodes.append(GraphNode(
                node_idx=pid, node_type="parameter",
                name=str(getattr(param, "name", "param")), fit_idx=fit_idx,
                value=_safe_float(getattr(param, "value", None)), fixed=fixed,
                is_linked=is_linked, link_name=link_name, link_uid=link_uid,
                param_uid=_uid(param), owner_uid=owner_uid, owner_id=owner_id,
            ))
            result.edges.append(GraphEdge(source=pid, target=node_id))
            counter["idx"] += 1

    for fi, fit in enumerate(fit_list):
        if skip_global_fit and isinstance(getattr(fit, "model", None), GlobalFitModel):
            continue
        fit_name = str(getattr(fit, "name", f"fit_{fi}"))
        try:
            data_filename = str(getattr(getattr(fit, "data", None), "filename", "") or "")
        except Exception:
            data_filename = ""
        try:
            model_full = (
                f"{getattr(fit.model.__class__, '__module__', '')}."
                f"{getattr(fit.model.__class__, '__name__', '')}"
            )
        except Exception:
            model_full = ""
        _add_owner(
            "fit", fit_name, fi, _model_of(fit),
            owner_uid=_uid(_model_of(fit)),
            data_filename=data_filename, model_full=model_full,
        )

    # Out-of-fit registered groups (plugin working models).
    for owner_id, label, group in (group_list or []):
        _add_owner(
            "group", str(label), -1, _model_of(group),
            owner_uid=_uid(_model_of(group)), owner_id=str(owner_id),
        )

    # Connect each linked parameter to the *one* parameter it follows. Resolved
    # by UUID; the name is only consulted when the master carries no UUID, and
    # even then the first match wins rather than all of them.
    by_uid = {
        n.param_uid: n for n in result.nodes
        if n.node_type == "parameter" and n.param_uid
    }
    by_name: Dict[str, GraphNode] = {}
    for n in result.nodes:
        if n.node_type == "parameter":
            by_name.setdefault(n.name, n)

    for n in result.nodes:
        if n.node_type != "parameter" or not n.is_linked:
            continue
        master = by_uid.get(n.link_uid) if n.link_uid else None
        if master is None and n.link_name:
            master = by_name.get(n.link_name)
        if master is not None and master.node_idx != n.node_idx:
            result.edges.append(GraphEdge(source=n.node_idx, target=master.node_idx))

    # Optional: connect every owner — fits and registered groups alike.
    if connect_owners:
        owners = [n for n in result.nodes if n.node_type in ("fit", "group")]
        for i, a in enumerate(owners):
            for b in owners[i + 1:]:
                result.edges.append(GraphEdge(source=a.node_idx, target=b.node_idx))

    return result
