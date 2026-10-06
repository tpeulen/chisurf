"""Qt-free state and actions of the FCS confocal calculator (the Qt ``ConfocalCalcWidget``'s logic).

The fields, the constraint, the reference dye and the shape estimator are plain attributes the
view spec (``fcs_calculator_emtk.view.json``) reads and writes; every edit recomputes the linked
quantities through :func:`..core.algorithms.compute_confocal`, as the Qt widget does through its
backend client.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..core import algorithms as physics

SHAPES = ("Sphere", "Ellipsoid", "Cylinder")
#: The field each constraint makes the input; the other two are computed.
CONSTRAINED = {"D": "D_um2_s", "rh": "rh_nm", "V": "veff_fL"}
NUMBERS = (
    "tau_us",
    "D_um2_s",
    "rh_nm",
    "S",
    "veff_fL",
    "temp_C",
    "eta_mPa_s",
    "conc_nM",
    "num_mols",
    "invN",
)


class ConfocalModel:
    """The calculator's values; defaults are the Qt widget's."""

    def __init__(self):
        self.tau_us = 70.0
        self.D_um2_s = 400.0
        self.rh_nm = 0.5
        self.S = 5.0
        self.veff_fL = 0.4
        self.temp_C = 20.0
        self.eta_mPa_s = 0.890
        self.use_water_eta = True
        self.invN = 0.0
        self.num_mols = 0.602214 * 0.4
        self.conc_nM = 1.0
        self.constraint = "D"
        self.last_edited = "conc"
        names = self.dye_names()
        self.dye = names[0] if names else ""
        self.scale_dref = True
        self.shape_type = "Sphere"
        self.shape_size_nm = 5.0
        self.shape_aspect = 1.0
        self.status = ""
        self.error = ""
        self.recompute()

    # -- the spec's hooks --------------------------------------------------------------
    def enabled(self, name):
        """Computed fields and the water viscosity are read-only, as in the Qt widget."""
        if name in CONSTRAINED.values():
            return name == CONSTRAINED[self.constraint]
        if name == "eta_mPa_s":
            return not self.use_water_eta
        if name == "shape_aspect":
            return self.shape_type != "Sphere"
        if name == "apply_dye":
            return physics.get_dye(self.dye) is not None
        return True

    @staticmethod
    def dye_names():
        return list(physics.dye_names())

    # -- recomputation -----------------------------------------------------------------
    def recompute(self, _value=None):
        """Recompute D, rh, Veff, eta and the occupancy from the inputs and the constraint."""
        result = physics.compute_confocal(
            tau_us=self.tau_us,
            S=self.S,
            temp_C=self.temp_C,
            eta_mPa_s=self.eta_mPa_s,
            use_water_eta=bool(self.use_water_eta),
            constraint=self.constraint,
            D_um2_s=self.D_um2_s,
            rh_nm=self.rh_nm,
            veff_fL=self.veff_fL,
            conc_nM=self.conc_nM,
            num_mols=self.num_mols,
            invN=self.invN,
            last_edited=self.last_edited or "conc",
        )
        for key in ("D_um2_s", "rh_nm", "veff_fL", "conc_nM", "num_mols", "invN"):
            setattr(self, key, result[key])
        if self.use_water_eta:
            self.eta_mPa_s = result["eta_mPa_s"]

    def conc_edited(self, _value=None):
        self.last_edited = "conc"
        self.recompute()

    def N_edited(self, _value=None):  # noqa: N802 - the quantity is called N
        self.last_edited = "N"
        self.recompute()

    def invN_edited(self, _value=None):  # noqa: N802
        self.last_edited = "invN"
        self.recompute()

    def eta_Pa_s(self):
        """The viscosity in Pa s: the water model's when it is on, else the typed one."""
        if self.use_water_eta:
            return physics.water_viscosity_Pa_s(self.temp_C + 273.15)
        return physics.mPa_s_to_Pa_s(self.eta_mPa_s)

    # -- actions -----------------------------------------------------------------------
    def apply_dye(self):
        """Set D from the reference dye (scaled to T and eta, or at 25 C) and switch to Fix D."""
        info = physics.get_dye(self.dye)
        value = float(info.get("d25_um2_s", float("nan"))) if info else float("nan")
        if not math.isfinite(value) or value <= 0.0:
            self.error = "The selected reference has no diffusion coefficient."
            return False
        if self.scale_dref:
            value = physics.scale_D_from_25C(value, self.temp_C + 273.15, self.eta_Pa_s())
        self._set_D(value)
        self.status = f"D = {value:.6g} µm²/s from {self.dye}."
        return True

    def apply_shape(self):
        """Estimate D from the shape (Stokes-Einstein, Perrin ellipsoid, cylinder) and switch to Fix D."""
        temperature, eta = self.temp_C + 273.15, self.eta_Pa_s()
        size, aspect = float(self.shape_size_nm), float(self.shape_aspect)
        value = None
        if size > 0:
            if self.shape_type == "Sphere":
                value = physics.m2s_to_um2s(
                    physics.stokes_einstein_D(temperature, eta, physics.nm_to_m(size) / 2.0)
                )
            elif aspect > 0 and self.shape_type == "Ellipsoid":
                minor = physics.nm_to_m(size) / 2.0
                value = physics.diffusion_ellipsoid(temperature, eta, minor * aspect, minor)
            elif aspect > 0 and self.shape_type == "Cylinder":
                diameter = physics.nm_to_m(size)
                value = physics.diffusion_cylinder(temperature, eta, diameter * aspect, diameter)
        if value is None or not math.isfinite(value) or value <= 0:
            self.error = "This shape gives no diffusion coefficient."
            return False
        self._set_D(value)
        self.status = f"D = {value:.6g} µm²/s from a {self.shape_type.lower()}."
        return True

    def _set_D(self, value):  # noqa: N802
        self.constraint = "D"
        self.D_um2_s = float(value)
        self.error = ""
        self.recompute()

    # -- settings ----------------------------------------------------------------------
    def settings(self):
        """The Qt widget's settings dict (``_collect_settings``), the JSON it exports."""
        data = {key: getattr(self, key) for key in NUMBERS}
        data.update(
            use_water_eta=bool(self.use_water_eta),
            fix_mode=self.constraint,
            dye=self.dye,
            scale_dref=bool(self.scale_dref),
            shape_type=self.shape_type,
            shape_size_nm=self.shape_size_nm,
            shape_aspect=self.shape_aspect,
        )
        return data

    def apply_settings(self, data):
        """Apply a settings dict as the Qt widget does: known keys only, unknown choices ignored."""
        for key in NUMBERS:
            if key in data:
                setattr(self, key, float(data[key]))
        if "use_water_eta" in data:
            self.use_water_eta = bool(data["use_water_eta"])
        if data.get("fix_mode") in CONSTRAINED:
            self.constraint = data["fix_mode"]
        if data.get("dye"):
            # Sessions saved before the table moved into MMFDB may name a species by an alias.
            entry = physics.get_dye(data["dye"])
            name = entry["name"] if entry else data["dye"]
            if name in self.dye_names():
                self.dye = name
        if "scale_dref" in data:
            self.scale_dref = bool(data["scale_dref"])
        if data.get("shape_type") in SHAPES:
            self.shape_type = data["shape_type"]
        if "shape_size_nm" in data:
            self.shape_size_nm = float(data["shape_size_nm"])
        if "shape_aspect" in data:
            self.shape_aspect = float(data["shape_aspect"])
        self.recompute()

    def export_json(self, path):
        path = Path(path)
        path.write_text(json.dumps(self.settings(), indent=2, sort_keys=True), encoding="utf-8")
        self.error, self.status = "", f"Settings saved to {path}."
        return path

    def import_json(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("The file holds no calculator settings.")
        self.apply_settings(data)
        self.error, self.status = "", f"Settings loaded from {Path(path).name}."
