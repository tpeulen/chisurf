"""Native detector-setup and folder/channel mosaic browser with full exports."""

from __future__ import annotations

import json
from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.dialog_window import DialogWindow
from emtk.docking import DockManager, Region, Split
from emtk.file_dialog import FileDialog

from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.help_guide import EmTkHelpWindow
from chisurf.emtk.image_canvas import ImageCanvas
from chisurf.emtk.jobs import SnapshotJob

from .native_model import NativeBrowserModel


class TTTRImageBrowserApp(ImApp):
    def __init__(self, model=None, client=None, coordinator=None):
        self.model = model or NativeBrowserModel(client)
        self.job = SnapshotJob(self.model)
        self.setup = ChannelDefinitionWidget(settings=self.model.setup_settings)
        self.canvas = ImageCanvas("channel_mosaic")
        self.page = 0
        self.pending_page = None
        self.filter = ""
        self.note = ""
        self._noted_file = None
        self.multi = False
        self.dialog = None
        self.file_window = None
        self.action = ""
        self.coordinator = coordinator
        self.error = ""
        self._pending_setup = None
        self.help = EmTkHelpWindow(
            title="TTTR Image Browser — Help",
            resource=Path(__file__).with_name("help.md"),
            owner=self,
        )
        self.docks = DockManager(Split("h", 0.32, Region("files"), Region("image")))
        self.docks.add_window(
            "files", "Files, ratings and exports", self.files, dock="files", closable=False
        )
        self.docks.add_window(
            "image", "Detector/window intensity mosaic", self.image, dock="image", closable=False
        )
        self.setup_docks = DockManager(Region("setup"))
        self.setup_docks.add_window(
            "setup", "Detector and acquisition setup", self.setup_view, dock="setup", closable=False
        )
        self.native_layouts = {"browser": self.docks, "setup": self.setup_docks}
        super().__init__(self.render, continuous=False)

    def start(self, method, *args):
        if self.job.busy:
            return False
        self.error = ""
        return self.job.start(method, *args)

    def open_folder(self, path):
        self.page = 1
        self.pending_page = 1
        self.start("open_folder", str(path))

    def open_paths(self, paths):
        for path in paths:
            value = Path(path)
            self.open_folder(value if value.is_dir() else value.parent)
            return

    def on_files_dropped(self, paths):
        if self.job.busy:
            return False
        for path in paths:
            if Path(path).is_dir():
                self.open_folder(path)
                return True
        self.error = "Drop a folder of photon images."
        return False

    def select(self, path):
        if self.job.busy:
            return
        self.model.current_file = str(path)
        if self.multi:
            if path in self.model.selected_files:
                self.model.selected_files.remove(path)
            else:
                self.model.selected_files.append(path)
        else:
            self.model.selected_files = [path]
        self.start("preview", str(path))
        if self.coordinator is not None:
            self.coordinator.set_pipeline(source=str(path))

    def next_step(self):
        if self.coordinator is None:
            self.error = "Open the browser inside the native Imaging Tools pipeline to use Next."
            return
        if self.model.current_file:
            self.coordinator.set_pipeline(source=self.model.current_file)
        self.coordinator.goto_role("pixel_intensity")
        self.coordinator.autorun_role("pixel_intensity")

    def choose(self, action):
        self.action = action
        folder = action in ("folder", "copy_files", "export_tiff")
        self.dialog = FileDialog(
            action.replace("_", " ").title(),
            mode="folder" if folder else "save",
            filters="DOCX (*.docx)" if action == "export_docx" else "JSON (*.json)",
            filename="images.docx" if action == "export_docx" else "image_browser.json",
            directory=self.model.current_folder,
        )
        self.file_window = DialogWindow(self.dialog.title, size=(700, 540), key="browser_file")
        self.file_window.show()

    def setup_view(self, box):
        if im.button("Use setup and browse"):
            self.apply_setup_settings(self.setup.model.get_settings())
            self.page = 1
            self.pending_page = 1
        im.set_item_tooltip(
            "Use detector routing, PIE windows, reading and calibration definitions for image mosaics."
        )
        self.setup.draw()

    def apply_setup_settings(self, payload):
        self.pending_page = 1
        if self.job.busy:
            self._pending_setup = payload
        else:
            self.start("apply_setup_settings", payload)

    def apply_pipeline_context(self, payload):
        files = payload.get("files") or ([payload["file"]] if payload.get("file") else [])
        if files:
            self.open_paths(files)

    def files(self, box):
        if im.button("Help"):
            self.help.show()
        im.set_item_tooltip(
            "Explain detector-window mosaics, metadata, caches, TIFF and report exports."
        )
        im.begin_disabled(self.job.busy or self.dialog is not None)
        for label, tip, action in [
            (
                "Open folder",
                "Scan a folder for compatible photon image files.",
                lambda: self.choose("folder"),
            ),
            ("Clear", "Clear the list and preview without deleting inputs.", self.model.clear),
            (
                "Clear caches",
                "Remove only image-browser cache artifacts and rebuild previews when selected.",
                lambda: self.start("clear_disk_caches"),
            ),
            (
                "Copy raw files",
                "Copy selected sources to a destination, preserving nested paths.",
                lambda: self.choose("copy_files"),
            ),
            (
                "Export TIFF",
                "Export full-intensity detector-window image stacks.",
                lambda: self.choose("export_tiff"),
            ),
            (
                "Export DOCX",
                "Export selected mosaics, star ratings and annotations to a Word report.",
                lambda: self.choose("export_docx"),
            ),
            (
                "Next → Intensity",
                "Hand the selected image to the native imaging pipeline.",
                self.next_step,
            ),
        ]:
            if im.button(label):
                action()
            im.set_item_tooltip(tip)
        changed, value = im.checkbox("Include subfolders", self.model.recursive)
        im.set_item_tooltip(
            "Recursively scan folders while preserving relative file paths and metadata."
        )
        if changed:
            self.start("set_recursive", value)
        options = self.model.rating_filter_options()
        index = (
            options.index(self.model.rating_filter) if self.model.rating_filter in options else 0
        )
        im.text_unformatted("Rating filter")
        changed, index = im.combo("##Rating filter", index, options)
        im.set_item_tooltip("Show all files, a minimum star rating, or only unrated files.")
        if changed:
            self.model.set_rating_filter(options[index])
        im.text_unformatted("Find files")
        _, self.filter = im.input_text("##Find files", self.filter)
        im.set_item_tooltip("Filter relative file names by substring.")
        _, self.multi = im.checkbox("Multiple selection", self.multi)
        im.set_item_tooltip(
            "Toggle entries into/out of the selection for batch copy, TIFF or DOCX export."
        )
        for entry in self.model.file_entries():
            if self.filter.casefold() not in entry["label"].casefold():
                continue
            if im.selectable(
                entry["label"] + " · " + entry["badge"], entry["id"] in self.model.selected_files
            ):
                self.select(entry["id"])
            im.set_item_tooltip(entry["id"])
        if im.button("Save settings"):
            self.choose("settings")
        im.set_item_tooltip(
            "Save active detector setup, scan mode, metadata filter and folder to JSON."
        )
        im.end_disabled()
        if self.model.current_folder:
            im.text_wrapped(self.model.current_folder)
        if self.job.busy:
            im.text_wrapped(self.job.progress)
        if self.error or self.job.error:
            im.text_wrapped(self.error or self.job.error)
        im.text_wrapped(getattr(self.model, "status_text", ""))

    def image(self, box):
        path = self.model.current_file
        entry = self.model._mosaic_cache.get(path)
        if path:
            im.text_wrapped(Path(path).name)
            changed, rating = im.slider_int("Stars", self.model.rating_of(path), 0, 3)
            im.set_item_tooltip("Persist a rating between zero and three stars for this image.")
            if changed and not self.job.busy:
                self.model.set_rating(path, rating)
            if path != self._noted_file:
                self.note = self.model.note_of(path)
                self._noted_file = path
            im.text_unformatted("Annotation")
            _, self.note = im.input_text("##Annotation", self.note)
            im.set_item_tooltip(
                "A per-file annotation saved in the folder’s image-browser metadata."
            )
            if im.button("Save annotation") and not self.job.busy:
                self.model.set_note(path, self.note)
            im.set_item_tooltip("Persist the current note without changing the image data.")
        image = entry["mosaic"] if entry else None
        labels = self.model.image_labels() if entry else []
        self.canvas.draw(image, labels=labels, pick_enabled=False)

    def animating(self):
        return self.job.busy or self.setup._future is not None or super().animating()

    def close(self):
        self.setup.close()

    def render(self):
        if self.job.poll():
            self.canvas.reset()
        if not self.job.busy and self._pending_setup is not None:
            payload = self._pending_setup
            self._pending_setup = None
            self.start("apply_setup_settings", payload)
        vp = im.get_main_viewport()
        width, height = vp.size
        im.set_next_window_pos((0, 0), im.Cond.ALWAYS)
        im.set_next_window_size((width, 28), im.Cond.ALWAYS)
        if im.begin("Browser pages", flags=im.WindowFlags.NO_TITLE_BAR | im.WindowFlags.NO_RESIZE):
            if im.begin_tab_bar("browser_pages"):
                for index, label in enumerate(["Detector setup", "Image browser"]):
                    if im.begin_tab_item(
                        label, im.TabItemFlags.SET_SELECTED if self.pending_page == index else 0
                    ):
                        self.page = index
                        im.end_tab_item()
                    im.set_item_tooltip(
                        "Configure detector/scanner parameters."
                        if index == 0
                        else "Browse and annotate channel mosaics."
                    )
                im.end_tab_bar()
                self.pending_page = None
        im.end()
        (self.setup_docks if self.page == 0 else self.docks).draw((0, 28, width, height - 28))
        if self.dialog:
            pressed = self.file_window.begin((0, 0, width, height))
            result = self.dialog.draw()
            if result:
                try:
                    path = Path(result[0])
                    if self.action == "folder":
                        self.open_folder(path)
                    elif self.action == "settings":
                        path.with_suffix(".json").write_text(
                            json.dumps(
                                dict(
                                    folder=self.model.current_folder,
                                    setup=self.model.setup_settings,
                                    recursive=self.model.recursive,
                                    rating_filter=self.model.rating_filter,
                                ),
                                indent=2,
                            )
                        )
                    else:
                        self.start(
                            self.action,
                            str(
                                path.with_suffix(".docx") if self.action == "export_docx" else path
                            ),
                        )
                    self.dialog = None
                except Exception as exc:
                    self.error = str(exc)
            elif result is False or pressed == "close":
                self.dialog = None
            self.file_window.end()
        self.setup.draw_dialogs((0, 0, width, height))
        if self.help.open:
            self.help.draw((0, 0, width, height))


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    return TTTRImageBrowserApp(
        model=kwargs.get("model"),
        client=kwargs.get("client"),
        coordinator=kwargs.get("coordinator"),
    )
