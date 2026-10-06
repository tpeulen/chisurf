"""Native input configuration and background execution without Qt."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event


class BackgroundController:
    def __init__(self, model):
        self.model = model
        self.detectors = {
            "green": {"chs": [0, 8], "micro_time_ranges": [[0, 32768]]},
            "red": {"chs": [1, 9], "micro_time_ranges": [[0, 32768]]},
        }
        if model.channels_provider is None:
            model.channels_provider = lambda: self.detectors
        from chisurf.emtk.channel_definition import ChannelDefinitionWidget

        self.channel_definition = ChannelDefinitionWidget(
            {
                "detectors": copy.deepcopy(model._channels()),
                "windows": {},
                "tttr_reading": {
                    "file_type": "auto",
                    "macro_time_resolution": 0.0,
                    "micro_time_resolution": 0.0,
                    "micro_time_binning": 1,
                },
            },
            on_changed=self._channels_changed,
        )
        model.channels_provider = lambda: self.channel_definition.model.get_settings()["detectors"]
        model.tttr_provider = self.channel_definition.model.open_tttr
        self.detector_text = json.dumps(model._channels(), indent=2)
        self.status = ""
        self.running = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="burst-background")
        self._future = None
        self._cancel = Event()
        self.dialog = None
        self.dialog_action = "files"
        from chisurf.emtk.dataset_picker import DatasetPicker

        self.datasets = DatasetPicker(on_paths=self.add_files)

    def _channels_changed(self, settings):
        self.detectors = settings["detectors"]
        if hasattr(self.model, "micro_time_binning"):
            self.model.micro_time_binning = max(
                1, int(settings["tttr_reading"].get("micro_time_binning", 1))
            )
        self.model.notify("channels")

    def add_files(self, paths):
        self.model.add_files([str(p) for p in paths])

    def remove_file(self, path):
        if path not in self.model.files:
            return
        self.model.files.remove(path)
        for field in ("backgrounds", "diagnostics", "_interphoton"):
            if hasattr(self.model, field):
                getattr(self.model, field).pop(path, None)
        for field in ("_display", "_mle"):
            if hasattr(self.model, field):
                setattr(self.model, field, {})
        self.model.notify("files")
        self.status = "File removed; recompute to refresh pooled results."

    MEASUREMENTS = {".ptu", ".pto", ".spc", ".ht3", ".pt3", ".h5", ".hdf5"}

    def on_paths_dropped(self, paths):
        """Add dropped files, and the measurements in dropped folders."""
        files = []
        for path in map(Path, paths):
            if path.is_file():
                files.append(path)
            elif path.is_dir():
                found = sorted(p for p in path.iterdir() if p.suffix.lower() in self.MEASUREMENTS)
                # A .pto beside a vendor file of the same stem is the container this tool
                # (and the burst search) writes next to the photons, not a second measurement.
                vendor = {p.stem for p in found if p.suffix.lower() != ".pto"}
                files.extend(
                    p for p in found if not (p.suffix.lower() == ".pto" and p.stem in vendor)
                )
        self.add_files(files)

    def apply_detectors(self, text):
        try:
            parsed = json.loads(text)
            if "detectors" in parsed:
                parsed = parsed["detectors"]
            if not isinstance(parsed, dict) or not parsed:
                raise ValueError("Define at least one named detector.")
            for name, info in parsed.items():
                if (
                    not isinstance(info, dict)
                    or not isinstance(info.get("chs"), list)
                    or not info["chs"]
                ):
                    raise ValueError(f"{name}: provide a nonempty chs list.")
                if any(not isinstance(ch, int) or ch < 0 for ch in info["chs"]):
                    raise ValueError(f"{name}: routing channels must be nonnegative integers.")
                for gate in info.get("micro_time_ranges", []):
                    if len(gate) != 2 or gate[0] < 0 or gate[1] <= gate[0]:
                        raise ValueError(f"{name}: use increasing microtime ranges.")
            self.detectors = parsed
            self.channel_definition.model.data["detectors"] = copy.deepcopy(parsed)
            self.channel_definition.model.changed()
            self.detector_text = json.dumps(parsed, indent=2)
            self.status = "Detector settings applied."
            return True
        except (ValueError, TypeError, KeyError) as exc:
            self.status = f"Invalid detector settings: {exc}"
            return False

    def load_setup(self, path):
        return self.apply_detectors(Path(path).read_text())

    def save_setup(self, path):
        Path(path).write_text(json.dumps({"detectors": self.model._channels()}, indent=2))
        self.status = "Detector setup saved."

    #: Per action: the dialog's title, mode and file filters.
    DIALOGS = {
        "files": (
            "Select TTTR files",
            "open",
            [("TTTR", ["*.ptu", "*.spc", "*.ht3", "*.pt3", "*.h5", "*.hdf5"])],
        ),
        "folder": ("Add TTTR folder", "folder", None),
        "load_setup": ("Load detector setup", "open", [("JSON", ["*.json"])]),
        "save_setup": ("Save detector setup", "save", [("JSON", ["*.json"])]),
    }

    def browse(self, action="files"):
        """Open the file dialog for *action* (files, folder, load_setup, save_setup)."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title, mode, filters = self.DIALOGS[action]
        self.dialog_action = action
        options = {"filters": filters} if filters else {}
        self.dialog = FileDialog(
            title,
            mode=mode,
            multiselect=action == "files",
            filename="detectors.json" if action == "save_setup" else None,
            **options,
        )
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="burst-background-file")
        self._dialog_window.show()

    def _snapshot(self):
        snapshot = copy.copy(self.model)
        snapshot.files = list(self.model.files)
        detectors = copy.deepcopy(self.model._channels())
        snapshot.channels_provider = lambda: detectors
        from chisurf.core.setup_channel_definition import ChannelDefinition

        reading = ChannelDefinition(self.channel_definition.model.get_settings())
        snapshot.tttr_provider = lambda path: reading.open_tttr(path, cancel_cb=self._cancel.is_set)
        snapshot._observers = []
        snapshot._interphoton = {}
        snapshot.backgrounds, snapshot.diagnostics = {}, {}
        snapshot._write_containers = lambda: None
        return snapshot

    def _execute(self, snapshot):
        snapshot.estimate(cancel_check=self.check_cancel)
        self.check_cancel()
        return snapshot

    def check_cancel(self):
        if self._cancel.is_set():
            raise InterruptedError("Computation cancelled")

    def run(self):
        if self.running:
            return
        if self.channel_definition._future is not None:
            self.status = "Wait for the calibration read to finish, or cancel it."
            return
        reason = self.model.can_estimate()
        if reason:
            self.status = reason
            return
        self._cancel.clear()
        self.running = True
        self.status = "Estimating background …"
        self._future = self._executor.submit(self._execute, self._snapshot())

    def _publish(self, snapshot):
        for field in (
            "backgrounds",
            "diagnostics",
            "_interphoton",
            "fit_from_ms",
            "fit_to_ms",
            "max_dt_ms",
            "status",
        ):
            setattr(self.model, field, getattr(snapshot, field))
        self.model._write_containers()
        self.model.notify("computed")
        # The parameters pane shows the model's status; a copy here doubled it.
        self.status = ""

    def poll(self):
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            snapshot = future.result()
            self.check_cancel()
            self._publish(snapshot)
        except InterruptedError:
            self.status = "Computation cancelled."
        except Exception as exc:
            self.status = "Computation cancelled." if self._cancel.is_set() else f"Error: {exc}"
        finally:
            self.running = False

    def stop(self):
        if self.running:
            self._cancel.set()
            self.status = "Stopping …"

    def clear(self):
        self.stop()
        self.model.clear()
        if hasattr(self.model, "_interphoton"):
            self.model._interphoton.clear()
        self.status = "Files and results cleared."

    def _show_channels_button(self, remember=None):
        from emtk import im

        if im.button("Channel definition"):
            callback = getattr(self, "on_show_channels", None)
            if callable(callback):
                callback()
        im.set_item_tooltip(
            "Open the complete detector setup, timing, calibration, PIE, TAC and optical editor."
        )
        if remember is not None:
            remember("bg_channels")

    #: The guide's key for each input button.
    INPUT_KEYS = {"Open TTTR files": "files"}

    def draw_inputs(self, remember=None, track=None):
        """File inputs, the channel editor button, Stop and the status; *remember* records rects for the guide."""
        from emtk import im

        im.text("Measurements & detectors")
        im.begin_disabled(self.running)
        for label, callback, tip in (
            ("Open TTTR files", self.browse, "Choose one or more photon measurement files."),
            (
                "Add TTTR folder",
                lambda: self.browse("folder"),
                "Add supported photon measurements from a folder.",
            ),
            (
                "MMFDB datasets",
                self.datasets.open,
                "Browse database measurements and resolve their local paths.",
            ),
            ("Clear files", self.clear, "Remove loaded files and analysis results."),
        ):
            if im.button(label):
                if track is not None and label in self.INPUT_KEYS:
                    track(self.INPUT_KEYS[label])
                callback()
            im.set_item_tooltip(tip)
            if remember is not None and label in self.INPUT_KEYS:
                remember(self.INPUT_KEYS[label])
        for path in list(self.model.files):
            im.text_wrapped(str(path))
            if im.button(f"Remove##{path}"):
                self.remove_file(path)
            im.set_item_tooltip(f"Remove {Path(path).name} from the analysis.")
        self._show_channels_button(remember)
        im.end_disabled()
        if im.button("Stop computation"):
            self.stop()
        im.set_item_tooltip("Cancel at the next file boundary and retain the previous results.")
        if self.status:
            im.text_wrapped(self.status)
        im.separator()

    def draw_dialogs(self, frame):
        """The file dialog in a sized window over *frame*, the MMFDB picker, the channel editor's dialogs."""
        if self.dialog is not None:
            pressed = self._dialog_window.begin(frame)
            result = self.dialog.draw()
            self._dialog_window.end()
            if result:
                try:
                    if self.dialog_action == "files":
                        self.add_files(result)
                    elif self.dialog_action == "folder":
                        self.on_paths_dropped(result)
                    elif self.dialog_action == "load_setup":
                        self.load_setup(result[0])
                    else:
                        self.save_setup(result[0])
                except Exception as exc:
                    self.status = f"Error: {exc}"
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
        self.datasets.render(frame)
        self.channel_definition.draw_dialogs(frame)

    def close(self):
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.channel_definition.close()
