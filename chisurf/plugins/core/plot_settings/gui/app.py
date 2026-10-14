"""Settings ▸ Plots: how every fit plot looks, with a live preview (emtk, Qt-free).

The controls are ``plot_settings_emtk.view.json`` drawn by
:func:`emtk.view_form.draw_sections` over :class:`~.model.PlotSettingsModel`;
every change applies at once and is saved once the mouse is released, as in
Settings ▸ Fonts. Only the **preview** is drawn here -- a plot is not something
a spec can express: a simulated measurement and its fit, stacked like a fit
window (autocorrelation, weighted residuals, data), styled by the settings.

Wide windows put the controls in a scrolling column beside the preview;
narrow ones put the preview on top.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im, implot, style
from emtk.app import ImApp
from emtk.view_form import FormState, draw_sections

from chisurf.core.plotting import appearance
from chisurf.core.support.i18n import tr
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.plugins.emtk_layout import action_button, window_size

from .model import PlotSettingsModel

HERE = Path(__file__).parent
VIEW_JSON = HERE / "plot_settings_emtk.view.json"

#: Below this width the preview goes above the controls instead of beside them.
_SIDE_BY_SIDE_MIN_WIDTH = 620.0
#: Width share and bounds of the controls column when side by side.
_COLUMN_SHARE, _COLUMN_MIN, _COLUMN_MAX = 0.42, 320.0, 520.0
#: Height shares of the preview's panels, as a fit window stacks them.
_PANEL_SHARES = (("acorr", 0.2), ("residuals", 0.22), ("data", 0.58))


def _legend_label(label: str) -> str:
    """A preview series' legend entry in the interface language."""
    labels = {
        "data": tr("data"),
        "model": tr("model"),
        "IRF": tr("IRF"),
        "other fit": tr("other fit"),
        "w.res.": tr("w.res."),
        "a.corr.": tr("a.corr."),
    }
    return labels.get(label, label)


def _rgba(color: str, opacity: float = 1.0) -> tuple[int, int, int, int]:
    """A stored colour at *opacity*, as implot takes it."""
    return (*appearance.hex_rgb(color), int(round(255 * min(max(opacity, 0.0), 1.0))))


