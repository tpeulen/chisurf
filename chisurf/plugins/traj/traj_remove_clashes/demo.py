"""Example data for the Remove-Clashed tool: the family's shipped example trajectory.

``make_demo`` resolves the in-repo NMSim example (894-frame DCD + PDB topology,
shared by the ``traj`` family — see :mod:`chisurf.plugins.traj.demo_data`); the
tool's action drops the clashing frames and writes the rest into the demo folder.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.traj import demo_data

OUTPUT = "clash_free.dcd"
#: Screen a strided sample: the demo is about the wiring, not a full scan.
STRIDE = 20


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Return the example trajectory and topology the tool runs on."""
    return demo_data.family_demo(Path(__file__).parent.name)


def prepare(app, folder: Path) -> None:
    """Screen a strided sample of the frames."""
    app.model.stride = STRIDE


def load_into(app) -> Path:
    """Fill the tool from the example and run the clash screen."""
    return demo_data.run_plugin_demo(app)
