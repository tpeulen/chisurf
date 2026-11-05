"""IRF extraction: the instrument response from whatever the lab measured -- one implementation.

Every tool that needs an IRF (Burst MLE, Burst IRF & Background, the MFD burst fit) hands its
histograms here and takes the IRF back; none extracts one of its own. Where the IRF comes from:

* **scatter** (water, Ludox): the measured prompt *is* the IRF, after its background (a buffer
  measurement scaled to the scatter's time, then the flat floor) -- :func:`irf_from_scatter`;
* **reference dye** of known, single lifetime (Rh110, Alexa647): its decay is the IRF convolved
  with the dye's polarised exponential; the IRF is recovered by Richardson-Lucy deconvolution
  with that kernel, the deconvolution of the blind estimate with the lifetime and rotation known
  instead of guessed -- :func:`irf_from_reference`;
* **non-burst photons** of a single-molecule measurement (scatter between the molecules, on a
  slow fluorescent tail): a Gaussian (or skewed Gaussian) fitted to the prompt's rising edge --
  :func:`irf_from_prompt`;
* **blind**, from a fluorescence decay alone (truncated exponential + Richardson-Lucy,
  Gómez-Sánchez et al. 2024), the last resort -- :func:`irf_from_decay`.

:func:`best_irf` picks among several in :data:`AUTO_ORDER`: a reference dye first (measured in
the same conditions as the sample), then a scatter, then the non-burst photons, then blind. Every function takes and returns plain NumPy histograms (one polarisation, or the two
halves VV | VH); reading photon files is the caller's (its reader settings, gates, binning).

What a fit then does to an IRF (VH shift, clip, background levels) is the fit's business, not
extraction's.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import threading
from collections import OrderedDict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

__all__ = [
    "IrfResult",
    "LIFETIME_TOLERANCE",
    "R0",
    "AUTO_ORDER",
    "ShiftCalibration",
    "best_irf",
    "calibrate_shifts",
    "gaussian_prompt",
    "irf_from_decay",
    "irf_from_prompt",
    "irf_from_reference",
    "irf_from_scatter",
    "polarised_kernels",
    "ReferenceFit",
    "reference_fit",
    "reference_anisotropy",
    "reference_irf",
    "reference_lifetime",
    "reference_rotation",
    "reference_tail_lifetime",
    "richardson_lucy",
    "scatter_irf",
]

#: Fundamental anisotropy of the reference dyes' polarised kernels (one-photon, parallel
#: absorption and emission dipoles; Rh110, fluorescein and the Alexa dyes are within 0.36-0.39).
R0 = 0.38
#: The most Richardson-Lucy iterations of a reference deconvolution (it stops earlier when the
#: model fits the counts at their noise, :func:`richardson_lucy`).
MAX_ITERATIONS = 2000
#: The recovered IRF ends where it falls below this fraction of its peak (both sides).
REFERENCE_TRIM = 1e-3


@dataclass
class IrfResult:
    """An extracted IRF and where it came from.

    ``irf`` is VV then VH (or one polarisation), each half normalised to one (zeros where it
    had nothing). ``counts`` are the photons each half stood on (the caller's quality bar).
    ``text`` is the line a window shows ("Rh110_ref.ptu (Rh110, 4.02 ns from its tail,
    rotation 0.18 ns, deconvolved)"); ``info`` the numbers behind it.
    """

    irf: np.ndarray
    source: str
    text: str
    counts: tuple[float, ...] = ()
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def halves(self) -> list[np.ndarray]:
        """The polarisations of :attr:`irf` (two halves, or the one)."""
        n = len(self.counts) or 1
        return list(np.split(np.asarray(self.irf, dtype=float), n))


# -- helpers --------------------------------------------------------------------------------- #
def _window(n: int, window) -> tuple[int, int]:
    lo, hi = (0, n) if window is None else (max(0, int(window[0])), min(n, int(window[1])))
    return (lo, hi) if hi > lo else (0, n)


def _peak_support(signal: np.ndarray, noise: np.ndarray, lo: int, hi: int, n_sigma: float):
    """The contiguous bins around the strongest peak in ``[lo, hi)`` that stand above
    *n_sigma* times the noise (both smoothed over three bins)."""
    box = np.ones(3) / 3.0
    sm = np.convolve(signal, box, "same")
    sn = np.convolve(noise, box, "same") / np.sqrt(3.0)
    peak = lo + int(np.argmax(sm[lo:hi]))
    i = j = peak
    while i > lo and sm[i - 1] > n_sigma * sn[i - 1]:
        i -= 1
    while j < hi - 1 and sm[j + 1] > n_sigma * sn[j + 1]:
        j += 1
    return i, j + 1


def _normalised(part: np.ndarray) -> np.ndarray:
    part = np.clip(np.asarray(part, dtype=float), 0.0, None)
    total = float(part.sum())
    return part / total if total > 0 else part


def _result(parts: Sequence[np.ndarray], source: str, text: str, info: dict | None = None) -> IrfResult:
    counts = tuple(float(np.clip(p, 0.0, None).sum()) for p in parts)
    return IrfResult(np.hstack([_normalised(p) for p in parts]), source, text, counts, dict(info or {}))


# -- scatter ------------------------------------------------------------------------------- #
def scatter_irf(
    counts: np.ndarray,
    *,
    buffer: np.ndarray | None = None,
    window: tuple[int, int] | None = None,
    floor_quantile: float = 0.1,
    n_sigma: float = 2.0,
) -> np.ndarray:
    """The IRF of a measured scatter decay (water, Ludox), corrected for its background.

    The buffer measurement (*buffer*, its counts scaled to the scatter's acquisition time), when
    there is one, is subtracted first: it carries the Raman line and the afterpulsing of the
    instrument, which are not the response. The flat floor left (dark counts) is the
    *floor_quantile* of the bins in *window*. The IRF is the contiguous peak standing above
    *n_sigma* times the Poisson noise; everything else is zero. Unnormalised counts.

    Parameters
    ----------
    counts : numpy.ndarray
        Micro-time histogram (counts) of the scatter measurement, one polarisation.
    buffer : numpy.ndarray, optional
        Histogram of the buffer measurement on the same bins, already scaled to *counts*' time.
    window : tuple of int, optional
        ``[start, stop)`` bins of the detector's gate (PIE): the peak searched there.
    floor_quantile : float
        Quantile of the gated bins taken as the flat background.
    n_sigma : float
        Noise multiple a bin must exceed to belong to the IRF.
    """
    raw = np.asarray(counts, dtype=float)
    lo, hi = _window(raw.size, window)
    d = raw - (np.asarray(buffer, dtype=float) if buffer is not None else 0.0)
    d = d - float(np.quantile(d[lo:hi], floor_quantile))
    noise = np.sqrt(np.clip(raw, 1.0, None))
    i, j = _peak_support(d, noise, lo, hi, n_sigma)
    out = np.zeros_like(d)
    out[i:j] = np.clip(d[i:j], 0.0, None)
    return out


def irf_from_scatter(
    parts: Sequence[np.ndarray],
    *,
    buffer: Sequence[np.ndarray] | None = None,
    window: tuple[int, int] | None = None,
    name: str = "scatter",
) -> IrfResult:
    """The IRF of a scatter measurement: :func:`scatter_irf` of each polarisation.

    *parts* are the polarisations (VV, VH) of the scatter's counts; *buffer* the buffer's counts
    on the same bins scaled to the scatter's time (``None``: the flat floor only).
    """
    buffer = list(buffer) if buffer is not None else [None] * len(parts)
    irfs = [scatter_irf(p, buffer=b, window=window) for p, b in zip(parts, buffer)]
    corrected = "buffer-corrected" if buffer[0] is not None else "floor-corrected"
    return _result(irfs, "scatter", f"scatter {name} ({corrected})", {"corrected": corrected})


# -- reference dye ------------------------------------------------------------------------- #
def reference_tail_lifetime(
    counts: np.ndarray,
    dt_ns: float,
    *,
    window: tuple[int, int] | None = None,
    skip_ns: float = 1.5,
    floor_quantile: float = 0.1,
) -> float | None:
    """The lifetime of a mono-exponential reference decay, from the slope of its tail.

    The tail starts *skip_ns* after the peak (past the IRF) and ends where the decay sinks into
    its floor (ten times the floor's noise, or 1 % of the peak); a straight line is fitted to the
    logarithm of the floor-free counts there, weighted by the counts. Use the magic-angle sum
    ``VV + 2 VH`` so the rotation of the dye does not bend the tail. The floor is taken as flat,
    which holds when the decay has died before the next pulse (a period of five lifetimes or
    more); a shorter period lifts the floor and shortens the result. ``None`` when the tail is
    shorter than five bins.
    """
    raw = np.asarray(counts, dtype=float)
    lo, hi = _window(raw.size, window)
    w = raw[lo:hi]
    floor = float(np.quantile(w, floor_quantile))
    d = w - floor
    peak = int(np.argmax(d))
    start = peak + max(1, int(round(float(skip_ns) / float(dt_ns))))
    limit = max(10.0 * np.sqrt(max(floor, 1.0)), 0.01 * d[peak])
    stop = start
    while stop < d.size and d[stop] > limit:
        stop += 1
    if stop - start < 5:
        return None
    x = np.arange(start, stop) * float(dt_ns)
    y = d[start:stop]
    slope = np.polyfit(x, np.log(y), 1, w=np.sqrt(y))[0]
    return float(-1.0 / slope) if slope < 0 else None


#: How far the lifetime a reference's tail gives may be from the dye database's before the
#: database's is taken as not this measurement's (5 %: Rh110's 4.02 ns against 4.0 is the same).
LIFETIME_TOLERANCE = 0.05


def reference_lifetime(
    vv: np.ndarray,
    vh: np.ndarray | None,
    dt_ns: float,
    listed_tau_ns: float | None,
    *,
    window: tuple[int, int] | None = None,
    tolerance: float = LIFETIME_TOLERANCE,
) -> tuple[float | None, dict[str, Any]]:
    """The one lifetime a reference dye's IRF is deconvolved with *and* its shifts calibrated at.

    The dye database's (*listed_tau_ns*) while the tail of ``VV + 2 VH``
    (:func:`reference_tail_lifetime`) agrees with it within *tolerance*; else the tail's, and the
    database's is said not to hold for this measurement (a buffer, a temperature or a
    conjugation the database's solvent value does not describe: Alexa 647 at 1.15 ns against
    1.0 ns). Deconvolving with one and fitting with the other is no calibration at all: on
    Alexa647_thick_1 that gave a reference fit of chi2_r 31 where either alone gives ~1.2-1.9.

    Returns
    -------
    tau : float or None
        ``None`` when neither is known.
    info : dict
        ``listed``, ``tail``, ``used``, ``how`` (``"listed"``, ``"from its tail"``) and
        ``consistent`` (``False``: the database's lifetime does not describe this dye here).
    """
    vv = np.asarray(vv, dtype=float)
    two = vh is not None and not np.array_equal(np.asarray(vh), vv)
    magic = vv + 2.0 * np.asarray(vh, dtype=float) if two else vv
    tail = reference_tail_lifetime(magic, dt_ns, window=window)
    listed = float(listed_tau_ns) if listed_tau_ns else None
    consistent = True
    if listed is None:
        used, how = tail, "from its tail"
    elif tail is None or abs(tail - listed) <= tolerance * listed or not 0.5 * listed < tail < 2.0 * listed:
        used, how = listed, "listed"
    else:
        used, how, consistent = tail, "from its tail", False
    return used, {"listed": listed, "tail": tail, "used": used, "how": how, "consistent": consistent}


def reference_anisotropy(
    vv: np.ndarray,
    vh: np.ndarray,
    g_factor: float,
    *,
    window: tuple[int, int] | None = None,
) -> float:
    """The anisotropy of a reference decay over its first 0.5 ns-ish (the peak and four bins
    after), ``r = (VV - G VH) / (VV + 2 G VH)`` above each polarisation's floor.

    A free dye excited by polarised light starts with ``r > 0``; a clearly negative one
    (below -0.05) says the VV and VH channels are swapped in the detector setup (RVZMT150's
    red pair read -0.12, swapped +0.14 decaying with 0.6 ns)."""
    vv, vh = np.asarray(vv, dtype=float), np.asarray(vh, dtype=float)
    lo, hi = _window(vv.size, window)
    a = vv[lo:hi] - float(np.quantile(vv[lo:hi], 0.1))
    b = vh[lo:hi] - float(np.quantile(vh[lo:hi], 0.1))
    peak = int(np.argmax(a + b))
    part = slice(peak, min(peak + 5, a.size))
    p, q = float(a[part].sum()), float(b[part].sum()) * float(g_factor)
    return (p - q) / (p + 2.0 * q) if p + 2.0 * q > 0 else 0.0


def polarised_kernels(
    n: int, dt_ns: float, tau_ns: float, rho_ns: float | None, r0: float = R0
) -> tuple[np.ndarray, np.ndarray]:
    """The decays of a rotating dye after a delta pulse, VV and VH, on *n* bins of *dt_ns*.

    ``VV = (1 + 2 r(t)) exp(-t / tau)``, ``VH = (1 - r(t)) exp(-t / tau)`` with
    ``r(t) = r0 exp(-t / rho)``; ``rho_ns=None`` (no rotation information, or one channel for
    both halves) gives the plain exponential to both.
    """
    n, dt = int(n), float(dt_ns)
    # A photon's bin minus its pulse's bin is the delay binned with a triangle, not a point:
    # both instants fall anywhere in their bins. Sampling the decay at the bin starts instead
    # overweights bin 0 -- at 64 ps bins and a 0.2 ns rotation that put the IRF 70 ps late.
    oversample = 32
    u = (np.arange(n * oversample) + 0.5) / oversample  # delays in bins
    left = np.floor(u).astype(int)
    frac = u - left

    def binned(rate: float) -> np.ndarray:
        f = np.exp(-rate * u * dt) * (dt / oversample)
        out = np.bincount(left, weights=f * (1.0 - frac), minlength=n + 1)
        out[1:] += np.bincount(left, weights=f * frac, minlength=n + 1)[:-1]
        return out[:n]

    decay = binned(1.0 / float(tau_ns))
    if rho_ns is None or rho_ns <= 0:
        return decay, decay.copy()
    rotating = float(r0) * binned(1.0 / float(tau_ns) + 1.0 / float(rho_ns))
    return decay + 2.0 * rotating, decay - rotating


def richardson_lucy(
    data: np.ndarray,
    kernel: np.ndarray,
    *,
    mask: np.ndarray | None = None,
    iterations: int | None = None,
    floor: float = 0.0,
    observed: np.ndarray | None = None,
    max_iterations: int = MAX_ITERATIONS,
) -> np.ndarray:
    """Richardson-Lucy deconvolution of *data* by a known, causal *kernel* (periodic).

    The same multiplicative update as the blind estimate's deconvolution
    (:class:`~chisurf.core.fluorescence.tcspc.irf_estimation.IRFEstimator`), with the kernel
    given rather than fitted. Bins outside *mask* (a detector's gate) carry no data: they do not
    vote in the update. Positive throughout.

    Where it stops is the regularisation: early, the estimate is smooth and too wide; late, it
    fits the noise. With *iterations* ``None`` it stops when the forward model (plus *floor*,
    the flat background taken off *data*) fits the *observed* counts (*data* + *floor* when not
    given; pass the raw counts when *data* was clipped at the floor) at their Poisson noise, reduced
    chi-square ``<= 1``, or stops improving (less than 0.1 % over 50 iterations),
    at most *max_iterations*: ~100 iterations for an IRF ten bins wide, ~700 for one of three.
    """
    y = np.clip(np.asarray(data, dtype=float), 0.0, None)
    m = np.ones_like(y) if mask is None else np.asarray(mask, dtype=float)
    k = np.asarray(kernel, dtype=float)
    k = k / k.sum()
    kf = np.fft.rfft(k, y.size)
    kt = np.conj(kf)  # correlation: the kernel reversed in time
    norm = np.fft.irfft(np.fft.rfft(m) * kt, y.size)
    norm = np.where(norm > 1e-12, norm, 1.0)
    x = np.full_like(y, max(float((y * m).sum()) / max(float(m.sum()), 1.0), 1e-12))
    inside = m > 0
    counts = (y + floor if observed is None else np.asarray(observed, dtype=float))[inside]
    target = 1.0  # a looser target (1 + sqrt(2/n)) stopped a three-bin IRF at TV 0.13 for 0.09
    history: list[float] = []
    for it in range(1, int(iterations or max_iterations) + 1):
        model = np.maximum(np.fft.irfft(np.fft.rfft(x) * kf, y.size), 1e-12)
        x = x * np.fft.irfft(np.fft.rfft(m * y / model) * kt, y.size) / norm
        np.clip(x, 0.0, None, out=x)
        if iterations is None and it % 10 == 0:
            fit = np.fft.irfft(np.fft.rfft(x) * kf, y.size)[inside] + floor
            chi2r = float(np.mean((counts - fit) ** 2 / np.maximum(fit, 1.0)))
            history.append(chi2r)
            if chi2r <= target or (len(history) > 5 and history[-6] - chi2r < 1e-3 * chi2r):
                break
    return x


def reference_irf(
    counts: np.ndarray,
    kernel: np.ndarray,
    *,
    window: tuple[int, int] | None = None,
    floor_quantile: float = 0.1,
    iterations: int | None = None,
    trim: float = REFERENCE_TRIM,
) -> np.ndarray:
    """The IRF in one polarisation of a reference decay, deconvolved from the dye's *kernel*.

    The flat floor (*floor_quantile* of the gated bins) is taken off, the rest deconvolved
    (:func:`richardson_lucy`, the gate as its mask), and the IRF kept from where it rises above
    *trim* of its peak to where it falls below it again. Counts (unnormalised).

    The exact difference ``D[i] - exp(-dt/tau) D[i-1]`` this replaces amplified the noise of
    every bin, and with the plain exponential on one polarisation it took the dye's rotation for
    part of the IRF: on a simulated Rh110 it cut 0.16 ns off the IRF's centre and biased a
    2.5 ns sample to 2.67 ns.
    """
    raw = np.asarray(counts, dtype=float)
    lo, hi = _window(raw.size, window)
    floor = float(np.quantile(raw[lo:hi], floor_quantile))
    y = np.clip(raw - floor, 0.0, None)
    # a gate that shows no decay (a green dye in the red detectors after the red pulse) has no
    # IRF to give: its strongest peak must stand clear of the noise, as a scatter's must
    # (measured against the gate's median: against the low floor quantile pure noise stands up)
    level = float(np.median(raw[lo:hi]))
    i, j = _peak_support(raw - level, np.sqrt(np.clip(raw, 1.0, None)), lo, hi, 2.0)
    if j - i < 2 or float((raw[i:j] - level).sum()) < 5.0 * np.sqrt(max(float(raw[i:j].sum()), 1.0)):
        return np.zeros_like(raw)
    mask = np.zeros(raw.size)
    mask[lo:hi] = 1.0
    x = richardson_lucy(
        y * mask, kernel[: raw.size], mask=mask, iterations=iterations, floor=floor, observed=raw
    )
    if not x[lo:hi].any():
        return np.zeros_like(raw)
    peak = lo + int(np.argmax(x[lo:hi]))
    level = float(trim) * x[peak]
    i = j = peak
    while i > lo and x[i - 1] > level:
        i -= 1
    while j < hi - 1 and x[j + 1] > level:
        j += 1
    out = np.zeros_like(x)
    out[i : j + 1] = x[i : j + 1]
    return out * (float(y[lo:hi].sum()) / max(float(out.sum()), 1e-12))


def _aligned_distance(a: np.ndarray, b: np.ndarray, dt_ns: float) -> float:
    """Total-variation distance of two IRF shapes once their centroids coincide."""
    a, b = _normalised(a), _normalised(b)
    if not a.any() or not b.any():
        return 1.0
    t = np.arange(a.size) * dt_ns
    shift = float((a * t).sum() - (b * t).sum())
    freq = np.fft.rfftfreq(b.size, d=dt_ns)
    moved = np.fft.irfft(np.fft.rfft(b) * np.exp(-2j * np.pi * freq * shift), b.size)
    return 0.5 * float(np.abs(a - _normalised(moved)).sum())


def reference_rotation(
    vv: np.ndarray,
    vh: np.ndarray,
    dt_ns: float,
    tau_ns: float,
    *,
    window: tuple[int, int] | None = None,
    r0: float = R0,
    bounds_ns: tuple[float, float] = (0.02, 3.0),
) -> float:
    """The dye's rotational correlation time, from its two polarisations.

    With the right ``rho`` the IRFs deconvolved from VV and VH with their polarised kernels have
    one shape; a wrong one leaves the rotation in one and takes it out of the other. The time
    minimising their distance (centroids aligned: the two detectors may sit at different delays)
    is returned. Recovers 0.12 / 0.20 / 0.40 ns within 0.04 ns on simulated Rh110, also with the
    VH response shifted and 10 % wider.
    """
    n = len(vv)

    def mismatch(log_rho: float) -> float:
        kv, kh = polarised_kernels(n, dt_ns, tau_ns, float(np.exp(log_rho)), r0)
        return _aligned_distance(
            reference_irf(vv, kv, window=window, iterations=100),
            reference_irf(vh, kh, window=window, iterations=100),
            dt_ns,
        )

    return float(np.exp(_golden(mismatch, np.log(bounds_ns[0]), np.log(bounds_ns[1]), 0.03)))


def _golden(f, a: float, b: float, tol: float) -> float:
    """The minimum of the unimodal *f* on ``[a, b]`` by golden-section search, to *tol*."""
    g = (np.sqrt(5.0) - 1.0) / 2.0
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    while b - a > tol:
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    return 0.5 * (a + b)


#: The initial anisotropies tried, below the ideal :data:`R0`, when a reference dye does not fit
#: with it (:func:`irf_from_reference`).
R0_STEPS = (0.3, 0.25, 0.2, 0.15, 0.1)


#: How many reference IRFs :func:`irf_from_reference` keeps (a hand-over needs one per dye and
#: detector pair; the oldest goes first).
REFERENCE_CACHE_SIZE = 32
_reference_cache: OrderedDict[tuple, IrfResult] = OrderedDict()
_reference_locks: dict[tuple, threading.Lock] = {}
_reference_guard = threading.Lock()


def _reference_key(vv, vh, dt_ns, kwargs: dict) -> tuple:
    """What an IRF of :func:`irf_from_reference` is a function of: the counts' content (not the
    arrays' identity -- each hand-over histograms the reference again) and every argument."""

    def digest(a) -> tuple:
        if a is None:
            return ()
        a = np.ascontiguousarray(a, dtype=float)
        return a.shape, hashlib.sha1(a.tobytes()).hexdigest()

    return (digest(vv), digest(vh), float(dt_ns), tuple(sorted(
        (k, tuple(v) if isinstance(v, (list, tuple)) else v) for k, v in kwargs.items())))


def _copied(result: IrfResult) -> IrfResult:
    return dataclasses.replace(result, irf=np.array(result.irf, dtype=float, copy=True),
                               info=copy.deepcopy(result.info))


def irf_from_reference(
    vv: np.ndarray,
    vh: np.ndarray | None,
    dt_ns: float,
    *,
    tau_ns: float | None = None,
    listed_tau_ns: float | None = None,
    rho_ns: float | None = None,
    window: tuple[int, int] | None = None,
    name: str = "reference dye",
    dye: str = "",
    r0: float = R0,
    g_factor: float | None = None,
    tau_how: str = "given",
) -> IrfResult:
    """The IRF from the decay of a reference dye with one known lifetime.

    The extraction (:func:`_irf_from_reference`: the rotation's search, the deconvolutions and
    the reference fits, seconds per dye) is a function of its inputs alone, so its result is kept
    by their content: a hand-over that histograms the same reference with the same setup, gate
    and binning again (Burst MLE prepares ahead of Next and again at it; a new setup re-reads the
    references) gets the same IRF back without extracting it again. Concurrent calls with the
    same inputs extract once. Each caller gets its own copy.
    """
    kwargs = dict(tau_ns=tau_ns, listed_tau_ns=listed_tau_ns, rho_ns=rho_ns, window=window,
                  name=name, dye=dye, r0=r0, g_factor=g_factor, tau_how=tau_how)
    key = _reference_key(vv, vh, dt_ns, kwargs)
    with _reference_guard:
        lock = _reference_locks.setdefault(key, threading.Lock())
    with lock:  # the same inputs on another thread: wait for its IRF rather than extract twice
        with _reference_guard:
            got = _reference_cache.get(key)
            if got is not None:
                _reference_cache.move_to_end(key)
        if got is None:
            got = _irf_from_reference(vv, vh, dt_ns, **kwargs)
            with _reference_guard:
                _reference_cache[key] = _copied(got)
                while len(_reference_cache) > REFERENCE_CACHE_SIZE:
                    _reference_cache.popitem(last=False)
    with _reference_guard:
        if _reference_locks.get(key) is lock and not lock.locked():
            _reference_locks.pop(key, None)
    return _copied(got)


def _irf_from_reference(
    vv: np.ndarray,
    vh: np.ndarray | None,
    dt_ns: float,
    *,
    tau_ns: float | None = None,
    listed_tau_ns: float | None = None,
    rho_ns: float | None = None,
    window: tuple[int, int] | None = None,
    name: str = "reference dye",
    dye: str = "",
    r0: float = R0,
    g_factor: float | None = None,
    tau_how: str = "given",
) -> IrfResult:
    """The IRF from the decay of a reference dye with one known lifetime (uncached; the public
    entry is :func:`irf_from_reference`).

    Parameters
    ----------
    vv, vh : numpy.ndarray
        The dye's counts in each polarisation, one period. *vh* ``None`` (or the same channel as
        *vv*): one polarisation, deconvolved with the plain exponential.
    dt_ns : float
        Width of one bin.
    tau_ns : float, optional
        The dye's lifetime. ``None``: fitted to the tail of ``VV + 2 VH``
        (:func:`reference_tail_lifetime`), the *listed_tau_ns* when that fails or lands farther
        than a factor two from it.
    rho_ns : float, optional
        Rotational correlation time. ``None``: from the data (:func:`reference_rotation`).
    r0 : float
        The initial anisotropy the kernels start from.
    tau_how : str
        How a given *tau_ns* was decided, for the source line (:func:`reference_lifetime`'s
        ``"listed"`` / ``"from its tail"``).
    g_factor : float, optional
        The detector pair's G (an estimate independent of this fit: Data Selection's tail
        ratio). Given, with the rotation taken from the data, the dye is fitted with the burst
        model (:func:`reference_fit`) at that G; when that fit is poor (chi2_r > 2) the initial
        anisotropy is taken from the data too: the *r0* of :data:`R0_STEPS` (each with its own
        rotation and IRF) whose fit is best. A dye such as Alexa 647 starts below the ideal
        0.38 -- on Alexa647_thick_1 r0 0.15, rho 0.99 ns give chi2_r 1.2 at the tail-ratio G,
        0.38 gave 16 -- and the deconvolution would otherwise put the missing anisotropy into
        the IRF.
    window : tuple of int, optional
        The detector's gate ``[start, stop)`` in bins.
    name, dye : str
        The file(s) and the dye, for the source line.
    """
    vv = np.asarray(vv, dtype=float)
    two = vh is not None and not np.array_equal(np.asarray(vh), vv)
    vh = np.asarray(vh, dtype=float) if vh is not None else vv
    how = str(tau_how or "given")
    if tau_ns is None:
        magic = vv + 2.0 * vh if two else vv
        tau_ns = reference_tail_lifetime(magic, dt_ns, window=window)
        if listed_tau_ns is not None and (tau_ns is None or not 0.5 * listed_tau_ns < tau_ns < 2.0 * listed_tau_ns):
            tau_ns, how = float(listed_tau_ns), "listed"
        elif tau_ns is None:
            return _result([np.zeros_like(vv)] * (2 if two else 1), "reference", f"{name}: no tail to fit")
        else:
            how = "from its tail"
    rotation = ""
    fit_chi2r = None
    if two:
        from_data = rho_ns is None

        def deconvolved(r0_: float, rho_: float | None):
            rho_ = reference_rotation(vv, vh, dt_ns, tau_ns, window=window, r0=r0_) if rho_ is None else rho_
            kv_, kh_ = polarised_kernels(vv.size, dt_ns, tau_ns, rho_, r0_)
            return rho_, [reference_irf(vv, kv_, window=window), reference_irf(vh, kh_, window=window)]

        def quality(r0_: float, rho_: float, parts_) -> float:
            if not all(np.any(p) for p in parts_):
                return np.inf
            return reference_fit([vv, vh], [_normalised(p) for p in parts_], dt_ns, tau_ns=tau_ns,
                                 rho_ns=rho_, r0=r0_, g_factor=g_factor, window=window).chi2r

        rho_ns, parts = deconvolved(r0, rho_ns)
        if from_data and g_factor is not None:
            fit_chi2r = quality(r0, rho_ns, parts)
            if fit_chi2r > 2.0:
                trials = [(fit_chi2r, r0, rho_ns, parts)]
                for step in R0_STEPS:
                    if step < r0:
                        rho_s, parts_s = deconvolved(step, None)
                        trials.append((quality(step, rho_s, parts_s), step, rho_s, parts_s))
                fit_chi2r, r0, rho_ns, parts = min(trials, key=lambda t: t[0])
        if from_data:
            rotation = f", rotation {rho_ns:.2f} ns" + ("" if r0 == R0 else f", r0 {r0:.2f}") + " from the data"
        else:
            rotation = f", rotation {rho_ns:.2f} ns"
    else:
        kv, _ = polarised_kernels(vv.size, dt_ns, tau_ns, None)
        parts = [reference_irf(vv, kv, window=window)]
        if vh is vv or np.array_equal(vh, vv):
            parts = parts * 2
    # The IRF's area is the excitations the decay stands on: its floor-free counts times
    # 1 - exp(-dt / tau) (what the exact difference D[i] - a D[i-1] sums to), the measure a
    # caller's quality bar (Burst MLE: 500) was set on.
    parts = [p * (1.0 - np.exp(-float(dt_ns) / float(tau_ns))) for p in parts]
    label = f"{dye}, " if dye else ""
    text = f"{name} ({label}{tau_ns:.2f} ns {how}{rotation}, deconvolved)"
    return _result(
        parts, "reference", text,
        {"tau_ns": float(tau_ns), "tau_how": how, "rho_ns": rho_ns, "r0": float(r0), "dye": dye,
         "fit_chi2r": fit_chi2r},
    )


# -- non-burst prompt ---------------------------------------------------------------------- #
def gaussian_prompt(prompt: np.ndarray, shape: float = 0.0) -> np.ndarray:
    """Fit a (skew-)Gaussian to a measured scatter prompt.

    A baseline-subtracted non-burst micro-time histogram is *not* an IRF: its
    prompt rides on a slow fluorescent tail, because the non-burst periods still
    hold dim and passing molecules, and a flat baseline subtraction removes the
    dark counts while leaving that decay in place. Convolving a lifetime model
    with such a "IRF" biases the recovered lifetime roughly two-fold short — a
    genuine ~2.2 ns decay came out ~1.1 ns on real BH smFRET data — and moves the
    prompt's own first moment several nanoseconds late.

    A Gaussian cannot represent a slow tail, which is exactly why it is the right
    shape here: least-squares fitting one over a window around the peak locks onto
    the sharp scatter prompt and leaves the fluorescent artifact behind, while
    still following the measured position and width. Falls back to the analytic
    peak/FWHM pulse if the fit fails.

    Parameters
    ----------
    prompt : numpy.ndarray
        Baseline-subtracted non-burst micro-time histogram.
    shape : float
        Skewness. ``0`` is a symmetric Gaussian; positive values add the right
        tail a real detector response has.

    Returns
    -------
    numpy.ndarray
        The fitted pulse, scaled to the prompt's total counts.
    """
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    prompt = np.asarray(prompt, dtype=np.float64)
    if prompt.size == 0 or float(prompt.max()) <= 0.0:
        return prompt

    pk = int(prompt.argmax())
    peak_val = float(prompt[pk])

    # Width from the *rising* edge only, mirrored. The falling side of a non-burst
    # histogram is the fluorescence decay, not the instrument, so a two-sided
    # half-max reads the decay's width and opens a fit window wide enough for the
    # tail to drag the Gaussian late again (2.5 ns against a true 1.0). The rise is
    # instrument-limited either way, and for a clean scatter prompt the two sides
    # agree, so this changes nothing where the old estimate was already right.
    #
    # The walk tolerates a short dip below half rather than stopping at the first
    # one. On a sparse non-burst stream — a few counts per bin — a single Poisson
    # dip inside the rise otherwise ends the walk immediately, the window collapses
    # to its floor, and the fit locks onto one noisy bin. Smoothing would fix that
    # too, and must not be used: the prompt is the sharpest feature in the
    # histogram, so any kernel wide enough to bridge the dip also broadens the
    # width being measured and pulls the window back into the decay.
    half = 0.5 * peak_val
    lo, run = pk, 0
    while lo > 0 and run < 2:
        lo -= 1
        run = 0 if prompt[lo] >= half else run + 1
    fwhm = max(1.0, 2.0 * float(pk - lo - run))
    sigma0 = fwhm / 2.3548
    x = np.arange(prompt.size, dtype=np.float64)
    # Fit the leading edge, not a symmetric window. Everything to the right of the
    # peak is prompt *plus* decay, and a window wide enough to hold the prompt's
    # own right flank also holds enough decay to drag the Gaussian late (0.6 ns on
    # a well-resolved 0.24 ns prompt). The rise is instrument-only — the decay is
    # flat across it — so it fixes the centre and the width on its own, and one
    # half-width past the peak is kept so the fit is not extrapolating the top.
    hw = max(1, pk - lo)
    sl = slice(max(0, pk - 3 * hw), min(prompt.size, pk + hw + 1))
    xw, yw = x[sl], prompt[sl]
    weights = np.sqrt(np.maximum(yw, 1.0))  # Poisson counting weights

    def _gauss(xx, amp, mu, sig):
        return amp * np.exp(-0.5 * ((xx - mu) / sig) ** 2)

    def _skew_gauss(xx, amp, mu, sig, alpha):
        from chisurf.core.math.special import erf

        z = (xx - mu) / sig
        return amp * np.exp(-0.5 * z * z) * (1.0 + erf(alpha * z / np.sqrt(2.0)))

    g = None
    try:
        from chisurf.core.math.numerics import curve_fit

        if shape != 0.0:
            popt, _ = curve_fit(
                _skew_gauss, xw, yw, p0=[peak_val, float(pk), sigma0, shape],
                sigma=weights, absolute_sigma=False, maxfev=5000,
            )
            g = _skew_gauss(x, 1.0, popt[1], abs(popt[2]), popt[3])
        else:
            popt, _ = curve_fit(
                _gauss, xw, yw, p0=[peak_val, float(pk), sigma0],
                sigma=weights, absolute_sigma=False, maxfev=5000,
            )
            g = _gauss(x, 1.0, popt[1], abs(popt[2]))
    except Exception:
        g = None
    if g is None or not np.all(np.isfinite(g)) or float(np.sum(g)) <= 0.0:
        # Fall back to the analytic pulse at the measured peak / FWHM.
        g = synthetic_irf(x, center_ns=float(pk), fwhm_ns=fwhm, shape=shape, norm=True)

    # Normalise to the prompt's counts so downstream scaling is unchanged.
    s = float(g.sum())
    return g * (float(prompt.sum()) / s) if s > 0 else g


#: The shapes :func:`irf_from_prompt` fits, by the names the windows offer.
PROMPT_MODELS = {"gaussian": 0.0, "skewed": 1.5, "skewed_gaussian": 1.5, "experimental": None, "raw": None}


def irf_from_prompt(
    parts: Sequence[np.ndarray],
    *,
    model: str = "gaussian",
    shape: float | None = None,
    window: tuple[int, int] | None = None,
    baseline_quantile: float | None = None,
    name: str = "photons outside the bursts",
) -> IrfResult:
    """The IRF from a scatter prompt on a fluorescent tail (the non-burst photons).

    *parts* are the polarisations' histograms. With *baseline_quantile* the flat floor (that
    quantile of the gated bins) is taken off first; without, they are already floor-free.
    ``model`` ``"gaussian"`` / ``"skewed"`` fits that pulse to the prompt's rising edge
    (:func:`gaussian_prompt`), which leaves the tail behind; ``"experimental"`` keeps the prompt
    as measured. *shape* overrides the model's skewness.
    """
    key = str(model).lower()
    if key not in PROMPT_MODELS:
        raise ValueError(f"unknown IRF model {model!r}: {sorted(PROMPT_MODELS)}")
    skew = PROMPT_MODELS[key] if shape is None or PROMPT_MODELS[key] is None else float(shape)
    out = []
    for part in parts:
        part = np.asarray(part, dtype=float)
        lo, hi = _window(part.size, window)
        inside = np.zeros(part.size, dtype=bool)
        inside[lo:hi] = True
        prompt = np.where(inside, part, 0.0)
        if baseline_quantile is not None and prompt.any():
            floor = float(np.quantile(part[inside], float(np.clip(baseline_quantile, 0.0, 1.0))))
            prompt = np.where(inside, np.clip(part - floor, 0.0, None), 0.0)
        if not prompt.any() or skew is None:
            out.append(prompt)
        else:
            out.append(gaussian_prompt(prompt, skew))
    label = {"gaussian": "gaussian", "experimental": "experimental", "raw": "experimental"}.get(key, "skewed gaussian")
    return _result(out, "non_burst", f"{name} ({label})", {"model": key})


# -- blind --------------------------------------------------------------------------------- #
def irf_from_decay(
    parts: Sequence[np.ndarray],
    *,
    window: tuple[int, int] | None = None,
    name: str = "the burst decay",
    trim_shape: float | None = 1.5,
) -> IrfResult:
    """The IRF estimated from a fluorescence decay alone (blind), the last resort.

    The blind estimate (truncated exponential fit + Richardson-Lucy, :func:`.estimation.blind_irf`
    via the tool's compiled engine) of each polarisation in *window*. What a multi-exponential
    sample leaves of its decay in that estimate is shed by fitting a skewed Gaussian of
    skewness *trim_shape* to its prompt (``None``: kept as estimated).
    """
    from chisurf.core.fluorescence.tcspc import IRFEstimator

    out = []
    for decay in parts:
        decay = np.asarray(decay, dtype=float)
        lo, hi = _window(decay.size, window)
        estimate = np.zeros(decay.size)
        if decay[lo:hi].sum() > 0:
            run = IRFEstimator(decay[lo:hi].reshape(-1, 1), dt=1.0).run()[:, 0]
            estimate[lo:hi] = np.clip(run, 0.0, None)
            if trim_shape is not None and estimate.any():
                estimate = gaussian_prompt(estimate, trim_shape)
        out.append(estimate)
    shaped = "blind estimate, skewed Gaussian" if trim_shape is not None else "blind estimate"
    return _result(out, "blind", f"{name} ({shaped})")


# -- choice -------------------------------------------------------------------------------- #
#: Which source an automatic choice takes first (owner's choice, 2026-11-04): a reference dye --
#: measured in the same conditions as the sample, its IRF recovered by deconvolution -- then a
#: scatter measurement, then the photons outside the bursts, then the blind estimate. Every
#: consumer's "Auto" follows this one order (:func:`best_irf`, Burst MLE's IRF selector).
AUTO_ORDER = ("reference", "scatter", "non_burst", "blind")


def best_irf(results: Iterable[IrfResult | None], min_counts: float = 0.0) -> IrfResult | None:
    """The best of several extractions, in :data:`AUTO_ORDER`: a reference dye before a scatter;
    of several of one kind, the one with the most counts in its weaker polarisation; ``None``
    when none has *min_counts* in both."""
    usable = [r for r in results if r is not None and r.counts and min(r.counts) >= min_counts]
    if not usable:
        return None
    rank = {kind: i for i, kind in enumerate(AUTO_ORDER)}
    return min(usable, key=lambda r: (rank.get(r.source, len(rank)), -min(r.counts)))


# -- time-shift calibration ------------------------------------------------------------------ #
@dataclass
class ShiftCalibration:
    """The IRF's time shift against a reference dye's decay, per polarisation, in bins.

    ``shift_vv`` / ``shift_vh`` move the IRF the way a fit moves it (linear interpolation of the
    fraction, :func:`chisurf.core.fluorescence.mle.irf.interpolate_shift`): positive is later.
    ``tau_ns`` is the lifetime the fit used -- the dye's known one (``tau_known``) or fitted.
    """

    shift_vv: float
    shift_vh: float
    tau_ns: float
    tau_known: bool
    rho_ns: float | None
    deviance: float
    text: str = ""
    info: dict[str, Any] = field(default_factory=dict)
    #: The dye's decay fitted with the burst model at the calibrated shifts (:func:`reference_fit`):
    #: what tells whether the IRF, G, l1, l2 and the rotation describe the reference.
    fit: ReferenceFit | None = None


def _decay_model(irf: np.ndarray, kernel: np.ndarray, shift: float) -> np.ndarray:
    from chisurf.core.fluorescence.mle.irf import interpolate_shift

    moved = interpolate_shift(np.clip(np.asarray(irf, dtype=float), 0.0, None), shift)
    n = moved.size
    return np.fft.irfft(np.fft.rfft(moved) * np.fft.rfft(kernel[:n], n), n)


def _poisson_fit(data: np.ndarray, shape: np.ndarray, mask: np.ndarray) -> float:
    """Poisson deviance of ``a * shape + b`` fitted to *data* in *mask* (a, b >= 0, by a few
    Newton steps on the likelihood from the least-squares start)."""
    y, f = data[mask], shape[mask]
    if f.sum() <= 0:
        return np.inf
    A = np.vstack([f, np.ones_like(f)]).T
    w = 1.0 / np.maximum(y, 1.0)
    a, b = np.linalg.lstsq(A * np.sqrt(w)[:, None], y * np.sqrt(w), rcond=None)[0]
    a, b = max(a, 1e-12), max(b, 1e-9)
    for _ in range(20):
        m = np.maximum(a * f + b, 1e-12)
        r = y / m - 1.0
        g = np.array([np.dot(r, f), r.sum()])
        h = np.array([[np.dot(y / m**2, f * f), np.dot(y / m**2, f)], [np.dot(y / m**2, f), (y / m**2).sum()]])
        try:
            step = np.linalg.solve(h + 1e-12 * np.eye(2), g)
        except np.linalg.LinAlgError:
            break
        a, b = max(a + step[0], 1e-12), max(b + step[1], 1e-9)
        if np.all(np.abs(step) < 1e-9 * (1 + np.abs([a, b]))):
            break
    m = np.maximum(a * f + b, 1e-12)
    with np.errstate(divide="ignore", invalid="ignore"):
        term = np.where(y > 0, y * np.log(y / m), 0.0)
    return float(2.0 * np.sum(term - (y - m)))


def _best_shift(data, irf, kernel, mask, max_shift: float) -> tuple[float, float]:
    """The shift minimising the deviance: a grid of quarter bins, then golden section."""
    grid = np.arange(-max_shift, max_shift + 1e-9, 0.25)
    scores = [_poisson_fit(data, _decay_model(irf, kernel, s), mask) for s in grid]
    k = int(np.argmin(scores))
    lo, hi = grid[max(0, k - 1)], grid[min(len(grid) - 1, k + 1)]
    best = _golden(lambda s: _poisson_fit(data, _decay_model(irf, kernel, s), mask), lo, hi, 0.01)
    return float(best), _poisson_fit(data, _decay_model(irf, kernel, best), mask)


def calibrate_shifts(
    parts: Sequence[np.ndarray],
    irf_parts: Sequence[np.ndarray],
    dt_ns: float,
    *,
    tau_ns: float | None = None,
    rho_ns: float | None = None,
    window: tuple[int, int] | None = None,
    max_shift: float = 5.0,
    name: str = "reference dye",
    g_factor: float | None = None,
    l1: float = 0.0,
    l2: float = 0.0,
    fit_model: bool = True,
    r0: float = R0,
) -> ShiftCalibration:
    """The time shift of the IRF against a reference dye's decay, VV and VH on their own.

    The dye's decay is fitted with the IRF convolved with its polarised exponential
    (:func:`polarised_kernels`), an amplitude and a flat background per polarisation, the
    shift free and the lifetime **fixed** to *tau_ns* (the dye database's). Without a known
    lifetime it is fitted too (the shift and the lifetime trade off a little: said in ``text``).
    What the shift absorbs: the different delays of the IRF's and the dye's measurements --
    detector count rate, pile-up, a cable or a filter between them -- which a burst fit would
    otherwise take into its lifetime.

    Parameters
    ----------
    parts, irf_parts : sequence of numpy.ndarray
        The dye's counts and the IRF, VV then VH (or one polarisation), on the same bins.
    dt_ns : float
        Bin width.
    tau_ns, rho_ns : float, optional
        The dye's lifetime and rotational correlation time (``None``: fitted / no rotation).
    window : tuple of int, optional
        ``[start, stop)`` bins the fit sees (the detector's gate).
    max_shift : float
        The largest shift searched, bins.
    g_factor, l1, l2 : float, optional
        The detector's polarisation factors (``g_factor`` ``None``: fitted). With *fit_model* the
        shifts each polarisation gives on its own are refined by fitting both together with the
        burst model (:func:`reference_fit`), which is kept on :attr:`ShiftCalibration.fit`.
    r0 : float
        The dye's initial anisotropy (the one its IRF was deconvolved with).
    """
    parts = [np.asarray(p, dtype=float) for p in parts]
    irf_parts = [np.asarray(p, dtype=float) for p in irf_parts]
    n = parts[0].size
    lo, hi = _window(n, window)
    mask = np.zeros(n, dtype=bool)
    mask[lo:hi] = True
    two = len(parts) > 1 and not np.array_equal(parts[0], parts[1])
    known = tau_ns is not None and tau_ns > 0

    def fit(tau: float) -> tuple[list[float], float]:
        kv, kh = polarised_kernels(n, dt_ns, tau, rho_ns if two else None, r0)
        out, total = [], 0.0
        for data, irf, kernel in zip(parts, irf_parts, (kv, kh)):
            s, d = _best_shift(data, irf, kernel, mask, max_shift)
            out.append(s)
            total += d
        return out, total

    if known:
        tau = float(tau_ns)
    else:
        magic = parts[0] + 2.0 * parts[1] if two else parts[0]
        start = reference_tail_lifetime(magic, dt_ns, window=window) or 2.0
        tau = float(np.exp(_golden(lambda lt: fit(float(np.exp(lt)))[1], np.log(start / 2), np.log(start * 2), 0.01)))
    shifts, deviance = fit(tau)
    if len(shifts) == 1:
        shifts = shifts * 2
    how = "known" if known else "fitted (no lifetime in the dye database)"
    joint = None
    if fit_model:
        joint = reference_fit(
            parts if two else parts[:1], irf_parts if two else irf_parts[:1], dt_ns,
            tau_ns=tau, rho_ns=rho_ns if two else None, r0=r0, g_factor=g_factor, l1=l1, l2=l2,
            window=window, shifts=shifts,
        )
        shifts = [joint.shift_vv, joint.shift_vh]
    text = (
        f"shift VV {shifts[0]:+.2f}, VH {shifts[1]:+.2f} bins against {name} "
        f"(lifetime {tau:.2f} ns {how})"
    )
    if joint is not None:
        text += "; " + joint.text
    return ShiftCalibration(
        shifts[0], shifts[1], tau, known, rho_ns, deviance, text,
        {"name": name, "window": (lo, hi), "dt_ns": float(dt_ns)}, joint,
    )


# -- the reference dye fitted with the burst model ------------------------------------------- #
@dataclass
class ReferenceFit:
    """A reference dye's decay fitted with the IRF and the model a burst fit uses.

    ``data`` and ``model`` are ``VV | VH`` (or one polarisation) on the full axis; ``residuals``
    the weighted residuals ``(data - model) / sqrt(model)``, NaN outside the window; ``chi2r``
    their reduced chi-square with the polarisation factors the caller gave (the setup's: what the
    bursts are fitted with). ``g_fitted`` / ``chi2r_g_free`` are the same fit with G free -- the
    G the reference itself asks for.
    """

    data: np.ndarray
    model: np.ndarray
    residuals: np.ndarray
    chi2r: float
    shift_vv: float
    shift_vh: float
    g_factor: float
    g_fitted: float
    chi2r_g_free: float
    tau_ns: float
    rho_ns: float | None
    window: tuple[int, int]
    background: tuple[float, ...] = ()
    text: str = ""


def _reference_model(params, irfs, dt_ns, tau, rho, r0, l1, l2, n, g):
    """``A (IRF(shift) * kernel) + flat`` per polarisation, the kernels of Fit23's physics:
    ``VV = e^-t/tau + r0 (2 - 3 l1) e^-t/tau e^-t/rho``,
    ``VH = (e^-t/tau + r0 (3 l2 - 1) e^-t/tau e^-t/rho) / G``, binned like photons."""
    from chisurf.core.fluorescence.mle.irf import interpolate_shift

    plain, _ = polarised_kernels(n, dt_ns, tau, None)
    if rho is not None and rho > 0 and len(irfs) > 1:
        rotating, _ = polarised_kernels(n, dt_ns, 1.0 / (1.0 / tau + 1.0 / rho), None)
        kernels = (plain + r0 * (2.0 - 3.0 * l1) * rotating, (plain + r0 * (3.0 * l2 - 1.0) * rotating) / g)
    else:
        kernels = (plain, plain / g)
    amplitude, flats, shifts = params[0], params[1 : 1 + len(irfs)], params[1 + len(irfs) :]
    return [
        amplitude * np.fft.irfft(np.fft.rfft(interpolate_shift(irf, s)) * np.fft.rfft(k, n), n) + b
        for irf, k, b, s in zip(irfs, kernels, flats, shifts)
    ]


def reference_fit(
    parts: Sequence[np.ndarray],
    irf_parts: Sequence[np.ndarray],
    dt_ns: float,
    *,
    tau_ns: float,
    rho_ns: float | None = None,
    r0: float = R0,
    g_factor: float | None = None,
    l1: float = 0.0,
    l2: float = 0.0,
    window: tuple[int, int] | None = None,
    shifts: Sequence[float] = (0.0, 0.0),
    hold_shifts: bool = False,
) -> ReferenceFit:
    """Fit a reference dye's decay with its IRF and the burst fit's polarised model.

    One amplitude for both polarisations, a flat background each, the IRF's time shift of each
    free (with *hold_shifts*: held at *shifts* -- how well shifts set by hand describe the
    reference); the lifetime *tau_ns* (the dye database's), the rotation *rho_ns*, *r0* and the
    polarisation factors fixed. Everything a burst fit takes for granted is tested at once: an
    IRF that is too narrow or late shows at the rise, a wrong G or l1/l2 as VV and VH pulling
    apart, a wrong rotation in the first nanosecond. Fitted by least squares with Neyman weights;
    the reported chi-square uses the model's Poisson variance (as a burst fit's residuals do).
    With *g_factor* ``None`` G is free; otherwise the fit is also repeated with G free
    (:attr:`ReferenceFit.g_fitted`), the G this reference asks for.
    """
    from chisurf.core.math.numerics import least_squares

    data = [np.asarray(p, dtype=float) for p in parts]
    irfs = [np.clip(np.asarray(p, dtype=float), 0.0, None) for p in irf_parts]
    n, k = data[0].size, len(data)
    lo, hi = _window(n, window)
    weights = [1.0 / np.sqrt(np.maximum(d[lo:hi], 1.0)) for d in data]
    floor = [max(float(np.quantile(d[lo:hi], 0.05)), 0.0) for d in data]
    shape = _reference_model([1.0] + [0.0] * k + list(shifts[:k]), irfs, dt_ns, tau_ns, rho_ns, r0, l1, l2, n,
                             g_factor or 1.0)
    amplitude = float(sum(d[lo:hi].sum() for d in data) / max(sum(s[lo:hi].sum() for s in shape), 1e-12))

    def solve(g_free: bool, g0: float, at=None):
        def residuals(p):
            g = p[-1] if g_free else g0
            model = _reference_model(p[: 1 + 2 * k], irfs, dt_ns, tau_ns, rho_ns, r0, l1, l2, n, g)
            return np.hstack([(d[lo:hi] - m[lo:hi]) * w for d, m, w in zip(data, model, weights)])

        start = list(shifts[:k]) if at is None else list(at)
        x0 = [amplitude] + floor + start + ([g0] if g_free else [])
        # shifts free, or held (within 1e-4 bin) at the ones the G-free fit found
        low_s, high_s = ([-5.0] * k, [5.0] * k) if at is None else ([v - 1e-4 for v in at], [v + 1e-4 for v in at])
        lower = [0.0] + [0.0] * k + low_s + ([0.05] if g_free else [])
        upper = [np.inf] + [np.inf] * k + high_s + ([20.0] if g_free else [])
        x = np.asarray(least_squares(residuals, np.asarray(x0, float), bounds=(lower, upper)).x)
        g = float(x[-1]) if g_free else g0
        model = _reference_model(x[: 1 + 2 * k], irfs, dt_ns, tau_ns, rho_ns, r0, l1, l2, n, g)
        res = [np.full(n, np.nan) for _ in data]
        for r, d, m in zip(res, data, model):
            r[lo:hi] = (d[lo:hi] - m[lo:hi]) / np.sqrt(np.maximum(m[lo:hi], 1e-12))
        flat = np.hstack([r[lo:hi] for r in res])
        chi2r = float(np.sum(flat * flat) / max(flat.size - len(x0), 1))
        return x, g, model, res, chi2r

    two = k > 1
    held = [float(s) for s in shifts[:k]] if hold_shifts else None
    # The shifts come from the fit with G free: a G the setup has wrong must show as a bad fit,
    # not be absorbed into the IRF's timing.
    free = solve(True, float(g_factor or 1.0), at=held) if two else None
    if g_factor is None and two:
        x, g, model, res, chi2r = free
    elif two:
        x, g, model, res, chi2r = solve(False, float(g_factor), at=free[0][1 + k : 1 + 2 * k])
    else:
        x, g, model, res, chi2r = solve(False, float(g_factor or 1.0), at=held)
    g_fitted, chi2r_free = (free[1], free[4]) if free is not None else (g, chi2r)
    shift_vv = float(x[1 + k])
    shift_vh = float(x[1 + k + 1]) if two else shift_vv
    text = f"reference fit chi2_r {chi2r:.2f} (lifetime {tau_ns:.2f} ns fixed"
    if two:
        text += f", G {g:.3f}" + ("" if g_factor is None else f"; G free {g_fitted:.3f}: chi2_r {chi2r_free:.2f}")
    text += ")"
    return ReferenceFit(
        np.hstack(data), np.hstack(model), np.hstack(res), chi2r, shift_vv, shift_vh, g, float(g_fitted),
        float(chi2r_free), float(tau_ns), rho_ns, (lo, hi), tuple(float(b) for b in x[1 : 1 + k]), text,
    )
