"""Global fits of an FCS power series against one photokinetic scheme.

A single saturated FCS curve does not pin a photochemical scheme down. Its
distortion is a *product* of the scheme's rates, the excitation rate and the
optics, and several combinations of those reproduce one curve about equally
well -- the dark-state relaxation time and a fast diffusion component are
partly degenerate, and so are the extinction coefficient and the beam waist.

A power series breaks that. The scheme, the optics and the diffusion
coefficient are properties of the sample and the instrument, so they are the
*same* for every curve; only the excitation power differs, and it is known
rather than fitted. Fitting the whole series at once with those parameters
linked is therefore the measurement that determines a scheme, and it is how
saturation data is analysed in practice (Widengren & Rigler, Bioimaging 4
(1996) 149).

This module builds that fit. It does not invent optimisation machinery: it
assembles the existing :class:`~chisurf.core.fitting.fit.FitGroup` with one
:class:`~chisurf.core.models.fcs.kinetics.FCSKineticsModel` per curve, fixes
each curve's power to its measured value, and links everything the curves
share onto the first fit.
"""

from __future__ import annotations

import numpy as np

#: Parameters that describe the sample and the instrument, not the measurement,
#: and are therefore linked across the whole series. The rate-matrix and
#: brightness parameters are added to this by name at build time, since how many
#: there are depends on the scheme.
SHARED_PARAMETERS = ("wavelength", "extinction", "w_r", "w_z", "D")

#: Parameters that legitimately differ from curve to curve. ``power`` is the
#: measured quantity that distinguishes them and is always fixed; ``N`` and the
#: baselines drift between acquisitions.
LOCAL_PARAMETERS = ("power", "N", "b", "bg")


def scheme_parameter_names(model) -> list[str]:
    """Return the names of a model's rate-matrix and brightness parameters.

    These describe the photochemistry, so they are shared across the series --
    but their number depends on the scheme, so they cannot be listed up front.

    Parameters
    ----------
    model : FCSKineticsModel
        A built model to read the scheme size from.

    Returns
    -------
    list of str
        Parameter names of the dark rates, excitation cross sections and
        per-state brightnesses.
    """
    saturation = model.saturation
    names = []
    for group in (saturation.dark, saturation.exc):
        names.extend(p.name for p in getattr(group, "_rates", []))
    names.extend(p.name for p in getattr(saturation.brightness, "_brightness", []))
    return names


def build_power_series_fit(
    curves,
    powers_mW,
    *,
    share_scheme: bool = True,
    shared: tuple[str, ...] = SHARED_PARAMETERS,
    free_local: tuple[str, ...] = ("N",),
    initial: dict | None = None,
    free: tuple[str, ...] = (),
):
    """Assemble a global fit of an FCS power series.

    Parameters
    ----------
    curves : sequence
        One :class:`~chisurf.core.data.DataCurve` per measured power, lag times
        in ms.
    powers_mW : sequence of float
        The excitation power each curve was measured at (mW). Measured, not
        fitted: each curve's ``power`` is set to its value and fixed.
    share_scheme : bool
        Link the rate-matrix and brightness parameters across the series. This
        is the point of the exercise; ``False`` is for diagnosing a series whose
        curves disagree.
    shared : tuple of str
        Further parameters to link -- by default the optics and the diffusion
        coefficient.
    free_local : tuple of str
        Which of the per-curve parameters to release. ``N`` by default, since
        concentration drifts between acquisitions; ``b`` and ``bg`` stay fixed
        unless asked for.
    initial : dict, optional
        Starting values by parameter name, applied to every fit. The model's
        defaults are *not* the instrument's: leaving the extinction coefficient
        or the beam waist at a default while the data was measured with another
        gives the optimiser a systematic error it can only absorb by distorting
        the scheme, which is a silent wrong answer rather than a bad fit.
    free : tuple of str
        Parameter names to release for fitting. Everything in the scheme is
        fixed by default, so this is how the rates being measured are chosen.

    Returns
    -------
    FitGroup
        Ready to optimise. Its ``grouped_fits`` are in the order given.

    Raises
    ------
    ValueError
        If the number of curves and powers differ, or fewer than two curves are
        given -- a "series" of one is just a fit.
    """
    from chisurf.core.data import DataGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.fcs.kinetics import FCSKineticsModel

    curves = list(curves)
    powers = [float(p) for p in powers_mW]
    if len(curves) != len(powers):
        raise ValueError(f"{len(curves)} curves but {len(powers)} powers")
    if len(curves) < 2:
        raise ValueError("a power series needs at least two curves")

    group = FitGroup(data=DataGroup(curves), model_class=FCSKineticsModel)
    fits = list(group.grouped_fits)

    for fit, curve in zip(fits, curves):
        # A Fit constructed headlessly has no fitting range -- xmin and xmax both
        # start at zero, so every residual slice comes back empty and the
        # optimiser refuses with "N must not exceed M". The GUI sets these when
        # a curve is opened; nothing does it here, so use the whole curve.
        n_points = int(np.asarray(curve.x).size)
        if fit.xmax <= fit.xmin:
            fit.xmin, fit.xmax = 0, max(0, n_points - 1)

    for fit, power_mW in zip(fits, powers):
        saturation = fit.model.saturation
        # The power is what distinguishes the curves and it was measured, so it
        # is set and fixed. Fitting it would hand the optimiser a second way to
        # produce the same distortion and undo the whole point of the series.
        saturation._power.value = power_mW
        saturation._power.fixed = True
        for name in LOCAL_PARAMETERS:
            parameter = fit.model.parameters_all_dict.get(name)
            if parameter is not None and name != "power":
                parameter.fixed = name not in free_local
        # A brightness that scales every state uniformly cancels out of a
        # normalised correlation curve, so releasing it by default would hand
        # the optimiser a direction the data cannot constrain. Brightness
        # *ratios* between states are identifiable; the overall scale is not.
        for parameter in getattr(saturation.brightness, "_brightness", []):
            parameter.fixed = True

    for fit in fits:
        for name, value in (initial or {}).items():
            parameter = fit.model.parameters_all_dict.get(name)
            if parameter is None:
                raise ValueError(f"no parameter named {name!r} in the model")
            parameter.value = float(value)
        for name in free:
            parameter = fit.model.parameters_all_dict.get(name)
            if parameter is None:
                raise ValueError(f"no parameter named {name!r} in the model")
            parameter.fixed = False

    names = list(shared)
    if share_scheme:
        names += scheme_parameter_names(fits[0].model)

    reference = fits[0]
    linked, missing = [], []
    for fit in fits[1:]:
        for name in names:
            if name not in fit.model.parameters_all_dict:
                missing.append(name)
                continue
            fit.link_parameter(name, name, reference)
            linked.append(name)
    if missing:
        raise ValueError(f"cannot link parameters absent from the model: {sorted(set(missing))}")

    group.update()
    return group


