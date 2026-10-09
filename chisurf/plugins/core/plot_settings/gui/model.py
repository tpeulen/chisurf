"""Qt-free model of the plot settings: every control of the Qt tool as an attribute.

The Qt tool (:class:`~.tool.PlotSettingsWidget`) keeps its state in widgets; this
class keeps the same state in plain attributes so the emtk app, a spec and the
tests can read and write it. The field set, the ranges, the defaults a missing
settings key falls back to and the layout of the settings dictionary are the
Qt tool's (``_load_settings_into_controls`` and ``_collect_settings``); the
differences are listed in the evidence report of the port.

Editing does not touch the settings: edits are *pending* until :meth:`apply`
(which writes them into the live ``gui.plot`` settings and re-styles the open
node graphs), and :meth:`save` applies and persists to ``settings_chisurf.yaml``.
:meth:`reset` reloads every field from the live settings and drops pending edits.
:meth:`preview_series` is what the sample plot draws: three curves that preview
the styling, never analysis data.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np

#: The registered chiplot backends, sorted as chiplot's ``available_backends()`` returns
#: them (that function lives in the Qt-dependent GUI package, which a Qt-free app must not
#: import; a test keeps the two lists equal).
BACKENDS = ("emtk", "pyqtgraph")

#: Qt's pyqtgraph combos, in the Qt order.
PG_BACKGROUNDS = ("k", "w", "default")
PG_FOREGROUNDS = ("d", "w", "l", "k")

#: The six palette entries: (settings key, model attribute, label as in the Qt tool).
COLOR_KEYS = (
    ("data", "color_data", "Data curve"),
    ("model", "color_model", "Model curve"),
    ("irf", "color_irf", "Instrument response"),
    ("residuals", "color_residuals", "Residuals"),
    ("auto_corr", "color_auto_corr", "Autocorrelation"),
    ("region_selector", "color_region_selector", "Region selector"),
)

#: Inclusive ranges of the numeric controls (the Qt spin boxes and sliders).
RANGES: dict[str, tuple[float, float]] = {
    "region_alpha": (0, 255),
    "active_transparency": (0.0, 1.0),
    "inactive_transparency": (0.0, 1.0),
    "line_width": (0.5, 10.0),
    "font_size": (0, 24),
    "grid_alpha_pct": (0, 100),
    "ng_line_width": (0.0, 4.0),
    "ng_grid_opacity_pct": (0, 100),
    "ng_grid_spacing": (4, 96),
    "ng_node_size": (6.0, 30.0),
}

#: Attributes that hold whole numbers (everything else numeric is a float).
INT_FIELDS = frozenset(
    {"region_alpha", "font_size", "grid_alpha_pct", "ng_grid_opacity_pct", "ng_grid_spacing"}
)

BOOL_FIELDS = (
    "enable_grid",
    "show_data_grid",
    "show_residual_grid",
    "show_acorr_grid",
    "enable_region_selector",
    "show_legend",
    "hide_title",
    "label_axis",
    "ng_show_grid",
    "pg_antialias",
    "pg_left_button_pan",
)

#: Every editable attribute, in the order of the Qt tool's sections.
FIELDS = (
    ("backend",)
    + tuple(attr for _, attr, _ in COLOR_KEYS)
    + (
        "region_alpha",
        "active_transparency",
        "inactive_transparency",
        "line_width",
        "font_size",
        "enable_grid",
        "grid_alpha_pct",
        "show_data_grid",
        "show_residual_grid",
        "show_acorr_grid",
        "enable_region_selector",
        "show_legend",
        "hide_title",
        "label_axis",
        "ng_show_grid",
        "ng_line_width",
        "ng_grid_opacity_pct",
        "ng_grid_spacing",
        "ng_node_size",
        "pg_antialias",
        "pg_left_button_pan",
        "pg_background",
        "pg_foreground",
    )
)

#: Colour of the preview's lines when a stored colour is not a hex string.
_FALLBACK_COLOR = "#b4b4be"


def normalise_color(value: Any) -> str:
    """``"#abc"`` / ``"AABBCC"`` as ``"#aabbcc"``; anything else (a name) unchanged."""
    text = str(value or "").strip()
    raw = text.lstrip("#").lower()
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    if len(raw) in (6, 8) and all(c in "0123456789abcdef" for c in raw):
        return "#" + raw[:6]
    return text


def color_rgb(value: Any) -> tuple[int, int, int]:
    """The RGB triple of a hex colour (a non-hex stored colour reads as light grey)."""
    text = normalise_color(value)
    if len(text) != 7 or not text.startswith("#"):
        text = _FALLBACK_COLOR
    try:
        return tuple(int(text[i : i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    except ValueError:
        return (180, 180, 190)


def _settings():
    import chisurf.core.settings as css

    return css


class PlotSettingsModel:
    """Pending plot settings, with Apply / Save / Reset against the live settings."""

    def __init__(self, load: bool = True) -> None:
        self.backend = "emtk"
        for _, attr, _ in COLOR_KEYS:
            setattr(self, attr, "#ffffff")
        self.region_alpha = 100
        self.active_transparency = 1.0
        self.inactive_transparency = 0.2
        self.line_width = 2.0
        self.font_size = 0
        self.enable_grid = True
        self.grid_alpha_pct = 35
        self.show_data_grid = True
        self.show_residual_grid = True
        self.show_acorr_grid = True
        self.enable_region_selector = True
        self.show_legend = False
        self.hide_title = True
        self.label_axis = False
        self.ng_show_grid = True
        self.ng_line_width = 0.5
        self.ng_grid_opacity_pct = 6
        self.ng_grid_spacing = 24
        self.ng_node_size = 13.0
        self.pg_antialias = False
        self.pg_left_button_pan = True
        self.pg_background = "k"
        self.pg_foreground = "d"
        #: What the last action reported ("" until one ran).
        self.message = ""
        self._baseline: dict[str, Any] = {}
        if load:
            self.reset()
            self.message = ""
        else:
            self._baseline = self.values()

    # ── the Qt tool's defaults and ranges ─────────────────────────────────
    @staticmethod
    def clamp(attr: str, value: Any) -> Any:
        """Clamp *value* into the range of *attr* (Qt's ``setValue`` does the same)."""
        lo, hi = RANGES[attr]
        number = float(value)
        number = min(max(number, lo), hi)
        return int(round(number)) if attr in INT_FIELDS else number

    def set_value(self, attr: str, value: Any) -> None:
        """Set a field with the clamping and coercion its control would apply."""
        if attr in RANGES:
            value = self.clamp(attr, value)
        elif attr in BOOL_FIELDS:
            value = bool(value)
        elif attr.startswith("color_"):
            value = normalise_color(value)
        setattr(self, attr, value)

    # ── load / collect (the Qt tool's _load_settings_into_controls / _collect_settings) ──
    @staticmethod
    def live_plot_settings() -> dict:
        """The live ``gui.plot`` settings dictionary (the one the plots read)."""
        return _settings().cs_settings.get("gui", {}).get("plot", {})

    def load(self, ps: dict) -> None:
        """Fill every field from a ``gui.plot`` dictionary, with the Qt defaults for missing keys."""
        colors = ps.get("colors", {}) or {}
        self.backend = str(ps.get("backend", "emtk"))
        for key, attr, _ in COLOR_KEYS:
            self.set_value(attr, colors.get(key, "#ffffff"))
        self.set_value("region_alpha", int(colors.get("region_selector_alpha", 100)))
        self.set_value("active_transparency", float(colors.get("active_transparency", 1.0)))
        self.set_value("inactive_transparency", float(colors.get("inactive_transparency", 0.2)))
        self.set_value("line_width", float(ps.get("line_width", 2.0)))
        self.set_value("font_size", int(ps.get("font_size", 0) or 0))
        self.enable_grid = bool(ps.get("enable_grid", True))
        self.set_value("grid_alpha_pct", int(round(float(ps.get("grid_alpha", 0.35)) * 100)))
        self.show_data_grid = bool(ps.get("show_data_grid", True))
        self.show_residual_grid = bool(ps.get("show_residual_grid", True))
        self.show_acorr_grid = bool(ps.get("show_acorr_grid", True))
        self.enable_region_selector = bool(ps.get("enable_region_selector", True))
        self.show_legend = bool(ps.get("show_legend", False))
        self.hide_title = bool(ps.get("hideTitle", True))
        self.label_axis = bool(ps.get("label_axis", False))
        ng = ps.get("node_graph", {}) or {}
        self.ng_show_grid = bool(ng.get("show_grid", True))
        self.set_value("ng_line_width", float(ng.get("grid_line_width", 0.5)))
        self.set_value("ng_grid_opacity_pct", int(round(float(ng.get("grid_opacity", 0.06)) * 100)))
        self.set_value("ng_grid_spacing", int(float(ng.get("grid_spacing", 24.0))))
        self.set_value("ng_node_size", float(ng.get("node_size", 13.0)))
        pg = ps.get("pyqtgraph_config", {}) or {}
        self.pg_antialias = bool(pg.get("antialias", False))
        self.pg_left_button_pan = bool(pg.get("leftButtonPan", True))
        self.pg_background = str(pg.get("background", "k"))
        self.pg_foreground = str(pg.get("foreground", "d"))

    def collect(self) -> dict[str, Any]:
        """The fields as a ``gui.plot`` dictionary (the Qt tool's ``_collect_settings``)."""
        colors = {key: getattr(self, attr) for key, attr, _ in COLOR_KEYS}
        colors.update(
            {
                "region_selector_alpha": self.region_alpha,
                "active_transparency": self.active_transparency,
                "inactive_transparency": self.inactive_transparency,
            }
        )
        return {
            "backend": self.backend,
            "colors": colors,
            "line_width": self.line_width,
            "font_size": self.font_size,
            "enable_grid": self.enable_grid,
            "grid_alpha": self.grid_alpha_pct / 100.0,
            "show_data_grid": self.show_data_grid,
            "show_residual_grid": self.show_residual_grid,
            "show_acorr_grid": self.show_acorr_grid,
            "enable_region_selector": self.enable_region_selector,
            "show_legend": self.show_legend,
            "hideTitle": self.hide_title,
            "label_axis": self.label_axis,
            "node_graph": {
                "show_grid": self.ng_show_grid,
                "grid_line_width": self.ng_line_width,
                "grid_opacity": self.ng_grid_opacity_pct / 100.0,
                "grid_spacing": float(self.ng_grid_spacing),
                "node_size": self.ng_node_size,
            },
            "pyqtgraph_config": {
                "antialias": self.pg_antialias,
                "background": self.pg_background,
                "foreground": self.pg_foreground,
                "leftButtonPan": self.pg_left_button_pan,
            },
        }

    def values(self) -> dict[str, Any]:
        """Every editable attribute and its value (for dirty tracking and tests)."""
        return {attr: getattr(self, attr) for attr in FIELDS}

    # ── state the form reads ─────────────────────────────────────────────
    @property
    def dirty(self) -> bool:
        """Whether a field differs from what was last loaded or applied."""
        return self.values() != self._baseline

    @property
    def backends(self) -> tuple[str, ...]:
        """The choices of the backend combo."""
        return BACKENDS

    @property
    def status_text(self) -> str:
        """One line under the buttons: what the last action did, and whether edits are pending."""
        if self.dirty:
            return "Edits not applied yet: Apply uses them, Save also keeps them."
        return self.message or "Showing the active plot settings."

    # ── actions ──────────────────────────────────────────────────────────
    def reset(self) -> None:
        """Reload every field from the live settings and drop pending edits (Qt: Reset)."""
        self.load(copy.deepcopy(self.live_plot_settings()))
        self._baseline = self.values()
        self.message = "Reloaded from the active settings."

    def apply(self) -> None:
        """Write the fields into the live ``gui.plot`` settings (Qt: Apply)."""
        settings = self.collect()
        css = _settings()
        gui = css.cs_settings.setdefault("gui", {})
        existing = gui.get("plot", {})
        existing_colors = existing.get("colors", {})
        settings["colors"].update(
            {k: v for k, v in existing_colors.items() if k not in settings["colors"]}
        )
        existing.update(settings)
        gui["plot"] = existing
        # The node graphs read their style when they are built; an open one would
        # keep the old grid until reopened without this.
        try:
            from chisurf.emtk.node_editor.style_settings import refresh_open_graphs

            refresh_open_graphs()
        except Exception:  # noqa: BLE001 - nothing open to catch up
            pass
        self._baseline = self.values()
        self.message = "Applied to the active settings."

    def settings_file(self) -> Path:
        """``settings_chisurf.yaml`` of the settings folder."""
        from chisurf.core.settings.path_utils import get_path

        return get_path("settings") / "settings_chisurf.yaml"

    def save(self) -> None:
        """Apply, then persist ``gui.plot`` to ``settings_chisurf.yaml`` (Qt: Save)."""
        self.apply()
        import yaml

        css = _settings()
        path = self.settings_file()
        try:
            data: Any = {}
            if path.exists():
                with open(path, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                data = {}
            data.setdefault("gui", {})["plot"] = copy.deepcopy(
                css.cs_settings.get("gui", {}).get("plot", {})
            )
            with open(path, "w", encoding="utf-8") as fh:
                yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=False)
        except Exception as exc:  # noqa: BLE001 - reported on the status line, as Qt's dialog did
            self.message = f"Save failed: {exc}"
            return
        self.message = f"Applied and saved to {path}."

    # ── the preview ──────────────────────────────────────────────────────
    @property
    def preview_dark(self) -> bool:
        """Whether the preview has the dark background (the pyqtgraph background ``k``)."""
        return self.pg_background == "k"

    @property
    def preview_grid(self) -> bool:
        """Whether the preview draws a grid (Qt: ``enable_grid`` and ``show_data_grid``)."""
        return bool(self.enable_grid and self.show_data_grid)

    def preview_series(self) -> list[dict[str, Any]]:
        """The three sample curves of the Qt preview, with the pending colours and widths.

        These are **sample** curves that preview the styling (two decays and an
        instrument response on a constant background, so the log axis stays
        readable); they are not analysis data.
        """
        t = np.linspace(0.0, 10.0, 256)
        background = 2.0
        data = 1000 * np.exp(-t / 3.0) + 200 * np.exp(-t / 8.0) + background
        model = 980 * np.exp(-t / 2.9) + 210 * np.exp(-t / 7.8) + background
        irf = 500 * np.exp(-((t - 1.0) ** 2) / 0.05) + background
        return [
            {
                "label": "data",
                "x": t,
                "y": data,
                "color": self.color_data,
                "width": self.line_width,
                "dash": False,
            },
            {
                "label": "model",
                "x": t,
                "y": model,
                "color": self.color_model,
                "width": self.line_width,
                "dash": True,
            },
            {
                "label": "IRF",
                "x": t,
                "y": irf,
                "color": self.color_irf,
                "width": 1.5,
                "dash": False,
            },
        ]
