from __future__ import annotations

import re
import time

import numpy as np
from qtpy import QtCore, QtWidgets

import chisurf as cs
import chisurf.core.fitting
import chisurf.core.models
import chisurf.core.parameter
import chisurf.core.settings
import chisurf.core.support.decorators
import chisurf.gui.decorators
from chisurf import typing
from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase
from chisurf.gui.widgets.dock_area.dock_area import DockArea
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

plot_settings = cs.core.settings.gui["plot"]
colors = plot_settings["colors"]
color_scheme = cs.core.settings.colors
lw = plot_settings["line_width"]

OVERLAY_PEN = cp.to_pen((255, 128, 0), width=1.5, style="dash")
CROSSING_PEN = cp.to_pen((0, 180, 0), width=1.5, style="dash_dot")
P_VALUE_LEVELS = (0.68, 0.95, 0.99)


class ParameterScanWidget(QtWidgets.QWidget):
    @cs.gui.decorators.init_with_ui(ui_filename="parameter_scan.ui")
    def __init__(
        self, model: cs.core.models.Model = None, parent: QtWidgets.QWidget = None, *args, **kwargs
    ):

        self.model = model
        self.parent = parent

        self.actionScanParameter.triggered.connect(self.scan_parameter)
        self.actionSmartScanParameter.triggered.connect(self.smart_scan_parameter)
        self.actionParameterChanged.triggered.connect(self.onParameterChanged)
        self.actionUpdateParameterList.triggered.connect(self.update)

        self.update()
        self._update_range_spinboxes()

    def _p_value_levels(self) -> typing.Tuple[float, ...]:
        """Return p-value levels entered in the list input.

        Returns
        -------
        tuple of float
            Valid p-values in input order. Falls back to the default
            prepopulated levels when the input does not contain any valid
            values.
        """
        widget = getattr(self, "lineEditPValues", None)
        if widget is None:
            return P_VALUE_LEVELS
        text = str(widget.text())
        levels = []
        for token in re.split(r"[\s,;]+", text.strip("[](){} ")):
            if not token:
                continue
            try:
                value = float(token)
            except ValueError:
                continue
            if 0.0 < value < 1.0 and value not in levels:
                levels.append(value)
        if not levels:
            levels = list(P_VALUE_LEVELS)
            widget.setText(", ".join(f"{value:g}" for value in levels))
        return tuple(levels)

    def _update_range_spinboxes(self):
        """Set the relative range spinboxes based on the selected parameter."""
        p = self.parameter
        if p is None:
            return
        v = p.value
        if v is None:
            return
        v = float(v)
        if abs(v) < 1e-15:
            v = 1.0
        err = p.error_estimate
        if isinstance(err, float) and not np.isnan(err) and err > 0:
            rel_range = min(max(3.0 * err / abs(v), 0.05), 2.0)
        else:
            rel_range = 0.1
        self.doubleSpinBox.setValue(rel_range)
        self.doubleSpinBox_2.setValue(rel_range)

    def onParameterChanged(self):
        self._update_range_spinboxes()
        update_parent = getattr(self.parent, "update", None)
        if callable(update_parent):
            update_parent()

    def update(self) -> None:
        super().update()
        self.comboBox.blockSignals(True)

        pn = list(getattr(self.model, "parameter_names", []) or [])
        self.comboBox.clear()
        self.comboBox.addItems([str(name) for name in pn])

        self.comboBox.blockSignals(False)
        update_plots = getattr(self.model, "update_plots", None)
        if callable(update_plots):
            update_plots()

    def _poll_scan_result(self, job_id: str, param) -> None:
        """Poll server for scan results and store locally.

        Called in a loop from scan_parameter / smart_scan_parameter
        when using the RPC path.
        """
        fc = get_fitting_client()
        if fc is None:
            return
        deadline = time.monotonic() + 300.0  # 5 min timeout
        while time.monotonic() < deadline:
            try:
                result = fc.parameter_scan_result(job_id)
                status = result.get("status", "")
                if status == "completed":
                    values = result.get("values", [])
                    chi2r = result.get("chi2r", result.get("chi2", []))
                    if values and chi2r:
                        param.parameter_scan = (values, chi2r)
                        param.scan_result = None
                    break
                if status in ("failed", "cancelled"):
                    break
            except Exception:
                break
            # Process Qt events while polling so the UI stays responsive
            QtCore.QCoreApplication.processEvents()
            time.sleep(0.05)
        self.parent.update()

    def scan_parameter(self) -> None:
        p = self.parameter
        if p is None or p.value is None:
            return
        n_steps = int(self.spinBox.value())
        p_min = float(self.doubleSpinBox.value())
        p_max = float(self.doubleSpinBox_2.value())
        value = float(p.value)
        scan_range = ((1.0 - p_min) * value, (1.0 + p_max) * value)

        fc = get_fitting_client()
        if fc is not None:
            try:
                fit_uid = str(getattr(self.parent.fit, "unique_identifier", "") or "")
                result = fc.start_parameter_scan(
                    parameter_name=p.name,
                    n_steps=n_steps,
                    range_factor=2.0,
                    fit_uid=fit_uid,
                )
                job_id = result.get("job_id")
                if job_id:
                    self._poll_scan_result(job_id, p)
                    return
            except Exception:
                pass
        fit_obj = getattr(self.parent, "fit", None)
        if fit_obj is not None:
            try:
                fit_obj.chi2_scan(
                    parameter_name=p.name,
                    scan_range=scan_range,
                    n_steps=n_steps,
                )
                p.scan_result = None
            except Exception as exc:
                cs.logging.warning(f"ParameterScanWidget: scan failed for '{p.name}': {exc}")
        self.parent.update()

    def smart_scan_parameter(self) -> None:
        p = self.parameter
        if p is None or p.value is None:
            return
        max_points = int(self.spinBox.value())
        fit_obj = getattr(self.parent, "fit", None)
        if fit_obj is None:
            return

        if self.checkBox.isChecked():
            p_min = float(self.doubleSpinBox.value())
            p_max = float(self.doubleSpinBox_2.value())
            value = float(p.value)
            scan_range = ((1.0 - p_min) * value, (1.0 + p_max) * value)
        else:
            scan_range = (None, None)

        p_value_levels = self._p_value_levels()
        try:
            result = fit_obj.adaptive_chi2_scan(
                parameter_name=p.name,
                scan_range=scan_range,
                p_value=max(p_value_levels),
                max_points_per_side=max_points,
            )
            result["confidence_intervals"] = (
                cs.core.fitting.support_plane.confidence_intervals_from_scan_result(
                    result,
                    p_values=p_value_levels,
                )
            )
            p.scan_result = result
        except Exception as exc:
            cs.logging.warning(f"ParameterScanWidget: smart scan failed for '{p.name}': {exc}")
        self.parent.update()

    @property
    def selected_parameter(self) -> typing.Tuple[int, str]:
        idx = self.comboBox.currentIndex()
        name = self.comboBox.currentText()
        return idx, str(name)

    @property
    def parameter(self) -> cs.core.parameter.Parameter:
        _, name = self.selected_parameter
        if not name:
            return None
        try:
            return self.model.parameters_all_dict[name]
        except (AttributeError, KeyError):
            parameter_dict = getattr(self.model, "parameter_dict", None) or {}
            return parameter_dict.get(name)


