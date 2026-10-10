"""A project carries its node graph through save and load.

The session runtime is ``IMP.bff``; the graph below is built from bff objects
in ``IMP.bff.get_session()``. Projects are ``.cs.pto`` containers holding the
validated scientific snapshot; the live graph is no longer dumped into them
(the old ``session.jsonl`` entry), it is rebuilt from the fits on restore. These
tests pin that contract and the session's ``clear``.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import IMP.bff as bff

from chisurf.core.project.archive import SESSION_FILENAME, ProjectArchive
from chisurf.core.project.project import Project


class TestBffSession(unittest.TestCase):
    """The live node graph and its relation to the project file."""

    def setUp(self):
        """Start from an empty session in a scratch directory."""
        self.test_dir = tempfile.mkdtemp()
        bff.get_session().clear()

    def tearDown(self):
        """Remove the scratch directory and empty the session again."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        bff.get_session().clear()

    def _build_graph(self):
        """Two nodes whose input port reads from the other's output port."""
        node_a = bff.GraphNode()
        node_a.name = "NodeA"
        port_a = bff.GraphPort(10.0)
        port_a.name = "out"
        node_a.add_output_port("out", port_a)

        node_b = bff.GraphNode()
        node_b.name = "NodeB"
        port_b = bff.GraphPort(0.0)
        port_b.name = "in"
        node_b.add_input_port("in", port_b)

        # ``Port.link`` is a property whose setter calls set_link.
        port_b.set_link(port_a)

        session = bff.get_session()
        session.add_node("NodeA", node_a)
        session.add_node("NodeB", node_b)
        return node_a, node_b

    def test_live_graph_is_not_embedded_in_the_project_file(self):
        """A saved project is the v5 scientific snapshot, not the live node graph.

        The ``session.jsonl`` graph dump of the ``.csp`` era is retired: the
        bff graph is rebuilt from the restored fits (``project.session``), so
        ``Project.save`` writes ``project.json`` and no native session entry,
        and a load does not resurrect nodes that were only in the live session.
        """
        self._build_graph()
        archive_path = Project(name="BffTest").save(os.path.join(self.test_dir, "proj1"))

        self.assertTrue(archive_path.is_file())
        self.assertTrue(archive_path.name.endswith(".cs.pto"))
        archive = ProjectArchive.open(archive_path)
        self.assertTrue(archive.has_entry("project.json"))
        self.assertFalse(archive.has_entry(SESSION_FILENAME))

        bff.get_session().clear()
        loaded = Project.load(archive_path)
        self.assertEqual(loaded.name, "BffTest")
        self.assertEqual(len(bff.get_session().nodes), 0)

    def test_clear_empties_the_session(self):
        """``clear`` drops the nodes, so a restore replaces rather than merges."""
        self._build_graph()
        self.assertEqual(len(bff.get_session().nodes), 2)
        bff.get_session().clear()
        self.assertEqual(len(bff.get_session().nodes), 0)
        self.assertEqual(bff.get_session().get_number_of_nodes(), 0)
