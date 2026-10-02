"""Native light-path editor with original graph editing and spectral bodies."""

import copy
import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.docking import DockManager, Region, Split
from emtk.im_core import Col

ACCENT_GREEN = (46, 160, 67, 255)
from emtk import nodes as _nodes

from chisurf.core.optical_configuration import _graph_to_config, extract_forster
from chisurf.emtk.node_editor.control import GraphControl
from chisurf.emtk.optical_configuration import OpticalConfigurationWidget

from .controller import LightPathController
from .emtk_view import BeampathContent
from .node_types import optical_registry

RIGHT_BUTTON = 2


class TextInputDialog:
    """A small modal text prompt (rename and the like), drawn in-canvas."""

    def __init__(self, title: str, label: str, value: str = "", on_ok=None) -> None:
        self.title = title
        self.label = label
        self.value = str(value)
        self.on_ok = on_ok

    def draw(self) -> bool:
        """Render one frame; True when the dialog is finished."""
        done = False
        im.set_next_window_pos(
            (im.get_main_viewport().size[0] / 2.0 - 180.0, 200.0), im.Cond.APPEARING
        )
        im.set_next_window_size((360.0, 0.0), im.Cond.APPEARING)
        if im.begin(self.title, close_button=True):
            im.text(self.label)
            _, self.value = im.input_text("##prompt_value", self.value)
            im.spacing()
            if im.button("OK"):
                if callable(self.on_ok) and self.value.strip():
                    self.on_ok(self.value.strip())
                done = True
            im.same_line()
            if im.button("Cancel"):
                done = True
        else:
            done = True
        im.end()
        return done


class OpticalGraphControl(GraphControl):
    """The optical graph, with right-click context menus.

    Right-click a node for node actions (rename, duplicate, delete), the
    canvas for graph actions (add a component, arrange, fit) -- the mouse
    vocabulary every node editor speaks, and what the palette buttons cover
    only half of.
    """

    #: Set while a context popup is open: ('node', node_id) or ('canvas', grid_pos).
    context: tuple | None = None

    def press(self, px: float, py: float, *box, modifiers: int = 0, clicks: int = 1) -> None:
        modifiers, clicks = self._trailing(box, modifiers, clicks)
        if clicks == 1 and not modifiers and not self.read_only and px >= self._box[0]:
            # The host delivers presses outside any frame, so the menu is only
            # *requested* here: the next draw_context_menu() opens it. Which
            # node was hit is resolved there too -- is_node_hovered reads the
            # editor's last drawn frame, the freshest hit-test there is.
            self.context = ("pending", px, py)
            return
        super().press(px, py, box, modifiers=modifiers, clicks=clicks)

    def draw_context_menu(self) -> bool:
        """Open and render the context popup a right-press requested."""
        if self.context is None:
            return False
        if self.context[0] == "pending":
            _, px, py = self.context
            number = _nodes.is_node_hovered(self.editor)
            node = self.document.node_for_number(number) if number is not None else None
            # (kind, payload, screen position) -- the anchor for the popup.
            self.context = (
                ("node", node.id, (px, py)) if node is not None else ("canvas", None, (px, py))
            )
        kind, payload, (px, py) = self.context
        im.get_current_context().open_context_popup("##optical_context", (px, py))
        if not im.begin_popup("##optical_context"):
            self.context = None  # dismissed without a pick
            return False
        if kind == "node":
            self._draw_node_menu(payload)
        else:
            self._draw_canvas_menu((px, py))
        im.end_popup()
        self.context = None
        return False

    def _menu_row(self, label: str, tooltip: str, action) -> None:
        if im.selectable(label):
            try:
                action()
            except Exception as exc:
                if self.host_app is not None:
                    self.host_app.controller.status = f"Error: {exc}"
        im.set_item_tooltip(tooltip)

    def _draw_node_menu(self, node_id: str) -> None:
        node = self.host_app.controller.document.node(node_id)
        if node is None:
            return
        im.separator_text(node.title)
        self._menu_row(
            "✎ Rename…", "Type a new title for this node.", lambda: self.rename_node_dialog(node_id)
        )
        self._menu_row(
            "⧉ Duplicate",
            "Copy this node and its component settings beside the original.",
            lambda: self.duplicate_node(node_id),
        )
        im.separator()
        self._menu_row(
            "🗑 Delete node",
            "Remove this node and its connections.",
            lambda: self.delete_node(node_id),
        )

    def _draw_canvas_menu(self, screen_pos: tuple) -> None:
        im.separator_text("Add to graph")
        for descriptor in optical_registry.all_types().values():
            self._menu_row(
                f"+ {descriptor.title}",
                f"Add a {descriptor.title.lower()} node at the clicked position.",
                lambda d=descriptor, s=screen_pos: self.add_component_at(d.id, s),
            )
        im.separator()
        self._menu_row(
            "Arrange optical graph",
            "Lay out nodes by optical signal flow.",
            self.host_app.controller.arrange,
        )
        self._menu_row("Fit graph to view", "Frame the entire beam path.", self.fit)

    # -- the actions the menus share with the palette --

    def rename_node_dialog(self, node_id: str) -> None:
        app = self.host_app
        node = app.controller.document.node(node_id)
        if app is None or node is None:
            return
        app.dialog = TextInputDialog(
            "Rename node",
            "Node title:",
            node.title,
            on_ok=lambda value: self._rename_node(node_id, value),
        )

    def _rename_node(self, node_id: str, title: str) -> None:
        node = self.host_app.controller.document.node(node_id)
        if node is not None and title.strip():
            node.title = title.strip()
            self.controller.changed()

    def duplicate_node(self, node_id: str) -> None:
        node = self.controller.document.node(node_id)
        if node is None:
            return
        import copy as _copy
        import uuid as _uuid

        from chisurf.emtk.node_editor.document import GraphNode

        copy_node = GraphNode(
            _uuid.uuid4().hex,
            node.type,
            f"{node.title} copy",
            node.inputs,
            node.outputs,
            _copy.deepcopy(node.config),
            (node.pos[0] + 40.0, node.pos[1] + 40.0),
        )
        self.controller.document.add_node(copy_node)
        self.controller.changed()

    def delete_node(self, node_id: str) -> None:
        self.host_app.controller.remove_node(node_id)

    def add_component_at(self, type_id: str, screen_pos: tuple) -> None:
        grid = self.editor.canvas.to_grid(screen_pos)
        self.host_app._call(self.host_app.controller.add_node, type_id, grid)


