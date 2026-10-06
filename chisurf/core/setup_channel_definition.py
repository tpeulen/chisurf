"""Complete toolkit-free detector setup state and persistence."""

import copy
import json
from pathlib import Path

import numpy as np

from chisurf.core.data_io.detector_setups import DETECTOR_SETUPS_FILE, setup_lut_open_kwargs
from chisurf.core.fio import setup_store as store

CONFIG = store.SetupTypeConfig(
    "tttr_detector_setup",
    "tttr_detector_setup",
    "tttr_detector_setup_preferences",
    DETECTOR_SETUPS_FILE,
    "TTTR detector and PIE-window setup",
)


def _save_row(db, name, data, user_id=None, is_public=None):
    store.save_setup_row(
        db,
        CONFIG,
        name,
        data,
        user_id=user_id,
        is_public=is_public,
        detectors=data.get("detectors") or {},
        windows=data.get("windows") or {},
        timing_resolution=data.get("tttr_reading") or {},
        burst_defaults=data.get("burst_selection") or {},
    )


def _row_data(row, db):
    configuration = store.json_loads(row.get("configuration_json"))
    data = copy.deepcopy(configuration.get("setup_data") or configuration)
    if row.get("is_public") is not None:
        data["_is_public"] = bool(row["is_public"])
    if row.get("created_by_user_id") is not None:
        data["_owner"] = row["created_by_user_id"]
    return data


