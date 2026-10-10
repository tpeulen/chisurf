"""Single Molecule Burst Selection Plugin.

The tool is the emtk app ``gui.native:create_app`` over the Qt-free model ``gui.model``; the search, the CLI and the
backend services are Qt-free as well.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

# Load manifest as source of truth
_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    # Legacy fallback
    name = "Spectroscopy:Single-Molecule:Burst-Selection"
    cli_entrypoint = "burst-selection=chisurf.plugins.burst.burst_selection.cli:cli"
