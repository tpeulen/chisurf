"""The Global View's graph: the session's parameter network.

The builder lives in :mod:`chisurf.core.fitting.parameter_network`, which the
server's ``graph.build`` service reads too; this is the plugin's name for it.
"""

from __future__ import annotations

from typing import Any

from chisurf.core.fitting.parameter_network import (
    NetworkEdge as GraphEdge,
)
from chisurf.core.fitting.parameter_network import (
    NetworkNode as GraphNode,
)
from chisurf.core.fitting.parameter_network import (
    ParameterNetwork as GraphResult,
)
from chisurf.core.fitting.parameter_network import (
    build_parameter_network,
    session_owners,
)

__all__ = ["GraphEdge", "GraphNode", "GraphResult", "build_graph"]


def build_graph(
    fit_list: list[Any],
    include_fixed: bool = True,
    connect_owners: bool = False,
    group_list: list[Any] | None = None,
) -> GraphResult:
    """The network of *fit_list* and the registered groups in *group_list*.

    Parameters
    ----------
    fit_list : list
        The fits, in session order. An aggregate global-fit model is left out;
        a fit group contributes its local fits.
    include_fixed : bool
        Keep parameters held fixed.
    connect_owners : bool
        Join every owner -- fit or group -- to every other.
    group_list : list, optional
        ``(owner_id, label, group)`` per registered out-of-fit group.

    Returns
    -------
    GraphResult
    """
    return build_parameter_network(
        session_owners(fit_list, group_list or ()), include_fixed, connect_owners
    )
