"""Native input configuration and background execution without Qt."""

import copy
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

from emtk.i18n import tr


class BackgroundController:
    #: The plugin whose manifest ``accepts`` entry ``photons`` the Input section feeds.
    PLUGIN = "burst_background"

    def __init__(self, model, app=None):
        self.model = model
        self.on_show_channels: Callable[[], None] | None = None
        self.detectors = {
            "G|G": {"chs": [0, 8], "micro_time_ranges": [[0, 32768]]},
            "R|G": {"chs": [1, 9], "micro_time_ranges": [[0, 32768]]},
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
            host_app=None,
        )
        model.channels_provider = lambda: self.channel_definition.model.get_settings()["detectors"]
        model.tttr_provider = lambda path: self.channel_definition.model.open_tttr(path)
        self.detector_text = json.dumps(model._channels(), indent=2)
        self.status = ""
        self.running = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="burst-background")
        self._future = None
        self._cancel = Event()
        self.dialog = None
        self.dialog_action = "save_setup"
        # The Input section: the workspace's photon streams (manifest ``accepts`` ``photons``).
        from emtk.view_form import FormState

        from chisurf.plugins.burst.workspace_io import NamedWorkspaceInput, input_spec

        manifest = Path(__file__).resolve().parents[2] / self.PLUGIN / "manifest.json"
        self.input = NamedWorkspaceInput(self.PLUGIN, "photons", app=app)
        self.input_spec = input_spec(manifest, "photons")
        self.input_form = FormState()
        #: Which workspace dataset each file came from: its results go into that dataset's
        #: analysis container in the project, never beside the photons.
        self.model.sources = {}

    def _channels_changed(self, settings):
        self.detectors = settings["detectors"]
        if hasattr(self.model, "micro_time_binning"):
            self.model.micro_time_binning = max(
                1, int(settings["tttr_reading"].get("micro_time_binning", 1))
            )
        self.model.notify("channels")

    def add_files(self, paths):
        self.model.add_files([str(p) for p in paths])

    def take_photons(self, paths, uids=()) -> int:
        """Add photon streams from the workspace; remember the dataset each came from."""
        before = len(self.model.files)
        self.add_files(paths)
        for path, uid in zip(paths, uids):
            if uid:
                self.model.sources[str(path)] = str(uid)
        return len(self.model.files) - before

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

    #: Per action: the dialog's title and file filters. Only outputs: the input comes from the
    #: workspace (a setup is loaded from a workspace ``setup`` row, not a dialog).
    DIALOGS = {
        "save_setup": ("Save detector setup", [("JSON", ["*.json"])]),
    }

    def browse(self, action="save_setup"):
        """Open the save dialog for *action*."""
        from emtk.dialog_window import DialogWindow
        from emtk.file_dialog import FileDialog

        title, filters = self.DIALOGS[action]
        self.dialog_action = action
        self.dialog = FileDialog(title, mode="save", filename="detectors.json", filters=filters)
        self._dialog_window = DialogWindow(title, size=(640.0, 460.0), key="burst-background-file")
        self._dialog_window.show()

    def _snapshot(self):
        snapshot = copy.copy(self.model)
        snapshot.files = list(self.model.files)
        detectors = copy.deepcopy(self.model._channels())
        snapshot.channels_provider = lambda: detectors
        from chisurf.core.setup_channel_definition import ChannelDefinition

        snapshot._input_settings = copy.deepcopy(self.channel_definition.model.get_settings())
        reading = ChannelDefinition(snapshot._input_settings)
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
            "_interphoton_settings",
            "_result_settings",
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

        if im.button(tr("Channel definition")):
            callback = getattr(self, "on_show_channels", None)
            if callable(callback):
                callback()
        im.set_item_tooltip(
            tr(
                "Open the complete detector setup, timing, calibration, PIE, TAC and optical editor."
            )
        )
        if remember is not None:
            remember("bg_channels")

    def draw_input(self, remember=None, track=None):
        """The generated Input section (the workspace's photon streams) and Clear files."""
        from emtk import im
        from emtk.view_form import draw_form

        if track is not None:
            self.input.workspace_input_on_used = track
        self.input_form.rects.clear()
        draw_form(self.input_spec, self.input, self.input_form)
        if remember is not None:
            for name, rect in self.input_form.rects.items():
                remember(name, tuple(rect))
        if im.button(tr("Clear files")):
            self.clear()
        im.set_item_tooltip(tr("Remove loaded files and analysis results."))

    def draw_inputs(self, remember=None, track=None):
        """File inputs, the channel editor button, Stop and the status; *remember* records rects for the guide."""
        from emtk import im

        im.text(tr("Measurements & detectors"))
        im.begin_disabled(self.running)
        self.draw_input(remember, track)
        for path in list(self.model.files):
            im.text_wrapped(str(path))
            if im.button(f"Remove##{path}"):
                self.remove_file(path)
            im.set_item_tooltip(f"Remove {Path(path).name} from the analysis.")
        self._show_channels_button(remember)
        im.end_disabled()
        if im.button(tr("Stop computation"), role="danger"):
            self.stop()
        im.set_item_tooltip(tr("Cancel at the next file boundary and retain the previous results."))
        if self.status:
            im.text_wrapped(self.status)
        im.separator()

    def draw_dialogs(self, frame):
        """The save dialog in a sized window over *frame*, and the channel editor's dialogs."""
        if self.dialog is not None:
            pressed = self._dialog_window.begin(frame)
            result = self.dialog.draw()
            self._dialog_window.end()
            if result:
                try:
                    self.save_setup(result[0])
                except Exception as exc:
                    self.status = f"Error: {exc}"
                self.dialog = None
            elif result is False or pressed == "close":
                self.dialog = None
        self.channel_definition.draw_dialogs(frame)

    def close(self):
        self.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.channel_definition.close()
