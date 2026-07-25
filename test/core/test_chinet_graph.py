"""Tests for :mod:`chinet.graph` — the in-tree graph layer.

These cover the properties the rest of ChiSurf relies on: the container
semantics the factor graph and the node editor are written against, the
algorithms behind independent components, junction trees and cycle
highlighting, layouts that are stable across redraws, and a GraphML round trip
that keeps attribute types.
"""

import itertools
import math

import numpy as np
import pytest
from chinet import graph as cg

# -- containers -----------------------------------------------------------


def test_adding_an_edge_adds_its_nodes():
    g = cg.Graph()
    g.add_edge("a", "b")
    assert sorted(g.nodes) == ["a", "b"]
    assert g.has_edge("a", "b") and g.has_edge("b", "a")
    assert g.number_of_nodes() == 2 and g.number_of_edges() == 1


def test_an_edge_added_twice_stays_one_edge_and_updates_its_attributes():
    g = cg.Graph()
    g.add_edge(1, 2, weight=1.0)
    g.add_edge(1, 2, weight=3.0, label="x")
    assert g.number_of_edges() == 1
    assert g[1][2] == {"weight": 3.0, "label": "x"}


def test_edge_attributes_are_shared_by_both_directions():
    """``tree[a][b]["separator"] = ...`` must be visible from either end."""
    g = cg.Graph()
    g.add_edge("a", "b")
    g["a"]["b"]["separator"] = ("x",)
    assert g["b"]["a"]["separator"] == ("x",)


def test_node_attributes_are_reachable_through_the_view():
    g = cg.Graph()
    g.add_node(7, kind="fit", value=1.5)
    assert g.nodes[7]["kind"] == "fit"
    assert g.nodes.get(7, {}).get("value") == 1.5
    assert g.nodes.get(8, {}) == {}
    g.add_node(7, value=2.5)
    assert g.nodes[7] == {"kind": "fit", "value": 2.5}


def test_views_are_callable_so_nodes_and_nodes_agree():
    g = cg.Graph()
    g.add_edge(1, 2)
    assert list(g.nodes()) == list(g.nodes) == [1, 2]
    assert list(g.edges()) == list(g.edges) == [(1, 2)]
    assert (1, 2) in g.edges and (2, 1) in g.edges


def test_removing_a_node_removes_its_edges():
    g = cg.Graph()
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.remove_node("b")
    assert sorted(g.nodes) == ["a", "c"]
    assert g.number_of_edges() == 0
    with pytest.raises(cg.GraphError):
        g.remove_node("b")


def test_a_copy_is_independent():
    g = cg.Graph()
    g.add_edge("a", "b", weight=1.0)
    clone = g.copy()
    clone.add_edge("b", "c")
    clone["a"]["b"]["weight"] = 9.0
    assert g.number_of_nodes() == 2
    assert g["a"]["b"]["weight"] == 1.0


def test_tuples_work_as_nodes():
    """Junction-tree nodes are tuples of parameter keys."""
    g = cg.Graph()
    a, b = ("x", "y"), ("y", "z")
    g.add_edge(a, b, weight=1)
    assert sorted(g.nodes) == [a, b]
    assert g.get_edge_data(a, b)["weight"] == 1


def test_iteration_order_is_insertion_order():
    g = cg.Graph()
    for n in [5, 3, 9, 1]:
        g.add_node(n)
    assert list(g.nodes) == [5, 3, 9, 1]


def test_directed_graph_tracks_both_directions():
    g = cg.DiGraph()
    g.add_edge(1, 2)
    g.add_edge(3, 2)
    assert list(g.successors(1)) == [2]
    assert sorted(g.predecessors(2)) == [1, 3]
    assert g.has_edge(1, 2) and not g.has_edge(2, 1)
    assert dict(g.in_degree())[2] == 2
    assert g.number_of_edges() == 2


def test_directed_removal_keeps_the_two_maps_in_step():
    g = cg.DiGraph()
    g.add_edge(1, 2)
    g.add_edge(2, 3)
    g.remove_node(2)
    assert list(g.nodes) == [1, 3]
    assert list(g.successors(1)) == [] and list(g.predecessors(3)) == []


