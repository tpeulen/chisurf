"""Headless (Qt-free) tests for the Save-Topology view-model."""

import pathlib

import numpy as np


def _tiny_trajectory(path: str) -> str:
    """Write a minimal two-frame single-atom trajectory to *path* (.dcd).

    The residue is a protein one on purpose: the PDB reader filters water, so a
    lone ``HOH`` comes back as an empty topology and the failure looks like a
    writer bug rather than a filter.
    """
    from chisurf.core.structure import trajectory_data as md

    topology = md.Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    topology.add_atom("CA", md.element.carbon, residue)
    xyz = np.zeros((2, 1, 3), dtype=np.float32)
    xyz[1, 0, 0] = 1.0
    traj = md.Trajectory(xyz=xyz, topology=topology)
    traj.save_dcd(path)
    pdb = str(path).replace(".dcd", ".pdb")
    traj[0].save_pdb(pdb)
    return pdb


def test_log_starts_ready():
    from chisurf.plugins.traj.traj_save_topology.view_model import SaveTopologyViewModel

    model = SaveTopologyViewModel()
    assert "Ready" in model.log_html()


def test_set_trajectory_notifies_and_logs():
    from chisurf.plugins.traj.traj_save_topology.view_model import SaveTopologyViewModel

    model = SaveTopologyViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory("/data/traj.dcd")
    assert model.trajectory_filename == "/data/traj.dcd"
    assert "loaded" in events
    assert "/data/traj.dcd" in model.log_html()


def test_save_topology_without_trajectory_is_noop():
    from chisurf.plugins.traj.traj_save_topology.view_model import SaveTopologyViewModel

    model = SaveTopologyViewModel()
    model.save_topology("/tmp/should_not_be_written.pdb")
    assert "No trajectory selected" in model.log_html()
    assert not pathlib.Path("/tmp/should_not_be_written.pdb").exists()


def test_save_topology_writes_first_frame(tmp_path):
    from chisurf.plugins.traj.traj_save_topology.view_model import SaveTopologyViewModel

    source = tmp_path / "traj.dcd"
    target = tmp_path / "topology.pdb"
    topology = _tiny_trajectory(str(source))

    model = SaveTopologyViewModel()
    model.set_trajectory(str(source))
    model.set_topology(topology)
    model.topology_filename = topology
    model.save_topology(str(target))

    assert target.exists()
    assert "Topology saved" in model.log_html()


def test_view_spec_loads():
    from chisurf.plugins.traj.traj_save_topology.view_model import SaveTopologyViewModel

    spec = SaveTopologyViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)