class PlotSettingsApp(ImApp):
    """Edit the plot appearance settings and preview them."""

    def __init__(self, model: PlotSettingsModel | None = None) -> None:
        self.model = model or PlotSettingsModel()
        self.spec = json.loads(VIEW_JSON.read_text(encoding="utf-8"))
        self.window_size = window_size(self.spec, (1200, 800))
        self.panels = {p["name"]: p for p in self.spec["sections"]}
        self.form = FormState()
        self.form.custom["preview_plot"] = self._draw_preview
        self.item_rects: dict[str, tuple] = {}
        #: What the preview submitted on the last frame, one row per series.
        self.preview_drawn: list[dict[str, Any]] = []
        #: The preview's panels on the last frame: panel -> grid alpha, axis names, legend.
        self.preview_panels: dict[str, dict[str, Any]] = {}
        #: The preview's shared time axis ``[min, max]`` (linked by all three panels).
        self._x_link: list[float] | None = None
        #: Factor the preview text was drawn at (the axis text size over the interface size).
        self.preview_scale = 1.0
        self.help_window = EmTkHelpWindow(
            title="Plot Settings — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=self.target_rect,
        )
        self.form.on_used = self.tour.notify_used
        super().__init__(self.render)

    def target_rect(self, key: str):
        """Where control *key* was drawn: a slider row registers its slider and its field."""
        for name in (key, f"{key}.slider", f"{key}.edit"):
            rect = self.item_rects.get(name) or self.form.rects.get(name)
            if rect:
                return rect
        return None

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        """Help / Guide, the controls and the preview, the help window and the tour."""
        vp = im.get_main_viewport()
        self.form.rects.clear()
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size(vp.size, im.Cond.ALWAYS)
        if im.begin("Plot Settings##plot_settings", flags=im.WindowFlags.NO_RESIZE):
            if action_button("help"):
                self.help_window.show()
            self.item_rects["help"] = im.get_item_rect()
            im.same_line()
            if action_button("guide"):
                self.tour.start()
            self.item_rects["guide"] = im.get_item_rect()
            avail_w, avail_h = (float(v) for v in im.get_content_region_avail())
            if avail_w >= _SIDE_BY_SIDE_MIN_WIDTH:
                column = min(max(avail_w * _COLUMN_SHARE, _COLUMN_MIN), _COLUMN_MAX)
                self._settings_child((column, avail_h))
                im.same_line()
                self._preview_child((max(avail_w - column - 8.0, 120.0), avail_h))
            else:
                preview_h = max(avail_h * 0.5, 180.0)
                self._preview_child((avail_w, preview_h))
                self._settings_child((avail_w, max(avail_h - preview_h - 6.0, 80.0)))
        im.end()
        # Keep the change once the hand is off the control: not on every frame of a drag.
        if self.model.unsaved and not im.is_mouse_down(0):
            self.model.flush()
        box = (*vp.pos, *vp.size)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _settings_child(self, size: tuple[float, float]) -> None:
        """The scrolling column of controls."""
        im.begin_child("##plot_settings_body", size)
        draw_sections(self.panels["settings"]["sections"], self.model, self.form, titles=True)
        self.item_rects["settings"] = im.end_child()

    def _preview_child(self, size: tuple[float, float]) -> None:
        """The preview, filling its box."""
        im.begin_child("##plot_settings_preview", size, scrollable=False)
        draw_sections(self.panels["preview"]["sections"], self.model, self.form, titles=False)
        im.end_child()

    # ── the preview plot ───────────────────────────────────────────────
    def _draw_preview(
        self, section: dict, model: PlotSettingsModel, state: FormState, width: float
    ) -> None:
        """The ``preview_plot`` custom section: a fit window's three panels on sample data."""
        preview = model.preview()
        curves = preview["curves"]
        (lo, hi), band = preview["region"]
        avail_h = max(float(im.get_content_region_avail()[1]), 180.0)
        x_limits = (0.0, float(curves["data"][0]["x"][-1]))
        names = {"acorr": tr("a.corr."), "residuals": tr("w.res."), "data": tr("counts")}
        scale = 1.0
        if preview["font_size"] > 0:
            from emtk import fonts

            scale = preview["font_size"] / max(float(fonts.role_size_pt("ui")), 1.0)
            im.push_font_scale(scale)
        self.preview_drawn = []
        self.preview_panels = {}
        top = None
        implot.begin_aligned_plots("##plot_settings_aligned")
        for panel, share in _PANEL_SHARES:
            grid = preview["grid"][panel]
            grid_flags = 0 if grid is not None else implot.AXIS_FLAGS_NO_GRID_LINES
            strength = appearance.grid_strength(grid) if grid is not None else 0.0
            theme_grid = style.PLOT_GRID  # the theme's grid line (emtk.theme), at the strength set
            grid_rgba = (*theme_grid[:3], min(255, int(round(theme_grid[3] * strength))))
            legend = panel == "data" and preview["legend"]
            flags = implot.FLAGS_NO_TITLE | implot.FLAGS_NO_MENUS
            flags |= 0 if legend else implot.FLAGS_NO_LEGEND
            implot.push_style_color(implot.COL_AXIS_GRID, grid_rgba)
            x_label = tr("time / ns") if preview["labels"] and panel == "data" else ""
            y_label = names[panel] if preview["labels"] else ""
            shown = implot.begin_plot(f"##preview_{panel}", (-1.0, avail_h * share - 4.0), flags)
            if shown:
                x_flags = grid_flags | (0 if panel == "data" else implot.AXIS_FLAGS_NO_TICK_LABELS)
                implot.setup_axes(x_label, y_label, x_flags, grid_flags)
                # One time axis for the three panels: a zoom or pan in one moves all.
                if self._x_link is None:
                    self._x_link = list(x_limits)
                implot.setup_axis_links(implot.AXIS_X1, self._x_link)
                if panel == "data":
                    implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
                    peak = max(float(max(c["y"])) for c in curves["data"])
                    implot.setup_axis_limits(implot.AXIS_Y1, 1.0, peak * 2.0, implot.COND_ONCE)
                    implot.setup_legend(implot.LOCATION_NORTH_EAST)
                    if band is not None:
                        rgb = band[:3]
                        implot.plot_shaded(
                            "##fit range",
                            [lo, hi],
                            [peak * 1e3] * 2,
                            yref=float("-inf"),
                            fill_color=(*rgb, int(band[3])),
                        )
                        implot.plot_inf_lines("##fit range edges", [lo, hi], line_color=(*rgb, 220))
                for series in curves[panel]:
                    colour = _rgba(series["color"], series["opacity"])
                    implot.plot_line(
                        _legend_label(series["label"]),
                        series["x"],
                        series["y"],
                        line_color=colour,
                        line_weight=float(series["width"]),
                    )
                    self.preview_drawn.append(
                        {
                            "panel": panel,
                            "label": series["label"],
                            "color": "#%02x%02x%02x" % colour[:3],
                            "alpha": colour[3],
                            "width": float(series["width"]),
                            "points": len(series["x"]),
                        }
                    )
                rect = (*implot.get_plot_pos(), *implot.get_plot_size())
                implot.end_plot()
            else:
                rect = tuple(im.get_item_rect())
            implot.pop_style_color(1)
            top = rect if top is None else top
            self.preview_panels[panel] = {
                "grid": None if grid is None else grid_rgba[3],
                "labels": (x_label, y_label) if shown else ("", ""),
                "legend": legend,
                "rect": tuple(rect),
                "band": band if panel == "data" else None,
            }
        implot.end_aligned_plots()
        if scale != 1.0:
            im.pop_font_scale()
        description = section.get("description")
        if description:
            im.set_item_tooltip(str(description))
        bottom = self.preview_panels["data"]["rect"]
        assert top is not None  # the loop drew at least one panel
        whole = (top[0], top[1], bottom[0] + bottom[2] - top[0], bottom[1] + bottom[3] - top[1])
        self.item_rects["preview_plot"] = whole
        state.rects["preview_plot"] = whole
        self.preview_scale = scale

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """What the window remembers: which sections are folded (the settings live in the settings file)."""
        return {"folds": dict(self.form.folds)}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        folds = settings.get("folds", {}) if isinstance(settings, dict) else {}
        if isinstance(folds, dict):
            self.form.folds.update({str(k): bool(v) for k, v in folds.items()})

    def close(self) -> None:
        """Keep a change made in the last frame."""
        self.model.flush()


def make_app() -> PlotSettingsApp:
    """Build the plot settings app (the manifest's ``entrypoints.emtk``)."""
    return PlotSettingsApp()


__all__ = ["PlotSettingsApp", "make_app"]
