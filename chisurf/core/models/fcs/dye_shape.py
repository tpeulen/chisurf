"""FCS model that fits the confocal volume shape against a *known* dye.

The measurement this describes is a calibration: a reference dye whose diffusion
coefficient at 25 °C is curated in MMFDB is measured, its ``D(T)`` is derived by
Stokes-Einstein scaling through the water viscosity at the experimental
temperature, and the only free geometry is the confocal volume — the lateral
waist ``w0`` and the structure parameter ``s = w_z / w_xy``.

Because ``D`` is fixed by the dye rather than fitted, the diffusion time is an
*output* of the geometry (``tau_D = w0^2 / 4D``), not a parameter, which is why
``D``, ``tauD`` and the two counts-per-molecule values are ``is_output``
parameters written by :meth:`DyeShapeFCSModel.update_model`.
"""
from __future__ import annotations

import math

import numpy as np

import chisurf.core.fitting
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.fluorescence import diffusion
from chisurf.core.fluorescence.dyes import diffusion_coefficient_25C, dye_names
from chisurf.core.models.model import ModelCurve

#: Reference temperature (K) of the curated ``D(25 °C, water)`` values.
_T_REF_K = 298.15


def dye_diffusion_m2_s(dye_name: str, temperature_K: float) -> float:
    """Return the diffusion coefficient ``D(T)`` of a reference dye, in m²/s.

    Reads the dye's diffusion coefficient at 25 °C in water from MMFDB (the
    ``d25`` probe property) and applies Stokes-Einstein scaling via an
    intermediate hydrodynamic radius ``r_h``.

    Parameters
    ----------
    dye_name : str
        Name (or MMFDB alias) of a reference species carrying ``d25``.
    temperature_K : float
        Experimental temperature in kelvin.

    Returns
    -------
    float
        Diffusion coefficient in m²/s, or NaN when the dye is unknown or the
        physical model cannot be evaluated at that temperature.
    """
    D25_um2_s = diffusion_coefficient_25C(dye_name)
    if not math.isfinite(D25_um2_s) or D25_um2_s <= 0.0:
        return float("nan")

    D25_m2_s = D25_um2_s * 1.0e-12
    try:
        eta_ref = diffusion.water_viscosity(_T_REF_K)
        r_h_m = diffusion.stokes_einstein_radius(_T_REF_K, eta_ref, D25_m2_s)
    except Exception:
        return float("nan")
    if not math.isfinite(r_h_m) or r_h_m <= 0.0:
        return float("nan")

    try:
        eta_T = diffusion.water_viscosity(float(temperature_K))
        D_T = diffusion.stokes_einstein_diffusion(float(temperature_K), eta_T, r_h_m)
    except Exception:
        return float("nan")
    return float(D_T)


