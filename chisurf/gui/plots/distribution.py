from __future__ import annotations

import copy

import numpy as np

import chisurf.core.fitting
import chisurf.core.fluorescence
import chisurf.core.math.datatools
from chisurf.gui import chiplot as cp
from chisurf.gui.plots import plotbase


def _symbol(s):
    """Normalise a curve-option symbol to a chiplot symbol or ``None``.

    The distribution option dicts spell "no marker" as the string ``"None"``
    (a pyqtgraph idiom); chiplot expects an actual ``None``.

    Parameters
    ----------
    s : str or None
        Symbol name from a curve-options dict.

    Returns
    -------
    str or None
        The symbol name, or ``None`` when no marker should be drawn.
    """
    return None if s is None or str(s) == "None" else s


plot_settings = chisurf.core.settings.gui["plot"]
colors = plot_settings["colors"]
color_scheme = chisurf.core.settings.colors
lw = plot_settings["line_width"]

"""
For plotting
"""


def d21(x, **kwargs):
    return x[0][0], x[0][1]


# Define some distribution options: If an attribute in a model is there it will be plotted.
# accessor: a function that accesses the attribute and returns a pair (y, x)
# that is plotted
# accessor_kwargs: are kwargs that are passed to the accessor function
# plot_options: default options used for plotting
distribution_options = {
    "Distance": {
        "attribute": "distance_distribution",
        "accessor": lambda x, **kwargs: (x[0][0], x[0][1]),
        "accessor_kwargs": {"sort": False},
        "curve_options": {
            "stepMode": False,  # 'right'
            "connect": False,  # 'all'
            "symbol": "t",
            "multi_curve": False,
        },
    },
    "FRET-rate": {
        "attribute": "fret_rate_spectrum",
        "accessor": chisurf.core.math.datatools.interleaved_to_two_columns,
        "accessor_kwargs": {"sort": True},
        "curve_options": {
            "stepMode": False,  #'right',
            "connect": False,  # 'all',
            "symbol": "x",
            "multi_curve": False,
        },
    },
    "Lifetime": {
        "attribute": "lifetime_spectrum",
        "accessor": chisurf.core.math.datatools.interleaved_to_two_columns,
        "accessor_kwargs": {"sort": True},
        "curve_options": {"stepMode": False, "connect": False, "symbol": "o", "multi_curve": False},
    },
}


