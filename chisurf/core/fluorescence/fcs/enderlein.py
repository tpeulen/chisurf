r"""Enderlein Gauss--Lorentz molecule-detection-function (MDF) FCS.

The standard analytic FCS models approximate the confocal detection volume by a
3-D Gaussian, which is only a rough description of a real confocal spot.  The
Enderlein *molecule-detection function* (MDF; Enderlein et al., 2005) is a more
faithful, semi-analytic profile built from the overlap of a Gaussian excitation
beam and a Gaussian-imaged pinhole, giving a **Gauss--Lorentz** shape whose
lateral width and collection efficiency vary with axial position.  It yields an
accurate effective volume :math:`V_\mathrm{eff}` (hence absolute concentrations)
and the diffusion autocorrelation without the Gaussian approximation — important
for absolute-number FCS and two-focus/dual-focus calibration.

This is a port of the Fretica ``FEnderleinMDF`` / ``FVeffEnderlein`` /
``FGdiffEnderlein`` functions.  The MDF (Fretica ``FEnderleinMDF``) is

.. math::

    U(\rho, z) = \frac{\kappa(z)}{w(z)^2}\,
                 \exp\!\left(-\frac{2\rho^2}{w(z)^2}\right) \big/ \mathrm{norm},

with

.. math::

    a &= \tfrac{1}{2}\,\text{pinhole}/\text{magnification}, \\
    w(z) &= w_0\sqrt{1 + \big(\lambda_\mathrm{ex} z / (\pi w_0^2 n)\big)^2}, \\
    R(z) &= R_0\sqrt{1 + \big(\lambda_\mathrm{em} z / (\pi R_0^2 n)\big)^2}, \\
    \kappa(z) &= 1 - \exp\!\big(-2 a^2 / R(z)^2\big), \qquad
    \mathrm{norm} = \big(1 - e^{-2a^2/R_0^2}\big)/w_0^2 .

The effective volume (Fretica ``FVeffEnderlein``) is
:math:`V_\mathrm{eff} = \pi\,(\int \kappa\,dz)^2 / \int (\kappa^2/w^2)\,dz`, and
the normalised diffusion autocorrelation follows from convolving the MDF with
the 3-D diffusion propagator (see :func:`g_diff`).

All lengths are in micrometres, ``tau`` in seconds and ``diffusion`` in
:math:`\mu m^2\,s^{-1}`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Optics:
    """Confocal optical parameters for the Enderlein MDF.

    Attributes
    ----------
    excitation_wavelength : float
        Excitation wavelength :math:`\\lambda_\\mathrm{ex}` (micrometres).
    emission_wavelength : float
        Emission wavelength :math:`\\lambda_\\mathrm{em}` (micrometres).
    refractive_index : float
        Refractive index :math:`n` of the immersion/sample medium.
    pinhole : float
        Confocal pinhole diameter (micrometres, in the image plane).
    magnification : float
        Detection-path magnification.
    """

    excitation_wavelength: float = 0.485
    emission_wavelength: float = 0.520
    refractive_index: float = 1.33
    pinhole: float = 50.0
    magnification: float = 60.0

    @property
    def pinhole_radius(self) -> float:
        """Back-projected pinhole radius ``a = pinhole / 2 / magnification`` (um)."""
        return 0.5 * self.pinhole / self.magnification


def _w(z: np.ndarray, w0: float, optics: Optics) -> np.ndarray:
    """Axial dependence of the lateral 1/e^2 beam radius ``w(z)`` (um).

    Display-side helper for :func:`mdf`; the fit-path twin lives in the
    engine (``IMP.bff`` FcsMdf, and the same law backs the photon
    simulator's Gauss-Lorentz profile in tttrlib's ``SimGrid``).
    """
    lam = optics.excitation_wavelength
    n = optics.refractive_index
    return w0 * np.sqrt(1.0 + (lam * z / (np.pi * w0 * w0 * n)) ** 2)


def _kappa(z: np.ndarray, R0: float, optics: Optics) -> np.ndarray:
    """Axial collection efficiency ``kappa(z)`` from the imaged pinhole."""
    lam = optics.emission_wavelength
    n = optics.refractive_index
    a = optics.pinhole_radius
    R = R0 * np.sqrt(1.0 + (lam * z / (np.pi * R0 * R0 * n)) ** 2)
    return 1.0 - np.exp(-2.0 * a * a / (R * R))


def mdf(
    rho: np.ndarray,
    z: np.ndarray,
    w0: float,
    R0: float,
    optics: Optics | None = None,
) -> np.ndarray:
    r"""Molecule-detection function :math:`U(\rho, z)` (normalised to its peak).

    Parameters
    ----------
    rho, z : numpy.ndarray
        Lateral and axial coordinates (micrometres); broadcast together.
    w0 : float
        Lateral :math:`1/e^2` beam radius at focus (micrometres).
    R0 : float
        Emission-beam waist parameter at focus (micrometres).
    optics : Optics, optional
        Optical parameters (defaults to :class:`Optics`).
    """
    optics = optics or Optics()
    a = optics.pinhole_radius
    norm = (1.0 - np.exp(-2.0 * a * a / (R0 * R0))) / (w0 * w0)
    w = _w(np.asarray(z, dtype=float), w0, optics)
    kappa = _kappa(np.asarray(z, dtype=float), R0, optics)
    return kappa / (w * w) * np.exp(-2.0 * np.asarray(rho, float) ** 2 / (w * w)) / norm


def effective_volume(
    w0: float,
    R0: float,
    optics: Optics | None = None,
    n_grid: int = 4001,
    span: float = 60.0,
) -> float:
    r"""Effective detection volume :math:`V_\mathrm{eff}` (femtolitres-scale, um^3).

    :math:`V_\mathrm{eff} = \pi\,(\int \kappa\,dz)^2 / \int (\kappa^2/w^2)\,dz`
    (Fretica ``FVeffEnderlein``). The integration runs in the engine
    (``IMP.bff.fcs_mdf_effective_volume``); this wrapper only spells the
    optics out.
    """
    import IMP.bff as _bff

    optics = optics or Optics()
    return float(
        _bff.fcs_mdf_effective_volume(
            float(w0),
            float(R0),
            float(optics.excitation_wavelength),
            float(optics.emission_wavelength),
            float(optics.refractive_index),
            float(optics.pinhole_radius),
            int(n_grid),
            float(span),
        )
    )


def g_diff(
    tau: np.ndarray,
    w0: float,
    R0: float,
    diffusion: float,
    optics: Optics | None = None,
    n_grid: int = 201,
    span: float = 40.0,
    normalize: bool = True,
    n_herm: int = 40,
    separation: float = 0.0,
) -> np.ndarray:
    r"""Diffusion autocorrelation for the Enderlein MDF.

    Obtained by convolving the MDF with the 3-D free-diffusion propagator and
    integrating.  With the Gauss--Lorentz MDF the lateral integral is analytic,
    leaving a double axial integral

    .. math::

        G(\tau) \propto \iint dz\,dz'\; \kappa(z)\kappa(z')\,
        (4\pi D\tau)^{-3/2} e^{-(z-z')^2/4D\tau}\,
        \frac{\pi^2}{4 + (w(z)^2 + w(z')^2)/(2 D\tau)} .

    Parameters
    ----------
    tau : numpy.ndarray
        Lag times (seconds).  ``tau = 0`` is handled analytically.
    w0, R0 : float
        MDF waist parameters (micrometres).
    diffusion : float
        Translational diffusion coefficient (:math:`\mu m^2 s^{-1}`).
    optics : Optics, optional
        Optical parameters.
    n_grid : int
        Axial grid points for the double integral.
    span : float
        Axial half-range in Rayleigh ranges.
    normalize : bool
        If ``True`` return the shape normalised to ``G(0) = 1`` (the usual FCS
        model factor multiplying ``1/N``); if ``False`` return
        ``G(tau)`` with ``G(0) = 1/V_eff`` (absolute).

    Returns
    -------
    numpy.ndarray
        The autocorrelation evaluated at each ``tau``.
    """
    # The whole double integral runs in the engine
    # (``IMP.bff.fcs_mdf_g_diff``): a trapezoid over the axial grid times a
    # Gauss--Hermite quadrature in the *difference* direction
    # (z' = z + sqrt(4 D t) xi), which resolves the propagator at any lag.
    # This used to be the single most expensive model evaluation left in
    # Python (110 ms/curve, 93% of it here -- board `T-20260901-15`); the
    # engine agrees with the deleted numpy body to ~2e-15 and the reference
    # transcription in ``test/fluorescence/test_enderlein_fcs.py`` keeps the
    # math pinned.
    import IMP.bff as _bff

    optics = optics or Optics()
    tau = np.atleast_1d(np.asarray(tau, dtype=float))
    return np.asarray(
        _bff.fcs_mdf_g_diff(
            [float(t) for t in tau],
            float(w0),
            float(R0),
            float(diffusion),
            float(optics.excitation_wavelength),
            float(optics.emission_wavelength),
            float(optics.refractive_index),
            float(optics.pinhole_radius),
            int(n_grid),
            float(span),
            bool(normalize),
            int(n_herm),
            float(separation),
        ),
        dtype=float,
    )


def acf(
    tau: np.ndarray,
    n_molecules: float,
    diffusion: float,
    w0: float,
    R0: float,
    offset: float = 0.0,
    optics: Optics | None = None,
    **kwargs,
) -> np.ndarray:
    r"""Full Enderlein-MDF FCS curve ``G(tau) = offset + (1/N) g(tau)``.

    ``g(tau)`` is the :func:`g_diff` shape normalised to ``g(0) = 1``; ``N`` is
    the mean number of molecules in :func:`effective_volume`.
    """
    g = g_diff(tau, w0, R0, diffusion, optics=optics, normalize=True, **kwargs)
    return offset + g / float(n_molecules)