class DyeShapeFCSModel(ModelCurve):

    """FCS model with fixed dye diffusion, fitting the confocal volume shape.

    The user selects a reference dye from the MMFDB dye repository. Its
    diffusion coefficient at the experimental temperature is computed via
    Stokes-Einstein using the water viscosity model. The correlation curve is
    then a 3D Gaussian with one bunching term:

    - ``N``    : particle number
    - ``s``    : structure parameter (w_z / w_xy)
    - ``w0``   : lateral waist (nm)
    - ``b``    : baseline
    - ``temp`` : temperature (°C, sets the viscosity)
    - ``ba``, ``bt`` : bunching amplitude and relaxation time (ms)

    The objective of the fit is the confocal volume shape (``s`` and ``w0``) for
    a known dye diffusion coefficient.
    """

    name = "FCS dye shape"
    view_spec_file = "dye_shape.view.json"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """Initialize the dye-shape FCS model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit this model belongs to.
        **kwargs
            Additional keyword arguments forwarded to the base class.
        """
        super().__init__(fit, **kwargs)

        self._N = FittingParameter(
            name="N", label_text="N", value=1.0, lb=1.0e-6, ub=1.0e9,
            bounds_on=False, fixed=False,
            description='Average number of fluorescent particles in the observation volume.'
        )
        self._s = FittingParameter(
            name="s", label_text="s", value=3.5, lb=0.1, ub=20.0,
            bounds_on=False, fixed=False,
            description='Structure parameter s = z0/w0 (axial-to-radial extent of the detection volume).'
        )
        # Confocal waist w0 specified in nanometers for the UI.
        self._w0 = FittingParameter(
            name="w0", label_text="w<sub>0</sub>[nm]", value=350.0, lb=10.0, ub=5000.0,
            bounds_on=False, fixed=False,
            description='Confocal radial waist (1/e²) of the detection volume (nm).'
        )
        self._b = FittingParameter(
            name="b", label_text="b", value=1.0, lb=-10.0, ub=10.0,
            bounds_on=False, fixed=False,
            description='Additive baseline/offset of the correlation function.'
        )
        # Experimental temperature (user-entered, in °C); viscosity is derived
        # from this internally using a kelvin conversion.
        self._temp = FittingParameter(
            name="temp", label_text="temp[°C]", value=20.0, lb=0.0, ub=100.0,
            bounds_on=False, fixed=True,
            description='Experimental temperature (°C). Viscosity is derived from this.'
        )
        # Single global bunching term ba, bt (time in ms).
        self._ba = FittingParameter(
            name="ba", label_text="b<sub>a</sub>", value=0.1, lb=0.0, ub=1.0,
            bounds_on=True, fixed=False,
            description='Bunching amplitude (fraction of molecules in the dark/bunching state).'
        )
        self._bt = FittingParameter(
            name="bt", label_text="b<sub>t</sub>[ms]", value=0.002, lb=1.0e-6,
            ub=float("inf"), bounds_on=False, fixed=False,
            description='Bunching (triplet/blink) correlation time (ms).'
        )
        # Derived diffusion coefficient D (µm²/s).
        self._D = FittingParameter(
            name="D", label_text="D[µm²/s]", value=float("nan"),
            lb=float("-inf"), ub=float("inf"),
            bounds_on=False, fixed=True, is_output=True,
            description='Output: translational diffusion coefficient D (µm²/s), derived from tauD and w0.'
        )
        # Derived diffusion time tauD (ms).
        self._tauD = FittingParameter(
            name="tauD", label_text="&tau;<sub>D</sub>[ms]", value=float("nan"),
            lb=0.0, ub=float("inf"),
            bounds_on=False, fixed=True, is_output=True,
            description='Output: diffusion time tauD (ms).'
        )
        # Derived counts per molecule: cpm over the bright molecules and
        # cpm_all over all molecules, including the dark/bunching states.
        self._cpm = FittingParameter(
            name="cpm", label_text="cpm", value=float("nan"),
            lb=float("-inf"), ub=float("inf"),
            bounds_on=False, fixed=True, is_output=True,
            description='Output: counts per molecule per second (bright fraction only).'
        )
        self._cpm_all = FittingParameter(
            name="cpm_all", label_text="cpm<sub>all</sub>", value=float("nan"),
            lb=float("-inf"), ub=float("inf"),
            bounds_on=False, fixed=True, is_output=True,
            description='Output: counts per molecule per second (all molecules including dark states).'
        )

        self.find_parameters()

        self._dye_name: str = ""
        names = self.dye_names()
        if names:
            self._dye_name = names[0]

    def _shape_parameter_rows(self) -> list:
        """Return the fitted amplitude and confocal-volume parameters, in order."""
        return [self._N, self._s, self._w0, self._b, self._temp]

    def _bunching_parameter_rows(self) -> list:
        """Return the single bunching term's amplitude and relaxation time."""
        return [self._ba, self._bt]

    def _output_parameter_rows(self) -> list:
        """Return the parameters :meth:`update_model` derives rather than fits."""
        return [self._D, self._tauD, self._cpm, self._cpm_all]

    def dye_names(self) -> list[str]:
        """List the reference species MMFDB can supply a ``D(25 °C)`` for."""
        try:
            return list(dye_names())
        except Exception:
            return []

    @property
    def dye_name(self) -> str:
        """Name of the reference dye whose diffusion coefficient is used."""
        return self._dye_name

    @dye_name.setter
    def dye_name(self, name: str) -> None:
        """Set the reference dye.

        Parameters
        ----------
        name : str
            Name of an MMFDB species carrying a diffusion coefficient.
        """
        self._dye_name = str(name)

    def _update_model(self, **kwargs) -> None:
        """Compute the FCS curve for the selected dye and confocal volume.

        The model is a 3D Gaussian with one bunching term. The derived
        parameters (``D``, ``tauD``, ``cpm``, ``cpm_all``) are written back as
        fixed output parameters.

        Parameters
        ----------
        **kwargs
            Additional keyword arguments accepted for signature compatibility.
        """
        data = self.fit.data
        tau = np.asarray(data.x, dtype=float).ravel()

        if tau.size == 0:
            self.x = np.array([], dtype=float)
            self.y = np.array([], dtype=float)
            return

        # Diffusion coefficient of the selected dye at the experimental
        # temperature. The fitting parameter is in °C; the physics is in K.
        T_K = float(self._temp.value) + 273.15
        D_m2_s = dye_diffusion_m2_s(self._dye_name, T_K)
        if not (math.isfinite(D_m2_s) and D_m2_s > 0.0):
            self.x = tau
            self.y = np.full_like(tau, float("nan"))
            return

        w0_nm = float(self._w0.value)
        if not (math.isfinite(w0_nm) and w0_nm > 0.0):
            self.x = tau
            self.y = np.full_like(tau, float("nan"))
            return
        w0_m = w0_nm * 1.0e-9

        # 3D Gaussian: tau_D = w_xy^2 / (4 D); use ms to match the lag axis.
        tauD_ms = (w0_m * w0_m) / (4.0 * D_m2_s) * 1.0e3
        if not (math.isfinite(tauD_ms) and tauD_ms > 0.0):
            self.x = tau
            self.y = np.full_like(tau, float("nan"))
            return

        self._D.value = D_m2_s * 1.0e12
        self._tauD.value = tauD_ms

        N = float(self._N.value)
        s_val = float(self._s.value)
        b_val = float(self._b.value)
        ba_val = float(self._ba.value)
        bt_val = float(self._bt.value)
        if bt_val <= 0.0 or not math.isfinite(bt_val):
            bt_val = 1.0e-6

        with np.errstate(divide="ignore", invalid="ignore"):
            x = tau / tauD_ms
            term1 = 1.0 / (1.0 + x)
            term2 = 1.0 / np.sqrt(1.0 + x / (s_val * s_val))
            bunch = 1.0 - ba_val + ba_val * np.exp(-tau / bt_val)
            g_fit = b_val + (1.0 / np.abs(N)) * term1 * term2 * bunch

        self.x = tau
        self.y = np.asarray(g_fit, dtype=float)

        self._update_counts_per_molecule(N)

    def _update_counts_per_molecule(self, n_bright: float) -> None:
        """Write the two counts-per-molecule outputs from the data's count rate.

        ``cpm`` divides the mean count rate by the fitted particle number;
        ``cpm_all`` first corrects that number for the fraction of molecules
        residing in the dark (bunching) states, so it counts every molecule in
        the volume rather than only the emitting ones.

        Parameters
        ----------
        n_bright : float
            The fitted particle number ``N`` (bright molecules).
        """
        meta = getattr(self.fit.data, "meta_data", {}) or {}
        mean_cr = meta.get("mean_count_rate")
        if mean_cr is None:
            return
        try:
            cr = float(mean_cr)
        except (TypeError, ValueError):
            return
        if not (n_bright > 0.0):
            return

        self._cpm.value = cr / n_bright

        bunch_sum = 0.0
        for name, p in self.parameters_all_dict.items():
            if not name.startswith("ba"):
                continue
            try:
                v = float(p.value)
            except (TypeError, ValueError):
                continue
            if not np.isfinite(v):
                continue
            bunch_sum += min(abs(v), 1.0)

        bright_fraction = 1.0 - bunch_sum
        if bright_fraction <= 0.0 or not np.isfinite(bright_fraction):
            return
        n_all = n_bright / bright_fraction
        if n_all > 0.0 and np.isfinite(n_all):
            self._cpm_all.value = cr / n_all
