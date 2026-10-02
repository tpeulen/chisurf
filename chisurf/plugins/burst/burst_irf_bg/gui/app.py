"""The Burst IRF & Background tool, drawn with emtk.

An immediate-mode emtk application (:class:`BurstIrfBackgroundApp`) over
:class:`~.view_model.IrfBackgroundViewModel`:
- Docking & Draggable Windows: All panels (Parameters & Actions, IRF Plot,
  Results Table) are dockable, draggable, resizable and floatable.
- Interactive Region Dropping & Dragging:
  - On the IRF micro-time plot, interactive baseline threshold (:func:`implot.drag_line_y`)
    and tags allow adjusting the background floor live.
  - Drop targets allow dropping region presets directly onto the plot.
- Compute & Send-to-MLE actions to drive downstream burst-MLE fits.

Runs toolkit-free under :class:`emtk.qt_host.ControlHost` in Qt,
in a desktop window (:mod:`emtk.native`), or in a WebGPU browser page (:mod:`emtk.web`).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.im_core import get_current_context
from emtk.view_form import FormState, draw_sections
from emtk.widgets.view_spec import load_view_spec

from .view_model import IrfBackgroundViewModel

__all__ = ["BurstIrfBackgroundApp", "BurstIrfBackgroundGui", "WINDOW_BG"]

logger = logging.getLogger(__name__)

WINDOW_BG = (30, 32, 38, 255)
PANEL_BG = (38, 41, 48, 255)
PANEL_BORDER = (55, 60, 72, 255)
ACCENT_GREEN = (46, 160, 67, 255)
ACCENT_BLUE = (31, 119, 180, 255)
ACCENT_GRAY = (158, 158, 158, 255)
ACCENT_RED = (214, 39, 40, 255)
REGION_FILL = (46, 117, 182, 60)
REGION_BORDER = (90, 160, 240, 255)


def _hex_to_rgba(col: Any, alpha: int = 255) -> tuple[int, int, int, int]:
    if isinstance(col, (tuple, list)):
        return int(col[0]), int(col[1]), int(col[2]), int(col[3] if len(col) > 3 else alpha)
    c = str(col).lstrip("#")
    if len(c) == 6:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), alpha
    return (100, 150, 240, alpha)


class BurstIrfBackgroundGui:
    """Immediate-mode GUI logic and rendering for Burst IRF & Background."""

    def __init__(
        self,
        model: IrfBackgroundViewModel | None = None,
        on_compute: Callable[[], None] | None = None,
        on_send_to_mle: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.model = model if model is not None else IrfBackgroundViewModel()
        self.on_compute = on_compute
        self.on_send_to_mle = on_send_to_mle
        self.on_guide = on_guide
        self.on_help = on_help
        self.status_text = "Load files, define detectors, then compute."
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        from pathlib import Path

        from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Burst IRF & Background — Help & Reference",
            resource=help_resource,
            owner=self.model,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        # The parameters are the AutoForm spec's own fields (typed, clamped to the ranges it declares) and the results table is a
        # data_table section: hand-drawn drag widgets had no typed entry and applied no drag at all (emtk reports a non-live drag
        # only on release, with the old value), and the table was drawn cell by cell.
        self.form_state = FormState()
        spec = load_view_spec(str(Path(__file__).parent / "irf_bg.view.json"))
        self._fields = self._leaf_sections(spec["sections"][0])
        table = load_view_spec(str(Path(__file__).parent / "irf_bg_results_emtk.view.json"))
        self.results_section = table["sections"][0]
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k) or self.form_state.rects.get(k),
            owner=self.model,
            wait_for_controls=True,
        )
        self.on_used = self.tour.notify_used  # the Extract step waits for Compute
        self.form_state.on_used = self.tour.notify_used

        self.model.add_observer(self._on_model_event)

        from emtk.docking import DockManager, Region, Split

        self.docks = DockManager(
            Split("h", 0.4, Region("controls"), Split("v", 0.6, Region("plot"), Region("results"))),
            name="burst_irf_bg",
        )
        self.docks.add_window(
            "controls", "IRF parameters", lambda box: self._draw_parameters(), dock="controls"
        )
        self.docks.add_window("plot", "IRF decay", lambda box: self._draw_irf_plot(), dock="plot")
        self.docks.add_window(
            "results", "IRF results", lambda box: self._draw_results_table(), dock="results"
        )
        self.docks.add_window(
            "channels", "Channel definition", self._draw_channels, dock="controls"
        )

    @staticmethod
    def _leaf_sections(section: dict) -> dict[str, dict]:
        """Every field of the spec by its attribute name."""
        found: dict[str, dict] = {}
        for child in section.get("sections", []) or []:
            if child.get("attr"):
                found[child["attr"]] = child
            found.update(BurstIrfBackgroundGui._leaf_sections(child))
        return found

    def _sync_binning(self) -> None:
        """The micro-time binning is also the channel editor's ``tttr_reading`` value: keep the two equal."""
        controller = getattr(self, "controller", None)
        if controller is None:
            return
        reading = controller.channel_definition.model.data["tttr_reading"]
        binning = int(self.model.micro_time_binning)
        if int(reading.get("micro_time_binning", 1)) != binning:
            reading["micro_time_binning"] = binning
            controller.channel_definition.model.changed()

    def _draw_channels(self, box):
        controller = getattr(self, "controller", None)
        if controller is not None:
            im.begin_disabled(controller.running)
            controller.channel_definition.draw()
            im.end_disabled()
        else:
            im.text_wrapped("Detector settings are supplied by the embedding host.")

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def _on_model_event(self, event: str) -> None:
        if event == "computed":
            n = len(self.model.results_rows())
            self.status_text = f"Extracted IRF + background for {n} detector(s)."

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def draw(self, w: float, h: float) -> None:
        self.docks.draw((0.0, 0.0, float(w), float(h)))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, float(w), float(h)))

        if self.tour.active:
            if self.tour.awaiting:
                self.tour.draw(float(w), float(h))   # the highlighted control must stay clickable: no overlay window over the docks
            else:
                # In a window of its own, over the docks: drawn into the root window the card's buttons sat under the dock
                # windows (a button is hovered only when no other window is under the pointer), so Close Tour, Prev and
                # most Next presses never arrived.
                flags = (im.WindowFlags.NO_DECORATION | im.WindowFlags.NO_BACKGROUND | im.WindowFlags.NO_SAVED_SETTINGS
                         | im.WindowFlags.NO_MOVE | im.WindowFlags.NO_NAV)
                im.begin("##irf_bg_tour_overlay", (0.0, 0.0, float(w), float(h)), flags)
                self.tour.draw(float(w), float(h))
                im.end()

    def _draw_parameters(self) -> None:
        avail_w = im.get_content_region_avail()[0]
        if getattr(self, "controller", None) is not None:
            self.controller.draw_inputs(remember=self.remember, track=self.track)
            if "bg_channels" in self.item_rects:  # the guide's name for the channel editor button
                self.item_rects["irf_bg_channels"] = self.item_rects["bg_channels"]
        running = bool(getattr(self, "controller", None) and self.controller.running)
        target = self.model
        if running:
            # ``begin_disabled`` greys the spec's fields but they still take typing; they draw against a throw-away copy
            # while a computation runs, so an edit is refused instead of being typed into a run that has its own snapshot.
            import copy

            target = copy.copy(self.model)
            target._observers = []
        im.begin_disabled(running)
        im.text_colored(ACCENT_BLUE, "Burst Search & Baseline")
        draw_sections(
            [self._fields[a] for a in ("min_photons", "photon_window", "time_window_ms", "baseline_quantile",
                                       "micro_time_binning")],
            target, self.form_state,
        )
        if not running:
            self._sync_binning()

        im.spacing()
        im.separator()
        im.spacing()

        im.end_disabled()

        # Actions
        from emtk.im_core import Col

        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button("🌙 Compute", (avail_w, 28.0)):
            self.track("toolAction_run")
            self.track("irf_bg_run")
            if callable(self.on_compute):
                self.on_compute()
            else:
                try:
                    self.model.compute()
                except Exception as exc:
                    self.status_text = f"Error: {exc}"
        self.remember("toolAction_run")
        self.remember("irf_bg_run")
        im.set_item_tooltip(
            "Extract the instrument response (IRF) and the per-detector background rates from the loaded files."
        )
        im.pop_style_color(3)

        im.spacing()
        if im.button("🎯 Send to MLE", (avail_w, 26.0)):
            self.track("send_to_mle")
            if callable(self.on_send_to_mle):
                self.on_send_to_mle()
        self.remember("send_to_mle")
        im.set_item_tooltip(
            "Send the extracted IRF and background patterns to the burst-MLE lifetime fit."
        )

        if getattr(self, "controller", None) is not None:
            if im.button("Export MLE patterns"):
                self.controller.browse("patterns")
            im.set_item_tooltip(
                "Save per-detector IRF and background patterns in a NumPy archive for scripted MLE fitting."
            )

        btn_half_w = max(50.0, (avail_w - 6.0) * 0.5)
        im.spacing()
        if im.button("📖 Guide", (btn_half_w, 24.0)):
            self.track("guide")
            self.start_guide()
        self.remember("guide")
        im.set_item_tooltip("Start a step-by-step guided tour of this tool.")

        im.same_line()
        if im.button("❓ Help", (btn_half_w, 24.0)):
            self.track("help")
            self.show_help()
        self.remember("help")
        im.set_item_tooltip("Open the help window with reference documentation.")

        im.spacing()
        im.text_colored(ACCENT_GRAY, f"Files loaded: {len(self.model.files)}")
        im.spacing()
        # The tool's own line (the extraction result); the controller's messages are drawn
        # with the inputs -- showing them here too doubled every one.
        im.text_wrapped(self.status_text)

    def _draw_irf_plot(self) -> None:
        avail_w, avail_h = im.get_content_region_avail()
        origin = im.get_cursor_screen_pos()
        plot_w = max(avail_w, 150.0)
        plot_h = max(avail_h - 10.0, 150.0)

        series = self.model.irf_series()
        if not series:
            im.text_disabled(
                "No IRF data available. Load TTTR files, define detectors, and compute."
            )
            return

        if implot.begin_plot("IRF (non-burst scatter)##irf_plot", (plot_w, plot_h)):
            implot.setup_axes("Micro time (ns)", "IRF (normalised)")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)

            for s in series:
                x = np.asarray(s.get("x", []), dtype=float)
                y = np.asarray(s.get("y", []), dtype=float)
                if len(x) == 0 or len(y) == 0:
                    continue
                col = _hex_to_rgba(s.get("color", ACCENT_BLUE))
                name = s.get("name", "IRF")
                implot.set_next_line_style(col, float(s.get("width", 2.0)))
                # Only plot positive values for log scale
                pos_mask = y > 0
                if np.any(pos_mask):
                    implot.plot_line(name, x[pos_mask], y[pos_mask])

            implot.end_plot()

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(
                        payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
                    )
                    if "min" in data:
                        self.model.baseline_quantile = min(0.9, max(0.0, float(data["min"])))
                except Exception:
                    pass
            im.end_drag_drop_target()

        self.remember("irf_series", (origin[0], origin[1], plot_w, plot_h))
        self.remember("IRF (non-burst scatter)", (origin[0], origin[1], plot_w, plot_h))

    def _draw_results_table(self) -> None:
        avail_w, avail_h = im.get_content_region_avail()
        rx, ry = im.get_cursor_screen_pos()
        self.remember("irf_bg_results", (rx, ry, avail_w, avail_h))
        draw_sections([self.results_section], self.model, self.form_state)


