"""Example data for Join-Trajectories: the family's example trajectory, twice.

``make_demo`` resolves the in-repo NMSim example (894-frame DCD + PDB topology,
shared by the ``traj`` family — see :mod:`chisurf.plugins.traj.demo_data`).
Both trajectory rows point at the example, so the join in ``time`` mode writes
twice its 894 frames; the tool has no topology row, so ``prepare`` hands the
model the PDB directly.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.traj import demo_data

OUTPUT = "joined.dcd"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Return the example trajectory and topology the tool runs on."""
    return demo_data.family_demo(Path(__file__).parent.name)


def prepare(app, folder: Path) -> None:
    """Give the join its topology (the tool has no topology row of its own)."""
    if not app.model.topology_filename:
        app.model.set_topology(str(demo_data.TOPOLOGY))


def load_into(app) -> Path:
    """Fill the tool from the example and run the join."""
    return demo_data.run_plugin_demo(app)
