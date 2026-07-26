"""The shared region-of-interest GUI.

Two pieces that a tool uses together or separately:

* :class:`~chisurf.gui.widgets.roi.editor.RegionEditor` — the list: name, shape,
  measurement, on/off, invert, the combining rule, save/load. No canvas needed.
* :class:`~chisurf.gui.widgets.roi.overlay.RegionOverlay` — the shapes drawn on
  a chiplot canvas, dragged by the user and written back.

Both edit one Qt-free
:class:`~chisurf.core.roi.collection.RegionCollection`, so the state a user
builds on screen is the same object a headless script or an RPC call uses.

Registering the editor as an AutoForm section means a plugin gets the whole
thing from its ``.view.json``::

    {"type": "custom", "key": "region_list", "target": "regions",
     "title": "Regions", "options": {"image_attr": "current_image"}}
"""

from __future__ import annotations

from .editor import SHAPES, RegionEditor
from .overlay import PALETTE, RegionOverlay, roi_from_handle

__all__ = [
    "RegionEditor",
    "RegionOverlay",
    "roi_from_handle",
    "SHAPES",
    "PALETTE",
]
