from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

import numpy as np
from emtk.colormaps import to_rgb

import chisurf as cs
import chisurf.core.data
import chisurf.core.experiments
import chisurf.core.fitting
import chisurf.core.math
import chisurf.core.math.statistics
import chisurf.core.plotting.transforms as plot_transforms
import chisurf.core.settings
import chisurf.core.support.decorators
from chisurf import typing
from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase

colors = cs.core.settings.gui["plot"]["colors"]

_BUILTIN_PRESETS_PATH = Path(__file__).parent / "reference_presets.json"


def _load_reference_presets() -> dict:
    """Load and merge built-in + user reference axis presets.

    Returns a dict keyed by reference-mode key, each value being a dict
    with optional keys ``y_range``, ``y_padding``, ``x_range``, ``x_padding``.
    User settings in ``~/.chisurf/reference_presets.json`` override the
    built-in defaults shipped with the package.
    """
    builtin: dict[str, dict] = {}
    try:
        with open(str(_BUILTIN_PRESETS_PATH)) as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                builtin = data
    except Exception:
        pass

    user: dict[str, dict] = {}
    try:
        user_path = cs.core.settings.get_path("settings") / "reference_presets.json"
        if user_path.exists():
            with open(str(user_path)) as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    user = data
    except Exception:
        pass

    # Merge: start with built-in, overlay user values per key
    merged: dict[str, dict] = {}
    all_keys = set(builtin) | set(user)
    for key in all_keys:
        entry: dict = {}
        entry.update(builtin.get(key, {}))
        entry.update(user.get(key, {}))
        # Convert JSON lists back to tuples for range fields
        for rkey in ("y_range", "x_range"):
            val = entry.get(rkey)
            if isinstance(val, list):
                entry[rkey] = tuple(val)
        merged[key] = entry
    return merged


