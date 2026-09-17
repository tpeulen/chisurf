"""One fit function for the whole image-correlation family.

RICS, STICS, TICS and iMSD fit the same correlation carpet
:math:`G(\\xi, \\psi, \\Delta)` with the same physics; they differ only in which
part of the carpet carries information. :func:`image_correlation` is therefore a
single model over all three lag axes, and the named methods are recovered by
which lags are supplied to it:

* **RICS** -- evaluate at :math:`\\Delta = 0`.
* **STICS** -- evaluate at :math:`\\Delta > 0`.
* **TICS** -- evaluate at :math:`\\xi = \\psi = 0`.
* **iMSD** -- read the Gaussian width of each :math:`\\Delta` slice, which the
  model encodes as :math:`w_r^2 + \\mathrm{MSD}(\\tau)`.

Every term is written so that its neutral value switches it off: ``alpha=1``
gives normal diffusion, ``a_triplet=0`` removes blinking, ``n_immobile=0``
removes the static component, and zero velocities remove flow.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.experiments.ics.data import lag_time


def _pos(x: float, floor: float = 1e-12) -> float:
    """Return ``max(abs(x), floor)``.

    Image-correlation fit functions divide by ``N`` and the beam waists, so
    unconstrained optimizer excursions to zero/negative values would produce
    ``inf``/``nan``. Magnitudes are taken and divisors floored to keep the model
    finite for any parameter value the optimizer proposes.

    Parameters
    ----------
    x : float
        The value to sanitise.
    floor : float
        Smallest magnitude to return.

    Returns
    -------
    float
        ``abs(x)``, floored.
    """
    v = abs(float(x))
    return v if v > floor else floor


def mean_square_displacement(
    tau: np.ndarray,
    diffusion_coefficient: float = 2.0,
    alpha: float = 1.0,
) -> np.ndarray:
    r"""Return the lateral mean square displacement at a lag time, in µm².

    .. math::

        \mathrm{MSD}(\tau) = 4 D \tau^{\alpha}

    This is the quantity iMSD extracts slice by slice: the Gaussian width of
    the correlation at frame lag :math:`\Delta` is :math:`w_r^2 +
    \mathrm{MSD}(\tau)`, so plotting the fitted width against :math:`\tau` and
    subtracting :math:`w_r^2` *is* an iMSD curve. Fitting the whole carpet with
    this model does the same thing in one step, with the PSF width as an
    explicit parameter rather than an intercept.

    Parameters
    ----------
    tau : numpy.ndarray
        Lag time in seconds.
    diffusion_coefficient : float
        Transport coefficient :math:`D` in µm²/s\ :sup:`α`. For ``alpha=1``
        this is the ordinary diffusion coefficient in µm²/s.
    alpha : float
        Anomalous exponent. ``1`` is normal diffusion, ``<1`` subdiffusion,
        ``>1`` superdiffusion.

    Returns
    -------
    numpy.ndarray
        Mean square displacement in µm².
    """
    d = abs(float(diffusion_coefficient))
    a = float(alpha)
    tau = np.asarray(tau, dtype=float)
    if a == 1.0:
        return 4.0 * d * tau
    return 4.0 * d * np.power(np.maximum(tau, 0.0), a)


def image_correlation(
    pixel_shift: np.ndarray,
    line_shift: np.ndarray,
    frame_shift: np.ndarray | float = 0.0,
    n: float = 1.0,
    diffusion_coefficient: float = 2.0,
    alpha: float = 1.0,
    offset: float = 0.0,
    pixel_duration: float = 11.1,
    line_duration: float = 3.33,
    frame_duration: float = 0.0,
    pixel_size: float = 40.0,
    w_r: float = 0.2,
    w_z: float = 1.0,
    tau_triplet: float = 0.002,
    a_triplet: float = 0.0,
    n_immobile: float = 0.0,
    w_immobile: float = 0.2,
    v_x: float = 0.0,
    v_y: float = 0.0,
    shift_x: float = 0.0,
    shift_y: float = 0.0,
    two_d: bool = False,
) -> np.ndarray:
    r"""Evaluate the spatiotemporal image-correlation model.

    .. math::

        G(\xi, \psi, \Delta) = G_0
            + \frac{\gamma}{(N + N_\mathrm{imm})^2}
              \left[ N\, T(\tau)\, D(\tau)\, S(\xi, \psi, \tau)
                   + N_\mathrm{imm}\, S_\mathrm{imm}(\xi, \psi) \right]

    where the lag time :math:`\tau(\xi, \psi, \Delta)` comes from
    :func:`chisurf.core.experiments.ics.data.lag_time`, :math:`T` is the
    triplet/blinking term, :math:`D` the diffusive amplitude decay and
    :math:`S` the spatial correlation broadened by
    :math:`\mathrm{MSD}(\tau)` and displaced by flow.

    Parameters
    ----------
    pixel_shift, line_shift : numpy.ndarray
        Lags :math:`\xi` (fast axis, pixels) and :math:`\psi` (slow axis,
        lines).
    frame_shift : numpy.ndarray or float
        Frame lag :math:`\Delta`. Zero gives a RICS map; non-zero extends the
        model into the STICS/TICS/iMSD region of the carpet.
    n : float
        Number of mobile particles in the observation volume.
    diffusion_coefficient : float
        Transport coefficient in µm²/s\ :sup:`α`.
    alpha : float
        Anomalous diffusion exponent; ``1`` is normal diffusion.
    offset : float
        Constant correlation offset :math:`G_0`.
    pixel_duration : float
        Pixel dwell time in µs.
    line_duration : float
        Line time in ms.
    frame_duration : float
        Frame time in ms. Only matters when ``frame_shift`` is non-zero.
    pixel_size : float
        Pixel size in nm.
    w_r, w_z : float
        Lateral and axial beam waists in µm.
    tau_triplet : float
        Blinking/triplet relaxation time in ms.
    a_triplet : float
        Blinking amplitude in ``[0, 1)``. Zero removes the term.
    n_immobile : float
        Number of immobile particles. Zero removes the static component.
    w_immobile : float
        Width of the immobile structure in µm.
    v_x, v_y : float
        Flow velocity along the fast/slow scan axes in µm/s.
    shift_x, shift_y : float
        Lateral displacement in nm applied to both components, for
        cross-correlation (ccRICS).
    two_d : bool
        Membrane/2D geometry: drop the axial term and use the 2D
        :math:`\gamma` factor.

    Returns
    -------
    numpy.ndarray
        The model correlation, broadcast over the lag inputs.

    Examples
    --------
    The model is normalised so that a single mobile species with no offset has
    amplitude :math:`\gamma / N` at zero lag:

    >>> g = image_correlation(0.0, 0.0, 0.0, n=4.0, w_r=0.25)
    >>> bool(abs(float(g) - 2.0 ** -1.5 / 4.0) < 1e-12)
    True
    """
    xi = np.asarray(pixel_shift, dtype=float)
    psi = np.asarray(line_shift, dtype=float)
    delta = np.asarray(frame_shift, dtype=float)

    n_mobile = _pos(n)
    n_imm = abs(float(n_immobile))
    a_nm = float(pixel_size)
    w_r_um = _pos(w_r, 1e-3)
    w_z_um = _pos(w_z, 1e-3)
    w_imm_um = _pos(w_immobile, 1e-3)

    tau = lag_time(
        xi,
        psi,
        delta,
        pixel_duration_us=pixel_duration,
        line_duration_ms=line_duration,
        frame_duration_ms=frame_duration,
    )

    # Lateral displacement of the correlation peak: the scan displacement in µm,
    # corrected for flow travelled during the lag and for a fixed ccRICS shift.
    dx = a_nm * xi * 1.0e-3 - float(v_x) * tau - float(shift_x) * 1.0e-3
    dy = a_nm * psi * 1.0e-3 - float(v_y) * tau - float(shift_y) * 1.0e-3

    msd = mean_square_displacement(tau, diffusion_coefficient, alpha)

    # Diffusive amplitude decay: lateral always, axial only in 3D.
    decay = 1.0 / (1.0 + msd / w_r_um**2)
    if not two_d:
        decay = decay / np.sqrt(1.0 + msd / w_z_um**2)

    # Blinking/triplet. a_triplet == 0 makes this exactly 1.
    at = float(a_triplet)
    if at != 0.0:
        tau_t = _pos(tau_triplet, 1e-9) * 1.0e-3
        triplet = 1.0 + (at / max(1.0 - at, 1e-12)) * np.exp(-tau / tau_t)
    else:
        triplet = 1.0

    spatial = np.exp(-(dx**2 + dy**2) / (w_r_um**2 + msd))
    mobile = triplet * decay * spatial

    # gamma: the shape factor of the detection volume.
    gamma = 0.5 if two_d else 2.0**-1.5

    if n_imm > 0.0:
        dx_imm = a_nm * xi * 1.0e-3 - float(shift_x) * 1.0e-3
        dy_imm = a_nm * psi * 1.0e-3 - float(shift_y) * 1.0e-3
        immobile = np.exp(-(dx_imm**2 + dy_imm**2) / w_imm_um**2)
        amplitude = gamma / _pos(n_mobile + n_imm) ** 2
        return float(offset) + amplitude * (n_mobile * mobile + n_imm * immobile)

    return float(offset) + gamma / n_mobile * mobile


def ics_gaussian_2d(
    pixel_shift: np.ndarray,
    line_shift: np.ndarray,
    amplitude: float = 1.0,
    pixel_size: float = 50.0,
    sigma_1: float = 200.0,
    sigma_2: float = 200.0,
    angle: float = 0.0,
    x_offset: float = 0.0,
    y_offset: float = 0.0,
    offset: float = 0.0,
) -> np.ndarray:
    """Anisotropic 2D-Gaussian spatial correlation (structure sizing).

    A purely spatial correlation with no diffusion term: two widths and an
    orientation, used to size elliptical structures or the PSF from an image
    auto-correlation. This is the one member of the family that does not read
    the time axis at all.

    Parameters
    ----------
    pixel_shift, line_shift : numpy.ndarray
        Lags along the fast and slow scan axes.
    amplitude : float
        Peak amplitude.
    pixel_size : float
        Pixel size in nm; converts lags to distances.
    sigma_1, sigma_2 : float
        Widths along the two principal axes, in nm.
    angle : float
        Orientation of the first principal axis, in radians.
    x_offset, y_offset : float
        Peak displacement in nm.
    offset : float
        Constant correlation offset.

    Returns
    -------
    numpy.ndarray
        The model correlation.
    """
    px = float(pixel_size)
    xi = np.asarray(pixel_shift, dtype=float)
    psi = np.asarray(line_shift, dtype=float)
    xr = xi * px - float(x_offset)
    yr = psi * px - float(y_offset)
    s1 = _pos(sigma_1, 1.0)
    s2 = _pos(sigma_2, 1.0)
    c, s = np.cos(float(angle)), np.sin(float(angle))
    u = (xr * c + yr * s) / s1
    v = (-xr * s + yr * c) / s2
    return float(offset) + abs(float(amplitude)) * np.exp(-(u**2) - (v**2))