class BurstIrfBackgroundApp(ImApp):
    """Immediate-mode EMTK application for Burst IRF & Background."""

    def __init__(
        self,
        model: IrfBackgroundViewModel | None = None,
        on_compute: Callable[[], None] | None = None,
        on_send_to_mle: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
        mle_receiver=None,
    ) -> None:
        self.controller = None
        if on_compute is None:
            from .controller import IrfBackgroundController

            model = model if model is not None else IrfBackgroundViewModel()
            self.controller = IrfBackgroundController(model, mle_receiver=mle_receiver)
            on_compute = self.controller.run
            on_send_to_mle = on_send_to_mle or self.controller.send_to_mle
        self.irf_gui = BurstIrfBackgroundGui(
            model=model,
            on_compute=on_compute,
            on_send_to_mle=on_send_to_mle,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.model = self.irf_gui.model
        self.item_rects = self.irf_gui.item_rects
        self.irf_gui.remember = self.remember
        self.irf_gui.controller = self.controller
        if self.controller is not None:
            self.controller.on_show_channels = lambda: self.irf_gui.docks.focus("channels")
        super().__init__(gui=self._render)

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.irf_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.irf_gui.show_help()

    def _render(self) -> None:
        if self.controller is not None:
            self.controller.poll()
            if self.controller.running or self.controller.channel_definition._future is not None:
                ctx = get_current_context()  # look again in 0.1 s while a worker runs
                ctx.request_frame_at(ctx.io.now + 0.1)
        w, h = im.get_main_viewport().size
        self.irf_gui.draw(w, h)
        if self.controller is not None:
            self.controller.draw_dialogs((0, 0, w, h))

    def close(self):
        if self.controller is not None:
            self.controller.close()

    def on_paths_dropped(self, paths):
        if self.controller is not None:
            self.controller.on_paths_dropped(paths)

    def files_dropped(self, paths) -> bool:
        """A host's file drop (Qt, the desktop window, a page): the same as ``on_paths_dropped``.

        Without this name only the Qt host reached the controller: the desktop and web hosts deliver ``files_dropped`` /
        ``on_files_dropped`` and found nothing to call.
        """
        paths = list(paths)
        self.on_paths_dropped(paths)
        return bool(paths) and self.controller is not None


def create_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return BurstIrfBackgroundApp(**kwargs)