class ParameterScanPlot(plotbase.Plot):
    name = "Parameter scan"

    def __init__(self, fit: cs.core.fitting.fit.FitGroup, *args, **kwargs):
        super().__init__(fit)

        self.data_x, self.data_y = None, None

        self.plot_controller = ParameterScanWidget(model=fit.model, parent=self)

        area = DockArea()
        self.layout.addWidget(area)

        self.p1 = QtWidgets.QPlainTextEdit()
        p2 = cp.Plot()

        area.addTab(p2, "Chi2-Surface")

        self.distribution_plot = p2
        self.distribution_curve = p2.line(
            [0.0],
            [0.0],
            pen=colors["data"],
            width=lw,
            name="Data",
        )

        self._overlay_items = []

    def _clear_overlays(self):
        for item in self._overlay_items:
            self.distribution_plot.remove(item)
        self._overlay_items = []

    def _add_overlay(self, handle):
        # The handle is already attached (created via hline/vline); just track it.
        self._overlay_items.append(handle)

    @staticmethod
    def _format_interval_label(interval) -> str:
        """Return a compact label for a p-value interval overlay.

        Parameters
        ----------
        interval : dict
            Interval data with ``p_value`` and ``crossings`` entries.

        Returns
        -------
        str
            Label for the horizontal threshold line.
        """
        p_value = float(interval.get("p_value", 0.0))
        lower, upper = interval.get("crossings", (None, None))
        if lower is None or upper is None:
            return f"p={p_value:.2f}"
        return f"p={p_value:.2f} [{lower:.4g}, {upper:.4g}]"

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        try:
            p = self.plot_controller.parameter
            if p is None:
                return

            x, y = p.parameter_scan
            if x is None or y is None:
                return

            x = np.asarray(x)
            y = np.asarray(y)
            if x.size == 0 or y.size == 0:
                return

            # Avoid feeding all-NaN arrays into pyqtgraph, which leads to
            # RuntimeWarnings about NaN slices.
            if not np.any(np.isfinite(x)) or not np.any(np.isfinite(y)):
                return

            self.distribution_curve.set_data(x, y)

            # Draw overlays from smart-scan result
            self._clear_overlays()
            result = getattr(p, "scan_result", None)
            if result is not None:
                intervals = result.get("confidence_intervals")
                if not intervals:
                    intervals = [
                        {
                            "p_value": result.get("p_value", 0.99),
                            "threshold": result.get("threshold"),
                            "crossings": result.get("crossings", (None, None)),
                        }
                    ]
                for interval in intervals:
                    threshold = interval.get("threshold")
                    if threshold is None:
                        continue
                    thr_line = self.distribution_plot.hline(
                        threshold,
                        pen=OVERLAY_PEN,
                        label=self._format_interval_label(interval),
                    )
                    self._add_overlay(thr_line)

                    crossings = interval.get("crossings", (None, None))
                    for cr in crossings:
                        if cr is not None:
                            vline = self.distribution_plot.vline(
                                cr,
                                pen=CROSSING_PEN,
                                label=f"{cr:.4g}",
                            )
                            self._add_overlay(vline)
        except Exception as e:
            cs.logging.warning(f"ParameterScanPlot: update failed: {e}")
