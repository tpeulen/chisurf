"""EMTK immediate-mode UI for the TTTR Inspector.

Left: the header tags as an editable table — one row per tag, the type chosen
from the tag-type combo, plus Open / Add / Remove / Save-as-PTU actions and the
source summary. Right, top: the read-only JSON view of the edited header;
bottom: the photon preview — the opened file's first events (routing channel,
macro and micro time). The widget
(:class:`~.native.NativeHeaderEditor`) keeps the Qt-free
:class:`~..view_model.HeaderEditorViewModel`, the file dialogs and the OS drop;
this app renders its state. The string editors are the source of truth for the
table and are committed to the model on every edit, the way the Qt table's
``itemChanged`` was.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import emtk.im as im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.i18n import tr

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from chisurf.plugins.emtk_layout import action_button

if TYPE_CHECKING:
    from .native import NativeHeaderEditor

WINDOW_BG = (30, 32, 38, 255)

_TABLE_FLAGS = im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.RESIZABLE


class HeaderEditorGui(TourTarget):
    """EMTK GUI for the TTTR header editor."""

    def __init__(
        self,
        tool: NativeHeaderEditor,
        on_open: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
        on_guide: Callable[[], None] | None = None,
        on_help: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.on_open = on_open
        self.on_save = on_save
        self.on_guide = on_guide
        self.on_help = on_help

        #: The string editors of the tag table — the source of truth for the
        #: cells, committed to the model on every edit and rebuilt on load.
        self._rows: list[dict] = []
        #: The photon preview table (a scrollable DataTable, wheel-driven).
        self._photon_binding = None
        self._photon_binding_model = None
        self.item_rects: dict[str, tuple[float, float, float, float]] = {}

        layout = Split(
            "h", 0.62, Region("tags"),
            Split("v", 0.45, Region("json"), Region("photons")),
        )
        self.docks = DockManager(layout)
        self.docks.add_window("tags", "Header tags", self._draw_tags, dock="tags")
        self.docks.add_window("json", "Header JSON", self._draw_json, dock="json")
        self.docks.add_window("photons", "Photons", self._draw_photons, dock="photons")

        self.help_window = EmTkHelpWindow(
            title="TTTR Inspector — Help & Reference",
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
        self.rebuild_rows()

    # ── plumbing ──────────────────────────────────────────────────────────

    @property
    def model(self):
        return self.tool.model

    def start_guide(self) -> None:
        self.tour.start()

    def show_help(self) -> None:
        self.help_window.show()

    def load_example(self) -> None:
        """Read the generated demonstration PTU through the tool."""
        loader = getattr(self.tool, "load_example", None)
        if callable(loader):
            loader()

    def draw(self, w: float = 0.0, h: float = 0.0) -> None:
        vp = im.get_main_viewport()
        width = float(w or vp.size[0] or 860.0)
        height = float(h or vp.size[1] or 560.0)
        self.docks.draw((0.0, 0.0, width, height))
        if self.help_window.open:
            self.help_window.draw((0.0, 0.0, width, height))
        if self.tour.active:
            self.tour.draw(width, height)

    # ── the string editors ↔ the model ────────────────────────────────────

    def rebuild_rows(self) -> None:
        """Rebuild the string editors from the model's tags (a load happened)."""
        type_names = list(self.model.TYPE_MAPPING.values())
        self._rows = []
        for tag in self.model.tags:
            self._rows.append(
                {
                    "name": str(tag.get("name", "")),
                    "type": self.model.TYPE_MAPPING.get(tag.get("type"), type_names[0])
                    if tag.get("type") in self.model.TYPE_MAPPING
                    else f"Unknown 0x{tag.get('type', 0):08X}",
                    "raw_type": tag.get("type"),
                    "raw_value": tag.get("value"),
                    "value": json.dumps(tag.get("value"))
                    if isinstance(tag.get("value"), list)
                    else str(tag.get("value", "")),
                    "idx": str(tag.get("idx", -1)),
                }
            )

    def _commit(self) -> None:
        """Commit the editors to the model (which refreshes the JSON view)."""
        try:
            self.model.set_tags([dict(r) for r in self._rows])
            self.tool.validation_error = ""
        except ValueError as exc:
            self.tool.validation_error = str(exc)

    # ── the tags dock ─────────────────────────────────────────────────────

    def _draw_tags(self, box: tuple[float, float, float, float]) -> None:
        if action_button("example", id="load_example"):
            self.load_example()
            self.tour.notify_used("load_example")
        im.set_item_tooltip(
            tr("Generate a deterministic demonstration PTU in the settings cache and read its header.")
        )
        self.remember("load_example")
        im.same_line()
        if action_button(
            "open", tooltip=tr("Open a TTTR file (PTU / HT3 / SPC / HDF5) and read its header.")
        ):
            if callable(self.on_open):
                self.on_open()
                self.tour.notify_used("open")
        self.remember("open")
        im.same_line()
        if im.button(tr("➕ Add")):
            self._rows.append({"name": "NewTag", "type": "AnsiString", "value": "", "idx": "-1"})
            self._commit()
            self.tour.notify_used("add")
        im.set_item_tooltip(tr("Append a new header tag with a placeholder name."))
        self.remember("add")
        im.same_line()
        if action_button("guide"):
            self.start_guide()
        self.remember("guide")
        if im.get_line_avail() < 170.0:
            im.new_line()
        else:
            im.same_line()
        if action_button("help"):
            self.show_help()
        self.remember("help")
        if im.get_line_avail() < 170.0:
            im.new_line()
        else:
            im.same_line()
        if im.button(tr("💾 Save as PTU"), role="primary"):
            if callable(self.on_save):
                self.on_save()
                self.tour.notify_used("save")
        im.set_item_tooltip(
            tr(
                "Write the edited header to a new PTU file — the source's photon "
                "data is copied verbatim."
            )
        )
        self.remember("save")

        im.separator()
        if getattr(self.tool, "validation_error", ""):
            im.text_wrapped(self.tool.validation_error)
        if getattr(self.tool, "message", ""):
            im.text_wrapped(self.tool.message)
        if getattr(getattr(self.tool, "job", None), "running", False):
            im.text(tr("Reading or saving TTTR data..."))
        im.text_disabled(self.model.source_summary)
        im.set_item_tooltip(
            tr("Reads any tttrlib container; edited headers are always written as PTU.")
        )

        type_names = list(self.model.TYPE_MAPPING.values())
        type_names.extend(row["type"] for row in self._rows if row["type"] not in type_names)
        rows = self._rows
        table_h = max(float(box[3]) - 92.0, 120.0)
        if im.begin_table("header_tags", 5, _TABLE_FLAGS, (0, table_h)):
            im.table_setup_column("Name", im.TableColumnFlags.WIDTH_FIXED, 170.0)
            im.table_setup_column("Type", im.TableColumnFlags.WIDTH_FIXED, 120.0)
            im.table_setup_column("Value", im.TableColumnFlags.WIDTH_STRETCH)
            im.table_setup_column("Idx", im.TableColumnFlags.WIDTH_FIXED, 60.0)
            im.table_setup_column("", im.TableColumnFlags.WIDTH_FIXED, 30.0)
            im.table_headers_row()
            for i, row in enumerate(rows):
                im.table_next_row()
                im.table_set_column_index(0)
                _, name = im.input_text(f"##name{i}", row["name"])
                im.set_item_tooltip(tr("Header tag name; names must not be empty."))
                if name != row["name"]:
                    row["name"] = name
                    self._commit()
                im.table_set_column_index(1)
                current = type_names.index(row["type"]) if row["type"] in type_names else 0
                changed, new_idx = im.combo(f"##type{i}", current, type_names)
                im.set_item_tooltip(tr("PTU tag type determines how the value is stored."))
                if changed and 0 <= new_idx < len(type_names):
                    row["type"] = type_names[new_idx]
                    self._commit()
                im.table_set_column_index(2)
                unknown_type = row["type"] not in self.model.REVERSE_TYPE_MAPPING
                im.begin_disabled(unknown_type)
                _, value = im.input_text(f"##value{i}", row["value"])
                im.end_disabled()
                im.set_item_tooltip(
                    "Unsupported tag value is preserved unchanged. " + row["value"]
                    if unknown_type
                    else "Native PTU value; timing in seconds, DateTime in PTU days, arrays in JSON. "
                    + row["value"]
                )
                if value != row["value"]:
                    row["value"] = value
                    self._commit()
                im.table_set_column_index(3)
                _, idx = im.input_text(f"##idx{i}", row["idx"])
                im.set_item_tooltip(tr("Indexed tag position; -1 means an unindexed tag."))
                if idx != row["idx"]:
                    row["idx"] = idx
                    self._commit()
                im.table_set_column_index(4)
                if im.small_button(f"✕##remove{i}"):
                    del self._rows[i]
                    self._commit()
                    im.end_table()
                    return
                im.set_item_tooltip(tr("Remove this tag."))
            im.end_table()
        self.remember("tag_table")

    # ── the JSON dock ─────────────────────────────────────────────────────

    def _draw_json(self, box: tuple[float, float, float, float]) -> None:
        im.text_wrapped(tr("Read-only view — saved with the tags into the PTU header."))
        im.separator()
        for line in (self.model.json_text or "").splitlines():
            im.text_wrapped(line)
        self.remember("json")


    # ── the photons dock ──────────────────────────────────────────────────
    def _draw_photons(self, box: tuple[float, float, float, float]) -> None:
        if not self.model.photon_rows:
            im.text_wrapped(
                tr("Open a TTTR file — its first events appear here "
                   "(routing channel, macro and micro time).")
            )
            self.remember("photons")
            return
        im.text_disabled(tr(self.model.photon_summary))
        im.set_item_tooltip(
            tr("First {n} events; macro/micro times are the format's raw clock; "
               "the header tags carry units and setup.").format(
                n=len(self.model.photon_rows))
        )
        im.separator()
        from emtk.widgets.data_table import TableBinding, draw_table

        model = self.model
        if (self._photon_binding is None
                or self._photon_binding_model is not model):
            section = {"type": "custom", "key": "data_table",
                       "options": {"source": "photon_rows", "row_key": "i",
                                   "editable": False, "height": 260.0,
                                   "stretch": 1.0, "min_height": 100.0,
                                   "columns": [
                                       {"key": "i", "title": "#", "align": "right"},
                                       {"key": "rch", "title": "Routing ch", "align": "right"},
                                       {"key": "macro", "title": "Macro time (raw)", "align": "right"},
                                       {"key": "micro", "title": "Micro time (raw)", "align": "right"},
                                   ]}}
            self._photon_binding = TableBinding(section, model)
            self._photon_binding_model = model
        draw_table(self._photon_binding, "photon_rows")
        self.remember("photons")


class HeaderEditorApp(ImApp):
    """The EMTK ImApp for the TTTR inspector (header + photon preview)."""

    def __init__(
        self,
        tool: NativeHeaderEditor,
        on_open: Callable[[], None] | None = None,
        on_save: Callable[[], None] | None = None,
    ) -> None:
        self.tool = tool
        self.header_gui = HeaderEditorGui(
            tool,
            on_open=on_open,
            on_save=on_save,
            on_guide=self.start_guide,
            on_help=self.show_help,
        )
        super().__init__(gui=self._render, continuous=False)

    @property
    def item_rects(self) -> dict[str, tuple[float, float, float, float]]:
        return self.header_gui.item_rects

    def start_guide(self) -> None:
        self.header_gui.start_guide()

    def show_help(self) -> None:
        self.header_gui.show_help()

    def _render(self) -> None:
        self.header_gui.draw()


__all__ = ["HeaderEditorApp", "WINDOW_BG"]
