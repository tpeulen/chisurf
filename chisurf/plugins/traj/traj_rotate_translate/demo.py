"""Example data for the Rotate/Translate tool: the family's shipped example trajectory.

``make_demo`` resolves the in-repo NMSim example (894-frame DCD + PDB topology,
shared by the ``traj`` family — see :mod:`chisurf.plugins.traj.demo_data`); the
tool's action applies the current rotation/translation (the identity, unless the
fields say otherwise) and writes the moved DCD into the demo folder.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.traj import demo_data

OUTPUT = "moved.dcd"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Return the example trajectory and topology the tool runs on."""
    return demo_data.family_demo(Path(__file__).parent.name)


def load_into(app) -> Path:
    """Fill the tool from the example and run the transform."""
    return demo_data.run_plugin_demo(app)
