"""The native QuEst window of this plugin: the QuEst card of Structure Tools, hosted on its own.

The card (``chisurf.plugins.modelling.structure_tools.cards.quest``) is the emtk counterpart of ``QuEstTool``: the project
form of ``quest.view.json``, the quenching table, the three result plots, a 3D trace of the structure and the project JSON.
It is reused here, not copied; the import is inside the factory so that importing this module pulls in neither IMP nor quest.
"""

from __future__ import annotations


def make_app():
    """Build the QuEst window (the card, as an app of its own)."""
    from chisurf.plugins.modelling.structure_tools.cards.quest import make_app as make_card

    return make_card()
