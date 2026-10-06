"""Native accurate-FRET workflow, safe calibration snapshots and handoffs."""

import copy
import sys
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from threading import Event

import numpy as np

from chisurf.core.fluorescence.fret.calibration import SETUP_CALIBRATION_FIELD, calibration_to_setup
from chisurf.emtk.channel_definition import ChannelDefinitionWidget
from chisurf.emtk.dataset_picker import DatasetPicker
from chisurf.emtk.session_sources import sources


def _is_container_run(path) -> bool:
    """Whether *path* names a burst run inside a ``.pto`` container (``m000.pto/sliding_window_All 0.1500#60``).

    A burst search over a container keeps its bursts there and writes no ``.bur``; such a run is not a file on disk
    but every burst reader opens it.
    """
    from chisurf.core.fio.fluorescence import burst_tree

    path = Path(path)
    return path.suffix.lower() != burst_tree.SUFFIX and burst_tree.is_container_path(path)


class AccurateFretController:
    def __init__(self, model, ndx_source=None, setup_model=None, db_path=None):
        self.model = model
        self.ndx_source = ndx_source
        self.model.database_path = str(db_path) if db_path is not None else self.model.database_path
        self.status = ""
        self.running = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="accurate-fret")
        self._future = None
        self._cancel = Event()
        self.dialog = None
        self.dialog_action = "load"
        self.channel_definition = ChannelDefinitionWidget(
            model=setup_model, on_changed=self.apply_setup
        )
        self.datasets = DatasetPicker(
            kinds=["burst_data", "analysis_result", "raw_data"], on_paths=self.on_paths_dropped
        )
        self.dyes_loaded = False
        self.lightpaths_loaded = False
        # Explicit refresh avoids a missing database being reopened every frame.
        model.dye_names = lambda: ["", *[dye.name for dye in model._dyes]]
        model.lightpath_names = lambda: [
            "",
            *[str(record.get("name") or record["operation_id"]) for record in model._lightpaths],
        ]

    def apply_setup(self, payload):
        self.model.apply_setup_settings(payload)
        calibration = (payload.get(SETUP_CALIBRATION_FIELD) or {}).get("values") or {}
        for key, field in [
            ("r0", "forster_radius"),
            ("bg_dd", "background_dd"),
            ("bg_da", "background_da"),
            ("bg_aa", "background_aa"),
            ("phi_d", "quantum_yield_donor"),
            ("phi_a", "quantum_yield_acceptor"),
        ]:
            if key in calibration and np.isfinite(float(calibration[key])):
                setattr(self.model, field, float(calibration[key]))

    def _snapshot(self):
        snapshot = copy.copy(self.model)
        snapshot._columns = {
            key: np.asarray(value).copy() for key, value in self.model._columns.items()
        }
        snapshot._lightpaths = copy.deepcopy(self.model._lightpaths)
        snapshot.detectors = copy.deepcopy(self.model.detectors)
        snapshot._observers = []
        snapshot._write_container = lambda: None
        snapshot._publish_parameters = lambda: None
        return snapshot

    def progress(self, fraction, message):
        if self._cancel.is_set():
            raise CancelledError()
        self.status = message

    def run(self):
        if self.running:
            return
        reason = self.model.can_run()
        if reason:
            self.status = reason
            return
        self._start("calibrate", self._snapshot())

    def load(self, path):
        if self.running:
            return
        if not Path(path).is_file() and not _is_container_run(path):
            self.status = f"Burst table does not exist: {path}"
            return
        self._start("load", self._snapshot(), str(path))

    def _start(self, action, snapshot=None, path=None):
        if self.running:
            return
        self.running = True
        self._action = action
        self._cancel.clear()
        self.status = {
            "load": "Reading burst columns …",
            "calibrate": "Calibrating accurate FRET …",
            "dyes": "Loading dye catalogue …",
            "lightpaths": "Loading saved optical priors …",
        }[action]
        self._future = self._executor.submit(self._execute, action, snapshot, path)

    def _execute(self, action, snapshot, path):
        self.progress(0.0, self.status)
        if action == "load":
            snapshot.set_filename(path)
            if not snapshot._columns:
                raise ValueError(snapshot.results_text)
            self.progress(1.0, snapshot.results_text)
            return snapshot
        if action == "calibrate":
            ok = snapshot.compute(progress=self.progress)
            if not ok:
                raise ValueError(snapshot.results_text)
            self.progress(1.0, "Calibration complete")
            return snapshot
        if action == "dyes":
            from chisurf.core.fluorescence.fret.dyes import list_dyes

            return list_dyes(db_path=self.model.database_path)
        if action == "lightpaths":
            from ..core import list_lightpaths

            return list_lightpaths(db_path=self.model.database_path)
        raise ValueError(action)

    def poll(self):
        if self._future is None or not self._future.done():
            return
        future, self._future = self._future, None
        try:
            value = future.result()
            self.progress(1.0, self.status)
            if self._action in ("load", "calibrate"):
                if self._action == "load":
                    self.model.filename, self.model._columns = value.filename, value._columns
                    for field in ("column_i_dd", "column_i_da", "column_i_aa", "column_tau_f"):
                        setattr(self.model, field, getattr(value, field))
                    self.model._result = None
                else:
                    self.model._result = value._result
                    self.model._write_container()
                    self.model._publish_parameters()
                self.model.results_text = value.results_text
                self.model.notify("file" if self._action == "load" else "result")
                self.status = (
                    "Burst table loaded." if self._action == "load" else "Accurate FRET calibrated."
                )
            elif self._action == "dyes":
                self.model._dyes = value
                self.dyes_loaded = True
                self.status = f"{len(value)} dyes available."
            else:
                self.model._lightpaths = value
                self.lightpaths_loaded = True
                self.status = f"{len(value)} saved optical priors available."
        except CancelledError:
            self.status = "Calibration/read cancelled; previous result retained."
        except Exception as exc:
            self.status = f"Error: {exc}"
        finally:
            self.running = False

    def stop(self):
        if self.running:
            self._cancel.set()
            self.status = "Stopping after the current numerical operation …"

    def _ndx_sources(self):
        selected = self.ndx_source() if callable(self.ndx_source) else self.ndx_source
        if selected is not None:
            return list(selected) if isinstance(selected, (list, tuple)) else [selected]
        return sources("ndx")

    def from_ndx(self):
        windows = self._ndx_sources()
        if not windows:
            if any(
                name in sys.modules
                for name in ("qtpy.QtWidgets", "PyQt5.QtWidgets", "PySide6.QtWidgets")
            ):
                self.status = self.model.load_from_ndxplorer()
            else:
                self.status = "No native ndX source registered; open ndX or load a burst table."
            return
        source = windows[-1]
        getter = getattr(source, "get_burst_columns", None)
        if callable(getter):
            columns = getter()
        else:
            from chisurf.plugins.ndxplorer.calibration_bridge import ndx_columns

            columns = ndx_columns(getattr(source, "data_source", None))
        if not columns:
            self.status = "The ndX source has no numeric burst columns."
            return
        self.model._columns = {
            str(key): np.asarray(value, dtype=float) for key, value in columns.items()
        }
        self.model.filename = "<ndX>"
        self.model._map_columns()
        self.model._result = None
        self.model.notify("file")
        self.status = f"Loaded {len(next(iter(columns.values())))} bursts from native ndX."

    def to_ndx(self):
        if self.model.result is None:
            self.status = "Calibrate first."
            return
        windows = self._ndx_sources()
        if not windows:
            if any(
                name in sys.modules
                for name in ("qtpy.QtWidgets", "PyQt5.QtWidgets", "PySide6.QtWidgets")
            ):
                self.status = self.model.push_to_ndxplorer()
            else:
                self.status = "No native ndX source registered."
            return
        calibration = self.model.result.calibration.calibration
        for source in windows:
            apply = getattr(source, "apply_fret_calibration", None)
            if callable(apply):
                apply(calibration)
            else:
                from chisurf.plugins.ndxplorer.calibration_bridge import push_calibration_to_ndx

                push_calibration_to_ndx(source, calibration)
        self.status = f"Calibration applied to {len(windows)} native ndX source(s)."

    def register(self):
        self.status = self.model.register_in_session()

    def store_setup(self):
        if self.model.result is None:
            self.status = "Calibrate first."
            return
        setup = self.channel_definition.model
        if not setup.current_name:
            self.status = "Select or save a named detector setup first."
            return
        setup.data[SETUP_CALIBRATION_FIELD] = calibration_to_setup(
            self.model.result.calibration.calibration,
            uncertainties=self.model.result.calibration.uncertainties,
        )
        setup.save_setup(setup.current_name, public=self.channel_definition.public)
        self.status = f"Calibration stored on setup {setup.current_name!r}."

    def export(self, path):
        self.model.export_csv(str(path))
        self.status = f"Per-burst accurate values exported: {path}"

    def browse(self, action="load"):
        from emtk.file_dialog import FileDialog

        self.dialog_action = action
        self.dialog = FileDialog(
            "Accurate FRET burst table / export",
            mode="open" if action == "load" else "save",
            filters=[("Burst tables", ["*.csv", "*.tsv", "*.txt", "*.bur", "*.npz", "*.pto"])],
            filename="accurate_fret.csv" if action != "load" else None,
        )

    def on_paths_dropped(self, paths):
        if paths:
            self.load(paths[0])

    def draw_dialogs(self, frame):
        from emtk import im

        if self.dialog is not None:
            if im.begin("Accurate FRET file chooser"):
                result = self.dialog.draw()
                if result:
                    try:
                        if self.dialog_action == "load":
                            self.load(result[0])
                        else:
                            self.export(result[0])
                    except Exception as exc:
                        self.status = f"Error: {exc}"
                    self.dialog = None
                elif result is False:
                    self.dialog = None
            im.end()
        self.datasets.render(frame)
        self.channel_definition.draw_dialogs(frame)

    def close(self):
        self.stop()
        self.channel_definition.close()
        from ..parameters import unregister_calibration_parameters

        unregister_calibration_parameters()
        self._executor.shutdown(wait=False, cancel_futures=True)
