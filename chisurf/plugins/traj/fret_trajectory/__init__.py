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

__all__ = ["FretTrajectoryApp", "make_app"]


def __getattr__(attribute):
    """Resolve the native surface lazily without loading an optional Qt host."""
    if attribute in __all__:
        from chisurf.plugins.traj.fret_trajectory import app

        return getattr(app, attribute)
    raise AttributeError(attribute)
