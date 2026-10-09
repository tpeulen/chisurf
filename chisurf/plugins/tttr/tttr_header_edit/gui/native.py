"""Qt-free launcher for the shared header table and scientific file model."""

from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.file_dialog import FileDialog

from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .app import HeaderEditorGui
from .view_model import OPEN_FILTER, HeaderEditorViewModel


class NativeHeaderEditor(ImApp):
    def __init__(self, json_data=None):
        self.model = HeaderEditorViewModel()
        if json_data:
            self.model.load_json(json_data)
        self.validation_error = ""
        self.message = ""
        self.job = BackgroundJob()
        self.dialog = None
        self.dialog_callback = None
        self.last_directory = ""
        self.header_gui = HeaderEditorGui(self, on_open=self.choose_open, on_save=self.choose_save)
        self.docks = self.header_gui.docks
        super().__init__(gui=self.render, continuous=True)

    def load(self, path):
        if self.job.running:
            return False

        def work():
            model = HeaderEditorViewModel()
            model.load_file(str(path))
            return model

        def publish(model):
            self.model = model
            self.validation_error = ""
            self.header_gui.rebuild_rows()
            self.last_directory = str(Path(path).parent)
            self.message = "Header loaded."

        return self.job.start(work, publish, self.error)

    def error(self, exc):
        self.message = str(exc)

    def choose_open(self):
        if not self.job.running:
            self.dialog = FileDialog(
                "Open TTTR file", filters=OPEN_FILTER, directory=self.last_directory or None
            )
            self.dialog_callback = lambda paths: self.load(paths[0]) if paths else None

    def choose_save(self):
        self.header_gui._commit()
        reason = self.validation_error or self.model.can_save()
        if reason:
            self.message = reason
            return
        if not self.job.running:
            self.dialog = FileDialog(
                "Save edited header as PTU",
                mode="save",
                filters="PTU (*.ptu)",
                directory=self.last_directory or None,
                filename=Path(self.model.opened_path).stem + "_edited.ptu",
            )
            self.dialog_callback = lambda paths: self.save(paths[0]) if paths else None

    def save(self, path):
        self.header_gui._commit()
        if self.job.running or self.validation_error:
            self.message = self.validation_error
            return False
        from copy import deepcopy

        model = deepcopy(self.model)
        model._observers = []
        return self.job.start(
            lambda: model.save(str(path)),
            lambda _: setattr(self, "message", f"Saved edited PTU: {path}"),
            self.error,
        )

    def render(self):
        self.job.poll()
        im.begin_disabled(self.job.running)
        self.header_gui.draw()
        im.end_disabled()
        # Status belongs inside the existing dock rather than a covering window.
        if self.dialog:
            im.begin("Header file chooser")
            result = self.dialog.draw()
            if result is not None:
                callback = self.dialog_callback
                self.dialog = None
                if result:
                    callback(result)
            im.end()

    def on_paths_dropped(self, paths):
        if paths:
            self.load(paths[0])

    def export_settings(self):
        return {"last_directory": self.last_directory}

    def restore_settings(self, settings):
        self.last_directory = str(settings.get("last_directory", ""))

    def close(self):
        self.job.close()


def create_app(json_data=None):
    return NativeHeaderEditor(json_data=json_data)