class ChannelDefinition:
    def __init__(self, settings=None, file_path=None, db=None):
        self.data = copy.deepcopy(settings or {})
        self.data.setdefault("detectors", {})
        self.data.setdefault("windows", {})
        self.data.setdefault(
            "tttr_reading",
            {
                "file_type": "auto",
                "macro_time_resolution": 0.0,
                "micro_time_resolution": 0.0,
                "micro_time_binning": 1,
            },
        )
        self.data.setdefault("channel_luts", {})
        self.data.setdefault("channel_shifts", {})
        self.data.setdefault("apply_lut", False)
        self.data.setdefault("polarization_resolved", True)
        self.file_path, self.db = file_path, db
        self.setups = {}
        #: The setup the store says was used last (read by :meth:`refresh_setups`, written by :meth:`remember_last_used`).
        self.last_used = ""
        self.current_name = self.data.get("setup_name", "")
        self.preview = {
            int(ch): np.asarray(counts, dtype=float)
            for ch, counts in (self.data.get("_microtime_per_channel_decay") or {})
            .get("channels", {})
            .items()
        }
        self.preview_path = (self.data.get("_microtime_per_channel_decay") or {}).get(
            "file_path", ""
        )
        self.raw_preview = {
            int(ch): np.asarray(counts, dtype=float)
            for ch, counts in (self.data.get("_raw_microtime_per_channel_decay") or {})
            .get("channels", {})
            .items()
        }
        self.on_changed = None
        self._last_g = {}

    def changed(self):
        self.publish_lut()
        if callable(self.on_changed):
            self.on_changed(self.get_settings())

    def get_settings(self):
        result = copy.deepcopy(self.data)
        reading = result["tttr_reading"]
        reading["effective_micro_time_resolution"] = float(
            reading.get("micro_time_resolution", 0)
        ) * max(1, int(reading.get("micro_time_binning", 1)))
        reading["excitation_period"] = float(reading.get("macro_time_resolution", 0))
        result["setup_name"] = self.current_name
        result["channels"] = {
            f"{window}_{detector}": [
                {
                    "window_range": window_range,
                    "detector_chs": info.get("chs", []),
                    "micro_time_range": gate,
                }
                for gate in info.get("micro_time_ranges", [])
            ]
            for window, window_range in result["windows"].items()
            for detector, info in result["detectors"].items()
        }
        return result

    def rename_detector(self, old, new):
        new = str(new).strip()
        if not new or new in self.data["detectors"]:
            raise ValueError("Choose an unused detector name.")
        # the renamed detector keeps its place (the tables list detectors in that order)
        self.data["detectors"] = {
            (new if name == old else name): info for name, info in self.data["detectors"].items()
        }
        if old in self._last_g:
            self._last_g[new] = self._last_g.pop(old)
        for detector in (self.data.get("optical_config") or {}).get("detectors", []):
            if detector.get("name") == old:
                detector["name"] = new
        self.changed()

    def rename_window(self, old, new):
        new = str(new).strip()
        if not new or new in self.data["windows"]:
            raise ValueError("Choose an unused PIE window name.")
        self.data["windows"] = {
            (new if name == old else name): bounds for name, bounds in self.data["windows"].items()
        }
        self.changed()

    def export_lut(self, channel, path):
        from chisurf.plugins.tttr.tttr_lut_tools.api.io import save_lut

        values = self.data["channel_luts"].get(str(int(channel)))
        if values is None:
            raise ValueError("Assign or compute a LUT for this channel first.")
        return save_lut(str(path), {"NTAC_fract": np.asarray(values)})

    def publish_lut(self):
        from chisurf.core.fio.lut_context import set_active_setup_lut

        kwargs = setup_lut_open_kwargs(self.data)
        set_active_setup_lut(**kwargs)

    def refresh_setups(self):
        if self.db is not None:
            payload = store.load_mmfdb_setups(self.db, CONFIG, row_to_data=_row_data)
        else:
            payload = store.load_setups(self.file_path, CONFIG, row_to_data=_row_data)
        self.setups = payload.get("setups") or {}
        self.last_used = str(payload.get("last_used") or "")
        return sorted(self.setups)

    def remember_last_used(self, name):
        """Store *name* as the last used setup, so the next start opens it (the Qt page does this on every choice)."""
        name = str(name or "")
        if not store.save_setups(
            {"last_used": name},
            CONFIG,
            self.file_path,
            get_db_fn=(lambda: self.db) if self.db is not None else None,
        ):
            raise OSError("The last used setup could not be stored.")
        self.last_used = name

    def open_last_used(self):
        """Select the last used setup if the store still has it; return its name, else ''."""
        if self.last_used and self.last_used in self.setups:
            self.select_setup(self.last_used)
            return self.last_used
        return ""

    def select_setup(self, name):
        if name not in self.setups:
            self.refresh_setups()
        if name not in self.setups:
            raise ValueError(f"Unknown setup: {name}")
        self.data = copy.deepcopy(self.setups[name])
        self.data.setdefault("tttr_reading", {})
        self.data.setdefault("channel_luts", {})
        self.data.setdefault("channel_shifts", {})
        self.data.setdefault("windows", {})
        self.data.setdefault("detectors", {})
        self.current_name = name
        self.preview = {
            int(ch): np.asarray(counts, dtype=float)
            for ch, counts in (self.data.get("_microtime_per_channel_decay") or {})
            .get("channels", {})
            .items()
        }
        self.preview_path = (self.data.get("_microtime_per_channel_decay") or {}).get(
            "file_path", ""
        )
        self.raw_preview = {
            int(ch): np.asarray(counts, dtype=float)
            for ch, counts in (self.data.get("_raw_microtime_per_channel_decay") or {})
            .get("channels", {})
            .items()
        }
        self.changed()

    def _persist(self, replace=False):
        payload = {"setups": self.setups, "last_used": self.current_name}
        if not store.save_setups(
            payload,
            CONFIG,
            self.file_path,
            replace=replace,
            save_row_fn=_save_row,
            get_db_fn=(lambda: self.db) if self.db is not None else None,
        ):
            raise OSError("Detector setups could not be saved.")

    def save_setup(self, name, public=False):
        name = str(name).strip()
        if not name:
            raise ValueError("Provide a setup name.")
        previous, previous_name = copy.deepcopy(self.setups), self.current_name
        current = copy.deepcopy(self.setups.get(name, {}) or {})
        current.update(self.get_settings())
        current["_is_public"] = bool(public)
        current["setup_name"] = name
        self.setups[name] = current
        self.current_name = name
        try:
            self._persist()
        except Exception:
            self.setups, self.current_name = previous, previous_name
            raise
        self.changed()

    def rename_setup(self, name):
        name = str(name).strip()
        if not self.current_name or self.current_name not in self.setups:
            raise ValueError("Select a saved setup first.")
        if not name or name in self.setups:
            raise ValueError("Choose an unused setup name.")
        previous, previous_name = copy.deepcopy(self.setups), self.current_name
        self.setups[name] = self.setups.pop(self.current_name)
        self.setups[name]["setup_name"] = name
        self.current_name = name
        try:
            self._persist(replace=True)
        except Exception:
            self.setups, self.current_name = previous, previous_name
            raise
        self.changed()

    def delete_setup(self):
        if not self.current_name or self.current_name not in self.setups:
            raise ValueError("Select a saved setup first.")
        previous, previous_name = copy.deepcopy(self.setups), self.current_name
        self.setups.pop(self.current_name)
        self.current_name = ""
        try:
            self._persist(replace=True)
        except Exception:
            self.setups, self.current_name = previous, previous_name
            raise

    def _database(self):
        return self.db or store.get_db()

    def calibration_dates(self):
        if not self.current_name:
            return []
        db = self._database()
        if db is None:
            return []
        try:
            key = store.setup_id_for_name(
                self.current_name, store.resolve_active_user_id(), CONFIG.id_prefix
            )
            return list(db.list_setup_calibration_dates(key))
        finally:
            if db is not self.db:
                store.close_owned_db(db)

    def apply_calibration(self, date=None):
        if not self.current_name:
            raise ValueError("Select a saved setup first.")
        db = self._database()
        if db is None:
            raise OSError("Calibration database unavailable.")
        try:
            key = store.setup_id_for_name(
                self.current_name, store.resolve_active_user_id(), CONFIG.id_prefix
            )
            rows = db.get_setup_calibration(key, calibrated_at=date)
            for row in rows:
                detector = self.data["detectors"].get(row.get("channel_name"))
                if detector is not None:
                    for key in ("g_factor", "l1", "l2"):
                        if row.get(key) is not None:
                            detector[key] = row[key]
            self.changed()
            return len(rows)
        finally:
            if db is not self.db:
                store.close_owned_db(db)

    def open_tttr(self, path, raw=False, cancel_cb=None, header_timing=False, auto=False):
        from chisurf.core.fio.staging import open_tttr

        reading = self.data["tttr_reading"]
        routine = reading.get("file_type")
        routine = None if auto or not routine or routine.lower() == "auto" else routine
        kwargs = setup_lut_open_kwargs(self.data)
        if raw:
            kwargs["apply_lut"] = False
        tttr = open_tttr(path, routine, cache=False, cancel_cb=cancel_cb, **kwargs)
        if reading.get("override_timing") and not header_timing:
            header = tttr.get_header()
            if float(reading.get("macro_time_resolution", 0)) > 0:
                header.set_macro_time_resolution(float(reading["macro_time_resolution"]) * 1e-9)
            if float(reading.get("micro_time_resolution", 0)) > 0:
                header.set_micro_time_resolution(float(reading["micro_time_resolution"]) * 1e-12)
        return tttr

    def read_tttr(self, path, cancel_cb=None):
        if str(path).lower().endswith(".set"):
            from chisurf.core.fio.fluorescence.bhfiles import BeckerHicklSetReader

            resolution = BeckerHicklSetReader(str(path)).micro_time_resolution
            if resolution is None:
                raise ValueError("SET file has no microtime calibration.")
            self.data["tttr_reading"]["micro_time_resolution"] = float(resolution) * 1000
            return
        tttr = self.open_tttr(path, raw=True, cancel_cb=cancel_cb, header_timing=True, auto=True)
        if len(tttr) == 0:
            # The Qt page detects the container from the file whatever File Type is chosen, and refuses an empty one.
            raise ValueError("File is not a supported TTTR file format or contains no events.")
        header = tttr.get_header()
        self.data["tttr_reading"].update(
            macro_time_resolution=float(header.macro_time_resolution) * 1e9,
            micro_time_resolution=float(header.micro_time_resolution) * 1e12,
            override_timing=False,
        )
        self.raw_preview = {
            int(ch): np.asarray(tttr.get_microtime_histogram(1, [int(ch)])[0], dtype=float)
            for ch in tttr.get_used_routing_channels()
        }
        from chisurf.core.fio.staging import apply_setup_lut

        apply_setup_lut(tttr, **setup_lut_open_kwargs(self.data))
        self.preview = {
            int(ch): np.asarray(tttr.get_microtime_histogram(1, [int(ch)])[0], dtype=float)
            for ch in tttr.get_used_routing_channels()
        }
        self.preview_path = str(path)
        self.data["_raw_microtime_per_channel_decay"] = {
            "file_path": str(path),
            "channels": {str(ch): counts.tolist() for ch, counts in self.raw_preview.items()},
        }
        self.data["_microtime_per_channel_decay"] = {
            "file_path": str(path),
            "channels": {str(ch): counts.tolist() for ch, counts in self.preview.items()},
        }
        self.changed()

    def assign_lut(self, channel, path):
        from chisurf.plugins.tttr.tttr_lut_tools.api.io import load_lut_file

        values = load_lut_file(str(path))
        self.data.setdefault("channel_luts", {})[str(int(channel))] = values.tolist()
        self.data.setdefault("channel_lut_sources", {})[str(int(channel))] = str(path)
        self.data["apply_lut"] = (
            True  # a LUT that is stored but never applied would be silently useless (the Qt page's rule)
        )
        self.changed()

    def compute_lut(self, channel, linear_start=None, linear_stop=None):
        from chisurf.plugins.tttr.tttr_lut_tools.api.compute import compute_lut_from_counts

        counts = self.raw_preview.get(int(channel), self.preview.get(int(channel)))
        if counts is None:
            raise ValueError("Read a uniform-illumination calibration measurement first.")
        table = compute_lut_from_counts(counts, linear_start, linear_stop)
        self.data["channel_luts"][str(int(channel))] = table["NTAC_fract"].tolist()
        self.data["apply_lut"] = True
        self.changed()
        return table

    def calculate_g(self, name, path=None, bounds=None):
        from chisurf.plugins.vv_vh_g_factor.core.calculations import calculate_g_factor_core

        detector = self.data["detectors"][name]
        channels = detector["chs"]
        if len(channels) < 2:
            raise ValueError("G-factor calculation needs parallel and perpendicular channels.")
        if path is not None:
            self.read_tttr(path)
        if not self.preview:
            raise ValueError("Read a calibration measurement first.")
        parallel = sum(
            (self.preview[ch] for ch in channels[::2] if ch in self.preview),
            start=np.zeros_like(next(iter(self.preview.values()))),
        )
        perpendicular = sum(
            (self.preview[ch] for ch in channels[1::2] if ch in self.preview),
            start=np.zeros_like(parallel),
        )
        region = bounds or detector.get("g_factor_channels") or [0, len(parallel) - 1]
        binning = max(1, int(self.data["tttr_reading"].get("micro_time_binning", 1)))
        if binning > 1:
            indices = np.arange(0, len(parallel), binning)
            parallel = np.add.reduceat(parallel, indices)
            perpendicular = np.add.reduceat(perpendicular, indices)
            region = [float(value) / binning for value in region]
        result = calculate_g_factor_core(parallel, perpendicular, region)
        value = result.get("g_factor")
        if value is None or not np.isfinite(value) or value <= 0:
            raise ValueError("No positive finite G factor could be estimated in this range.")
        detector["g_factor"] = float(value)
        detector.pop("g_factor_decay_uuid", None)
        detector.pop("g_factor_calibration_id", None)
        self._last_g[name] = {
            "parallel": parallel,
            "perpendicular": perpendicular,
            "bounds": region,
            "result": result,
            "source": self.preview_path,
        }
        self.changed()
        return result

    def archive_g(self, name):
        import tempfile

        from chisurf.plugins.vv_vh_g_factor.backend.services import archive_g_factor_handler

        calculation = self._last_g.get(name)
        if calculation is None:
            raise ValueError("Calculate the G factor from a reference decay first.")
        detector = self.data["detectors"][name]
        parameters = dict(calculation["result"])
        parameters.update(
            region_min=calculation["bounds"][0],
            region_max=calculation["bounds"][1],
            decay_shift=0.0,
            flip=False,
            use_bg=False,
            l1=detector.get("l1", 0.0),
            l2=detector.get("l2", 0.0),
            micro_time_resolution=self.get_settings()["tttr_reading"][
                "effective_micro_time_resolution"
            ],
            source_measurement=calculation["source"],
        )
        with tempfile.TemporaryDirectory(prefix="chisurf-g-calibration-") as directory:
            path = Path(directory) / "reference_vv_vh.txt"
            np.savetxt(
                path, np.concatenate([calculation["parallel"], calculation["perpendicular"]])
            )
            result = archive_g_factor_handler(
                str(path), parameters, active_user=store.resolve_active_user_id()
            )
        if not result.get("ok"):
            raise OSError(result.get("error") or "G-factor calibration could not be archived.")
        detector["g_factor_decay_uuid"] = result.get("reference_decay_id")
        detector["g_factor_calibration_id"] = result.get("calibration_id")
        self.changed()
        return result
