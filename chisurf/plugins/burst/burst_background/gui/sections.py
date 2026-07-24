"""Custom AutoForm sections for the Burst Background Estimation tool.

Registered under string keys referenced by ``background.view.json``: the detector
channel-definition page (``bg_channels``), the estimate action bar (``bg_run``)
and the per-detector background-rate bar chart (``bg_rate_plot``). The file list
(``path_list``), the inter-photon-time plot (``plot``) and the results table
(``table``) are built-in AutoForm sections. Mirrors ``burst_irf_bg/gui/sections``.
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from qtpy import QtWidgets

from chisurf.gui.autoform.sections.registry import register_section
from chisurf.gui.glyphs import Glyphs
from chisurf.gui.widgets.tool_buttons import styled_tool_button

logger = logging.getLogger(__name__)


# ── channel-definition page ───────────────────────────────────────────────────
def build_detector_page(model):
    """Create the detector page + wire the model's channels, or reuse the model's.

    The page is always created (so the shell can push channels via the model even
    when the channels dock is hidden); this returns the existing one when present.
    """
    page = getattr(model, "detector_wizard_page", None)
    if page is not None:
        return page
    from chisurf.gui.widgets.wizard.tttr_channeldefinition import DetectorWizardPage

    page = DetectorWizardPage(
        show_edit_json=False,
        show_save=False,
        show_setups_file=True,
        show_setup_selection=True,
        show_help=True,
        show_tttr_reading=True,
        show_tables=True,
        show_add_inputs=True,
    )

    def _detectors() -> dict:
        try:
            return page.get_settings().get("detectors", {})
        except Exception:
            logger.warning("background: reading detectors failed", exc_info=True)
            return {}

    model.channels_provider = _detectors
    model.detector_wizard_page = page
    return page


@register_section("bg_channels")
def bg_channels(model, target=None, **options):
    """Detector channel-definition page (drives the Qt-free model's channels)."""
    return build_detector_page(model)


# ── estimate action bar ───────────────────────────────────────────────────────
@register_section("bg_run")
def bg_run(model, target=None, **options):
    """Build the 'Estimate background' action + a status line."""
    return _RunSection(model)


class _RunSection(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        bar = QtWidgets.QHBoxLayout(self)
        bar.setContentsMargins(2, 2, 2, 2)
        btn = styled_tool_button(
            f"{Glyphs.RUN}  Estimate background",
            kind="run",
            tooltip="Estimate the per-detector background rate from every loaded file.",
        )
        btn.clicked.connect(self._estimate)
        bar.addWidget(btn)
        bar.addStretch(1)
        self._status = QtWidgets.QLabel(model.status)
        self._status.setWordWrap(True)
        bar.addWidget(self._status, 1)
        model.add_observer(self._on_event)

    def _estimate(self):
        try:
            self._model.estimate()
        except ValueError as exc:
            logging.getLogger(__name__).warning("%s", exc)
            self._status.setText(str(exc))
        except Exception as exc:  # noqa: BLE001
            QtWidgets.QMessageBox.critical(self, "Error", str(exc))

    def _on_event(self, _event):
        self._status.setText(self._model.status)


# ── inter-photon-time distribution (points + fitted tail) ─────────────────────
@register_section("bg_iht_plot")
def bg_iht_plot(model, target=None, **options):
    """Log-log inter-photon-time histogram (points) + fitted background tail."""
    return _IhtPlotSection(model)


class _IhtPlotSection(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plot = pg.PlotWidget()
        self.plot.setLogMode(x=True, y=True)
        self.plot.setLabel("bottom", "inter-photon time", units="ms")
        self.plot.setLabel("left", "counts")
        self.plot.setTitle("Inter-photon-time distribution + background tail fit")
        self.plot.addLegend(offset=(-10, 10))
        lay.addWidget(self.plot)
        model.add_observer(self._on_event)
        self._redraw()

    def _on_event(self, _event):
        self._redraw()

    def _redraw(self):
        self.plot.clear()
        legend = getattr(self.plot, "legend", None)
        if legend is not None:
            legend.clear()
        for s in self._model.iht_series():
            x = np.asarray(s["x"], dtype=float)
            y = np.asarray(s["y"], dtype=float)
            if s.get("symbol"):
                self.plot.plot(
                    x,
                    y,
                    pen=None,
                    symbol="o",
                    symbolSize=3,
                    symbolBrush=(*_rgb(s["color"]), 90),
                    symbolPen=None,
                    name=s.get("name"),
                )
            else:
                self.plot.plot(x, y, pen=pg.mkPen(s["color"], width=s.get("width", 2)))


def _rgb(color):
    c = str(color).lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


# ── per-detector rate bar chart ───────────────────────────────────────────────
@register_section("bg_rate_plot")
def bg_rate_plot(model, target=None, **options):
    """Bar chart of the mean background rate (kHz) per detector."""
    return _RatePlotSection(model)


class _RatePlotSection(QtWidgets.QWidget):
    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.plot = pg.PlotWidget()
        self.plot.setLabel("left", "background", units="kHz")
        self.plot.setTitle("Background rate per detector")
        lay.addWidget(self.plot)
        model.add_observer(self._on_event)
        self._redraw()

    def _on_event(self, _event):
        self._redraw()

    def _redraw(self):
        self.plot.clear()
        rows = self._model.rate_rows()
        if not rows:
            return
        x = np.arange(len(rows))
        self.plot.addItem(
            pg.BarGraphItem(
                x=x,
                height=[r["rate"] for r in rows],
                width=0.6,
                brushes=[r["color"] for r in rows],
            )
        )
        self.plot.getAxis("bottom").setTicks([list(zip(x.tolist(), [r["detector"] for r in rows]))])
