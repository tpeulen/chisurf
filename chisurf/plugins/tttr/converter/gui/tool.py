"""ConverterTool — unified converter hub using NavigationPanelTool.

A single window with a left navigation list and a lazily-loaded right panel
area. Each panel embeds one of the existing conversion tools **unchanged**:

    1. TTTR Split / Convert     — PTUSplitter
    2. TTTR → Time Windows      — TTTRTimeWindowTool
    3. BID → Analysis           — BidToAnalysisGUI

Panels are imported lazily inside their factory functions so the combined
window opens fast and a sub-tool whose heavy dependencies are missing only
breaks its own panel (NavigationPanelTool renders an error panel) rather than
the whole window.
"""

from __future__ import annotations

import pathlib

from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.navigation import NavigationPanelTool, load_panels_json

# ---------------------------------------------------------------------------
# Data-driven panel list
# ---------------------------------------------------------------------------
# Panels are declared in ``panels.json`` and translated by the shared
# ``load_panels_json`` helper (lazy entrypoint factories; ``embed`` flattens
# QMainWindow tools). Adding a tool is a single JSON entry — no Python.

_PANEL_SPEC, CONVERTER_PANELS = load_panels_json(pathlib.Path(__file__).with_name("panels.json"))


class ConverterTool(NavigationPanelTool):
    """Unified converter hub with a left-navigation panel."""

    def __init__(self, parent=None):
        super().__init__(
            title=_PANEL_SPEC.get("title", f"{Glyphs.LOOP} Converter"),
            panels=CONVERTER_PANELS,
            parent=parent,
            minimum_size=(900, 600),
            initial_size=(1200, 750),
            navigation_width=220,
            searchable=False,
            settings_key="converter",
        )


__all__ = ["ConverterTool"]
