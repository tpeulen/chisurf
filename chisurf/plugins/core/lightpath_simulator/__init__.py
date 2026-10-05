from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness

# Load manifest as source of truth
_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    icon = _manifest.icon
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Tools:Calculators:Light Path Simulator"
    icon = "🔦"
    cli_entrypoint = "lightpath-simulator=chisurf.plugins.core.lightpath_simulator.cli:cli"


__all__ = ["LightPathSimulatorWidget"]

def __getattr__(name):
    if name == 'LightPathSimulatorWidget':
        from .gui.tool import LightPathSimulatorWidget
        return LightPathSimulatorWidget
    raise AttributeError(name)


# When the plugin is loaded, this code will be executed
if __name__ == "plugin":
    from .gui.tool import LightPathSimulatorWidget
    window = LightPathSimulatorWidget()
    if _manifest is not None:
        apply_manifest_statefulness(window, _manifest)
    window.show()
