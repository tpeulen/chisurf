"""Smoke tests for :mod:`chinet.graph`, chinet's plain graph-theory layer.

The exhaustive suite lives with the application that drives it
(``test/core/test_chinet_graph.py`` in ChiSurf); this file keeps chinet's own
``pixi run test-chinet`` honest about the module existing and working.
"""

import unittest

import numpy as np
from chinet import graph as cg


class TestGraphContainer(unittest.TestCase):
    """Container semantics: nodes, edges and their attributes."""

    def test_edges_and_attributes(self):
        g = cg.Graph()
        g.add_edge("a", "b", weight=2.0)
        g.add_node("c", kind="lonely")
        self.assertEqual(sorted(g.nodes), ["a", "b", "c"])
        self.assertEqual(g.number_of_edges(), 1)
        self.assertEqual(g["a"]["b"]["weight"], 2.0)
        self.assertEqual(g.nodes["c"]["kind"], "lonely")
        # Edge attributes are shared between the two directions.
        g["b"]["a"]["weight"] = 3.0
        self.assertEqual(g["a"]["b"]["weight"], 3.0)

    def test_directed_graph_keeps_direction(self):
        g = cg.DiGraph()
        g.add_edge(1, 2)
        self.assertTrue(g.has_edge(1, 2))
        self.assertFalse(g.has_edge(2, 1))
        self.assertEqual(list(g.predecessors(2)), [1])


class TestGraphAlgorithms(unittest.TestCase):
    """Components, spanning trees, orderings and cycles."""

    def test_components_and_spanning_tree(self):
        g = cg.Graph()
        g.add_edge(1, 2, weight=1.0)
        g.add_edge(2, 3, weight=5.0)
        g.add_edge(1, 3, weight=4.0)
        g.add_node(4)
        self.assertEqual(cg.number_connected_components(g), 2)
        tree = cg.maximum_spanning_tree(g)
        total = sum(tree.get_edge_data(u, v)["weight"] for u, v in tree.edges)
        self.assertAlmostEqual(total, 9.0)

    def test_cycles_and_ordering(self):
        g = cg.DiGraph()
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        self.assertTrue(cg.is_directed_acyclic_graph(g))
        self.assertEqual(list(cg.topological_sort(g)), ["a", "b", "c"])
        g.add_edge("c", "a")
        self.assertFalse(cg.is_directed_acyclic_graph(g))
        self.assertEqual(len(list(cg.simple_cycles(g))), 1)


class TestGraphLayout(unittest.TestCase):
    """Drawing coordinates: finite, bounded and reproducible."""

    def test_layout_is_finite_bounded_and_reproducible(self):
        g = cg.path_graph(5)
        first = cg.kamada_kawai_layout(g)
        second = cg.kamada_kawai_layout(g)
        for key, point in first.items():
            self.assertTrue(np.all(np.isfinite(point)))
            self.assertLessEqual(float(np.max(np.abs(point))), 1.0 + 1e-6)
            np.testing.assert_allclose(point, second[key])


class TestGraphML(unittest.TestCase):
    """GraphML reading and writing."""

    def test_round_trip(self):
        import os
        import tempfile

        g = cg.Graph()
        g.add_node("n0", label="first", index=1)
        g.add_edge("n0", "n1", weight=0.5)
        directory = tempfile.mkdtemp()
        try:
            path = os.path.join(directory, "graph.gml")
            cg.write_graphml(g, path)
            back = cg.read_graphml(path)
        finally:
            import shutil

            shutil.rmtree(directory, ignore_errors=True)
        self.assertEqual(sorted(back.nodes), ["n0", "n1"])
        self.assertEqual(back.nodes["n0"]["index"], 1)
        self.assertAlmostEqual(back["n0"]["n1"]["weight"], 0.5)


if __name__ == "__main__":
    unittest.main()
