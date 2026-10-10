"""MaxEnt TCSPC lifetime/FRET MEM plugin."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🌡️"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest else "Spectroscopy:Fluorescence decay:MaxEnt MEM"
cli_entrypoint = (
    _manifest.entrypoints.cli
    if _manifest
    else "maxent-decay=chisurf.plugins.fluorescence_decay.maxent_decay.cli.cli:cli"
)


def load():
    """Return the standalone MaxEnt MEM emtk app."""
    from .gui.app import make_app

    return make_app()


__all__ = ["name", "cli_entrypoint", "load"]
