"""Qt-free launcher for the shared header table and scientific file model.

The input is the Datasets workspace: the Header tags dock draws the generated Input section (the
manifest's ``accepts[].from_workspace``) over this app, and :func:`receive_photons` reads the
picked photon stream. The edited copy a save writes comes back into the workspace as a child of it.
"""

from pathlib import Path

from emtk import im
from emtk.app import ImApp
from emtk.file_dialog import FileDialog

from chisurf.core.plugin.workspace_input import WorkspaceInputMixin
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .app import HeaderEditorGui
from .view_model import HeaderEditorViewModel


class NativeHeaderEditor(WorkspaceInputMixin, ImApp):
    workspace_input_plugin = "tttr_header_edit"

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
        #: The workspace dataset the header is of: the saved copy becomes its child.
        self.source_uid = ""
        self.workspace_input_app = self
        self.header_gui = HeaderEditorGui(self, on_save=self.choose_save)
        self.workspace_input_on_used = self.header_gui.tour.notify_used
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
            from chisurf.core.fio.address import container_of

            self.last_directory = str(container_of(str(path)).parent)
            self.message = "Header loaded."

        return self.job.start(work, publish, self.error)

    def error(self, exc):
        self.message = str(exc)

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
        target = str(path) if str(path).lower().endswith(".ptu") else f"{path}.ptu"

        def saved(_):
            self.message = f"Saved edited PTU: {target}"
            # The edited copy is a photon stream of its own, made from the picked one.
            from chisurf.plugins.tttr.workspace_io import add_photons

            add_photons(target, result_of=self.source_uid)

        return self.job.start(lambda: model.save(str(path)), saved, self.error)

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

    def load_example(self):
        """Generate the demonstration PTU in the settings cache, add it to the workspace and read
        its header, as a picked row would be."""
        from chisurf.plugins.tttr.workspace_io import example_into_workspace

        from ..demo import demo_folder, make_demo

        if self.job.running:
            return False
        try:
            path = make_demo(demo_folder())
        except OSError as exc:
            self.error(exc)
            return False
        example_into_workspace(path, receive_photons, self, key="file")
        return True

    def export_settings(self):
        return {"last_directory": self.last_directory}

    def restore_settings(self, settings):
        self.last_directory = str(settings.get("last_directory", ""))

    def close(self):
        self.job.close()


def create_app(json_data=None):
    return NativeHeaderEditor(json_data=json_data)


def receive_photons(app: NativeHeaderEditor, payload: dict) -> None:
    """Hand-off receiver (manifest ``accepts`` ``photons``): read the header of ``payload["file"]``,
    an address as the workspace hands it (a TTTR file or a container's photon stream)."""
    from chisurf.core.fio.address import container_of
    from chisurf.core.plugin.workspace_input import read_address

    address = read_address(str(payload["file"]))
    if not container_of(address).is_file():
        raise FileNotFoundError(f"{address} does not exist")
    if not app.load(address):
        raise RuntimeError("the tool is busy; try again when it has finished")
    app.source_uid = str((payload.get("datasets") or [""])[0])
