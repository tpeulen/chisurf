"""Qt-free EMTK plot settings editor."""
from __future__ import annotations

from emtk import i18n, im
from emtk.app import ImApp

from .strings import install_translations, tr

install_translations()


class PlotSettingsModel:
    def __init__(self):
        self.backend = "emtk"
        self.colors = {
            "data": "#ffa52f", "model": "#d000d0", "irf": "#4080e8",
            "residuals": "#e00000", "auto_corr": "#ff00d0", "region_selector": "#2ca39c",
        }
        self.region_alpha = 50
        self.active_transparency = 1.0
        self.inactive_transparency = 0.2
        self.line_width = 1.5
        self.font_size = 0
        self.enable_grid = True
        self.grid_alpha = 0.35
        self.show_data_grid = True
        self.show_residual_grid = True
        self.show_acorr_grid = True
        self.enable_region_selector = True
        self.show_legend = False
        self.hide_title = True
        self.label_axis = False
        # The node-graph section starts from what the settings hold, not from
        # a second copy of the defaults: this panel and the graphs read the
        # same numbers through chisurf.emtk.node_editor.style_settings.
        try:
            from chisurf.emtk.node_editor.style_settings import node_graph_settings

            self.node_graph = node_graph_settings()
        except Exception:  # noqa: BLE001 - no settings: the shipped defaults
            from chisurf.emtk.node_editor.style_settings import NODE_GRAPH_DEFAULTS

            self.node_graph = dict(NODE_GRAPH_DEFAULTS)
        self.pyqtgraph_config = {"antialias": False, "leftButtonPan": True, "background": "k", "foreground": "d"}
        self.message = tr("Defaults loaded")

    def apply(self) -> None:
        try:
            import chisurf.core.settings as css
            plot = css.cs_settings.setdefault("gui", {}).setdefault("plot", {})
            plot.update({"backend": self.backend, "colors": dict(self.colors),
                         "region_selector_alpha": self.region_alpha,
                         "active_transparency": self.active_transparency,
                         "inactive_transparency": self.inactive_transparency,
                         "line_width": self.line_width})
            plot.update({"font_size": self.font_size, "enable_grid": self.enable_grid,
                         "grid_alpha": self.grid_alpha, "show_data_grid": self.show_data_grid,
                         "show_residual_grid": self.show_residual_grid,
                         "show_acorr_grid": self.show_acorr_grid,
                         "enable_region_selector": self.enable_region_selector,
                         "show_legend": self.show_legend, "hideTitle": self.hide_title,
                         "label_axis": self.label_axis, "pyqtgraph_config": dict(self.pyqtgraph_config),
                         "node_graph": dict(self.node_graph)})
            # An open Global View reads its style only when it is built.
            try:
                from chisurf.emtk.node_editor.style_settings import refresh_open_graphs

                refresh_open_graphs()
            except Exception:  # noqa: BLE001
                pass
            self.message = tr("Applied")
        except Exception as exc:
            self.message = f"{type(exc).__name__}: {exc}"

    def export_settings(self):
        return {"backend": self.backend, "colors": dict(self.colors),
                "region_alpha": self.region_alpha,
                "active_transparency": self.active_transparency,
                "inactive_transparency": self.inactive_transparency,
                "line_width": self.line_width, "font_size": self.font_size,
                "enable_grid": self.enable_grid, "grid_alpha": self.grid_alpha,
                "show_data_grid": self.show_data_grid,
                "show_residual_grid": self.show_residual_grid,
                "show_acorr_grid": self.show_acorr_grid,
                "enable_region_selector": self.enable_region_selector,
                "show_legend": self.show_legend, "hide_title": self.hide_title,
                "label_axis": self.label_axis,
                "node_graph": dict(self.node_graph),
                "pyqtgraph_config": dict(self.pyqtgraph_config)}


