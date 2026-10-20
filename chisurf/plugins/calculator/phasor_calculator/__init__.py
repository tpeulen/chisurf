"""Interactive phasor-plot calculator.

A data-free phasor plot (Tools › Calculators › Phasor Calculator): place reference lifetimes, a FRET
trajectory and a two-component mixing line on the universal semicircle. Built from a
declarative ``phasor_emtk.view.json`` spec drawn by emtk over a plain model that assembles the
overlay geometry through the shared phasor toolkit
(:mod:`chisurf.plugins.microscopy.img_pixel_phasor.analysis`).
"""

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Calculators:Phasor Calculator"
