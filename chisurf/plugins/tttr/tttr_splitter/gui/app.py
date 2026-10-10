"""EMTK immediate-mode UI for the TTTR Split / Convert tool.

Left: the input file and output folder rows (browse buttons; OS drops land on
the Qt window and load the input) with the Convert/Split button and its
progress bar. Right: the split options and the batch panel — a queue of files
processed with the current option set. The widget
(:class:`~.tool.PTUSplitter`) keeps the Qt-free
:class:`~..view_model.SplitterViewModel` and the dialogs; this app renders its
state and calls back.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from emtk.i18n import tr
import emtk.im as im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import action_button

if TYPE_CHECKING:
    from .tool import PTUSplitter

WINDOW_BG = (30, 32, 38, 255)
ACCENT_GREEN = (46, 160, 67, 255)
#: The smallest chunk the Qt spin box allowed (``splitter.view.json`` ``minimum``), in thousands of photons.
MIN_PHOTONS_PER_FILE_K = 100


class SplitterGui(TourTarget):
    """EMTK GUI for the TTTR Split / Convert tool."""

    def __init__(
        self,
        tool: PTUSplitter,
        on_browse_input: Callable[[], None] | None = None,
        on_browse_output: Callable[[], None] | None = None,
        on_run: Callable[[], None] | None = None,
        on_add_batch_files: Callable[[], None] | None = None,
        on_add_batch_folder: Callable[[], None] | None = None,
        on_clear_batch: Callable[[], None] | None = None,
        on_run_batch: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_browse_input = on_browse_input
        self.on_browse_output = on_browse_output
        self.on_run = on_run
        self.on_add_batch_files = on_add_batch_files
        self.on_add_batch_folder = on_add_batch_folder
        self.on_clear_batch = on_clear_batch
        self.on_run_batch = on_run_batch
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}

        layout = Split(
            "h", 0.44, Region("io"), Split("v", 0.55, Region("options"), Region("batch"))
        )
        self.docks = DockManager(layout)
        self.docks.add_window("io", "📂 Input / Output", self._draw_io, dock="io", closable=True)
        self.docks.add_window(
            "options", "⚙️ Split options", self._draw_options, dock="options", closable=True
        )
        self.docks.add_window("batch", "🗂️ Batch", self._draw_batch, dock="batch", closable=True)

        self.help_window = EmTkHelpWindow(
            title="TTTR Split / Convert — Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=Path(__file__).parent / "guide.json",
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=tool,
            wait_for_controls=True,
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
        width = float(w or vp.size[0] or 860.0)
        height = float(h or vp.size[1] or 560.0)
        self.docks.draw((0.0, 0.0, width, height))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # ── one picker row: caption + field + browse button ───────────────────

    def _picker_row(self, caption: str, value: str, hint: str, on_browse: Callable, target: str) -> str:
        im.text(f"{caption}:")
        im.same_line()
        browse_w = im.calc_text_size("…")[0] + 28.0
        caption_pad = 8.0
        row_w = im.get_line_avail()
        im.set_next_item_width(max(row_w - browse_w - caption_pad, 60.0))
        _, text = im.input_text_with_hint(f"##{caption}", value, hint)
        im.set_item_tooltip(
            f"{caption} — type a path, or drop it on the window, or press … to browse."
        )
        im.same_line()
        if im.button(f"…##{target}"):
            if callable(on_browse):
                on_browse()
                self.tour.notify_used(target)
        im.set_item_tooltip(f"Browse for the {caption.lower()}.")
        return text

    # ── input / output ────────────────────────────────────────────────────

    def _draw_io(self, box: tuple[float, float, float, float]) -> None:
        tool = self.tool
        m = self.model

        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        if im.button(tr("✂ Convert / Split")):
            if callable(self.on_run):
                self.on_run()
                self.tour.notify_used("run")
        im.set_item_tooltip(
            tr("Split the loaded TTTR file into the output folder, one file per "
            "photon chunk, converting the container format when it differs.")
        )
        im.pop_style_color(3)
        self.remember("run")
        im.same_line()
        if action_button("guide"):
            self.start_guide()
        self.remember("guide")
        if im.get_line_avail() < 110.0:
            im.new_line()
        else:
            im.same_line()
        if action_button("help"):
            self.show_help()
        self.remember("help")

        im.separator()
        new_input = self._picker_row(
            "Input file",
            m.input_file,
            "Drop a TTTR file here or browse…",
            self.on_browse_input,
            "input",
        )
        if new_input != m.input_file and new_input.strip():
            tool.load_input(new_input.strip())
        self.remember("input")

        new_out = self._picker_row(
            "Output folder", m.output_folder, "Output folder", self.on_browse_output, "output"
        )
        if new_out != m.output_folder:
            m.output_folder = new_out
        self.remember("output")

        im.spacing()
        im.text(tr("Drop a TTTR file onto this window to load it."))
        if m.tttr is not None:
            n = len(m.tttr)
            im.text_colored(f"Loaded: {m.input_file}", (0.4, 0.85, 0.5, 1.0))
            im.text_disabled(f"{n:,} photons")
        reason = m.can_split()
        if reason is not None and m.tttr is not None:
            im.text_colored(reason, (0.9, 0.6, 0.3, 1.0))

        im.spacing()
        progress = tool.run_progress
        if tool.run_running or progress > 0:
            im.progress_bar(progress / 100.0, (-1, 0.0), f"{progress}%" if progress else "")

    # ── options ───────────────────────────────────────────────────────────

    def _draw_options(self, box: tuple[float, float, float, float]) -> None:
        m = self.model

        formats_open = im.collapsing_header("Formats", im.TreeNodeFlags.DEFAULT_OPEN)
        im.set_item_tooltip(tr("Expand or collapse the input and output container settings."))
        if formats_open:
            in_opts = m.input_format_options()
            idx = in_opts.index(m.input_format) if m.input_format in in_opts else 0
            changed, new_idx = im.combo("Input format", idx, in_opts)
            im.set_item_tooltip(
                tr("How to read the input file. Auto detects the container from its "
                "content; pick the vendor format when the extension lies.")
            )
            if changed and 0 <= new_idx < len(in_opts):
                m.input_format = in_opts[new_idx]
            out_opts = m.output_format_options()
            idx = out_opts.index(m.output_format) if m.output_format in out_opts else 0
            changed, new_idx = im.combo("Output format", idx, out_opts)
            im.set_item_tooltip(
                tr("Container the output files are written in — the same format "
                "when it matches the input, a transcode otherwise.")
            )
            if changed and 0 <= new_idx < len(out_opts):
                m.output_format = out_opts[new_idx]
            self.remember("formats")

        split_open = im.collapsing_header("Split", im.TreeNodeFlags.DEFAULT_OPEN)
        im.set_item_tooltip(
            tr("Expand or collapse photon chunking, timing and source retention settings.")
        )
        if split_open:
            changed_k, v = im.input_int("Photons per file [k]", m.photons_per_file_k, step=100)
            im.set_item_tooltip(
                tr("Chunk size in thousands of photons when Split into files is enabled "
                "(at least 100 k).")
            )
            # The Qt spin box bounded what a user commits (100 k) while letting "3" through on the way to "300".
            if changed_k:
                m.photons_per_file_k = max(1, int(v))
            if im.is_item_deactivated_after_edit() or (changed_k and not im.is_item_active()):
                m.photons_per_file_k = max(MIN_PHOTONS_PER_FILE_K, m.photons_per_file_k)
            bin_opts = ["1", "2", "4", "8", "16"]
            idx = bin_opts.index(m.microtime_binning) if m.microtime_binning in bin_opts else 0
            changed, new_idx = im.combo("Micro time binning", idx, bin_opts)
            im.set_item_tooltip(tr("Divide the micro-time resolution of the output by this factor."))
            if changed and 0 <= new_idx < len(bin_opts):
                m.microtime_binning = bin_opts[new_idx]
            for attr, label, tip in (
                (
                    "split_files",
                    "Split into files",
                    "Split into photon chunks; disable to write a single converted file.",
                ),
                (
                    "reset_macro_times",
                    "Reset macro times",
                    "Restart the macro-time clock at zero for each output file.",
                ),
                (
                    "keep_original",
                    "Keep original",
                    "Keep the input file; disabling deletes it after successful writing.",
                ),
            ):
                _, value = im.checkbox(label, getattr(m, attr))
                im.set_item_tooltip(tip)
                setattr(m, attr, value)
            self.remember("split")

    # ── batch ─────────────────────────────────────────────────────────────

    def _draw_batch(self, box: tuple[float, float, float, float]) -> None:
        m = self.model

        if im.button(tr("➕ Files")):
            if callable(self.on_add_batch_files):
                self.on_add_batch_files()
        im.set_item_tooltip(tr("Queue PTU files for the batch run."))
        self.remember("batch_files")
        im.same_line()
        if im.button(tr("📁 Folder")):
            if callable(self.on_add_batch_folder):
                self.on_add_batch_folder()
        im.set_item_tooltip(tr("Queue .ptu files recursively from a folder, sorted by name."))
        self.remember("batch_folder")
        im.same_line()
        if im.button(tr("🗑️ Clear")):
            if callable(self.on_clear_batch):
                self.on_clear_batch()
        im.set_item_tooltip(tr("Empty the batch queue."))
        self.remember("batch_clear")
        if im.button(tr("🗄 Database")):
            self.tool._add_batch_database()
        im.set_item_tooltip(tr("Queue PTU datasets from the session MMFDB database."))
        im.separator()

        if not m.batch_files:
            im.text_disabled(tr("No files queued — add PTU files or a folder."))
        else:
            im.text_disabled(f"Queued files ({len(m.batch_files)})")
            available = im.get_content_region_avail()
            # A child owns a bounded scroll region.  A table's computed height
            # can collapse when a dock is short, allowing the following
            # checkbox to paint over the last filename.
            list_height = max(54.0, min(150.0, float(box[3]) - 170.0))
            im.begin_child(
                (*im.get_cursor_screen_pos(), available[0], list_height),
                child_id="tttr_splitter_batch_queue",
                scrollable=True,
            )
            for row, path in enumerate(list(m.batch_files)):
                im.push_id(("batch-file", row))
                im.selectable(f"{path}##queued_{row}")
                im.set_item_tooltip(f"{path} — right-click to remove this queued file.")
                if im.begin_popup_context_item(f"batch_menu{row}"):
                    if im.menu_item("Remove from queue"):
                        m.batch_files.remove(path)
                    im.set_item_tooltip(tr("Remove this file without deleting it from disk."))
                    im.end_popup()
                im.pop_id()
            im.end_child()

        _, checked = im.checkbox(tr("Output next to each file"), m.batch_use_parent)
        im.set_item_tooltip(
            tr("Write each file's output into its own folder instead of the shared output folder.")
        )
        m.batch_use_parent = checked

        im.spacing()
        if im.button(tr("▶ Start batch")):
            if callable(self.on_run_batch):
                self.on_run_batch()
        im.set_item_tooltip(tr("Split every queued file with the options set above."))
        self.remember("batch_run")
        index, count = self.tool.batch_progress
        if self.tool.batch_running or count:
            fraction = float(index) / float(count) if count else 0.0
            im.progress_bar(fraction, (-1, 0.0), f"{index}/{count}")


class SplitterApp(ImApp):
    """The EMTK ImApp for the TTTR Split / Convert tool."""

    def __init__(self, tool: PTUSplitter, **callbacks: Callable) -> None:
        self.tool = tool
        self.splitter_gui = SplitterGui(tool, **callbacks)
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.splitter_gui.item_rects

    def start_guide(self) -> None:
        self.splitter_gui.start_guide()

    def show_help(self) -> None:
        self.splitter_gui.show_help()

    def _render(self) -> None:
        self.splitter_gui.draw()


__all__ = ["SplitterApp", "WINDOW_BG"]
