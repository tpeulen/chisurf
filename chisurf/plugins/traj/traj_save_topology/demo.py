"""Example data for the Save-Topology tool: the family's shipped example trajectory.

``make_demo`` resolves the in-repo NMSim example (894-frame DCD + PDB topology,
shared by the ``traj`` family — see :mod:`chisurf.plugins.traj.demo_data`); the
tool's action writes the DCD's topology (named atoms, from the trajectory's
first frame) as a PDB into the demo folder.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.traj import demo_data

OUTPUT = "topology_demo.pdb"


#: The example the tool runs on: the family's shipped NMSim trajectory (nothing is
#: simulated, so no seed), and what the tool writes from it.
DEMO = {"example": "modelling/fret/examples/olga_t4l", "output": OUTPUT}


def demo_folder() -> Path:
    """The settings-owned demonstration folder of this tool."""
    return demo_data.demo_folder(Path(__file__).parent.name)


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Return the example trajectory and topology the tool runs on."""
    return demo_data.family_demo(Path(__file__).parent.name)


def load_into(app) -> Path:
    """Fill the tool from the example and write the topology."""
    return demo_data.run_plugin_demo(app)
