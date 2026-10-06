from __future__ import annotations

import re
import time

import numpy as np

import chisurf as cs
import chisurf.core.fitting
import chisurf.core.models
import chisurf.core.parameter
import chisurf.core.settings
import chisurf.core.support.decorators
from chisurf import typing
from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase
from chisurf.gui.widgets.fitting.fitting_client import get_fitting_client

plot_settings = cs.core.settings.gui["plot"]
colors = plot_settings["colors"]
color_scheme = cs.core.settings.colors
lw = plot_settings["line_width"]

OVERLAY_PEN = cp.to_pen((255, 128, 0), width=1.5, style="dash")
CROSSING_PEN = cp.to_pen((0, 180, 0), width=1.5, style="dash_dot")
P_VALUE_LEVELS = (0.68, 0.95, 0.99)


def parse_p_values(text: str) -> tuple[float, ...]:
    """The p-value levels in *text*: valid values in input order, no repeats.

    Parameters
    ----------
    text : str
        Comma/space/semicolon separated numbers, optionally bracketed.

    Returns
    -------
    tuple of float
        The values in (0, 1); :data:`P_VALUE_LEVELS` when there are none.
    """
    levels: list[float] = []
    for token in re.split(r"[\s,;]+", str(text).strip("[](){} ")):
        if not token:
            continue
        try:
            value = float(token)
        except ValueError:
            continue
        if 0.0 < value < 1.0 and value not in levels:
            levels.append(value)
    return tuple(levels) if levels else P_VALUE_LEVELS


