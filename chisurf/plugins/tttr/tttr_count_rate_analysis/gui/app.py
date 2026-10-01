"""EMTK immediate-mode UI for the Count Rate Analysis tool.

Left: the TTTR file queue (add/clear) and the detector-channel source — a
saved detector setup from the canonical store, converted into the channel
definition the model computes with. Right: the count-rate-vs-file plot and
the per-channel results table, with the Calculate / Save actions. The widget
(:class:`~.tool.CountRateAnalyzer`) keeps the Qt-free
:class:`~..view_model.CountRateViewModel` and injects the channels provider;
this app renders its state.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import emtk.im as im
import emtk.implot as implot
import numpy as np
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_form

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

if TYPE_CHECKING:
    from .tool import CountRateAnalyzer

WINDOW_BG = (30, 32, 38, 255)

#: The results table, declared (the Qt tool's Results tab, same columns).
RESULTS_TABLE = {
    "sections": [{
        "type": "custom",
        "key": "data_table",
        "description": "One row per detector channel, summed over every queued file.",
        "options": {
            "source": "results_rows",
            "editable": False,
            "expand": True,
            "columns": [
                {"key": "channel", "title": "Channel", "description": "Channel of the detector setup."},
                {"key": "mean_khz", "title": "Mean (kHz)", "format": "%.2f",
                 "description": "Mean count rate over the files."},
                {"key": "std_khz", "title": "Std (kHz)", "format": "%.2f",
                 "description": "Standard deviation of the count rate between files."},
                {"key": "photons", "title": "#Photons", "format": "%.0f",
                 "description": "Photons of this channel in all files."},
                {"key": "time_s", "title": "Time (s)", "format": "%.3f",
                 "description": "Total measurement time of the files."},
            ],
        },
    }]
}


def setup_to_channels(setup: dict) -> dict:
    """Convert a saved detector setup into the model's channel-definition map.

    One entry per detector of the setup, each gating its routing channels by
    the detector's micro-time windows — the shape
    :meth:`CountRateViewModel.compute` consumes.
    """
    if setup.get("channels") and not setup.get("detectors"):
        from copy import deepcopy

        return deepcopy(setup["channels"])
    channels: dict = {}
    windows = setup.get("windows") or {"": None}
    for window_name, window in windows.items():
        for name, detector in (setup.get("detectors") or {}).items():
            infos = []
            for gate in detector.get("micro_time_ranges") or [None]:
                info = {
                    "detector_chs": list(detector.get("chs") or []),
                    "micro_time_range": gate,
                    "window_range": window,
                }
                infos.append(info)
            channels[f"{window_name}_{name}" if window_name else name] = infos
    return channels


class CountRateGui(TourTarget):
    """EMTK GUI for the count-rate analysis."""

    def __init__(
        self,
        tool: CountRateAnalyzer,
        on_calculate: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
        on_add_files: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_calculate = on_calculate
        self.on_save = on_save
        self.on_add_files = on_add_files
        self.on_clear = on_clear
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.plot_signature = None
        self.selected_file: str | None = None
        self.results_form = FormState()

        layout = Split(
            "h",
            0.34,
            Split("v", 0.55, Region("files"), Region("channels")),
            Split("v", 0.52, Region("plot"), Region("results")),
        )
        self.docks = DockManager(layout)
        self.docks.add_window("files", "TTTR files", self._draw_files, dock="files", closable=True)
        self.docks.add_window(
            "channels",
            "Detector channels",
            self._draw_channels,
            dock="channels",
            closable=True,
        )
        self.docks.add_window(
            "plot", "Count rate per file", self._draw_plot, dock="plot", closable=True
        )
        self.docks.add_window(
            "results",
            "Results per channel",
            self._draw_results,
            dock="results",
            closable=True,
        )

        self.help_window = EmTkHelpWindow(
            title="Count Rate Analysis — Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).parent / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=tool,
        )

    # ── plumbing ──────────────────────────────────────────────────────────

    @property
    def model(self):
        return self.tool._model

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()


    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 900.0)
        height = float(h or vp.size[1] or 620.0)
        self.docks.draw((0.0, 0.0, width, height))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    def busy(self):
        job = getattr(self.tool, "job", None)
        picker = getattr(self.tool, "dataset_picker", None)
        return bool(
            (job is not None and job.running)
            or (picker is not None and picker.is_open)
            or getattr(self.tool, "dialog", None) is not None
        )

    def draw_status(self):
        message = getattr(self.tool, "message", "")
        if message:
            im.text_wrapped(message)
        job = getattr(self.tool, "job", None)
        if job is not None and job.running:
            current, count = self.tool.progress
            im.text(f"{current}/{count} files")
            if im.button("Stop analysis"):
                job.stop()
                self.tool.message = "Stopped analysis; incomplete results will be discarded."
            im.set_item_tooltip(
                "Stop between file reads and discard incomplete computation results."
            )

    # ── files ─────────────────────────────────────────────────────────────

    def _draw_files(self, box: tuple[float, float, float, float]) -> None:
        im.begin_disabled(self.busy())
        if im.button("Add files"):
            if callable(self.on_add_files):
                self.on_add_files()
        im.set_item_tooltip("Queue TTTR files (.ptu, .ht3, .spc, …) for the analysis.")
        self.remember("add_files")
        if im.get_line_avail() >= im.calc_text_size("Clear")[0] + 24:
            im.same_line()
        if im.button("Clear"):
            if callable(self.on_clear):
                self.on_clear()
        im.set_item_tooltip("Drop the file queue and any computed results.")
        self.remember("clear")
        if im.get_line_avail() >= im.calc_text_size("Help")[0] + 24:
            im.same_line()
        if im.button("Help"):
            self.show_help()
        im.set_item_tooltip("The short help page.")
        self.remember("help")
        if im.button("Guide"):
            self.start_guide()
        im.set_item_tooltip("Walk through inputs, detector gates, calculation and export.")
        self.remember("guide")
        im.separator()

        for label, callback, tip in (
            (
                "Folder…",
                getattr(self.tool, "add_folder_dialog", None),
                "Queue supported TTTR files recursively from a folder.",
            ),
            (
                "Database…",
                getattr(self.tool, "add_database", None),
                "Select TTTR datasets from MMFDB.",
            ),
        ):
            if callable(callback):
                if im.button(label):
                    callback()
                im.set_item_tooltip(tip)
        files = self.model.files
        if not files:
            im.text_disabled("No files queued.")
            im.end_disabled()
            self.draw_status()
            return
        if self.selected_file not in files:
            self.selected_file = None
        im.begin_disabled(self.selected_file is None)
        if im.button("Remove"):
            self.remove_file(self.selected_file)
        im.set_item_tooltip("Remove the selected file from the queue (it stays on disk).")
        im.end_disabled()
        self.remember("remove")
        for i, path in enumerate(list(files)):
            if im.selectable(f"{Path(path).name}##file{i}", path == self.selected_file):
                self.selected_file = path
            im.set_item_tooltip(f"{path} — click to select, right-click to remove from the queue.")
            if im.begin_popup_context_item(f"file-menu{i}"):
                if im.menu_item("Remove from queue"):
                    self.remove_file(path)
                im.set_item_tooltip("Remove this input without deleting it from disk.")
                im.end_popup()
        self.remember("file_list")
        im.end_disabled()
        self.draw_status()

    def remove_file(self, path) -> None:
        """Take *path* off the queue and refresh, as the Qt list's Remove does."""
        if path in self.model.files:
            self.model.files.remove(path)
            self.model.update()
        if self.selected_file == path:
            self.selected_file = None

    # ── the channel source ────────────────────────────────────────────────

    def _draw_channels(self, box: tuple[float, float, float, float]) -> None:
        im.begin_disabled(self.busy())
        tool = self.tool
        editor = getattr(tool, "channel_editor", None)
        if editor is not None:
            editor.draw()
            im.end_disabled()
            self.remember("setup_source")
            return
        refresh = getattr(tool, "refresh_setups", None)
        if callable(refresh):
            if im.button("Refresh saved setups"):
                refresh()
            im.set_item_tooltip("Read authoritative Detector Definition setups from MMFDB or JSON.")
        editor = getattr(tool, "edit_setup", None)
        if callable(editor):
            if im.button("Edit detector setup…"):
                editor()
            im.set_item_tooltip("Edit routing channels, detector gates and excitation windows.")
        browse = getattr(tool, "browse_setups", None)
        if callable(browse):
            if im.button("Open setup library…"):
                browse()
            im.set_item_tooltip("Read detector definitions from another setup library JSON file.")
        setups = tool.available_setups()
        names = list(setups.keys())
        if tool.selected_setup not in names:
            tool.selected_setup = names[0] if names else ""

        im.text("Detector setup:")
        im.same_line()
        if not names:
            im.text_disabled(
                "none saved"
                if getattr(tool, "setups_ready", True)
                else "not loaded — press Refresh"
            )
            im.set_item_tooltip(
                "No detector setups are saved yet — define one in the "
                "Detector Configuration wizard and it appears here."
            )
            im.end_disabled()
            return
        idx = names.index(tool.selected_setup) if tool.selected_setup in names else 0
        im.set_next_item_width(-1.0)
        changed, new_idx = im.combo("##setup_source", idx, names)
        im.set_item_tooltip(
            "The saved detector setup whose detectors and micro-time windows "
            "define the channels this analysis reports."
        )
        if changed and 0 <= new_idx < len(names):
            tool.selected_setup = names[new_idx]
        self.remember("setup_source")

        channels = tool.channels()
        im.spacing()
        im.text_colored(f"{len(channels)} channels defined", (0.4, 0.85, 0.5, 1.0))
        im.set_item_tooltip("The channel names the results table and plot will report.")
        for cname in channels:
            det = channels[cname]
            chs = ", ".join(
                ",".join(str(c) for c in info.get("detector_chs") or []) for info in det
            )
            im.bullet_text(f"{cname}  ·  chs {chs}")
        self.remember("channel_list")
        im.end_disabled()

    # ── the plot ──────────────────────────────────────────────────────────

    def _draw_plot(self, box: tuple[float, float, float, float]) -> None:
        if implot.begin_plot("##count_rate", (-1, -1)):
            implot.setup_axes("file #", "count rate (kHz)")
            implot.setup_legend()
            series = [
                item
                for item in self.model.count_rate_series()
                if len(item.get("x", [])) and len(item.get("y", []))
            ]
            if series:
                peak = max(float(np.max(item["y"])) for item in series if len(item["y"]))
                count = max(len(item["x"]) for item in series)
                signature = (id(self.model._per_file), count, peak)
                padding = max(peak * 0.06, 1e-4)
                implot.setup_axes_limits(
                    -0.5,
                    max(0.5, count - 0.5),
                    -padding,
                    peak + padding,
                    cond=implot.COND_ALWAYS
                    if signature != self.plot_signature
                    else implot.COND_ONCE,
                )
                self.plot_signature = signature
                for s in series:
                    x = np.asarray(s.get("x", []), dtype=float)
                    y = np.asarray(s.get("y", []), dtype=float)
                    if not len(x):
                        continue
                    colour = s.get("color", "#888888")
                    if isinstance(colour, str):
                        colour = tuple(
                            int(colour.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)
                        ) + (255,)
                    implot.set_next_line_style(colour, float(s.get("width", 1.0)))
                    implot.plot_line(s.get("name") or "channel", x, y)
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 5.0, colour)
                    implot.plot_scatter(f"##pts_{s.get('name', 'ch')}", x, y)
            else:
                implot.plot_dummy("press Calculate to draw the count rates")
            implot.end_plot()
        im.set_item_tooltip("Count rate per channel (kHz), one series per detector.")
        self.remember("plot")

    # ── results ───────────────────────────────────────────────────────────

    def _draw_results(self, box: tuple[float, float, float, float]) -> None:
        m = self.model

        im.begin_disabled(self.busy())
        if im.button("Calculate"):
            if callable(self.on_calculate):
                self.on_calculate()
        im.set_item_tooltip("Compute count rates for all queued files.")
        self.remember("calculate")
        im.same_line()
        if im.button("Save"):
            if callable(self.on_save):
                self.on_save()
        im.set_item_tooltip("Save the results table as tab-separated text.")
        self.remember("save")
        im.end_disabled()
        im.separator()

        rows = m.results_rows()
        if not rows:
            im.text_disabled("No results yet — press Calculate.")
            return
        draw_form(RESULTS_TABLE, m, self.results_form)
        self.remember("results")


class CountRateApp(ImApp):
    """The EMTK ImApp for the count-rate analysis."""

    def __init__(
        self,
        tool: CountRateAnalyzer,
        on_calculate: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
        on_add_files: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.count_rate_gui = CountRateGui(
            tool,
            on_calculate=on_calculate,
            on_save=on_save,
            on_add_files=on_add_files,
            on_clear=on_clear,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.count_rate_gui.item_rects

    def start_guide(self) -> None:
        self.count_rate_gui.start_guide()

    def show_help(self) -> None:
        self.count_rate_gui.show_help()

    def _render(self) -> None:
        self.count_rate_gui.draw()


__all__ = ["CountRateApp", "WINDOW_BG", "setup_to_channels"]
