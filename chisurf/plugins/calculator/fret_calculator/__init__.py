"""Combined FRET / HomoFRET Calculator Plugin.

Provides heteroFRET and homoFRET parameter calculations in a single tabbed
window, backed by the new client-server architecture.

The window is the native emtk app in :mod:`.gui.app`; importing this package — and with
it the ``api`` / ``core`` / ``backend`` layers — needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

# Load manifest as source of truth
_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:Calculators:FRET Calculator"
