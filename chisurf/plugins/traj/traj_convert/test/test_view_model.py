"""Headless (Qt-free) tests for the MD-Converter view-model."""

import glob
import os

import numpy as np
import pytest


def _tiny_trajectory(path: str, n_frames: int = 5) -> str:
    """Write a minimal *n_frames* three-atom trajectory to *path* and return it."""
    from chisurf.core.structure import trajectory_data as md

    topology = md.Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    for name in ("N", "CA", "C"):
        topology.add_atom(name, md.element.carbon, residue)
    rng = np.random.default_rng(0)
    xyz = rng.random((n_frames, 3, 3)).astype(np.float32)
    traj = md.Trajectory(xyz=xyz, topology=topology)
    traj.save_dcd(path)
    pdb = str(path).replace('.dcd', '.pdb')
    traj[0].save_pdb(pdb)
    return pdb
    return traj


def test_log_starts_ready():
    from chisurf.plugins.traj.traj_convert.view_model import MDConverterViewModel

    assert "Ready" in MDConverterViewModel().log_html()


def test_settable_attrs_round_trip():
    from chisurf.plugins.traj.traj_convert.view_model import MDConverterViewModel

    model = MDConverterViewModel()
    model.set_trajectory("/data/traj.dcd")
    model.set_target_directory("/data/out")
    model.use_folder = True
    model.first_frame = 3
    model.last_frame = 42
    model.stride = 5
    model.filename = "conv"
    model.ending = ".pdb"
    model.split = True
    assert model.trajectory == "/data/traj.dcd"
    assert model.target_directory == "/data/out"
    assert model.use_folder is True
    assert model.first_frame == 3
    assert model.last_frame == 42
    assert model.stride == 5
    assert model.filename == "conv"
    assert model.ending == ".pdb"
    assert model.split is True


def test_default_frame_range_and_ending():
    from chisurf.plugins.traj.traj_convert.view_model import ENDINGS, MDConverterViewModel

    model = MDConverterViewModel()
    assert model.first_frame == 0
    assert model.last_frame == -1
    assert model.stride == 1
    assert model.filename == "out"
    assert model.ending == ENDINGS[0] == ".dcd"
    assert not model.split
    assert not model.use_folder


def test_topology_file_none_for_missing(tmp_path):
    from chisurf.plugins.traj.traj_convert.view_model import MDConverterViewModel

    model = MDConverterViewModel()
    model.set_topology(str(tmp_path / "does_not_exist.pdb"))
    assert model.topology_file is None


def test_topology_file_returns_existing(tmp_path):
    from chisurf.plugins.traj.traj_convert.view_model import MDConverterViewModel

    pdb = tmp_path / "top.pdb"
    pdb.write_text("REMARK dummy\nEND\n")
    model = MDConverterViewModel()
    model.topology_file = str(pdb)  # property setter
    assert model.topology_file == str(pdb)
    assert model.topology_path == str(pdb)


def test_set_trajectory_notifies():
    from chisurf.plugins.traj.traj_convert.view_model import MDConverterViewModel

    model = MDConverterViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory("/data/traj.dcd")
    assert model.trajectory == "/data/traj.dcd"
    assert "trajectory" in events


def test_convert_single_file(tmp_path):
    from chisurf.core.structure import trajectory_data as md

    from chisurf.plugins.traj.traj_convert.view_model import MDConverterViewModel

    source = tmp_path / "src.dcd"
    pdb = _tiny_trajectory(str(source), n_frames=5)

    model = MDConverterViewModel()
    model.set_trajectory(str(source))
    model.set_topology(str(pdb))
    model.set_target_directory(str(tmp_path))
    model.filename = "out"
    model.ending = ".dcd"
    model.convert()

    out = tmp_path / "out.dcd"
    assert out.exists()
    loaded = md.load(str(out), top=str(pdb))
    assert loaded.n_frames == 5
    assert loaded.n_atoms == 3
    assert "Conversion done" in model.log_html()


def test_convert_split_per_frame(tmp_path):
    from chisurf.plugins.traj.traj_convert.view_model import MDConverterViewModel

    source = tmp_path / "src.dcd"
    pdb = _tiny_trajectory(str(source), n_frames=4)

    model = MDConverterViewModel()
    model.set_trajectory(str(source))
    model.set_topology(str(pdb))
    model.set_target_directory(str(tmp_path))
    model.filename = "frame"
    model.ending = ".pdb"
    model.split = True
    model.convert()

    files = sorted(glob.glob(os.path.join(str(tmp_path), "frame_*.pdb")))
    assert len(files) == 4
    assert files[0].endswith("frame_00000000.pdb")


def test_view_spec_loads():
    from chisurf.plugins.traj.traj_convert.view_model import MDConverterViewModel

    spec = MDConverterViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)