def test_subgraph_keeps_only_edges_with_both_ends():
    g = cg.Graph()
    g.add_edge(1, 2)
    g.add_edge(2, 3)
    sub = g.subgraph([1, 2])
    assert sorted(sub.nodes) == [1, 2]
    assert sub.number_of_edges() == 1


# -- algorithms -----------------------------------------------------------


def test_connected_components_finds_the_independent_pieces():
    g = cg.Graph()
    g.add_edge("a", "b")
    g.add_edge("c", "d")
    g.add_node("e")
    components = sorted(
        (sorted(c) for c in cg.connected_components(g)), key=len, reverse=True
    )
    assert components == [["a", "b"], ["c", "d"], ["e"]]
    assert cg.number_connected_components(g) == 3


def test_topological_sort_orders_every_edge_forwards():
    g = cg.DiGraph()
    g.add_edge("read", "fit")
    g.add_edge("fit", "plot")
    g.add_edge("read", "plot")
    order = list(cg.topological_sort(g))
    assert order.index("read") < order.index("fit") < order.index("plot")


def test_topological_sort_refuses_a_cycle():
    g = cg.DiGraph()
    g.add_edge(1, 2)
    g.add_edge(2, 1)
    assert not cg.is_directed_acyclic_graph(g)
    with pytest.raises(cg.CycleError):
        list(cg.topological_sort(g))


def test_an_undirected_graph_is_never_a_dag():
    g = cg.Graph()
    g.add_edge(1, 2)
    assert cg.is_directed_acyclic_graph(g) is False


def test_simple_cycles_reports_every_circuit_once():
    g = cg.DiGraph()
    for u, v in [(1, 2), (2, 3), (3, 1), (3, 4), (4, 3)]:
        g.add_edge(u, v)
    cycles = [tuple(c) for c in cg.simple_cycles(g)]
    canonical = {
        tuple(c[c.index(min(c)):] + c[:c.index(min(c))]) for c in map(list, cycles)
    }
    assert canonical == {(1, 2, 3), (3, 4)}


def test_simple_cycles_reports_a_self_loop():
    g = cg.DiGraph()
    g.add_edge(1, 1)
    g.add_edge(1, 2)
    assert [list(c) for c in cg.simple_cycles(g)] == [[1]]


def test_maximum_spanning_tree_maximises_the_total_weight():
    g = cg.Graph()
    g.add_edge("a", "b", weight=1.0)
    g.add_edge("b", "c", weight=5.0)
    g.add_edge("a", "c", weight=4.0)
    tree = cg.maximum_spanning_tree(g)
    assert tree.number_of_edges() == 2
    total = sum(tree.get_edge_data(u, v)["weight"] for u, v in tree.edges)
    assert total == pytest.approx(9.0)


def test_minimum_spanning_tree_minimises_it():
    g = cg.Graph()
    g.add_edge("a", "b", weight=1.0)
    g.add_edge("b", "c", weight=5.0)
    g.add_edge("a", "c", weight=4.0)
    tree = cg.minimum_spanning_tree(g)
    total = sum(tree.get_edge_data(u, v)["weight"] for u, v in tree.edges)
    assert total == pytest.approx(5.0)


def test_a_spanning_tree_of_a_disconnected_graph_is_a_forest():
    g = cg.Graph()
    g.add_edge(1, 2, weight=1)
    g.add_edge(3, 4, weight=1)
    tree = cg.maximum_spanning_tree(g)
    assert tree.number_of_nodes() == 4
    assert tree.number_of_edges() == 2
    assert cg.number_connected_components(tree) == 2


def test_a_spanning_tree_keeps_the_edge_attributes():
    g = cg.Graph()
    g.add_edge(1, 2, weight=2.0, tag="keep")
    tree = cg.maximum_spanning_tree(g)
    assert tree[1][2]["tag"] == "keep"


def test_shortest_path_length_follows_the_weights():
    g = cg.Graph()
    g.add_edge("a", "b", weight=1.0)
    g.add_edge("b", "c", weight=1.0)
    g.add_edge("a", "c", weight=5.0)
    weighted = cg.shortest_path_length(g, weight="weight")
    assert weighted["a"]["c"] == pytest.approx(2.0)
    hops = cg.shortest_path_length(g)
    assert hops["a"]["c"] == 1


