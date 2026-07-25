r"""Beam-waist calibration from a reference dye (MIA ``Calibration`` port).

Transport and optics enter the correlation together,

.. math::  \exp\!\left[-\frac{a^2(\xi^2 + \psi^2)}{w_r^2 + 4 D \tau}\right]

and for a measurement that samples a *single* lag time — single-point FCS at one
diffusion time — they are genuinely degenerate: widen the beam and slow the
diffusion and nothing changes. A raster scan is different. Its lag time varies
across the carpet, from microseconds along the fast axis to milliseconds along
the slow one, and that spread separates the two: near the fast axis the width is
set mostly by :math:`w_r`, along the slow axis mostly by :math:`D`.

So calibration here is not breaking a degeneracy. It is running the measurement
**backwards** on a sample where the answer is known — image a freely diffusing
reference dye, fix :math:`D` at its literature value corrected to the bench
temperature, and solve for :math:`w_r` and :math:`w_z` — because the waist is far
better determined from a bright, fast, well-characterised dye than from a dim
unknown, and because it then transfers to every later measurement.

A practical consequence worth knowing: because the two are *not* degenerate, a
wrong reference value cannot be absorbed by rescaling the waist. It shows up as
a **poor fit**. If the residual is large, the dye identity, the temperature or
the scan timing is wrong — the calibration carries its own check.

The reference value comes from the metadata store
(:mod:`chisurf.core.fluorescence.dyes`) and the temperature correction from
:mod:`chisurf.core.fluorescence.diffusion`, shared with FCS focus calibration so
the two cannot disagree.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional, Sequence

import numpy as np

from chisurf.core.fluorescence.diffusion import (
    combined_waist,
    diffusion_at_temperature,
    reference_diffusion,
    temperature_sensitivity,
)
from chisurf.core.models.ics.models import image_correlation


@dataclasses.dataclass
class WaistCalibration:
    """Beam waists measured against a reference dye.

    Attributes
    ----------
    w_r : float
        Lateral beam waist, in µm.
    w_z : float
        Axial beam waist, in µm.
    diffusion_coefficient : float
        The reference ``D`` used, in µm²/s, already corrected to
        :attr:`temperature_c`.
    dye : str
        Reference species the calibration was run against.
    temperature_c : float
        Sample temperature the reference value was corrected to.
    n_particles : float
        Fitted particle number, a by-product worth checking: a wildly
        implausible ``N`` means the fit found the wrong minimum.
    offset : float
        Fitted correlation offset.
    success : bool
        Whether the optimiser converged.
    chi2 : float
        Sum of squared residuals at the optimum.
    """

    w_r: float
    w_z: float
    diffusion_coefficient: float
    dye: str = ""
    temperature_c: float = 25.0
    n_particles: float = float("nan")
    offset: float = 0.0
    success: bool = True
    chi2: float = float("nan")

    @property
    def structure_parameter(self) -> float:
        """Return the aspect ratio :math:`S = w_z / w_r`.

        Typically 3–8 for a confocal focus. A value near 1 or above ~15 usually
        means the axial waist was not actually constrained by the data.
        """
        return float(self.w_z / self.w_r) if self.w_r else float("nan")

    def temperature_error(self, delta_c: float = 1.0) -> float:
        """Return the relative error in ``w_r`` from a temperature uncertainty.

        Since :math:`w_r \\propto \\sqrt{D}`, a temperature error propagates at
        *half* its effect on ``D`` — but it then enters every later diffusion
        coefficient as :math:`w_r^2`, i.e. at full strength again.

        Parameters
        ----------
        delta_c : float
            Temperature uncertainty in °C.

        Returns
        -------
        float
            Relative error in the waist.
        """
        return 0.5 * abs(temperature_sensitivity(self.temperature_c)) * abs(delta_c)

    def to_dict(self) -> dict:
        """Return the calibration as a JSON-friendly dictionary."""
        return {
            "w_r": float(self.w_r),
            "w_z": float(self.w_z),
            "structure_parameter": float(self.structure_parameter),
            "diffusion_coefficient": float(self.diffusion_coefficient),
            "dye": self.dye,
            "temperature_c": float(self.temperature_c),
            "n_particles": float(self.n_particles),
            "offset": float(self.offset),
            "success": bool(self.success),
            "chi2": float(self.chi2),
        }


def calibrate_waist(
    carpet,
    *,
    dye: str = "",
    diffusion_coefficient: Optional[float] = None,
    temperature_c: float = 25.0,
    viscosity: Optional[float] = None,
    w_r: float = 0.25,
    w_z: float = 1.2,
    n_particles: float = 1.0,
    offset: float = 0.0,
    fit_axial: bool = True,
    two_d: bool = False,
) -> WaistCalibration:
    """Fit an image correlation of a reference dye for the beam waists.

    Parameters
    ----------
    carpet : IcsCarpet
        Correlation of the calibration measurement — a freely diffusing dye. A
        zero-frame-lag (plain RICS) carpet is enough and is what the reference
        implementation uses.
    dye : str
        Reference species, resolved through the metadata store. Its tabulated
        25 °C value is corrected to *temperature_c* automatically.
    diffusion_coefficient : float, optional
        Reference ``D`` in µm²/s at *temperature_c*, bypassing the store. Use
        when the species is not catalogued; it is **not** corrected further.
    temperature_c : float
        Bench temperature of the calibration measurement. Getting this wrong is
        the dominant systematic error — see
        :meth:`WaistCalibration.temperature_error`.
    viscosity : float, optional
        Sample viscosity in Pa·s when the reference is not in water.
    w_r, w_z : float
        Starting values for the waists, in µm.
    n_particles, offset : float
        Starting values for the amplitude and baseline, both fitted.
    fit_axial : bool
        Release ``w_z``. Fix it when the carpet has too little axial
        information to constrain it, which is common for a fast dye.
    two_d : bool
        Membrane geometry: drop the axial term entirely.

    Returns
    -------
    WaistCalibration
        The fitted waists and the reference conditions they came from.

    Raises
    ------
    ValueError
        If no usable reference ``D`` can be determined, or the carpet lacks the
        timing needed to convert lags into lag times.
    """
    from scipy.optimize import least_squares

    if diffusion_coefficient is None:
        if not dye:
            raise ValueError(
                "a calibration needs either a reference dye or an explicit "
                "diffusion_coefficient"
            )
        d_ref = reference_diffusion(dye, temperature_c, viscosity)
        if not np.isfinite(d_ref):
            raise ValueError(
                f"no diffusion coefficient known for {dye!r}; pass "
                "diffusion_coefficient explicitly"
            )
    else:
        d_ref = float(diffusion_coefficient)

    data = np.asarray(carpet.correlation, dtype=float)
    xi = np.asarray(carpet.pixel_shift, dtype=float)
    psi = np.asarray(carpet.line_shift, dtype=float)
    lags = np.atleast_1d(np.asarray(carpet.frame_lags, dtype=float))
    timing = carpet.timing

    xi3 = np.broadcast_to(xi[None, ...], data.shape)
    psi3 = np.broadcast_to(psi[None, ...], data.shape)
    delta3 = lags[:, None, None]

    free = ["N", "w_r", "offset"]
    start = [float(n_particles), float(w_r), float(offset)]
    if fit_axial and not two_d:
        free.append("w_z")
        start.append(float(w_z))

    def unpack(p: np.ndarray) -> dict:
        """Return the model parameters from the free vector."""
        values = dict(zip(free, p))
        return {
            "n": values["N"],
            "w_r": values["w_r"],
            "offset": values["offset"],
            "w_z": values.get("w_z", w_z),
        }

    def residual(p: np.ndarray) -> np.ndarray:
        v = unpack(p)
        model = image_correlation(
            xi3, psi3, delta3,
            # D is fixed: that is what makes the waists identifiable.
            diffusion_coefficient=d_ref,
            n=v["n"], offset=v["offset"], w_r=v["w_r"], w_z=v["w_z"],
            pixel_duration=timing.pixel_duration_us,
            line_duration=timing.line_duration_ms,
            frame_duration=timing.frame_duration_ms,
            pixel_size=timing.pixel_size_nm,
            two_d=two_d,
        )
        return (model - data).ravel()

    lower = [1e-9, 1e-4, -np.inf] + ([1e-4] if "w_z" in free else [])
    upper = [np.inf, 1e3, np.inf] + ([1e4] if "w_z" in free else [])

    fit = least_squares(residual, start, bounds=(lower, upper))
    values = unpack(fit.x)

    return WaistCalibration(
        w_r=float(values["w_r"]),
        w_z=float(values["w_z"]),
        diffusion_coefficient=float(d_ref),
        dye=str(dye),
        temperature_c=float(temperature_c),
        n_particles=float(values["n"]),
        offset=float(values["offset"]),
        success=bool(fit.success),
        chi2=float(np.sum(fit.fun ** 2)),
    )


def cross_channel_calibration(
    a: WaistCalibration, b: WaistCalibration
) -> WaistCalibration:
    """Combine two per-channel calibrations into the cross-correlation one.

    Two detection channels focus to different waists — chromatic aberration
    alone guarantees it — and their cross-correlation samples the *overlap* of
    the two volumes. Using either channel's own waist for the cross term biases
    the result, so the combination :math:`w = \\sqrt{(w_a^2 + w_b^2)/2}` is used
    for both the lateral and the axial waist.

    Parameters
    ----------
    a, b : WaistCalibration
        The two per-channel calibrations.

    Returns
    -------
    WaistCalibration
        A calibration carrying the combined waists.
    """
    return WaistCalibration(
        w_r=combined_waist(a.w_r, b.w_r),
        w_z=combined_waist(a.w_z, b.w_z),
        diffusion_coefficient=0.5 * (a.diffusion_coefficient + b.diffusion_coefficient),
        dye=a.dye or b.dye,
        temperature_c=a.temperature_c,
        success=a.success and b.success,
    )