def series_relaxation_times(group) -> list[tuple[float, float]]:
    """Return ``(power_mW, slowest relaxation time in s)`` for each fit in a series.

    The relaxation time is an eigenvalue of ``K_dark + k_exc K_exc``, so it is
    not a free parameter of the fit -- it is a prediction the linked scheme
    makes separately for every power. Comparing it against the bunching time
    measured on each curve is the sharpest check that a global fit worked.

    Parameters
    ----------
    group : FitGroup
        A group built by :func:`build_power_series_fit`.

    Returns
    -------
    list of tuple
        One ``(power_mW, tau_relax_s)`` per curve, in the group's order.
    """
    from chisurf.core.fluorescence.fcs.saturation import (
        excitation_rate_peak,
        relaxation_spectrum,
    )

    out = []
    for fit in group.grouped_fits:
        saturation = fit.model.saturation
        modes = relaxation_spectrum(
            excitation_rate_peak(
                saturation.power,
                saturation.extinction,
                saturation.w_r_nm * 1e-9,
                saturation.wavelength_m,
            ),
            saturation.dark_matrix_hz,
            saturation.exc.rate_matrix(),
            saturation.brightness.array,
        )
        out.append((float(saturation._power.value), modes[0][0] if modes else float("nan")))
    return out


def simulate_power_series(
    powers_mW,
    dark_matrix,
    exc_matrix,
    brightness,
    *,
    tau_ms=None,
    extinction: float = 1e5,
    wavelength_nm: float = 488.0,
    w_r_nm: float = 200.0,
    w_z_nm: float = 1000.0,
    D_um2s: float = 400.0,
    n_molecules: float = 1.0,
    baseline: float = 1.0,
    noise: float = 0.0,
    seed: int | None = None,
):
    """Simulate a power series from a known scheme, for testing and teaching.

    Parameters
    ----------
    powers_mW : sequence of float
        Powers to simulate at (mW).
    dark_matrix, exc_matrix, brightness : np.ndarray
        The scheme to simulate.
    tau_ms : np.ndarray, optional
        Lag grid (ms); a 1 us -- 1 s log grid by default.
    extinction, wavelength_nm, w_r_nm, w_z_nm, D_um2s, n_molecules
        The optics and sample the series was measured with.
    noise : float
        Standard deviation of Gaussian noise added to each curve, relative to
        ``G(0)``. Zero gives noiseless curves.
    seed : int, optional
        Seed for the noise.

    Returns
    -------
    list of DataCurve
        One curve per power, named by their power.
    """
    from chisurf.core.data import DataCurve
    from chisurf.core.fluorescence.fcs.saturation import saturated_curve_shape

    if tau_ms is None:
        tau_ms = np.logspace(-3, 3, 96)
    tau_ms = np.asarray(tau_ms, dtype=float)
    rng = np.random.default_rng(seed)

    curves = []
    for power_mW in powers_mW:
        shape = saturated_curve_shape(
            tau_ms * 1e-3,
            power_mW * 1e-3,
            extinction,
            dark_matrix,
            exc_matrix,
            brightness,
            w_r_nm * 1e-9,
            w_z_nm * 1e-9,
            D_um2s * 1e-12,
            include_bunching=True,
            wavelength_m=wavelength_nm * 1e-9,
        )
        y = baseline + shape / n_molecules
        error = np.full_like(y, max(noise, 1e-6))
        if noise > 0:
            y = y + rng.normal(0.0, noise, size=y.shape)
        curves.append(
            DataCurve(
                name=f"{power_mW:g} mW",
                load_filename_on_init=False,
                x=tau_ms,
                y=y,
                ey=error,
            )
        )
    return curves
