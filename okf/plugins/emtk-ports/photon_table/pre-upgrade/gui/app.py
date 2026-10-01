"""EMTK immediate-mode UI for the Photon Table.

Left: the file (browse/drop to load) and its summary — photon count, routing
channels, acquisition time. Right: the table itself, one row per photon, with
a channel filter and page navigation (a TTTR file holds millions of photons,
so the table shows a window of rows and moves through them). "Copy visible"
puts the shown rows on the clipboard as TSV.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

import emtk.im as im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget

if TYPE_CHECKING:
    from .tool import PhotonTableTool

WINDOW_BG = (30, 32, 38, 255)
ACCENT_GREEN = (46, 160, 67, 255)

_TABLE_FLAGS = im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.RESIZABLE

_CHANNEL_ANY = -1


class PhotonTableGui(TourTarget):
    """EMTK GUI for the photon table."""

    def __init__(
        self,
        tool: PhotonTableTool,
        on_browse: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_browse = on_browse
        self.on_guide = on_guide
        self.on_help = on_help

        self.item_rects: dict[str, tuple[float, float, float, float]] = {}

        layout = Split("h", 0.34, Region("file"), Region("table"))
        self.docks = DockManager(layout)
        self.docks.add_window("file", "📁 TTTR file", self._draw_file, dock="file", closable=True)
        self.docks.add_window("table", "🔆 Photons", self._draw_table, dock="table", closable=True)

        self.help_window = EmTkHelpWindow(
            title="Photon Table — Help & Reference",
            resource=Path(__file__).parent / "help.md",
            owner=tool,
            on_start_guide=self.start_guide,
            size=(680.0, 520.0),
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

    # ── the file dock ─────────────────────────────────────────────────────

    def _draw_file(self, box: tuple[float, float, float, float]) -> None:
        tool = self.tool
        m = self.model

        if im.button("📂 Open TTTR…"):
            if callable(self.on_browse):
                self.on_browse()
        im.set_item_tooltip(
            "Open a TTTR file (.ptu, .ht3, .phu, …). Dropping one on the window does the same."
        )
        self.remember("open")

        im.same_line()
        if im.button("📋 Copy visible"):
            im.set_clipboard_text(
                m.page_tsv(tool.first_index, tool.rows_per_page, tool.channel_filter)
            )
        im.set_item_tooltip("Copy the visible rows to the clipboard as tab-separated text.")
        self.remember("copy")

        im.same_line()
        if im.button("📖 Guide"):
            self.start_guide()
        im.set_item_tooltip("A step-by-step walk through the tool.")
        self.remember("guide")
        if im.get_line_avail() < 110.0:
            im.new_line()
        else:
            im.same_line()
        if im.button("❓ Help"):
            self.show_help()
        im.set_item_tooltip("The short help page.")
        self.remember("help")

        im.separator()
        if not m.n_photons:
            im.text_wrapped(
                "Open a TTTR file — or drop one on this window — to inspect its photons."
            )
            return

        im.text_colored(m.filename, (0.55, 0.8, 1.0, 1.0))
        acq = m.acquisition_time_s()
        summary = f"{m.n_photons:,} photons"
        if acq > 0:
            summary += f", {acq:.3g} s"
        if m.n_micro_channels:
            summary += f", {m.n_micro_channels} µ-channels"
        im.text_disabled(summary)
        channels = m.used_channels
        im.text_disabled(f"Routing channels: {', '.join(str(c) for c in channels) or '—'}")
        self.remember("file_info")

    # ── the table dock ────────────────────────────────────────────────────

    def _navigation(self, box: tuple[float, float, float, float]) -> None:
        tool = self.tool
        m = self.model
        count = m.filtered_count(tool.channel_filter)

        if im.button("⏮ First"):
            tool.first_index = 0
        im.set_item_tooltip("Jump to the first photon of the filtered selection.")
        im.same_line()
        if im.button("◀ Prev"):
            tool.first_index = m.clamp_first(
                tool.first_index - tool.rows_per_page, tool.rows_per_page, tool.channel_filter
            )
        im.set_item_tooltip("One page back.")
        im.same_line()
        if im.button("Next ▶"):
            tool.first_index = m.clamp_first(
                tool.first_index + tool.rows_per_page, tool.rows_per_page, tool.channel_filter
            )
        im.set_item_tooltip("One page forward.")
        im.same_line()
        if im.button("Last ⏭"):
            tool.first_index = m.clamp_first(
                max(count - tool.rows_per_page, 0), tool.rows_per_page, tool.channel_filter
            )
        im.set_item_tooltip("Jump to the last full page of the filtered selection.")

        im.same_line()
        im.text_disabled(
            f"photons {tool.first_index:,}–{min(count, tool.first_index + tool.rows_per_page):,}"
            if count
            else "no photons"
        )
        im.set_item_tooltip(
            f"{count:,} photons match the filter; the table shows "
            f"{tool.rows_per_page} of them per page."
        )

        im.spacing()
        # One control per row, each filling the line: two fields sharing a row
        # overflowed a narrow dock and pushed the channel combo off its edge.
        im.text("First photon:")
        im.same_line()
        im.set_next_item_width(-1.0)
        _, v = im.input_int("##first_photon", tool.first_index, step=0)
        im.set_item_tooltip("Index of the first photon shown (within the filtered selection).")
        if v != tool.first_index:
            tool.first_index = m.clamp_first(v, tool.rows_per_page, tool.channel_filter)

        im.text("Rows:")
        im.same_line()
        im.set_next_item_width(-1.0)
        _, r = im.input_int("##rows_per_page", tool.rows_per_page, step=0)
        im.set_item_tooltip(
            "Rows shown at once (1–20000). Large pages are fine; the table only "
            "draws what fits the window."
        )
        if r != tool.rows_per_page:
            tool.rows_per_page = max(1, min(int(r), 20_000))
            tool.first_index = m.clamp_first(
                tool.first_index, tool.rows_per_page, tool.channel_filter
            )

        channels = m.used_channels
        options = ["All channels"] + [str(c) for c in channels]
        current = (
            0
            if tool.channel_filter == _CHANNEL_ANY
            else options.index(str(tool.channel_filter))
            if str(tool.channel_filter) in options
            else 0
        )
        im.text("Channel:")
        im.same_line()
        im.set_next_item_width(-1.0)
        changed, new_idx = im.combo("##channel_filter", current, options)
        im.set_item_tooltip(
            "Show only the photons of one routing channel. 'All channels' keeps the file's order."
        )
        if changed and 0 <= new_idx < len(options):
            tool.channel_filter = _CHANNEL_ANY if new_idx == 0 else int(options[new_idx])
            tool.first_index = m.clamp_first(0, tool.rows_per_page, tool.channel_filter)
        self.remember("filters")

    def _draw_table(self, box: tuple[float, float, float, float]) -> None:
        tool = self.tool
        m = self.model

        self._navigation(box)
        im.separator()

        if not m.n_photons:
            im.text_disabled("No photons loaded.")
            return

        rows = m.page(tool.first_index, tool.rows_per_page, tool.channel_filter)
        table_h = max(float(box[3]) - 20.0, 120.0)
        if im.begin_table("photons", 5, _TABLE_FLAGS, (0, table_h)):
            im.table_setup_column("Photon", im.TableColumnFlags.WIDTH_FIXED, 90.0)
            im.table_setup_column("File idx", im.TableColumnFlags.WIDTH_FIXED, 90.0)
            im.table_setup_column("Channel", im.TableColumnFlags.WIDTH_FIXED, 80.0)
            im.table_setup_column("Micro time", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("Macro time [ms]", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_headers_row()
            for r in rows:
                im.table_next_row()
                im.table_set_column_index(0)
                im.text_unformatted(f"{r['photon']:,}")
                im.table_set_column_index(1)
                im.text_unformatted(f"{r['idx']:,}")
                im.table_set_column_index(2)
                im.text_colored(f"{r['channel']}", (0.55, 0.8, 1.0, 1.0))
                im.table_set_column_index(3)
                im.text_unformatted(f"{r['micro']}")
                im.table_set_column_index(4)
                macro = f"{r['macro']:.6f}" if m.macro_resolution > 0 else f"{r['macro']:.0f}"
                im.text_unformatted(macro)
            im.end_table()
        self.remember("photon_table")


class PhotonTableApp(ImApp):
    """The EMTK ImApp for the photon table."""

    def __init__(
        self,
        tool: PhotonTableTool,
        on_browse: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.table_gui = PhotonTableGui(
            tool, on_browse=on_browse, on_guide=self.start_guide, on_help=self.show_help
        )
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.table_gui.item_rects

    def start_guide(self) -> None:
        self.table_gui.start_guide()

    def show_help(self) -> None:
        self.table_gui.show_help()

    def _render(self) -> None:
        self.table_gui.draw()


__all__ = ["PhotonTableApp", "WINDOW_BG"]
