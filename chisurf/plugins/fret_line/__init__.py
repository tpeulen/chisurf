"""FRET line generator plugin — static, dynamic, WLC, and mixture modes.

Computes FRET efficiency lines (E_FRET and τ_X against τ_F) over parameter ranges
and overlays them on smFRET 2D histograms in ndxplorer. The window is the emtk app
:func:`chisurf.plugins.fret_line.gui.app.make_app`, declared by
``gui/fret_line_emtk.view.json`` over the Qt-free model ``gui/model.py``.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

# Plugin brand icon (unified emoji set)
icon = "🧵"

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "FRET:FRET Line Generator"