class LightPathApp(ImApp):
    def __init__(self, db_path=None, client=None, state_path=None, owner_id="lightpath"):
        self.controller = LightPathController(db_path, client, state_path, owner_id)
        self.content = BeampathContent()
        self.graph_control = OpticalGraphControl(
            self.controller.document, content=self.content, on_change=self.controller.changed
        )
        self.graph_control.host_app = self
        self.graph_control.controller = self.controller
        self.easy = OpticalConfigurationWidget(
            _graph_to_config(self.controller.graph()), on_changed=self.controller.apply_easy
        )
        self.easy.refresh_probes = lambda: self.controller.start("catalogue")
        self.easy.simulate = self._simulate_easy
        self.easy.on_open_graph = lambda: self.docks.focus("graph")
        self.controller.on_document = self._set_document
        self.controller.on_easy_sync = self._sync_easy
        self.controller.on_probes = self._set_probes
        self.controller.on_result = self._adopt_result
        self.dialog = None
        self.dialog_action = "load"
        self.selected_node = ""
        self.source_node = self.target_node = ""
        self.source_port = self.target_port = 0
        self.results_tab = "Signals"
        #: The MMFDB catalogue is requested once on the first frame -- the old
        #: tool loaded it at startup, and without it the easy setup's spectrum
        #: and sample dropdowns open empty.
        self._catalogue_requested = False
        # The graph is the workspace and fills the canvas; everything else
        # starts as floating tool windows over it. Every window is movable,
        # resizable and dockable -- drag a title bar, or drag a docked tab off
        # its strip, to rearrange or float it.
        self.docks = DockManager(
            Split("h", 0.72, Region("graph"), Region("results")), name="lightpath"
        )
        self.docks.add_window("graph", "Light path graph", self._draw_graph, dock="graph")
        self.docks.add_window(
            "results", "Signals and crosstalk", self._draw_results, dock="results"
        )
        self.docks.add_window(
            "controls",
            "Optical components",
            self._draw_controls,
            box=(16.0, 52.0, 300.0, 540.0),
        )
        self.docks.add_window(
            "easy",
            "Easy optical setup",
            self._draw_easy,
            box=(0.0, 52.0, 340.0, 560.0),
        )
        # The easy window starts at the right edge: positioned on the first
        # frame, when the viewport size is known (the constructor runs outside
        # any frame, so im.get_main_viewport() is unavailable there).
        self._easy_placed = False
        self.graph_control.fit()
        super().__init__(gui=self._render, continuous=False)

    def animating(self) -> bool:
        """Request frames only while there is something to wait for.

        A background job (a simulation, a catalogue load, a queued auto-update)
        needs frames so ``controller.poll()`` can pick it up; an idle editor
        does not -- repainting the graph at full frame rate made the whole UI
        laggy. Editing and dragging repaint through the host's input events.
        """
        controller = self.controller
        if controller.running or controller.pending:
            return True
        return super().animating()

    @staticmethod
    def _button(label, tooltip, callback):
        if im.button(label):
            callback()
        im.set_item_tooltip(tooltip)

    def _call(self, function, *args):
        try:
            return function(*args)
        except Exception as exc:
            self.controller.status = f"Error: {exc}"

    def _set_document(self, document, fit=True):
        canvas = self.graph_control.editor.canvas
        view = (canvas.panning, canvas.zoom, canvas.origin)
        self.graph_control.set_document(document, fit=fit)
        if not fit:
            (
                self.graph_control.editor.canvas.panning,
                self.graph_control.editor.canvas.zoom,
                self.graph_control.editor.canvas.origin,
            ) = view

    def _sync_easy(self, config):
        self.easy.config = copy.deepcopy(config)

    def _set_probes(self, probes):
        self.content.set_probes(probes)
        self.easy.probes = list(probes)
        self.easy.status = f"{len(probes)} optical spectra available."

    def _adopt_result(self, result):
        self.easy.results = result
        self.easy.config["_cached_results"] = {
            "forster": extract_forster(result),
            "crosstalk_matrices": result.get("crosstalk_matrices", {}),
        }

    def _simulate_easy(self):
        self.controller.apply_easy(self.easy.config)
        return self.controller.start()

    def _draw_controls(self, box):
        controller = self.controller
        im.begin_disabled(controller.running)

        # The two headline actions stay at the top, always visible.
        im.push_style_color(Col.BUTTON, ACCENT_GREEN)
        im.push_style_color(Col.BUTTON_HOVERED, (56, 180, 77, 255))
        im.push_style_color(Col.BUTTON_ACTIVE, (36, 140, 57, 255))
        self._button(
            "▶ Simulate light path",
            "Propagate spectra and calculate detector signals, Förster radii and crosstalk.",
            controller.start,
        )
        im.pop_style_color(3)
        im.same_line()
        self._button(
            "⟳ Reset to default",
            "Restore the standard two-color laser/sample/dichroic/detector path.",
            controller.reset,
        )

        im.separator()
        if im.collapsing_header("Backend", 1):
            self._button(
                "Load optical catalogue",
                "Load dye, transmission and detector spectra from the selected backend.",
                lambda: controller.start("catalogue"),
            )
            changed, controller.remote = im.checkbox("Use configured RPC server", controller.remote)
            im.set_item_tooltip(
                "Use the existing ChiSurf/MMFDB connection and session token rather than the local scientific backend."
            )
            im.text("Spectra database path:")
            changed, path = im.input_text("##lightpath_db", controller.db_path or "")
            im.set_item_tooltip(
                "Optional MMFDB spectra database path; leave empty to use the configured database."
            )
            if changed:
                controller.db_path = path or None
            _, controller.auto_update = im.checkbox(
                "Auto update optical changes", controller.auto_update
            )
            im.set_item_tooltip(
                "Queue one fresh simulation after graph or easy-mode parameter edits."
            )

        if im.collapsing_header("Graph files", 1):
            for label, action, tip in (
                ("Load graph", "load", "Open a saved optical graph or easy-mode preset."),
                (
                    "Save graph",
                    "save",
                    "Save nodes, connections, component choices and layout as JSON.",
                ),
                (
                    "Save optical preset",
                    "preset",
                    "Save this optical path for the easy setup editor.",
                ),
                (
                    "Export instrument setting",
                    "instrument",
                    "Export the simulated instrument setting as JSON.",
                ),
            ):
                self._button(label, tip, lambda a=action: self.browse(a))

        if im.collapsing_header("Add optical component", 1):
            for descriptor in optical_registry.all_types().values():
                self._button(
                    descriptor.title,
                    f"Add a {descriptor.title.lower()} node to the graph.",
                    lambda type_id=descriptor.id: self._add_component(type_id),
                )
            self._button(
                "Delete selected graph items",
                "Delete the selected nodes and connections from the optical graph.",
                self._delete_selection,
            )

        if im.collapsing_header("Graph view", 1):
            self._button(
                "Arrange optical graph",
                "Lay out nodes by optical signal flow and frame the complete graph.",
                lambda: self._call(controller.arrange),
            )
            self._button(
                "Fit graph to view",
                "Frame the entire beam path without changing its saved node positions.",
                self.graph_control.fit,
            )
            _, self.graph_control.show_minimap = im.checkbox(
                "Show graph minimap", self.graph_control.show_minimap
            )
            im.set_item_tooltip("Show a small overview for navigating a large optical network.")

        # Collapsed by default: the graph's own ports drag-connect, and this
        # numeric form is the fallback for precise port indices.
        if im.collapsing_header("Connections", 0):
            self._draw_connections()

        if im.collapsing_header("MMFDB", 1):
            im.text("Saved simulation name:")
            _, controller.operation_name = im.input_text(
                "##simulation_name", controller.operation_name
            )
            im.set_item_tooltip("Name stored with the simulation and its MMFDB artifacts.")
            self._button(
                "Save simulation to MMFDB",
                "Persist this graph and its numerical outputs using the existing lightpath backend.",
                lambda: controller.start("save"),
            )
            self._button(
                "Browse saved simulations",
                "List previously stored light-path simulations from MMFDB.",
                lambda: controller.start("list"),
            )
            for record in controller.saved:
                operation = str(record["operation_id"])
                self._button(
                    f"{record.get('name') or operation}##{operation}",
                    "Restore the selected saved graph and numerical result.",
                    lambda key=operation: controller.start("get", key),
                )

        im.end_disabled()
        if controller.running:
            self._button(
                "⏹ Stop backend operation",
                "Discard a pending simulation when its backend call finishes; an MMFDB save completes consistently.",
                controller.stop,
            )
        im.separator()
        status = controller.status or ""
        if status.startswith("Error"):
            im.text_colored(status, (1.0, 0.45, 0.4, 1.0))
        elif controller.running:
            im.text_disabled(f"⏳ {status}")
        else:
            im.text_disabled(status)

    def _add_component(self, type_id):
        x, y, width, height = self.graph_control._box
        position = self.graph_control.editor.canvas.to_grid((x + width / 2, y + height / 2))
        return self._call(self.controller.add_node, type_id, position)

    def _draw_connections(self):
        document = self.controller.document
        ids = [node.id for node in document.nodes]
        if not ids:
            return
        labels = [f"{node.title} [{node.id[:6]}]" for node in document.nodes]
        if self.source_node not in ids:
            self.source_node = ids[0]
        if self.target_node not in ids:
            self.target_node = ids[-1]
        im.text("Connect nodes:")
        im.text("From:")
        im.same_line()
        im.set_next_item_width(-1.0)
        changed, index = im.combo("##source_node", ids.index(self.source_node), labels)
        im.set_item_tooltip("Node producing the optical spectrum or scalar parameter.")
        if changed:
            self.source_node = ids[index]
        im.text("To:")
        im.same_line()
        im.set_next_item_width(-1.0)
        changed, index = im.combo("##target_node", ids.index(self.target_node), labels)
        im.set_item_tooltip("Node that consumes the selected source output.")
        if changed:
            self.target_node = ids[index]
        half = max(im.get_content_region_avail()[0] * 0.5 - 6.0, 60.0)
        im.text("Out port:")
        im.same_line()
        im.set_next_item_width(half)
        _, self.source_port = im.input_int("##source_output", self.source_port)
        im.set_item_tooltip("Zero-based output-port index on the source node.")
        im.same_line()
        im.text("In port:")
        im.same_line()
        im.set_next_item_width(-1.0)
        _, self.target_port = im.input_int("##target_input", self.target_port)
        im.set_item_tooltip("Zero-based input-port index on the target node.")
        if im.button("🔗 Connect ports"):
            self._call(
                self.controller.connect,
                self.source_node,
                self.source_port,
                self.target_node,
                self.target_port,
            )
        im.set_item_tooltip("Create an optical connection; one source may feed each input.")
        if document.edges:
            im.separator()
        for edge in list(document.edges):
            label = f"{edge.source[:6]}:{edge.source_port} → {edge.target[:6]}:{edge.target_port}"
            im.text(label)
            im.same_line()
            if im.small_button(f"✕##{edge.key()}"):
                self.controller.remove_edge(edge)
            im.set_item_tooltip("Remove this optical link.")

    def _delete_selection(self):
        self.graph_control.delete_selection()

    def _draw_graph(self, box):
        self.graph_control._box = box
        self.graph_control.io = self.io
        self.graph_control.read_only = self.controller.running
        self.graph_control._draw_graph(box)
        im.set_item_tooltip(
            "Drag nodes to arrange; drag pins to connect; wheel zooms; select items and use Delete selected graph items to remove them."
        )

    def _draw_easy(self, box):
        im.begin_disabled(self.controller.running)
        self.easy.draw()
        im.end_disabled()

    def _draw_results(self, box):
        result = self.controller.result
        if not result:
            im.text_wrapped(
                "Simulate a configured light path to inspect detector signals and spectral crosstalk."
            )
            return
        if im.begin_tab_bar("lightpath_results"):
            for title in ("Signals", "Excitation", "Emission", "Detected", "Förster radius"):
                opened = im.begin_tab_item(title)
                im.set_item_tooltip(
                    f"Inspect calculated {title.lower()} values for this optical path."
                )
                if opened:
                    if title == "Signals":
                        self._signal_table(result.get("detector_signals", []))
                    elif title == "Förster radius":
                        self.easy._draw_matrix(title, extract_forster(result))
                    else:
                        self.easy._draw_matrix(
                            title, result.get("crosstalk_matrices", {}).get(title.lower(), {})
                        )
                    im.end_tab_item()
            im.end_tab_bar()

    @staticmethod
    def _signal_table(signals):
        columns = ("dye", "detector", "intensity")
        if im.begin_table(
            "optical_signals",
            3,
            im.TableFlags.BORDERS | im.TableFlags.ROW_BG | im.TableFlags.SCROLL_Y,
        ):
            for title in ("Fluorophore", "Detector", "Intensity"):
                im.table_setup_column(title)
            im.table_headers_row()
            for row in signals:
                im.table_next_row()
                for key in columns:
                    im.table_next_column()
                    value = row.get(key, "")
                    im.text(f"{value:.5g}" if isinstance(value, (int, float)) else str(value))
            im.end_table()

    def browse(self, action):
        from emtk.file_dialog import FileDialog

        self.dialog_action = action
        self.dialog = FileDialog(
            "Light-path graph / preset / instrument",
            mode="open" if action == "load" else "save",
            filters=[("Optical JSON", ["*.json"])],
            filename="lightpath.json" if action != "load" else None,
        )

    def _draw_dialog(self):
        if self.dialog is None:
            return
        if isinstance(self.dialog, TextInputDialog):
            if self.dialog.draw():
                self.dialog = None
            return
        if im.begin("Light-path file chooser"):
            result = self.dialog.draw()
            if result:
                action = {
                    "load": self.controller.load_graph,
                    "save": self.controller.save_graph,
                    "preset": self.controller.save_preset,
                    "instrument": self.controller.export_instrument,
                }[self.dialog_action]
                self._call(action, result[0])
                self.dialog = None
            elif result is False:
                self.dialog = None
        im.end()

    def _render(self):
        if not self._easy_placed:
            # First frame: slide the floating easy window to the right edge,
            # clear of the components window on the left. Only when the user
            # has not already moved or docked it (a saved layout restores the
            # window with its own dock id, which this must not override).
            self._easy_placed = True
            easy = self.docks.windows.get("easy")
            if easy is not None and self.docks.region_of("easy") is None:
                x, y, w, h = easy.box or (0.0, 52.0, 340.0, 560.0)
                easy.box = (max(im.get_main_viewport().size[0] - w - 16.0, 16.0), y, w, h)
        if not self._catalogue_requested:
            # First frame: request the MMFDB spectra catalogue, so the easy
            # setup's spectrum/sample dropdowns open populated. The load runs
            # on the controller's executor, so showing the window never blocks
            # on ZMQ -- the same reason the old tool deferred it to a timer.
            self._catalogue_requested = True
            if not self.controller.probes:
                self.controller.start("catalogue")
        self.controller.poll()
        width, height = im.get_main_viewport().size
        self.docks.draw((0.0, 0.0, float(width), float(height)))
        if self.graph_control.draw_context_menu():
            pass  # the popup stays open until a row is picked or focus is lost
        self._draw_dialog()
        self.easy.draw_dialogs((0.0, 0.0, float(width), float(height)))

    def key(self, key, text, modifiers):
        if not self.io.want_text_input and self.graph_control.key(key, text, modifiers):
            return True
        return super().key(key, text, modifiers)

    def export_settings(self):
        return {
            "graph": self.controller.graph(),
            "auto_update": self.controller.auto_update,
            "remote": self.controller.remote,
            "db_path": self.controller.db_path,
            "minimap": self.graph_control.show_minimap,
        }

    def restore_settings(self, settings):
        if isinstance(settings.get("graph"), dict):
            self._call(self.controller.load_document, settings["graph"])
        self.controller.auto_update = bool(settings.get("auto_update", True))
        self.controller.remote = bool(settings.get("remote", self.controller.remote))
        self.controller.db_path = settings.get("db_path", self.controller.db_path)
        self.graph_control.show_minimap = bool(settings.get("minimap", True))

    def pointer_press(self, x, y, button, modifiers=0, clicks=1):
        from emtk.events import ALT_MODIFIER, LEFT_BUTTON

        gx, gy, gw, gh = self.graph_control._box
        if (
            button == LEFT_BUTTON
            and gx <= x <= gx + gw
            and gy <= y <= gy + gh
            and modifiers & ALT_MODIFIER
        ):
            self.graph_control.io = self.io
            self.graph_control.press(x, y, gx, gy, gw, gh, modifiers=modifiers, clicks=clicks)
        else:
            super().pointer_press(x, y, button, modifiers, clicks)

    def pointer_move(self, x, y, buttons=0, modifiers=0):
        if self.graph_control._panning:
            self.graph_control.drag(x, y)
        else:
            super().pointer_move(x, y, buttons, modifiers)

    def pointer_release(self, x, y, button, modifiers=0):
        if self.graph_control._panning:
            self.graph_control.release()
        super().pointer_release(x, y, button, modifiers)

    def press(self, px, py, x=0.0, y=0.0, w=0.0, h=0.0, modifiers=0, clicks=1):
        gx, gy, gw, gh = self.graph_control._box
        if gx <= px <= gx + gw and gy <= py <= gy + gh and modifiers & 0x08000000:
            self.graph_control.io = self.io
            self.graph_control.press(px, py, gx, gy, gw, gh, modifiers=modifiers, clicks=clicks)
        else:
            super().press(px, py, x, y, w, h, modifiers, clicks)

    def drag(self, px, py, *box):
        if self.graph_control._panning:
            self.graph_control.drag(px, py, *box)
        else:
            super().drag(px, py, *box)

    def release(self):
        if self.graph_control._panning:
            self.graph_control.release()
        else:
            super().release()

    def on_paths_dropped(self, paths):
        if paths:
            self._call(self.controller.load_graph, paths[0])

    def close(self):
        self.controller.close()


def create_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return LightPathApp(**kwargs)
