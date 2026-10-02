"""Native light-path editor with original graph editing and spectral bodies."""

import copy
import json
import types
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.im_core import Col
from emtk.docking import DockManager, Region, Split

from emtk import nodes as _nodes

from chisurf.core.optical_configuration import _graph_to_config, extract_forster
from chisurf.emtk.node_editor.control import GraphControl
from chisurf.emtk.optical_configuration import OpticalConfigurationWidget

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow, TourTarget
from emtk.view_form import FormState, draw_form

from .controller import LightPathController
from .emtk_view import BeampathContent
from .node_types import optical_registry
from .panel import LightPathPanel

RIGHT_BUTTON = 2


class _Modal:
    """A titled, closable window over the app (emtk's DialogWindow); subclasses draw :meth:`body`."""

    size = (400.0, 170.0)

    def __init__(self, title: str) -> None:
        self.title = title
        self.finished = False
        self.window = DialogWindow(title, size=self.size, key=title, fit_height=True)
        self.window.show()

    def draw(self, box) -> bool:
        """Render one frame; True when the dialog is finished."""
        pressed = self.window.begin(box)
        self.body()
        self.window.end()
        return self.finished or pressed == "close"

    def body(self) -> None:
        raise NotImplementedError


class TextInputDialog(_Modal):
    """A small modal text prompt (a preset name, a simulation name), drawn in-canvas."""

    def __init__(self, title: str, label: str, value: str = "", on_ok=None) -> None:
        super().__init__(title)
        self.label = label
        self.value = str(value)
        self.on_ok = on_ok

    def body(self) -> None:
        im.text(self.label)
        im.set_next_item_width(-1.0)
        _, self.value = im.input_text("##prompt_value", self.value)
        im.set_item_tooltip("Type the name, then press OK.")
        im.spacing()
        if im.button("OK"):
            if callable(self.on_ok) and self.value.strip():
                self.on_ok(self.value.strip())
            self.finished = True
        im.set_item_tooltip("Use this name. An empty name does nothing.")
        im.same_line()
        if im.button("Cancel"):
            self.finished = True
        im.set_item_tooltip("Close without doing anything.")


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
        """Open the popup a right-press requested and rebuild it every frame while it is open (emtk popups are immediate)."""
        if self.context is None:
            return False
        ctx = im.get_current_context()
        if self.context[0] == "pending":
            _, px, py = self.context
            number = _nodes.is_node_hovered(self.editor)
            node = self.document.node_for_number(number) if number is not None else None
            # (kind, payload, screen position) -- the anchor for the popup.
            self.context = (
                ("node", node.id, (px, py)) if node is not None else ("canvas", None, (px, py))
            )
            ctx.open_context_popup("##optical_context", (px, py))
        kind, payload, (px, py) = self.context
        if not im.begin_popup("##optical_context"):
            self.context = None  # dismissed without a pick
            return False
        if kind == "node":
            self._draw_node_menu(payload)
        else:
            self._draw_canvas_menu((px, py))
        im.end_popup()
        if not ctx.state(("context_popup", "##optical_context")).get("open"):
            self.context = None  # a row was picked or focus was lost
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
        self._menu_row(
            "Rename...", "Type a new title for this node.", lambda: self.rename_node_dialog(node_id)
        )
        self._menu_row(
            "Duplicate",
            "Copy this node and its component settings beside the original.",
            lambda: self.duplicate_node(node_id),
        )
        im.separator()
        self._menu_row(
            "Delete Node",
            "Remove this node and its connections.",
            lambda: self.delete_node(node_id),
        )

    def _draw_canvas_menu(self, screen_pos: tuple) -> None:
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


HERE = Path(__file__).parent
SPEC = json.loads((HERE / "lightpath.view.json").read_text(encoding="utf-8"))


class MessageDialog(_Modal):
    """A small modal message (an error box, a confirmation of what was saved), drawn in-canvas."""

    def __init__(self, title: str, text: str) -> None:
        super().__init__(title)
        self.text = text

    def body(self) -> None:
        im.text_wrapped(self.text)
        im.spacing()
        if im.button("OK"):
            self.finished = True
        im.set_item_tooltip("Close this message.")


class SavedChooser(_Modal):
    """Choose one of the simulations stored in MMFDB (the Qt tool's input-item dialog)."""

    size = (460.0, 330.0)

    def __init__(self, app: "LightPathApp") -> None:
        super().__init__("Load Simulation from MMFDB")
        self.app = app
        self.state = FormState(on_used=app.tour.notify_used)

    def body(self) -> None:
        panel = self.app.panel
        self.state.rects.clear()
        draw_form(SPEC["mmfdb_list"], panel, self.state, titles=False)
        im.begin_disabled(not panel.selected_saved)
        if im.button("Load"):
            panel.load_saved()
            self.finished = True
        im.set_item_tooltip("Load the selected simulation: its graph and its numerical result.")
        im.end_disabled()
        im.same_line()
        if im.button("Cancel"):
            panel.want_list = False
            self.finished = True
        im.set_item_tooltip("Close this list without loading anything.")


