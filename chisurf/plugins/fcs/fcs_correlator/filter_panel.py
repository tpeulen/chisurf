"""Photon/Burst filter step: the Qt custom AutoForm sections over the Qt-free :mod:`.filter_model`."""

from __future__ import annotations

import numpy as np
from qtpy import QtWidgets

from chisurf.gui.autoform import register_section

from .filter_model import FilterSettingsModel

__all__ = ["FilterSettingsModel"]


# ---- Custom AutoForm sections ----------------------------------------------


class _FilterPlot(QtWidgets.QWidget):
    """Reusable plot that redraws a model source on refresh."""

    AUTOFORM_REFRESH = True

    def __init__(self, model, source, title, *, log_y=False, x_label="", y_label=""):
        super().__init__()
        from chisurf.gui import chiplot as cp

        self._model = model
        self._source = source
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plot = cp.Plot(title=title)
        if x_label:
            self.plot.set_labels(bottom=x_label)
        if y_label:
            self.plot.set_labels(left=y_label)
        if log_y:
            self.plot.set_log(y=True)
        self.plot.set_menu_enabled(False)
        layout.addWidget(self.plot)
        self.refresh()

    def refresh(self):
        src = getattr(self._model, self._source, None)
        if not callable(src):
            return
        try:
            series = src() or []
        except Exception:
            return
        self.plot.clear()
        scatter = self._source == "dt_scatter_series"
        for s in series:
            x = np.asarray(s.get("x", []))
            y = np.asarray(s.get("y", []))
            if scatter:
                self.plot.scatter(
                    x,
                    y,
                    size=2,
                    brush=s.get("color", "w"),
                    pen=None,
                    symbol="o",
                    name=s.get("name", ""),
                )
            else:
                self.plot.line(x, y, pen=s.get("color", "w"), width=1, name=s.get("name", ""))


@register_section("filter_dt_plot")
class _FilterDtPlot(_FilterPlot):
    """dT scatter with a draggable horizontal region bound to min/max dMT."""

    _region = None

    def __init__(self, model, target: str = "", **options):
        super().__init__(
            model,
            "dt_scatter_series",
            "Delta macro-time",
            log_y=True,
            x_label="Photon index",
            y_label="dT (ms)",
        )

    def refresh(self):
        super().refresh()

        if self._region is None:
            self._region = self.plot.region(
                (0.0, 1.0),
                orientation="horizontal",
                brush=(80, 180, 255, 40),
                movable=True,
            )
            self._region.on_change(self._on_region, final=True)
        else:
            # ``clear()`` in the base refresh detached the region; re-add it.
            self.plot.add(self._region)
        # Position it from the model (log-y axis => region values are log10).
        # ``set_bounds`` blocks signals, so this does not re-enter ``_on_region``.
        lo = max(float(self._model.min_dmt), 1e-12)
        hi = max(float(self._model.max_dmt), lo * (1.0 + 1e-6))
        self._region.set_bounds(np.log10(lo), np.log10(hi))

    def _on_region(self, lo, hi):
        a, b = 10.0**lo, 10.0**hi
        self._model.min_dmt = float(min(a, b))
        self._model.max_dmt = float(max(a, b))
        self._model.use_min = True
        self._model.use_max = True
        form = getattr(self._model, "_form", None)
        if form is not None:
            try:
                form.sync_fields()
            except Exception:
                pass
        self._model.on_param_changed()


@register_section("filter_cr_plot")
class _FilterCrPlot(_FilterPlot):
    def __init__(self, model, target: str = "", **options):
        super().__init__(
            model,
            "count_rate_series",
            "Count rate",
            x_label="Time (s)",
            y_label="Intensity (kHz)",
        )


@register_section("filter_info")
class _FilterInfo(QtWidgets.QWidget):
    AUTOFORM_REFRESH = True

    def __init__(self, model, target: str = "", **options):
        super().__init__()
        self._model = model
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QtWidgets.QLabel("No data loaded.")
        layout.addWidget(self.label)
        layout.addStretch(1)

    def refresh(self) -> None:
        self.label.setText(self._model.info_text())
