"""Native IRF/background workflow and explicit MLE handoff."""

import copy
from pathlib import Path

import numpy as np

from chisurf.plugins.burst.burst_background.gui.controller import BackgroundController


class IrfBackgroundController(BackgroundController):
    def __init__(self, model, mle_receiver=None):
        super().__init__(model)
        self.mle_receiver = mle_receiver

    def draw_inputs(self, remember=None, track=None):
        """The data row (open, add, MMFDB, clear, channel editor) and the loaded files, in one wrapped row."""
        from emtk import im

        from chisurf.plugins.emtk_layout import button_row

        im.text("Measurements & detectors")
        im.begin_disabled(self.running)
        pressed = button_row([
            {"label": "Open TTTR files", "key": "files", "tip": "Choose one or more photon measurement files."},
            {"label": "Add TTTR folder", "tip": "Add supported photon measurements from a folder."},
            {"label": "MMFDB datasets", "tip": "Browse database measurements and resolve their local paths."},
            {"label": "Clear files", "tip": "Remove loaded files and analysis results."},
            {"label": "Channel definition", "key": "bg_channels",
             "tip": "Open the complete detector setup, timing, calibration, PIE, TAC and optical editor."},
        ], remember=remember)
        if pressed == "files":
            if track is not None:
                track("files")
            self.browse()
        elif pressed == "Add TTTR folder":
            self.browse("folder")
        elif pressed == "MMFDB datasets":
            self.datasets.open()
        elif pressed == "Clear files":
            self.clear()
        elif pressed == "bg_channels":
            callback = getattr(self, "on_show_channels", None)
            if callable(callback):
                callback()
        for path in list(self.model.files):
            im.text_wrapped(str(path))
            if im.button(f"Remove##{path}"):
                self.remove_file(path)
            im.set_item_tooltip(f"Remove {Path(path).name} from the analysis.")
        im.end_disabled()
        im.separator()

    def draw_status(self):
        """The controller's message (a refused run, a stop); the extraction result is the window's own line."""
        from emtk import im

        if self.status:
            im.text_wrapped(self.status)

    def _snapshot(self):
        snapshot = copy.copy(self.model)
        snapshot.files = list(self.model.files)
        detectors = copy.deepcopy(self.model._channels())
        snapshot.channels_provider = lambda: detectors
        from chisurf.core.setup_channel_definition import ChannelDefinition

        reading = ChannelDefinition(self.channel_definition.model.get_settings())
        snapshot.tttr_provider = lambda path: reading.open_tttr(path, cancel_cb=self._cancel.is_set)
        snapshot._observers = []
        snapshot._display, snapshot._mle = {}, {}
        return snapshot

    def _execute(self, snapshot):
        snapshot.compute(cancel_check=self.check_cancel)
        self.check_cancel()
        return snapshot

    def run(self):
        if self.running:
            return
        if self.channel_definition._future is not None:
            self.status = "Wait for the calibration read to finish, or cancel it."
            return
        reason = self.model.can_compute()
        if reason:
            self.status = reason
            return
        self._cancel.clear()
        self.running = True
        self.status = "Extracting IRF and background …"
        self._future = self._executor.submit(self._execute, self._snapshot())

    def _publish(self, snapshot):
        self.model._display, self.model._mle = snapshot._display, snapshot._mle
        self.model.notify("computed")
        # The window's status line already reports the extraction; a copy here doubled it.
        self.status = ""

    def send_to_mle(self):
        if not self.model.has_results():
            self.status = "Compute the IRF and background first."
            return False
        if callable(self.mle_receiver):
            try:
                count = self.mle_receiver(self.model.mle_patterns())
                self.status = f"Sent IRF + background to MLE for {count} detector(s)."
                return True
            except Exception as exc:
                self.status = f"Error sending to MLE: {exc}"
                return False
        self.status = (
            "Open inside Burst Analysis to feed MLE, or export the patterns for scripted use."
        )
        return False

    def export_patterns(self, path):
        if not self.model.has_results():
            raise ValueError("Compute the IRF and background first.")
        arrays = {
            f"{name}/{kind}": value
            for name, patterns in self.model.mle_patterns().items()
            for kind, value in patterns.items()
        }
        np.savez_compressed(path, **arrays)
        self.status = f"MLE patterns exported: {path}"

    def browse(self, action="files"):
        """The base dialogs, plus the MLE-pattern export (in the same sized window)."""
        if action != "patterns":
            return super().browse(action)
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        if not self.model.has_results():
            self.status = "Compute the IRF and background first."
            return
        self.dialog_action = "patterns"
        self.dialog = FileDialog(
            "Export MLE patterns",
            mode="save",
            filename="irf_background.npz",
            filters=[("NumPy patterns", ["*.npz"])],
        )
        self._dialog_window = DialogWindow("Export MLE patterns", size=(640.0, 460.0), key="burst-irf-bg-file")
        self._dialog_window.show()

    def save_setup(self, path):
        if self.dialog_action == "patterns":
            self.export_patterns(path)
        else:
            super().save_setup(path)
