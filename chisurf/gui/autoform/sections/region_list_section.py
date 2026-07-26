"""General ``region_list`` AutoForm section — the shared region editor.

Any tool that works with regions gets the whole editor from its ``.view.json``::

    {"type": "custom", "key": "region_list", "target": "regions",
     "title": "Regions",
     "options": {"image_attr": "current_image"},
     "description": "Named regions; tick to include, ~ to invert."}

``target`` names an attribute holding a
:class:`~chisurf.core.roi.collection.RegionCollection`. It does not have to
exist yet — the editor creates one and stores it back, so a view-model that only
declares the name is enough to start.

Options are :class:`~chisurf.gui.widgets.roi.editor.RegionEditor`'s:
``image_attr`` (what the regions are measured against), ``extent_attr`` (where a
new region is placed), ``refresh_on`` (which observer events redraw the list) and
``allow_shapes`` (whether regions can be drawn here at all, as opposed to only
painted or loaded).
"""

from __future__ import annotations

from chisurf.gui.autoform.sections.registry import register_section


@register_section("region_list")
def _region_list_section_factory(model, target: str = "regions", **options):
    """Custom-section factory for the shared region editor."""
    from chisurf.gui.widgets.roi import RegionEditor

    return RegionEditor(model, target or "regions", **options)


__all__ = []