class PlotSettingsApp(ImApp):
    def __init__(self):
        self.model = PlotSettingsModel()
        super().__init__(self.render)

    def _input_float(self, label, value, tip):
        im.text(tr(label))
        im.same_line()
        im.set_next_item_width(120)
        changed, result = im.input_float("##" + label, float(value), step=0.0)
        im.set_item_tooltip(tr(tip))
        return result if changed else value

    @staticmethod
    def _hex_color(value):
        raw = str(value).lstrip("#")
        try:
            if len(raw) == 3:
                raw = "".join(char * 2 for char in raw)
            return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4)) + (255,)
        except (TypeError, ValueError):
            return (180, 180, 190, 255)

    def _draw_preview(self):
        """Draw the same three representative curves as the Qt preview."""
        ctx = im.get_current_context()
        origin = im.get_cursor_screen_pos()
        width = max(260.0, im.get_content_region_avail()[0])
        height = 112.0
        ctx.draw.add_rect_filled(origin, (origin[0] + width, origin[1] + height), (18, 18, 22, 255), 2)
        if self.model.enable_grid:
            for index in range(1, 10):
                x = origin[0] + width * index / 10.0
                ctx.draw.add_line((x, origin[1]), (x, origin[1] + height), (55, 55, 62, 130), 1)
            for index in range(1, 5):
                y = origin[1] + height * index / 5.0
                ctx.draw.add_line((origin[0], y), (origin[0] + width, y), (55, 55, 62, 130), 1)
        import math
        curves = (("data", 3.0, 0.0), ("model", 2.8, 0.03), ("irf", 0.9, 0.12))
        for key, tau, offset in curves:
            points = []
            for index in range(96):
                fraction = index / 95.0
                value = math.exp(-fraction * 4.0 / tau)
                points.append((origin[0] + fraction * width, origin[1] + height * (0.9 - 0.72 * value - offset)))
            ctx.draw.add_polyline(points, self._hex_color(self.model.colors[key]), thickness=max(1.0, self.model.line_width))
        im.dummy(0.0, height)

    def render(self):
        viewport = im.get_main_viewport().size
        width = max(420.0, min(760.0, float(viewport[0])))
        height = max(320.0, min(700.0, float(viewport[1])))
        im.begin(tr("Plot Settings"), (0, 0, width, height))
        im.begin_child("plot_settings_scroll", (width - 8.0, height - 8.0), scrollable=True)
        im.heading(tr("Rendering Backend"), level=2)
        changed, selected = im.combo("##backend", ["emtk", "pyqtgraph", "matplotlib"].index(self.model.backend), ["emtk", "pyqtgraph", "matplotlib"])
        im.set_item_tooltip(tr("Backend used for newly created plots"))
        if changed:
            self.model.backend = ["emtk", "pyqtgraph", "matplotlib"][selected]
        im.separator()
        im.heading(tr("Colors"), level=2)
        for key in tuple(self.model.colors):
            im.text(tr(key))
            im.same_line()
            im.set_next_item_width(130)
            changed, value = im.input_text("##color_" + key, self.model.colors[key])
            im.set_item_tooltip(tr("Hex color used for this plot series"))
            if changed:
                self.model.colors[key] = value
        im.separator()
        im.heading(tr("Appearance"), level=2)
        for attr, label, tip in (("font_size", "Axis font size", "Base point size for plot axes and labels."),):
            value = self._input_float(label, getattr(self.model, attr), tip)
            setattr(self.model, attr, int(max(0, value)))
        appearance_toggles = (("enable_grid", "Enable grid", "Show plot grid lines."), ("show_data_grid", "Grid on data panel", "Show grid on data plots."), ("show_residual_grid", "Grid on residuals", "Show grid on residual plots."), ("show_acorr_grid", "Grid on autocorrelation", "Show grid on autocorrelation plots."), ("enable_region_selector", "Fit-range selector", "Show the draggable fit-range region."), ("show_legend", "Show legend", "Show plot legends by default."), ("hide_title", "Hide titles", "Hide plot titles by default."), ("label_axis", "Label axes", "Show axis names."))
        for index, (attr, label, tip) in enumerate(appearance_toggles):
            if index % 2:
                im.same_line()
            changed, value = im.checkbox(tr(label), getattr(self.model, attr))
            im.set_item_tooltip(tr(tip))
            if changed:
                setattr(self.model, attr, value)
        self.model.grid_alpha = self._input_float("Grid opacity", self.model.grid_alpha, "Grid line opacity.")
        im.separator()
        im.heading(tr("Node Graphs (Global View)"), level=2)
        changed, value = im.checkbox(tr("Show grid"), self.model.node_graph["show_grid"])
        im.set_item_tooltip(tr("Show the background grid of a node graph."))
        if changed:
            self.model.node_graph["show_grid"] = value
        self.model.node_graph["grid_line_width"] = self._input_float(
            "Grid line width", self.model.node_graph["grid_line_width"],
            "Grid line thickness. Below one pixel draws a hairline, which is what keeps the grid under the edges drawn on top of it.")
        self.model.node_graph["grid_opacity"] = self._input_float(
            "Node grid opacity", self.model.node_graph["grid_opacity"], "Grid line opacity of a node graph.")
        self.model.node_graph["grid_spacing"] = self._input_float(
            "Grid spacing", self.model.node_graph["grid_spacing"], "Distance between the grid lines of a node graph.")
        self.model.node_graph["node_size"] = self._input_float(
            "Node size (Global View)", self.model.node_graph["node_size"],
            "The node radius a newly opened Global View starts its own node-size control at.")
        im.separator()
        im.heading(tr("Advanced: pyqtgraph Configuration"), level=2)
        for index, (attr, label, tip) in enumerate((("antialias", "Antialiasing", "Use antialiased pyqtgraph lines."), ("leftButtonPan", "Left button pans", "Pan with the left mouse button."))):
            if index:
                im.same_line()
            changed, value = im.checkbox(tr(label), self.model.pyqtgraph_config[attr])
            im.set_item_tooltip(tr(tip))
            if changed:
                self.model.pyqtgraph_config[attr] = value
        for attr, label in (("background", "Background"), ("foreground", "Foreground")):
            options = ["k", "w", "default"] if attr == "background" else ["d", "w", "l", "k"]
            changed, index = im.combo("##pg_" + attr, options.index(self.model.pyqtgraph_config[attr]) if self.model.pyqtgraph_config[attr] in options else 0, options)
            im.set_item_tooltip(tr("pyqtgraph " + attr + " color"))
            if changed:
                self.model.pyqtgraph_config[attr] = options[index]
        self.model.region_alpha = int(self._input_float("Region alpha", self.model.region_alpha, "Transparency of the selected region"))
        self.model.active_transparency = self._input_float("Active transparency", self.model.active_transparency, "Opacity of the active plot")
        self.model.inactive_transparency = self._input_float("Inactive transparency", self.model.inactive_transparency, "Opacity of inactive plots")
        self.model.line_width = self._input_float("Line width", self.model.line_width, "Width of plotted lines")
        im.separator()
        im.heading(tr("Actions"), level=2)
        if im.button(tr("Apply")):
            self.model.apply()
        im.set_item_tooltip(tr("Apply plot settings to the active configuration"))
        im.same_line()
        if im.button(tr("Save")):
            self.model.apply()
        im.set_item_tooltip(tr("Apply and persist plot settings"))
        im.same_line()
        if im.button(tr("Reset")):
            self.model = PlotSettingsModel()
        im.set_item_tooltip(tr("Restore the default plot settings"))
        im.text_wrapped(self.model.message)
        im.separator()
        im.heading(tr("Preview"), level=2)
        im.text_wrapped(tr("Sample decay preview uses the current colors, line width, grid and legend settings."))
        self._draw_preview()
        im.end_child()
        im.end()

    def export_settings(self):
        return self.model.export_settings()

    def restore_settings(self, settings):
        for key, value in settings.items():
            if key == "colors" and isinstance(value, dict):
                self.model.colors.update(value)
            elif key == "pyqtgraph_config" and isinstance(value, dict):
                self.model.pyqtgraph_config.update(value)
            elif key == "node_graph" and isinstance(value, dict):
                self.model.node_graph.update(value)
            elif hasattr(self.model, key):
                setattr(self.model, key, value)


def make_app():
    return PlotSettingsApp()
