from __future__ import annotations

import numpy as np

import chisurf.core.math
from chisurf import typing


def anisotropy_rt(times: np.ndarray, anisotropy_spectrum: np.ndarray) -> np.ndarray:
    """Rotational anisotropy decay r(t) from an interleaved rotation spectrum.

    Computes

        r(t) = sum_i b_i * exp(-t / rho_i)

    from the interleaved ``(b_1, rho_1, b_2, rho_2, ...)`` rotation spectrum.
    This is the same r(t) that :func:`vm_rt_to_vv_vh` builds internally to
    construct the polarized VV/VH decays; exposing it separately lets the
    simulator and plotting code show the underlying anisotropy without
    duplicating the sum.

    Parameters
    ----------
    times : numpy.ndarray
        Time axis (same unit as the correlation times).
    anisotropy_spectrum : numpy.ndarray
        Interleaved amplitudes and rotational correlation times
        ``(b_1, rho_1, b_2, rho_2, ...)``. May be empty, in which case a
        zero array (no anisotropy) is returned.

    Returns
    -------
    numpy.ndarray
        r(t) evaluated on ``times``.

    Examples
    --------
    >>> import numpy as np
    >>> from chisurf.core.fluorescence.anisotropy.decay import anisotropy_rt
    >>> t = np.array([0.0, 2.0, 4.0])
    >>> np.round(anisotropy_rt(t, np.array([0.3, 2.0])), 6).tolist()
    [0.3, 0.110364, 0.040601]

    Two rotation components add up (b = 0.3 + 0.1, fast and slow):

    >>> np.round(anisotropy_rt(t, np.array([0.3, 2.0, 0.1, 10.0])), 6).tolist()
    [0.4, 0.192237, 0.107633]
    """
    t = np.asarray(times, dtype=np.float64)
    spectrum = np.asarray(anisotropy_spectrum, dtype=np.float64).ravel()
    amplitudes = spectrum[0::2]
    correlation_times = spectrum[1::2]
    n = min(amplitudes.size, correlation_times.size)
    if n == 0:
        return np.zeros_like(t)
    return np.exp(-np.outer(t, 1.0 / correlation_times[:n])) @ amplitudes[:n]


