"""Small Qt widgets that belong to the node editor.

The one survivor of the old view layer: the palette a host uses to offer
node creation (:class:`WidgetPalette`). The lightpath simulator's tool
window hosts it beside its emtk canvas.
"""

from __future__ import annotations

from .widget_palette import WidgetPalette

__all__ = ["WidgetPalette"]
