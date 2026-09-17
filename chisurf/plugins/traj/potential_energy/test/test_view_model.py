"""Headless (Qt-free) tests for the Potential-Energy view-model."""

import numpy as np
import pytest


def _peptide_trajectory(path: str, n_res: int = 3, n_frames: int = 4) -> str:
    """Write a small *n_res*-residue ALA peptide trajectory to *path* (.dcd).

    Uses real backbone atom names/elements so the chisurf structure reader can
    parse it and the potentials have a genuine structure to score. Returns the
    topology PDB written beside it, since a DCD names no atoms.
    """
    from chisurf.core.fio.trajectory import write_dcd
    from chisurf.core.structure import trajectory_data as md
    elements = {
        "N": md.element.nitrogen,
        "CA": md.element.carbon,
        "C": md.element.carbon,
        "O": md.element.oxygen,
    }
    topology = md.Topology()
    chain = topology.add_chain()
    for _ in range(n_res):
        residue = topology.add_residue("ALA", chain)
        for name in ("N", "CA", "C", "O"):
            topology.add_atom(name, elements[name], residue)
    n_atoms = 4 * n_res
    rng = np.random.default_rng(0)
    # Ångström, spread over ~10 Å so the radius of gyration is nonzero.
    xyz = (10.0 * rng.random((n_frames, n_atoms, 3))).astype(np.float32)
    write_dcd(path, xyz)
    pdb = str(path).replace(".dcd", ".pdb")
    md.Trajectory(xyz=xyz, topology=topology)[0].save_pdb(pdb)
    return pdb


class _RadiusGyrationPotential:
    """Minimal Qt-free radius-of-gyration potential for the headless tests."""

    name = "Radius-Gyration"

    def __init__(self, structure=None):
        self.structure = structure

    def getEnergy(self):  # noqa: N802 (matches the potential interface)
        """Return the radius of gyration of the current structure."""
        return float(self.structure.radius_gyration)


def test_log_starts_ready():
    from chisurf.plugins.traj.potential_energy.view_model import PotentialEnergyViewModel

    assert "Ready" in PotentialEnergyViewModel().log_html()


def test_stride_round_trips():
    from chisurf.plugins.traj.potential_energy.view_model import PotentialEnergyViewModel

    model = PotentialEnergyViewModel()
    model.stride = 7
    assert model.stride == 7


def test_set_trajectory_round_trips_and_notifies():
    from chisurf.plugins.traj.potential_energy.view_model import PotentialEnergyViewModel

    model = PotentialEnergyViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory("/data/traj.h5")
    assert model.trajectory_file == "/data/traj.h5"
    assert "loaded" in events


def test_add_and_remove_potential_updates_table_and_universe():
    from chisurf.plugins.traj.potential_energy.view_model import PotentialEnergyViewModel

    model = PotentialEnergyViewModel()
    assert model.added_potentials() == []

    model.add_potential(_RadiusGyrationPotential(), 2.0)
    model.add_potential(_RadiusGyrationPotential(), 0.5, name="second")

    rows = model.added_potentials()
    assert [r["name"] for r in rows] == ["Radius-Gyration", "second"]
    assert [r["weight"] for r in rows] == [2.0, 0.5]
    assert [r["idx"] for r in rows] == [0, 1]
    assert len(model.universe.potentials) == 2
    assert model.universe.scaling == [2.0, 0.5]

    # Double-click removal path (dispatched by the table section with a row dict).
    model.remove_potential_activated(rows[0])
    rows = model.added_potentials()
    assert [r["name"] for r in rows] == ["second"]
    assert len(model.universe.potentials) == 1
    assert model.universe.scaling == [0.5]


def test_process_writes_csv_end_to_end(tmp_path):
    from chisurf.plugins.traj.potential_energy.view_model import PotentialEnergyViewModel

    source = tmp_path / "peptide.dcd"
    csv_path = tmp_path / "energies.txt"
    n_frames = 4
    topology = _peptide_trajectory(str(source), n_res=3, n_frames=n_frames)

    model = PotentialEnergyViewModel()
    model.set_trajectory(str(source))
    model.set_topology(topology)
    model.add_potential(_RadiusGyrationPotential(), 1.0)

    seen = []
    n = model.process(str(csv_path), progress_cb=seen.append)

    assert n == n_frames
    assert seen == list(range(1, n_frames + 1))
    assert csv_path.exists()

    lines = csv_path.read_text().splitlines()
    header = lines[0].split("\t")
    assert header[0] == "FrameNbr"
    assert "Radius-Gyration" in header[1]
    body = [line for line in lines[1:] if line.strip()]
    assert len(body) == n_frames
    for row in body:
        cells = [c for c in row.split("\t") if c != ""]
        # FrameNbr + one numeric energy column.
        assert len(cells) == 2
        float(cells[0])
        energy = float(cells[1])
        assert energy > 0.0  # radius of gyration of a spread-out peptide is positive
        # Coordinates within a 10-Å cube: a radius of gyration beyond that means
        # the frame was scaled on the way in (the old nm -> Å ×10).
        assert energy < 10.0
    assert "Processed" in model.log_html()


def test_process_reads_with_the_stride_it_numbers_by(tmp_path):
    from chisurf.plugins.traj.potential_energy.view_model import PotentialEnergyViewModel

    source = tmp_path / "peptide.dcd"
    csv_path = tmp_path / "energies.txt"
    topology = _peptide_trajectory(str(source), n_res=3, n_frames=4)

    model = PotentialEnergyViewModel()
    model.set_trajectory(str(source))
    model.set_topology(topology)
    model.stride = 2
    model.add_potential(_RadiusGyrationPotential(), 1.0)

    assert model.process(str(csv_path)) == 2
    rows = [line.split("\t")[0] for line in csv_path.read_text().splitlines()[1:] if line.strip()]
    assert rows == ["1", "3"]


def test_process_without_trajectory_is_noop(tmp_path):
    from chisurf.plugins.traj.potential_energy.view_model import PotentialEnergyViewModel

    model = PotentialEnergyViewModel()
    csv_path = tmp_path / "out.txt"
    assert model.process(str(csv_path)) == 0
    assert "No trajectory selected" in model.log_html()
    assert not csv_path.exists()


def test_view_spec_loads():
    from chisurf.plugins.traj.potential_energy.view_model import PotentialEnergyViewModel

    spec = PotentialEnergyViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)
