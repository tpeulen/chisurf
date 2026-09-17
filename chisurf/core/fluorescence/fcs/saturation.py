"""Numerical FCS with photokinetic saturation of an N-state rate scheme.

This module provides the core physics to compute the FCS autocorrelation curve
from a non-Gaussian steady-state emission profile, arising from saturation of
the excited/dark states at high excitation powers.

An arbitrary N-state photochemical scheme is solved at steady state on a 2D
cylindrical ``(r, z)`` grid, and the emission profile ``F(r, z) = sum_i Q_i
P_i(r, z)`` is spatially autocorrelated to obtain ``G(tau)`` without relying on
the analytical 3D-Gaussian approximation.

Conventions
-----------
Rate matrices are **column-stochastic generators**: ``K[target, source]`` holds
the rate of the transition ``source -> target``; the diagonal is derived, never
supplied (see :func:`_generator_matrices`). The total generator at a point is
``K(r) = K_dark + k_exc(r) * K_exc``.

Only states that actually emit may carry a non-zero brightness ``Q_i``. A
ground state with ``Q > 0`` would fluoresce without being excited, and its
emission profile would not decay away from the focus — making every volume
integral in this module grid-size dependent. :func:`emission_profile` warns
when that happens rather than returning a silently meaningless number.
"""

from __future__ import annotations

import functools
import logging
import warnings

import numpy as np

try:
    from numpy import trapezoid as _trapz
except ImportError:  # NumPy < 2
    from numpy import trapz as _trapz

logger = logging.getLogger(__name__)

#: Factor converting a stored dark-rate value from its display unit to Hz (s^-1).
DARK_RATE_UNITS = {"1/s": 1.0, "1/ms": 1e3, "1/us": 1e6, "1/ns": 1e9}

#: Excitation wavelength (m) assumed when a caller does not supply one.
DEFAULT_WAVELENGTH_M = 488e-9

#: Half-width of the (r, z) integration grid, in beam waists.
GRID_EXTENT_WAISTS = 5.0

#: Default radial / axial sampling of the (r, z) integration grid. The radial
#: quadrature dominates the error (the axial FFT converges spectrally), so the
#: grid is deliberately asymmetric: 120 x 40 reproduces the analytical Gaussian
#: curve to ~6e-4 of G(0) for about the cost of a symmetric 60 x 60.
DEFAULT_N_R = 120
DEFAULT_N_Z = 40

_PLANCK = 6.62607015e-34
_C_LIGHT = 2.99792458e8
_N_AVOGADRO = 6.02214076e23


def _gaussian_psf(r: np.ndarray, z: np.ndarray, w0: float, z0: float) -> np.ndarray:
    """Evaluate a normalized Gaussian excitation profile.

    Parameters
    ----------
    r : np.ndarray
        Radial coordinates (m).
    z : np.ndarray
        Axial coordinates (m).
    w0 : float
        Radial beam waist, 1/e^2 radius (m).
    z0 : float
        Axial beam waist, 1/e^2 radius (m).

    Returns
    -------
    np.ndarray
        Excitation profile normalized to 1 at the center.
    """
    return np.exp(-2.0 * r**2 / w0**2) * np.exp(-2.0 * z**2 / z0**2)


def photon_flux(power_W: float, wavelength_m: float = DEFAULT_WAVELENGTH_M) -> float:
    """Total photon flux (photons/s) for a measured power at a wavelength.

    Parameters
    ----------
    power_W : float
        Total measured excitation power (W).
    wavelength_m : float
        Excitation wavelength (m).

    Returns
    -------
    float
        Photon flux (photons/s).
    """
    photon_energy = _PLANCK * _C_LIGHT / wavelength_m
    return float(power_W / photon_energy)


def absorption_cross_section_m2(extinction_coefficient: float) -> float:
    """Absorption cross section (m^2) from the molar extinction coefficient.

    ``sigma = ln(10) * 1000 * epsilon / N_A`` in cm^2, converted to m^2.

    Parameters
    ----------
    extinction_coefficient : float
        Molar extinction coefficient (M^-1 cm^-1).

    Returns
    -------
    float
        Absorption cross section (m^2).
    """
    sigma_cm2 = 1000.0 * np.log(10.0) * extinction_coefficient / _N_AVOGADRO
    return float(sigma_cm2 * 1e-4)


def integrated_excitation_rate(
    power_W: float,
    extinction_coefficient: float,
    wavelength_m: float = DEFAULT_WAVELENGTH_M,
) -> float:
    """Excitation rate integrated over the focal plane, ``sigma_abs * Phi_total``.

    In experimental FCS, the total average laser power ``P_total`` (W) is measured
    at the objective back aperture; the total photon flux is
    ``Phi_total = P_total / (h c / lambda)``. The area-integral of the local
    excitation rate ``k_exc(r) = sigma_abs * phi(r)`` over the focal plane is
    then ``sigma_abs * Phi_total``, independent of how tightly the beam is
    focused. It is a useful power readout, but it is not the rate any single
    molecule experiences — that is :func:`excitation_rate_peak`.

    Parameters
    ----------
    power_W : float
        Total measured excitation power (W).
    extinction_coefficient : float
        Molar extinction coefficient (M^-1 cm^-1).
    wavelength_m : float
        Excitation wavelength (m).

    Returns
    -------
    float
        Area-integrated excitation rate (m^2 s^-1).
    """
    return absorption_cross_section_m2(extinction_coefficient) * photon_flux(power_W, wavelength_m)