def test_shortest_path_length_omits_unreachable_pairs():
    g = cg.Graph()
    g.add_edge(1, 2)
    g.add_node(3)
    assert 3 not in cg.shortest_path_length(g)[1]


def test_complete_and_path_generators():
    assert cg.complete_graph(4).number_of_edges() == 6
    assert cg.complete_graph(["a", "b", "c"]).number_of_edges() == 3
    chain = cg.path_graph(5)
    assert chain.number_of_edges() == 4
    assert cg.number_connected_components(chain) == 1


# -- layouts --------------------------------------------------------------


LAYOUTS = [
    cg.circular_layout,
    cg.shell_layout,
    cg.spectral_layout,
    cg.spring_layout,
    cg.kamada_kawai_layout,
    cg.arf_layout,
]


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_places_every_node_inside_the_canvas(layout):
    g = cg.Graph()
    g.add_edges_from([(1, 2), (2, 3), (3, 1), (3, 4), (4, 5)])
    pos = layout(g)
    assert set(pos) == set(g.nodes)
    for point in pos.values():
        assert np.all(np.isfinite(point))
        assert np.max(np.abs(point)) <= 1.0 + 1e-6


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_is_reproducible(layout):
    """A redraw that reshuffles the picture is unreadable."""
    g = cg.Graph()
    g.add_edges_from([("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")])
    first, second = layout(g), layout(g)
    for key in first:
        assert first[key] == pytest.approx(second[key])


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_survives_the_degenerate_graphs(layout):
    assert layout(cg.Graph()) == {}
    single = cg.Graph()
    single.add_node("only")
    assert list(layout(single)) == ["only"]


@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_layout_survives_a_disconnected_graph(layout):
    g = cg.Graph()
    g.add_edge(1, 2)
    g.add_edge(3, 4)
    g.add_node(5)
    pos = layout(g)
    assert len(pos) == 5
    assert all(np.all(np.isfinite(p)) for p in pos.values())


def test_kamada_kawai_draws_a_chain_as_evenly_spaced_points():
    """The point of the layout: drawn distance tracks graph distance."""
    g = cg.path_graph(6)
    pos = cg.kamada_kawai_layout(g)
    steps = [
        float(np.linalg.norm(pos[i + 1] - pos[i])) for i in range(5)
    ]
    assert max(steps) - min(steps) < 0.02 * max(steps)
    # ... and a chain is drawn as a chain, not a ball: end to end is nearly the
    # whole path. (Nearly, not exactly -- the stress-optimal drawing of a path
    # bows very slightly, which is a property of the objective, not a defect.)
    ends = float(np.linalg.norm(pos[5] - pos[0]))
    assert ends > 0.97 * sum(steps)


def test_kamada_kawai_reads_the_weight_as_a_length():
    g = cg.Graph()
    g.add_edge("a", "b", weight=0.1)
    g.add_edge("b", "c", weight=1.0)
    pos = cg.kamada_kawai_layout(g, weight="weight")
    close = float(np.linalg.norm(pos["a"] - pos["b"]))
    far = float(np.linalg.norm(pos["b"] - pos["c"]))
    assert close < far


def test_kamada_kawai_accepts_a_distance_matrix():
    g = cg.Graph()
    g.add_edges_from([(0, 1), (1, 2)])
    d = np.array([[0.0, 1.0, 2.0], [1.0, 0.0, 1.0], [2.0, 1.0, 0.0]])
    pos = cg.kamada_kawai_layout(g, dist=d)
    assert len(pos) == 3
    with pytest.raises(ValueError):
        cg.kamada_kawai_layout(g, dist=np.zeros((2, 2)))


def test_circular_layout_puts_the_nodes_on_a_circle():
    g = cg.Graph()
    g.add_nodes_from(range(6))
    pos = cg.circular_layout(g, scale=2.0)
    for point in pos.values():
        assert float(np.linalg.norm(point)) == pytest.approx(2.0)
    angles = sorted(math.atan2(p[1], p[0]) for p in pos.values())
    gaps = np.diff(angles)
    assert np.allclose(gaps, gaps[0])


def test_shell_layout_puts_each_shell_on_its_own_radius():
    g = cg.Graph()
    g.add_nodes_from(range(6))
    pos = cg.shell_layout(g, nlist=[[0, 1], [2, 3, 4, 5]], scale=1.0)
    inner = [float(np.linalg.norm(pos[n])) for n in (0, 1)]
    outer = [float(np.linalg.norm(pos[n])) for n in (2, 3, 4, 5)]
    assert max(inner) < min(outer)


