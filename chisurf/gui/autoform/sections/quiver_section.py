"""AutoForm ``quiver`` section: a vector field drawn over an image.

Arrows on a picture are the natural display for anything that measures a
*direction per place* — a flow map, a drift field, a tracking summary — and none
of the existing sections can show one: the image section draws points, and a
plot section draws curves.

Declare it in a view spec as a custom section::

    {"type": "custom", "key": "quiver", "title": "Flow field",
     "options": {"image_source": "flow_image",
                 "vectors_source": "flow_vectors",
                 "extent_source": "flow_extent",
                 "scale_attr": "arrow_scale",
                 "units": "µm/s"}}

Options
-------
``image_source``
    Model method returning the 2-D background image, or ``None`` for a bare
    field.
``vectors_source``
    Model method returning the arrows as a list of dicts with ``x``, ``y``,
    ``dx``, ``dy`` and an optional ``value`` used for colouring. Coordinates are
    in the same units as ``extent_source``.
``extent_source``
    Model method returning ``(x0, x1, y0, y1)`` — the real-world span the image
    covers, so the arrows and the picture share one coordinate system. Without
    it both are in pixel indices.
``scale_attr``
    Model attribute (float) multiplying the drawn arrow length. Display only:
    it never touches the numbers, which is why the section shows the scale it
    used rather than hiding it.
``colormap``
    Colormap for the arrow colours (default ``"inferno"``).
``units``
    Unit shown in the colour legend.

Every arrow is drawn as a chiplot line plus a chiplot arrow head, so the section
carries no renderer-specific code (PRD-64). An arrow of zero length is skipped
rather than drawn as a dot: a tile with no measurable velocity should look
empty, not like a very slow one.
"""

from __future__ import annotations

import logging

import numpy as np
from qtpy import QtWidgets

from chisurf.gui import chiplot as cp

from .registry import register_section

logger = logging.getLogger(__name__)


@register_section("quiver")
class QuiverSectionWidget(QtWidgets.QWidget):
    """A vector field over an optional image background."""

    AUTOFORM_REFRESH = True
    _autoform_expanding = True

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        self._image_source = str(options.get("image_source", "") or "")
        self._vectors_source = str(options.get("vectors_source", target or "") or "")
        self._extent_source = str(options.get("extent_source", "") or "")
        self._scale_attr = str(options.get("scale_attr", "") or "")
        self._colormap = str(options.get("colormap", "inferno") or "inferno")
        self._units = str(options.get("units", "") or "")
        self._items: list = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.plot = cp.Plot()
        self.plot.set_labels(bottom=str(options.get("x_label", "x") or "x"),
                             left=str(options.get("y_label", "y") or "y"))
        try:
            self.plot.set_aspect_locked(True)
            # Image coordinates: row 0 is the top row, so an un-inverted axis
            # shows the picture upside down *and* mirrors every arrow's y
            # component against it.
            self.plot.invert_y(True)
        except Exception:
            logger.debug("chiplot backend cannot orient the axes", exc_info=True)
        layout.addWidget(self.plot, 1)
        self.caption = QtWidgets.QLabel("")
        self.caption.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.caption)
        self.refresh()

    # ── model access ──
    def _call(self, name):
        """Call a named model method, returning ``None`` when it is absent."""
        fn = getattr(self._model, name, None) if name else None
        try:
            return fn() if callable(fn) else None
        except Exception:
            logger.debug("quiver source %r failed", name, exc_info=True)
            return None

    def refresh(self) -> None:
        """Redraw the background and every arrow from the model."""
        try:
            self._refresh()
        except Exception:
            # A section that raises during a rebuild leaves the form half-built
            # and the caption stale, which reads as "no data" rather than as a
            # bug. Say so instead.
            logger.debug("quiver refresh failed", exc_info=True)
            self.caption.setText("The vector field could not be drawn (see the log).")

    def _refresh(self) -> None:
        """Do the redraw; see :meth:`refresh`, which guards it."""
        for item in self._items:
            try:
                self.plot.remove(item)
            except Exception:
                logger.debug("could not remove a quiver item", exc_info=True)
        self._items = []

        extent = self._call(self._extent_source)
        image = self._call(self._image_source)
        if image is not None:
            data = np.asarray(image, dtype=float)
            if data.ndim == 2 and data.size:
                rect = None
                if extent is not None and len(extent) == 4:
                    x0, x1, y0, y1 = (float(v) for v in extent)
                    rect = (x0, y0, x1 - x0, y1 - y0)
                self._items.append(
                    self.plot.image(data.T, colormap="gray", rect=rect)
                )

        vectors = self._call(self._vectors_source) or []
        scale = float(getattr(self._model, self._scale_attr, 1.0) or 1.0) \
            if self._scale_attr else 1.0
        drawn, speeds = 0, []
        magnitudes = [
            float(np.hypot(v.get("dx", 0.0), v.get("dy", 0.0))) for v in vectors
        ]
        largest = max(magnitudes) if magnitudes else 0.0
        for vector, magnitude in zip(vectors, magnitudes):
            if not np.isfinite(magnitude) or magnitude <= 0.0:
                continue
            x, y = float(vector["x"]), float(vector["y"])
            dx = float(vector.get("dx", 0.0)) * scale
            dy = float(vector.get("dy", 0.0)) * scale
            colour = self._colour(magnitude, largest)
            self._items.append(
                self.plot.line([x, x + dx], [y, y + dy], pen=colour, width=2)
            )
            self._items.append(
                self.plot.arrow(
                    x + dx, y + dy,
                    angle=float(np.degrees(np.arctan2(dy, dx))),
                    size=9.0, brush=colour, pen=None,
                )
            )
            drawn += 1
            speeds.append(magnitude)

        if extent is not None and len(extent) == 4:
            x0, x1, y0, y1 = (float(v) for v in extent)
            try:
                self.plot.set_range(x=(x0, x1), y=(y0, y1))
            except Exception:
                logger.debug("chiplot backend cannot set an explicit range", exc_info=True)
        self._set_caption(drawn, len(vectors), speeds, scale)

    def _colour(self, magnitude: float, largest: float) -> str:
        """Map a magnitude to a colour, warm for fast and cool for slow."""
        fraction = 0.0 if largest <= 0 else min(1.0, magnitude / largest)
        red = int(255 * min(1.0, 0.35 + 0.65 * fraction))
        green = int(200 * (1.0 - 0.75 * fraction))
        return f"#{red:02x}{green:02x}40"

    def _set_caption(self, drawn: int, total: int, speeds, scale: float) -> None:
        """Say how many arrows are shown and what the longest one means."""
        if not drawn:
            self.caption.setText(
                "No arrows — nothing passed the quality threshold, or the field is empty."
            )
            return
        unit = f" {self._units}" if self._units else ""
        parts = [f"{drawn} of {total} arrows"]
        if speeds:
            parts.append(f"fastest {max(speeds):.3g}{unit}")
        if abs(scale - 1.0) > 1e-9:
            parts.append(f"drawn at {scale:g}x (display only)")
        self.caption.setText(" · ".join(parts))

    def sync(self) -> None:
        """AutoForm hook: redraw when the model changed."""
        self.refresh()
