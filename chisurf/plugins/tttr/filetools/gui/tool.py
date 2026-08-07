"""FileToolsTool — the hub for everything that acts on a *file*.

A single window with a left navigation list and a lazily-loaded right panel
area. Each panel embeds one of the existing file tools **unchanged**:

    1. TTTR Split / Convert     — PTUSplitter
    2. TTTR → Time Windows      — TTTRTimeWindowTool
    3. BID → Analysis           — BidToAnalysisGUI
    4. ⇄ .pto                   — TttrToPtoTool
    5. PTO Inspector            — PtoInspectorTool
    6. TTTR header editor       — TagsEditor

They belong together because they are the same *kind* of operation: none of
them measures anything. They move a measurement between containers, read one
back, or correct what a vendor wrote into a header — which is why the packing
and unpacking of a ``.pto``, and the window that reads one, sit beside the
format converters rather than beside the analyses.

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

_PANEL_SPEC, FILETOOLS_PANELS = load_panels_json(pathlib.Path(__file__).with_name("panels.json"))


class FileToolsTool(NavigationPanelTool):
    """Unified file-tools hub with a left-navigation panel."""

    def __init__(self, parent=None):
        super().__init__(
            title=_PANEL_SPEC.get("title", f"{Glyphs.LOOP} File tools"),
            panels=FILETOOLS_PANELS,
            parent=parent,
            minimum_size=(900, 600),
            initial_size=(1300, 800),
            navigation_width=240,
            searchable=False,
            settings_key="filetools",
        )


__all__ = ["FileToolsTool"]
