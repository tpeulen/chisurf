"""Calculators hub plugin.

A two-panel launcher: pick a calculator on the left, use it embedded on the
right. It groups the independent FRET-line, FRET/homoFRET and FCS calculators
under a single ``Main:Tools:Calculators`` entry. The catalogue of calculators is
plain data in :mod:`.core.registry`; the native host (:mod:`.gui.app`) builds
each calculator's app lazily on first selection.
"""

# Plugin brand icon (unified emoji set)
icon = "🧮"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:Calculators:Calculators"