def _fmt_metric(value, nd: int = 3) -> str:
    """A fit metric for the overlay: fixed-point when ordinary, scientific when not.

    An unfitted start can have a χ² of 1e180; printed fixed-point it is a line of
    digits that runs off the panel and hides the curves under it.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "?"
    if not np.isfinite(v):
        return str(v)
    if v == 0.0 or 1e-3 <= abs(v) < 1e5:
        return f"{v:.{int(nd)}f}"
    return f"{v:.{int(nd)}e}"


class LinePlotSettings:
    """The *Plot settings* of a :class:`LinePlot`: plain state, drawn by emtk.

    Drawn from ``lineplot_settings.view.json``; what the spec cannot say -- the
    parameters of the selected reference transform, which change with the mode
    -- is the ``reference_parameters`` custom section (:meth:`draw_reference_parameters`).
    The attribute names the drawing code reads (``data_logy``, ``xmin`` as
    ``None`` while unticked, ``getCheckState``) are kept.
    """

    director = {
        "data": {
            "lw": 1.0,
            "color": colors["data"],
            "target": "main_plot",
            "allow_reference_transform": True,
            "allow_shift": True,
            "allow_density": True,
            "plot_only_region": False,
            "auto_downsample": True,
        },
        "IRF": {
            "lw": 2.0,
            "color": colors["irf"],
            "target": "main_plot",
            "allow_reference_transform": False,
            "allow_shift": True,
            "allow_density": True,
            "plot_only_region": False,
        },
        "model": {
            "lw": 2.0,
            "target": "main_plot",
            "color": colors["model"],
            "allow_reference_transform": True,
            "allow_shift": True,
            "allow_density": True,
            "plot_only_region": True,
        },
        "weighted residuals": {
            "lw": 2.0,
            "target": "top_left_plot",
            "label": "w.res.",
            "color": colors["residuals"],
            "allow_reference_transform": False,
            "allow_shift": True,
            "allow_density": False,
            "plot_only_region": False,
            "auto_downsample": True,
        },
        "autocorrelation": {
            "lw": 2.0,
            "target": "top_right_plot",
            "color": colors["auto_corr"],
            "label": "a.cor.",
            "allow_reference_transform": False,
            "allow_shift": True,
            "allow_density": False,
            "plot_only_region": False,
            "auto_downsample": True,
        },
        "default": {
            "lw": 2.0,
            "color": colors["data"],
            "target": "main_plot",
            "allow_reference_transform": False,
            "allow_shift": True,
            "allow_density": False,
            "allow_clipping": False,
            "plot_only_region": False,
        },
    }

    def __init__(
        self,
        parent=None,
        scale_x: str = "lin",
        d_scaley: str = "log",
        r_scaley: str = "lin",
        xmin: float = 0.0,
        ymin: float = 1.0,
    ):
        self.parent = parent
        self.log_x = scale_x not in ("lin", "linear")
        self.log_y = d_scaley not in ("lin", "linear")
        self.res_logy = r_scaley
        self.is_density = False
        self.display_group = False
        self.plot_ftt = False
        self.xmin_enabled = self.xmax_enabled = False
        self.ymin_enabled = self.ymax_enabled = False
        self.xmin_value, self.xmax_value = float(xmin), 0.0
        self.ymin_value, self.ymax_value = float(ymin), 0.0
        self.x_shift = 0.0
        self.y_shift = 0.0
        #: Curve name -> drawn, in plot order.
        self.curve_visibility: typing.OrderedDict[str, bool] = OrderedDict()
        self._reference_modes: typing.OrderedDict[str, plot_transforms.PlotReferenceMode] = (
            OrderedDict()
        )
        self._reference_mode = "raw"
        #: Reference-parameter values by parameter key (all modes share keys by name).
        self._reference_values: typing.Dict[str, typing.Any] = {}

    # -- what the drawing code reads -------------------------------------------

    @property
    def data_logy(self) -> str:
        """``"log"`` while the data are plotted logarithmically, else ``"linear"``."""
        return "log" if self.log_y else "linear"

    @data_logy.setter
    def data_logy(self, v: str) -> None:
        self.log_y = v not in ("lin", "linear")

    @property
    def scale_x(self) -> str:
        """``"log"`` while x is plotted logarithmically, else ``"linear"``."""
        return "log" if self.log_x else "linear"

    @scale_x.setter
    def scale_x(self, v: str) -> None:
        self.log_x = v not in ("lin", "linear")

    @property
    def data_is_log_x(self) -> bool:
        """Whether x is logarithmic."""
        return bool(self.log_x)

    @property
    def data_is_log_y(self) -> bool:
        """Whether the data are logarithmic."""
        return bool(self.log_y)

    @property
    def xmin(self) -> float | None:
        """The fixed lower x limit, ``None`` while it follows the data."""
        return self.xmin_value if self.xmin_enabled else None

    @xmin.setter
    def xmin(self, v: float) -> None:
        self.xmin_value = float(v)

    @property
    def xmax(self) -> float | None:
        """The fixed upper x limit, ``None`` while it follows the data."""
        return self.xmax_value if self.xmax_enabled else None

    @xmax.setter
    def xmax(self, v: float) -> None:
        self.xmax_value = float(v)

    @property
    def ymin(self) -> float | None:
        """The fixed lower y limit, ``None`` while it follows the data."""
        return self.ymin_value if self.ymin_enabled else None

    @ymin.setter
    def ymin(self, v: float) -> None:
        self.ymin_value = float(v)

    @property
    def ymax(self) -> float | None:
        """The fixed upper y limit, ``None`` while it follows the data."""
        return self.ymax_value if self.ymax_enabled else None

    @ymax.setter
    def ymax(self, v: float) -> None:
        self.ymax_value = float(v)

    def getCheckState(self, name: str) -> bool:  # noqa: N802 - the drawing code's spelling
        """Whether the curve *name* is drawn."""
        return bool(self.curve_visibility.get(name, True))

    def fill_line_widget(self) -> None:
        """List the parent plot's curves, all drawn."""
        for key in getattr(self.parent, "lines", {}) or {}:
            self.curve_visibility.setdefault(key, True)

    # -- the form ------------------------------------------------------------

    def changed(self, *_args) -> None:
        """A setting changed: redraw the plot."""
        if self.parent is not None:
            self.parent.update()

    def curve_rows(self) -> list[dict]:
        """The curve table's rows."""
        return [
            {"index": index, "shown": bool(shown), "name": name}
            for index, (name, shown) in enumerate(self.curve_visibility.items())
        ]

    def curve_edited(self, record: dict, key: str, value) -> None:
        """A curve's E box was flipped."""
        if key == "shown":
            self.curve_visibility[str(record["name"])] = bool(value)
            self.changed()

    # -- reference transform -------------------------------------------------

    def reference_mode_options(self) -> list[tuple[str, str]]:
        """``(key, label)`` of every reference mode, ``Raw`` first."""
        return [("raw", "Raw")] + [(key, str(mode.label)) for key, mode in self._reference_modes.items()]

    @property
    def reference_mode(self) -> str:
        """The selected reference mode key (``"raw"``: none)."""
        return self._reference_mode if self._reference_mode in self._reference_modes else "raw"

    @reference_mode.setter
    def reference_mode(self, key: str) -> None:
        # Kept even while the mode is not offered yet: a project restores the
        # mode before the plot has asked the model which modes it has.
        self._reference_mode = str(key or "raw")

    def reference_changed(self, *_args) -> None:
        """The reference mode changed: redraw."""
        self.changed()

    def selected_reference_mode(self) -> plot_transforms.PlotReferenceMode | None:
        """The selected reference mode, ``None`` for raw plotting."""
        return self._reference_modes.get(self.reference_mode)

    def set_reference_modes(
        self, modes: typing.Iterable[plot_transforms.PlotReferenceMode]
    ) -> None:
        """Offer *modes* (the model's) in the reference selector."""
        self._reference_modes = OrderedDict(
            (str(mode.key), mode)
            for mode in modes or []
            if isinstance(mode, plot_transforms.PlotReferenceMode)
        )

    @property
    def reference_parameters(self) -> typing.Dict[str, typing.Any]:
        """The selected mode's parameter values, defaults where unset."""
        mode = self.selected_reference_mode()
        if mode is None:
            return {}
        return {spec.key: self._reference_values.get(spec.key, spec.default) for spec in mode.parameters}

    @reference_parameters.setter
    def reference_parameters(self, values: typing.Mapping[str, typing.Any]) -> None:
        if isinstance(values, dict):
            self._reference_values.update(values)

    def reset_reference_parameters(self, *_args) -> None:
        """Reset the selected mode's parameters to their defaults."""
        mode = self.selected_reference_mode()
        if mode is None:
            return
        for spec in mode.parameters:
            self._reference_values[spec.key] = spec.default
        self.changed()

    def draw_reference_parameters(self, section, model, state, width: float) -> None:
        """The ``reference_parameters`` custom section: one row per parameter."""
        from emtk import im

        mode = self.selected_reference_mode()
        if mode is None or not mode.parameters:
            return
        values = self.reference_parameters
        if not im.begin_grid("##reference-parameters", (0, 1)):
            return
        for row, spec in enumerate(mode.parameters):
            if row:
                im.next_row()
            im.text(str(spec.label))
            im.next_cell()
            kind = str(spec.kind).lower()
            value = values.get(spec.key, spec.default)
            label = f"##reference-{spec.key}"
            if kind == "bool":
                changed, value = im.checkbox(label, bool(value))
            elif kind == "int":
                step = int(spec.step if spec.step is not None else 1)
                changed, value = im.input_int(label, int(value), step)
            elif kind == "choice":
                keys = [c[0] if isinstance(c, (tuple, list)) and len(c) >= 2 else c for c in spec.choices]
                names = [str(c[1]) if isinstance(c, (tuple, list)) and len(c) >= 2 else str(c)
                         for c in spec.choices]
                current = next((i for i, k in enumerate(keys) if str(k) == str(value)), 0)
                changed, picked = im.combo(label, current, names)
                value = keys[picked] if keys else value
            else:
                step = float(spec.step if spec.step is not None else 0.1)
                changed, value = im.input_float(label, float(value), step, step * 10, "%.6g")
            if changed:
                if kind in ("int", "float") or kind not in ("bool", "choice"):
                    low, high = spec.minimum, spec.maximum
                    if low is not None:
                        value = max(value, type(value)(low))
                    if high is not None:
                        value = min(value, type(value)(high))
                self._reference_values[spec.key] = value
                self.changed()
        im.end_grid()

    def save_current_presets(self, *_args) -> None:
        """Save the current axis range as the user preset of the active reference mode."""
        mode = self.selected_reference_mode()
        if mode is None:
            return
        entry: dict = {}
        if self.ymin_enabled or self.ymax_enabled:
            entry["y_range"] = [
                self.ymin_value if self.ymin_enabled else 0.0,
                self.ymax_value if self.ymax_enabled else 1.0,
            ]
        if self.xmin_enabled or self.xmax_enabled:
            entry["x_range"] = [
                self.xmin_value if self.xmin_enabled else 0.0,
                self.xmax_value if self.xmax_enabled else 1.0,
            ]
        user_path = cs.core.settings.get_path("settings") / "reference_presets.json"
        presets: dict = {}
        try:
            if user_path.exists():
                raw = json.loads(user_path.read_text())
                if isinstance(raw, dict):
                    presets = raw
        except Exception:
            pass
        presets[str(mode.key)] = entry
        try:
            user_path.write_text(json.dumps(presets, indent=2))
        except Exception as exc:
            cs.logging.warning("Could not save reference presets: %s", exc)
            return
        type(self.parent)._invalidate_presets_cache()
        self.changed()

    # -- project state -------------------------------------------------------

    def get_state(self) -> dict:
        """The settings, for the project file (the old controller's keys)."""
        return {
            "data_logy": self.data_logy,
            "scale_x": self.scale_x,
            "res_logy": self.res_logy,
            "reference_mode": self.reference_mode,
            "reference_parameters": self.reference_parameters,
            "is_density": bool(self.is_density),
            "display_group": bool(self.display_group),
            "plot_ftt": bool(self.plot_ftt),
            "xmin_enabled": bool(self.xmin_enabled),
            "xmax_enabled": bool(self.xmax_enabled),
            "ymin_enabled": bool(self.ymin_enabled),
            "ymax_enabled": bool(self.ymax_enabled),
            "xmin": float(self.xmin_value),
            "xmax": float(self.xmax_value),
            "ymin": float(self.ymin_value),
            "ymax": float(self.ymax_value),
            "x_shift": float(self.x_shift),
            "y_shift": float(self.y_shift),
            "curve_visibility": {k: bool(v) for k, v in self.curve_visibility.items()},
        }

    def set_state(self, state: dict) -> None:
        """Restore :meth:`get_state` and redraw."""
        if not isinstance(state, dict):
            return
        if "data_logy" in state:
            self.data_logy = str(state["data_logy"])
        if "scale_x" in state:
            self.scale_x = str(state["scale_x"])
        if "res_logy" in state:
            self.res_logy = str(state["res_logy"])
        for key in ("xmin_enabled", "xmax_enabled", "ymin_enabled", "ymax_enabled",
                    "is_density", "display_group", "plot_ftt"):
            if key in state:
                setattr(self, key, bool(state[key]))
        for key, attr in (("xmin", "xmin_value"), ("xmax", "xmax_value"), ("ymin", "ymin_value"),
                          ("ymax", "ymax_value"), ("x_shift", "x_shift"), ("y_shift", "y_shift")):
            if key in state:
                try:
                    setattr(self, attr, float(state[key]))
                except (TypeError, ValueError):
                    pass
        if "reference_mode" in state:
            self.reference_mode = str(state["reference_mode"])
        if "reference_parameters" in state:
            self.reference_parameters = state.get("reference_parameters") or {}
        visibility = state.get("curve_visibility")
        if isinstance(visibility, dict):
            for key, shown in visibility.items():
                if key in self.curve_visibility:
                    self.curve_visibility[key] = bool(shown)
        self.changed()


