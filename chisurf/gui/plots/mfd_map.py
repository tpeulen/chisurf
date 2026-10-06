"""The MFD 2D map, as a *plot* on the fit window's emtk surface.

The map belongs with the other plots, not in the analysis dock beside the
parameters: it is what you look at while fitting, it wants the room a plot tab
gives it, and the dock is for controls.

It is one chiplot panel showing the model's ``target`` array on the real axes
(``extent_source``: proximity ratio and ⟨t⟩, never bin indices), with two
selectors drawn above it by emtk: the **channel** -- measured, model, residual,
difference on the *same* axes and colour scale, which compares better than two
heat maps side by side -- and the **colormap**. The options are the view spec's,
in the vocabulary the AutoForm image section uses (``channel_source``,
``channel_attr``, ``channel_call``, ``colormap_attr``, ``default_colormap``,
``x_label``, ``y_label``).
"""

from __future__ import annotations

import inspect

import numpy as np

from chisurf import logging
from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase

#: The colormaps offered; the spec's default is added when it is not among them.
COLORMAPS = ("inferno", "magma", "viridis", "plasma", "cividis", "gray", "RdBu_r")


class MfdMapPlot(plotbase.Plot):
    """The 2D MFD histogram, hosted in a plot tab."""

    name = "MFD map"

    def __init__(self, fit, parent=None, target: str = "mfd_image", **options):
        """Build the panel, bound to the fit's model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit whose model supplies the map.
        parent : object, optional
            Parent widget.
        target : str
            Model method returning the 2D array, rows along y.
        **options
            The view spec's plot options (see the module docstring).
        """
        super().__init__(fit, parent=parent)
        self.model = getattr(fit, "model", None)
        self.target = target
        self.options = dict(options)
        default = str(options.get("default_colormap", "inferno"))
        self.colormaps = list(COLORMAPS) if default in COLORMAPS else [default, *COLORMAPS]
        self.colormap = self._read_attr(options.get("colormap_attr"), default)
        self.panel = cp.Panel()
        self.panel.set_labels(
            bottom=options.get("x_label", "x"), left=options.get("y_label", "y")
        )
        from chisurf.gui.plots.emtk_page import PanelItem

        self.panel_items = [PanelItem(self.panel, self.panel._canvas)]
        self._image = None
        self._extent = None
        self.update_all()

    # -- model binding --------------------------------------------------- #
    def _read_attr(self, name, default):
        if name and self.model is not None:
            value = getattr(self.model, name, None)
            if value:
                return value
        return default

    def _call(self, name, *args):
        method = getattr(self.model, name, None) if name else None
        if not callable(method):
            return None
        try:
            if args and not inspect.signature(method).parameters:
                return method()
        except (TypeError, ValueError):
            pass
        return method(*args)

    def channels(self) -> list[str]:
        """The names the channel selector offers."""
        names = self._call(self.options.get("channel_source"))
        return [str(n) for n in names] if names else []

    def channel(self) -> str:
        """The channel shown now."""
        return str(self._read_attr(self.options.get("channel_attr"), ""))

    def set_channel(self, name: str) -> None:
        """Show another channel: write it to the model, let the model react, redraw."""
        attr = self.options.get("channel_attr")
        if attr and self.model is not None:
            setattr(self.model, attr, name)
        self._call(self.options.get("channel_call"), name)
        self.update_all()

    def set_colormap(self, name: str) -> None:
        """Recolour the map; the choice is kept on the model when the spec names where."""
        self.colormap = str(name)
        attr = self.options.get("colormap_attr")
        if attr and self.model is not None:
            setattr(self.model, attr, self.colormap)
        if self._image is not None:
            self._image.set_colormap(cp.to_colormap(self.colormap))

    # -- drawing ---------------------------------------------------------- #
    def update_all(self, *args, **kwargs) -> None:
        """Re-read the map and its extent from the model."""
        try:
            data = np.asarray(self._call(self.target), dtype=float)
        except Exception:
            # A map that cannot be read must not take the fit window down with
            # it; the panel keeps whatever it last drew.
            logging.warning(f"MFD map: reading {self.target} failed")
            return
        if data.ndim != 2 or not data.size:
            return
        extent = self._call(self.options.get("extent_source"))
        if extent is None:
            extent = (0.0, float(data.shape[1]), 0.0, float(data.shape[0]))
        x0, x1, y0, y1 = (float(v) for v in extent)
        rect = (x0, y0, x1 - x0, y1 - y0)
        finite = data[np.isfinite(data)]
        levels = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
        if levels[1] <= levels[0]:
            levels = (levels[0], levels[0] + 1.0)
        if self._image is None:
            self._image = self.panel.image(
                data, colormap=self.colormap, levels=levels, rect=rect
            )
        else:
            self._image.set_image(data)
            self._image.set_levels(*levels)
            self._image.set_rect(*rect)
        if extent != self._extent:
            self.panel.set_range(x=(x0, x1), y=(y0, y1), padding=0.0)
            self._extent = extent

    def update(self, *args, **kwargs) -> None:
        """Redraw, then run the base-class update."""
        self.update_all()
        super().update(*args, **kwargs)

    def emtk_draw(self, box) -> None:
        """The selectors above the map, then the map (inside an emtk frame)."""
        from emtk import im

        channels = self.channels()
        if channels:
            im.text("Channel")
            im.same_line()
            current = channels.index(self.channel()) if self.channel() in channels else 0
            im.set_next_item_width(130.0)
            changed, picked = im.combo("##mfd-channel", current, channels)
            im.set_item_tooltip(
                "Which map to show on these axes: the measured histogram, the model, "
                "the weighted residual or the difference."
            )
            if changed:
                self.set_channel(channels[picked])
            im.same_line()
        im.text("Colormap")
        im.same_line()
        index = self.colormaps.index(self.colormap) if self.colormap in self.colormaps else 0
        im.set_next_item_width(110.0)
        changed, picked = im.combo("##mfd-colormap", index, self.colormaps)
        im.set_item_tooltip("Colour scale of the map; the counts are unchanged.")
        if changed:
            self.set_colormap(self.colormaps[picked])
        im.host_control("##mfd-map", self.panel_items[0])
