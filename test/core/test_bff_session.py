"""A project carries its node graph through save and load.

The session runtime is ``IMP.bff``; the graph below is built from bff objects
in ``IMP.bff.get_session()``. Projects are ``.cs.pto`` containers holding the
validated scientific snapshot plus the live graph as the typed ``session.jsonl``
entry (owner decision 2026-10-24: nodes and free ports that no fit owns are
kept again). A load installs the stored graph as the live session, replacing
it. These tests pin that contract and the session's ``clear``.
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

    def test_live_graph_is_embedded_and_restored(self):
        """A saved project carries the live node graph and a load restores it.

        ``Project.save`` captures ``IMP.bff.get_session()`` into the typed
        ``session.jsonl`` entry (nodes, ports and their links); ``Project.load``
        installs it back as the live session, replacing whatever is there.
        """
        node_a, _node_b = self._build_graph()
        archive_path = Project(name="BffTest").save(os.path.join(self.test_dir, "proj1"))

        self.assertTrue(archive_path.is_file())
        self.assertTrue(archive_path.name.endswith(".cs.pto"))
        archive = ProjectArchive.open(archive_path)
        self.assertTrue(archive.has_entry("project.json"))
        self.assertTrue(archive.has_entry(SESSION_FILENAME))
        self.assertTrue(bytes(archive.read_bytes(SESSION_FILENAME)).startswith(b"{"))

        bff.get_session().clear()
        self.assertEqual(len(bff.get_session().nodes), 0)
        loaded = Project.load(archive_path)
        self.assertEqual(loaded.name, "BffTest")
        self.assertEqual(len(bff.get_session().nodes), 2)
        restored_b = bff.get_session().get_node("NodeB")
        self.assertEqual(restored_b.get_input_port("in").get_link().name, "out")
        self.assertAlmostEqual(restored_b.get_input_port("in").value, node_a.get_output_port("out").value)
        self.assertTrue(bytes(loaded.graph_session_bytes).startswith(b"{"))

    def test_storage_routes_carry_the_graph(self):
        """Both storage routes embed the graph: typed-object and archive-entry.

        ``storage.save_file`` picks ``write_project`` for resource-less
        projects and ``Project.save`` otherwise; the graph must survive both.
        """
        from chisurf.core.project import storage

        self._build_graph()
        project = Project(name="BffStorage")
        path_a = storage.save_file(project, os.path.join(self.test_dir, "route_a"))
        self.assertTrue(path_a.name.endswith(".cs.pto"))

        from chisurf.core.project.project import ResourceContext

        project.resources = ResourceContext({"notes.txt": b"resource"})
        path_b = storage.save_file(project, os.path.join(self.test_dir, "route_b"))

        for path, label in ((path_a, "write_project"), (path_b, "archive")):
            with self.subTest(route=label):
                bff.get_session().clear()
                loaded = storage.load_file(path)
                self.assertEqual(len(bff.get_session().nodes), 2, label)
                self.assertTrue(bytes(loaded.graph_session_bytes).startswith(b"{"), label)

    def test_empty_session_writes_no_entry(self):
        """Without live nodes the project stays exactly the scientific snapshot."""
        bff.get_session().clear()
        archive_path = Project(name="BffEmpty").save(os.path.join(self.test_dir, "proj2"))
        archive = ProjectArchive.open(archive_path)
        self.assertFalse(archive.has_entry(SESSION_FILENAME))

    def test_restore_replaces_rather_than_merges(self):
        """A load installs the stored graph; nodes added after the save vanish."""
        self._build_graph()
        archive_path = Project(name="BffReplace").save(os.path.join(self.test_dir, "proj3"))
        extra = bff.GraphNode()
        extra.name = "ExtraNode"
        bff.get_session().add_node("ExtraNode", extra)
        self.assertEqual(len(bff.get_session().nodes), 3)

        Project.load(archive_path)
        names = sorted(bff.get_session().nodes)  # the map yields node names
        self.assertIn("NodeA", names)
        self.assertIn("NodeB", names)
        self.assertNotIn("ExtraNode", names)

    def test_clear_empties_the_session(self):
        """``clear`` drops the nodes, so a restore replaces rather than merges."""
        self._build_graph()
        self.assertEqual(len(bff.get_session().nodes), 2)
        bff.get_session().clear()
        self.assertEqual(len(bff.get_session().nodes), 0)
        self.assertEqual(bff.get_session().get_number_of_nodes(), 0)
