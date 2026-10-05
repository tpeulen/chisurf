"""The native FPS JSON editor: the Structure Tools FPS card as a window of its own.

The editor (Positions, Distances, FlexFit, JSON and 3D tabs, AV computation, MRC export) is the card of
``structure_tools`` (imported, not copied): its Qt-free model, specs, guide and help. The Qt tool's RCSB fetch is the
card's PDB-ID fetch.
"""

from __future__ import annotations

from chisurf.plugins.modelling.structure_tools.cards.fps_json import FpsJsonCard, make_app

__all__ = ["FpsJsonCard", "make_app"]
