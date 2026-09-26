"""EMTK immediate-mode UI for Data Selection in Burst Analysis."""

from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

import emtk.im as im
import emtk.implot as implot
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split

from chisurf.gui.widgets.tools.emtk_help_guide import EmTkGuidedTour, EmTkHelpWindow

if TYPE_CHECKING:
    from .tool import BurstDataSelectionWidget

WINDOW_BG = (30, 32, 38, 255)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class BurstDataSelectionGui:
    """EMTK GUI providing responsive, dockable windows for TTTR data selection."""

    def __init__(
        self,
        widget: BurstDataSelectionWidget,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.widget = widget
        self.on_guide = on_guide
        self.on_help = on_help
        self.filter_text = ""
        self.selected_index: int | None = None
        self._last_dropped_region: dict[str, Any] | None = None
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}
        self.on_used: Callable[[str], None] | None = None

        layout = Split(
            "h",
            0.62,
            Region("left"),
            Split("v", 0.55, Region("details"), Region("summary")),
        )
        self.docks = DockManager(layout)
        self.docks.add_window(
            "files",
            "📁 TTTR Data Files",
            self._draw_files,
            dock="left",
            closable=False,
        )
        self.docks.add_window(
            "details",
            "ℹ️ File Details",
            self._draw_details,
            dock="details",
            closable=False,
        )
        self.docks.add_window(
            "summary",
            "📊 Summary & Next Steps",
            self._draw_summary,
            dock="summary",
            closable=False,
        )

        help_resource = Path(__file__).parent / "help.md"
        guide_resource = Path(__file__).parent / "guide.json"
        self.help_window = EmTkHelpWindow(
            title="Data Selection — Help & Reference",
            resource=help_resource,
            owner=self.widget,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=guide_resource,
            get_target_rect=lambda k: self.item_rects.get(k),
            owner=self.widget,
        )

    def start_guide(self) -> None:
        """Start the in-EMTK guided tour."""
        self.tour.start()

    def show_help(self) -> None:
        """Show the in-EMTK help window."""
        self.help_window.show()

    def remember(self, name: str, rect: tuple[float, float, float, float] | None = None) -> None:
        """Store the item's screen rectangle for tour targeting."""
        r = rect if rect is not None else im.get_item_rect()
        if r is not None:
            self.item_rects[name] = tuple(r)

    def track(self, name: str) -> None:
        """Record usage of a named control."""
        if callable(self.on_used):
            self.on_used(name)

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        paths = self.widget.paths()
        if self.selected_index is not None and self.selected_index >= len(paths):
            self.selected_index = len(paths) - 1 if paths else None

        vp = im.get_main_viewport()
        vw, vh = vp.size
        width = float(w or vw or 800.0)
        height = float(h or vh or 600.0)
        self.docks.draw((0.0, 0.0, width, height))

        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))

        if self.tour.active:
            self.tour.draw(width, height)

    def update(self) -> None:
        self.draw()

    def _draw_files(self, box: tuple[float, float, float, float]) -> None:
        paths = self.widget.paths()
        # Top Action Bar
        if im.button("➕ Add Files"):
            self.widget._browse_files()
        im.same_line()
        if im.button("📁 Add Folder"):
            self.widget._browse_folder()
        im.same_line()
        if im.button("🗄️ Database (MMFDB)"):
            self.widget._browse_mmfdb()
        im.same_line()
        if self.selected_index is not None and 0 <= self.selected_index < len(paths):
            if im.button("➖ Remove"):
                self.widget._remove_index(self.selected_index)
                if self.selected_index >= len(self.widget.paths()):
                    self.selected_index = (
                        len(self.widget.paths()) - 1 if self.widget.paths() else None
                    )
        else:
            im.begin_disabled()
            im.button("➖ Remove")
            im.end_disabled()
        im.same_line()
        if paths:
            if im.button("🗑️ Clear All"):
                self.widget.clear()
                self.selected_index = None
        else:
            im.begin_disabled()
            im.button("🗑️ Clear All")
            im.end_disabled()

        # Search / filter
        im.separator()
        im.align_text_to_frame_padding()
        im.text("Filter:")
        im.same_line()
        im.set_next_item_width(200)
        _, self.filter_text = im.input_text("##file_filter", self.filter_text)
        if self.filter_text:
            im.same_line()
            if im.button("Clear##filter_clear"):
                self.filter_text = ""

        if self._last_dropped_region:
            im.same_line()
            im.text_colored(
                f"Region: {self._last_dropped_region.get('x_range', '')}",
                (0.4, 0.9, 0.4, 1.0),
            )

        im.spacing()

        # Table of files - dynamically sized to fill the remaining dock height
        table_flags = (
            im.TableFlags.BORDERS
            | im.TableFlags.ROW_BG
            | im.TableFlags.RESIZABLE
            | im.TableFlags.SCROLL_Y
            | im.TableFlags.SIZING_FIXED_FIT
        )
        table_h = max(120.0, box[3] - 78.0)
        if im.begin_table("tttr_files_table", 5, table_flags, (0, table_h)):
            im.table_setup_column("#", im.TableColumnFlags.WIDTH_FIXED, 36.0)
            im.table_setup_column("Filename", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("Size", im.TableColumnFlags.WIDTH_FIXED, 80.0)
            im.table_setup_column("Format", im.TableColumnFlags.WIDTH_FIXED, 65.0)
            im.table_setup_column("Status", im.TableColumnFlags.WIDTH_FIXED, 75.0)
            im.table_headers_row()

            imports = self.widget.mmfdb_payload().get("imports", {})
            for idx, p in enumerate(paths):
                if self.filter_text and self.filter_text.lower() not in p.name.lower():
                    continue

                im.table_next_row()

                # Column 0: Index
                im.table_set_column_index(0)
                im.text(f"{idx + 1}")

                # Column 1: Filename (Selectable + Drag Source)
                im.table_set_column_index(1)
                is_selected = self.selected_index == idx
                if im.selectable(
                    f"{p.name}##file_{idx}", is_selected, im.SelectableFlags.SPAN_ALL_COLUMNS
                ):
                    self.selected_index = idx

                if im.begin_drag_drop_source():
                    drag_data = json.dumps({"type": "tttr_file", "path": str(p), "index": idx})
                    im.set_drag_drop_payload("BURST_FILE", drag_data.encode("utf-8"))
                    im.text(f"Moving {p.name}")
                    im.end_drag_drop_source()

                # Column 2: Size
                im.table_set_column_index(2)
                try:
                    size_bytes = p.stat().st_size
                    im.text(_format_size(size_bytes))
                except Exception:
                    im.text("—")

                # Column 3: Format
                im.table_set_column_index(3)
                im.text(p.suffix.upper().lstrip("."))

                # Column 4: Status
                im.table_set_column_index(4)
                key = str(p)
                entry = imports.get(key)
                if entry and "error" not in entry:
                    im.text_colored("✓ MMFDB", (0.3, 0.85, 0.4, 1.0))
                elif entry and "error" in entry:
                    im.text_colored("✗ Error", (0.9, 0.3, 0.3, 1.0))
                else:
                    im.text_colored("Ready", (0.4, 0.7, 1.0, 1.0))

            im.end_table()

        # Window Drop Target for Region / Files
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(payload.decode("utf-8"))
                    self._last_dropped_region = data
                except Exception:
                    pass
            im.end_drag_drop_target()

    def _draw_details(self, box: tuple[float, float, float, float]) -> None:
        paths = self.widget.paths()
        if self.selected_index is None or not (0 <= self.selected_index < len(paths)):
            im.text_colored("No file selected.", (0.6, 0.6, 0.6, 1.0))
            im.text("Click on any file in the table to inspect details.")
            return

        p = paths[self.selected_index]
        im.text_colored("Selected TTTR File:", (0.3, 0.8, 1.0, 1.0))
        im.text(f"Name: {p.name}")
        im.text_wrapped(f"Path: {p}")
        im.spacing()

        try:
            st = p.stat()
            im.text(f"Size: {_format_size(st.st_size)} ({st.st_size:,} bytes)")
            mtime = datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            im.text(f"Modified: {mtime}")
        except Exception as e:
            im.text_colored(f"Stat error: {e}", (0.9, 0.3, 0.3, 1.0))

        im.separator()
        im.text_colored("MMFDB Integration:", (0.9, 0.7, 0.2, 1.0))
        imports = self.widget.mmfdb_payload().get("imports", {})
        key = str(p)
        entry = imports.get(key)
        if entry:
            if "error" in entry:
                im.text_colored(f"Error: {entry['error']}", (0.9, 0.3, 0.3, 1.0))
                if im.button("Retry Import##retry"):
                    self.widget._import_path_to_mmfdb(p)
                    self.widget.host.update()
            else:
                obj_res = entry.get("object_result", {})
                raw_res = entry.get("raw_data_result", {})
                obj_uuid = obj_res.get("object", {}).get("object_uuid", "—")
                raw_id = raw_res.get("raw_data", {}).get("raw_data_id", "—")
                im.text(f"Object UUID: {obj_uuid}")
                im.text(f"Raw Data ID: {raw_id}")
                im.text_colored("✓ Synced with MMFDB object store", (0.3, 0.85, 0.4, 1.0))
        else:
            im.text("Status: Pending import")
            if im.button("Import Now##import_single"):
                self.widget._import_path_to_mmfdb(p)
                self.widget.host.update()

    def _draw_summary(self, box: tuple[float, float, float, float]) -> None:
        paths = self.widget.paths()
        total_files = len(paths)
        total_size = 0
        for p in paths:
            try:
                total_size += p.stat().st_size
            except Exception:
                pass

        imports = self.widget.mmfdb_payload().get("imports", {})
        imported_count = sum(1 for e in imports.values() if "error" not in e)

        im.text_colored("Workflow Overview:", (0.4, 0.9, 0.4, 1.0))
        im.bullet_text(f"Total Files: {total_files}")
        im.bullet_text(f"Total Disk Size: {_format_size(total_size)}")
        im.bullet_text(f"MMFDB Registered: {imported_count} / {total_files}")

        im.separator()
        if total_files > 0:
            im.text_colored("Ready to proceed!", (0.3, 0.85, 0.4, 1.0))
            if im.button("Proceed to 2. Burst Selection ➔"):
                parent = self.widget.parent()
                show_panel = getattr(parent, "show_panel_by_role", None)
                if callable(show_panel):
                    show_panel("selection")
        else:
            im.text_colored("Add TTTR files to begin analysis.", (0.8, 0.8, 0.8, 1.0))


class BurstDataSelectionApp(ImApp):
    """The EMTK App for TTTR Data Selection."""

    def __init__(
        self,
        widget: BurstDataSelectionWidget,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.selection_gui = BurstDataSelectionGui(
            widget=widget,
            on_guide=on_guide,
            on_help=on_help,
        )
        self.widget = widget
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.selection_gui.item_rects

    @property
    def on_used(self) -> Callable[[str], None] | None:
        return self.selection_gui.on_used

    @on_used.setter
    def on_used(self, cb: Callable[[str], None] | None) -> None:
        self.selection_gui.on_used = cb

    def start_guide(self) -> None:
        """Start guided tour inside EMTK."""
        self.selection_gui.start_guide()

    def show_help(self) -> None:
        """Show help documentation inside EMTK."""
        self.selection_gui.show_help()

    def _render(self) -> None:
        self.selection_gui.draw()
