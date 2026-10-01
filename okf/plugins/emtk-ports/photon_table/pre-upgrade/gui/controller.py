"""Standalone EMTK controller; Qt remains an optional compatibility host."""

from __future__ import annotations

from pathlib import Path

from emtk import im
from emtk.file_dialog import FileDialog

from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from ..core.model import PhotonTableModel
from .app import PhotonTableApp


class PhotonTableController:
    """Own photon loading and navigation independently of any window toolkit."""

    def __init__(self):
        self._model = PhotonTableModel()
        self.first_index = 0
        self.rows_per_page = 200
        self.channel_filter = -1
        self.error = ""
        self.job = BackgroundJob()
        self.dialog = None
        self.app = _StandaloneApp(self, on_browse=self.browse)

    def browse(self):
        self.dialog = FileDialog(
            "Open TTTR", filters="TTTR (*.ptu *.phu *.ht2 *.ht3 *.pt3 *.t3r);;All files (*)"
        )

    def load_file(self, path):
        if self.job.running:
            return False
        if not Path(path).is_file():
            self.error = f"Could not open {path}: file does not exist"
            return False

        def work():
            model = PhotonTableModel()
            model.load_file(str(path))
            return model

        def publish(model):
            self._model = model
            self.first_index = 0
            self.channel_filter = -1
            self.error = ""

        return self.job.start(
            work, publish, lambda exc: setattr(self, "error", f"Could not open {path}: {exc}")
        )

    def on_paths_dropped(self, paths):
        if paths:
            self.load_file(paths[0])


class _StandaloneApp(PhotonTableApp):
    def close(self):
        self.tool.job.close()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.continuous = True

    def _render(self):
        self.tool.job.poll()
        super()._render()
        if self.tool.job.running:
            if im.begin("Loading TTTR"):
                im.text("Loading photon table…")
                if im.button("Stop loading"):
                    self.tool.job.stop()
                im.set_item_tooltip("Discard the pending load; the existing table stays available.")
            im.end()
        if self.tool.error:
            if im.begin("Load error"):
                im.text_wrapped(self.tool.error)
            im.end()
        if self.tool.dialog is not None:
            if im.begin("Open TTTR file"):
                result = self.tool.dialog.draw()
                if result:
                    self.tool.load_file(result[0])
                    self.tool.dialog = None
                elif result is False:
                    self.tool.dialog = None
            im.end()


def create_app():
    """Create the runnable pure EMTK plugin application."""
    return PhotonTableController().app