def _normalize_none(obj):
    """Recursively map the string ``"None"`` to Python ``None``.

    The option dicts spell "nothing" as the string ``"None"`` in places
    (pyqtgraph's idiom); consumers expect a real ``None``. Dicts and lists are
    copied; every other value (numbers, bools, callables, ...) is returned by
    reference.
    """
    if isinstance(obj, str):
        return None if obj == "None" else obj
    if isinstance(obj, dict):
        return {k: _normalize_none(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_none(v) for v in obj]
    return obj


class OptionsForm:
    """One distribution's option dict, as a model emtk's view form can edit.

    The dict is nested (``curve_options`` holds ``stepMode``, ``connect``, ...)
    and its keys depend on the distribution, so its form is generated, not
    authored: :meth:`spec` returns view-spec sections whose ``attr`` is the
    dotted path of a leaf (``"curve_options.stepMode"``), and attribute access
    on this object resolves such paths into the dict. Each editable leaf has a
    ↩ button (action ``"reset:<path>"``) back to the value it started with. A
    list is a choice whose pick moves the item to the front, as the old
    parameter tree did; callables and other values are shown read-only.

    Parameters
    ----------
    data : dict
        The option dict, edited in place.
    on_change : callable
        Called after every edit.
    """

    def __init__(self, data: dict, on_change) -> None:
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_defaults", copy.deepcopy(_plain(data)))
        object.__setattr__(self, "_on_change", on_change)

    # -- dotted-path access ------------------------------------------------
    def _lookup(self, path: str):
        node = self._data
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                raise AttributeError(path)
            node = node[key]
        return node

    def _store(self, path: str, value) -> None:
        *parents, leaf = path.split(".")
        node = self._data
        for key in parents:
            node = node[key]
        node[leaf] = value
        self._on_change()

    def __getattr__(self, name: str):
        if name.startswith("reset:"):
            return lambda: self._reset(name[len("reset:"):])
        if name.startswith("options:"):
            return lambda: [str(v) for v in self._lookup(name[len("options:"):])]
        if name.startswith("first:"):
            values = self._lookup(name[len("first:"):])
            return str(values[0]) if values else ""
        return self._lookup(name)

    def __setattr__(self, name: str, value) -> None:
        if name.startswith("first:"):
            path = name[len("first:"):]
            values = list(self._lookup(path))
            chosen = next((v for v in values if str(v) == str(value)), None)
            if chosen is not None:
                values.remove(chosen)
                self._store(path, [chosen] + values)
            return
        self._store(name, value)

    def _reset(self, path: str) -> None:
        node = self._defaults
        for key in path.split("."):
            node = node[key]
        self._store(path, copy.deepcopy(node))

    # -- the form ----------------------------------------------------------
    def spec(self, needle: str = "") -> list:
        """Sections for every leaf whose path contains *needle* (lower case)."""
        return self._sections(self._data, "", needle.strip().lower())

    def _sections(self, data: dict, prefix: str, needle: str) -> list:
        """One aligned grid per run of leaves (field, ↩), a fold per nested dict."""
        sections: list = []
        leaves: list = []

        def flush() -> None:
            if leaves:
                sections.append({"type": "panel", "collapsible": False, "n_col": 2,
                                 "sections": list(leaves)})
                leaves.clear()

        for key, value in data.items():
            path = f"{prefix}{key}"
            if isinstance(value, dict):
                children = self._sections(value, path + ".", needle)
                if children:
                    flush()
                    sections.append({"type": "panel", "title": str(key), "collapsible": True,
                                     "sections": children})
                continue
            if needle and needle not in path.lower():
                continue
            leaves.extend(self._leaf(path, str(key), value))
        flush()
        return sections

    @staticmethod
    def _leaf(path: str, label: str, value) -> list:
        """The field of one leaf and its ↩ (a blank cell for a read-only one)."""
        reset = {"type": "button_row", "width": 30, "buttons": [
            {"action": f"reset:{path}", "label": "↩", "description": "Reset to the starting value."}
        ]}
        description = f"{path} of the distribution options."
        if isinstance(value, bool):
            field = {"type": "toggle", "attr": path, "label": label, "description": description}
        elif isinstance(value, int):
            field = {"type": "value", "attr": path, "label": label, "kind": "int",
                     "description": description}
        elif isinstance(value, float):
            field = {"type": "value", "attr": path, "label": label, "kind": "float",
                     "decimals": 6, "description": description}
        elif isinstance(value, str):
            field = {"type": "value", "attr": path, "label": label, "kind": "str",
                     "description": description}
        elif isinstance(value, (list, tuple)) and value:
            field = {"type": "choice", "attr": f"first:{path}", "label": label,
                     "options_source": f"options:{path}",
                     "description": description + " The chosen entry is moved to the front."}
        else:
            field = {"type": "value", "attr": path, "label": label, "kind": "str",
                     "read_only": True, "description": description + " (not editable here)"}
            reset = {"type": "info", "text": "", "width": 30}
        return [field, reset]


def _plain(data):
    """A deep copy of the plain values of *data* (callables are kept by reference)."""
    if isinstance(data, dict):
        return {k: _plain(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_plain(v) for v in data]
    return data


class DistributionPlot(plotbase.Plot):
    """A distribution the model serves (distance, rate, lifetime, PDA histogram).

    The settings (``distribution.settings.view.json``) choose the distribution,
    edit how it is read and drawn (its option dict, as a generated form with a
    filter -- :class:`OptionsForm`), and toggle the component curves.
    """

    name = "Distribution"
    settings_view = "distribution.settings.view.json"

    def __init__(
        self,
        fit: chisurf.core.fitting.fit.FitGroup,
        parent=None,
        distribution_options: dict = None,
        **kwargs,
    ):
        super().__init__(fit=fit, parent=parent)
        self.data_x, self.data_y = None, None
        if distribution_options is None:
            distribution_options = globals()["distribution_options"]
        self.distribution_options = distribution_options
        #: The edited copy of each distribution's options, made on first choice.
        self._edited: dict = {}
        self._forms: dict = {}
        self._filter = ""
        self._show_gaussians = True
        types = self.distribution_types()
        self._distribution_type = types[0] if types else ""

        # Optional axis scaling and an optional residual panel (for PDA 1D
        # histograms), where weighted residuals are shown on a separate top
        # plot, similar to the TCSPC LinePlot layout.
        self._scale_x = kwargs.pop("scale_x", "lin")
        self._scale_y = kwargs.pop("scale_y", "lin")
        self._with_residual_panel = kwargs.pop("with_residual_panel", False)
        self.residual_plot = None

        if self._with_residual_panel:
            # The residuals panel takes ~1/3 of the height, the histogram ~2/3.
            p_res = self.add_panel(stretch=1)
            p_main = self.add_panel(stretch=2)
            p_res.link_x(p_main)
            self.residual_plot = p_res
            self.distribution_plot = p_main
            self.residual_plot.set_axis_visible(bottom=False)
            self.residual_plot.set_labels(left="w.res.")
        else:
            p = self.add_panel()
            self.distribution_plot = p

        # Match LinePlot's grid settings where applicable: show a grid on the
        # main distribution plot and, when present, on the residuals.
        if plot_settings.get("enable_grid", False):
            if plot_settings.get("show_data_grid", False):
                self.distribution_plot.grid(x=True, y=True, alpha=0.5)
            if self.residual_plot is not None and plot_settings.get("show_residual_grid", False):
                self.residual_plot.grid(x=True, y=True, alpha=1.0)

        # Apply requested axis scaling (x) to main plot and residuals.
        log_x = str(self._scale_x).lower() == "log"
        log_y = str(self._scale_y).lower() == "log"
        self.distribution_plot.set_log(x=log_x, y=log_y)
        if self.residual_plot is not None:
            self.residual_plot.set_log(x=log_x, y=False)

        self.distribution_curve = self.distribution_plot.line(
            [0.0], [0.0], pen=colors["data"], width=lw, fill=colors["data"]
        )

        # Draggable fit-quality box (χ²_red and DW), similar to LinePlot: a
        # screen-pinned yellow overlay whose plain text is refreshed on update.
        try:
            self._quality_text = self.distribution_plot.text(
                "",
                (0, 0),
                color="#FF0",
                border="w",
                fill=(0, 0, 255, 100),
                anchor=(0, 0),
                draggable=True,
                anchored=True,
            )
        except Exception:
            self._quality_text = None

    # -- settings -----------------------------------------------------------

    def distribution_types(self) -> list[str]:
        """The distributions the model actually serves."""
        model = self.fit.model
        items = []
        for distribution_type, d in self.distribution_options.items():
            # ``getattr``, not ``__getattribute__``: a described model serves
            # its distributions from ``__getattr__``, which ``__getattribute__``
            # never reaches -- every lifetime fit's Distribution tab found no
            # distribution and failed with ``KeyError: ''``.
            try:
                getattr(model, d["attribute"])
                items.append(distribution_type)
            except AttributeError:
                pass
        return items

    @property
    def distribution_type(self) -> str:
        """The distribution drawn."""
        return self._distribution_type

    @distribution_type.setter
    def distribution_type(self, value: str) -> None:
        self._distribution_type = str(value)
        self.update()

    @property
    def show_gaussians(self) -> bool:
        """Whether individual component curves (e.g. PDA Gaussians) are drawn."""
        return self._show_gaussians

    @show_gaussians.setter
    def show_gaussians(self, value: bool) -> None:
        self._show_gaussians = bool(value)
        self.update()

    def _options_form(self) -> OptionsForm:
        """The form over the current distribution's (edited) options."""
        key = self._distribution_type
        if key not in self._forms:
            self._edited[key] = copy.deepcopy(self.distribution_options[key])
            self._forms[key] = OptionsForm(self._edited[key], self.update)
        return self._forms[key]

    @property
    def options(self) -> dict:
        """The current distribution's options as drawn (``"None"`` read as ``None``)."""
        return _normalize_none(self._options_form()._data)

    def register_settings_sections(self, form) -> None:
        """Register the generated options form (``custom`` key ``distribution_options``)."""
        form.custom["distribution_options"] = self._draw_options

    def _draw_options(self, section, model, state, width) -> None:
        """A filter field over the generated form of the option dict."""
        from emtk import im
        from emtk.view_form import draw_sections

        if not self._distribution_type:
            return
        im.set_next_item_width(-1.0)
        changed, text = im.input_text_with_hint("##distribution-filter",
                                                "Filter parameters…", self._filter)
        im.set_item_tooltip("Show only the options whose name contains this text.")
        if changed:
            self._filter = text
        form = self._options_form()
        draw_sections(form.spec(self._filter), form, state)

    def get_settings_state(self) -> dict:
        """The settings, for the project file."""
        return {"distribution_type": self._distribution_type,
                "show_components": bool(self.show_gaussians)}

    def set_settings_state(self, state: dict) -> None:
        """Restore :meth:`get_settings_state`."""
        if not isinstance(state, dict):
            return
        if state.get("distribution_type") in self.distribution_types():
            self._distribution_type = state["distribution_type"]
        if "show_components" in state:
            self._show_gaussians = bool(state["show_components"])
        self.update()

    # -- drawing ------------------------------------------------------------

    def update(self, *args, **kwargs) -> None:
        super().update(*args, **kwargs)
        if not self._distribution_type:
            return
        # Clear curves and recreate plots. The screen-pinned statistics box is
        # parented to the plot item (not an addItem'd handle), so it survives
        # clear() and stays visible, mirroring the TCSPC LinePlot.
        self.distribution_plot.clear()
        if self.residual_plot is not None:
            self.residual_plot.clear()

        # Get distribution
        ds = self.options

        # Update x-axis label to reflect the currently used histogram axis /
        # function. Prefer an explicit axis label or kw_hist['_axis_type']
        # when configured; otherwise fall back to the distribution selector
        # text (e.g. 'S1/(S0+S1)', 'S0/S1', 'Distance').
        try:
            axis_label = ds.get("axis_label")
        except Exception:
            axis_label = None
        if not axis_label:
            try:
                kw_hist = ds.get("accessor_kwargs", {}).get("kw_hist", {})
                axis_label = kw_hist.get("_axis_type")
            except Exception:
                axis_label = None
        if not axis_label:
            axis_label = self._distribution_type
        if axis_label:
            self.distribution_plot.set_labels(bottom=axis_label)

        # Update axis scaling based on the currently selected distribution
        scale_x = ds.get("scale_x", self._scale_x)
        scale_y = ds.get("scale_y", self._scale_y)
        log_x = str(scale_x).lower() == "log"
        log_y = str(scale_y).lower() == "log"
        self.distribution_plot.set_log(x=log_x, y=log_y)
        if self.residual_plot is not None:
            self.residual_plot.set_log(x=log_x, y=False)
        r = ds["accessor"](
            getattr(self.fit.model, ds["attribute"]), **ds.get("accessor_kwargs", {})
        )

        # Helper to drop curves with no finite support. This prevents
        # feeding all-NaN or empty arrays into pyqtgraph's ScatterPlotItem,
        # which otherwise emits RuntimeWarnings.
        def _sanitize_curve(y, x):
            try:
                x_arr = np.asarray(x, dtype=float).ravel()
                y_arr = np.asarray(y, dtype=float).ravel()
            except Exception:
                return None
            if x_arr.size == 0 or y_arr.size == 0:
                return None
            if not np.any(np.isfinite(x_arr)) or not np.any(np.isfinite(y_arr)):
                return None
            return y_arr, x_arr

        # Optionally derive weighted residuals and basic fit statistics from the
        # first two curves (data, model) using counting shot noise
        # sigma = sqrt(max(data, 1)). For PDA 1D histograms this matches the
        # definition used in chisurf.gui.widgets.models.pda2c.get_distribution and
        # allows us to define DW directly from the currently shown histogram
        # rather than only from the global Fit object. Bins with zero
        # experimental counts do not contribute to DW or the effective
        # fit-range; we only use bins with at least one photon.
        wres_curve = None
        dw = None
        hist_i_min = None
        hist_i_max = None
        try:
            if isinstance(r, (list, tuple)) and len(r) >= 2:
                data_y, data_x = r[0]
                model_y, model_x = r[1]
                dy = np.asarray(data_y, dtype=float)
                my = np.asarray(model_y, dtype=float)
                if dy.shape == my.shape and dy.size > 0:
                    # Consider only bins with at least one photon in the data
                    mask = dy > 0.0
                    nz_idx = np.nonzero(mask)[0]
                    if nz_idx.size > 0:
                        hist_i_min = int(nz_idx[0])
                        hist_i_max = int(nz_idx[-1])
                        dy_nz = dy[mask]
                        my_nz = my[mask]
                        sigma_nz = np.sqrt(np.maximum(dy_nz, 1.0))
                        resid_nz = (dy_nz - my_nz) / sigma_nz
                        # Durbin–Watson statistic for these residuals
                        if resid_nz.size > 1:
                            num = float(np.sum(np.diff(resid_nz) ** 2))
                            den = float(np.sum(resid_nz**2))
                            if den > 0.0:
                                dw = num / den
                        # Build a residual curve that is zero outside the
                        # non-empty bins so the w.res. panel visually matches
                        # the effective fit-range.
                        resid_full = np.zeros_like(dy, dtype=float)
                        resid_full[mask] = resid_nz
                        has_explicit_residual = isinstance(r, (list, tuple)) and len(r) >= 3
                        if self.residual_plot is not None and not has_explicit_residual:
                            wres_curve = (resid_full, data_x)
        except Exception:
            wres_curve = None
            dw = None
            hist_i_min = None
            hist_i_max = None

        p = dict(ds.get("curve_options", {}))

        # Normalize optional fill/line colors for single-curve distributions.
        # If a fillBrush is provided, use the same RGB values for the line and
        # make the fill about 50% transparent so that the histogram area is
        # softly shaded but the outline remains fully opaque.
        try:
            if not p.get("multi_curve", False) and "fillBrush" in p:
                base = p["fillBrush"]
                col = cp.to_color(base)
                r_c, g_c, b_c, _ = col.as_tuple()
                alpha_fill = int(0.5 * 255)
                p["fillBrush"] = (r_c, g_c, b_c, alpha_fill)
                if "pen" not in p:
                    p["pen"] = (r_c, g_c, b_c, 255)
        except Exception:
            pass

        bar_mode = p.pop("bar_mode", None)
        multi_curve = p.get("multi_curve", False)

        # If we have a residual panel and a synthesized wres curve, append it so
        # that it is plotted in the residual axis (index >= 2).
        if multi_curve and self.residual_plot is not None and wres_curve is not None:
            try:
                r = list(r)
                r.append(wres_curve)
            except Exception:
                pass

        if multi_curve:
            n_curves = len(r)
            pens = p.pop("pen", ["r", "b", "g", "y", "c", "m", "k"])
            symbols = p.pop("symbol", ["o", "x", "v", "^", "<"])

            # Normalize pens/symbols so they are lists of at least n_curves
            # elements. This avoids IndexError when more curves are returned
            # than there are explicit colors/symbols configured.
            if isinstance(pens, str):
                pens = [pens]
            if isinstance(symbols, str):
                symbols = [symbols]

            if len(pens) < n_curves:
                base = pens if pens else ["w"]
                pens = [base[i % len(base)] for i in range(n_curves)]
            if len(symbols) < n_curves:
                base = symbols if symbols else ["o"]
                symbols = [base[i % len(base)] for i in range(n_curves)]

            # Remove any global stepMode/connect from p; we choose them per
            # curve index below so that data/model remain stepped histograms
            # while residuals and Gaussian components are smooth lines or
            # discrete "sticks" when requested via bar_mode.
            p.pop("stepMode", None)
            p.pop("connect", None)

            # Optional filled-under-curve styling for multi-curve plots. When
            # a fillBrush/fillLevel is provided in curve_options, apply it to
            # the first curve only (typically the experimental PDA histogram).
            # The fill uses the same RGB values as the data line but with
            # ~50% transparency so that the line remains clearly visible.
            fill_brush = None
            try:
                if "fillBrush" in p:
                    fill_brush = p.pop("fillBrush")
                    p.pop("fillLevel", None)
                    if pens:
                        base_col = cp.to_color(pens[0])
                        r_c, g_c, b_c, _ = base_col.as_tuple()
                        alpha_fill = int(0.5 * 255)
                        fill_brush = (r_c, g_c, b_c, alpha_fill)
                        pens[0] = (r_c, g_c, b_c, 255)
            except Exception:
                fill_brush = None

            for i in range(n_curves):
                y_raw, x_raw = r[i]
                cur = _sanitize_curve(y_raw, x_raw)
                if cur is None:
                    continue
                y, x = cur
                c, s = pens[i], symbols[i]

                # Allow the plot controller to hide individual component
                # curves (indices >= 3 in PDA Gaussian-distance plots) while
                # keeping data, model and residuals visible.
                if i >= 3 and not self.show_gaussians:
                    continue

                # For discrete PDA histograms (PDA-discrete), we want data,
                # model, and residuals as vertical lines (sticks) when the
                # accessor requested bar_mode == 'sticks'.
                use_sticks = bar_mode == "sticks" and i in (0, 1, 2)
                if use_sticks:
                    x_arr = np.asarray(x, dtype=float)
                    y_arr = np.asarray(y, dtype=float)
                    if (
                        x_arr.size == 0
                        or not np.any(np.isfinite(x_arr))
                        or not np.any(np.isfinite(y_arr))
                    ):
                        continue
                    xs = np.empty(3 * x_arr.size, dtype=float)
                    ys = np.empty_like(xs)
                    xs[0::3] = x_arr
                    xs[1::3] = x_arr
                    xs[2::3] = np.nan
                    ys[0::3] = 0.0
                    ys[1::3] = y_arr
                    ys[2::3] = np.nan
                    x_plot, y_plot = xs, ys
                else:
                    x_plot, y_plot = x, y

                # By convention for PDA multi-curve plots:
                #   0: data      (stepped or sticks, main plot)
                #   1: model     (stepped or sticks, main plot)
                #   2: w.res.    (stepped or sticks, residual plot if present)
                #   3+: extra curves (e.g. Gaussian components) -> smooth, main
                if self.residual_plot is not None and i == 2:
                    target_plot = self.residual_plot
                    if use_sticks:
                        curve_step = False
                    else:
                        # Weighted residuals: stepped style for visual
                        # consistency with data/model.
                        curve_step = "right"
                    # Use the dedicated residuals color for the w.res. curve.
                    try:
                        c = colors.get("residuals", c)
                    except Exception:
                        pass
                else:
                    target_plot = self.distribution_plot
                    if i in (0, 1):
                        # Data and model: histogram-style stepped plot or
                        # sticks, depending on bar_mode.
                        curve_step = False if use_sticks else "right"
                    else:
                        # Gaussian components and any other extra curves:
                        # smooth lines.
                        curve_step = False

                if fill_brush is not None and i == 0:
                    target_plot.line(
                        x_plot,
                        y_plot,
                        step=curve_step,
                        pen=c,
                        width=lw,
                        symbol=_symbol(s),
                        fill=fill_brush,
                    )
                else:
                    target_plot.line(
                        x_plot,
                        y_plot,
                        step=curve_step,
                        pen=c,
                        width=lw,
                        symbol=_symbol(s),
                    )
        else:
            y_raw, x_raw = r
            cur = _sanitize_curve(y_raw, x_raw)
            if cur is None:
                return
            y, x = cur
            c = p.pop("pen", "b")
            s = p.pop("symbol", "o")
            # Translate the remaining pyqtgraph-style curve options to chiplot
            # line kwargs. stepMode ('right'/'left'/'center'/True) passes through
            # as the step mode; fillBrush/fillLevel becomes a fill to baseline.
            step = p.pop("stepMode", False)
            fill = p.pop("fillBrush", None)
            p.pop("fillLevel", None)
            if bar_mode == "sticks":
                # Single-curve discrete distributions (e.g., lifetime
                # distributions) are rendered as vertical lines from 0 to y at
                # each x when bar_mode == 'sticks'.
                x_arr = np.asarray(x, dtype=float)
                y_arr = np.asarray(y, dtype=float)
                if x_arr.size > 0:
                    xs = np.empty(3 * x_arr.size, dtype=float)
                    ys = np.empty_like(xs)
                    xs[0::3] = x_arr
                    xs[1::3] = x_arr
                    xs[2::3] = np.nan
                    ys[0::3] = 0.0
                    ys[1::3] = y_arr
                    ys[2::3] = np.nan
                    self.distribution_plot.line(
                        xs, ys, step=False, pen=c, width=lw, symbol=_symbol(s), fill=fill
                    )
            else:
                self.distribution_plot.line(
                    x, y, step=step, pen=c, width=lw, symbol=_symbol(s), fill=fill
                )

        # Show basic fit quality metrics in a draggable box. Prefer the
        # histogram-based chi²/DW computed above and fall back to the Fit
        # object's statistics only if necessary, while keeping the HTML
        # formatting identical to the TCSPC LinePlot.
        try:
            if self._quality_text is not None:
                fit = self.fit
                chi2_display = getattr(fit, "chi2r", None)
                dw_display = dw if dw is not None else getattr(fit, "durbin_watson", None)
                # Prefer the effective histogram fit-range (first/last non-empty
                # bin) and fall back to the Fit object's xmin/xmax otherwise.
                xmin = hist_i_min if hist_i_min is not None else getattr(fit, "xmin", None)
                xmax = hist_i_max if hist_i_max is not None else getattr(fit, "xmax", None)
                if chi2_display is not None and dw_display is not None:
                    lines = []
                    if xmin is not None and xmax is not None:
                        lines.append(f"Fit-range {xmin}, {xmax}")
                    lines.append(f"χ²r={chi2_display:.4f}")
                    lines.append(f"DW={dw_display:.4f}")
                    self._quality_text.text = "\n".join(lines)
        except Exception:
            pass

        # Keep the main plot title free of statistics, like the LinePlot.
        self.distribution_plot.set_title("")
