"""TttrToolboxTool — unified TTTR file toolbox using NavigationPanelTool.

A single window with a left navigation list and a lazily-loaded right panel area.
Each panel embeds one of the existing TTTR tools **unchanged**:

    1. ALEX Creator         — AlexPTUCreator
    2. Micro-time Shifter   — MicrotimeShifterTool
    3. PTU Header Editor    — TagsEditor
    ───────────────────────  (separator)
    4. Split / Convert      — PTUSplitter

Panels are imported lazily inside their factory functions so the combined window
opens fast and a sub-tool whose heavy dependencies are missing only breaks its own
panel (NavigationPanelTool renders an error panel) rather than the whole window.
"""

from __future__ import annotations

import pathlib

from chisurf.gui.widgets.navigation import NavigationPanelTool, load_panels_json

# ---------------------------------------------------------------------------
# Data-driven panel list
# ---------------------------------------------------------------------------
# Panels are declared in ``panels.json`` and translated by the shared
# ``load_panels_json`` helper (lazy entrypoint factories; ``embed`` flattens
# QMainWindow tools). Adding a tool is a single JSON entry — no Python.

_PANEL_SPEC, TTTR_PANELS = load_panels_json(pathlib.Path(__file__).with_name("panels.json"))


class TttrToolboxTool(NavigationPanelTool):
    """Unified TTTR file toolbox with a left-navigation panel."""

    def __init__(self, parent=None):
        super().__init__(
            title=_PANEL_SPEC.get("title", "🧰 TTTR Tools"),
            panels=TTTR_PANELS,
            parent=parent,
            minimum_size=(900, 600),
            initial_size=(1200, 750),
            navigation_width=210,
            settings_key="tttr_toolbox",
        )


__all__ = ["TttrToolboxTool"]
