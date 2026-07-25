"""A project carries its chinet node graph through save and load.

The graph is stored as ``session.jsonl`` inside the ``.csp`` archive. What makes
this worth testing is the *link*: a port that reads its value from another port
has to come back linked, not merely present with the right number in it, or the
graph is dead on arrival and only shows it when something downstream changes.

Two defects this pins. ``Session.load`` is a classmethod, so the old
``chinet.session.load(path)`` built a session and threw it away — opening a
project restored nothing. And ``Session`` had no ``clear()``, which is what a
restore needs so the saved graph replaces the current one instead of merging
into it.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest

import chinet

from chisurf.core.project.archive import SESSION_FILENAME, ProjectArchive
from chisurf.core.project.project import Project


class TestChinetSession(unittest.TestCase):
    """Round-trip of a two-node graph through a project archive."""

    def setUp(self):
        """Start from an empty session in a scratch directory."""
        self.test_dir = tempfile.mkdtemp()
        chinet.session.clear()

    def tearDown(self):
        """Remove the scratch directory and empty the session again."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        chinet.session.clear()

    def _build_graph(self):
        """Two nodes whose input port reads from the other's output port."""
        node_a = chinet.Node()
        node_a.name = "NodeA"
        port_a = chinet.Port(10.0)
        port_a.name = "out"
        node_a.add_output_port("out", port_a)

        node_b = chinet.Node()
        node_b.name = "NodeB"
        port_b = chinet.Port(0.0)
        port_b.name = "in"
        node_b.add_input_port("in", port_b)

        # ``Port.link`` is a property whose setter calls set_link.
        port_b.set_link(port_a)

        chinet.session.add_node("NodeA", node_a)
        chinet.session.add_node("NodeB", node_b)
        return node_a, node_b

    def test_session_is_stored_in_the_project_archive(self):
        """Saving a project writes the node graph into the .csp archive."""
        self._build_graph()
        archive_path = Project(name="ChinetTest").save(os.path.join(self.test_dir, "proj1"))

        self.assertTrue(archive_path.is_file())
        archive = ProjectArchive.open(archive_path)
        self.assertTrue(archive.has_entry(SESSION_FILENAME))
        self.assertIn(SESSION_FILENAME, archive.list_entries())

    def test_graph_and_link_survive_a_round_trip(self):
        """Loading restores the nodes into the live session, links included."""
        _, node_b = self._build_graph()
        self.assertEqual(node_b.inputs["in"].value, 10.0)

        archive_path = Project(name="ChinetTest").save(os.path.join(self.test_dir, "proj2"))
        chinet.session.clear()
        self.assertEqual(len(chinet.session.nodes), 0)

        loaded = Project.load(archive_path)
        self.assertEqual(loaded.name, "ChinetTest")

        nodes = chinet.session.nodes
        self.assertIn("NodeA", nodes)
        self.assertIn("NodeB", nodes)
        restored_a, restored_b = nodes["NodeA"], nodes["NodeB"]
        self.assertEqual(restored_a.outputs["out"].value, 10.0)
        self.assertEqual(restored_b.inputs["in"].value, 10.0)

        # The link, not just the value: change the source and the sink follows.
        restored_a.outputs["out"].value = 25.0
        self.assertEqual(restored_b.inputs["in"].value, 25.0)

    def test_clear_empties_the_session(self):
        """``clear`` drops the nodes, so a restore replaces rather than merges."""
        self._build_graph()
        self.assertEqual(len(chinet.session.nodes), 2)
        chinet.session.clear()
        self.assertEqual(len(chinet.session.nodes), 0)
        self.assertEqual(chinet.session.to_dict()["session"]["nodes"], {})


if __name__ == "__main__":
    unittest.main()
