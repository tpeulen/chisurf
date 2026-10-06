"""EMTK immediate-mode UI for the TTTR → time-window BIDs tool.

Left: the file queue (buttons + the drop hint; OS drops land on the Qt window
and are routed to :meth:`TTTRTimeWindowTool.on_paths_dropped`) and the split
settings — time-window duration and output folder. Right: the intensity-trace
preview with the time-window boundaries as dashed vertical lines, and the
processing log. The tool (:class:`~.tool.TTTRTimeWindowTool`) keeps the client,
the processing and the file-list state; this app renders and calls back.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import emtk.im as im
import emtk.implot as implot
import numpy as np
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

if TYPE_CHECKING:
    from .tool import TTTRTimeWindowTool

WINDOW_BG = (30, 32, 38, 255)
#: More boundaries than this are not drawn (they would only cover the trace).
MAX_BOUNDARY_LINES = 300
ACCENT_RED = (214, 80, 80, 255)
BOUNDARY_COLOUR = (220, 220, 220, 180)


#: The time-window duration, as a form field (typed, clamped to the Qt spin box's range).
TIME_WINDOW_FIELD = [
    {
        "type": "value",
        "attr": "time_window_ms",
        "label": "Time window (ms)",
        "kind": "float",
        "minimum": 0.001,
        "maximum": 3_600_000.0,
        "decimals": 3,
        "step": 1.0,
        "style": "spin",
        "call": "on_time_window",
        "description": (
            "Duration of each time window in milliseconds. Smaller values give more windows with "
            "fewer photons each; the preview's dashed lines follow."
        ),
    }
]


class TimeWindowGui(TourTarget):
    """EMTK GUI for the TTTR time-window tool."""

    def __init__(
        self,
        tool: TTTRTimeWindowTool,
        on_process: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        on_browse: Callable[[], None] | None = None,
        on_add_files: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_process = on_process
        self.on_clear = on_clear
        self.on_browse = on_browse
        self.on_add_files = on_add_files
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.form = FormState()
        #: Index of the queued file shown in the preview (-1 = none).
        self.preview_index: int = -1
        #: The preview data the plot draws: set by the tool on load.
        self.preview: dict | None = None

        layout = Split(
            "h",
            0.36,
            Split("v", 0.58, Region("files"), Region("settings")),
            Split("v", 0.62, Region("preview"), Region("summary")),
        )
        self.docks = DockManager(layout)
        self.docks.add_window("files", "TTTR files", self._draw_files, dock="files", closable=True)
        self.docks.add_window(
            "settings", "Settings", self._draw_settings, dock="settings", closable=True
        )
        self.docks.add_window(
            "preview",
            "Intensity trace preview",
            self._draw_preview,
            dock="preview",
            closable=True,
        )
        self.docks.add_window(
            "summary", "Processing log", self._draw_summary, dock="summary", closable=True
        )

        self.help_window = EmTkHelpWindow(
            title="TTTR Time-Window BIDs — Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(700.0, 560.0),
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).parent / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=tool,
            wait_for_controls=True,
        )

    # ── plumbing ──────────────────────────────────────────────────────────

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def _used(self, name: str) -> None:
        """Tell the tour that the user used the control it is waiting for."""
        self.tour.notify_used(name)

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 1000.0)
        height = float(h or vp.size[1] or 700.0)
        self.docks.draw((0.0, 0.0, width, height))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # ── the file queue ────────────────────────────────────────────────────

    def _draw_files(self, box: tuple[float, float, float, float]) -> None:
        if im.button("Files"):
            self._used("add_files")
            if callable(self.on_add_files):
                self.on_add_files()
        im.set_item_tooltip("Pick TTTR files (.ptu, .ht3, .phu, …) and queue them for splitting.")
        self.remember("add_files")
        im.same_line()
        if im.button("Clear"):
            if callable(self.on_clear):
                self.on_clear()
        im.set_item_tooltip("Empty the file queue and reset the preview and the log.")
        self.remember("clear")
        im.same_line()
        if im.button("Help"):
            self.show_help()
        im.set_item_tooltip("How this tool works: queue files, set the window, Process.")
        self.remember("help")
        im.separator()

        for label, callback, tooltip in (
            (
                "Folder",
                self.tool._add_folder_dialog,
                "Queue supported TTTR files from a folder recursively.",
            ),
            (
                "Database",
                self.tool._add_from_database,
                "Select TTTR datasets from the session MMFDB database.",
            ),
            (
                "− Remove",
                self.tool._remove_preview_file,
                "Remove the selected preview file from the queue.",
            ),
        ):
            if im.button(label):
                callback()
            im.set_item_tooltip(tooltip)
        im.separator()
        im.text_wrapped("Drop TTTR files here (.ptu, .ht3, .phu, …) — or use the buttons.")
        paths = self.tool._file_paths
        if not paths:
            im.text_disabled("No files queued.")
            return
        # One row per queued file; clicking a row selects it for the preview.
        for i, path in enumerate(paths):
            selected = i == self.preview_index
            if im.selectable(f"{path.name}##file{i}", selected=selected):
                self.select_preview(i)
            im.set_item_tooltip(
                "Click to preview this file's intensity trace with the window boundaries."
            )
            self.remember(f"file{i}")

    def select_preview(self, index: int) -> None:
        """Select a queued file for the preview and load its trace."""
        job = getattr(self.tool, "job", None)
        if job is not None and job.running:
            return
        self.preview_index = index
        self.tool.load_preview_for_index(index)

    # ── the settings ──────────────────────────────────────────────────────

    def _draw_settings(self, box: tuple[float, float, float, float]) -> None:
        tool = self.tool

        if im.button("Process"):
            self._used("process")
            if callable(self.on_process):
                self.on_process()
        im.set_item_tooltip(
            "Compute start/stop photon indices per time window for every queued "
            "file and write one .bst (BID) file each."
        )
        self.remember("process")
        im.same_line()
        if im.button("Guide"):
            self.start_guide()
        im.set_item_tooltip("A step-by-step walk through the tool.")
        self.remember("guide")
        if im.get_line_avail() < 140.0:
            im.new_line()
        else:
            im.same_line()
        if im.button("Help"):
            self.show_help()
        im.set_item_tooltip("The short help page, also behind Help ▸ About.")
        self.remember("help")
        im.separator()

        # A typeable field (the view spec's ``value``): ``input_float`` is a drag field, which
        # takes no typed number, and the Qt tool's spin box did.
        draw_sections(TIME_WINDOW_FIELD, tool, self.form)
        if "time_window_ms" in self.form.rects:
            self.item_rects["time_window"] = self.form.rects["time_window_ms"]

        im.text("Output folder:")
        im.same_line()
        browse_w = im.calc_text_size("Browse…")[0] + 24.0
        caption_w = max(im.get_line_avail() - browse_w - 8.0, 60.0)
        im.set_next_item_width(caption_w)
        _, hint = im.input_text_with_hint(
            "##output_dir", tool.output_dir_text, "Auto (derived from first file)"
        )
        im.set_item_tooltip(
            "Where the .bst files go. Leave empty to create a folder next to the first input file."
        )
        if hint != tool.output_dir_text:
            tool.output_dir_text = hint
        im.same_line()
        if im.button("Browse…"):
            if callable(self.on_browse):
                self.on_browse()
        im.set_item_tooltip("Choose the output folder manually.")
        self.remember("output")
        # The status line (the Qt window's status bar): what was loaded, done or failed.
        if tool.message:
            im.separator()
            im.text_wrapped(tool.message)

        im.spacing()
        im.separator()
        last = tool._last_result
        if last is not None:
            metadata = getattr(last, "metadata", None) or {}
            im.text_colored(
                f"{metadata.get('total_windows', '?')} windows total",
                (0.4, 0.85, 0.5, 1.0),
            )
            im.text_disabled(f"Output: {metadata.get('output_dir', '?')}")

    def refresh_preview(self) -> None:
        """Reload the preview for the current selection (settings changed)."""
        if 0 <= self.preview_index < len(self.tool._file_paths):
            self.tool.load_preview_for_index(self.preview_index)

    # ── the preview plot ──────────────────────────────────────────────────

    def _draw_preview(self, box: tuple[float, float, float, float]) -> None:
        preview = self.preview
        if implot.begin_plot("##tw_preview", (-1, -1)):
            implot.setup_axes("Time (s)", "Intensity (counts)")
            implot.setup_legend()
            data = preview or {}
            counts = np.asarray(data.get("counts", []), dtype=float)
            time_axis = np.asarray(data.get("time_axis", []), dtype=float)
            if len(counts) and len(counts) == len(time_axis):
                implot.set_next_line_style((255, 220, 90, 255), 1.0)
                implot.plot_line("intensity", time_axis, counts)
                # One dashed vertical per time-window boundary.
                tw_s = float(data.get("time_window_ms", 0.0)) / 1000.0
                if tw_s > 0 and time_axis[-1] > 0:
                    bounds = np.arange(tw_s, time_axis[-1] + tw_s, tw_s)
                    # Thousands of lines (10 ms over minutes) fill the plot and hide
                    # the trace, as they did in the Qt tool; draw them only when
                    # they can be told apart.
                    if 0 < len(bounds) <= MAX_BOUNDARY_LINES:
                        implot.plot_inf_lines(
                            "window boundaries",
                            bounds,
                            spec=implot.PlotSpec(
                                flags=implot.ITEM_FLAGS_NO_LEGEND,
                                line_color=BOUNDARY_COLOUR,
                                line_weight=1.0,
                            ),
                        )
            else:
                implot.plot_dummy("select a file to preview its trace")
            implot.end_plot()
        self.remember("preview")

    # ── the log ───────────────────────────────────────────────────────────

    def _draw_summary(self, box: tuple[float, float, float, float]) -> None:
        lines = self.tool._log_lines
        if not lines:
            im.text_disabled("Processing log will appear here…")
            return
        # Newest at the bottom, like the log it replaces; a clip keeps long
        # sessions from dragging the layout.
        for line in lines[-60:]:
            im.text_wrapped(line)
        self.remember("summary")


class TimeWindowApp(ImApp):
    """The EMTK ImApp for the TTTR time-window tool."""

    def __init__(
        self,
        tool: TTTRTimeWindowTool,
        on_process: Callable[[], None] | None = None,
        on_clear: Callable[[], None] | None = None,
        on_browse: Callable[[], None] | None = None,
        on_add_files: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.time_window_gui = TimeWindowGui(
            tool,
            on_process=on_process,
            on_clear=on_clear,
            on_browse=on_browse,
            on_add_files=on_add_files,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.time_window_gui.item_rects

    def start_guide(self) -> None:
        self.time_window_gui.start_guide()

    def show_help(self) -> None:
        self.time_window_gui.show_help()

    def _render(self) -> None:
        self.time_window_gui.draw()


__all__ = ["TimeWindowApp", "WINDOW_BG"]
