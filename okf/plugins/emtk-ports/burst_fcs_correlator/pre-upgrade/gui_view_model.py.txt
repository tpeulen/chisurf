"""Toolkit-free burst FCS settings and plot sources."""

from pathlib import Path
from typing import Any

from ..core.algorithms import BurstFcsSettings

_GUI_DIR = Path(__file__).parent


class _BurstFcsModel:
    """Settings model + plot data sources for the declarative editor."""

    def __init__(self) -> None:
        self.n_bins = 3
        self.n_casc = 20
        self.make_fine = False
        self.padding_ms = 100.0
        self.fit_mode = "simple"
        self.maxent_log10_reg = 0.0
        self.maxent_td_min = 0.0
        self.maxent_td_max = 0.0
        self.tmin_fit = 0.0
        self.tmax_fit = 0.0
        self._selected: dict[str, Any] | None = None

    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_GUI_DIR / "burst_fcs.view.json")

    # -- settings <-> core ---------------------------------------------
    def to_settings(self) -> BurstFcsSettings:
        def _opt(v):
            return float(v) if v and float(v) > 0.0 else None

        return BurstFcsSettings(
            n_bins=int(self.n_bins),
            n_casc=int(self.n_casc),
            make_fine=bool(self.make_fine),
            padding_ms=float(self.padding_ms),
            fit_mode=str(self.fit_mode),
            maxent_reg=float(10.0 ** float(self.maxent_log10_reg)),
            maxent_td_min=_opt(self.maxent_td_min),
            maxent_td_max=_opt(self.maxent_td_max),
            tmin_fit=_opt(self.tmin_fit),
            tmax_fit=_opt(self.tmax_fit),
        )

    # -- declarative plot sources --------------------------------------
    def corr_plot_series(self) -> list[dict[str, Any]]:
        c = self._selected
        if not c:
            return []
        series = [
            {
                "x": c.get("tau_raw", c.get("tau", [])),
                "y": c.get("g_raw", c.get("g", [])),
                "name": "data",
                "color": "w",
            }
        ]
        g_fit = c.get("g_fit") or []
        tau = c.get("tau") or []
        if len(g_fit) and len(tau) == len(g_fit):
            series.append({"x": tau, "y": g_fit, "name": "fit", "color": "r", "width": 2})
        return series

    def dist_plot_series(self) -> list[dict[str, Any]]:
        c = self._selected
        if not c:
            return []
        td = c.get("td_grid") or []
        p = c.get("p") or []
        if len(td) and len(td) == len(p):
            return [{"x": td, "y": p, "name": "P(τ_D)", "color": "y", "width": 2}]
        return []
