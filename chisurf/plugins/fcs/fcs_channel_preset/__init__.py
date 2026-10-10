from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Setup:FCS Definitions"

description = "FCS channel definition plugin per detector setup"
icon = "📡"


def load():
    """Return the emtk app of the FCS channel definition editor."""
    from .gui.app import create_app

    return create_app()


__all__ = ["load", "name", "description", "icon"]