def excitation_rate_peak(
    power_W: float,
    extinction_coefficient: float,
    w0: float,
    wavelength_m: float = DEFAULT_WAVELENGTH_M,
) -> float:
    """Compute the peak focal excitation rate ``k_exc(0, 0)`` in s^-1.

    ``k_exc(0, 0) = sigma_abs * 2 Phi_total / (pi w0^2)`` — the excitation rate
    at the centre of the Gaussian focus, used to scale the spatial profile.

    Parameters
    ----------
    power_W : float
        Total measured excitation power (W).
    extinction_coefficient : float
        Molar extinction coefficient (M^-1 cm^-1).
    w0 : float
        Radial beam waist (1/e^2 radius, m).
    wavelength_m : float
        Excitation wavelength (m).

    Returns
    -------
    float
        Peak focal excitation rate (s^-1).
    """
    peak_flux_density = 2.0 * photon_flux(power_W, wavelength_m) / (np.pi * w0**2)
    return absorption_cross_section_m2(extinction_coefficient) * peak_flux_density


def excitation_rate(
    r: np.ndarray,
    z: np.ndarray,
    w0: float,
    z0: float,
    power_W: float,
    extinction_coefficient: float,
    wavelength_m: float = DEFAULT_WAVELENGTH_M,
) -> np.ndarray:
    """Compute the spatially dependent excitation rate ``k_exc(r, z)`` in s^-1.

    Derived from the total measured laser power ``P_total`` (W) at the objective
    back aperture::

        Phi_total = P_total / h nu                        (photons / s)
        peak flux density = 2 Phi_total / (pi w0^2)       (photons / s m^2)
        k_exc(0, 0) = sigma_abs * peak flux density       (s^-1)

    Parameters
    ----------
    r : np.ndarray
        Radial coordinates (m).
    z : np.ndarray
        Axial coordinates (m).
    w0 : float
        Radial beam waist (1/e^2 radius, m).
    z0 : float
        Axial beam waist (1/e^2 radius, m).
    power_W : float
        Total measured excitation laser power (W).
    extinction_coefficient : float
        Molar extinction coefficient (M^-1 cm^-1).
    wavelength_m : float
        Excitation wavelength (m).

    Returns
    -------
    np.ndarray
        Excitation rate (s^-1), matching the shape of ``(r, z)``.
    """
    k_exc_peak = excitation_rate_peak(power_W, extinction_coefficient, w0, wavelength_m)
    return k_exc_peak * _gaussian_psf(r, z, w0, z0)


