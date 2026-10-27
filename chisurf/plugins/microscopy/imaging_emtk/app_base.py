"""The window shell of an imaging tool: settings form, result windows, dialogs, worker, help and guide.

A subclass names its spec, its dialogs and its guide outcomes; everything it draws comes from the model.
The spec's top-level panels become dock windows (``"dock": "settings" | "report" | "views"``); inside a
panel the sections are drawn by :func:`emtk.view_form.draw_sections`, and the ``custom`` sections whose keys
are registered in :attr:`FormState.custom` (``series_plot``, ``image_panel``, ``quiver``) by the views of
:mod:`.views`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog
from emtk.i18n import tr
from emtk.view_form import FormState, draw_form, draw_sections

from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import action_button, window_size

from .views import ImagePanel, QuiverPanel, draw_series_plot

#: Where the three kinds of window go: the form on the left, the report above the views on the right.
LAYOUT = Split("h", 0.40, Region("settings"), Split("v", 0.30, Region("report"), Region("views")))

#: Spec actions that used to open an input (a file dialog or the MMFDB picker) -> the ``accepts``
#: entry whose generated Input section takes their place (``None``: the button just goes; its
#: entry's section stands in for it already).
INPUT_ACTIONS: dict[str, str | None] = {
    "open_file": "image",
    "open_database": None,
    "open_second_file": "second",
    "open_second_database": None,
    "open_irf": "irf",
}
#: A path list's ``add`` dialog kind -> the ``accepts`` entry that fills the list instead.
PATH_LIST_INPUTS: dict[str, str] = {"add_files": "files", "add_irf": "irf_files"}
#: Payload key of a workspace input -> the model method that takes it (a list for ``many``).
RECEIVERS: dict[str, str] = {
    "file": "open_path",
    "second": "open_second_path",
    "irf": "open_irf_path",
    "files": "add_files",
    "irf_files": "add_irf",
}
#: ``value`` fields whose commit took a typed input path: shown read only.
TYPED_PATHS = frozenset({"commit_filename", "commit_second_filename"})
#: Dialog kinds that still open for reading: a tool's own state files, never measurement data.
STATE_DIALOGS = frozenset({"load_regions", "roi"})


def receive_input(app: Any, payload: dict) -> bool:
    """The receive hook of every imaging tool's workspace inputs (``accepts[].receive``).

    Each payload key the tool's :data:`RECEIVERS` knows is read to a local path (a container member
    through its container) and handed to the model method -- the path a picked file always took.
    """
    from chisurf.core.plugin.workspace_input import read_address

    model = getattr(app, "model", app)
    receivers = getattr(type(app), "RECEIVERS", RECEIVERS)
    datasets = [str(d) for d in payload.get("datasets") or [] if d]
    if datasets:
        model.source_dataset = datasets[0]
    taken = False
    for key, method in receivers.items():
        if key not in payload or not hasattr(model, method):
            continue
        value = payload[key]
        if isinstance(value, (list, tuple)):
            getattr(model, method)([read_address(str(v)) for v in value])
        else:
            getattr(model, method)(read_address(str(value)))
        taken = True
    if taken and hasattr(app, "request_frame"):
        app.request_frame()
    return taken


class ImagingToolApp(ImApp):
    """Base of the imaging apps.

    Subclasses set the class attributes and may extend ``DIALOGS`` / ``OUTCOMES``:

    ``DIALOGS``
        ``kind -> (title, mode, filters, handler)``: the dialog a ``model.dialog = kind`` request opens and
        the model method called with the chosen path.
    ``OUTCOMES``
        ``event -> control name``: when the model announces ``event`` the guided tour is told that the
        control was used, and a step that points at ``event`` is drawn on that control's rectangle.
    """

    GUI_DIR: Path
    LAYOUT = LAYOUT
    SPEC: str
    TITLE: str = ""
    HELP_TITLE: str = ""
    DIALOGS: dict[str, tuple] = {}
    OUTCOMES: dict[str, str] = {}
    INPUT_ACTIONS = INPUT_ACTIONS
    PATH_LIST_INPUTS = PATH_LIST_INPUTS
    RECEIVERS = RECEIVERS
    #: Save-dialog kinds whose file is a result of the input -> its workspace kind: it comes back
    #: as a row, a child of the dataset the input was picked from.
    RESULTS: dict[str, str] = {}
    #: The workspace kind *Load example*'s file enters as.
    EXAMPLE_KIND = "image"

    def __init__(self, model: Any) -> None:
        self.model = model
        self.job = SnapshotJob(model)
        model.runner = self.start_job
        model.add_observer(self._on_event)
        specification = json.loads((self.GUI_DIR / self.SPEC).read_text(encoding="utf-8"))
        self.window_size = window_size(specification, (1100, 720))
        #: One generated Input section per ``accepts`` entry that reads from the workspace.
        self.inputs = self._workspace_inputs()
        self.spec = self._workspace_spec(self.prepare_spec(specification))
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.dialog: FileDialog | None = None
        self.dialog_window: DialogWindow | None = None
        self.dialog_kind = ""
        self.panels: dict[str, Any] = {}
        self.form.custom.update(
            series_plot=lambda s, m, st, w: draw_series_plot(s, m, self),
            image_panel=lambda s, m, st, w: self._draw_image_panel(s),
            image_pair=lambda s, m, st, w: self._draw_image_pair(s),
            quiver=lambda s, m, st, w: self._draw_quiver(s),
        )
        for name, named in self.inputs.items():
            self.form.custom[f"workspace_input:{name}"] = lambda s, m, st, w, name=name: (
                self._draw_input(name)
            )
        self.tour = EmTkGuidedTour(
            steps=self.GUI_DIR / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.help_window = EmTkHelpWindow(
            title=self.HELP_TITLE,
            resource=self.GUI_DIR / "help.md",
            owner=self,
            on_start_guide=self.tour.start,
        )
        self.form.on_used = self.tour.notify_used
        for name, named in self.inputs.items():
            named.workspace_input_on_used = lambda _key, name=name: self._input_used(name)
        self._reported_error = ""
        self.docks = DockManager(self.LAYOUT)
        self.windows: dict[str, dict] = {}
        for panel in self.spec["sections"]:
            key = str(panel["title"])
            self.windows[key] = panel
            self.docks.add_window(
                key,
                key,
                lambda box, p=panel: self._draw_window(p),
                dock=str(panel.get("dock", "views")),
                closable=False,
                tooltip=str(panel.get("description", "")),
            )
        super().__init__(self.render, continuous=False)

    def prepare_spec(self, spec: dict) -> dict:
        """Hook: the spec as loaded (a subclass may lay it out or extend it)."""
        return spec

    # -- the workspace inputs ------------------------------------------------- #
    def _workspace_inputs(self) -> dict[str, Any]:
        """``name -> Input section model`` for every ``accepts`` entry reading from the workspace."""
        from chisurf.plugins.tttr.workspace_io import NamedWorkspaceInput

        path = self.GUI_DIR.parent / "manifest.json"
        if not path.is_file():
            return {}
        manifest = json.loads(path.read_text(encoding="utf-8"))
        inputs: dict[str, Any] = {}
        for entry in manifest.get("accepts") or []:
            if entry.get("from_workspace") and entry.get("name"):
                # 72 px holds the filter box, the header and one row; at 60 px the row was drawn
                # over the hint under the table (the layout checks caught it).
                inputs[str(entry["name"])] = NamedWorkspaceInput(
                    str(manifest["id"]), str(entry["name"]), self, height=72
                )
        return inputs

    def _workspace_spec(self, spec: dict) -> dict:
        """The spec with every input button replaced by its generated Input section.

        A button whose action opened an input (``INPUT_ACTIONS``) goes; the Input section of its
        ``accepts`` entry is drawn where its row was. A path list filled by a dialog shows the entry's
        section above it and loses its Add/Database buttons.
        """
        placed: set[str] = set()

        def custom(name: str) -> dict:
            placed.add(name)
            return {
                "type": "custom",
                "key": f"workspace_input:{name}",
                "description": "Pick the data this tool works on from the Datasets workspace "
                "(drop files on the ChiSurf window to add them there).",
            }

        def walk(sections: list) -> list:
            out: list = []
            for section in sections:
                if not isinstance(section, dict):
                    out.append(section)
                    continue
                if isinstance(section.get("sections"), list):
                    section["sections"] = walk(section["sections"])
                buttons = section.get("buttons")
                if isinstance(buttons, list):
                    gone = [b for b in buttons if b.get("action") in self.INPUT_ACTIONS]
                    names = [
                        self.INPUT_ACTIONS[b["action"]]
                        for b in gone
                        if self.INPUT_ACTIONS[b["action"]] in self.inputs
                        and self.INPUT_ACTIONS[b["action"]] not in placed
                    ]
                    out.extend(custom(n) for n in dict.fromkeys(names))
                    section["buttons"] = [b for b in buttons if b not in gone]
                    if not section["buttons"]:
                        continue
                if section.get("type") == "value" and section.get("call") in TYPED_PATHS:
                    # A typed path was an input route too: the field now shows what was picked.
                    section.pop("call")
                    section["read_only"] = True
                    section["placeholder"] = "picked in the Input section"
                    section["description"] = (
                        "The file picked in the Input section (the Datasets workspace)."
                    )
                options = section.get("options") if section.get("type") == "custom" else None
                if isinstance(options, dict) and section.get("key") == "path_list":
                    name = self.PATH_LIST_INPUTS.get(str(options.get("add", "add_files")))
                    if name in self.inputs:
                        options["workspace"] = True
                        if name not in placed:
                            out.append(custom(name))
                out.append(section)
            return out

        spec["sections"] = walk(spec.get("sections", []))
        return spec

    def _draw_input(self, name: str) -> None:
        named = self.inputs[name]
        draw_form(named.spec, named, named.form)
        rect = named.form.rects.get("workspace_input_rows")
        if rect is not None:
            self.item_rects[f"input_{name}"] = rect
            # Guide steps written for the buttons this section replaced point at it.
            for action, target in self.INPUT_ACTIONS.items():
                if target == name:
                    self.item_rects[action] = rect

    def _input_used(self, name: str) -> None:
        self.tour.notify_used(f"input_{name}")
        for action, target in self.INPUT_ACTIONS.items():
            if target == name:
                self.tour.notify_used(action)

    def _demo_module(self):
        """The plugin's demo module when it ships one (the *Load example* affordance)."""
        import importlib

        try:
            return importlib.import_module(
                f"chisurf.plugins.microscopy.{self.GUI_DIR.parent.name}.demo"
            )
        except ModuleNotFoundError:
            return None

    def load_example(self) -> None:
        """The demo affordance: the plugin's shared synthetic stack in, the tool's run on it.

        The plugin's ``demo`` module produces the example (see
        :mod:`chisurf.plugins.microscopy.demo_stack`) and hands it to the model,
        so the tool runs the same path a dropped file takes.
        """
        demo = self._demo_module()
        if demo is None:
            self.model.status_line = "This tool has no example data."
            return
        path = demo.load_into(self)
        if path:
            self._example_into_workspace(path)

    def _example_into_workspace(self, path: Any) -> None:
        """The example file enters the Datasets workspace, as a dropped file would."""
        from chisurf.core.plugin.workspace_input import register_result

        try:
            row = register_result(str(path), kind=self.EXAMPLE_KIND)
            self.model.source_dataset = str(getattr(row, "unique_identifier", "") or "")
        except Exception:  # noqa: BLE001 - the example is loaded; its row is a convenience
            import logging

            logging.getLogger(__name__).exception("adding the example to the workspace failed")

    def _draw_main(self, box: tuple) -> None:
        """Hook: what fills the frame under the dialogs (the dock windows)."""
        self.docks.draw(box)
        shown = self.docks.selected.get("views")
        if (
            shown
            and hasattr(self.model, "view_tab")
            and shown in self.windows
            and self.model.view_tab != shown
        ):
            self.model.view_tab = shown  # the View choice follows the tab that was clicked

    # -- worker ----------------------------------------------------------- #
    def start_job(self, method: str) -> bool:
        """Run the model method *method* on a snapshot in a worker thread."""
        self._reported_error = ""
        started = self.job.start(method)
        if started:
            self.model.busy = True
        return started

    def animating(self) -> bool:
        playing = any(getattr(p, "playing", False) for p in self.panels.values())
        return bool(self.job.busy or playing or super().animating())

    def _on_event(self, event: str) -> None:
        """The model announced something: tell the tour when it is an outcome a step waits for."""
        control = self.OUTCOMES.get(event)
        if control is not None:
            if control in self.form.rects:
                self.item_rects[event] = self.form.rects[control]
            self.tour.notify_used(event)
            self.tour.notify_used(control)

    # -- one frame --------------------------------------------------------- #
    def render(self) -> None:
        self.job.poll()
        self.model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            self.model.status_line = f"Failed: {self.job.error}"
        vp = im.get_main_viewport()
        box = (*vp.pos, *vp.size)
        self.form.rects.clear()
        self._open_requested_dialog()
        self._follow_tour()
        self._draw_main(box)
        self._draw_dialog(box)
        for event, control in self.OUTCOMES.items():
            if control in self.form.rects:
                self.item_rects[event] = self.form.rects[control]
        self.help_window.draw(box)
        self.tour.draw(*vp.size)

    def _follow_tour(self) -> None:
        """Bring the tab forward while a tour step points at one of the windows."""
        if self.tour.active and self.tour.steps:
            key = self.tour._target_key(self.tour.steps[self.tour.step_idx].get("target"))
            if key in self.windows:
                self.docks.focus(key)

    # -- windows ----------------------------------------------------------- #
    def _draw_window(self, panel: dict) -> None:
        is_settings = panel.get("dock") == "settings"
        if is_settings:
            self._toolbar()
        im.begin_disabled(is_settings and bool(self.model.busy))
        draw_sections(
            panel.get("sections") or [], self.model, self.form, int(panel.get("n_col") or 1)
        )
        im.end_disabled()
        if is_settings:
            self._round_to_decimals(panel)

    def _round_to_decimals(self, panel: dict) -> None:
        """A typed number is kept to the decimals the field shows, as the Qt spin box did (the value is the one on screen)."""
        stack = [panel]
        while stack:
            section = stack.pop()
            stack.extend(section.get("sections") or [])
            decimals = section.get("decimals")
            if (
                section.get("type") == "value"
                and section.get("kind") == "float"
                and decimals is not None
                and section.get("attr")
            ):
                value = getattr(self.model, section["attr"], None)
                if (
                    isinstance(value, float)
                    and value == value
                    and round(value, int(decimals)) != value
                ):
                    setattr(self.model, section["attr"], round(value, int(decimals)))

    #: show a Cancel button (greyed while idle) that calls ``model.cancel()``
    CANCELLABLE = False

    def _toolbar(self) -> None:
        """Help and Guide (and Cancel), then the status line (what the Qt status bar showed)."""
        if action_button("help"):
            self.help_window.show()
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if action_button("guide"):
            self.tour.start()
        self.item_rects["guide"] = im.get_item_rect()
        if self._demo_module() is not None:  # only tools with a demo offer the example
            im.same_line()
            if action_button("example"):
                self.tour.notify_used("load_example")
                self.load_example()
            self.item_rects["load_example"] = im.get_item_rect()
        if self.CANCELLABLE:
            im.same_line()
            im.begin_disabled(not (self.job.busy or self.model.busy))
            if action_button(
                "cancel",
                tooltip=tr(
                    "Stop at the next checkpoint of the running calculation and discard the unfinished result."
                ),
            ):
                self.model.cancel()
            self.item_rects["cancel"] = im.get_item_rect()
            im.end_disabled()
        message = (
            f"{self.job.progress} {self.model.status_line}".strip()
            if self.job.busy
            else self.model.status_line
        )
        if message:
            im.text_wrapped(message)
        im.separator()

    def _panel(self, name: str, factory: Any) -> Any:
        if name not in self.panels:
            self.panels[name] = factory(name)
        return self.panels[name]

    def _draw_image_panel(self, section: dict) -> None:
        options = section.get("options") or {}
        name = str(options.get("name", section.get("title", "image")))
        panel = self._panel(name, lambda key: ImagePanel(key, movie=bool(options.get("movie"))))
        panel.canvas.image_label = str(
            options.get("label", section.get("title", name))
        )  # the legend names what is drawn
        fn = getattr(self.model, str(options.get("source", "")), None)
        array = fn() if callable(fn) else None
        marks = getattr(self.model, str(options.get("markers", "")), None)
        array = panel.hold(array)
        panel.draw(
            array,
            self.model,
            self,
            markers=marks() if callable(marks) else (),
            empty=str(options.get("empty", "")),
            description=str(section.get("description", "")),
            colormap_attr=str(options.get("colormap_attr", "")),
        )
        if "image" in panel.rects and array is not None:
            self.item_rects[str(section.get("title", name))] = panel.rects["image"]

    def _draw_image_pair(self, section: dict) -> None:
        """Two image panels side by side (Qt: the Before and After docks), each in its own child region."""
        left, right = section["options"]["images"]
        width, height = im.get_content_region_avail()
        x, y = im.get_cursor_screen_pos()
        half = max(80.0, width / 2.0 - 2.0)
        for i, spec in enumerate((left, right)):
            im.begin_child(
                (x + i * (half + 4.0), y, half, max(100.0, height - 4.0)),
                clip=True,
                child_id=f"pair_{i}",
            )
            im.text(str(spec.get("title", "")))
            self._draw_image_panel(
                {
                    "title": spec.get("title", ""),
                    "description": spec.get("description", ""),
                    "options": dict(spec, name=spec.get("name", spec.get("title", ""))),
                }
            )
            im.end_child()
        self.item_rects[str(section.get("title", "images"))] = (x, y, 2.0 * half + 4.0, height)

    def _draw_quiver(self, section: dict) -> None:
        panel = self._panel(str(section.get("title", "quiver")), QuiverPanel)
        panel.draw(section, self.model, self)

    # -- file dialogs -------------------------------------------------------- #
    def _open_requested_dialog(self) -> None:
        kind, self.model.dialog = self.model.dialog, ""
        if not kind or self.dialog is not None or kind not in self.DIALOGS:
            return
        title, mode, filters, _handler, *rest = self.DIALOGS[kind]
        if mode != "save" and kind not in STATE_DIALOGS:
            # Measurement data comes from the Datasets workspace, never from a file dialog.
            self.model.status_line = "Pick the data in the Input section (the Datasets workspace)."
            return
        name_for = getattr(self.model, "dialog_filename", None)
        # not-input: only save dialogs and a tool's own state files (STATE_DIALOGS) open here.
        self.dialog = FileDialog(
            title,
            mode=mode,
            filters=filters,
            multiselect=bool(rest and rest[0]),
            directory=self.model.folder or None,
            filename=name_for(kind) if callable(name_for) and mode == "save" else "",
        )
        self.dialog_kind = kind
        self.dialog_window = DialogWindow(title, size=(640.0, 460.0), key=f"file_{kind}")

    def _draw_dialog(self, frame: tuple) -> None:
        """The file chooser in a titled window with a close button (Escape and the cross cancel)."""
        if self.dialog is None or self.dialog_window is None:
            return
        pressed = self.dialog_window.begin(frame)
        result = self.dialog.draw()
        self.dialog_window.end()
        if result:
            kind, self.dialog = self.dialog_kind, None
            self.tour.notify_used(kind)
            self.model.remember_folder(result[0])
            handler = getattr(self.model, self.DIALOGS[kind][3])
            handler(
                [str(p) for p in result]
                if len(self.DIALOGS[kind]) > 4 and self.DIALOGS[kind][4]
                else result[0]
            )
            if kind in self.RESULTS:
                self._result_into_workspace(str(result[0]), self.RESULTS[kind])
        elif result is False or pressed == "close":
            self.dialog = None

    def _result_into_workspace(self, path: str, kind: str) -> None:
        """A file the tool wrote enters the workspace as a child of the dataset it came from."""
        from chisurf.core.plugin.workspace_input import register_result

        try:
            register_result(
                path, kind=kind, result_of=str(getattr(self.model, "source_dataset", ""))
            )
        except Exception:  # noqa: BLE001 - the file is written; its row is a convenience
            import logging

            logging.getLogger(__name__).exception("adding %s to the workspace failed", path)

    # -- settings, hub contract ------------------------------------------------ #
    def export_settings(self) -> dict:
        return self.model.export_settings()

    def restore_settings(self, state: dict) -> None:
        self.model.restore_settings(state)

    def apply_setup_settings(self, payload: dict) -> None:
        """The imaging hub's shared detector setup (photon streams)."""
        self.model.apply_setup_settings(payload)
        self.request_frame()

    def apply_pipeline_context(self, payload: dict) -> None:
        """The imaging hub's current source file."""
        self.model.apply_pipeline_context(payload)
        self.request_frame()

    def close(self) -> None:
        """Workers are daemon threads and no file stays open."""
