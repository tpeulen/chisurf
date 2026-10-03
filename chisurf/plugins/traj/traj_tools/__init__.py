"""Combined trajectory tools plugin."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🧰"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Structure:Trajectory:Traj Tools"
    cli_entrypoint = ""

__all__ = ["TrajectoryToolsTool"]


def __getattr__(attribute):
    # Lazy export: the Qt widget (and its qtpy import) must not load before the
    # native EMTK factory declared in the manifest.
    if attribute == "TrajectoryToolsTool":
        from chisurf.plugins.traj.traj_tools.gui.tool import TrajectoryToolsTool

        return TrajectoryToolsTool
    raise AttributeError(attribute)


if __name__ == "plugin":
    window = __getattr__("TrajectoryToolsTool")()
    window.show()
