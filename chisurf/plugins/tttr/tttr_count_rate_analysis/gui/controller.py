"""Native count-rate controller with snapshot jobs and canonical detector setups."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from emtk import im
from emtk.file_dialog import FileDialog

from chisurf.core.data_io.detector_setups import setup_lut_open_kwargs
from chisurf.core.fio.staging import TTTR_EXTENSIONS, open_tttr
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.plugins.tttr.tttr_splitter.gui.jobs import BackgroundJob

from .app import CountRateApp, setup_to_channels
from .view_model import CountRateViewModel


class CountRateController:
    def __init__(self, reader=None, setups=None):
        self._model = CountRateViewModel()
        self.reader = reader
        self._setups = deepcopy(setups or {})
        self.setups_ready = setups is not None
        self.selected_setup = next(iter(self._setups), "")
        self.setups_path = ""
        initial = deepcopy(self._setups.get(self.selected_setup, {}))
        if self.selected_setup:
            initial["setup_name"] = self.selected_setup
        self.channel_editor = ChannelDefinitionWidget(
            settings=initial, on_changed=self.on_definition_changed
        )
        self.channel_editor.model.setups = deepcopy(self._setups)
        self._model.channels_provider = self.channels
        self.job = BackgroundJob()
        self.dialog = None
        self.dialog_callback = None
        self.dataset_picker = DatasetPicker(on_paths=self.add_paths)
        self.setup_editor = None
        self.message = ""
        self.progress = (0, 0)
        self.app = _StandaloneApp(
            self,
            on_calculate=self.calculate,
            on_save=self.save_dialog,
            on_add_files=self.add_files_dialog,
            on_clear=self.clear,
        )

    def available_setups(self):
        return self._setups

    def on_definition_changed(self, settings):
        self.selected_setup = str(
            settings.get("setup_name") or self.selected_setup or "Custom setup"
        )
        self._setups[self.selected_setup] = deepcopy(settings)
        self.setups_ready = True

    def channels(self):
        return setup_to_channels(self.channel_editor.model.get_settings())

    def adopt_editor_definition(self, setup, name=""):
        from chisurf.core.setup_channel_definition import ChannelDefinition

        self.channel_editor.model = ChannelDefinition(
            {**deepcopy(setup), "setup_name": name}, file_path=self.setups_path or None
        )
        self.channel_editor.model.on_changed = self.on_definition_changed
        self.channel_editor.model.setups = deepcopy(self._setups)
        self.channel_editor.setup_name = name
        self.channel_editor.detector_names = {}
        self.channel_editor.window_names = {}
        self.channel_editor.optical = None

    def refresh_setups(self):
        if self.job.running:
            return

        def work():
            from chisurf.core.setup_channel_definition import ChannelDefinition

            store = ChannelDefinition(file_path=self.setups_path or None)
            store.refresh_setups()
            return store.setups

        def publish(setups):
            self._setups = setups
            self.setups_ready = True
            if self.selected_setup not in setups:
                self.selected_setup = next(iter(setups), "")
            self.channel_editor.model.setups = deepcopy(setups)
            self.channel_editor.model.file_path = self.setups_path or None
            if self.selected_setup:
                self.channel_editor.select_setup(self.selected_setup)
            self.message = f"Loaded {len(setups)} detector setups."

        self.job.start(work, publish, lambda exc: setattr(self, "message", str(exc)))

    def browse_setups(self):
        self.choose(
            "Detector setup library", self.load_setups_file, filters="Setup library (*.json)"
        )

    def load_setups_file(self, paths):
        self.setups_path = str(paths[0])
        self.refresh_setups()

    def edit_setup(self):
        setup = self._setups.get(
            self.selected_setup,
            {
                "detectors": {"green": {"chs": [0], "micro_time_ranges": [[0, 4095]]}},
                "windows": {"all": None},
            },
        )
        self.setup_editor = json.dumps(setup, indent=2)

    def apply_setup(self):
        try:
            setup = json.loads(self.setup_editor)
            if not setup_to_channels(setup):
                raise ValueError("Define at least one detector channel.")
            name = self.selected_setup or "Custom setup"
            self._setups[name] = setup
            self.selected_setup = name
            self.adopt_editor_definition(setup, name)
            self.setup_editor = None
        except Exception as exc:
            self.message = str(exc)

    def add_paths(self, paths):
        if self.job.running:
            return
        expanded = []
        extensions = tuple(ext.lower() for ext in TTTR_EXTENSIONS)
        for path in paths:
            p = Path(path)
            candidates = sorted(p.rglob("*")) if p.is_dir() else [p]
            expanded.extend(
                str(candidate.resolve())
                for candidate in candidates
                if candidate.is_file() and candidate.suffix.lower() in extensions
            )
        if not expanded:
            self.message = "Choose supported TTTR or PTO photon files."
        self._model.add_files(expanded)

    def choose(
        self,
        title,
        callback,
        mode="open",
        multiple=False,
        filters="TTTR (*.pto *.ptu *.ht3 *.ht2 *.spc *.phu *.tttr);;All files (*)",
    ):
        if self.job.running:
            return
        self.dialog = FileDialog(title, mode=mode, multiselect=multiple, filters=filters)
        self.dialog_callback = callback

    def add_files_dialog(self):
        self.choose("Add TTTR files", self.add_paths, multiple=True)

    def add_folder_dialog(self):
        self.choose("Add TTTR folder", self.add_paths, mode="folder")

    def add_database(self):
        self.dataset_picker.open()

    def calculate(self):
        if self.channel_editor._future is not None:
            self.message = "Wait for the detector calibration read to finish."
            return False
        if self.job.running:
            return False
        model = CountRateViewModel()
        model.files = list(self._model.files)
        channels = deepcopy(self.channels())
        model.channels_provider = lambda: channels
        setup = deepcopy(self.channel_editor.model.get_settings())
        reading = setup_lut_open_kwargs(setup)
        timing = setup.get("tttr_reading") or {}
        if timing.get("override_timing") and float(timing.get("macro_time_resolution", 0) or 0) > 0:
            model.macro_resolution_override = float(timing["macro_time_resolution"]) * 1e-9
        routine = (setup.get("tttr_reading") or {}).get("file_type")
        routine = None if routine in (None, "", "auto", "Auto") else routine
        model.loader = self.reader or (
            lambda path: open_tttr(
                path, routine=routine, cancel_cb=self.job.cancelled.is_set, **reading
            )
        )
        if model.can_compute():
            self.message = (
                "Select or edit a detector setup first."
                if model.files and not channels
                else model.can_compute()
            )
            return False

        def progress(index, count):
            self.progress = (index, count)

        def publish(result):
            self._model = result
            self._model.channels_provider = self.channels
            self.message = f"Analyzed {len(result.files)} files."

        def work():
            model.compute(cancel_cb=self.job.cancelled.is_set, progress_cb=progress)
            return model

        self.message = "Calculating…"
        return self.job.start(work, publish, lambda exc: setattr(self, "message", str(exc)))

    def clear(self):
        self.job.stop()
        self._model.clear()
        self.progress = (0, 0)

    def save_dialog(self):
        if self._model.can_save():
            self.message = self._model.can_save()
            return
        self.choose(
            "Save count-rate table",
            lambda paths: self.save(paths[0]),
            mode="save",
            filters="Table (*.txt *.tsv)",
        )

    def save(self, path):
        if self.job.running:
            return False
        model = CountRateViewModel()
        for name in ("files", "_per_file", "_per_file_photons", "_meas_times", "_channel_order"):
            setattr(model, name, deepcopy(getattr(self._model, name)))
        return self.job.start(
            lambda: model.save_table(str(path)),
            lambda _: setattr(self, "message", f"Saved {path}"),
            lambda exc: setattr(self, "message", str(exc)),
        )

    def export_settings(self):
        fields = {
            "detectors",
            "windows",
            "tttr_reading",
            "channel_luts",
            "channel_shifts",
            "apply_lut",
        }
        setup = self.channel_editor.model.get_settings()
        return {
            "files": list(self._model.files),
            "selected_setup": self.selected_setup,
            "setups_path": str(self.channel_editor.model.file_path or self.setups_path or ""),
            "setup_definition": {
                key: deepcopy(value) for key, value in setup.items() if key in fields
            },
        }

    def restore_settings(self, state):
        setup = state.get("setup_definition") or {}
        name = str(state.get("selected_setup") or "Custom setup")
        self.restore_state(
            {
                "files": state.get("files", []),
                "selected_setup": name,
                "setups_path": state.get("setups_path", ""),
                "setups": {name: setup} if setup else {},
            }
        )
        self.setups_ready = bool(setup)

    def export_state(self):
        return {
            "files": list(self._model.files),
            "setups": deepcopy(self._setups),
            "selected_setup": self.selected_setup,
            "setups_path": self.setups_path,
            "per_file": deepcopy(self._model._per_file),
            "per_file_photons": deepcopy(self._model._per_file_photons),
            "measurement_times": dict(self._model._meas_times),
            "channel_order": list(self._model._channel_order),
        }

    def restore_state(self, state):
        self.job.stop()
        self._model.clear()
        self._model.files = list(state.get("files", []))
        self._setups = deepcopy(state.get("setups", {}))
        self.selected_setup = str(state.get("selected_setup", ""))
        self.setups_path = str(state.get("setups_path", ""))
        self._model._per_file = deepcopy(state.get("per_file", {}))
        self._model._per_file_photons = deepcopy(state.get("per_file_photons", {}))
        self._model._meas_times = dict(state.get("measurement_times", {}))
        self._model._channel_order = list(state.get("channel_order", []))
        self.adopt_editor_definition(self._setups.get(self.selected_setup, {}), self.selected_setup)


class _StandaloneApp(CountRateApp):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.continuous = True

    def _render(self):
        self.tool.job.poll()
        self.tool.channel_editor.poll()
        super()._render()
        frame = (0.0, 0.0, *im.get_main_viewport().size)
        self.tool.dataset_picker.render(frame)
        self.tool.channel_editor.draw_dialogs(frame)
        if self.tool.dialog:
            if im.begin("Choose analysis path"):
                result = self.tool.dialog.draw()
                if result:
                    callback = self.tool.dialog_callback
                    self.tool.dialog = None
                    callback(result)
                elif result is False:
                    self.tool.dialog = None
            im.end()
        if self.tool.setup_editor is not None:
            if im.begin("Detector channel setup"):
                _, self.tool.setup_editor = im.input_text_multiline(
                    "Definition", self.tool.setup_editor, (-1, 300)
                )
                im.set_item_tooltip(
                    "Define detector routing channels, inclusive micro-time gates and excitation-window ranges."
                )
                if im.button("Apply setup"):
                    self.tool.apply_setup()
                im.set_item_tooltip("Validate and adopt this detector/window definition.")
                if im.button("Cancel setup"):
                    self.tool.setup_editor = None
                im.set_item_tooltip("Discard the current channel-definition edit.")
            im.end()

    def on_paths_dropped(self, paths):
        self.tool.add_paths(paths)

    def export_settings(self):
        return self.tool.export_settings()

    def restore_settings(self, state):
        self.tool.restore_settings(state)

    def export_state(self):
        return self.tool.export_state()

    def restore_state(self, state):
        self.tool.restore_state(state)

    def close(self):
        self.tool.job.close()
        self.tool.dataset_picker.close()
        self.tool.channel_editor.close()


def create_app(reader=None, setups=None):
    return CountRateController(reader=reader, setups=setups).app
