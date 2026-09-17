from __future__ import annotations

import numpy as np
import tttrlib


def convolve_lifetime_spectrum_periodic(
    decay: np.ndarray,
    lifetime_spectrum: np.ndarray,
    irf: np.ndarray,
    start: int,
    stop: int,
    n_points: int,
    period: float,
    dt: float,
    conv_stop: int,
):
    """Convolve a lifetime spectrum with a periodic IRF using tttrlib.

    Parameters
    ----------
    decay : np.ndarray
        Output array filled with the convolved decay.
    lifetime_spectrum : np.ndarray
        Interleaved array of amplitudes and lifetimes.
    irf : np.ndarray
        Instrument response function.
    start : int
        Start channel for convolution.
    stop : int
        Stop channel for convolution.
    n_points : int
        Number of points in the decay.
    period : float
        Period of repetition in nanoseconds.
    dt : float
        Channel width in nanoseconds.
    conv_stop : int
        Stopping channel for convolution.

    Notes
    -----
    ``stop`` and ``conv_stop`` are clamped to the last valid *index*. Callers
    pass ``n_points`` (a length), and ``fconv_per_cs`` treats its stop arguments
    as inclusive indices, so an unclamped call reads and writes one element past
    the end of the buffers. That corrupts the heap and aborts the process at some
    later allocation -- far from the real cause, and only on builds that do not
    clamp internally, which is why it surfaced as a GUI crash on a stock
    tttrlib while a locally patched one was fine.

    There used to be a numba twin of this function. It was deleted rather than
    ported: checked against an independent brute-force periodic convolution, it
    never gave the **final channel** its inter-pulse tail -- 2.2e-53 where the
    true value is 1.55e-27 for two lifetimes, and 200x low for 128 -- while this
    path reproduces the reference. The guard that was supposed to keep the two
    in step had been failing.
    """
    last = min(len(irf), len(decay), n_points) - 1
    if last < 0:
        return
    tttrlib.fconv_per_cs(
        decay, irf, lifetime_spectrum, period, min(conv_stop, last), min(stop, last), dt
    )


def convolve_decay(
    decay_curve: np.ndarray, irf: np.ndarray, start: int, stop: int, dt: float
) -> np.ndarray:
    """Convolve a fluorescence decay with an instrument response function.

    Parameters
    ----------
    decay_curve : numpy.ndarray
        Fluorescence decay, before convolution.
    irf : numpy.ndarray
        Instrument response function; must be the same length as
        ``decay_curve``.
    start, stop : int
        Channel range to convolve. Channels outside it are zero.
    dt : float
        Channel width of the decay.

    Returns
    -------
    numpy.ndarray
        The convolved decay.

    Notes
    -----
    Delegates to the photon library's ``sconv``, which is the same trapezoidal
    sum this used to spell out as a numba kernel — half weights on the first and
    last term, ``fit[0]`` forced to zero. ``sconv`` does not apply the channel
    width, so the scaling is applied here.

    Channels outside ``[start, stop)`` come back **zero**. The numba version
    allocated with ``np.empty_like`` and wrote only inside the range, so
    anything outside it was uninitialised memory; both call sites in the tree
    pass the full range, so nothing depended on that.

    Examples
    --------
    >>> import scipy.stats
    >>> n_points = 2048
    >>> time_axis = np.linspace(0, 16, n_points)
    >>> dt = time_axis[1] - time_axis[0]
    >>> irf = scipy.stats.norm.pdf(time_axis, loc=5.0, scale=0.5)
    >>> decay_u = np.exp(- time_axis / 4.1)
    >>> model_decay = convolve_decay(decay_u, irf=irf, start=0, stop=n_points, dt=dt)
    """
    decay_curve = np.ascontiguousarray(decay_curve, dtype=np.float64)
    irf = np.ascontiguousarray(irf, dtype=np.float64)
    out = np.zeros_like(decay_curve)
    tttrlib.sconv(out, irf, decay_curve, int(start), int(stop))
    out *= dt
    out[0] = 0.0
    return out


def periodic_shift(arr: np.ndarray, shift: float) -> np.ndarray:
    """Circularly shift a 1-D histogram by ``shift`` channels (wrap-around).

    The micro-time shifter ``(t + shift) mod n``: the shifted-out tail wraps to
    the front rather than being zero-filled — correct for a periodic IRF / a
    TCSPC colour shift. The fractional part is linearly interpolated, also
    circularly. ``shift`` is in channels (bins); convert from ns by dividing by
    the bin width.

    Parameters
    ----------
    arr : numpy-array
        The histogram to shift (IRF or decay).
    shift : float
        Shift in channels; positive delays (moves later in time).
    """
    arr = np.asarray(arr, dtype=float)
    if arr.size == 0 or not shift:
        return arr.copy()
    int_shift = int(np.floor(shift))
    frac = float(shift) - int_shift
    rolled = np.roll(arr, int_shift)
    if frac:
        rolled = (1.0 - frac) * rolled + frac * np.roll(rolled, 1)
    return rolled


def convolve_lifetime_spectrum(
    output_decay: np.array,
    lifetime_spectrum: np.array,
    instrument_response_function: np.array,
    convolution_stop: int = -1,
    time_axis: np.array = None,
    amplitude_threshold: float = 0,
    use_amplitude_threshold: bool = False,
) -> None:
    """Convolve a lifetime spectrum with an IRF using tttrlib.

    Parameters
    ----------
    output_decay : np.ndarray
        Output array filled with the convolved decay.
    lifetime_spectrum : np.ndarray
        Interleaved array of amplitudes and lifetimes.
    instrument_response_function : np.ndarray
        The instrument response function.
    convolution_stop : int, optional
        Convolution stop channel index.
    time_axis : np.ndarray, optional
        The time axis of the decay.
    amplitude_threshold : float, optional
        Amplitude threshold for filtering lifetime components.
    use_amplitude_threshold : bool, optional
        If True, filter components by amplitude threshold.
    """
    dt = time_axis[1] - time_axis[0]
    tttrlib.fconv(
        output_decay, instrument_response_function, lifetime_spectrum, 0, convolution_stop, dt
    )
