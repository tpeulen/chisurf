"""Native emtk TTTR image browser: the Qt tool's two pages on emtk.

Page *Image browser* (what the window opens on) holds three windows, laid out side by side so that the mosaic
gets most of the area:

* ``toolbar`` -- the Qt toolbar (Open folder, Clear, Clear caches, Copy raw files, TIFF, DOCX, Next, Include
  subfolders, Help, Guide), drawn from ``browser_emtk.view.json``;
* ``files`` -- the Qt left column: folder, rating filter, the file list as a ``data_table`` (with its filter box,
  sortable, one row selected or several), rating, info line and annotation;
* ``image`` -- the display controls of the Qt image dock (colormap, gamma, levels, tile labels, reset view), the
  detector-window mosaic with its tile labels (mouse wheel zooms, a drag pans) and a level histogram whose two
  lines are the display levels (drag them).

Page *Detector setup* hosts the shared setup editor (:class:`chisurf.emtk.channel_definition.ChannelDefinitionWidget`)
unchanged; *Use setup and continue* hands its settings to the browser.

The windows are plain ``im.begin`` windows: the mouse wheel does not reach an ``implot`` inside a ``DockManager``
window (see REPORT.md). Photon files are never read in the draw loop: a mosaic loads on a worker
(:class:`~.model.MosaicLoader`), scans and exports on a snapshot job. All state is in :class:`~.model.ImageBrowserModel`.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from emtk import im, implot
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.file_dialog import FileDialog
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkGuidedTour, EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.emtk_layout import cap_widths, group_by_width

from .model import ImageBrowserModel, MosaicLoader

HERE = Path(__file__).parent

#: Height of the page tab strip.
TAB_H = 30.0
#: Width the file list gets (a share of the window, within these limits).
LEFT_MIN, LEFT_MAX, LEFT_SHARE = 250.0, 360.0, 0.27
#: Width of the level histogram beside the mosaic.
HIST_W = 120.0
#: Widest the shared setup editor is drawn: its fields take all the width they are given.
EDITOR_W = 720.0
#: Height of the annotation box.
NOTE_H = 66.0

_FLAGS = None


def _window_flags() -> int:
    """No title bar, not resizable, not movable: the windows tile the frame."""
    global _FLAGS
    if _FLAGS is None:
        f = im.WindowFlags
        _FLAGS = f.NO_TITLE_BAR | f.NO_RESIZE | f.NO_MOVE
    return _FLAGS


def fit_label(text: str, room: float) -> str:
    """The longest form of a tile label ("green  |  mt: 0-4095  |  ch: 0,1") that fits *room* pixels.

    Full text, then the detector and its routing channels, then the detector name; a tile narrower than its own
    name keeps the name (zoom in to see it whole).
    """
    parts = [part.strip() for part in text.split("|")]
    for candidate in (" | ".join(parts), f"{parts[0]} | {parts[-1]}" if len(parts) > 2 else "", parts[0]):
        if candidate and im.calc_text_size(candidate)[0] <= room:
            return candidate
    return parts[0]


class TTTRImageBrowserApp(ImApp):
    """The TTTR image browser (detector setup page and browser page).

    Parameters
    ----------
    model : ImageBrowserModel, optional
        The state; a fresh one by default.
    client : TTTRImageBrowserClient, optional
        The RPC client of a fresh model (default: the service handlers called directly).
    coordinator : object, optional
        The Imaging Tools coordinator (``set_pipeline``, ``goto_role``, ``autorun_role``); *Next* needs it.
    setups_file : str or Path, optional
        Detector-setups JSON the setup page offers (default: the user's canonical file).
    """

    DIALOGS = {
        "folder": ("Open folder", "folder", "", "open_folder"),
        "copy": ("Copy raw files to", "folder", "", "do_copy_files"),
        "tiff": ("Write TIFF stacks to", "folder", "", "do_export_tiff"),
        "docx": ("Save DOCX report", "save", "DOCX (*.docx)", "do_export_docx"),
    }

    def __init__(
        self,
        model: ImageBrowserModel | None = None,
        client: Any = None,
        coordinator: Any = None,
        setups_file: Any = None,
    ) -> None:
        self.model = model or ImageBrowserModel(client)
        self._coordinator = coordinator
        self.setups_file = str(setups_file) if setups_file else None
        self.job = SnapshotJob(self.model)
        self.loader = MosaicLoader(self.model._client)
        self.load_job = SnapshotJob(self.loader)
        self._queue: deque[tuple[str, tuple]] = deque()
        self._reported_error = ""
        self.spec = json.loads((HERE / "browser_emtk.view.json").read_text(encoding="utf-8"))
        # capped widths everywhere; the Files column also gets one grid per kind of field (the spec file stays as the
        # AutoForm dialect reads it). The toolbar and the display strip keep their rows of mixed fields.
        cap_widths(self.spec["sections"])
        for panel in self.spec["sections"]:
            if panel["window"] == "files":
                panel["sections"] = group_by_width(panel["sections"])
        self.panels = {p["window"]: p for p in self.spec["sections"]}
        self.form = FormState()
        self.form.custom["annotation"] = lambda s, m, st, w: self._draw_annotation()
        self.item_rects: dict[str, tuple] = {}
        self.page = "browser"
        self.pending_page: str | None = None
        self.dialog: FileDialog | None = None
        self.dialog_window: DialogWindow | None = None
        self.dialog_kind = ""
        self.canvas = ImageCanvas("channel_mosaic")
        self.view_key: Any = None
        #: Visible ``(x_min, x_max, y_min, y_max)`` of the mosaic plot in pixels (what zooming and panning change).
        self.view_limits: tuple | None = None
        self.note_text = ""
        self.note_for: str | None = None
        self.toolbar_h = 40.0
        self.status_h = 28.0
        self.editor: ChannelDefinitionWidget | None = None
        self.model.can_next = coordinator is not None
        self.model.add_observer(self._on_event)
        self.tour = EmTkGuidedTour(
            steps=HERE / "guide.json",
            owner=self,
            wait_for_controls=True,
            get_target_rect=lambda key: self.item_rects.get(key) or self.form.rects.get(key),
        )
        self.help_window = EmTkHelpWindow(
            title="TTTR Image Browser — Help",
            resource=HERE / "help.md",
            owner=self,
            on_start_guide=self.tour.start,
        )
        self.form.on_used = self._used
        self._new_editor(None)
        super().__init__(self.render, continuous=False)

    # -- coordinator (the Imaging Tools hub sets ``_coordinator`` after construction too) ---------------- #
    @property
    def coordinator(self) -> Any:
        return self._coordinator

    @coordinator.setter
    def coordinator(self, value: Any) -> None:
        self._coordinator = value

    # -- the shared setup editor --------------------------------------------------------------------- #
    def _new_editor(self, settings: dict | None) -> None:
        """Replace the setup editor by a fresh one holding *settings*."""
        from chisurf.core.setup_channel_definition import ChannelDefinition

        if self.editor is not None:
            self.editor.close()
        self.editor = ChannelDefinitionWidget(
            model=ChannelDefinition(settings, file_path=self.setups_file)
        )
        self._list_saved_setups()

    def _list_saved_setups(self) -> None:
        """Offer the saved setups in the editor's *Setups* tab, as the Qt setup page does; none is applied.

        The Qt tool starts on its setup page and applies nothing until *Use setup and continue*: a saved setup
        that is adopted silently would change which files the list shows (a setup that reads PTO lists no PTU).
        """
        assert self.editor is not None
        try:
            self.editor.model.refresh_setups()
        except Exception as exc:  # the saved setups are an extra; the browser works without
            self.model.status_line = f"Saved detector setups are not available: {exc}"

    def use_setup(self, switch: bool = True) -> None:
        """*Use setup and continue*: the editor's settings drive the tiles; show the browser."""
        assert self.editor is not None
        self.model.setup_name = str(getattr(self.editor.model, "current_name", "") or "")
        self.model.apply_setup_settings(self.editor.model.get_settings())
        self.model.status_line = f"Detector setup: {self.model.setup_text()}"
        if switch:
            self.pending_page = "browser"
            self.tour.notify_used("use_setup")

    # -- hub contract --------------------------------------------------------------------------------- #
    def apply_setup_settings(self, payload: dict) -> None:
        """The imaging hub's shared detector setup: shown in the editor, used for the tiles."""
        if not payload:
            return
        self._new_editor(payload)
        self.model.setup_name = str(payload.get("setup_name") or "")
        self.model.apply_setup_settings(payload)
        self.model.status_line = f"Detector setup: {self.model.setup_text()}"
        self.request_frame()

    def apply_pipeline_context(self, payload: dict) -> None:
        """The imaging hub's current source: open its folder and select it."""
        self.model.apply_pipeline_context(payload)
        self.request_frame()

    def files_dropped(self, paths: Any) -> bool:
        """Files dropped on the window (the host's verb): a folder opens, anything else is reported."""
        paths = [str(p) for p in paths]
        if not paths:
            return False
        if any(Path(p).is_dir() for p in paths):
            folder = next(p for p in paths if Path(p).is_dir())
            self.page = "browser"
            self.pending_page = "browser"
            self.queue("open_folder", folder)
            return True
        self.model.status_line = "Drop a folder of photon files, not a single file."
        return False

    on_files_dropped = files_dropped

    def open_folder(self, path: Any) -> None:
        """Open *path* (a file opens the folder that holds it)."""
        value = Path(str(path))
        self.queue("open_folder", str(value if value.is_dir() else value.parent))

    def export_settings(self) -> dict:
        return self.model.export_settings()

    def restore_settings(self, state: dict) -> None:
        self.model.restore_settings(state)

    def close(self) -> None:
        if self.editor is not None:
            self.editor.close()

    # -- jobs ------------------------------------------------------------------------------------------ #
    def queue(self, method: str, *args: Any) -> None:
        """Run the model method *method* on a snapshot worker once the one running is done."""
        item = (method, args)
        if item not in self._queue:
            self._queue.append(item)
        self.request_frame()

    def _pump(self) -> None:
        """Collect finished workers, start the next job and the mosaic the selection asks for (once a frame)."""
        model = self.model
        self.job.poll()
        model.busy = self.job.busy
        if self.job.error and self.job.error != self._reported_error:
            self._reported_error = self.job.error
            model.status_line = f"Failed: {self.job.error}"
        if self._queue and not self.job.busy:
            method, args = self._queue.popleft()
            self._reported_error = ""
            if self.job.start(method, *args):
                model.busy = True
        # a finished mosaic
        was = self.load_job.busy
        self.load_job.poll()
        if was and not self.load_job.busy:
            path = self.loader.path
            if path:
                if self.load_job.error:
                    model.store_mosaic(path, None)
                    model._failed[path] = f"failed ({self.load_job.error})"
                else:
                    model.store_mosaic(path, self.loader.result)
        want = model.wanted_image()
        if want and not self.load_job.busy and not self.job.busy and not self._queue:
            self.load_job.start("load", want, model.setup_settings, model.current_folder)
        # requests of the buttons
        while model.requests:
            request = model.requests.pop(0)
            if request == "help":
                self.help_window.show()
            elif request == "guide":
                self.tour.start()
            elif request == "next":
                self.next_step()

    def animating(self) -> bool:
        return bool(
            self.job.busy
            or self.load_job.busy
            or self._queue
            or self.model.wanted_image()
            or self.model.requests
            or super().animating()
        )

    #: Model events that count as the user having used a control (a tour step waits for them).
    OUTCOMES = {"folder": "choose_folder", "select": "rows", "rating": "current_rating"}

    def _used(self, name: str) -> None:
        """A control was used. Pressing *Open folder* only opens the chooser: the step waits for the folder."""
        if name != "choose_folder":
            self.tour.notify_used(name)

    def _on_event(self, event: str) -> None:
        if event == "select" and self._coordinator is not None and self.model.current_file:
            try:
                self._coordinator.set_pipeline(source=str(self.model.current_file))
            except Exception as exc:
                self.model.status_line = f"The pipeline did not take the image: {exc}"
        if event in ("select", "folder"):
            self.view_key = None
        self.tour.notify_used(event)
        control = self.OUTCOMES.get(event)
        if control:
            self.tour.notify_used(control)

    def next_step(self) -> None:
        """Hand the current image to the imaging pipeline and open its Intensity step (the Qt *Next*)."""
        coordinator = self._coordinator
        if coordinator is None:
            self.model.status_line = "Next needs Imaging Tools: open the browser from there."
            return
        try:
            source = self.model.current_file or (self.model.paths() or [None])[0]
            if source:
                coordinator.set_pipeline(source=str(source))
            coordinator.goto_role("pixel_intensity")
            coordinator.autorun_role("pixel_intensity")
            self.model.status_line = "Sent to the Intensity step of Imaging Tools."
        except Exception as exc:
            self.model.status_line = f"The pipeline did not take the image: {exc}"
        self.tour.notify_used("next_step")

    # -- one frame --------------------------------------------------------------------------------------- #
    def render(self) -> None:
        self._pump()
        vp = im.get_main_viewport()
        width, height = float(vp.size[0]), float(vp.size[1])
        box = (0.0, 0.0, width, height)
        self.form.rects.clear()
        self._open_requested_dialog()
        self._tabs(width)
        status_y = height - self.status_h
        if self.page == "setup":
            self._window("Detector setup", (0.0, TAB_H, width, status_y - TAB_H), self._setup_page)
        else:
            self._browser_page(width, status_y)
        self._window("Status", (0.0, status_y, width, self.status_h), self._status_bar)
        assert self.editor is not None
        self.editor.draw_dialogs(box)
        self._draw_dialog(box)
        self.help_window.draw(box)
        self.tour.draw(width, height)
        # A notch the image plot used for zooming stays in ``io.mouse_wheel`` (emtk gap, gap_wheel_stale.py) and would
        # step the next spin field the pointer reaches; every window has had its chance to take it by now.
        self.io.mouse_wheel = 0.0
        self.io.mouse_wheel_h = 0.0

    def _window(self, name: str, box: tuple, body: Any) -> None:
        if im.begin(name, box, _window_flags()):
            body()
        im.end()

    def _tabs(self, width: float) -> None:
        """The two pages as tabs (the Qt tool showed the setup page first and had no way back)."""
        labels = {"browser": "Image browser", "setup": "Detector setup"}
        tips = {
            "browser": "Browse the folder: file list, detector-window mosaic, ratings, annotations and exports.",
            "setup": "Detector routing, PIE windows, reading routine, TAC corrections and optical setup (the shared setup editor).",
        }
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width, TAB_H), im.Cond.ALWAYS)
        if im.begin("Browser pages", flags=_window_flags()):
            if im.begin_tab_bar("browser_pages"):
                for key in ("browser", "setup"):
                    flag = im.TabItemFlags.SET_SELECTED if self.pending_page == key else 0
                    if im.begin_tab_item(labels[key], flag):
                        if self.page != key:
                            self.page = key
                            self.tour.notify_used(f"tab_{key}")
                        im.end_tab_item()
                    im.set_item_tooltip(tips[key])
                    self.item_rects[f"tab_{key}"] = im.get_item_rect()
                im.end_tab_bar()
                self.pending_page = None
        im.end()

    # -- the setup page ------------------------------------------------------------------------------------ #
    def _setup_page(self) -> None:
        if im.button("Use setup and continue"):
            self.use_setup()
        im.set_item_tooltip(
            "Use these detector routing, PIE window, reading and calibration settings for the mosaics of the "
            "browser, then show the browser."
        )
        self.item_rects["use_setup"] = im.get_item_rect()
        im.same_line()
        if im.button("Help##setup_help"):
            self.help_window.show()
        im.set_item_tooltip("Explain the detector setup and the browser.")
        self.item_rects["setup_help"] = im.get_item_rect()
        im.separator()
        assert self.editor is not None
        x, y = im.get_cursor_screen_pos()
        avail_w, avail_h = (float(v) for v in im.get_content_region_avail())
        im.begin_child((x, y, min(avail_w, EDITOR_W), max(100.0, avail_h)), clip=True, child_id="setup_editor")
        self.editor.draw()
        im.end_child()

    # -- the browser page ------------------------------------------------------------------------------------ #
    def _browser_page(self, width: float, bottom: float) -> None:
        top = TAB_H
        bar_h = float(self.toolbar_h)
        left_w = min(LEFT_MAX, max(LEFT_MIN, width * LEFT_SHARE))
        body_y = top + bar_h
        body_h = max(120.0, bottom - body_y)
        self._window("Toolbar", (0.0, top, width, bar_h), self._toolbar)
        self._window("Files", (0.0, body_y, left_w, body_h), self._files)
        self._window("Image", (left_w, body_y, width - left_w, body_h), self._image_window)
        self._sync_table()

    def _toolbar(self) -> None:
        draw_sections(self.panels["toolbar"]["sections"], self.model, self.form, 1, True, False)
        self._fit("toolbar_h", 6.0)

    def _status_bar(self) -> None:
        """The Qt status bar: the last message, or what the worker is doing."""
        model = self.model
        text = f"{self.job.progress} {model.status_line}".strip() if self.job.busy else model.status_line
        if self.load_job.busy and not self.job.busy:
            text = f"Loading {Path(self.loader.path or '').name} \u2026"
        im.text_wrapped(text or " ")
        self.item_rects["status"] = im.get_item_rect()
        self._fit("status_h", 8.0)

    def _fit(self, attr: str, pad: float) -> None:
        """Size the window to what it drew (read from last frame: one frame late, then stable)."""
        wanted = float(im.get_cursor_pos_y()) - float(im.get_window_pos()[1]) + float(im.get_scroll_y()) + pad
        if abs(wanted - getattr(self, attr)) > 1.0:
            setattr(self, attr, wanted)
            self.request_frame()

    def _files(self) -> None:
        im.begin_disabled(bool(self.model.busy))
        draw_sections(self.panels["files"]["sections"], self.model, self.form)
        im.end_disabled()

    def _sync_table(self) -> None:
        """Show the model's selection in the file table (a click selects one row; several after *Multiple selection*)."""
        binding = self.form.tables.get("rows")
        if binding is None:
            return
        control = binding.control
        model = self.model
        if model.select_all_requested:
            model.select_all_requested = False
            control.select_all()
            rows = model.rows()
            chosen = [rows[i]["path"] for i in control.selected_indices() if 0 <= i < len(rows)]
            if chosen:
                model.selected_files = chosen
                if model.current_file not in chosen:
                    model.current_file = chosen[0]
                model.notify("select")
        if model.multi_select:
            # Every selected row is "also selected" and none is *the* selected one: the table calls the selection
            # back only when the clicked row differs from its selected row, and a click on a row that is
            # already selected must still toggle it off.
            control.selected_key = None
            control.also_selected = set(model.selected_files)
            return
        current = model.current_file
        if current != control.selected_key or control.also_selected:
            if current is None:
                control.selected_key = None
            else:
                control.select_key(current)
            control.also_selected = set()

    def _draw_annotation(self) -> None:
        model = self.model
        path = model.current_file
        if path != self.note_for:
            self.note_for = path
            self.note_text = model.note_of(path) if path else ""
        im.text_unformatted("Annotation")
        self.item_rects["annotation_label"] = im.get_item_rect()
        im.begin_disabled(path is None)
        changed, text = im.input_text_multiline("##annotation", self.note_text, (0.0, NOTE_H))
        im.set_item_tooltip(
            "A note for the file shown. It is saved at once beside the data in .image_browser_meta.json."
        )
        self.item_rects["annotation"] = im.get_item_rect()
        im.end_disabled()
        if changed and path is not None:
            self.note_text = text
            model.set_note(path, text)
            self.tour.notify_used("annotation")

    # -- the image window ------------------------------------------------------------------------------------ #
    def _image_window(self) -> None:
        model = self.model
        im.begin_disabled(model.current_image() is None or bool(model.busy))
        draw_sections(self.panels["display"]["sections"], model, self.form, 1, True, False)
        im.end_disabled()
        array = model.current_image()
        avail_w, avail_h = (float(v) for v in im.get_content_region_avail())
        info = model.file_info()
        if array is None:
            self._empty_image(avail_w)
            return
        im.text_unformatted(info)
        avail_w, avail_h = (float(v) for v in im.get_content_region_avail())
        plot_h = max(120.0, avail_h - 4.0)
        hist_w = HIST_W if avail_w > 360 else 0.0
        self._draw_mosaic(array, max(120.0, avail_w - hist_w - 6.0), plot_h)
        if hist_w:
            im.same_line()
            self._draw_levels(hist_w, plot_h)

    def _empty_image(self, width: float) -> None:
        """What the image area says when there is nothing to draw (never an invented image)."""
        model = self.model
        if not model.current_folder:
            text = "Open a folder with photon files (or drop one here) to see their detector-window mosaics."
        elif not model.current_file:
            text = "Select a file in the list to see its detector-window mosaic."
        elif model.image_error():
            text = f"{Path(model.current_file).name}: {model.image_error()}."
        else:
            text = f"Loading {Path(model.current_file).name} …"
        im.push_text_wrap_pos(0.0)
        im.text_disabled(text)
        im.pop_text_wrap_pos()
        self.item_rects["image"] = im.get_item_rect()

    def _draw_mosaic(self, array: np.ndarray, width: float, height: float) -> None:
        model = self.model
        canvas = self.canvas
        canvas.colormap = model.colormap if model.colormap in model.colormap_options() else "magma"
        canvas.gamma = float(model.gamma)
        canvas.auto_levels = bool(model.auto_levels)
        canvas.low, canvas.high = float(model.level_low), float(model.level_high)
        texture = canvas.texture(array)
        ny, nx = array.shape
        plot_w, plot_h = max(100.0, width - 70.0), max(100.0, height - 50.0)
        span_x = 1.08 * max(nx, ny * plot_w / plot_h)
        span_y = span_x * plot_h / plot_w
        cx, cy = (nx - 1.0) / 2.0, (ny - 1.0) / 2.0
        limits = (cx - span_x / 2, cx + span_x / 2, cy - span_y / 2, cy + span_y / 2)
        key = (id(array), model.current_file, round(width), round(height))  # a resized window shows the whole mosaic again
        reset = model.reset_view_requested or key != self.view_key
        model.reset_view_requested = False
        self.view_key = key
        if implot.begin_plot("##mosaic", (width, height), implot.FLAGS_EQUAL | implot.FLAGS_NO_LEGEND):
            implot.setup_axes("x [px]", "y [px]", y_flags=implot.AXIS_FLAGS_INVERT)
            if reset:
                implot.setup_axes_limits(*limits, implot.COND_ALWAYS)
            implot.setup_axes_limits(*limits, implot.COND_ONCE)
            implot.plot_image(
                "Mosaic", texture, (-0.5, -0.5), (nx - 0.5, ny - 0.5), uv0=(0, 1), uv1=(1, 0)
            )
            per_pixel = abs(implot.plot_to_pixels(1.0, 0.0)[0] - implot.plot_to_pixels(0.0, 0.0)[0])
            line = im.get_text_line_height()
            for label in model.tile_labels():
                text = fit_label(str(label["text"]), model.tile_width() * per_pixel - 8.0)
                implot.plot_text(text, float(label["x"]), float(label["y"]),
                                 pix_offset=(im.calc_text_size(text)[0] / 2 + 2, line / 2 + 2))
            self.item_rects["image"] = (*implot.get_plot_pos(), *implot.get_plot_size())
            limits_now = implot.get_plot_limits()
            self.view_limits = (limits_now.x_min, limits_now.x_max, limits_now.y_min, limits_now.y_max)
            implot.end_plot()
        im.set_item_tooltip(
            "The detector-window mosaic of the selected file. Scroll the mouse wheel to zoom, drag to pan, "
            "Reset view to see it all."
        )

    def _draw_levels(self, width: float, height: float) -> None:
        """The pixel-value histogram with the two display levels as draggable lines (the Qt level bar)."""
        model = self.model
        counts = model.histogram()
        if counts is None:
            return
        low, high = model.level_range()
        xs = np.log10(1.0 + counts.astype(float))
        ys = np.arange(len(counts), dtype=float)
        if implot.begin_plot("##levels", (width, height), implot.FLAGS_NO_LEGEND):
            implot.setup_axes("log n", "level")
            implot.setup_axes_limits(0.0, float(max(1.0, xs.max())) * 1.05, -1.0, 256.0, implot.COND_ALWAYS)
            implot.plot_line("Pixels", xs, ys)
            lo = implot.drag_line_y(1, float(low), (255, 210, 60, 255), 2.0)
            hi = implot.drag_line_y(2, float(high), (255, 120, 60, 255), 2.0)
            if lo.modified or hi.modified:
                a, b = sorted((float(lo.value), float(hi.value)))
                a, b = float(np.clip(round(a), 0, 254)), float(np.clip(round(b), 1, 255))
                if b <= a:
                    b = min(255.0, a + 1.0)
                model.auto_levels = False
                model.level_low, model.level_high = a, b
                self.tour.notify_used("level_low")
            self.item_rects["levels"] = (*implot.get_plot_pos(), *implot.get_plot_size())
            implot.end_plot()
        im.set_item_tooltip(
            "Histogram of the mosaic's pixel values (logarithmic counts). The two lines are the display levels: "
            "drag them to change Min and Max (Auto levels switches off)."
        )

    # -- file dialogs ------------------------------------------------------------------------------------------ #
    def _open_requested_dialog(self) -> None:
        kind, self.model.dialog = self.model.dialog, ""
        if not kind or self.dialog is not None:
            return
        title, mode, filters, _handler = self.DIALOGS[kind]
        name = self.model.dialog_filename(kind) if mode == "save" else ""
        self.dialog = FileDialog(
            title,
            mode=mode,
            filters=filters or (("All files", ("*",)),),
            directory=self.model.current_folder or self.model.folder or None,
            filename=name,
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
            path = str(result[0])
            if kind == "docx" and not path.lower().endswith(".docx"):
                path += ".docx"
            self.tour.notify_used(kind)
            self.model.remember_folder(path)
            self.queue(self.DIALOGS[kind][3], path)
        elif result is False or pressed == "close":
            self.dialog = None


def make_app(**kwargs: Any) -> TTTRImageBrowserApp:
    """The app (the imaging hub passes ``coordinator=``)."""
    from chisurf.emtk.i18n import install

    install()
    return TTTRImageBrowserApp(
        model=kwargs.get("model"),
        client=kwargs.get("client"),
        coordinator=kwargs.get("coordinator"),
        setups_file=kwargs.get("setups_file"),
    )