def _generator_matrices(dark_matrix, exc_matrix) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(K_dark, K_exc)`` as generator matrices with a derived diagonal.

    Each matrix is zeroed on the diagonal and its diagonal set to ``-sum(column)``,
    so every column sums to zero and ``K = K_dark + k_exc * K_exc`` is a proper
    master-equation generator. This is the one place the diagonal convention is
    applied; the steady-state and bunching solvers both build on it.

    Parameters
    ----------
    dark_matrix : array_like
        N x N matrix of power-independent rates, ``K[target, source]`` in Hz.
    exc_matrix : array_like
        N x N matrix of relative excitation cross sections, ``K[target, source]``.

    Returns
    -------
    tuple of np.ndarray
        ``(K_dark, K_exc)`` with derived diagonals.
    """
    K_d = np.array(dark_matrix, dtype=float)
    K_e = np.array(exc_matrix, dtype=float)
    if K_d.shape != K_e.shape or K_d.ndim != 2 or K_d.shape[0] != K_d.shape[1]:
        raise ValueError(
            f"dark and excitation matrices must be square and equal-sized, "
            f"got {K_d.shape} and {K_e.shape}"
        )
    np.fill_diagonal(K_d, 0.0)
    np.fill_diagonal(K_e, 0.0)
    np.fill_diagonal(K_d, -K_d.sum(axis=0))
    np.fill_diagonal(K_e, -K_e.sum(axis=0))
    return K_d, K_e


def steady_state_full_populations(
    k_exc: np.ndarray, dark_matrix: np.ndarray, exc_matrix: np.ndarray
) -> np.ndarray:
    """Compute steady-state populations ``P_i(r, z)`` for all N states.

    Solves the master equation ``K(r) P(r) = 0`` subject to ``sum_i P_i(r) = 1``
    for an arbitrary N-state rate scheme.

    Parameters
    ----------
    k_exc : np.ndarray
        Excitation rate array (s^-1) of arbitrary shape (e.g. a 2D grid).
    dark_matrix : np.ndarray
        N x N dark-state transition matrix ``K_dark`` (Hz).
    exc_matrix : np.ndarray
        N x N excitation cross-section matrix ``K_exc``.

    Returns
    -------
    np.ndarray
        State populations of shape ``(N, *k_exc.shape)``, where ``P[i]`` is the
        spatial population profile of state ``i``.
    """
    k_exc = np.asarray(k_exc, dtype=float)
    K_d, K_e = _generator_matrices(dark_matrix, exc_matrix)
    n_states = K_d.shape[0]
    n_points = int(k_exc.size)

    # K_m[p] is the generator at grid point p; the last row is replaced by the
    # normalisation constraint sum_i P_i = 1 (the generator's rows are linearly
    # dependent, so exactly one of them is redundant).
    K_m = np.empty((n_points, n_states, n_states), dtype=float)
    K_m[:] = K_d
    K_m += k_exc.reshape(-1, 1, 1) * K_e
    K_m[:, -1, :] = 1.0

    b = np.zeros((n_points, n_states, 1), dtype=float)
    b[:, -1, 0] = 1.0

    # LAPACK per matrix, despite the per-call overhead looking like the thing to
    # beat here: a Gauss-Jordan vectorised over the grid was measured at 1172 us
    # against 657 us for this, because at N = 3 the temporaries and the
    # per-system row swaps cost more than the overhead they remove.
    try:
        P_all = np.linalg.solve(K_m, b).squeeze(-1)
    except np.linalg.LinAlgError:
        # A generator whose rates are all zero (no scheme configured, no
        # excitation) is singular even after the constraint row.
        P_all = np.empty((n_points, n_states), dtype=float)
        for p in range(n_points):
            P_all[p] = np.linalg.lstsq(K_m[p], b[p], rcond=None)[0].ravel()

    return P_all.T.reshape((n_states,) + k_exc.shape)


def emission_profile(
    k_exc: np.ndarray,
    dark_matrix: np.ndarray,
    exc_matrix: np.ndarray,
    brightness: np.ndarray,
) -> np.ndarray:
    """Compute the steady-state fluorescence profile ``F = sum_i Q_i P_i``.

    Parameters
    ----------
    k_exc : np.ndarray
        Excitation rate (s^-1), array of arbitrary shape (e.g. a 2D grid).
    dark_matrix : np.ndarray
        N x N dark-state rate matrix ``K_dark`` (Hz).
    exc_matrix : np.ndarray
        N x N excitation cross-section matrix ``K_exc``.
    brightness : np.ndarray
        Relative fluorescence brightness ``Q_i`` of each state, shape ``(N,)``
        for a single detection channel, or ``(n_channels, N)`` for several —
        the per-channel form is what a FRET measurement needs, where the donor
        and acceptor channels see the same states with different brightnesses.

    Returns
    -------
    np.ndarray
        Emission profile shaped like ``k_exc``, or ``(n_channels, *k_exc.shape)``
        when a per-channel brightness matrix was given.
    """
    q = np.atleast_1d(np.asarray(brightness, dtype=float))
    P_states = steady_state_full_populations(k_exc, dark_matrix, exc_matrix)
    if q.shape[-1] != P_states.shape[0]:
        raise ValueError(
            f"brightness has {q.shape[-1]} entries but the scheme has {P_states.shape[0]} states"
        )
    profile = np.tensordot(q, P_states, axes=(q.ndim - 1, 0))

    # An emitter that glows where there is no light is not an emitter: every
    # volume integral below would then be set by the box, not by the physics.
    peak = float(np.max(profile)) if profile.size else 0.0
    first_spatial = q.ndim - 1  # leading axes are detection channels, not space
    if peak > 0.0 and profile.ndim > first_spatial:
        edge = max(
            float(np.max(np.abs(np.take(profile, -1, axis=axis))))
            for axis in range(first_spatial, profile.ndim)
        )
        if edge > 1e-3 * peak:
            warnings.warn(
                f"The emission profile does not vanish at the edge of the integration "
                f"grid (edge/peak = {edge / peak:.3g}). A state that emits without being "
                f"excited (e.g. Q > 0 on the ground state) makes the effective volume "
                f"depend on the grid size rather than on the photophysics.",
                RuntimeWarning,
                stacklevel=2,
            )
    return profile


#: Backwards-compatible alias; :func:`emission_profile` is the intended spelling.
steady_state_population_matrix = emission_profile


def effective_volume(r: np.ndarray, z: np.ndarray, profile: np.ndarray) -> float:
    """Compute the FCS effective volume ``V_eff = (int F)^2 / int F^2``.

    Parameters
    ----------
    r : np.ndarray
        1D radial coordinates (m), starting at 0.
    z : np.ndarray
        1D axial coordinates (m), symmetric about 0.
    profile : np.ndarray
        Emission profile ``F(r, z)`` of shape ``(len(r), len(z))``.

    Returns
    -------
    float
        Effective volume (m^3); ``0.0`` if the profile integrates to zero.
    """
    R = r[:, None]
    r_element = 2.0 * np.pi * R
    int_f = float(_trapz(_trapz(profile * r_element, r, axis=0), z))
    int_f2 = float(_trapz(_trapz(profile**2 * r_element, r, axis=0), z))
    if int_f <= 0.0 or int_f2 <= 0.0:
        return 0.0
    return int_f**2 / int_f2


def gaussian_g_diff(tau_s: np.ndarray, w0: float, z0: float, D: float) -> np.ndarray:
    """Analytical 3D-Gaussian diffusion autocorrelation shape, ``G(0) = 1``.

    Parameters
    ----------
    tau_s : np.ndarray
        Lag times (s).
    w0 : float
        Radial beam waist (1/e^2 radius, m).
    z0 : float
        Axial beam waist (1/e^2 radius, m).
    D : float
        Diffusion coefficient (m^2/s).

    Returns
    -------
    np.ndarray
        ``(1 + 4 D tau / w0^2)^-1 (1 + 4 D tau / z0^2)^-1/2``.
    """
    import IMP.bff as _bff

    tau_s = np.atleast_1d(np.asarray(tau_s, dtype=float))
    return np.asarray(
        _bff.fcs_gaussian_g_diff([float(v) for v in tau_s], float(w0), float(z0), float(D)),
        dtype=float,
    )


@functools.lru_cache(maxsize=16)
def _hankel_matrix(n_r: int, r_max: float, kr_max: float, n_kr: int) -> np.ndarray:
    """Return the 0-th order Hankel quadrature matrix ``2 pi r J0(kr r) dr``.

    Cached, because it is the single most expensive part of a curve evaluation
    (thousands of Bessel evaluations) and it depends on nothing but the two
    grids -- which are fixed by the beam waist and the sampling. Dragging the
    power, or running a fit that only moves rates, reuses it every time.

    Parameters
    ----------
    n_r : int
        Number of radial samples; the grid is ``linspace(0, r_max, n_r)``.
    r_max : float
        Outer radius of the grid (m).
    kr_max : float
        Largest radial wavevector (m^-1); the grid is ``linspace(0, kr_max, n_kr)``.
    n_kr : int
        Number of radial wavevectors.

    Returns
    -------
    np.ndarray
        Read-only ``(n_kr, n_r)`` matrix; multiply a profile by it to transform.
    """
    from scipy.special import j0

    r = np.linspace(0.0, r_max, n_r)
    kr = np.linspace(0.0, kr_max, n_kr)
    weights = np.full(n_r, r_max / (n_r - 1) if n_r > 1 else 1.0)
    weights[0] *= 0.5
    weights[-1] *= 0.5
    matrix = 2.0 * np.pi * (r * weights)[None, :] * j0(kr[:, None] * r[None, :])
    matrix.setflags(write=False)  # shared between callers; never mutate in place
    return matrix


def fcs_numerical_g_diff(
    tau: np.ndarray,
    r: np.ndarray,
    z: np.ndarray,
    profile: np.ndarray,
    D: float,
    v_ref: float | None = None,
    kr_max: float | None = None,
    n_kr: int | None = None,
    profile_b: np.ndarray | None = None,
) -> np.ndarray:
    """Numerically compute the FCS diffusion (cross-)correlation ``G(tau)``.

    Evaluates the spatial correlation of arbitrary axially symmetric emission
    profiles in reciprocal space::

        G(tau) = int d^3k Fa~(k) Fb~*(k) exp(-D k^2 tau) / (c int Fa dV int Fb dV)

    using a 0-th order Hankel transform along ``r`` and an FFT along ``z``, so
    that ``d^3k = 2 pi k_r dk_r dk_z`` and ``int d^3k / (2 pi)^3 = int k_r dk_r
    dk_z / (4 pi^2)``. With ``profile_b`` omitted this is the autocorrelation of
    ``profile``; giving a second profile yields the cross-correlation of two
    detection channels, which is what a FRET-FCS measurement needs.

    The reciprocal-space sum is normalised by *its own* ``tau = 0`` value and
    the amplitude is then taken from the real-space integrals (which satisfy
    Parseval's theorem exactly). That makes ``G(0)`` exact at any grid density
    and leaves only the much smaller shape error to the quadrature.

    Parameters
    ----------
    tau : np.ndarray
        Lag times (s).
    r : np.ndarray
        1D array of radial coordinates (m), starting at 0.
    z : np.ndarray
        1D array of axial coordinates (m), symmetric about 0.
    profile : np.ndarray
        2D emission profile of shape ``(len(r), len(z))``.
    D : float
        Diffusion coefficient (m^2/s).
    v_ref : float, optional
        Reference volume (m^3) to normalise against, e.g. the Gaussian
        ``V_0 = pi**1.5 * w0^2 * z0``. When given, the amplitude carries the
        saturation volume expansion: ``G(0) = v_ref / V_eff``. When ``None``,
        the shape is normalised to ``G(0) = 1``.
    kr_max : float, optional
        Largest radial wavevector included (m^-1). Defaults to ``30 / r[-1]``,
        i.e. ``6 / w0`` on the standard five-waist grid, which truncates a
        Gaussian power spectrum at the 1e-4 level.
    n_kr : int, optional
        Number of radial wavevectors, default ``min(len(r), 64)``. The accuracy
        is set by the *real-space* radial sampling, not by this one, so a denser
        k grid buys nothing.
    profile_b : np.ndarray, optional
        Second channel's emission profile, for a cross-correlation.

    Returns
    -------
    np.ndarray
        The diffusion (cross-)correlation ``G(tau)`` at each lag time.
    """
    tau = np.atleast_1d(np.asarray(tau, dtype=float))
    r = np.asarray(r, dtype=float)
    z = np.asarray(z, dtype=float)
    profile = np.asarray(profile, dtype=float)
    is_auto = profile_b is None
    profile_b = profile if is_auto else np.asarray(profile_b, dtype=float)
    nr, nz = len(r), len(z)
    if profile.shape != (nr, nz) or profile_b.shape != (nr, nz):
        raise ValueError(
            f"profile shapes {profile.shape}/{profile_b.shape} do not match ({nr}, {nz})"
        )
    if nr < 2 or nz < 2:
        raise ValueError("the (r, z) grid needs at least two points per axis")

    r_element = 2.0 * np.pi * r[:, None]
    int_a = float(_trapz(_trapz(profile * r_element, r, axis=0), z))
    int_b = float(_trapz(_trapz(profile_b * r_element, r, axis=0), z))
    int_ab = float(_trapz(_trapz(profile * profile_b * r_element, r, axis=0), z))
    if int_a <= 0.0 or int_b <= 0.0 or int_ab == 0.0:
        return np.zeros_like(tau)

    dz = float(z[1] - z[0])
    if kr_max is None:
        kr_max = 30.0 / float(r[-1])

    # The k-space quadrature weights (d_kr, and d_kz = 2 pi / (nz dz)) and the
    # 1/(4 pi^2) of the cylindrical measure are all constants, so the
    # self-normalisation below cancels them exactly; only the k grids matter.
    kr = np.linspace(0.0, kr_max, max(2, int(n_kr) if n_kr else min(nr, 64)))

    # The profile is real, so the axial transform only needs its non-negative
    # frequencies: rfft halves both the transform and everything downstream of
    # it. The dropped half is the mirror image (|F(-k)| = |F(k)|, and k^2 is even
    # in k), so it is restored exactly by doubling the paired bins -- all of them
    # except DC and, for an even-length grid, Nyquist, which have no partner.
    kz = np.fft.rfftfreq(nz, d=dz) * (2.0 * np.pi)
    mirror = np.full(kz.size, 2.0)
    mirror[0] = 1.0
    if nz % 2 == 0:
        mirror[-1] = 1.0

    # Transform the real and imaginary parts separately. Feeding a complex array
    # to a real matrix makes NumPy promote the matrix and run a complex GEMM,
    # which costs far more than the two real ones it replaces.
    j0_matrix = _hankel_matrix(nr, float(r[-1]), float(kr_max), kr.size)
    f_zk = np.fft.rfft(profile, axis=1) * dz
    f_re, f_im = j0_matrix @ f_zk.real, j0_matrix @ f_zk.imag
    if is_auto:
        csd = f_re * f_re + f_im * f_im
    else:
        g_zk = np.fft.rfft(profile_b, axis=1) * dz
        g_re, g_im = j0_matrix @ g_zk.real, j0_matrix @ g_zk.imag
        csd = f_re * g_re + f_im * g_im

    # Cylindrical spectral density; the k_r weight already kills the DC bin.
    csd = csd * kr[:, None] * mirror[None, :]
    total = float(csd.sum())
    if total == 0.0:
        return np.zeros_like(tau)

    # G(0) = v_ref * int(Fa Fb) / (int Fa int Fb) -- i.e. v_ref / V_eff for an
    # autocorrelation; the reciprocal-space sum carries only the tau dependence.
    amplitude = (v_ref * int_ab / (int_a * int_b)) if v_ref is not None else 1.0

    # The propagator separates: exp(-D (kr^2 + kz^2) tau) = exp(-D kr^2 tau)
    # exp(-D kz^2 tau). Summing over the full (kr, kz) grid would evaluate
    # n_kr*n_kz*n_tau exponentials; factoring needs only (n_kr + n_kz)*n_tau of
    # them and leaves the rest to two matrix products, which are an order of
    # magnitude cheaper per element. For the default grid that is 31k
    # exponentials instead of 768k, and it is exact -- not an approximation.
    decay_z = np.exp(-D * np.square(kz)[:, None] * tau[None, :])
    decay_r = np.exp(-D * np.square(kr)[:, None] * tau[None, :])
    out = np.einsum("it,it->t", decay_r, csd @ decay_z, optimize=True)
    return out * (amplitude / total)


def _relaxation_modes(K, p_eq, q_a, q_b):
    """Eigen-decompose a generator into its relaxation modes.

    ``X(tau) = sum_m c_m exp(lambda_m tau)``, so the eigenvalues of
    ``K = K_dark + k_exc K_exc`` *are* the relaxation rates a bunching fit
    reports -- not an approximation to them. One eigenvalue is always zero (the
    stationary distribution); the rest are the scheme's relaxation modes.

    Parameters
    ----------
    K : np.ndarray
        Generator matrix at one excitation rate.
    p_eq : np.ndarray
        Its normalised stationary distribution.
    q_a, q_b : np.ndarray
        Per-state brightness of the two detection channels.

    Returns
    -------
    tuple of np.ndarray
        ``(eigenvalues, amplitudes)``; the amplitudes are unnormalised.
    """
    evals, evecs = np.linalg.eig(K)
    # A generator has no eigenvalue with a positive real part; clip the
    # numerical noise on the stationary one so exp() cannot blow up.
    evals = np.minimum(np.real(evals), 0.0) + 1j * np.imag(evals)
    c_m = np.dot(q_a, evecs) * np.linalg.solve(evecs, q_b * p_eq)
    return evals, c_m


def relaxation_spectrum(
    k_exc_0: float,
    dark_matrix: np.ndarray,
    exc_matrix: np.ndarray,
    brightness: np.ndarray,
) -> list[tuple[float, float]]:
    """Relaxation times and amplitudes of a scheme at one excitation rate.

    These are what a bunching fit measures. For the familiar three-state case
    the slow mode is close to ``1/(k_T + k_ISC f_S1)``, but that is a limit of
    this, not a definition: the eigenvalue is exact, stays exact when the
    excitation rate approaches the dark-state rates, and generalises to any
    number of states, where several modes mix and no closed form exists.

    Parameters
    ----------
    k_exc_0 : float
        Excitation rate to evaluate at (s^-1), usually the peak focal rate.
    dark_matrix, exc_matrix : np.ndarray
        The scheme's rate and cross-section matrices.
    brightness : np.ndarray
        Relative brightness of each state.

    Returns
    -------
    list of tuple
        ``(relaxation_time_s, amplitude)`` per non-stationary mode, slowest
        first. The amplitude is the mode's weight in ``X(tau) - 1``.
    """
    K_d, K_e = _generator_matrices(dark_matrix, exc_matrix)
    K = K_d + max(0.0, float(k_exc_0)) * K_e
    n_states = K_d.shape[0]

    K_eq = K.copy()
    K_eq[-1, :] = 1.0
    b = np.zeros(n_states)
    b[-1] = 1.0
    try:
        p_eq = np.linalg.solve(K_eq, b)
    except np.linalg.LinAlgError:
        return []
    p_eq = np.maximum(p_eq, 0.0)
    total = float(p_eq.sum())
    if total <= 0.0:
        return []
    p_eq /= total

    q = np.asarray(brightness, dtype=float)
    average = float(np.dot(q, p_eq))
    if average <= 0.0:
        return []

    try:
        evals, c_m = _relaxation_modes(K, p_eq, q, q)
    except np.linalg.LinAlgError:
        return []

    # One eigenvalue is exactly zero in exact arithmetic -- the stationary
    # distribution -- but comes back as a tiny value of either sign. Testing
    # `rate > 0` therefore lets it through as a spurious mode of ~1e14 s, so the
    # cut has to be relative to the fastest rate in the spectrum.
    rates = -np.real(evals)
    scale = float(rates.max()) if rates.size else 0.0
    modes = []
    for rate, weight in zip(rates, c_m):
        if rate <= 1e-9 * scale:
            continue
        modes.append((1.0 / float(rate), float(np.real(weight)) / average**2))
    modes.sort(key=lambda item: item[0], reverse=True)
    return modes


def compute_bunching_factor(
    k_exc_0: float,
    dark_matrix: np.ndarray,
    exc_matrix: np.ndarray,
    brightness: np.ndarray,
    tau_s: np.ndarray,
    brightness_b: np.ndarray | None = None,
) -> np.ndarray:
    """Compute the photokinetic state-relaxation (bunching) factor ``X(tau)``.

    ``X(tau) = <I_a(0) I_b(tau)> / (<I_a> <I_b>)`` for a molecule hopping between
    the states of the scheme, evaluated at a single (peak) excitation rate::

        X(tau) = q_a^T exp(K tau) (q_b * p_eq) / ((q_a . p_eq) (q_b . p_eq))

    It tends to 1 as ``tau -> inf`` and, for the autocorrelation case, to
    ``sum_i Q_i^2 p_i / (sum_i Q_i p_i)^2`` at ``tau = 0``. With no excitation
    (``k_exc_0 = 0``) a scheme whose bright states are only reachable by
    excitation has ``<I> = 0`` and ``X = 1``.

    Nothing here assumes a triplet, or any particular number or ordering of
    states: the scheme is whatever the two matrices say it is. Passing a second
    brightness vector gives the cross-channel factor a FRET-FCS measurement
    needs.

    Parameters
    ----------
    k_exc_0 : float
        Excitation rate the scheme is evaluated at (s^-1), usually the peak
        focal rate :func:`excitation_rate_peak`.
    dark_matrix : np.ndarray
        N x N dark-state rate matrix ``K_dark`` (Hz).
    exc_matrix : np.ndarray
        N x N excitation cross-section matrix ``K_exc``.
    brightness : np.ndarray
        Relative brightness ``Q_i`` of each state, shape ``(N,)``.
    tau_s : np.ndarray
        Lag times (s).
    brightness_b : np.ndarray, optional
        Second channel's brightness vector, for a cross-correlation.

    Returns
    -------
    np.ndarray
        Bunching factor ``X(tau)``, same shape as ``tau_s``.
    """
    # The engine's eigen-decomposition (imp.bff, Eigen) -- one
    # implementation with the C++ forward model; parity pinned at 5e-14
    # including cyclic schemes with complex relaxation modes.
    import IMP.bff as _bff

    tau_grid = np.atleast_1d(np.asarray(tau_s, dtype=float))
    dark = np.asarray(dark_matrix, dtype=float)
    n_states = int(dark.shape[0])
    qb = [] if brightness_b is None else [float(v) for v in np.asarray(brightness_b, dtype=float)]
    return np.asarray(
        _bff.fcs_bunching_factor(
            [float(v) for v in tau_grid],
            float(max(0.0, float(k_exc_0))),
            [float(v) for v in dark.ravel()],
            [float(v) for v in np.asarray(exc_matrix, dtype=float).ravel()],
            n_states,
            [float(v) for v in np.asarray(brightness, dtype=float)],
            qb,
        ),
        dtype=float,
    )


def saturated_curve_shape(
    tau_s: np.ndarray,
    power_W: float,
    extinction: float,
    dark_matrix: np.ndarray,
    exc_matrix: np.ndarray,
    brightness: np.ndarray,
    w0: float,
    z0: float,
    D: float,
    include_bunching: bool = True,
    n_r: int = DEFAULT_N_R,
    n_z: int = DEFAULT_N_Z,
    wavelength_m: float = DEFAULT_WAVELENGTH_M,
    brightness_b: np.ndarray | None = None,
) -> np.ndarray:
    """Compute the numerically integrated saturated FCS diffusion shape ``G(tau)``.

    This is the single implementation of the non-analytical saturation path used
    by both the fitting model (:class:`~chisurf.core.models.fcs.kinetics.FCSKineticsModel`)
    and the ``fcs_saturation_calc`` calculator plugin, so a change to the physics
    or the units propagates to both. The steady-state emission profile is solved
    on an ``(r, z)`` grid spanning :data:`GRID_EXTENT_WAISTS` beam waists, then
    spatially autocorrelated via :func:`fcs_numerical_g_diff`. The photokinetic
    state-relaxation (bunching) factor is included when requested.

    At ``power_W = 0`` there is no excitation, hence no emission profile to
    integrate: the analytical Gaussian shape (:func:`gaussian_g_diff`, amplitude
    1) is returned, which is the exact zero-power limit of the numerical result.

    Parameters
    ----------
    tau_s : np.ndarray
        Lag times (s).
    power_W : float
        Total measured excitation power (W).
    extinction : float
        Molar extinction coefficient (M^-1 cm^-1).
    dark_matrix : np.ndarray
        N x N dark transition matrix ``K_dark`` in Hz.
    exc_matrix : np.ndarray
        N x N excitation cross-section matrix ``K_exc``.
    brightness : np.ndarray
        Relative brightness of each state, shape ``(N,)``.
    w0 : float
        Radial beam waist (1/e^2, m).
    z0 : float
        Axial beam waist (1/e^2, m).
    D : float
        Diffusion coefficient (m^2/s).
    include_bunching : bool
        Multiply by the photokinetic bunching factor (default True).
    n_r : int
        Radial grid points. The quadrature error is set almost entirely by this
        one (the axial FFT converges spectrally), so it is the knob to turn.
    n_z : int
        Axial grid points.
    wavelength_m : float
        Excitation wavelength (m).
    brightness_b : np.ndarray, optional
        Second detection channel's brightness vector. When given the result is
        the channel cross-correlation rather than the autocorrelation.

    Returns
    -------
    np.ndarray
        The saturated autocorrelation shape with amplitude ``V_0/V_eff`` (the
        saturation volume expansion ratio; ``1`` for an unsaturated Gaussian),
        before the ``1/N`` normalisation and baseline the caller applies.
    """
    # The whole pipeline runs in the engine (imp.bff FcsSaturation):
    # placement per the owner's rule -- a forward model belongs in bff
    # regardless of how fast the Python was. Parity pinned at 5e-14 (auto
    # and cross), the zero-power Gaussian limit exact, performance equal
    # (2.1 ms both sides on the model's grid; the Hankel matrix is cached
    # on its grids there exactly as the lru_cache here did).
    import IMP.bff as _bff

    tau_s = np.atleast_1d(np.asarray(tau_s, dtype=float))
    dark = np.asarray(dark_matrix, dtype=float)
    qb = [] if brightness_b is None else [float(v) for v in np.asarray(brightness_b, dtype=float)]
    return np.asarray(
        _bff.fcs_saturated_curve_shape(
            [float(v) for v in tau_s],
            float(power_W),
            float(extinction),
            [float(v) for v in dark.ravel()],
            [float(v) for v in np.asarray(exc_matrix, dtype=float).ravel()],
            int(dark.shape[0]),
            [float(v) for v in np.asarray(brightness, dtype=float)],
            float(w0),
            float(z0),
            float(D),
            bool(include_bunching),
            int(n_r),
            int(n_z),
            float(wavelength_m),
            qb,
        ),
        dtype=float,
    )


def compute_power_sweep(
    power_mW: float,
    extinction: float,
    dark_matrix: np.ndarray,
    exc_matrix: np.ndarray,
    brightness: np.ndarray,
    w_r_nm: float,
    w_z_nm: float,
    D_um2s: float,
    n_points: int = 30,
    n_r: int = DEFAULT_N_R,
    n_z: int = DEFAULT_N_Z,
    wavelength_nm: float = DEFAULT_WAVELENGTH_M * 1e9,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute the volume expansion ratio and diffusion time across laser powers.

    The apparent diffusion time is reported from an isotropically expanded
    waist, ``w_eff = w_r (V_eff/V_0)^(1/3)``, which tracks the half-decay time of
    the numerically integrated saturated curve to within a few percent over the
    whole saturation range (see ``test_saturation_physics.py``).

    Parameters
    ----------
    power_mW : float
        Excitation power the sweep is centred on (mW); the sweep spans
        ``1e-2 mW`` to ``max(50, 2 * power_mW)``.
    extinction : float
        Molar extinction coefficient (M^-1 cm^-1).
    dark_matrix : np.ndarray
        N x N dark-state rate matrix (Hz).
    exc_matrix : np.ndarray
        N x N excitation cross-section matrix.
    brightness : np.ndarray
        State brightness array, shape ``(N,)``.
    w_r_nm : float
        Radial beam waist (nm).
    w_z_nm : float
        Axial beam waist (nm).
    D_um2s : float
        Diffusion coefficient (um^2/s).
    n_points : int
        Number of power sweep steps.
    n_r, n_z : int
        Radial and axial sampling of the (r, z) integration grid.
    wavelength_nm : float
        Excitation wavelength (nm).

    Returns
    -------
    tuple of np.ndarray
        ``(powers_mW, v_eff_over_v0, tau_d_ms)``.
    """
    w0_m = w_r_nm * 1e-9
    z0_m = w_z_nm * 1e-9
    D_m2s = D_um2s * 1e-12
    wavelength_m = wavelength_nm * 1e-9

    tau_d_0_ms = (w0_m**2 / (4.0 * D_m2s)) * 1e3
    max_p = max(50.0, float(power_mW) * 2.0)
    powers_mW = np.logspace(-2, np.log10(max_p), n_points)

    r = np.linspace(0.0, GRID_EXTENT_WAISTS * w0_m, n_r)
    z = np.linspace(-GRID_EXTENT_WAISTS * z0_m, GRID_EXTENT_WAISTS * z0_m, n_z)
    R, Z = np.meshgrid(r, z, indexing="ij")
    v_0 = np.pi**1.5 * w0_m**2 * z0_m

    v_rel_arr = np.ones(n_points)
    tau_d_arr = np.full(n_points, tau_d_0_ms)

    for idx, p_mW in enumerate(powers_mW):
        k_exc = excitation_rate(R, Z, w0_m, z0_m, p_mW * 1e-3, extinction, wavelength_m)
        profile = emission_profile(k_exc, dark_matrix, exc_matrix, brightness)
        v_eff = effective_volume(r, z, profile)
        if v_eff <= 0.0:
            continue
        v_rel = v_eff / v_0
        v_rel_arr[idx] = v_rel
        w_eff = w0_m * (v_rel ** (1.0 / 3.0))
        tau_d_arr[idx] = (w_eff**2 / (4.0 * D_m2s)) * 1e3

    return powers_mW, v_rel_arr, tau_d_arr


def fit_single_component(
    tau_s: np.ndarray, g_shape: np.ndarray, w0: float, z0: float, D: float
) -> tuple[float, float, np.ndarray, float]:
    """Fit one 3D-Gaussian diffusion component to a computed correlation shape.

    This is what an experimenter fits when they do not know the volume has
    stopped being Gaussian, so it answers the question the model cannot answer
    by itself: *what would I have measured?* Saturation flattens the emission
    profile, and a flat-topped profile's autocorrelation is a broader mixture of
    decay rates than any single Gaussian component -- so the fit returns an
    inflated apparent diffusion time and, once the distortion is strong, stops
    describing the curve at all (see Widengren & Rigler, Bioimaging 4 (1996) 149).

    Parameters
    ----------
    tau_s : np.ndarray
        Lag times (s).
    g_shape : np.ndarray
        Diffusion shape to fit, normalised or not; it is fitted on its own
        ``tau -> 0`` value so only the shape matters.
    w0, z0 : float
        Beam waists (m), used only for the starting guess.
    D : float
        Diffusion coefficient (m^2/s), used only for the starting guess.

    Returns
    -------
    tuple
        ``(tau_d_s, structure_parameter, fitted_shape, rms_residual)``. The
        fitted shape is normalised to 1 at the first lag. On failure the
        starting guess is returned with an infinite residual.
    """
    from scipy.optimize import curve_fit

    tau_s = np.asarray(tau_s, dtype=float)
    y = np.asarray(g_shape, dtype=float)
    if y.size == 0 or not np.isfinite(y[0]) or y[0] == 0.0:
        return float("nan"), float("nan"), np.zeros_like(tau_s), float("inf")
    y = y / y[0]

    def model(t, tau_d, structure):
        return 1.0 / (1.0 + t / tau_d) / np.sqrt(1.0 + t / (structure**2 * tau_d))

    guess = (w0**2 / (4.0 * D), max(1.0, z0 / w0))
    try:
        params, _ = curve_fit(
            model,
            tau_s,
            y,
            p0=guess,
            bounds=([1e-12, 0.5], [1.0, 100.0]),
            maxfev=20000,
        )
    except Exception:
        return guess[0], guess[1], model(tau_s, *guess), float("inf")
    fitted = model(tau_s, *params)
    return float(params[0]), float(params[1]), fitted, float(np.sqrt(np.mean((fitted - y) ** 2)))


def fit_two_components(
    tau_s: np.ndarray, g_shape: np.ndarray, w0: float, z0: float, D: float
) -> tuple[float, float, float, np.ndarray, float]:
    """Fit two 3D-Gaussian diffusion components to a computed correlation shape.

    This is how a saturated curve is analysed in practice (Widengren & Rigler,
    Bioimaging 4 (1996) 149): a global triplet term times *two* diffusion times,
    because the flattened emission profile autocorrelates as a broader mixture
    of decay rates than one component can produce. Here the triplet is known --
    it is the scheme -- so it is divided out before fitting and only the two
    diffusion components are recovered.

    The two components share a structure parameter: they are the same molecule
    in one distorted volume, not two species, so what differs between them is
    the transit time, not the shape of the focus.

    Parameters
    ----------
    tau_s : np.ndarray
        Lag times (s).
    g_shape : np.ndarray
        Diffusion shape to fit; only the shape matters, it is normalised here.
    w0, z0 : float
        Beam waists (m), for the starting guess.
    D : float
        Diffusion coefficient (m^2/s), for the starting guess.

    Returns
    -------
    tuple
        ``(fraction_fast, tau_d_fast_s, tau_d_slow_s, fitted_shape, rms)``.
        ``fraction_fast`` is the amplitude of the shorter component. On failure
        the residual is infinite and the times are NaN.
    """
    from scipy.optimize import curve_fit

    tau_s = np.asarray(tau_s, dtype=float)
    y = np.asarray(g_shape, dtype=float)
    if y.size == 0 or not np.isfinite(y[0]) or y[0] == 0.0:
        return (float("nan"),) * 3 + (np.zeros_like(tau_s), float("inf"))
    y = y / y[0]

    def one(t, tau_d, structure):
        return 1.0 / (1.0 + t / tau_d) / np.sqrt(1.0 + t / (structure**2 * tau_d))

    def model(t, fraction, tau_1, tau_2, structure):
        return fraction * one(t, tau_1, structure) + (1.0 - fraction) * one(t, tau_2, structure)

    tau_d = w0**2 / (4.0 * D)
    guess = (0.2, 0.5 * tau_d, 3.0 * tau_d, max(1.0, z0 / w0))
    try:
        params, _ = curve_fit(
            model,
            tau_s,
            y,
            p0=guess,
            bounds=([0.0, 1e-12, 1e-12, 0.5], [1.0, 1.0, 1.0, 100.0]),
            maxfev=200000,
        )
    except Exception:
        return (float("nan"),) * 3 + (np.zeros_like(tau_s), float("inf"))

    fraction, tau_1, tau_2, structure = params
    fitted = model(tau_s, *params)
    rms = float(np.sqrt(np.mean((fitted - y) ** 2)))
    if tau_1 > tau_2:  # report the fast component first, whichever way it landed
        fraction, tau_1, tau_2 = 1.0 - fraction, tau_2, tau_1
    return float(fraction), float(tau_1), float(tau_2), fitted, rms
