"""K² Distribution calculator for FRET orientation factors.

Provides an emtk tool (``gui.app.make_app``) for computing and visualising the
orientation-factor distribution p(κ²) using Wobbling-in-Cone (WIC),
Diffusion-with-Traps (DWT) and isotropic models.  The window is the emtk app in ``gui/app.py``.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Structure:FRET:Kappa2 Distribution"
