"""Example data for Trajectory→FRET: the family's shipped example trajectory.

``make_demo`` resolves the in-repo NMSim example (894-frame DCD + PDB topology,
shared by the ``traj`` family — see :mod:`chisurf.plugins.traj.demo_data`).
``prepare`` picks the donor and acceptor dipole atom pairs, four CA atoms spread
along the protein, so *Process trajectory* computes a per-frame transfer table.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.traj import demo_data

OUTPUT = "fret_demo.csv"


def _ca_indices(pdb_path: Path) -> list[int]:
    """The first four CA atom indices of the example topology."""
    from chisurf.core.structure import trajectory_data as md

    topology = md.load(str(pdb_path)).topology
    return [int(i) for i in topology.select("name CA")][:4]


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Return the example trajectory and topology the tool runs on."""
    return demo_data.family_demo(Path(__file__).parent.name)


def prepare(app, folder: Path) -> None:
    """Pick the donor/acceptor dipole pairs (CA atoms of the example topology)."""
    if not app.model.donor:
        indices = _ca_indices(demo_data.TOPOLOGY)
        app.model.donor = (indices[0], indices[1])
        app.model.acceptor = (indices[2], indices[3])


def load_into(app) -> Path:
    """Fill the tool from the example and run the transfer calculation."""
    return demo_data.run_plugin_demo(app)
