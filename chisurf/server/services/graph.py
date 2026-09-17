from __future__ import annotations

from typing import Any

from chisurf.server.services import ServiceResult
from chisurf.server.session import SessionState


def _safe_float(val: Any) -> float | None:
    """Convert *val* to float, returning ``None`` on failure.

    Parameters
    ----------
    val : any
        Value to convert.

    """
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def build_fit_graph(
    state: SessionState,
    fit_indices: list[int] | None = None,
    fit_uids: list[str] | None = None,
    include_fixed: bool = True,
    connect_owners: bool = False,
) -> ServiceResult:
    """Build a graph from fits on the server, returning nodes and edges as JSON.

    Mirrors the client-side ``GraphWizard.build_graph()`` logic so the
    global-view wizard can work with pure DTO data.
    """
    fits = list(state.fits)
    selected = []

    if fit_uids:
        uid_set = set(fit_uids)
        for i, f in enumerate(fits):
            uid = str(getattr(f, "unique_identifier", ""))
            if uid in uid_set:
                selected.append((i, f))
    elif fit_indices:
        for i in fit_indices:
            if 0 <= i < len(fits):
                selected.append((i, fits[i]))
    else:
        selected = list(enumerate(fits))

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_idx = 0
    fit_node_ids: dict[int, int] = {}  # fit_index -> node_idx

    for fit_idx, fit in selected:
        fit_name = str(getattr(fit, "name", "fit"))
        try:
            data_filename = str(getattr(getattr(fit, "data", None), "filename", "") or "")
        except Exception:
            data_filename = ""
        try:
            model_module = getattr(fit.model.__class__, "__module__", "")
            model_class_name = getattr(fit.model.__class__, "__name__", "")
            model_full = f"{model_module}.{model_class_name}"
        except Exception:
            model_full = ""

        node = {
            "node_idx": node_idx,
            "node_type": "fit",
            "name": fit_name,
            "fit_idx": fit_idx,
            "data_filename": data_filename,
            "model": model_full,
        }
        node_id = node_idx
        nodes.append(node)
        fit_node_ids[fit_idx] = node_id
        node_idx += 1

        try:
            parameters = list(getattr(fit.model, "parameters_all", []) or [])
        except Exception:
            parameters = []

        for param in parameters:
            try:
                fixed = bool(getattr(param, "fixed", False))
            except Exception:
                fixed = False
            if fixed and not include_fixed:
                continue

            param_name = str(getattr(param, "name", "param"))
            param_value = _safe_float(getattr(param, "value", None))
            try:
                is_linked = bool(getattr(param, "is_linked", False))
            except Exception:
                is_linked = False
            try:
                link = getattr(param, "link", None)
                link_name = str(getattr(link, "name", "") or "")
                link_uid = str(getattr(link, "unique_identifier", "") or "")
            except Exception:
                link_name = ""
                link_uid = ""

            param_node = {
                "node_idx": node_idx,
                "node_type": "parameter",
                "name": param_name,
                "fit_idx": fit_idx,
                "value": param_value,
                "fixed": fixed,
                "is_linked": is_linked,
                "link_name": link_name,
                "link_uid": link_uid,
                "param_uid": str(getattr(param, "unique_identifier", "") or ""),
            }
            param_node_id = node_idx
            nodes.append(param_node)
            edges.append({"source": param_node_id, "target": node_id})
            node_idx += 1

    # Connect each linked parameter to the *one* parameter it follows. Resolved
    # by UUID; the name is only a fallback, and even then the first match wins.
    # Matching by name alone drew an edge to every same-named parameter in the
    # session — three fits of one model turned one link into three arrows, two
    # of them fiction.
    by_uid = {
        n["param_uid"]: n for n in nodes if n["node_type"] == "parameter" and n.get("param_uid")
    }
    by_name: dict[str, Any] = {}
    for n in nodes:
        if n["node_type"] == "parameter":
            by_name.setdefault(n["name"], n)

    for n in nodes:
        if n["node_type"] != "parameter" or not n.get("is_linked"):
            continue
        master = by_uid.get(n.get("link_uid", "")) if n.get("link_uid") else None
        if master is None and n.get("link_name"):
            master = by_name.get(n["link_name"])
        if master is not None and master["node_idx"] != n["node_idx"]:
            edges.append({"source": n["node_idx"], "target": master["node_idx"]})

    # Optional: connect every owner node to every other. "Owner" rather than
    # "fit" so a registered parameter group (a plugin's working model) joins the
    # same web instead of floating apart from the fits it can be linked to.
    if connect_owners:
        owners = [n for n in nodes if n["node_type"] in ("fit", "group")]
        for i, a in enumerate(owners):
            for b in owners[i + 1 :]:
                edges.append({"source": a["node_idx"], "target": b["node_idx"]})

    return {
        "ok": True,
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
    }
