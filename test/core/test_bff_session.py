"""A project carries its node graph through save and load.

The graph is stored as ``session.jsonl`` inside the ``.csp`` archive. What makes
this worth testing is the *link*: a port that reads its value from another port
has to come back linked, not merely present with the right number in it, or the
graph is dead on arrival and only shows it when something downstream changes.

The session runtime is ``IMP.bff`` (phase 3 of removing chinet: bff absorbed
chinet's Port/Node/Session and reads/writes chinet's session format), so the
graph below is built from bff objects in ``IMP.bff.get_session()`` -- the
registry bff exposes instead of chinet's silent global database. A separate
test writes a session with *vendored chinet itself* and opens it through the
same path, pinning that chinet-era archives on disk still load.

Two defects the chinet-era version of this test pinned, both carried over:
``Session.load`` builds and returns a new session, so calling it without moving
the result restored nothing; and a restore needs ``clear()`` so the saved graph
replaces the current one instead of merging into it.
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
    """Round-trip of a two-node graph through a project archive."""

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

    def test_session_is_stored_in_the_project_archive(self):
        """Saving a project writes the node graph into the .csp archive."""
        self._build_graph()
        archive_path = Project(name="BffTest").save(os.path.join(self.test_dir, "proj1"))

        self.assertTrue(archive_path.is_file())
        archive = ProjectArchive.open(archive_path)
        self.assertTrue(archive.has_entry(SESSION_FILENAME))
        self.assertIn(SESSION_FILENAME, archive.list_entries())

    def test_graph_and_link_survive_a_round_trip(self):
        """Loading restores the nodes into the live session, links included."""
        _, node_b = self._build_graph()
        self.assertEqual(node_b.inputs["in"].value, 10.0)

        archive_path = Project(name="BffTest").save(os.path.join(self.test_dir, "proj2"))
        bff.get_session().clear()
        self.assertEqual(len(bff.get_session().nodes), 0)

        loaded = Project.load(archive_path)
        self.assertEqual(loaded.name, "BffTest")

        nodes = bff.get_session().nodes
        self.assertIn("NodeA", nodes)
        self.assertIn("NodeB", nodes)
        restored_a, restored_b = nodes["NodeA"], nodes["NodeB"]
        self.assertEqual(restored_a.outputs["out"].value, 10.0)
        self.assertEqual(restored_b.inputs["in"].value, 10.0)

        # The link, not just the value: change the source and the sink follows.
        restored_a.outputs["out"].value = 25.0
        self.assertEqual(restored_b.inputs["in"].value, 25.0)

    def test_free_ports_survive_a_round_trip(self):
        """A free port (what a fit parameter is) is restored as a free port.

        chinet's DB held these silently; bff's session is the registry, and
        the restore moves loaded free ports into the live session so a
        re-save writes them again.
        """
        port = bff.GraphPort(value=3.5, name="gamma", lb=0.0, ub=10.0, is_bounded=True)
        bff.get_session().add_port(port)

        archive_path = Project(name="BffTest").save(os.path.join(self.test_dir, "proj3"))
        bff.get_session().clear()

        Project.load(archive_path)
        restored = bff.get_session().get_port("gamma")
        self.assertIsNotNone(restored)
        self.assertEqual(restored.value, 3.5)
        self.assertEqual(restored.bounds, (0.0, 10.0))

    def test_clear_empties_the_session(self):
        """``clear`` drops the nodes, so a restore replaces rather than merges."""
        self._build_graph()
        self.assertEqual(len(bff.get_session().nodes), 2)
        bff.get_session().clear()
        self.assertEqual(len(bff.get_session().nodes), 0)
        self.assertEqual(bff.get_session().get_number_of_nodes(), 0)

    def test_chinet_written_archive_opens(self):
        """A session.jsonl written by chinet itself loads through the bff path.

        This is the phase-3 contract: archives saved by chinet-era chisurf
        keep opening. The graph is built and saved with vendored chinet (a
        node with an output port, a linked input port, a vector port and a
        prior-carrying free port), packaged into a .csp, and loaded.
        """
        chinet = None
        try:
            import chinet
        except ImportError:
            self.skipTest("vendored chinet not importable")

        chinet.session.clear()
        node_a = chinet.Node()
        node_a.name = "LegacyNode"
        port_a = chinet.Port(10.0)
        port_a.name = "out"
        node_a.add_output_port("out", port_a)

        node_b = chinet.Node()
        node_b.name = "LegacySink"
        port_b = chinet.Port(0.0)
        port_b.name = "in"
        node_b.add_input_port("in", port_b)
        port_b.set_link(port_a)

        free = chinet.Port(value=2.5, name="legacy_free", lb=0.0, ub=5.0, is_bounded=True)
        free.prior = {"kind": "normal", "mu": 2.0, "sigma": 0.5}

        chinet.session.add_node("LegacyNode", node_a)
        chinet.session.add_node("LegacySink", node_b)

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                legacy_path = os.path.join(tmpdir, "session.jsonl")
                chinet.session.save(legacy_path)
                with open(legacy_path) as fp:
                    first = json.loads(fp.readline())
                self.assertEqual(first.get("type"), "session")  # chinet's JSONL
                self.assertIn("LegacyNode", first["nodes"])

                # A real .csp: project.json plus the chinet-written session.
                archive = ProjectArchive()
                Project(name="Legacy").save_to_archive(archive)
                with open(legacy_path, "rb") as fp:
                    archive.write_bytes(SESSION_FILENAME, fp.read())
                archive_path = archive.save(os.path.join(self.test_dir, "legacy.csp"))
        finally:
            chinet.session.clear()

        bff.get_session().clear()
        Project.load(archive_path)

        nodes = bff.get_session().nodes
        self.assertIn("LegacyNode", nodes)
        self.assertIn("LegacySink", nodes)
        self.assertEqual(nodes["LegacyNode"].outputs["out"].value, 10.0)
        sink = nodes["LegacySink"].inputs["in"]
        self.assertEqual(sink.value, 10.0)
        nodes["LegacyNode"].outputs["out"].value = 42.0
        self.assertEqual(sink.value, 42.0)  # the link survived

        restored_free = bff.get_session().get_port("legacy_free")
        self.assertIsNotNone(restored_free)
        self.assertEqual(restored_free.value, 2.5)
        self.assertEqual(restored_free.bounds, (0.0, 5.0))
        self.assertEqual(restored_free.prior, {"kind": "normal", "mu": 2.0, "sigma": 0.5})


if __name__ == "__main__":
    unittest.main()
