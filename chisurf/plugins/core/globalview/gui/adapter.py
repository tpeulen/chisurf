from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from chinet import graph as cg

from chisurf.plugins.core.globalview.api.graph import build_graph, GraphResult


NODE_COLORS = {
    0: [0, 0, 128, 255],    # fit
    1: [0, 128, 0, 128],    # parameter fixed
    2: [0, 128, 0, 255],    # parameter linked
    3: [128, 0, 128, 255],  # parameter free
    4: [180, 95, 6, 255],   # out-of-fit group owner (plugin working model)
}


def compute_node_types(
    result: GraphResult,
    include_fixed: bool = True,
) -> List[int]:
    """Map each node to its type code for color-coding.

    Returns
    -------
    list of int
        0=fit, 1=fixed parameter, 2=linked parameter, 3=free parameter.
    """
    types = []
    for n in result.nodes:
        if n.node_type == "fit":
            types.append(0)
        elif n.node_type == "group":
            types.append(4)
        else:
            if n.fixed:
                types.append(1)
            elif n.is_linked:
                types.append(2)
            else:
                types.append(3)
    return types


def graph_result_to_graph(result: GraphResult) -> cg.Graph:
    """Convert a GraphResult to a :class:`chinet.graph.Graph` for layout."""
    G = cg.Graph()
    for n in result.nodes:
        G.add_node(n.node_idx, **{
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
        })
    for e in result.edges:
        G.add_edge(e.source, e.target)
    return G


def compute_layout(G: cg.Graph, layout: str = "kamada_kawai", scale: float = 1.0) -> Dict[int, Any]:
    """Compute node positions using the given layout algorithm.

    Parameters
    ----------
    G : chinet.graph.Graph
        Graph to lay out.
    layout : str, optional
        One of ``kamada_kawai``, ``shell``, ``arf``, ``spectral``; anything else
        falls back to a spring layout.
    scale : float, optional
        Half-width of the drawing.

    Returns
    -------
    dict
        Node index to ``(x, y)``.
    """
    if layout == "shell":
        return cg.shell_layout(G, scale=scale)
    elif layout == "kamada_kawai":
        return cg.kamada_kawai_layout(G, scale=scale)
    elif layout == "arf":
        return cg.arf_layout(G, etol=1e-9, dt=0.01, scale=scale)
    elif layout == "spectral":
        return cg.spectral_layout(G, scale=scale)
    else:
        return cg.spring_layout(G, iterations=500, scale=scale)