def test_spectral_layout_separates_two_clusters():
    g = cg.Graph()
    for u, v in itertools.combinations(range(4), 2):
        g.add_edge(u, v)
    for u, v in itertools.combinations(range(4, 8), 2):
        g.add_edge(u, v)
    g.add_edge(0, 4)
    pos = cg.spectral_layout(g)
    left = np.mean([pos[n][0] for n in range(4)])
    right = np.mean([pos[n][0] for n in range(4, 8)])
    spread = np.std([pos[n][0] for n in range(4)])
    assert abs(left - right) > 3 * max(spread, 1e-6)


def test_arf_refuses_a_spring_constant_that_cannot_hold():
    g = cg.Graph()
    g.add_edge(1, 2)
    with pytest.raises(ValueError):
        cg.arf_layout(g, a=1.0)


def test_a_layout_can_be_centred_and_scaled():
    g = cg.path_graph(4)
    pos = cg.kamada_kawai_layout(g, scale=5.0, center=(10.0, -3.0))
    points = np.array(list(pos.values()))
    assert points.mean(axis=0) == pytest.approx(np.array([10.0, -3.0]), abs=1e-6)
    assert np.abs(points - np.array([10.0, -3.0])).max() == pytest.approx(5.0)


# -- GraphML --------------------------------------------------------------


def test_graphml_round_trip_keeps_structure_and_typed_attributes(tmp_path):
    g = cg.Graph()
    g.add_node("n0", label="fit", index=3, value=1.25, fixed=True, missing=None)
    g.add_node("n1", label="parameter", index=4, value=-2.0, fixed=False)
    g.add_edge("n0", "n1", kind="constrains", strength=0.5)
    path = tmp_path / "graph.gml"
    cg.write_graphml(g, str(path))

    back = cg.read_graphml(str(path))
    assert sorted(back.nodes) == ["n0", "n1"]
    assert list(back.edges) == [("n0", "n1")]
    assert back.nodes["n0"]["label"] == "fit"
    assert back.nodes["n0"]["index"] == 3 and isinstance(
        back.nodes["n0"]["index"], int
    )
    assert back.nodes["n0"]["value"] == pytest.approx(1.25)
    assert back.nodes["n0"]["fixed"] is True
    assert back.nodes["n1"]["fixed"] is False
    # A value that was ``None`` has no GraphML spelling and is simply absent.
    assert "missing" not in back.nodes["n0"]
    assert back["n0"]["n1"]["strength"] == pytest.approx(0.5)


def test_graphml_round_trip_keeps_direction(tmp_path):
    g = cg.DiGraph()
    g.add_edge("a", "b")
    path = tmp_path / "directed.gml"
    cg.write_graphml(g, str(path))
    back = cg.read_graphml(str(path))
    assert back.is_directed()
    assert back.has_edge("a", "b") and not back.has_edge("b", "a")


def test_graphml_node_identifiers_can_be_read_back_as_integers(tmp_path):
    g = cg.Graph()
    g.add_edge(0, 1)
    path = tmp_path / "ints.gml"
    cg.write_graphml(g, str(path))
    assert sorted(cg.read_graphml(str(path)).nodes) == ["0", "1"]
    assert sorted(cg.read_graphml(str(path), node_type=int).nodes) == [0, 1]


def test_graphml_mixed_numeric_attributes_become_double(tmp_path):
    g = cg.Graph()
    g.add_node("a", size=1)
    g.add_node("b", size=1.5)
    path = tmp_path / "mixed.gml"
    cg.write_graphml(g, str(path))
    back = cg.read_graphml(str(path))
    assert back.nodes["a"]["size"] == pytest.approx(1.0)
    assert back.nodes["b"]["size"] == pytest.approx(1.5)


def test_reading_something_that_is_not_graphml_is_an_error(tmp_path):
    path = tmp_path / "empty.gml"
    path.write_text("<graphml xmlns='http://graphml.graphdrawing.org/xmlns'/>")
    with pytest.raises(cg.GraphError):
        cg.read_graphml(str(path))
