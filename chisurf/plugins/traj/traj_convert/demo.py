"""Example data for the MD-Converter: the family's shipped example trajectory.

``make_demo`` resolves the in-repo NMSim example (894-frame DCD + PDB topology,
shared by the ``traj`` family — see :mod:`chisurf.plugins.traj.demo_data`); the
converter writes the (strided) frames as one DCD into the demo folder, which the
target-folder row points at.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.traj import demo_data

#: The converter names its output after the model's own base name (``out``).
OUTPUT = "out.dcd"
#: Convert a strided sample: the demo is about the wiring, not a full copy.
STRIDE = 40


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Return the example trajectory and topology the tool runs on."""
    return demo_data.family_demo(Path(__file__).parent.name)


def prepare(app, folder: Path) -> None:
    """Convert a strided sample of the frames."""
    app.model.stride = STRIDE


def load_into(app) -> Path:
    """Fill the tool from the example and run the conversion."""
    return demo_data.run_plugin_demo(app)
