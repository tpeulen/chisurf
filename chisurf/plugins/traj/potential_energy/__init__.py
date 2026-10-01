"""Potential energy calculator plugin."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "⚡"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Structure:Trajectory:Energy Calculator"

__all__ = ["PotentialEnergyWidget"]


def __getattr__(attribute):
    # Lazy export: the Qt widget (and its qtpy import) must not load before the
    # native EMTK factory, which the plugin scanner renders Qt-free.
    if attribute == "PotentialEnergyWidget":
        from chisurf.plugins.traj.potential_energy.widget import PotentialEnergyWidget

        return PotentialEnergyWidget
    raise AttributeError(attribute)


if __name__ == "plugin":
    window = __getattr__("PotentialEnergyWidget")()
    window.show()