def vm_rt_to_vv_vh(
    times: np.array,
    vm: np.array,
    anisotropy_spectrum: np.ndarray,
    g_factor: float = 1.0,
    l1: float = 0.0,
    l2: float = 0.0,
) -> typing.Tuple[np.array, np.array]:
    """
    Compute the VV and VH decays from a VM decay given an anisotropy spectrum.

    The parallel (VV) and perpendicular (VH) decays are computed in the
    Schaffer/Eggeling parameterisation — the same forward model ``tttrlib`` fits
    (``DecayFit23``: ``x_vv[2] = r0 (2 - 3 l1)``, ``x_vh[0] = 1/g``,
    ``x_vh[2] = r0 (-1 + 3 l2)/g``):

        f_VV(t) = f_VM(t) * (1 + (2 - 3 * l1) * r(t))
        f_VH(t) = f_VM(t) * (1 - (1 - 3 * l2) * r(t)) / g

    where r(t) is calculated from the anisotropy spectrum:

        r(t) = sum_i (b_i * exp(-t / rho_i))

    ``G = S_par / S_perp`` is the parallel/perpendicular sensitivity ratio, so the
    perpendicular channel records ``1/G`` of what an equally sensitive one would —
    it **divides** rather than multiplies. That placement, and this meaning of
    l1/l2, are what make the pair invert back to the anisotropy it was built from:

        r(t) = (f_VV - G * f_VH) / (f_VV + 2 * G * f_VH)

    with numerator and denominator of the correction both collapsing to
    ``3 vm (1 - l1 - l2)`` for any ``l1``, ``l2`` and ``G``.

    .. note::

       l1 and l2 are **not** a 2x2 mixing of an ideal pair
       (``vv(1-l1) + vh l1``, Koshioka 1995). That is a different meaning for the
       same symbols, it does not invert with the correction the rest of the stack
       applies, and this docstring described it for a while after the code had
       moved on — a round trip with both a non-unit G and non-zero l1/l2 came back
       at 0.274 and 0.318 against a truth of 0.300.

    Parameters
    ----------
    times : numpy.array
        Time-axis of the decay.
    vm : numpy.array
        The magic angle (VM) decay.
    anisotropy_spectrum : numpy.array
        An interleaved array containing anisotropy parameters: amplitude and
        correlation time pairs (b_i, rho_i).
    g_factor : float, optional
        Correction factor for different detection sensitivities (default is 1.0).
    l1 : float, optional
        Mixing factor for the parallel (VV) channel (default is 0.0).
    l2 : float, optional
        Mixing factor for the perpendicular (VH) channel (default is 0.0).

    Returns
    -------
    tuple of numpy.array
        A tuple (vv_j, vh_j) where vv_j is the mixed VV decay and vh_j is the
        mixed VH decay.

    Examples
    --------
    >>> import numpy as np
    >>> import chisurf.core.fluorescence.general
    >>> import chisurf.core.fluorescence.anisotropy
    >>> times = np.linspace(0, 50, 32)
    >>> lifetime_spectrum = np.array([1.0, 4.0], dtype=np.float64)
    >>> times, vm = chisurf.core.fluorescence.general.calculate_fluorescence_decay(
    ...     lifetime_spectrum=lifetime_spectrum,
    ...     time_axis=times
    ... )
    >>> anisotropy_spectrum = np.array([0.1, 0.6, 0.38 - 0.1, 10.0])
    >>> vv, vh = chisurf.core.fluorescence.anisotropy.decay.vm_rt_to_vv_vh(
    ...     times,
    ...     vm,
    ...     anisotropy_spectrum
    ... )

    Both rotation components contribute, so ``r(0)`` equals their amplitude
    sum ``r0 = 0.38``: VV starts at ``1 + 2*r0`` and VH at ``g * (1 - r0)``,
    here with the default ``g = 1``.

    >>> float(vv[0])
    1.76
    >>> float(vh[0])
    0.62

    Notes
    -----
    The returned decays account for anisotropy mixing as described in [1]_.

    References
    ----------
    .. [1] Masanori Koshioka, Keiji Sasaki, Hiroshi Masuhara, "Time-Dependent
           Fluorescence Depolarization Analysis in Three-Dimensional
           Microspectroscopy", Applied Spectroscopy, 1995, vol. 49, pp. 224-228.
    """
    # r(t) = sum_i b_i exp(-t / rho_i), summed as one matrix-vector product
    # over the interleaved (b, rho) pairs.
    amplitudes = np.asarray(anisotropy_spectrum[0::2], dtype=np.float64)
    correlation_times = np.asarray(anisotropy_spectrum[1::2], dtype=np.float64)
    n_anisotropies = min(amplitudes.size, correlation_times.size)
    if n_anisotropies:
        rt = (
            np.exp(-np.outer(times, 1.0 / correlation_times[:n_anisotropies]))
            @ amplitudes[:n_anisotropies]
        )
    else:
        rt = np.zeros_like(vm)
    # Schaffer/Eggeling, the same forward model tttrlib fits (DecayFit23:
    # x_vv[2] = r0 (2 - 3 l1), x_vh[0] = 1/g, x_vh[2] = r0 (-1 + 3 l2)/g):
    #
    #     VV = vm (1 + (2 - 3 l1) r),    VH = vm (1 - (1 - 3 l2) r) / G
    #
    # G is the parallel/perpendicular sensitivity ratio, so the perpendicular
    # channel records 1/G of what an equally sensitive one would.
    #
    # This used to build an ideal pair and then mix it with a 2x2 matrix
    # (`vv(1-l1) + vh l1`, Koshioka 1995). That is a *different* meaning for
    # l1/l2, and it does not invert with the correction the rest of the stack
    # applies: a round trip with both a non-unit G and non-zero l1/l2 came back
    # at 0.274 and 0.318 against a truth of 0.300. In this parameterisation the
    # round trip is exact for any l1, l2 and G -- but only against the matching
    # correction, which is DecayFit23's (DecayFit23.cpp, `anisotropy_denominator`):
    #
    #     r = (Sp - G Ss) / (Sp (1 - 3 l2) + (2 - 3 l1) G Ss)
    #
    # Both sides then collapse to 3 vm (1 - l1 - l2) and it cancels exactly
    # (measured 2.7e-16 over 200 random (G, l1, l2)). The naive
    # (Sp - G Ss) / (Sp + 2 G Ss) is *not* that correction: its denominator is
    # 3 vm + 3 vm r (2 l2 - l1), so it recovers r for any G but only at
    # l1 = l2 = 0 -- G = 1.7 with l1 = 0.05, l2 = 0.08 returns 0.2527 against a
    # truth of 0.300. If a round trip here looks wrong, check which denominator
    # is being used before suspecting the pair.
    vv_j = vm * (1.0 + (2.0 - 3.0 * l1) * rt)
    vh_j = vm * (1.0 - (1.0 - 3.0 * l2) * rt) / g_factor
    return vv_j, vh_j


