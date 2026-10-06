"""Native emtk MMFDB Admin: browse, edit, import and export the Multiparametric Fluorescence Database.

The window is the Qt tool's shell -- a menu bar, a connection toolbar, a
searchable rail of panels on the left, the open panel on the right and a status
bar with Back / Next -- drawn without Qt. Everything a panel shows is declared:
``admin.view.json`` (the toolbar, the entity panel, every dialog) and
``admin_panels.view.json`` (the other panels), drawn by
:func:`emtk.view_form.draw_sections` over the Qt-free models of ``gui/native``.
The entity forms are generated from the mmCIF dictionary
(:func:`~.entity_values.view_section`). Only what a spec cannot express is drawn
here: the menu bar, the rail, the status bar, the connection dot, the spectrum
plots and the provenance graph.

All server calls run on the model's :class:`~.native.runner.Runner` (a worker
thread), so the window never waits on the network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot, nodes
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.node_editor.control import GraphControl, NodeContentRenderer
from chisurf.emtk.node_editor.document import GraphDocument

from .native.model import AdminModel
from .native.runner import Runner

HERE = Path(__file__).parent

#: Width of the rail and height of the status bar.
RAIL_W = 230.0
BAR_H = 30.0
#: Line styles of the spectrum traces as emtk dash patterns.
DASHES = {"solid": None, "dash": (8.0, 5.0), "dot": (2.0, 4.0), "dashdot": (8.0, 4.0)}


def load_specs() -> tuple[dict, dict, dict]:
    """``(shell panels by name, other panels by name, entity actions)`` of the two view specs."""
    shell = json.loads((HERE / "admin.view.json").read_text(encoding="utf-8"))
    panels = json.loads((HERE / "admin_panels.view.json").read_text(encoding="utf-8"))
    by_name = {}
    for section in shell["sections"]:
        include = section.get("include")
        if include:
            extra = json.loads((HERE / include).read_text(encoding="utf-8"))
            section = dict(section, sections=list(extra["sections"]) + list(section["sections"]))
        by_name[section["name"]] = section
    by_name["duplicates_tree"] = shell.get("duplicates_tree", {})
    return by_name, {p["name"]: p for p in panels["sections"]}, shell.get("entity_actions", {})


def rgba(rgb) -> tuple[int, int, int, int]:
    """A trace colour as an RGBA tuple (the traces carry RGB)."""
    r, g, b = (int(c) for c in tuple(rgb)[:3])
    return (r, g, b, 255)


class ProvenanceContent(NodeContentRenderer):
    """Provenance nodes as discs labelled by their record id, edges coloured by relationship.

    The kind (artifact / operation) is the disc's colour and, with the id, the
    hover tooltip; leaving it out of the label keeps the label short enough not
    to be elided under a disc.
    """

    def node_shape(self, node):
        return nodes.NodeShape.DISC, str(node.config.get("node_id") or node.title), 21

    def node_style(self, node):
        kind = node.config.get("node_type", "")
        colour = {"artifact": (70, 130, 175), "operation": (175, 120, 60)}.get(kind, (110, 140, 110))
        return (*colour, 255)

    def port_label(self, node, port, is_output):
        return ""

    def link_style(self, edge):
        colour = tuple(edge.config.get("color", (140, 150, 160)))[:3]
        return (*colour, 255), 1.5, True


class MMFDBAdminApp(ImApp):
    """The MMFDB Admin window."""

    window_title = "MMFDB Admin"
    window_size = (1200, 800)

    def __init__(
        self,
        model: AdminModel | None = None,
        *,
        client: Any = None,
        runner: Runner | None = None,
        autoconnect: bool = True,
    ) -> None:
        self.model = model or AdminModel(client=client, runner=runner)
        self.shell, self.panel_specs, self.entity_actions = load_specs()
        self.autoconnect = autoconnect
        self.forms: dict[str, FormState] = {}
        self.item_rects: dict[str, tuple] = {}
        self.windows: dict[int, DialogWindow] = {}
        self.file_dialog: FileDialog | None = None
        self._file_then = None
        self.top_h = 64.0
        #: Fraction of an entity panel (and of the Spectra panel) given to the table.
        self.splits = {"entity": 0.5, "spectra": 0.42, "spectra_plot": 0.45, "provenance": 0.62}
        self.graph = GraphControl(read_only=True, content=ProvenanceContent(), on_select=self._graph_selected)
        self.graph._box = (0.0, 0.0, 0.0, 0.0)
        self._graph_revision = -1
        self._graph_focus = False
        self._entity_buttons: dict[str, dict] = {}
        self._last_panel = ""
        self._last_selected: dict[str, str] = {}
        self.help_window = EmTkHelpWindow(title="MMFDB Admin — Help", resource=HERE / "help.md", owner=self)
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=self._target_rect,
        )
        super().__init__(self.render, continuous=False)

    # ── forms and targets ──────────────────────────────────────────────
    def form(self, name: str) -> FormState:
        state = self.forms.get(name)
        if state is None:
            state = self.forms[name] = FormState(on_used=self._used)
        return state

    def _used(self, name: str) -> None:
        self.tour.notify_used(name)

    def _target_rect(self, key: str):
        if key in self.item_rects:
            return self.item_rects[key]
        for state in self.forms.values():
            if key in state.rects:
                return state.rects[key]
        return None

    def remember_item(self, name: str) -> None:
        self.item_rects[name] = tuple(im.get_item_rect())

    # ── frame ──────────────────────────────────────────────────────────
    def animating(self) -> bool:
        return bool(super().animating() or self.model.busy)

    def render(self) -> None:
        model = self.model
        if self.autoconnect:
            self.autoconnect = False
            model.start()
        model.poll()
        for state in self.forms.values():
            state.rects.clear()
        self.item_rects.clear()
        if model.selected != self._last_panel:
            self._last_panel = model.selected
            model.select(model.selected)
        width, height = im.get_main_viewport().size
        self._draw_top(width)
        rail_w = min(RAIL_W, width * 0.26)
        body_h = max(1.0, height - self.top_h - BAR_H)
        self._draw_rail((0.0, self.top_h, rail_w, body_h))
        self._draw_panel((rail_w, self.top_h, width - rail_w, body_h))
        self._draw_status((0.0, height - BAR_H, width, BAR_H))
        frame = (0.0, 0.0, width, height)
        self._draw_dialogs(frame)
        self._serve_requests()
        self._draw_file_dialog()
        self.help_window.draw(frame)
        self.tour.draw(width, height)

    # ── menu bar and toolbar ───────────────────────────────────────────
    def _draw_top(self, width: float) -> None:
        model = self.model
        im.begin("##mmfdb_top", (0.0, 0.0, width, self.top_h))
        if im.begin_main_menu_bar():
            if im.begin_menu("File"):
                for label, action, tip in (
                    ("Import...", model.import_file,
                     "Import a PDBx / PDB-IHM / FLR CIF file into the MMFDB."),
                    ("Export selected sample...", model.export_selected_sample,
                     "Export the sample selected in Samples as an FLR CIF file (validated first)."),
                    ("Backup database...", model.backup_database,
                     "Write a backup copy of the active MMFDB database."),
                    ("Reset", model.reset_database,
                     "Replace the user database with the curated source (asks first; a backup is written)."),
                ):
                    if im.menu_item(label, enabled=model.connected):
                        action()
                    im.set_item_tooltip(tip)
                im.separator()
                if im.menu_item("Close"):
                    self.request_close()
                im.set_item_tooltip("Close the MMFDB Admin window.")
                im.end_menu()
            if im.begin_menu("Settings"):
                if im.menu_item("Reset window layout"):
                    self.reset_layout()
                im.set_item_tooltip("Restore the default panel splits and open the Overview.")
                im.end_menu()
            if im.begin_menu("Help"):
                if im.menu_item("Help..."):
                    self.help_window.show()
                im.set_item_tooltip("Read how MMFDB Admin works.")
                if im.menu_item("Guide"):
                    self.tour.start()
                im.set_item_tooltip("A step-by-step walk through signing in, picking a panel and editing a record.")
                if im.menu_item("About mmfdb-admin"):
                    model.show_about()
                im.set_item_tooltip("The version, the connection and the database in use.")
                im.end_menu()
            im.end_main_menu_bar()
        draw_sections(self.shell["toolbar"]["sections"], model, self.form("toolbar"),
                      n_col=5, titles=False, indent_wraps=False)
        im.same_line()
        self._draw_dot()
        # The database actions and Help / Guide follow on the same line when they fit.
        actions = self.shell["database_actions"]["sections"][0]["buttons"]
        pad = 2.0 * im.get_style().frame_padding[0] + im.get_style().item_inner_spacing[0]
        needed = sum(im.calc_text_size(b["label"])[0] + pad for b in actions)
        needed += im.calc_text_size("Help")[0] + im.calc_text_size("Guide")[0] + 4 * pad + 24.0
        im.same_line()
        if im.get_content_region_avail()[0] < needed:
            im.new_line()
        draw_sections(self.shell["database_actions"]["sections"], model, self.form("database"), titles=False)
        im.same_line()
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip("Read how MMFDB Admin works: the connection, the panels, editing and the dialogs.")
        self.remember_item("help")
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("A step-by-step walk through signing in, picking a panel and editing a record.")
        self.remember_item("guide")
        self.top_h = max(48.0, float(im.get_cursor_screen_pos()[1]) + 4.0)
        im.end()

    def _draw_dot(self) -> None:
        model = self.model
        size = im.get_frame_height()
        x, y = im.get_cursor_screen_pos()
        im.dummy((size, size))
        draw = im.get_window_draw_list()
        draw.add_circle_filled((x + size / 2, y + size / 2), size * 0.3, model.connection_colour())
        im.set_item_tooltip(model.connection_tip())
        self.remember_item("status_dot")
        label = model.login_user if model.connected else ""
        if label:
            im.same_line()
            im.text_unformatted(label)
            im.set_item_tooltip(model.connection_tip())

    def reset_layout(self) -> None:
        """Settings > Reset window layout: the default panel splits and the Overview."""
        self.splits = {"entity": 0.5, "spectra": 0.42, "spectra_plot": 0.45, "provenance": 0.62}
        self.model.search = ""
        self.model.select("overview")

    # ── rail ───────────────────────────────────────────────────────────
    def _draw_rail(self, box) -> None:
        model = self.model
        x, y, w, h = box
        im.begin("##mmfdb_rail", box)
        im.set_next_item_width(w - 16.0)
        _, model.search = im.input_text("##mmfdb_search", model.search, hint="Search...")
        im.set_item_tooltip("Find a panel by name or description.")
        self.remember_item("search")
        cx, cy = im.get_cursor_screen_pos()
        im.begin_child("##mmfdb_rail_list", (cx, cy, w - 8.0, max(20.0, y + h - cy - 4.0)))
        rows = model.rail()
        for kind, value in rows:
            if kind == "group":
                im.text_disabled(value)
                continue
            if im.selectable(f"{model.panel_name(value)}##nav_{value}", model.selected == value, size=(w - 24.0, 24.0)):
                model.select(value)
                self.tour.notify_used("nav." + value)
            im.set_item_tooltip(model.panel_description(value))
            self.remember_item("nav." + value)
        if not any(kind == "panel" for kind, _ in rows):
            im.text_wrapped("No matching panels.")
        im.end_child()
        im.end()

    # ── status bar ─────────────────────────────────────────────────────
    def _draw_status(self, box) -> None:
        model = self.model
        im.begin("##mmfdb_status", box)
        im.text_unformatted(model.status if not model.busy else "Working...")
        im.set_item_tooltip("The last thing that happened.")
        self.remember_item("status")
        im.same_line(max(160.0, box[2] * 0.36))
        im.begin_disabled(not model.can_step(-1))
        if im.button("Back"):
            model.step(-1)
        im.set_item_tooltip("Open the previous panel of the rail.")
        self.remember_item("back")
        im.end_disabled()
        im.same_line()
        im.begin_disabled(not model.can_step(1))
        if im.button("Next"):
            model.step(1)
        im.set_item_tooltip("Open the next panel of the rail.")
        self.remember_item("next")
        im.end_disabled()
        im.same_line()
        summary = model.current.status_line() or model.database_summary
        shown = self._fit(summary, im.get_content_region_avail()[0])
        im.text_unformatted(shown)
        im.set_item_tooltip("\n".join(t for t in (summary, model.database_summary) if t)
                            or "The open panel's state.")
        self.remember_item("summary")
        im.end()

    @staticmethod
    def _fit(text: str, width: float) -> str:
        """*text* cut with an ellipsis to fit *width* (the full text is the tooltip)."""
        if im.calc_text_size(text)[0] <= width:
            return text
        while len(text) > 1 and im.calc_text_size(text + "…")[0] > width:
            text = text[:-1]
        return text + "…"

    # ── panels ─────────────────────────────────────────────────────────
    def _draw_panel(self, box) -> None:
        model = self.model
        key = model.selected
        panel = model.current
        x, y, w, h = box
        im.begin("##mmfdb_panel", box)
        im.text_unformatted(model.panel_name(key))
        im.same_line()
        description = model.panel_description(key)
        im.text_disabled(self._fit(description, im.get_content_region_avail()[0] - 4.0))
        im.set_item_tooltip(description)
        if not model.connected:
            im.text_wrapped(
                "Not connected. Enter the server and your user above and press Login."
                if model.connection != "denied"
                else "Signed in, but this account is not an MMFDB administrator."
            )
        cx, cy = im.get_cursor_screen_pos()
        inner = (cx, cy, w - (cx - x) - 6.0, max(40.0, y + h - cy - 4.0))
        if panel.spec == "entity":
            self._draw_entity(panel, inner)
        elif key == "spectra":
            self._draw_spectra(panel, inner)
        elif key == "provenance":
            self._draw_provenance(panel, inner)
        else:
            im.begin_child(f"##panel_{key}", inner)
            state = self.form(key)
            draw_sections(self.panel_specs[key]["sections"], panel, state, titles=True)
            self._sync_spec_tables(key, panel, state)
            im.end_child()
        im.end()

    def _split(self, name: str, box, minimum: float = 80.0) -> tuple[tuple, tuple]:
        """Two stacked boxes of *box* with a draggable bar between them (fraction in :attr:`splits`)."""
        x, y, w, h = box
        top = max(minimum, min(h - minimum, h * self.splits[name]))
        im.begin_child(f"##split_top_{name}", (x, y, w, top), scrollable=False)
        return (x, y, w, top), (x, y + top + 8.0, w, max(20.0, h - top - 8.0))

    def _bar(self, name: str, box_top, total: tuple) -> None:
        x, y, w, h = total
        im.set_cursor_screen_pos((x, box_top[1] + box_top[3]))
        moved, top, _rest = im.splitter(f"##bar_{name}", im.Axis.Y, 8.0, w, box_top[3], h - box_top[3] - 8.0, 60.0, 60.0)
        if moved and h > 0:
            self.splits[name] = top / h

    def entity_toolbar(self, panel) -> dict:
        section = self._entity_buttons.get(panel.key)
        if section is None:
            base = self.shell["entity"]["sections"][0]
            buttons = [b for b in base["buttons"] if panel.writable]
            buttons += self.entity_actions.get(panel.key, [])
            section = self._entity_buttons[panel.key] = dict(base, buttons=buttons)
        return section

    def _draw_entity(self, panel, box) -> None:
        state = self.form(f"entity:{panel.key}")
        x, y, w, h = box
        toolbar = self.entity_toolbar(panel)
        if toolbar["buttons"]:
            draw_sections([toolbar], panel, state, titles=False)
        cx, cy = im.get_cursor_screen_pos()
        area = (x, cy, w, max(120.0, y + h - cy))
        top, bottom = self._split("entity", area)
        draw_sections([self.shell["entity"]["sections"][1]], panel, state, titles=False)
        self._sync_selection(state, "table_rows", panel.selected_id)
        if "table_rows" in state.rects:
            self.item_rects["row_selected"] = state.rects["table_rows"]
        if panel.selected_id and self._last_selected.get(panel.key) != panel.selected_id:
            self.tour.notify_used("row_selected")
        self._last_selected[panel.key] = panel.selected_id
        im.end_child()
        self._bar("entity", top, area)
        im.begin_child(f"##entity_form_{panel.key}", bottom)
        if not panel.selected_id:
            im.text_disabled("Pick a row to see and edit its fields." if panel.rows else "No records.")
        draw_sections(panel.form_sections(), panel.form, state, n_col=2, titles=False)
        im.end_child()

    def _sync_spec_tables(self, key: str, panel, state: FormState) -> None:
        """Show a spec-drawn panel's ``selected`` in each of its pickable tables.

        Protocols, Studies, Reagent Lots and Pipelines keep the picked row's key in
        ``panel.selected``; when the model sets it (a jump, a new record, a refresh) the table
        must highlight that row too, as the entity panels and Spectra already do.
        """
        selected = getattr(panel, "selected", None)
        if not isinstance(selected, str):
            return
        for section in self.panel_specs[key]["sections"]:
            options = section.get("options") or {}
            if options.get("selected_call") and options.get("source"):
                self._sync_selection(state, options["source"], selected)

    @staticmethod
    def _sync_selection(state: FormState, source: str, key: str) -> None:
        """Show the model's selection in a table (a jump, a new record)."""
        binding = state.tables.get(source)
        if binding is None:
            return
        wanted = key or None
        if binding.control.selected_key != wanted:
            binding.control.select_key(wanted)

    # ── Spectra ────────────────────────────────────────────────────────
    def _draw_spectra(self, panel, box) -> None:
        state = self.form("spectra")
        sections = self.panel_specs["spectra"]["sections"]
        x, y, w, h = box
        head = [s for s in sections if s.get("type") != "custom" and s.get("source") != "items_text"]
        table = next(s for s in sections if s.get("key") == "data_table")
        draw_sections(head, panel, state, titles=False)
        cx, cy = im.get_cursor_screen_pos()
        area = (x, cy, w, max(160.0, y + h - cy - 22.0))
        top, bottom = self._split("spectra", area)
        draw_sections([table], panel, state, titles=False)
        self._sync_selection(state, "component_rows", panel.selected_id)
        im.end_child()
        self._bar("spectra", top, area)
        plot_h = max(90.0, bottom[3] * self.splits["spectra_plot"])
        im.set_cursor_screen_pos((bottom[0], bottom[1]))
        self.plot("spectra_plot", panel.traces, (bottom[0], bottom[1], w, plot_h),
                  "Wavelength (nm)", "Normalized", "Pick a component to see its spectra.")
        im.begin_child("##spectra_form", (bottom[0], bottom[1] + plot_h + 4.0, w, max(30.0, bottom[3] - plot_h - 4.0)))
        draw_sections(panel.form_spec()["sections"], panel.values, self.form("spectra_form"), n_col=2, titles=False)
        im.end_child()
        im.set_cursor_screen_pos((x, area[1] + area[3] + 2.0))
        im.text_unformatted(panel.items_text())
        im.set_item_tooltip("How many items are listed (of how many in the database).")

    def plot(self, name: str, traces: list[dict], box, x_label: str, y_label: str, empty: str) -> None:
        """Spectrum traces in a plot filling *box* (the hand-drawn part of the Spectra panel)."""
        x, y, w, h = box
        im.set_cursor_screen_pos((x, y))
        if not traces:
            im.dummy((w, h))
            draw = im.get_window_draw_list()
            draw.add_rect((x, y), (x + w, y + h), (140, 140, 140, 120))
            tw = im.calc_text_size(empty)[0]
            draw.add_text((x + (w - tw) / 2, y + h / 2 - 8), (130, 130, 130, 255), empty)
            im.set_item_tooltip("The spectra plot: pick a row, or tick several to overlay them.")
            self.item_rects[name] = (x, y, w, h)
            return
        if implot.begin_plot(f"##{name}", size=(w, h)):
            implot.setup_axes(x_label, y_label)
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
            for trace in traces:
                implot.set_next_line_style(rgba(trace.get("color", (128, 128, 128))),
                                           float(trace.get("width", 2)),
                                           DASHES.get(str(trace.get("style", "solid"))))
                implot.plot_line(str(trace.get("name", "")), np.asarray(trace["x"], float),
                                 np.asarray(trace["y"], float))
            implot.end_plot()
        self.item_rects[name] = (x, y, w, h)

    # ── Provenance ─────────────────────────────────────────────────────
    def _graph_selected(self, kind, node) -> None:
        if kind == "node":
            self.model.panel("provenance").select_node(getattr(node, "id", node))

    def _draw_provenance(self, panel, box) -> None:
        state = self.form("provenance")
        sections = self.panel_specs["provenance"]["sections"]
        x, y, w, h = box
        draw_sections(sections[:2], panel, state, titles=False)
        cx, cy = im.get_cursor_screen_pos()
        left_w = max(200.0, (w - 8.0) * self.splits["provenance"])
        rest_h = max(120.0, y + h - cy)
        im.begin_child("##prov_left", (x, cy, left_w, rest_h), scrollable=False)
        draw_sections([sections[2]], panel, state, titles=False)
        gx, gy = im.get_cursor_screen_pos()
        gbox = (gx, gy, left_w - 4.0, max(60.0, cy + rest_h - gy - 4.0))
        if panel.revision != self._graph_revision:
            self._graph_revision = panel.revision
            self.graph.set_document(GraphDocument.from_dict(panel.document))
            self.graph._box = gbox
            self.graph.fit()
        if tuple(self.graph._box[2:]) != tuple(gbox[2:]):
            self.graph._box = gbox
            self.graph.fit()
        self.graph._box = gbox
        self.graph.io = self.io
        self.graph._draw_graph(gbox)
        self.item_rects["provenance_graph"] = gbox
        hovered = nodes.is_node_hovered(self.graph.editor)
        if hovered is not None:
            node = self.graph.document.node_for_number(hovered)
            if node is not None:
                im.get_current_context().set_tooltip(f"{node.title}\n{node.id}", owner=("mmfdb_node", node.id))
        elif self._inside(gbox, *self.io.mouse_pos):
            im.get_current_context().set_tooltip(
                "The provenance graph: click a node to see its record; the wheel zooms, Alt-drag pans.",
                owner="mmfdb_graph",
            )
        im.end_child()
        im.set_cursor_screen_pos((x + left_w + 8.0, cy))
        im.begin_child("##prov_right", (x + left_w + 8.0, cy, w - left_w - 8.0, rest_h))
        draw_sections([sections[4]], panel, state, titles=False)
        im.end_child()

    @staticmethod
    def _inside(box, px, py) -> bool:
        x, y, w, h = box
        return x <= px < x + w and y <= py < y + h

    # ── dialogs ────────────────────────────────────────────────────────
    def _draw_dialogs(self, frame) -> None:
        live = {id(d) for d in self.model.dialogs}
        for key in list(self.windows):
            if key not in live:
                self.windows.pop(key)
                self.forms.pop(f"dialog:{key}", None)
        for dialog in list(self.model.dialogs):
            window = self.windows.get(id(dialog))
            if window is None:
                window = self.windows[id(dialog)] = DialogWindow(
                    dialog.title, size=dialog.size, key=f"mmfdb_{id(dialog)}",
                    fit_height=dialog.spec not in ("duplicates", "analysis_details"),
                )
                window.show()
            window.title = dialog.title
            pressed = window.begin(frame)
            state = self.form(f"dialog:{id(dialog)}")
            if dialog.spec == "duplicates":
                state.custom["duplicates_body"] = self._draw_duplicates_body
            draw_sections(self.shell[dialog.spec]["sections"], dialog, state, titles=dialog.spec == "analysis_details")
            window.end()
            for name, rect in state.rects.items():
                self.item_rects[f"dialog.{name}"] = rect
            if pressed == "close" and dialog in self.model.dialogs:
                dialog.cancel()

    def _draw_duplicates_body(self, section, dialog, state, width) -> None:
        x, y = im.get_cursor_screen_pos()
        avail_h = max(200.0, im.get_content_region_avail()[1] - 40.0)
        left_w = width * 0.45
        im.begin_child("##dup_tree", (x, y, left_w, avail_h), scrollable=False)
        tree = dict(self.shell["duplicates_tree"])
        draw_sections([{"type": "custom", "key": "data_table", "title": "",
                        "description": "The duplicate groups.", "options": tree}], dialog, state, titles=False)
        im.end_child()
        rx = x + left_w + 8.0
        rw = width - left_w - 8.0
        comparison = dialog.comparison()
        im.begin_child("##dup_right", (rx, y, rw, avail_h))
        im.text_unformatted("Spectra Comparison")
        if not comparison:
            im.text_wrapped("Pick a group or a probe to compare its spectra.")
        for stype, traces in comparison:
            # The caption names the plot under it (drawn after, it read as the next plot's title).
            im.text_unformatted(f"{stype.title()} Spectrum")
            px, py = im.get_cursor_screen_pos()
            self.plot(f"dup_{stype}", traces, (px, py, rw - 12.0, 170.0), "Wavelength", "Intensity", "")
        im.separator()
        im.text_unformatted(dialog.metadata_text())
        im.end_child()
        im.set_cursor_screen_pos((x, y + avail_h + 4.0))
        state.rects["duplicates_body"] = (x, y, width, avail_h)

    # ── host requests ──────────────────────────────────────────────────
    def _serve_requests(self) -> None:
        model = self.model
        while model.copies:
            im.set_clipboard_text(model.copies.pop(0))
        if model.file_request is not None and self.file_dialog is None:
            title, mode, filename, filters, then = model.file_request
            model.file_request = None
            self.file_dialog = FileDialog(title, mode=mode, filename=filename, filters=filters)
            self._file_then = then

    def _draw_file_dialog(self) -> None:
        if self.file_dialog is None:
            return
        if im.begin(self.file_dialog.title):
            result = self.file_dialog.draw()
            if result:
                then, self._file_then = self._file_then, None
                self.file_dialog = None
                if then is not None:
                    then(str(result[0]))
            elif result is False:
                self.file_dialog = None
                self._file_then = None
        im.end()

    # ── input routed to the graph ──────────────────────────────────────
    def _over_window(self) -> bool:
        return bool(self.model.dialogs or self.help_window.open or self.file_dialog is not None)

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        super().pointer_press(x, y, button, modifiers, clicks)
        self._graph_focus = (
            self.model.selected == "provenance" and self._inside(self.graph._box, x, y)
            and not self._over_window()
        )
        if self._graph_focus and button == 1:
            gx, gy, gw, gh = self.graph._box
            self.graph.io = self.io
            self.graph.press(x, y, gx, gy, gw, gh, modifiers=modifiers, clicks=clicks)

    def pointer_release(self, x, y, button, modifiers=0):
        super().pointer_release(x, y, button, modifiers)
        if self._graph_focus:
            self.graph.release()
        self._graph_focus = False

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        super().pointer_move(x, y, buttons, modifiers)
        if self._graph_focus and getattr(self.graph, "_panning", False):
            self.graph.drag(x, y)

    # ── persistence ────────────────────────────────────────────────────
    def export_settings(self) -> dict:
        """What is remembered: the open panel and the splits (never a password)."""
        model = self.model
        return {"selected": model.selected, "splits": dict(self.splits),
                "host": model.host, "port": model.port, "user": model.user}

    def restore_settings(self, settings: dict) -> None:
        settings = settings or {}
        model = self.model
        if settings.get("selected") in model.panel_keys():
            model.selected = settings["selected"]
        for key, value in (settings.get("splits") or {}).items():
            if key in self.splits:
                self.splits[key] = float(value)

    def close(self) -> None:
        self.model.close()


def make_app() -> MMFDBAdminApp:
    """Build the MMFDB Admin app (the manifest's ``entrypoints.emtk``)."""
    return MMFDBAdminApp()
