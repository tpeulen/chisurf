"""AutoForm ``decay_conv`` section: live decay + IRF plot with a draggable range.

Plots the selected detector's data decay (semilog) and, if set, its IRF, with a
draggable convolution-range region. Dragging the region writes the range back to
the model (``set_conv_range``); the model's value fields stay in sync. Reads
``model.<target>()`` → ``{"data", "irf", "conv": (start, stop), "bg", "n"}``.
"""

from __future__ import annotations

import logging

import numpy as np
from qtpy import QtWidgets

from chisurf.gui import chiplot as cp
from .registry import register_section

logger = logging.getLogger(__name__)


@register_section("decay_conv")
class DecayConvWidget(QtWidgets.QWidget):
    """Decay/IRF plot with a draggable convolution-range region + BG line."""

    AUTOFORM_REFRESH = True
    _autoform_expanding = True

    def __init__(self, model, target: str, **options):
        super().__init__()
        self._model = model
        self._target = target

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._plot = cp.Plot(title=str(options["title"]) if options.get("title") else None)
        self._plot.set_log(y=True)
        self._plot.set_labels(bottom="micro-time channel", left="counts")
        self._plot.legend(offset=(-10, 10))
        self._data_curve = self._plot.line([], [], pen=(0, 200, 255), width=1, name="data")
        self._irf_vv_curve = self._plot.line([], [], pen=(255, 80, 200), width=1, name="IRF VV")
        self._irf_vh_curve = self._plot.line([], [], pen=(255, 170, 60), width=1, name="IRF VH")
        # Convolution/fit window (blue) and the separate IRF window (green).
        self._region = self._plot.region((0.0, 1.0), brush=(80, 160, 255, 40), movable=True)
        self._region.on_change(self._on_region, final=True)
        self._irf_region = self._plot.region(
            (0.0, 1.0), brush=(80, 255, 140, 30), pen=cp.to_pen((80, 255, 140), width=1), movable=True,
        )
        self._irf_region.on_change(self._on_irf_region, final=True)
        # Background-estimation region (grey): mean data counts here → bg_vv/bg_vh.
        self._bg_region = self._plot.region(
            (0.0, 0.0), brush=(180, 180, 180, 40), pen=cp.to_pen((180, 180, 180), width=1), movable=True,
        )
        self._bg_region.on_change(self._on_bg_region, final=True)
        layout.addWidget(self._plot, 1)
        self.refresh()

    def _payload(self):
        source = getattr(self._model, self._target, None) if self._target else None
        if not callable(source):
            return None
        try:
            return source()
        except Exception:
            logger.debug("decay_conv: source %r failed", self._target, exc_info=True)
            return None

    def refresh(self) -> None:
        """Redraw data + IRF and move the range/BG markers to the model's values."""
        payload = self._payload()
        if not payload:
            return
        # ``set_bounds`` is signal-safe, so moving the markers here does not
        # re-enter the region handlers.
        data = np.asarray(payload["data"], dtype=float)
        x = np.arange(data.size)
        self._data_curve.set_data(x, np.clip(data, 0.1, None))
        data_peak = max(float(data.max()), 1.0)
        for curve, key in ((self._irf_vv_curve, "irf_vv"), (self._irf_vh_curve, "irf_vh")):
            irf = payload.get(key)
            if irf is not None and len(irf):
                irf = np.asarray(irf, dtype=float)
                # normalised IRF (unit area) → scale its peak to the data for overlay
                scale = data_peak / max(float(irf.max()), 1e-12)
                curve.set_data(np.arange(irf.size), np.clip(irf * scale, 0.1, None))
            else:
                curve.set_data([], [])
        start, stop = payload.get("conv", (0, data.size))
        self._region.set_bounds(float(start), float(stop))
        irf_start, irf_stop = payload.get("irf_range", (0, data.size))
        self._irf_region.set_bounds(float(irf_start), float(irf_stop))
        bg_start, bg_stop = payload.get("bg_range", (0, 0))
        self._bg_region.set_bounds(float(bg_start), float(bg_stop))

    def _on_region(self, start, stop) -> None:
        setter = getattr(self._model, "set_conv_range", None)
        if callable(setter):
            setter(start, stop)

    def _on_irf_region(self, start, stop) -> None:
        setter = getattr(self._model, "set_irf_range", None)
        if callable(setter):
            setter(start, stop)

    def _on_bg_region(self, start, stop) -> None:
        setter = getattr(self._model, "set_bg_range", None)
        if callable(setter):
            setter(start, stop)
