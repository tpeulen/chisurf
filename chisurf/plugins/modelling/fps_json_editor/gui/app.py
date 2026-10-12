"""The native FPS JSON editor: the Structure Tools FPS card as a window of its own.

The editor (Positions, Distances, FlexFit, JSON and 3D tabs, AV computation, MRC export) is the card of
``structure_tools`` (imported, not copied): its Qt-free model, specs, guide and help. The Qt tool's RCSB fetch is the
card's PDB-ID fetch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the names __getattr__ serves, for linters and type checkers
    from chisurf.plugins.modelling.structure_tools.cards.fps_json import FpsJsonCard, make_app

__all__ = ["FpsJsonCard", "make_app"]


def __getattr__(name: str):
    """Serve the Structure Tools card on first access.

    The card lives in the plugin that hosts it and that plugin imports this one's model, so a
    module-level import here would make the two plugins require each other.
    """
    if name == "FpsJsonCard":
        from chisurf.plugins.modelling.structure_tools.cards.fps_json import FpsJsonCard

        return FpsJsonCard
    if name == "make_app":
        from chisurf.plugins.modelling.structure_tools.cards.fps_json import make_app

        return make_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