class ParameterScanPlot(plotbase.Plot):
    """χ² against one parameter, re-fitting the others at each step.

    The settings (``parameter_scan.settings.view.json``) choose the parameter,
    the relative scan range and steps, the p-value levels, and start a scan or
    an adaptive (smart) scan. A scan run as a server job is polled from the
    frame, so the window stays responsive while it runs.
    """

    name = "Parameter scan"
    settings_view = "parameter_scan.settings.view.json"

    def __init__(self, fit: cs.core.fitting.fit.FitGroup, *args, **kwargs):
        super().__init__(fit)
        self.model = fit.model
        self.data_x, self.data_y = None, None

        # Settings.
        self._parameter_names: list[str] = []
        self._parameter_name = ""
        self.scan_lower = 0.1
        self.scan_upper = 0.1
        self.scan_steps = 50
        self.p_values = ", ".join(f"{v:g}" for v in P_VALUE_LEVELS)
        self.bound_range = False
        #: ``(job_id, parameter, deadline)`` of a server scan being polled.
        self._job = None
        self._next_poll = 0.0

        # One panel; its title is what the single-tab dock around it used to say.
        p2 = cp.Panel(title="Chi2-Surface")
        from chisurf.gui.plots.emtk_page import PanelItem

        self.panel_items = [PanelItem(p2, p2.control())]
        self.distribution_plot = p2
        self.distribution_curve = p2.line(
            [0.0],
            [0.0],
            pen=colors["data"],
            width=lw,
            name="Data",
        )

        self._overlay_items = []
        self.refresh_parameters()
        self._update_range()

    # -- page body ----------------------------------------------------------

    def emtk_draw(self, box) -> None:
        """The χ² surface; a running server scan is polled first."""
        from emtk import im

        self._poll_job()
        im.host_control("##chi2-surface", self.panel_items[0])

    # -- settings -----------------------------------------------------------

    def parameter_names(self) -> list[str]:
        """The parameters that can be scanned."""
        return list(self._parameter_names)

    @property
    def parameter_name(self) -> str:
        """The parameter scanned."""
        return self._parameter_name

    @parameter_name.setter
    def parameter_name(self, value: str) -> None:
        self._parameter_name = str(value)
        self._update_range()
        self.update()

    def refresh_parameters(self) -> None:
        """Re-read the model's parameter names, keeping the selection if it is still there."""
        self._parameter_names = [
            str(n) for n in list(getattr(self.model, "parameter_names", []) or [])
        ]
        if self._parameter_name not in self._parameter_names:
            self._parameter_name = self._parameter_names[0] if self._parameter_names else ""
        update_plots = getattr(self.model, "update_plots", None)
        if callable(update_plots):
            update_plots()

    def _p_value_levels(self) -> typing.Tuple[float, ...]:
        """The p-value levels typed in the settings (the defaults when none is valid)."""
        levels = parse_p_values(self.p_values)
        if levels == P_VALUE_LEVELS:
            # nothing valid typed: show the levels that are used
            self.p_values = ", ".join(f"{v:g}" for v in levels)
        return levels

    def _update_range(self) -> None:
        """Set the relative scan range from the selected parameter's error estimate."""
        p = self.parameter
        if p is None or p.value is None:
            return
        v = float(p.value)
        if abs(v) < 1e-15:
            v = 1.0
        err = p.error_estimate
        if isinstance(err, float) and not np.isnan(err) and err > 0:
            rel_range = min(max(3.0 * err / abs(v), 0.05), 2.0)
        else:
            rel_range = 0.1
        self.scan_lower = rel_range
        self.scan_upper = rel_range

    @property
    def parameter(self) -> cs.core.parameter.Parameter:
        """The selected parameter object, or ``None``."""
        name = self._parameter_name
        if not name:
            return None
        try:
            return self.model.parameters_all_dict[name]
        except (AttributeError, KeyError):
            parameter_dict = getattr(self.model, "parameter_dict", None) or {}
            return parameter_dict.get(name)

    def enabled(self, name: str) -> bool:
        """Whether a settings action is usable (none while a scan job runs)."""
        if name in ("scan_parameter", "smart_scan_parameter"):
            return self._job is None and self.parameter is not None
        return True

    def get_settings_state(self) -> dict:
        """The settings, for the project file."""
        return {
            "parameter": self._parameter_name,
            "scan_lower": float(self.scan_lower),
            "scan_upper": float(self.scan_upper),
            "scan_steps": int(self.scan_steps),
            "p_values": str(self.p_values),
            "bound_range": bool(self.bound_range),
        }

    def set_settings_state(self, state: dict) -> None:
        """Restore :meth:`get_settings_state`."""
        if not isinstance(state, dict):
            return
        if state.get("parameter") in self._parameter_names:
            self._parameter_name = state["parameter"]
        for key, kind in (("scan_lower", float), ("scan_upper", float), ("scan_steps", int),
                          ("p_values", str), ("bound_range", bool)):
            if key in state:
                setattr(self, key, kind(state[key]))
        self.update()

    # -- scans --------------------------------------------------------------

    def scan_parameter(self) -> None:
        """Scan the selected parameter over the scan range (a server job when one is available)."""
        p = self.parameter
        if p is None or p.value is None:
            return
        n_steps = int(self.scan_steps)
        value = float(p.value)
        scan_range = ((1.0 - float(self.scan_lower)) * value, (1.0 + float(self.scan_upper)) * value)

        fc = get_fitting_client()
        if fc is not None:
            try:
                fit_uid = str(getattr(self.fit, "unique_identifier", "") or "")
                result = fc.start_parameter_scan(
                    parameter_name=p.name,
                    n_steps=n_steps,
                    range_factor=2.0,
                    fit_uid=fit_uid,
                )
                job_id = result.get("job_id")
                if job_id:
                    self._job = (job_id, p, time.monotonic() + 300.0)
                    self.request_redraw()
                    return
            except Exception:
                pass
        try:
            self.fit.chi2_scan(parameter_name=p.name, scan_range=scan_range, n_steps=n_steps)
            p.scan_result = None
        except Exception as exc:
            cs.logging.warning(f"ParameterScanPlot: scan failed for '{p.name}': {exc}")
        self.update()

    def _poll_job(self) -> None:
        """Check a running server scan once (at most every 50 ms) and store its result."""
        if self._job is None:
            return
        now = time.monotonic()
        if now < self._next_poll:
            self.request_redraw()
            return
        self._next_poll = now + 0.05
        job_id, param, deadline = self._job
        fc = get_fitting_client()
        done = fc is None or now > deadline
        if not done:
            try:
                result = fc.parameter_scan_result(job_id)
                status = result.get("status", "")
                if status == "completed":
                    values = result.get("values", [])
                    chi2r = result.get("chi2r", result.get("chi2", []))
                    if values and chi2r:
                        param.parameter_scan = (values, chi2r)
                        param.scan_result = None
                    done = True
                elif status in ("failed", "cancelled"):
                    done = True
            except Exception:
                done = True
        if done:
            self._job = None
            self.update()
        self.request_redraw()

    def smart_scan_parameter(self) -> None:
        """Walk out from the optimum until each p-value threshold is crossed."""
        p = self.parameter
        if p is None or p.value is None:
            return
        if self.bound_range:
            value = float(p.value)
            scan_range = (
                (1.0 - float(self.scan_lower)) * value,
                (1.0 + float(self.scan_upper)) * value,
            )
        else:
            scan_range = (None, None)

        p_value_levels = self._p_value_levels()
        try:
            result = self.fit.adaptive_chi2_scan(
                parameter_name=p.name,
                scan_range=scan_range,
                p_value=max(p_value_levels),
                max_points_per_side=int(self.scan_steps),
            )
            result["confidence_intervals"] = (
                cs.core.fitting.support_plane.confidence_intervals_from_scan_result(
                    result,
                    p_values=p_value_levels,
                )
            )
            p.scan_result = result
        except Exception as exc:
            cs.logging.warning(f"ParameterScanPlot: smart scan failed for '{p.name}': {exc}")
        self.update()

    # -- drawing ------------------------------------------------------------

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
            p = self.parameter
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
