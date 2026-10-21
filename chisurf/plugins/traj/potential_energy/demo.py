"""Example data for the Potential-Energy calculator: the family's example trajectory.

``make_demo`` resolves the in-repo NMSim example (894-frame DCD + PDB topology,
shared by the ``traj`` family — see :mod:`chisurf.plugins.traj.demo_data`).
``prepare`` adds the first registered potential type (H-Bond, on its bundled
table) and strides the scan so *Process* scores a quick, deterministic sample of
the frames into the demo CSV.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.traj import demo_data

OUTPUT = "energies_demo.csv"
#: Score every Nth frame: the demo is about the wiring, not a full scan.
STRIDE = 20


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Return the example trajectory and topology the tool runs on."""
    return demo_data.family_demo(Path(__file__).parent.name)


def prepare(app, folder: Path) -> None:
    """Add one potential (the registry's first) so the action has something to score."""
    from chisurf.plugins.traj.potential_energy.potential_specs import (
        make_potential,
        potential_names,
    )

    if not app.model.universe.potentials:
        name = potential_names()[0]
        app.model.add_potential(make_potential(name, {}), 1.0, name=name)
    app.model.stride = STRIDE


def load_into(app) -> Path:
    """Fill the tool from the example and run the energy scan."""
    return demo_data.run_plugin_demo(app)
