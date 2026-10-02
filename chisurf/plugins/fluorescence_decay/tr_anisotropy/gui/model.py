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


class SpectrumTable:
    """One editable ``[amplitude, value]`` spectrum as the rows a ``data_table`` section reads.

    The rows are fresh records (``row`` is the 1-based position); an edit, a delete or an add writes the
    model's list, so the Qt tool and the native one hold the spectra the same way.
    """

    def __init__(self, model, attr, new_attr):
        self.model, self._attr, self._new = model, attr, new_attr
        self.selected = -1
        self.new_amplitude = 0.5
        self.new_value = 1.0

    @property
    def spectrum(self):
        return getattr(self.model, self._attr)

    def rows(self):
        return [
            {"row": i + 1, "amplitude": float(a), "value": float(v)}
            for i, (a, v) in enumerate(self.spectrum)
        ]

    def select(self, record):
        self.selected = int(record["row"]) - 1 if record else -1

    def edit(self, record, key, value):
        index = int(record["row"]) - 1
        value = float(value)
        if not np.isfinite(value) or (key == "value" and value <= 0) or value < 0:
            self.model.status = "A component needs a nonnegative amplitude and a positive time."
            return
        self.spectrum[index][0 if key == "amplitude" else 1] = value
        self.model.update()

    def delete(self, record=None):
        index = int(record["row"]) - 1 if record else self.selected
        if not 0 <= index < len(self.spectrum):
            index = len(self.spectrum) - 1
        if 0 <= index < len(self.spectrum):
            self.spectrum.pop(index)
            self.selected = -1
            self.model.update()

    def add(self):
        if self.new_amplitude < 0 or self.new_value <= 0:
            self.model.status = "A component needs a nonnegative amplitude and a positive time."
            return
        self.spectrum.append([float(self.new_amplitude), float(self.new_value)])
        self.model.update()

    def enabled(self, name):
        return bool(self.spectrum) if name == "delete" else True


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
        self.lifetime = SpectrumTable(self, "lifetime_spectrum", "new_lifetime")
        self.rotation = SpectrumTable(self, "rotation_spectrum", "new_rotation")

    # -- what the form may touch now ------------------------------------------------------------ #
    def enabled(self, name):
        """Whether the control *name* means something in the current state (no idle controls)."""
        if name == "first_column_is_time":
            return not self.stacked_files
        if name == "bin_width":
            # a measured time column keeps its own axis; channel-index and stacked files take the bin width
            return self.stacked_files or not self.first_column_is_time
        if name in ("region_lb", "region_ub"):
            return self.data["irf_vv"] is not None
        if name == "load_data":
            return self.files_ready()
        if name == "export_irfs":
            return self.data["irf_vv_bg_norm"] is not None
        if name == "create_fits":
            return self.data["irf_vv_bg_norm"] is not None and self.components_ready
        return True

    def bounds(self, name):
        if name in ("region_lb", "region_ub"):
            n = min(
                (len(self.data[k].y) for k in ("irf_vv", "irf_vh") if self.data[k] is not None),
                default=0,
            )
            return 0, n
        raise KeyError(name)

    def region_edited(self, _value=None):
        self.apply_region(self.region_lb, self.region_ub)

    def step_complete(self, index):
        """The wizard's check marks: Data needs the files, Components needs both spectra, the rest are always ticked."""
        if index == 1:
            return self.data_ready
        if index == 4:
            return self.components_ready
        return True

    def error(self, action, *args):
        """Run *action*; a failure becomes the status line instead of escaping."""
        try:
            return action(*args)
        except Exception as exc:  # noqa: BLE001
            self.status = f"Error: {exc}"
            return None

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
