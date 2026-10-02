"""FRET analysis from molecular dynamics trajectories."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🎞️"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Structure:Trajectory:FRET"

__all__ = ["Structure2Transfer"]


def __getattr__(attribute):
    # Lazy export: the Qt widget (and its qtpy import) must not load before the
    # native EMTK factory declared in the manifest.
    if attribute == "Structure2Transfer":
        from chisurf.plugins.traj.fret_trajectory.gui import Structure2Transfer

        return Structure2Transfer
    raise AttributeError(attribute)


if __name__ == "plugin":
    window = __getattr__("Structure2Transfer")()
    window.show()