class LinePlot(plotbase.Plot):
    name = "Fit"
    settings_view = "lineplot_settings.view.json"

    def get_bounds(
        self, fit: cs.core.fitting.fit.Fit, region_selector: cp.handles.Region
    ) -> typing.Tuple[int, int]:
        lb, ub = region_selector.bounds

        x_shift = self.settings.x_shift
        lb -= x_shift
        ub -= x_shift

        data_x = fit.data.x
        x_len = len(data_x) - 1

        if self.settings.data_is_log_x:
            lb, ub = 10.0**lb, 10.0**ub

        lb_i: int = np.searchsorted(data_x, lb, side="right")
        ub_i: int = np.searchsorted(data_x, ub, side="left")

        return np.clip(lb_i - 1, 0, x_len), np.clip(ub_i, 0, x_len)

    def __init__(
        self,
        fit: cs.core.fitting.fit.FitGroup,
        scale_x: str = "lin",
        d_scaley: str = "lin",
        r_scaley: str = "lin",
        x_label: str = "x",
        y_label: str = "y",
        curve_styles: typing.Dict | None = None,
        **kwargs,
    ):
        # Internal state of region selector
        self.lb_i: int = 0
        self.ub_i: int = 0

        self.curve_styles = curve_styles or {}
        self._base_y_label = y_label

        kwargs["fit"] = fit
        super().__init__(**kwargs)
        #: The *Plot settings*: plain state the settings dock draws (emtk).
        self.settings = LinePlotSettings(
            parent=self, scale_x=scale_x, d_scaley=d_scaley, r_scaley=r_scaley
        )
        #: ``(lb_i, ub_i)`` after the fit range was dragged on the plot.
        self.regionChanged = plotbase.Hook()

        # If the plot is associated with a FitGroup containing multiple local fits,
        # default to displaying the full group. Do this once and avoid overriding
        # user intent later.
        self._auto_display_group_applied = False
        try:
            self._auto_enable_display_group_if_grouped()
        except Exception:
            pass
        # chiplot panels, stacked a.corr. residuals / residuals / data with a
        # shared x-axis. The fit window draws its pages on one emtk surface, so
        # the stack is an emtk PaneStack of the panels' canvases (emtk_body):
        # weighted, so data : (a.corr + w.res) stays the golden ratio through
        # every resize until the user drags a bar, and collapsible, so a strip
        # can be folded away and dragged back.
        p1 = cp.Panel()
        p2 = cp.Panel()
        p3 = cp.Panel()
        p1.link_x(p3)
        p2.link_x(p3)

        plots = {"top_left_plot": p1, "top_right_plot": p2, "main_plot": p3}
        plots["top_left_plot"].set_axis_visible(bottom=False)
        plots["top_right_plot"].set_axis_visible(bottom=False)
        # Panels, not widgets: the fit window's surface draws their canvases.
        self._panels = (p2, p1, p3)  # A.corr. residuals, residuals, data
        self.plot_stack = None

        # Labels - draggable text box for the fit-quality metrics overlay: light
        # text on a dark translucent box with a quiet border, pinned to the top
        # of the data panel, clear of the axis.
        self.text = plots["main_plot"].text(
            "",
            (100, 6),
            color="#e6e8ee",
            border=(110, 116, 128, 200),
            fill=(18, 20, 26, 200),
            anchor=(0, 0),
            draggable=True,
            anchored=True,
        )

        # Fitting-region selector
        if cs.core.settings.gui["plot"]["enable_region_selector"]:
            ca = list(to_rgb(colors["region_selector"]))
            co = [ca[0] * 255, ca[1] * 255, ca[2] * 255, colors["region_selector_alpha"]]
            region = plots["main_plot"].region((0.0, 1.0), brush=co)
            self.region = region

            def onRegionUpdate(*_):
                # Get the currently selected fit for region update
                if hasattr(fit, "selected_fit"):
                    current_fit = fit.selected_fit
                else:
                    current_fit = fit

                self.lb_i, self.ub_i = self.get_bounds(current_fit, region)
                lb, ub = current_fit.data.x[self.lb_i], current_fit.data.x[self.ub_i]
                x_shift = self.settings.x_shift
                lb += x_shift
                ub += x_shift
                if self.settings.data_is_log_x:
                    lb = np.log10(lb)
                    ub = np.log10(ub)
                self.region.set_bounds(lb, ub)
                cs.core.actions.dispatch(
                    name="fit.range.set",
                    payload={
                        "xmin": int(self.lb_i),
                        "xmax": int(self.ub_i),
                        "fit_index": getattr(self.fit, "fit_idx", 0),
                    },
                )
                try:
                    self.regionChanged.emit(self.lb_i, self.ub_i)
                except Exception:
                    pass
                self.update(only_fit_range=True)

            region.on_change(onRegionUpdate, final=True)

        # Grid
        if cs.core.settings.gui["plot"]["enable_grid"]:
            grid_alpha = float(cs.core.settings.gui["plot"].get("grid_alpha", 0.35))
            if cs.core.settings.gui["plot"]["show_data_grid"]:
                plots["main_plot"].grid(x=True, y=True, alpha=grid_alpha)
            # ``alpha`` is the grid's opacity, not an on/off flag — these two
            # panels asked for 1.0 and drew solid foreground-coloured stripes
            # across a strip only eighty pixels tall, burying the residuals.
            # It went unnoticed while the foreground was black on black, and
            # there was no way to turn it down: the value is a setting now.
            if cs.core.settings.gui["plot"]["show_residual_grid"]:
                plots["top_left_plot"].grid(x=True, y=True, alpha=grid_alpha)
            if cs.core.settings.gui["plot"]["show_acorr_grid"]:
                plots["top_right_plot"].grid(x=True, y=True, alpha=grid_alpha)
        # Same story as "Label axes" below: a settings checkbox that no plot
        # read, so a legend could be asked for and never appear — and one that
        # never appears is one that cannot be dragged either. The curves are
        # already named, which is all a legend needs.
        if cs.core.settings.gui["plot"].get("show_legend", False):
            # Top-right: the fit-quality box holds the top-left.
            plots["main_plot"].legend(offset=(-10, 10))

        # "Label axes" was a settings checkbox nothing read, so turning it off
        # did nothing at all. Honour it: axis names cost horizontal space that
        # a narrow docked panel may prefer to give the data.
        if cs.core.settings.gui["plot"].get("label_axis", True):
            plots["top_left_plot"].set_labels(left="w.res.")
            plots["top_right_plot"].set_labels(left="a.corr.")
            plots["main_plot"].set_labels(left=y_label, bottom=x_label)

        lines = OrderedDict()
        curves = self.fit.get_curves()
        curves_keys = list(curves.keys())[::-1]
        for i, curve_key in enumerate(curves_keys):
            lines[curve_key] = self.add_plot(
                curves=curves, curve_key=curve_key, plot_dict=plots, index=i
            )
        self.lines = lines
        self.plots = plots
        self.settings.fill_line_widget()

    def settings_model(self):
        """The settings spec edits :attr:`settings`."""
        return self.settings

    def register_settings_sections(self, form) -> None:
        """The reference transform's parameters are drawn by the settings object."""
        form.custom["reference_parameters"] = self.settings.draw_reference_parameters

    def get_settings_state(self) -> dict:
        """The settings, for the project file."""
        return self.settings.get_state()

    def set_settings_state(self, state: dict) -> None:
        """Restore :meth:`get_settings_state`."""
        self.settings.set_state(state)

    #: The data panel's share of the stack. The residual strips split the rest,
    #: so data : (a.corr + w.res) is the golden ratio.
    GOLDEN_DATA_FRACTION = 0.6180339887498949

    def golden_weights(self) -> tuple[float, float, float]:
        """The panels' shares: data takes the golden fraction, the strips halve the rest."""
        strip = (1.0 - self.GOLDEN_DATA_FRACTION) / 2.0
        return (strip, strip, self.GOLDEN_DATA_FRACTION)

    def emtk_body(self):
        """The panel stack as one emtk control (built once, then kept)."""
        if self.plot_stack is None:
            from emtk.flags import Axis
            from emtk.widgets.pane_stack import PaneStack

            from chisurf.gui.plots.emtk_page import PanelItem

            self.panel_items = [PanelItem(panel, panel.control()) for panel in self._panels]
            self.plot_stack = PaneStack(
                self.panel_items, self.golden_weights(), axis=Axis.Y, collapsible=True
            )
        return self.plot_stack

    def get_state(self) -> dict:
        """The panel split and any zoomed view, once the user chose them (project persistence).

        ``views`` holds one ``{"x": [lo, hi] | None, "y": ...}`` per panel, in
        :attr:`_panels` order; ``None`` is an axis still following its data, so a
        restored plot zooms exactly where the user had zoomed and autoscales
        everywhere else.
        """
        state: dict = {}
        stack = self.plot_stack
        if stack is not None and stack.user_sized:
            state["split"] = [round(float(w), 6) for w in stack.weights]
        views = []
        for panel in self._panels:
            try:
                auto_x, auto_y = panel.is_auto_range()
                (x0, x1), (y0, y1) = panel.get_range()
            except Exception:
                views.append({"x": None, "y": None})
                continue
            views.append(
                {
                    "x": None if auto_x else [float(x0), float(x1)],
                    "y": None if auto_y else [float(y0), float(y1)],
                }
            )
        if any(view["x"] is not None or view["y"] is not None for view in views):
            state["views"] = views
        return state

    def set_state(self, state: dict) -> None:
        """Restore a split and zoomed views saved by :meth:`get_state`."""
        if not isinstance(state, dict):
            return
        split = state.get("split")
        if isinstance(split, (list, tuple)) and len(split) == len(self._panels):
            stack = self.emtk_body()
            stack.set_weights([float(w) for w in split])
            stack.user_sized = True
        views = state.get("views")
        if isinstance(views, (list, tuple)) and len(views) == len(self._panels):
            for panel, view in zip(self._panels, views):
                if not isinstance(view, dict):
                    continue
                x, y = view.get("x"), view.get("y")
                if x is not None or y is not None:
                    panel.set_range(
                        x=tuple(float(v) for v in x) if x is not None else None,
                        y=tuple(float(v) for v in y) if y is not None else None,
                        padding=0.0,
                    )

    def _auto_enable_display_group_if_grouped(self) -> None:
        """Enable "display group" by default for multi-fit FitGroups.

        This keeps the plot readable for grouped fits (e.g. VV/VH, grouped FCS)
        without forcing the user to manually toggle the checkbox each time.
        """
        if bool(getattr(self, "_auto_display_group_applied", False)):
            return
        grouped_fits = getattr(self.fit, "grouped_fits", None)
        if not isinstance(grouped_fits, (list, tuple)):
            return
        if len(grouped_fits) <= 1:
            return
        self.settings.display_group = True
        self._auto_display_group_applied = True

    @staticmethod
    def _make_line(target_plot, pen_color, lw, name, auto_downsample, clip_to_view):
        """Draw an empty chiplot curve with optional render-perf hints.

        The line/scatter data is filled in later by :meth:`update`. Auto-
        downsampling and clip-to-view are pyqtgraph render optimisations with no
        renderer-neutral chiplot verb, so they are set on the backend item via
        the documented ``.native`` escape hatch.

        Parameters
        ----------
        target_plot : cp.Plot
            Panel to draw on.
        pen_color : str
            Line color (hex, possibly with a leading ``#RRGGBBAA`` alpha).
        lw : float
            Line width.
        name : str
            Legend label.
        auto_downsample, clip_to_view : bool
            pyqtgraph render-perf hints.

        Returns
        -------
        cp.handles.Curve
        """
        line = target_plot.line([0.0], [0.0], pen=pen_color, width=lw, name=name)
        if auto_downsample or clip_to_view:
            line.set_downsampling(auto=auto_downsample)
            line.set_clip_to_view(clip_to_view)
        return line

    def add_plot(self, curves: typing.Dict, curve_key: str, plot_dict: typing.Dict, index: int = 1):
        color_idx = index % len(cs.core.settings.colors)
        pen_color = cs.core.settings.colors[color_idx]["hex"]
        lw = cs.core.settings.gui["plot"]["line_width"]

        director = self.settings.director

        if curve_key in director.keys():
            for ik in director.keys():
                # if the curve name matches the template
                if ik in curve_key:
                    curve_options = director[ik]
                    target_plot = plot_dict[curve_options.get("target", "main_plot")]
                    lw = curve_options.get("lw", lw)
                    pen_color = curve_options.get("color", pen_color)
                    label = curve_options.get("label", curve_key)
                    auto_downsample = curve_options.get("auto_downsample", False)
                    clip_to_view = curve_options.get("clip_to_view", auto_downsample)
                    if curve_key != ik:
                        # make the line half as wide, and transparent (30%)
                        lw *= 0.5
                        pen_color = "#4D" + pen_color.split("#")[1]
                    line = self._make_line(
                        target_plot,
                        pen_color,
                        lw,
                        label,
                        auto_downsample,
                        clip_to_view,
                    )
                    self._apply_curve_style(curve_key, line)
                    return line
        else:
            curve = curves[curve_key]
            if isinstance(curve, cs.core.data.DataCurve):
                curve_options = director["default"]
                target_plot = plot_dict[curve_options.get("target", "main_plot")]
                auto_downsample = curve_options.get("auto_downsample", False)
                clip_to_view = curve_options.get("clip_to_view", auto_downsample)
                line = self._make_line(
                    target_plot,
                    pen_color,
                    lw,
                    curve_key,
                    auto_downsample,
                    clip_to_view,
                )
                self._apply_curve_style(curve_key, line)
                return line

        return None

    def _get_curve_style(self, curve_key: str) -> typing.Optional[typing.Dict]:
        styles = getattr(self, "curve_styles", None)
        if not styles:
            return None
        if curve_key in styles:
            return styles[curve_key]
        if "_" in curve_key:
            base = curve_key.split("_", 1)[0]
            if base in styles:
                return styles[base]
        return None

    def _apply_curve_style(self, curve_key: str, line: cp.handles.Curve) -> None:
        style = self._get_curve_style(curve_key)
        if not style:
            return
        try:
            if "pen" in style:
                line.set_pen(style.get("pen"))
        except Exception:
            pass
        try:
            symbol = style.get("symbol")
            if symbol is not None:
                line.set_symbol(symbol)
        except Exception:
            pass
        try:
            size = style.get("symbol_size")
            if size is not None:
                line.set_symbol_size(size)
        except Exception:
            pass
        try:
            brush = style.get("symbol_brush")
            if brush is not None:
                line.set_symbol_brush(brush)
        except Exception:
            pass
        try:
            if style.get("no_line"):
                line.set_pen(None)
        except Exception:
            pass

    _MERGED_PRESETS: typing.ClassVar[dict | None] = None

    def _reference_modes_for_model(self, model) -> typing.List[plot_transforms.PlotReferenceMode]:
        """Return model-provided plot reference modes, merged with JSON presets.

        Parameters
        ----------
        model : object
            Model object to query.

        Returns
        -------
        list
            Valid reference modes with axis presets applied.
        """
        getter = getattr(model, "get_plot_reference_modes", None)
        if not callable(getter):
            return []
        try:
            modes = getter()
        except Exception as exc:
            cs.logging.warning("Could not query plot reference modes: %s", exc)
            return []
        modes = [
            mode for mode in modes or [] if isinstance(mode, plot_transforms.PlotReferenceMode)
        ]
        # Merge JSON presets into each mode
        presets = self._get_merged_presets()
        return [self._apply_presets_to_mode(mode, presets.get(str(mode.key), {})) for mode in modes]

    @classmethod
    def _get_merged_presets(cls) -> dict:
        """Return cached merged presets (built-in + user)."""
        if cls._MERGED_PRESETS is None:
            cls._MERGED_PRESETS = _load_reference_presets()
        return cls._MERGED_PRESETS

    @classmethod
    def _apply_presets_to_mode(
        cls, mode: plot_transforms.PlotReferenceMode, preset: dict
    ) -> plot_transforms.PlotReferenceMode:
        """Apply JSON preset fields onto a PlotReferenceMode, skipping None."""
        kwargs: dict = {}
        for field_name in ("y_range", "y_padding", "x_range", "x_padding"):
            val = preset.get(field_name)
            if val is not None:
                kwargs[field_name] = val
        if not kwargs:
            return mode
        from dataclasses import replace

        return replace(mode, **kwargs)

    @classmethod
    def _invalidate_presets_cache(cls) -> None:
        """Clear cached presets so they are reloaded on next access."""
        cls._MERGED_PRESETS = None

    def _update_reference_modes(self, current_fit) -> None:
        """Refresh the reference-mode selector for the active model.

        Parameters
        ----------
        current_fit : cs.core.fitting.fit.Fit
            Fit whose model controls the available modes.
        """
        model = getattr(current_fit, "model", None)
        modes = self._reference_modes_for_model(model)
        self.settings.set_reference_modes(modes)

    def _metrics_text_alive(self) -> bool:
        """Return True when the overlay text handle can still be drawn to.

        This used to reach through ``.native`` for pyqtgraph's ``textItem`` and
        ask sip whether it had been deleted, which answers "dead" on any other
        renderer — so the fit-quality overlay was created and then never
        written on the native backend. ``Handle.is_alive`` is the chiplot query
        that both backends answer.
        """
        text_handle = getattr(self, "text", None)
        if text_handle is None:
            return False
        try:
            return bool(text_handle.is_alive())
        except Exception:
            # A handle predating the query, or one whose backend cannot say.
            return True

    def _build_metrics_overlay_text(self, current_fit) -> str:
        """Build a plain-text variant of the metrics overlay.

        Using plain text avoids Qt rich-text parsing paths that have shown
        instability in some Windows save/switch workflows.
        """
        grouped_fits = getattr(self.fit, "grouped_fits", None)
        show_group = (
            bool(self.settings.display_group)
            and isinstance(grouped_fits, (list, tuple))
            and len(grouped_fits) > 1
        )
        current_idx = getattr(self.fit, "selected_fit_index", None)
        if not isinstance(current_idx, int):
            try:
                current_idx = grouped_fits.index(current_fit) if show_group else 0
            except Exception:
                current_idx = 0

        header = f"range {int(getattr(current_fit, 'xmin', 0))}\u2013{int(getattr(current_fit, 'xmax', 0))}"
        if show_group:
            # One self-describing line per dataset. A tab-separated table
            # needed its columns to line up, and in a proportional font they
            # did not: the values ran into each other ("505.57590.0173").
            lines = [header]
            for idx, f in enumerate(grouped_fits):
                marker = "\u25b8" if idx == current_idx else "  "
                chi2r = _fmt_metric(getattr(f, "chi2r", None))
                dw = _fmt_metric(getattr(f, "durbin_watson", None))
                lines.append(f"{marker} {idx + 1}  \u03c7\u00b2\u1d63 {chi2r}   DW {dw}")
            return "\n".join(lines)

        return "\n".join(
            [
                header,
                f"\u03c7\u00b2\u1d63 {_fmt_metric(getattr(current_fit, 'chi2r', None))}"
                f"   DW {_fmt_metric(getattr(current_fit, 'durbin_watson', None))}",
            ]
        )

    @staticmethod
    def _axis_range(min_value, max_value, values, log_mode: bool = False):
        """Return a finite axis range in data units, or ``None`` if invalid."""
        if min_value is None and max_value is None:
            return None

        try:
            values = np.asarray(values)
            if values.size == 0:
                return None
            a_min = values[0] if min_value is None else min_value
            a_max = values[-1] if max_value is None else max_value
            a_min = float(a_min)
            a_max = float(a_max)
        except (TypeError, ValueError, IndexError):
            return None

        if not np.isfinite(a_min) or not np.isfinite(a_max):
            return None
        # Data units on a log axis too (chiplot's set_range contract); a log
        # axis only refuses what it cannot show. Taking log10 here as well made
        # the backend take it a second time.
        if log_mode and (a_min <= 0.0 or a_max <= 0.0):
            return None
        if a_min > a_max:
            return None
        return [a_min, a_max]

    def update(self, only_fit_range: bool = False, *args, **kwargs) -> None:
        """Redraw the curves from the current fit."""
        super().update(*args, **kwargs)

        # Auto-enable group display once for multi-fit groups (do not override
        # user toggles after initial application).
        try:
            self._auto_enable_display_group_if_grouped()
        except Exception:
            pass

        fit = self.fit
        data_log_y = self.settings.data_is_log_y
        data_log_x = self.settings.data_is_log_x
        director = self.settings.director

        curves = fit.get_curves()
        data = curves["data"]

        y_shift = self.settings.y_shift
        x_shift = self.settings.x_shift

        # update region selector (set_limits/set_bounds each block the region's
        # signals internally, so no manual blockSignals dance is needed)

        # Get the currently selected fit for region selector bounds
        if hasattr(self.fit, "selected_fit"):
            current_fit = self.fit.selected_fit
            current_data = current_fit.data
        else:
            current_fit = self.fit
            current_data = data

        self._reference_y_label_override = None
        self._update_reference_modes(current_fit)

        x_last = max(0, len(current_data.x) - 1)
        xmin_i = int(np.clip(getattr(current_fit, "xmin", 0), 0, x_last))
        xmax_i = int(np.clip(getattr(current_fit, "xmax", x_last), 0, x_last))
        lb_min, ub_max = current_data.x[0], current_data.x[-1]
        lb, ub = current_data.x[xmin_i], current_data.x[xmax_i]

        lb_min += x_shift
        ub_max += x_shift
        lb += x_shift
        ub += x_shift

        if data_log_x:
            lb_min = np.log10(lb_min)
            ub_max = np.log10(ub_max)
            lb = np.log10(lb)
            ub = np.log10(ub)

        self.region.set_limits(lb_min, ub_max)
        self.region.set_bounds(lb, ub)

        # Handle group display mode
        if self.settings.display_group and hasattr(self.fit, "grouped_fits"):
            # Display all fits in the group
            self._plot_group_curves(fit, data_log_x, data_log_y, director, x_shift, y_shift)
        elif hasattr(self.fit, "grouped_fits"):
            # FitGroup but display group disabled: only show active fit
            self._plot_active_fit_only(fit, data_log_x, data_log_y, director, x_shift, y_shift)
        else:
            # Normal single fit display
            self._plot_single_fit_curves(
                fit, curves, data_log_x, data_log_y, director, x_shift, y_shift
            )

        # Set log-scales
        self.plots["main_plot"].set_log(x=data_log_x, y=data_log_y)
        self.plots["top_left_plot"].set_log(x=data_log_x)
        self.plots["top_right_plot"].set_log(x=data_log_x)
        self.plots["main_plot"].set_labels(
            left=self._reference_y_label_override or self._base_y_label
        )

        # Set manual scale
        xRange = self._axis_range(
            self.settings.xmin,
            self.settings.xmax,
            data.x,
            data_log_x,
        )
        yRange = self._axis_range(
            self.settings.ymin,
            self.settings.ymax,
            data.y,
            data_log_y,
        )
        # Apply reference-mode axis presets if user hasn't manually overridden
        try:
            model = getattr(current_fit, "model", None)
            ref_mode = self._selected_reference_mode_for_model(model)
            if ref_mode is not None:
                # Y-axis preset
                if (
                    ref_mode.y_range is not None
                    and not self.settings.ymin_enabled
                    and not self.settings.ymax_enabled
                ):
                    y_lo, y_hi = ref_mode.y_range
                    span = y_hi - y_lo
                    pad = ref_mode.y_padding or 0.0
                    if span > 0:
                        yRange = [y_lo - span * pad, y_hi + span * pad]
                # X-axis preset
                if (
                    ref_mode.x_range is not None
                    and not self.settings.xmin_enabled
                    and not self.settings.xmax_enabled
                ):
                    x_lo, x_hi = ref_mode.x_range
                    span = x_hi - x_lo
                    pad = ref_mode.x_padding or 0.0
                    if span > 0:
                        xRange = [x_lo - span * pad, x_hi + span * pad]
        except Exception:
            pass
        if xRange is not None or yRange is not None:
            self.plots["main_plot"].set_range(x=xRange, y=yRange)

        if self._metrics_text_alive() and not bool(
            getattr(cs, "_suspend_plot_metrics_overlay", False)
        ):
            try:
                metrics_text = self._build_metrics_overlay_text(current_fit=current_fit)
                # The text property setter keeps the overlay's colour and box
                # while replacing the content.
                self.text.text = metrics_text
            except Exception:
                pass

    def _build_metrics_overlay_html(self, current_fit) -> str:
        """Build the metrics overlay HTML.

        For FitGroups with multiple local fits shown, present a compact table of
        chi2r and Durbin-Watson, with the current fit highlighted.
        """
        font_pt = 8
        try:
            # Keep it compact; allow user override if present.
            font_pt = int(cs.core.settings.gui.get("plot", {}).get("metrics_font_pt", font_pt))
        except Exception:
            font_pt = 8

        # Determine whether this is a multi-fit group display.
        grouped_fits = getattr(self.fit, "grouped_fits", None)
        show_group = (
            bool(self.settings.display_group)
            and isinstance(grouped_fits, (list, tuple))
            and len(grouped_fits) > 1
        )
        current_idx = getattr(self.fit, "selected_fit_index", None)
        if not isinstance(current_idx, int):
            try:
                current_idx = grouped_fits.index(current_fit) if show_group else 0
            except Exception:
                current_idx = 0

        if show_group:
            rows = []
            for idx, f in enumerate(grouped_fits):
                chi2r = _fmt_metric(getattr(f, "chi2r", None), nd=4)
                dw = _fmt_metric(getattr(f, "durbin_watson", None), nd=4)
                if idx == current_idx:
                    row_style = "font-weight: 700; background-color: #2a2a2a;"
                else:
                    row_style = "color: #cccccc;"
                rows.append(
                    f"<tr style='{row_style}'>"
                    f"<td style='padding: 0px 6px 0px 0px; text-align:right;'>" + chi2r + "</td>"
                    "<td style='padding: 0px 0px 0px 6px; text-align:right;'>" + dw + "</td>"
                    "</tr>"
                )

            return (
                "<div style='name-align:center;'>"
                f"<div style='color:#FF0; font-size:{font_pt}pt;'>"
                + f"<div>Range {int(getattr(current_fit, 'xmin', 0))}, {int(getattr(current_fit, 'xmax', 0))}</div>"
                + "<table style='margin-top:3px; border-collapse:collapse;'>"
                + f"<tr style='color:#aaaaaa; font-size:{max(7, font_pt - 1)}pt;'>"
                + "<th style='text-align:right; padding: 0px 6px 1px 0px;'>chi2r</th>"
                + "<th style='text-align:right; padding: 0px 0px 1px 6px;'>DW</th>"
                + "</tr>"
                + "".join(rows)
                + "</table>"
                + "</div></div>"
            )

        # Single-fit overlay (compact)
        return (
            "<div style='name-align: center'>"
            f"<span style='color: #FF0; font-size: {font_pt}pt;'>"
            f"Range {int(getattr(current_fit, 'xmin', 0))}, {int(getattr(current_fit, 'xmax', 0))}<br/>"
            f"&Chi;<sup>2</sup>={_fmt_metric(getattr(current_fit, 'chi2r', None), nd=4)}<br/>"
            f"DW={_fmt_metric(getattr(current_fit, 'durbin_watson', None), nd=4)}"
            "</span></div>"
        )

    def _selected_reference_mode_for_model(self, model) -> plot_transforms.PlotReferenceMode | None:
        """Return the selected reference mode for ``model``.

        Parameters
        ----------
        model : object
            Model that may provide reference modes.

        Returns
        -------
        PlotReferenceMode or None
            Selected mode for this model, or None for raw plotting.
        """
        key = self.settings.reference_mode
        if key == "raw":
            return None
        for mode in self._reference_modes_for_model(model):
            if mode.key == key:
                return mode
        return None

    def _apply_reference_mode_to_curve(
        self,
        fit,
        model,
        curve_key: str,
        x: np.ndarray,
        y: np.ndarray,
        curves: typing.Mapping[str, typing.Any],
        group_fits: typing.Sequence | None = None,
        group_index: int | None = None,
        selected_group_index: int | None = None,
    ) -> plot_transforms.PlotReferenceResult:
        """Apply the selected reference mode to one curve.

        Parameters
        ----------
        fit : object
            Fit owning the curve.
        model : object
            Model attached to ``fit``.
        curve_key : str
            Curve name being plotted.
        x : numpy.ndarray
            Curve x-values.
        y : numpy.ndarray
            Curve y-values.
        curves : mapping
            Curves available for ``fit``.
        group_fits : sequence, optional
            Grouped fits.
        group_index : int, optional
            Index of ``fit`` in ``group_fits``.
        selected_group_index : int, optional
            Active grouped fit index.

        Returns
        -------
        PlotReferenceResult
            Transformed curve result.
        """
        mode = self._selected_reference_mode_for_model(model)
        if mode is None:
            return plot_transforms.PlotReferenceResult(x=x, y=y)

        context = plot_transforms.PlotReferenceContext(
            fit=fit,
            model=model,
            curve_key=curve_key,
            x=x,
            y=y,
            curves=curves,
            group_fits=tuple(group_fits or ()),
            group_index=group_index,
            selected_group_index=selected_group_index,
            parameters=self.settings.reference_parameters,
        )
        if not mode.applies(context):
            return plot_transforms.PlotReferenceResult(x=x, y=y)

        try:
            result = mode.callback(context)
        except Exception as exc:
            cs.logging.warning(
                "Plot reference mode '%s' failed for %s: %s", mode.key, curve_key, exc
            )
            return plot_transforms.PlotReferenceResult(x=x, y=y)

        if result is None:
            return plot_transforms.PlotReferenceResult(x=x, y=y)
        if isinstance(result, plot_transforms.PlotReferenceResult):
            self._reference_y_label_override = (
                result.y_label or mode.y_label or self._reference_y_label_override
            )
            return result
        if isinstance(result, tuple) and len(result) >= 2:
            transformed = plot_transforms.PlotReferenceResult(
                x=np.asarray(result[0], dtype=float),
                y=np.asarray(result[1], dtype=float),
            )
        else:
            try:
                transformed = plot_transforms.PlotReferenceResult(
                    x=x,
                    y=np.asarray(result, dtype=float),
                )
            except Exception:
                transformed = plot_transforms.PlotReferenceResult(x=x, y=y)
        if mode.y_label:
            self._reference_y_label_override = mode.y_label
        return transformed

    def _plot_single_fit_curves(
        self, fit, curves, data_log_x, data_log_y, director, x_shift, y_shift
    ):
        """Plot curves for a single fit (original behavior)"""
        curves_keys = list(curves.keys())[::-1]
        for i, curve_key in enumerate(curves_keys):
            curve_settings = director.get(curve_key, director["default"])
            curve = curves[curve_key]

            y = np.copy(curve.y)
            x = np.copy(curve.x)

            line: cp.handles.Curve = self.lines[curve_key]

            if curve_settings.get("allow_reference_transform", False):
                result = self._apply_reference_mode_to_curve(
                    fit=fit,
                    model=getattr(fit, "model", None),
                    curve_key=curve_key,
                    x=x,
                    y=y,
                    curves=curves,
                )
                if not result.visible:
                    line.set_data([], [])
                    line.hide()
                    continue
                x = np.asarray(result.x, dtype=float)
                y = np.asarray(result.y, dtype=float)

            if curve_settings["allow_shift"]:
                y += y_shift
                x += x_shift

            if self.settings.is_density and curve_settings["allow_density"]:
                y[1:] = y[1:] / np.diff(x)

            # Base data for plotting: either full curve or fit-range only
            if curve_settings["plot_only_region"] and len(x) == len(curve.x):
                x_plot = x[fit.xmin : fit.xmax]
                y_plot = y[fit.xmin : fit.xmax]
            else:
                x_plot = x
                y_plot = y

            line.set_data(x_plot, y_plot)
            if not self.settings.getCheckState(curve_key):
                line.hide()
            else:
                line.show()

    def _plot_group_curves(self, fit, data_log_x, data_log_y, director, x_shift, y_shift):
        """Plot curves for all fits in the group with highlighting"""
        grouped_fits = getattr(fit, "grouped_fits", [])
        if not grouped_fits:
            # Fallback to single fit if no group
            self._plot_single_fit_curves(
                fit, fit.get_curves(), data_log_x, data_log_y, director, x_shift, y_shift
            )
            return

        current_fit_index = getattr(fit, "selected_fit_index", 0)
        wres_offsets = self._compute_group_curve_offsets(
            grouped_fits, current_fit_index, curve_name="weighted residuals"
        )
        acor_offsets = self._compute_group_curve_offsets(
            grouped_fits, current_fit_index, curve_name="autocorrelation"
        )

        # Create line names for group fits
        group_line_names = {}
        for i, group_fit in enumerate(grouped_fits):
            group_curves = group_fit.get_curves()
            for curve_key in group_curves:
                group_line_names[f"{curve_key}_{i}"] = (group_fit, curve_key)

        # Plot all curves from all fits
        for line_name, (group_fit, curve_key) in group_line_names.items():
            group_curves = group_fit.get_curves()
            curve = group_curves[curve_key]
            curve_settings = director.get(curve_key, director["default"])

            y = np.copy(curve.y)
            x = np.copy(curve.x)

            if curve_settings.get("allow_reference_transform", False):
                result = self._apply_reference_mode_to_curve(
                    fit=group_fit,
                    model=getattr(group_fit, "model", None),
                    curve_key=curve_key,
                    x=x,
                    y=y,
                    curves=group_curves,
                    group_fits=grouped_fits,
                    group_index=grouped_fits.index(group_fit),
                    selected_group_index=current_fit_index,
                )
                if not result.visible:
                    if line_name in self.lines:
                        self.lines[line_name].set_data([], [])
                        self.lines[line_name].hide()
                    continue
                x = np.asarray(result.x, dtype=float)
                y = np.asarray(result.y, dtype=float)

            if curve_settings["allow_shift"]:
                y += y_shift
                x += x_shift

            if self.settings.is_density and curve_settings["allow_density"]:
                y[1:] = y[1:] / np.diff(x)

            # In grouped display mode, vertically separate weighted residuals so
            # each local-fit residual trace remains readable.
            if "weighted residuals" in curve_key:
                fit_index = grouped_fits.index(group_fit)
                y = y + wres_offsets.get(fit_index, 0.0)
            elif "autocorrelation" in curve_key:
                fit_index = grouped_fits.index(group_fit)
                y = y + acor_offsets.get(fit_index, 0.0)

            # Get or create the line for this group curve
            if line_name not in self.lines:
                # Create a new line for this group curve using the same logic as original lines
                curve_options = director.get(curve_key, director["default"])
                target_plot = self.plots[curve_settings["target"]]

                # Get color and width using the same logic as original line creation
                lw = curve_options.get("lw", 2)
                pen_color = curve_options.get("color", "#FFFFFF")
                label = curve_options.get("label", curve_key)
                if len(grouped_fits) > 1:
                    # Numbered like the rows of the fit-quality box, so a legend
                    # entry and a chi2 row name the same dataset.
                    label = f"{label} {grouped_fits.index(group_fit) + 1}"
                auto_downsample = curve_options.get("auto_downsample", False)
                clip_to_view = curve_options.get("clip_to_view", auto_downsample)

                # Apply the same transparency logic for non-primary curves
                if curve_key != curve_options.get("name", curve_key):
                    # make the line half as wide, and transparent (30%)
                    lw *= 0.5
                    pen_color = "#4D" + pen_color.split("#")[1]

                line = self._make_line(
                    target_plot,
                    pen_color,
                    lw,
                    label,
                    auto_downsample,
                    clip_to_view,
                )
                self._apply_curve_style(curve_key, line)
                self.lines[line_name] = line
            else:
                line = self.lines[line_name]

            # Base data for plotting: either full curve or fit-range only
            if curve_settings["plot_only_region"] and len(x) == len(curve.x):
                x_plot = x[group_fit.xmin : group_fit.xmax]
                y_plot = y[group_fit.xmin : group_fit.xmax]
            else:
                x_plot = x
                y_plot = y

            # Apply transparency and highlighting: the active fit is solid, the
            # other grouped fits are dimmed. chiplot's Curve.set_opacity gives
            # this in one call (replacing the former four-method fallback stack).
            fit_index = grouped_fits.index(group_fit)
            alpha = 1.0 if fit_index == current_fit_index else 0.4
            try:
                line.set_opacity(alpha)
            except Exception:
                pass  # If opacity is unsupported, continue without transparency

            line.set_data(x_plot, y_plot)

            # Show/hide based on checkbox state
            if not self.settings.getCheckState(curve_key):
                line.hide()
            else:
                line.show()

        # Hide original single-fit lines when in group mode
        for curve_key in fit.get_curves():
            if curve_key in self.lines:
                self.lines[curve_key].hide()

    def _plot_active_fit_only(self, fit, data_log_x, data_log_y, director, x_shift, y_shift):
        """Plot only the currently selected fit from a FitGroup"""
        # Get the currently selected fit
        current_fit = getattr(fit, "selected_fit", fit)
        current_curves = current_fit.get_curves()

        # Hide all group lines first
        grouped_fits = getattr(fit, "grouped_fits", [])
        for i, group_fit in enumerate(grouped_fits):
            group_curves = group_fit.get_curves()
            for curve_key in group_curves:
                line_name = f"{curve_key}_{i}"
                if line_name in self.lines:
                    self.lines[line_name].hide()

        # Plot only the current fit using the single fit logic
        self._plot_single_fit_curves(
            current_fit, current_curves, data_log_x, data_log_y, director, x_shift, y_shift
        )

    def _compute_group_curve_offsets(
        self, grouped_fits, current_fit_index: int, curve_name: str
    ) -> typing.Dict[int, float]:
        """Return per-fit y-offsets for grouped residual-like curve display.

        The spacing is derived from residual amplitudes across the group and the
        active fit is centered at zero.
        """
        if len(grouped_fits) <= 1:
            return {}

        amplitudes = []
        for group_fit in grouped_fits:
            try:
                curves = group_fit.get_curves()
                y = None
                if curve_name in curves:
                    y = np.asarray(curves[curve_name].y, dtype=float)
                else:
                    for key, c in curves.items():
                        if curve_name in str(key):
                            y = np.asarray(c.y, dtype=float)
                            break
                if y is None:
                    continue
            except Exception:
                continue
            if y.size == 0:
                continue
            finite = np.isfinite(y)
            if not np.any(finite):
                continue
            yv = y[finite]
            amp = float(np.nanpercentile(np.abs(yv), 95.0))
            if np.isfinite(amp) and amp > 0.0:
                amplitudes.append(amp)

        if amplitudes:
            typical_amp = float(np.nanmedian(amplitudes))
        else:
            typical_amp = 1.0

        # Keep residual traces separated, similar to pyqtgraph's multi-curve
        # demonstration where each curve is shifted by a fixed y-step.
        spacing = max(1.0, 2.5 * typical_amp)

        return {idx: (idx - int(current_fit_index)) * spacing for idx in range(len(grouped_fits))}
