"""Native emtk plot settings editor (Qt-free), at parity with the Qt tool.

The form -- the five collapsible sections of the Qt tool, the Apply / Save /
Reset bar and the status line -- is the view spec ``plot_settings_emtk.view.json``
drawn by :func:`emtk.view_form.draw_sections`. Only what a spec cannot express is
drawn here: the Help / Guide buttons and the **preview**, an ``emtk.implot`` plot
of three *sample* curves (data, model, IRF) that previews the styling and follows
every pending edit. All state and work is in :class:`~.model.PlotSettingsModel`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im, implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow

from .model import PlotSettingsModel, color_rgb

HERE = Path(__file__).parent

_SETTINGS, _ACTIONS, _PREVIEW = "settings", "actions", "preview"

#: Colours of the axis furniture by the pyqtgraph foreground letter.
_FOREGROUND = {"d": (200, 200, 200), "w": (255, 255, 255), "l": (220, 220, 220), "k": (0, 0, 0)}
#: The dashed model curve of the Qt preview: pixels on / off.
_DASH = (8.0, 5.0)


class PlotSettingsApp(ImApp):
    """Edit the plot appearance settings and preview them."""

    def __init__(self, model: PlotSettingsModel | None = None) -> None:
        self.model = model or PlotSettingsModel()
        spec = json.loads((HERE / "plot_settings_emtk.view.json").read_text(encoding="utf-8"))
        self.panels = {p["name"]: p for p in spec["sections"]}
        self.form = FormState()
        self.form.custom["preview_plot"] = self._draw_preview
        self.item_rects: dict[str, tuple] = {}
        #: What the preview submitted on the last frame, one row per series.
        self.preview_drawn: list[dict[str, Any]] = []
        self.help_window = EmTkHelpWindow(
            title="Plot Settings — Help", resource=HERE / "help.md", owner=self
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.form.on_used = self.tour.notify_used
        # Settings above, the Apply / Save / Reset bar under them (as in the Qt tool), the
        # preview below. The bar is a window of its own and the form scrolls with its window:
        # a scrolling child inside one window lets the clipped rows under its bottom edge take
        # the clicks meant for the buttons below it.
        self.docks = DockManager(
            Split(
                "v", 0.64, Split("v", 0.8, Region("settings"), Region("actions")), Region("preview")
            )
        )
        self.docks.add_window(
            "settings", "Plot Settings", self.draw_settings, dock="settings", closable=False
        )
        self.docks.add_window(
            "actions", "Apply / Save / Reset", self.draw_actions, dock="actions", closable=False
        )
        self.docks.add_window(
            "preview",
            "Preview (sample curves)",
            self.draw_preview_window,
            dock="preview",
            closable=False,
        )
        super().__init__(self.render)

    # ── one frame ──────────────────────────────────────────────────────
    def render(self) -> None:
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self.docks.draw(box)
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    # ── windows ────────────────────────────────────────────────────────
    def draw_settings(self, box: Any) -> None:
        """The settings window: Help / Guide and the folding sections."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Explain the sections, Apply, Save and Reset.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through changing a colour and applying it.")
        self.item_rects["guide"] = im.get_item_rect()
        draw_sections(self.panels[_SETTINGS]["sections"], self.model, self.form, titles=False)

    def draw_actions(self, box: Any) -> None:
        """The Apply / Save / Reset bar and the status line."""
        draw_sections(self.panels[_ACTIONS]["sections"], self.model, self.form, titles=False)

    def draw_preview_window(self, box: Any) -> None:
        """The docked preview window."""
        draw_sections(self.panels[_PREVIEW]["sections"], self.model, self.form, titles=False)

    # ── the preview plot ───────────────────────────────────────────────
    def _draw_preview(
        self, section: dict, model: PlotSettingsModel, state: FormState, width: float
    ) -> None:
        """The ``preview_plot`` custom section: sample data / model / IRF curves."""
        dark = model.preview_dark
        background = (0, 0, 0, 255) if dark else (255, 255, 255, 255)
        foreground = _FOREGROUND.get(model.pg_foreground, (200, 200, 200) if dark else (60, 60, 60))
        axis = (*foreground, 255)
        grid_alpha = int(round(255 * model.grid_alpha_pct / 100.0))
        pushed = [
            (implot.COL_FRAME_BG, background),
            (implot.COL_PLOT_BG, background),
            (implot.COL_AXIS_TEXT, axis),
            (implot.COL_AXIS_TICK, axis),
            (implot.COL_PLOT_BORDER, (*foreground, 120)),
            (implot.COL_LEGEND_TEXT, axis),
            (implot.COL_AXIS_GRID, (*foreground, grid_alpha)),
        ]
        for index, colour in pushed:
            implot.push_style_color(index, colour)
        avail = im.get_content_region_avail()
        flags = implot.FLAGS_NO_TITLE | (0 if model.show_legend else implot.FLAGS_NO_LEGEND)
        grid_flag = 0 if model.preview_grid else implot.AXIS_FLAGS_NO_GRID_LINES
        self.preview_drawn = []
        shown = implot.begin_plot(
            "##plot_settings_preview", (-1.0, max(float(avail[1]), 90.0)), flags
        )
        if shown:
            x_label = "t / ns" if model.label_axis else ""
            y_label = "counts" if model.label_axis else ""
            implot.setup_axes(x_label, y_label, grid_flag, grid_flag)
            implot.setup_axis_limits(implot.AXIS_X1, 0.0, 10.0, implot.COND_ONCE)
            # The sample curves span 2 .. 1200 counts: fixed limits keep the baseline above the frame.
            implot.setup_axis_limits(implot.AXIS_Y1, 1.0, 2000.0, implot.COND_ONCE)
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            for series in model.preview_series():
                rgb = color_rgb(series["color"])
                kwargs = {"line_color": (*rgb, 255), "line_weight": float(series["width"])}
                if series["dash"]:
                    kwargs["dash"] = _DASH
                implot.plot_line(series["label"], series["x"], series["y"], **kwargs)
                self.preview_drawn.append(
                    {
                        "label": series["label"],
                        "color": "#%02x%02x%02x" % rgb,
                        "width": float(series["width"]),
                        "dash": bool(series["dash"]),
                        "points": len(series["x"]),
                    }
                )
            implot.end_plot()
        implot.pop_style_color(len(pushed))
        self.item_rects["preview_plot"] = im.get_item_rect()
        state.rects["preview_plot"] = im.get_item_rect()

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """What the window remembers: which sections are folded (the settings live in the settings file)."""
        return {"folds": dict(self.form.folds)}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`."""
        folds = settings.get("folds", {})
        if isinstance(folds, dict):
            self.form.folds.update({str(k): bool(v) for k, v in folds.items()})

    def close(self) -> None:
        """Nothing to release."""


def make_app() -> PlotSettingsApp:
    """Build the plot settings app (the manifest's ``entrypoints.emtk``)."""
    return PlotSettingsApp()
