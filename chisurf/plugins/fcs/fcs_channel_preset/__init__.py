from __future__ import annotations

from pathlib import Path

import chisurf as cs
from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Setup:FCS Definitions"

description = "FCS channel definition plugin per detector setup"
icon = "📡"


def load():
    """Return the FCS channel definition widget."""
    from .gui.tool import FCSChannelWidget

    return FCSChannelWidget()


def __getattr__(name):
    if name in {"FCSChannelWidget", "FCSChannelDialog"}:
        from .gui import tool

        return getattr(tool, name)
    raise AttributeError(name)


__all__ = [
    "FCSChannelWidget",
    "FCSChannelDialog",
    "load",
    "name",
    "description",
    "icon",
]

if __name__ == "plugin":
    try:
        from chisurf.plugins.fcs.fcs_channel_preset.gui.tool import FCSChannelWidget

        parent = getattr(cs, "cs", None)
        window = FCSChannelWidget(parent=parent)
        if _manifest is not None:
            apply_manifest_statefulness(window, _manifest)
        window.show()
    except Exception as exc:
        print(f"Failed to open FCS Channel preset: {exc}")
