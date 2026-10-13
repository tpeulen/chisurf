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


__all__ = ["name", "icon", "cli_entrypoint"]


if (
    __name__ == "plugin"
):  # pragma: no cover - the legacy macro launch; the manifest's emtk entry comes first
    from emtk.qt_host import ControlHost

    from chisurf.plugins.core.lightpath_simulator.gui.app import create_app

    window = ControlHost(create_app())
    if _manifest is not None:
        apply_manifest_statefulness(window, _manifest)
    window.show()