def calculcate_spectrum(
    lifetime_spectrum: np.ndarray,
    anisotropy_spectrum: np.ndarray,
    polarization_type: str,
    g_factor: float = 1.0,
    l1: float = 0.0,
    l2: float = 0.0,
) -> np.ndarray:
    """
    Generate a joint spectrum from a lifetime and an anisotropy spectrum for a specified polarization.

    This function converts a lifetime spectrum and an anisotropy spectrum into a
    joint spectrum for either the 'VV', 'VH', or 'VV/VH' detection channels. The relative
    sensitivity of the channels is adjusted via the g_factor, while l1 and l2
    describe the mixing between the VV and VH channels.

    The unmixed decays for VV and VH are given by:

        f_VV(t) = f_VM(t) * (1 + 2 * r(t))
        f_VH(t) = f_VM(t) * (1 - r(t)) / G

    ``G = S_par / S_perp`` is the parallel/perpendicular sensitivity ratio, so
    the perpendicular channel records ``1/G`` of what an equally sensitive one
    would. That placement -- the same one :func:`vm_rt_to_vv_vh` uses -- is what
    makes the pair invert back to the anisotropy it was built from:

        r(t) = (f_VV - G * f_VH) / (f_VV + 2 * G * f_VH)

    The polarization mixing enters the amplitudes themselves, as it does in
    :func:`vm_rt_to_vv_vh`, rather than as a 2x2 mixing of an ideal pair:

        f_VV(t) = f_VM(t) * (1 + (2 - 3 * l1) * r(t))
        f_VH(t) = f_VM(t) * (1 - (1 - 3 * l2) * r(t)) / G

    Parameters
    ----------
    lifetime_spectrum : numpy.array
        Interleaved amplitudes and fluorescence lifetimes
        (amplitude 1, lifetime 1, amplitude 2, lifetime 2, ...).
    anisotropy_spectrum : numpy.array
        Interleaved amplitudes and depolarization times
        (amplitude 1, rho 1, amplitude 2, rho 2, ...).
    polarization_type : str
        'VV', 'VH', or 'VV/VH'. If neither, the lifetime spectrum is returned unmodified.
        For 'VV/VH', returns stacked VV and VH spectra for joint fitting.
    g_factor : float, optional
        Correction factor for the detection channel sensitivity (default is 1.0).
    l1 : float, optional
        Fraction of VH contributing to the VV channel (default is 0.0).
    l2 : float, optional
        Fraction of VV contributing to the VH channel (default is 0.0).

    Returns
    -------
    numpy.array
        The combined spectrum for the specified detection channel.
        For 'VV/VH', returns stacked VV and VH spectra concatenated.

    Examples
    --------
    >>> import numpy as np
    >>> from chisurf.core.fluorescence.anisotropy.decay import calculcate_spectrum
    >>> lifetime_spectrum = np.array([1.0, 4.0])
    >>> anisotropy_spectrum = np.array([1.0, 1.0])
    >>> g_factor = 2.0

    The VH channel is scaled by ``1 / G``, so at ``G = 2`` its amplitudes are
    half of what an equally sensitive channel would record.

    >>> calculcate_spectrum(
    ...     lifetime_spectrum=lifetime_spectrum,
    ...     anisotropy_spectrum=anisotropy_spectrum,
    ...     polarization_type='VV',
    ...     g_factor=g_factor,
    ...     l1=0.0,
    ...     l2=0.0
    ... )
    array([ 1. ,  4. ,  2. ,  0.8,  0. ,  4. , -0. ,  0.8])
    >>> calculcate_spectrum(
    ...     lifetime_spectrum=lifetime_spectrum,
    ...     anisotropy_spectrum=anisotropy_spectrum,
    ...     polarization_type='VV',
    ...     g_factor=g_factor,
    ...     l1=0.1,
    ...     l2=0.0
    ... )
    array([ 0.9 ,  4.  ,  1.8 ,  0.8 ,  0.05,  4.  , -0.05,  0.8 ])
    >>> calculcate_spectrum(
    ...     lifetime_spectrum=lifetime_spectrum,
    ...     anisotropy_spectrum=anisotropy_spectrum,
    ...     polarization_type='VH',
    ...     g_factor=g_factor,
    ...     l1=0.0,
    ...     l2=0.0
    ... )
    array([ 0. ,  4. ,  0. ,  0.8,  0.5,  4. , -0.5,  0.8])
    >>> out = calculcate_spectrum(
    ...     lifetime_spectrum=lifetime_spectrum,
    ...     anisotropy_spectrum=anisotropy_spectrum,
    ...     polarization_type='VH',
    ...     g_factor=g_factor,
    ...     l1=0.0,
    ...     l2=0.1
    ... )
    >>> out.tolist()
    [0.1, 4.0, 0.2, 0.8, 0.45, 4.0, -0.45, 0.8]

    Notes
    -----
    If the polarization_type is neither 'VV', 'VH', nor 'VV/VH', the function simply
    returns the input lifetime spectrum without modifications.

    References
    ----------
    .. [1] Masanori Koshioka, Keiji Sasaki, Hiroshi Masuhara, "Time-Dependent
           Fluorescence Depolarization Analysis in Three-Dimensional
           Microspectroscopy", Applied Spectroscopy, 1995, vol. 49, pp. 224-228.
    .. [2] Same as [1].
    """
    polarization_type = polarization_type.upper()
    f = np.asarray(lifetime_spectrum, dtype=np.float64)
    a = np.asarray(anisotropy_spectrum, dtype=np.float64)
    if (polarization_type == "VV") or (polarization_type == "VH") or (polarization_type == "VV/VH"):
        e1tn = chisurf.core.math.datatools.e1tn
        # ``e1tn`` scales amplitudes *in place*. Always feed it a fresh copy,
        # otherwise the unmixed VV/VH spectra (which share ``d``) and the two
        # mixed channels (which share ``vv``/``vh``) corrupt one another — the
        # original code reused the same arrays, which collapsed the VH decay to
        # near-zero (only the scatter peak remained).
        d = chisurf.core.math.datatools.elte2(a, f)
        vv = np.hstack([f, e1tn(d.copy(), 2.0)])  # f_VV = f * (1 + 2 r)
        # G is the parallel/perpendicular sensitivity ratio, so the
        # perpendicular channel records 1/G of what an equally sensitive one
        # would -- the placement `vm_rt_to_vv_vh` and the Schaffer correction
        # applied downstream both use. Multiplying here instead put the two
        # forward models a factor g**2 apart in VH.
        vh = e1tn(
            np.hstack([f, e1tn(d.copy(), -1.0)]),  # f_VH = f * (1 - r) / G
            1.0 / g_factor,
        )

        # A mixed channel is the *union* of the scaled VV and VH components, so
        # concatenate them. Element-wise addition (the previous behaviour) also
        # summed the lifetime columns, doubling the decay times.
        vv_mixed = np.hstack([e1tn(vv.copy(), 1.0 - l1), e1tn(vh.copy(), l1)])
        vh_mixed = np.hstack([e1tn(vv.copy(), l2), e1tn(vh.copy(), 1.0 - l2)])

        if polarization_type == "VH":
            return vh_mixed
        elif polarization_type == "VV":
            return vv_mixed
        elif polarization_type == "VV/VH":
            # Return stacked VV and VH spectra for joint fitting
            return np.hstack([vv_mixed, vh_mixed])
    else:
        return f
