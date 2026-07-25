"""Graph containers, algorithms, layouts and GraphML I/O.

chinet already models a *computation* graph (nodes, ports, links). This package
is the plain graph-theory layer underneath that vocabulary: containers with
attributes, the algorithms ChiSurf's factor graphs and node editors need
(components, elimination orders, cycles, spanning trees) and deterministic
drawing coordinates for them.

Examples
--------
>>> from chinet import graph as cg
>>> g = cg.Graph()
>>> g.add_edge("a", "b", weight=3.0)
>>> g.add_edge("b", "c", weight=1.0)
>>> [sorted(c) for c in cg.connected_components(g)]
[['a', 'b', 'c']]
>>> sorted(cg.maximum_spanning_tree(g).edges)
[('a', 'b'), ('b', 'c')]
>>> sorted(cg.kamada_kawai_layout(g))
['a', 'b', 'c']
"""

from .algorithms import (
    complete_graph as complete_graph,
)
from .algorithms import (
    connected_components as connected_components,
)
from .algorithms import (
    is_connected as is_connected,
)
from .algorithms import (
    is_directed_acyclic_graph as is_directed_acyclic_graph,
)
from .algorithms import (
    maximum_spanning_tree as maximum_spanning_tree,
)
from .algorithms import (
    minimum_spanning_tree as minimum_spanning_tree,
)
from .algorithms import (
    number_connected_components as number_connected_components,
)
from .algorithms import (
    path_graph as path_graph,
)
from .algorithms import (
    shortest_path_length as shortest_path_length,
)
from .algorithms import (
    simple_cycles as simple_cycles,
)
from .algorithms import (
    topological_sort as topological_sort,
)
from .graph import (
    CycleError as CycleError,
)
from .graph import (
    DiGraph as DiGraph,
)
from .graph import (
    EdgeView as EdgeView,
)
from .graph import (
    Graph as Graph,
)
from .graph import (
    GraphError as GraphError,
)
from .graph import (
    NodeView as NodeView,
)
from .graphml import (
    read_graphml as read_graphml,
)
from .graphml import (
    write_graphml as write_graphml,
)
from .layout import (
    arf_layout as arf_layout,
)
from .layout import (
    circular_layout as circular_layout,
)
from .layout import (
    kamada_kawai_layout as kamada_kawai_layout,
)
from .layout import (
    shell_layout as shell_layout,
)
from .layout import (
    spectral_layout as spectral_layout,
)
from .layout import (
    spring_layout as spring_layout,
)

__all__ = [
    "CycleError",
    "DiGraph",
    "EdgeView",
    "Graph",
    "GraphError",
    "NodeView",
    "arf_layout",
    "circular_layout",
    "complete_graph",
    "connected_components",
    "is_connected",
    "is_directed_acyclic_graph",
    "kamada_kawai_layout",
    "maximum_spanning_tree",
    "minimum_spanning_tree",
    "number_connected_components",
    "path_graph",
    "read_graphml",
    "shell_layout",
    "shortest_path_length",
    "simple_cycles",
    "spectral_layout",
    "spring_layout",
    "topological_sort",
    "write_graphml",
]
