"""Native anisotropy state using pure readers and linked fitting models."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from chisurf.core.data import DataCurve
from chisurf.core.experiments.tcspc.reader import TCSPCReader

from ..core import spectra
from ..core.native_fits import create_linked_fits
from .view_model import AnisotropyViewModel


class NativeAnisotropyModel(AnisotropyViewModel):
    def __init__(self):
        super().__init__(persist=False)
        self.stacked_files = False
        self.bin_width = float(TCSPCReader().dt)
        self.rep_rate = float(TCSPCReader().rep_rate)
        self.skiprows = 0
        self.use_header = True
        self.first_column_is_time = False
        self.fit_groups = None
        self.loaded_signature = None
        self.status = "Select the polarization-resolved inputs."
        self.selected_lifetime_row = -1
        self.selected_rotation_row = -1
        self.new_lifetime_amplitude = 0.5
        self.new_lifetime_value = 1.0
        self.new_rotation_amplitude = 0.5
        self.new_rotation_value = 1.0

    def _pairs(self):
        return [
            ("irf_vv", "vv", self.irf_vv_path),
            ("irf_vh", "vh", self.irf_vv_path if self.stacked_files else self.irf_vh_path),
            ("data_vv", "vv", self.data_vv_path),
            ("data_vh", "vh", self.data_vv_path if self.stacked_files else self.data_vh_path),
        ]

    def load_data(self):
        if not self.files_ready():
            raise ValueError("Select every required file before loading.")
        loaded = {}
        for key, role, path in self._pairs():
            width = self.bin_width
            if self.stacked_files:
                from chisurf.core.fio.vv_vh import read_vv_vh

                _, metadata = read_vv_vh(path, split=True, return_metadata=True)
                width = float(metadata.get("dt", metadata.get("dt_ns", width)))
            elif self.first_column_is_time:
                width = 1.0
            reader = TCSPCReader(
                dt=width,
                rep_rate=self.rep_rate,
                polarization=role,
                is_vv_vh=self.stacked_files,
                use_header=self.use_header,
                skiprows=int(self.skiprows),
                g_factor=self.g_factor,
                l1=self.l1,
                l2=self.l2,
            )
            if self.stacked_files:
                channels, metadata = read_vv_vh(path, split=True, return_metadata=True)
                label = role.upper()
                if label not in channels:
                    raise ValueError(f"{label} channel is absent from {path}.")
                values = np.asarray(channels[label], dtype=float)
                curve = DataCurve(
                    x=np.arange(len(values)) * width,
                    y=values,
                    ey=np.sqrt(np.maximum(values, 1.0)),
                    name=Path(path).stem + "_" + role,
                    load_filename_on_init=False,
                )
                curve.meta_data.update(
                    {key: value for key, value in metadata.items() if key != "unique_identifier"}
                )
                curve.data_reader = reader
            else:
                dataset = reader.get_data(filename=path, name=Path(path).stem + "_" + role)
                if not len(dataset):
                    raise ValueError(f"No curve read from {path}.")
                curve = dataset[0]
            if not len(curve.y) or not np.isfinite(curve.y).all():
                raise ValueError(f"Invalid decay samples in {path}.")
            if len(curve.x) > 1:
                reader.dt = float(np.mean(np.diff(curve.x)))
            loaded[key] = curve
        self.data.update(loaded)
        self.loaded_signature = self.input_signature()
        from ..core.irf import initial_region

        self.region_lb, self.region_ub = initial_region(len(self.data["irf_vv"].y))
        self.apply_region(self.region_lb, self.region_ub)
        self.status = "Loaded VV/VH IRFs and decays; select a dark IRF background region."
        self.notify("refresh")
        return True

    def input_signature(self):
        return (
            tuple(self._pairs()),
            self.bin_width,
            self.rep_rate,
            self.skiprows,
            self.use_header,
            self.first_column_is_time,
        )

    def apply_region(self, lb, ub):
        lower, upper = sorted((int(lb), int(ub)))
        n = min(
            (len(self.data[key].y) for key in ("irf_vv", "irf_vh") if self.data[key] is not None),
            default=max(upper, 0),
        )
        super().apply_region(max(0, min(lower, n)), max(0, min(upper, n)))
        self.notify("refresh")

    def _make_curve(self, template, y, suffix):
        n = len(y)
        curve = DataCurve(
            x=np.asarray(template.x)[:n].copy(),
            y=np.asarray(y).copy(),
            ey=np.asarray(template.ey)[:n].copy(),
            name=Path(template.name).stem + suffix,
            load_filename_on_init=False,
        )
        curve.meta_data.update(
            {key: value for key, value in template.meta_data.items() if key != "unique_identifier"}
        )
        curve.meta_data["source_uid"] = template.unique_identifier
        curve.data_reader = getattr(template, "data_reader", None)
        return curve

    def create_fits(self):
        try:
            if self.loaded_signature != self.input_signature():
                raise ValueError(
                    "Input files or reader settings changed; load/reload the data first."
                )
            self.fit_groups = create_linked_fits(
                self.data, self.lifetime_spectrum, self.rotation_spectrum, self._corrections
            )
            self.status = "Created VV, VH and global anisotropy fits with shared parameters."
            self._set_status(True, self.status)
            return self.fit_groups
        except Exception as exc:
            self.status = f"Fit creation failed: {exc}"
            self._set_status(False, self.status)
            return None

    def spectrum_source(self):
        return [{"amplitude": row[0], "value": row[1]} for row in self.lifetime_spectrum]

    def rotation_source(self):
        return [{"amplitude": row[0], "value": row[1]} for row in self.rotation_spectrum]

    def _edit(self, rows, row, key, value):
        rows[int(row)][0 if key == "amplitude" else 1] = float(value)
        self.update()

    def edit_lifetime(self, row, key, value):
        self._edit(self.lifetime_spectrum, row, key, value)

    def edit_rotation(self, row, key, value):
        self._edit(self.rotation_spectrum, row, key, value)

    def add_lifetime(self):
        self.lifetime_spectrum.append([self.new_lifetime_amplitude, self.new_lifetime_value])

    def add_rotation(self):
        self.rotation_spectrum.append([self.new_rotation_amplitude, self.new_rotation_value])

    def remove_lifetime(self):
        index = (
            self.selected_lifetime_row
            if self.selected_lifetime_row >= 0
            else len(self.lifetime_spectrum) - 1
        )
        if 0 <= index < len(self.lifetime_spectrum):
            self.lifetime_spectrum.pop(index)

    def remove_rotation(self):
        index = (
            self.selected_rotation_row
            if self.selected_rotation_row >= 0
            else len(self.rotation_spectrum) - 1
        )
        if 0 <= index < len(self.rotation_spectrum):
            self.rotation_spectrum.pop(index)

    def save_spectra(self, path=None):
        path = Path(path or self.spk_path)
        if not str(path) or path == Path("."):
            raise ValueError("Choose a spectrum file first.")
        path.parent.mkdir(parents=True, exist_ok=True)
        spectra.save_spectra(
            path, self.lifetime_spectrum, self.rotation_spectrum, mirror_to_default=False
        )
        self.spk_path = str(path)
        self.status = f"Saved spectra to {path}."

    def export_irfs(self, path):
        from chisurf.core.fio.vv_vh import write_vv_vh

        vv, vh = self.data["irf_vv_bg_norm"], self.data["irf_vh_bg_norm"]
        if vv is None or vh is None:
            raise ValueError("Load and normalize the IRFs first.")
        dt = float(np.mean(np.diff(vv.x))) if len(vv.x) > 1 else self.bin_width
        return write_vv_vh(
            path, vv=vv.y, vh=vh.y, metadata={"dt": dt, "source": "tr_anisotropy"}, fmt="%.12g"
        )

    def restore_preferences(self, settings):
        if not settings:
            # Read old preferences without seeding directories or modifying defaults.
            path = self._corrections_path()
            if path.is_file():
                self._corrections.update(json.loads(path.read_text()))
            from chisurf.core.settings import chisurf_settings_path

            path = chisurf_settings_path / "plugins" / "tr_anisotropy" / "wizard.spk.json"
            if path.is_file():
                self.load_spectra(str(path))
            return
        self._corrections.update(settings.get("corrections", {}))
        for attr in (
            "irf_vv_path",
            "irf_vh_path",
            "data_vv_path",
            "data_vh_path",
            "spk_path",
            "stacked_files",
            "bin_width",
            "rep_rate",
            "skiprows",
            "use_header",
            "first_column_is_time",
        ):
            if attr in settings:
                setattr(self, attr, settings[attr])
        for attr in ("lifetime_spectrum", "rotation_spectrum"):
            if attr in settings:
                setattr(self, attr, [list(row) for row in settings[attr]])

    def export_preferences(self):
        return {
            **{
                attr: getattr(self, attr)
                for attr in (
                    "irf_vv_path",
                    "irf_vh_path",
                    "data_vv_path",
                    "data_vh_path",
                    "spk_path",
                    "stacked_files",
                    "bin_width",
                    "rep_rate",
                    "skiprows",
                    "use_header",
                    "first_column_is_time",
                    "lifetime_spectrum",
                    "rotation_spectrum",
                )
            },
            "corrections": dict(self._corrections),
        }