class FileChooser(_Modal):
    """The in-app file dialog of a graph, an instrument setting."""

    size = (560.0, 420.0)

    def __init__(self, title: str, mode: str, filename: str | None) -> None:
        super().__init__(title)
        from emtk.file_dialog import FileDialog

        self.dialog = FileDialog(title, mode=mode, filters=[("JSON", ["*.json"])], filename=filename)
        self.result = None

    def body(self) -> None:
        result = self.dialog.draw()
        if result:
            self.result = result[0]
            self.finished = True
        elif result is False:
            self.finished = True


class LightPathApp(TourTarget, ImApp):
    """The light-path simulator window: graph, components, Easy Mode and the simulation results, docked."""

    def __init__(self, db_path=None, client=None, state_path=None, owner_id="lightpath"):
        self.item_rects: dict = {}
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
        self.results_tab = "Signals"
        self._catalogue_requested = False
        self._last_operation = ""
        self._was_running = False
        self.help_window = EmTkHelpWindow(
            title="Light Path Simulator - Help & Reference",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=self.start_guide,
            size=(700.0, 520.0),
        )
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            get_target_rect=lambda key: self.item_rects.get(key),
            owner=self,
            wait_for_controls=True,
        )
        self.panel = LightPathPanel(
            self.controller,
            self.graph_control,
            browse=self.browse,
            ask_name=self.ask_name,
            show_help=self.help_window.show,
            start_guide=self.start_guide,
        )
        self.forms = {name: FormState(on_used=self.tour.notify_used) for name in ("toolbar", "palette", "view", "backend", "connections", "mmfdb", "calc", "table")}
        # Graph | (components and Easy Mode as tabs over the results): every window is docked, none floats over
        # the graph; a title bar can still be dragged to rearrange or float one.
        self.docks = DockManager(
            Split("h", 0.55, Split("v", 0.62, Region("graph"), Region("results")), Region("setup")),
            name="lightpath",
        )
        self.docks.add_window("graph", "Optical Path", self._draw_graph, dock="graph", closable=False)
        self.docks.add_window("controls", "Optical Components", self._draw_controls, dock="setup", closable=False)
        self.docks.add_window("easy", "Easy Mode", self._draw_easy, dock="setup", closable=False)
        self.docks.add_window("results", "Emission Probability", self._draw_results, dock="results", closable=False)
        self.docks.focus("controls")
        self.native_layouts = {"main": self.docks}
        self.graph_control.fit()
        super().__init__(gui=self._render, continuous=False)

    # -- plumbing ------------------------------------------------------------------------------------------ #
    @property
    def form(self):
        """The rectangles every form drew (what the click tests and the tour read)."""
        return types.SimpleNamespace(rects=self.item_rects)

    def animating(self) -> bool:
        """Frames only while a backend job needs polling; an idle editor repaints on input events."""
        controller = self.controller
        if controller.running or controller.pending:
            return True
        return super().animating()

    def start_guide(self) -> None:
        self.tour.start()

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

    def _form(self, name: str, spec: dict, titles: bool = False) -> None:
        state = self.forms[name]
        state.rects.clear()
        draw_form(spec, self.panel, state, titles=titles)
        self.item_rects.update(state.rects)

    # -- windows ------------------------------------------------------------------------------------------- #
    def _draw_graph(self, box):
        self._form("toolbar", SPEC["toolbar"])
        x, y = im.get_cursor_screen_pos()
        gx, gy, gw, gh = box
        top = max(y - gy + 2.0, 0.0)
        canvas = (gx, gy + top, gw, max(gh - top, 40.0))
        self.graph_control._box = canvas
        self.graph_control.io = self.io
        self.graph_control.read_only = self.controller.running
        self.graph_control._draw_graph(canvas)
        io = self.io
        px, py = io.mouse_pos
        if (io.mouse_clicked[1] and not self.controller.running and self.graph_control.context is None
                and canvas[0] <= px <= canvas[0] + canvas[2] and canvas[1] <= py <= canvas[1] + canvas[3]):
            # A right press on the canvas asks for the component menu (the node under it is resolved on the next draw).
            self.graph_control.context = ("pending", px, py)
        im.set_item_tooltip(
            "Drag nodes to arrange; drag pins to connect; wheel zooms; right-click for the component menu; "
            "select items and use Delete Selected to remove them."
        )
        self.item_rects["graph"] = canvas

    def _draw_controls(self, box):
        panel = self.panel
        self._form("palette", SPEC["palette"])
        self._form("palette", SPEC["palette_buttons"])
        self._form("view", SPEC["view"], True)
        self._form("backend", SPEC["backend"], True)
        self._form("connections", SPEC["connections"], True)
        self._form("mmfdb", SPEC["mmfdb"], True)
        self.remember("components", tuple(box))

    def _add_component(self, type_id):
        x, y, width, height = self.graph_control._box
        position = self.graph_control.editor.canvas.to_grid((x + width / 2, y + height / 2))
        return self._call(self.controller.add_node, type_id, position)

    def _draw_easy(self, box):
        im.begin_disabled(self.controller.running)
        # The form's inputs take the whole line otherwise; a short number does not need 500 px.
        im.push_item_width(max(min(float(box[2]) * 0.55, 320.0), 120.0))
        self.easy.draw()
        im.pop_item_width()
        im.end_disabled()
        self.remember("easy", tuple(box))

    def _draw_results(self, box):
        controller = self.controller
        self._form("calc", SPEC["results_buttons"])
        status = controller.status or ""
        if status.startswith("Error"):
            im.push_style_color(Col.TEXT, (255, 115, 100, 255))
            im.text_wrapped(status)
            im.pop_style_color(1)
        elif status:
            im.text_wrapped(status)
        if not controller.result and not controller.running:
            im.text_wrapped("Press Calculate Emission Intensity to simulate the light path; the results appear in these tabs.")
        if im.begin_tab_bar("lightpath_results"):
            for title in self.panel.TABS:
                opened = im.begin_tab_item(title)
                im.set_item_tooltip(f"Inspect the calculated {title.lower()} values for this optical path.")
                if opened:
                    self.results_tab = title
                    key = {"Förster radius": "forster"}.get(title, title.lower())
                    self._form("table", SPEC["tables"][key])
                    im.end_tab_item()
            im.end_tab_bar()
        self.remember("results", tuple(box))

    # -- dialogs and files ----------------------------------------------------------------------------------- #
    def ask_name(self, title, label, value, on_ok):
        self.dialog = TextInputDialog(title, label, value, on_ok=on_ok)

    def browse(self, action):
        self.dialog_action = action
        names = {"load": None, "save": "lightpath.json", "instrument": "instrument_setting.json"}
        self.dialog = FileChooser(
            {"load": "Open Graph", "save": "Save Graph", "instrument": "Export Instrument Setting"}[action],
            "open" if action == "load" else "save",
            names[action],
        )

    def _draw_dialog(self, box):
        if self.dialog is None:
            return
        dialog = self.dialog
        if dialog.draw(box):
            self.dialog = None
            if isinstance(dialog, FileChooser) and dialog.result:
                title, function = {
                    "load": ("Load Failed", self.controller.load_graph),
                    "save": ("Save Failed", self.controller.save_graph),
                    "instrument": ("Export Failed", self.controller.export_instrument),
                }[self.dialog_action]
                self.panel._try(title, function, dialog.result)
                if self.dialog_action == "load":
                    self.graph_control.fit()

    def _after_poll(self):
        """Announce what a finished backend call means to the user, as the Qt tool's message boxes did."""
        controller, panel = self.controller, self.panel
        if panel.message is not None and not isinstance(self.dialog, MessageDialog):
            title, text = panel.message
            panel.message = None
            self.dialog = MessageDialog(title, text)
        running = controller.running
        if self._was_running and not running:
            action = getattr(controller, "_action", "")
            failed = controller.status.startswith("Error")
            if action == "save" and not failed and controller.last_operation_id != self._last_operation:
                self._last_operation = controller.last_operation_id
                self.dialog = MessageDialog("Saved to MMFDB", f"Saved operation {controller.last_operation_id}")
            elif action in ("save", "list", "get") and failed:
                self.dialog = MessageDialog({"save": "MMFDB Save Failed"}.get(action, "MMFDB Load Failed"), controller.status[7:])
            elif action == "list" and panel.want_list:
                if controller.saved:
                    panel.selected_saved = ""
                    self.dialog = SavedChooser(self)
                else:
                    panel.want_list = False
                    self.dialog = MessageDialog("MMFDB", "No saved light path simulations found.")
            elif action == "get" and not failed:
                self.graph_control.fit()
        self._was_running = running

    def _render(self):
        if not self._catalogue_requested:
            # First frame: request the spectra catalogue so the component choosers open populated; it runs on the
            # controller's executor, so showing the window never blocks on the backend.
            self._catalogue_requested = True
            if not self.controller.probes:
                self.controller.start("catalogue")
        self.controller.poll()
        self._after_poll()
        width, height = im.get_main_viewport().size
        box = (0.0, 0.0, float(width), float(height))
        self._follow_tour()
        self.docks.draw(box)
        if self.graph_control.draw_context_menu():
            pass  # the popup stays open until a row is picked or focus is lost
        self._draw_dialog(box)
        self.easy.draw_dialogs(box)
        self.help_window.draw(box)
        self.tour.draw(float(width), float(height))

    def _follow_tour(self):
        """Bring the tab forward while a tour step points at a control inside one of the tabs."""
        if self.tour.active and self.tour.steps:
            step = self.tour.steps[self.tour.step_idx]
            window = step.get("window")
            if window in self.docks.windows:
                self.docks.focus(window)

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

    def files_dropped(self, paths):
        """A dropped ``.json`` graph replaces the document (the Qt tool's drop handler); anything else is ignored."""
        path = next((str(p) for p in paths if str(p).endswith(".json")), "")
        if not path or self.controller.running:
            return False
        self.panel._try("Load Failed", self.controller.load_graph, path)
        self.graph_control.fit()
        return True

    on_paths_dropped = files_dropped

    def close(self):
        self.controller.close()


def create_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return LightPathApp(**kwargs)
