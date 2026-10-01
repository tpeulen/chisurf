"""Trajectory alignment tool."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "📐"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Structure:Trajectory:Align"

__all__ = ["AlignTrajectoryWidget"]


def __getattr__(attribute):
    if attribute == "AlignTrajectoryWidget":
        from chisurf.plugins.traj.traj_align.widget import AlignTrajectoryWidget
        return AlignTrajectoryWidget
    raise AttributeError(attribute)

if __name__ == "plugin":
    window = __getattr__("AlignTrajectoryWidget")()
    window.show()
