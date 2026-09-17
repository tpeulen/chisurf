"""Interactive IRF background-region selector (embedded in the wizard).

A chiplot plot of the raw and corrected VV/VH IRFs with a draggable region for
the background window, mirrored by two spin boxes. Dragging the region
recomputes the corrected IRFs through the model
(which calls the Qt-free :func:`...core.irf.correct_irfs`). Embedded via the
``embed`` section with ``pass_model=True``.
"""

from __future__ import annotations

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.gui import chiplot as cp
from chisurf.gui import dialogs
from chisurf.gui.glyphs import Glyphs


class IrfNormalizationWidget(QtWidgets.QWidget):
    """Plot + region selector bound to an :class:`AnisotropyViewModel`."""

    _autoform_expanding = True

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self._model = model
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        bar = QtWidgets.QHBoxLayout()
        load_btn = QtWidgets.QToolButton()
        load_btn.setText(f"{Glyphs.REFRESH} Load / reload data")
        load_btn.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        load_btn.setToolTip("Load the polarised IRF/data files selected on the previous step.")
        load_btn.clicked.connect(self._on_load)
        bar.addWidget(load_btn)
        bar.addStretch(1)
        bar.addWidget(QtWidgets.QLabel("BG from"))
        self._lb = QtWidgets.QSpinBox()
        self._lb.setMaximum(1_000_000)
        bar.addWidget(self._lb)
        bar.addWidget(QtWidgets.QLabel("to"))
        self._ub = QtWidgets.QSpinBox()
        self._ub.setMaximum(1_000_000)
        bar.addWidget(self._ub)
        layout.addLayout(bar)

        self._plot = cp.Plot()
        self._plot.set_log(y=True)
        self._plot.legend()
        layout.addWidget(self._plot, 1)

        self._region = self._plot.region((0.0, 1.0), movable=True)

        self._region.on_change(self._on_region, final=True)
        self._lb.editingFinished.connect(self._on_spin)
        self._ub.editingFinished.connect(self._on_spin)

        self._sync_region_from_model()
        self._refresh_plot()

    # ── actions ─────────────────────────────────────────────────────────
    def _on_load(self) -> None:
        try:
            ok = self._model.load_data()
        except Exception as exc:
            dialogs.warning(self, "Load failed", str(exc))
            return
        if not ok:
            dialogs.warning(
                self, "Load failed", "Could not load data — check the file paths and setup."
            )
            return
        self._sync_region_from_model()
        self._refresh_plot()

    def _on_region(self, lb, ub) -> None:
        self._lb.blockSignals(True)
        self._ub.blockSignals(True)
        self._lb.setValue(int(lb))
        self._ub.setValue(int(ub))
        self._lb.blockSignals(False)
        self._ub.blockSignals(False)
        self._model.apply_region(int(lb), int(ub))
        self._refresh_plot(keep_region=True)

    def _on_spin(self) -> None:
        lb, ub = self._lb.value(), self._ub.value()
        # ``set_bounds`` blocks signals, so this does not re-enter ``_on_region``.
        self._region.set_bounds(lb, ub)
        self._model.apply_region(lb, ub)
        self._refresh_plot(keep_region=True)

    # ── rendering ───────────────────────────────────────────────────────
    def _sync_region_from_model(self) -> None:
        lb, ub = int(self._model.region_lb), int(self._model.region_ub)
        for w, v in ((self._lb, lb), (self._ub, ub)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self._region.set_bounds(lb, ub)

    def _refresh_plot(self, keep_region: bool = False) -> None:
        # clear the data curves, then re-attach the region and legend
        self._plot.clear()
        self._plot.legend()
        self._plot.add(self._region)
        for s in self._model.plot_series():
            self._plot.line(
                np.asarray(s["x"]),
                np.asarray(s["y"]),
                pen=s.get("color", "w"),
                width=s.get("width", 1),
                name=s.get("name"),
            )


__all__ = ["IrfNormalizationWidget"]
