"""The native FRET docking app: the docking window and the pair selection window of the plugin.

The docking window is the Structure Tools docking card (imported, not copied: its own Qt-free session, spec, tour and
help); the pair selection window is this plugin's own (``pair_selection_app``). Both live in one window with a short
list of tools on the left, in the mechanics of the Structure Tools hub.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.modelling.structure_tools.app import StructureToolsHubApp

ENTRIES = [
    {
        "name": "Docking & Screening",
        "group": 0,
        "description": "FRET-restrained rigid-body docking, refinement and structure-library screening (IMP + IMP.bff).",
        "emtk": "chisurf.plugins.modelling.structure_tools.cards.docking:make_app",
    },
    {
        "name": "Pair Selection",
        "group": 0,
        "description": "Choose the most informative FRET pairs to tell the conformations of a trajectory apart.",
        "emtk": "chisurf.plugins.modelling.fret.gui.pair_selection_app:make_app",
    },
]


class FretApp(StructureToolsHubApp):
    """Docking & Screening and Pair Selection in one window."""

    ENTRIES = ENTRIES
    TITLE = "FRET"
    COMPACT = True
    GUIDE_FILE = Path(__file__).parent / "guide.json"
    HELP_FILE = Path(__file__).parent / "help.md"


def make_app() -> FretApp:
    """The FRET docking plugin's native app."""
    return FretApp()


__all__ = ["FretApp", "make_app"]
