"""EMTK immediate-mode UI for Data Selection in Burst Analysis."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import emtk.im as im
import emtk.implot as implot

if TYPE_CHECKING:
    from .tool import BurstDataSelectionWidget

WINDOW_BG = (0.12, 0.12, 0.14, 1.0)


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class BurstDataSelectionApp:
    """EMTK app providing dockable, draggable windows for TTTR data selection."""

    def __init__(self, widget: BurstDataSelectionWidget) -> None:
        self.widget = widget
        self.filter_text = ""
        self.selected_index: int | None = None
        self._last_dropped_region: dict[str, Any] | None = None

    def update(self) -> None:
        # Full viewport dockspace
        im.dock_space_over_viewport(1)

        paths = self.widget.paths()
        if self.selected_index is not None and self.selected_index >= len(paths):
            self.selected_index = len(paths) - 1 if paths else None

        self._render_files_window(paths)
        self._render_details_window(paths)
        self._render_summary_window(paths)

    def _render_files_window(self, paths: list[Path]) -> None:
        im.set_next_window_size((580, 480), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((20, 20), im.Cond.FIRST_USE_EVER)

        expanded, opened = im.begin("TTTR Data Files")
        if not expanded:
            im.end()
            return

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
                    self.selected_index = len(self.widget.paths()) - 1 if self.widget.paths() else None
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
        im.set_next_item_width(240)
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

        # Table of files
        table_flags = (
            im.TableFlags.BORDERS
            | im.TableFlags.ROW_BG
            | im.TableFlags.RESIZABLE
            | im.TableFlags.SCROLL_Y
            | im.TableFlags.SIZING_FIXED_FIT
        )
        if im.begin_table("tttr_files_table", 5, table_flags):
            im.table_setup_column("#", im.TableColumnFlags.WIDTH_FIXED, 36.0)
            im.table_setup_column("Filename", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("Size", im.TableColumnFlags.WIDTH_FIXED, 75.0)
            im.table_setup_column("Format", im.TableColumnFlags.WIDTH_FIXED, 60.0)
            im.table_setup_column("Status", im.TableColumnFlags.WIDTH_FIXED, 95.0)
            im.table_headers_row()

            filter_lower = self.filter_text.strip().lower()
            imports = self.widget.mmfdb_payload().get("imports", {})

            for i, p in enumerate(paths):
                fname = p.name
                if filter_lower and filter_lower not in fname.lower() and filter_lower not in str(p).lower():
                    continue

                im.table_next_row()

                # Column 0: Index
                im.table_set_column_index(0)
                im.text(f"{i + 1}")

                # Column 1: Selectable Filename + Drag Source
                im.table_set_column_index(1)
                is_selected = (self.selected_index == i)
                clicked, _ = im.selectable(f"{fname}##file_{i}", selected=is_selected)
                if clicked:
                    self.selected_index = i

                if im.begin_drag_drop_source():
                    im.set_drag_drop_payload("BURST_FILE", str(p).encode("utf-8"))
                    im.text(f"File: {fname}")
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
                    import json
                    data = json.loads(payload.decode("utf-8"))
                    self._last_dropped_region = data
                except Exception:
                    pass
            im.end_drag_drop_target()

        im.end()

    def _render_details_window(self, paths: list[Path]) -> None:
        im.set_next_window_size((380, 320), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((610, 20), im.Cond.FIRST_USE_EVER)

        expanded, opened = im.begin("File Metadata & MMFDB")
        if not expanded:
            im.end()
            return

        if self.selected_index is None or not (0 <= self.selected_index < len(paths)):
            im.text_colored("No file selected.", (0.6, 0.6, 0.6, 1.0))
            im.text("Click on any file in the table to inspect details.")
            im.end()
            return

        p = paths[self.selected_index]
        im.text_colored("Selected TTTR File:", (0.3, 0.8, 1.0, 1.0))
        im.text(f"Name: {p.name}")
        im.text_wrapped(f"Path: {p}")
        im.spacing()

        try:
            st = p.stat()
            im.text(f"Size: {_format_size(st.st_size)} ({st.st_size:,} bytes)")
            import datetime
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

        im.end()

    def _render_summary_window(self, paths: list[Path]) -> None:
        im.set_next_window_size((380, 200), im.Cond.FIRST_USE_EVER)
        im.set_next_window_pos((610, 350), im.Cond.FIRST_USE_EVER)

        expanded, opened = im.begin("Summary & Next Steps")
        if not expanded:
            im.end()
            return

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

        im.end()
