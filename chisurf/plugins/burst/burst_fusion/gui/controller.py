"""Native burst fusion execution, configuration and workflow handoff."""

import copy
import json
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from threading import Event


class FusionController:
    def __init__(self, model):
        self.model = model
        self.running = False
        self.writing = False
        self.status = ""
        self._cancel = Event()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="burst-fusion")
        self._future = None
        self.action = "folder"
        self.dialog = None
        self.channel_text = json.dumps(
            {"detectors": model.detectors, "windows": model.windows}, indent=2
        )
        from chisurf.emtk.dataset_picker import DatasetPicker

        self.datasets = DatasetPicker(
            kinds=["analysis_result", "burst_data"], on_paths=self.on_paths_dropped
        )

    def on_paths_dropped(self, paths):
        """Adopt the first dropped burst folder or container; report anything else."""
        from chisurf.core.fio.fluorescence import burst_tree

        for path in map(Path, paths):
            if path.is_dir() or burst_tree.is_container_path(path):
                self.model.set_folder(str(path))
                self.status = ""
                return
        if paths:
            self.status = f"Burst fusion reads a burst-analysis folder; {Path(paths[0]).name} is not one."

    def progress(self, fraction=0, message=""):
        if self._cancel.is_set():
            raise CancelledError()
        if message:
            self.status = message

    def _execute(self, snapshot, action):
        self.progress()
        if action == "demo":
            snapshot.load_demo(progress=self.progress)
        else:
            snapshot.analyze(cancel_check=self.progress)
            self.progress()
            if action == "fuse":
                # Finish the writer as one operation; stopping halfway could leave
                # an incomplete output folder and source grouping companions.
                self.writing = True
                try:
                    snapshot.write()
                finally:
                    self.writing = False
        return snapshot

    def run(self, action="fuse"):
        if self.running:
            return
        if action != "demo":
            reason = self.model.can_run()
            if reason:
                self.status = reason
                return
        self._cancel.clear()
        snapshot = copy.copy(self.model)
        snapshot.settings = copy.deepcopy(self.model.settings)
        snapshot.detectors, snapshot.windows = (
            copy.deepcopy(self.model.detectors),
            copy.deepcopy(self.model.windows),
        )
        snapshot._observers = []
        snapshot.folder_written = None
        self.running = True
        self._action = action
        self.status = {
            "demo": "Generating demo …",
            "fuse": "Estimating and fusing bursts …",
            "estimate": "Estimating same-molecule probability …",
        }[action]
        self._future = self._executor.submit(self._execute, snapshot, action)

    def estimate(self):
        self.run("estimate")

    def demo(self):
        self.run("demo")

    def poll(self):
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            snapshot = future.result()
            if self._cancel.is_set() and not (self._action == "fuse" and snapshot._written):
                raise CancelledError()
            observers, handoff = self.model._observers, self.model.folder_written
            self.model.__dict__.update(snapshot.__dict__)
            self.model._observers, self.model.folder_written = observers, handoff
            if self._action == "fuse" and snapshot._written and callable(handoff):
                handoff(snapshot._written)
            self.model.notify(
                "written"
                if self._action == "fuse"
                else ("demo" if self._action == "demo" else "analyzed")
            )
            # The model's status is drawn under the actions; a copy here doubled it.
            self.status = ""
        except CancelledError:
            self.status = "Fusion cancelled before writing; previous results retained."
        except Exception as exc:
            self.status = f"Error: {exc}"
        finally:
            self.running = False

    def stop(self):
        if self.running:
            self._cancel.set()
            self.status = (
                "Finishing the current output write …" if self.writing else "Stopping fusion …"
            )

    def apply_channels(self, text):
        data = json.loads(text)
        detectors, windows = data.get("detectors", {}), data.get("windows", {})
        if not isinstance(detectors, dict) or not isinstance(windows, dict):
            raise ValueError("detectors and windows must be JSON objects.")
        for name, detector in detectors.items():
            channels = detector.get("chs", [])
            if not channels or any(not isinstance(ch, int) or ch < 0 for ch in channels):
                raise ValueError(f"{name}: provide nonnegative routing channels in chs.")
        self.model.detectors, self.model.windows = detectors, windows
        self.channel_text = json.dumps(data, indent=2)
        self.status = "Detector and PIE window definitions applied."

    def save_settings(self, path):
        data = self.model.settings.to_dict()
        data.update(detectors=self.model.detectors, windows=self.model.windows)
        Path(path).write_text(json.dumps(data, indent=2))
        self.status = "Fusion settings saved."

    def load_settings(self, path):
        from ..api.models import FusionSettings

        data = json.loads(Path(path).read_text())
        settings = FusionSettings.from_dict(data)
        if (
            not 0 <= settings.threshold <= 1
            or settings.tau_min_s <= 0
            or settings.tau_max_s <= settings.tau_min_s
            or settings.n_bins < 5
            or settings.min_pairs < 1
            or settings.max_group < 0
            or settings.max_gap_ms < 0
        ):
            raise ValueError("Invalid fusion parameters.")
        if "detectors" in data or "windows" in data:
            self.apply_channels(json.dumps(data))
        self.model.settings = settings
        self.model._invalidate()
        self.model.notify("changed")
        self.status = "Fusion settings loaded."

    def export_summary(self, path):
        if not self.model.has_analysis():
            raise ValueError("Estimate or fuse bursts first.")
        Path(path).write_text(
            json.dumps(
                {
                    "settings": self.model.settings.to_dict(),
                    "statistics": self.model.analysis.statistics,
                    "summary": self.model.summary_rows(),
                    "output_folder": self.model.written_folder,
                },
                indent=2,
                default=lambda value: value.tolist() if hasattr(value, "tolist") else str(value),
            )
        )
        self.status = "Fusion report exported."

    #: Per action: the dialog's title, mode and file filters.
    DIALOGS = {
        "folder": ("Select burst folder", "folder", None),
        "load": ("Load fusion settings", "open", [("JSON", ["*.json"])]),
        "save": ("Save fusion settings", "save", [("JSON", ["*.json"])]),
        "export": ("Export fusion report", "save", [("JSON", ["*.json"])]),
    }

    def browse(self, action="folder"):
        """Open the file dialog for *action* (folder, load, save, export)."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title, mode, filters = self.DIALOGS[action]
        self.action = action
        options = {"filters": filters} if filters else {}
        filename = {"save": "fusion.json", "export": "fusion_report.json"}.get(action)
        self.dialog = FileDialog(title, mode=mode, filename=filename, **options)
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="burst-fusion-file")
        self._dialog_window.show()

    def draw_controls(self):
        from emtk import im

        im.begin_disabled(self.running)
        for label, callback, tip in (
            (
                "Open burst folder",
                self.browse,
                "Select the burst-analysis folder containing bi4_bur.",
            ),
            (
                "MMFDB datasets",
                self.datasets.open,
                "Resolve an existing burst analysis from the database.",
            ),
            (
                "Load settings",
                lambda: self.browse("load"),
                "Load a saved fusion parameter JSON file.",
            ),
            (
                "Save settings",
                lambda: self.browse("save"),
                "Save current fusion parameters as JSON.",
            ),
            (
                "Export fusion report",
                lambda: self.browse("export"),
                "Export before/after statistics and the output folder path.",
            ),
        ):
            if im.button(label):
                callback()
            im.set_item_tooltip(tip)
        im.text("TTTR file type:")
        changed, file_type = im.input_text("##fusion_type", self.model.settings.file_type)
        im.set_item_tooltip(
            "Use auto for header detection or specify SPC-130, PTU, HT3 or HDF; a source manifest takes precedence."
        )
        if changed:
            self.model.settings.file_type = file_type
        expanded = im.collapsing_header("Detector definitions")
        im.set_item_tooltip(
            "Define detector routing and PIE windows when a legacy source folder has no reading manifest."
        )
        if expanded:
            changed, text = im.input_text_multiline(
                "##fusion_channels", self.channel_text, size=(0, 140)
            )
            im.set_item_tooltip(
                "JSON with named detectors (chs and micro_time_ranges) and named PIE windows."
            )
            if changed:
                self.channel_text = text
            if im.button("Apply detector definitions"):
                try:
                    self.apply_channels(self.channel_text)
                except Exception as exc:
                    self.status = f"Invalid detector definitions: {exc}"
            im.set_item_tooltip(
                "Validate and apply detector definitions used to regenerate fused burst tables."
            )
        im.end_disabled()
        if im.button("Stop fusion"):
            self.stop()
        im.set_item_tooltip(
            "Cancel the estimate before writing; an output write already started finishes consistently."
        )
        if self.status:
            im.text_wrapped(self.status)

    def draw_dialogs(self, frame):
        """The file dialog in a sized window over *frame*, and the MMFDB picker."""
        if self.dialog is not None:
            pressed = self._dialog_window.begin(frame)
            result = self.dialog.draw()
            self._dialog_window.end()
            if result:
                try:
                    if self.action == "folder":
                        self.on_paths_dropped([result[0]])
                    elif self.action == "load":
                        self.load_settings(result[0])
                    elif self.action == "save":
                        self.save_settings(result[0])
                    else:
                        self.export_summary(result[0])
                except Exception as exc:
                    self.status = f"Error: {exc}"
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
        self.datasets.render(frame)

    def close(self):
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
