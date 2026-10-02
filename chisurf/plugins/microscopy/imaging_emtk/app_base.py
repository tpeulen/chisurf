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
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.jobs import SnapshotJob

from .views import ImagePanel, QuiverPanel, draw_series_plot

#: Where the three kinds of window go: the form on the left, the report above the views on the right.
LAYOUT = Split("h", 0.40, Region("settings"), Split("v", 0.30, Region("report"), Region("views")))

#: Suffixes the Database picker offers.
PICKER_FORMATS = ["ptu", "pto", "ht3", "spc", "pt3", "tif", "tiff"]


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

    def __init__(self, model: Any) -> None:
        self.model = model
        self.job = SnapshotJob(model)
        model.runner = self.start_job
        model.add_observer(self._on_event)
        self.spec = self.prepare_spec(json.loads((self.GUI_DIR / self.SPEC).read_text(encoding="utf-8")))
        self.form = FormState()
        self.item_rects: dict[str, tuple] = {}
        self.dialog: FileDialog | None = None
        self.dialog_window: DialogWindow | None = None
        self.dialog_kind = ""
        self.panels: dict[str, Any] = {}
        self.picker_target = "main"
        self.picker = DatasetPicker(formats=PICKER_FORMATS, on_paths=self._picked)
        self.form.custom.update(
            series_plot=lambda s, m, st, w: draw_series_plot(s, m, self),
            image_panel=lambda s, m, st, w: self._draw_image_panel(s),
            image_pair=lambda s, m, st, w: self._draw_image_pair(s),
            quiver=lambda s, m, st, w: self._draw_quiver(s),
        )
        self.tour = EmTkGuidedTour(
            steps=self.GUI_DIR / "guide.json", owner=self, wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key))
        self.help_window = EmTkHelpWindow(title=self.HELP_TITLE, resource=self.GUI_DIR / "help.md", owner=self,
                                          on_start_guide=self.tour.start)
        self.form.on_used = self.tour.notify_used
        self._reported_error = ""
        self.docks = DockManager(self.LAYOUT)
        self.windows: dict[str, dict] = {}
        for panel in self.spec["sections"]:
            key = str(panel["title"])
            self.windows[key] = panel
            self.docks.add_window(key, key, lambda box, p=panel: self._draw_window(p),
                                  dock=str(panel.get("dock", "views")), closable=False)
        super().__init__(self.render, continuous=False)

    def prepare_spec(self, spec: dict) -> dict:
        """Hook: the spec as loaded (a subclass may lay it out or extend it)."""
        return spec

    def _draw_main(self, box: tuple) -> None:
        """Hook: what fills the frame under the dialogs (the dock windows)."""
        self.docks.draw(box)

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
        return bool(self.job.busy or self.picker.is_open or playing or super().animating())

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
        self.picker.render(box)
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
        draw_sections(panel.get("sections") or [], self.model, self.form, int(panel.get("n_col") or 1))
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
            if section.get("type") == "value" and section.get("kind") == "float" and decimals is not None and section.get("attr"):
                value = getattr(self.model, section["attr"], None)
                if isinstance(value, float) and value == value and round(value, int(decimals)) != value:
                    setattr(self.model, section["attr"], round(value, int(decimals)))

    def _toolbar(self) -> None:
        """Help and Guide, then the status line (what the Qt status bar showed)."""
        if im.button("Help"):
            self.help_window.show()
        im.set_item_tooltip(f"Explain what {self.TITLE.lower()} measures, which settings decide the answer and what to check.")
        self.item_rects["help"] = im.get_item_rect()
        im.same_line()
        if im.button("Guide"):
            self.tour.start()
        im.set_item_tooltip("Walk through the tool step by step; each step waits for you to use the control it points at.")
        self.item_rects["guide"] = im.get_item_rect()
        message = f"{self.job.progress} {self.model.status_line}".strip() if self.job.busy else self.model.status_line
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
        fn = getattr(self.model, str(options.get("source", "")), None)
        array = fn() if callable(fn) else None
        marks = getattr(self.model, str(options.get("markers", "")), None)
        if array is not None and getattr(panel, "_array_id", None) != id(array):
            panel._array_id = id(array)
            panel.reset()
        panel.draw(array, self.model, self, markers=marks() if callable(marks) else (),
                   empty=str(options.get("empty", "")), description=str(section.get("description", "")),
                   colormap_attr=str(options.get("colormap_attr", "")))
        if "image" in panel.rects and array is not None:
            self.item_rects[str(section.get("title", name))] = panel.rects["image"]

    def _draw_image_pair(self, section: dict) -> None:
        """Two image panels side by side (Qt: the Before and After docks), each in its own child region."""
        left, right = section["options"]["images"]
        width, height = im.get_content_region_avail()
        x, y = im.get_cursor_screen_pos()
        half = max(80.0, width / 2.0 - 2.0)
        for i, spec in enumerate((left, right)):
            im.begin_child((x + i * (half + 4.0), y, half, max(100.0, height - 4.0)), clip=True, child_id=f"pair_{i}")
            im.text(str(spec.get("title", "")))
            self._draw_image_panel({"title": spec.get("title", ""), "description": spec.get("description", ""),
                                    "options": dict(spec, name=spec.get("name", spec.get("title", "")))})
            im.end_child()
        self.item_rects[str(section.get("title", "images"))] = (x, y, 2.0 * half + 4.0, height)

    def _draw_quiver(self, section: dict) -> None:
        panel = self._panel(str(section.get("title", "quiver")), QuiverPanel)
        panel.draw(section, self.model, self)

    # -- file dialogs -------------------------------------------------------- #
    def _open_requested_dialog(self) -> None:
        kind, self.model.dialog = self.model.dialog, ""
        if not kind or self.dialog is not None or self.picker.is_open:
            return
        if kind.startswith("database"):
            self.picker_target = "second" if kind == "database_second" else "main"
            self.picker.open()
            return
        title, mode, filters, _handler = self.DIALOGS[kind]
        name_for = getattr(self.model, "dialog_filename", None)
        self.dialog = FileDialog(title, mode=mode, filters=filters,
                                 directory=self.model.folder or None,
                                 filename=name_for(kind) if callable(name_for) and mode == "save" else "")
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
            getattr(self.model, self.DIALOGS[kind][3])(result[0])
        elif result is False or pressed == "close":
            self.dialog = None

    def _picked(self, paths: Any) -> None:
        if getattr(self, "picker_target", "main") == "second":
            self.model.open_second_path(str(paths[0]))
        else:
            self.model.open_path(str(paths[0]))

    # -- drops, settings, hub contract --------------------------------------- #
    def files_dropped(self, paths: Any) -> bool:
        """Files dropped on the window: the first one becomes the input, as the Qt data-source field did."""
        paths = [str(p) for p in paths]
        if not paths or self.job.busy or self.model.busy:
            return False
        route = getattr(self.model, "on_paths_dropped", None)
        if callable(route):
            return bool(route(paths))
        self.model.open_path(paths[0])
        return True

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
        self.picker.close()
