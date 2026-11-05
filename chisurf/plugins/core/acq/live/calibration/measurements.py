"""Measured-quantity estimators for the calibration workflows.

Every function computes a *value* from data the user measured and returns
``(value, detail)``: the value is ``None`` when the estimator cannot honestly
run, and ``detail`` then says exactly why (which input is missing, which window
is degenerate). Nothing here judges the value -- accept/reject limits are the
user's, configured on the workflow's metrics, never shipped.

Formulas and their grounding:

* **IRF full width at half maximum** -- linear interpolation of the half-maximum
  crossings around the histogram peak.
* **Tail lifetime** -- counts-weighted (Poisson, ``w = sqrt(n)``) log-linear
  least-squares single-exponential fit over the user's tail window. A
  first-order estimator: a reconvolution fit against the measured IRF is the
  proper analysis, and its value can be entered alongside.
* **PIE gamma** -- from one doubly-labelled sample with 1:1 stoichiometry
  (Müller et al., *Biophys. J.* 2005, DOI 10.1529/biophysj.105.064766): the
  sensitized acceptor emission and the directly excited acceptor emission share
  the same detection channel and acceptor brightness, so the transfer
  efficiency follows from their ratio and the detection correction follows as
  ``gamma = (F_AA - F_AD) / F_DD``. The input names and the correction factors
  alpha (donor leakage), delta (direct acceptor excitation) and beta
  (excitation normalisation) follow Hellenkamp et al., *Nat. Methods* 2018,
  DOI 10.1038/s41592-018-0085-0.
* **Polarisation factor G** -- inverting the measured anisotropy model
  ``r = (I_par - G I_perp) / (I_par + 2 G I_perp)`` for an assumed true
  anisotropy (``r = 0`` for a fast-rotating reference dye).

The power-diode conversion (reference points, dark offset, the reported
linearity fit and the bounded interpolation) lives in
:mod:`chisurf.plugins.core.acq.live.power_calibration`; this module does not
duplicate it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np

__all__ = [
    "apparent_anisotropy",
    "background_rate_khz",
    "g_factor",
    "irf_fwhm_ns",
    "load_histogram",
    "microtime_histogram",
    "pie_gamma",
    "tail_lifetime_ns",
]

#: TTTR suffixes the microtime-histogram helper reads through tttrlib.
TTTR_SUFFIXES = {".ptu", ".ht3", ".pt3", ".spc", ".sdt", ".bin"}


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# -- the water IRF ------------------------------------------------------------------------------

def irf_fwhm_ns(hist, bin_ns) -> tuple[float | None, str]:
    """Full width at half maximum of a microtime histogram, in ns."""
    bin_ns = _number(bin_ns)
    if bin_ns is None or bin_ns <= 0:
        return None, "the micro time resolution must be a positive number of ns"
    h = np.asarray(hist, dtype=float)
    if h.size < 3:
        return None, "the histogram is empty"
    peak = int(np.argmax(h))
    if h[peak] <= 0:
        return None, "the histogram has no counts"
    if peak in (0, h.size - 1):
        return None, (
            "the peak sits at the edge of the histogram; record a longer microtime window"
        )
    half = h[peak] / 2.0

    def _cross(i_out: int, i_in: int) -> float:
        h0, h1 = h[i_out], h[i_in]
        if h1 == h0:
            return float(i_in)
        return i_out + (half - h0) / (h1 - h0) * (i_in - i_out)

    left = peak
    while left > 0 and h[left] > half:
        left -= 1
    right = peak
    while right < h.size - 1 and h[right] > half:
        right += 1
    fwhm_bins = _cross(right, right - 1) - _cross(left, left + 1)
    fwhm = float(fwhm_bins * bin_ns)
    return (
        fwhm,
        f"FWHM {fwhm:.3f} ns: half-maximum crossings around bin {peak} ({h[peak]:.0f} counts)",
    )


# -- the tail lifetime --------------------------------------------------------------------------

def tail_lifetime_ns(hist, bin_ns, *, start_ns, stop_ns) -> tuple[float | None, str]:
    """Counts-weighted log-linear single-exponential tail fit over a window."""
    bin_ns = _number(bin_ns)
    start, stop = _number(start_ns), _number(stop_ns)
    if bin_ns is None or bin_ns <= 0:
        return None, "the micro time resolution must be a positive number of ns"
    if start is None or stop is None or not stop > start:
        return None, "set a tail window with start < stop (in ns)"
    h = np.asarray(hist, dtype=float)
    i0 = int(np.ceil(start / bin_ns))
    i1 = min(int(np.floor(stop / bin_ns)), h.size)
    if i1 - i0 < 10:
        return None, "the tail window covers fewer than 10 bins; widen it"
    t = (np.arange(i0, i1) + 0.5) * bin_ns
    y = h[i0:i1]
    mask = y > 0
    if int(mask.sum()) < 10:
        return None, "fewer than 10 non-empty bins in the tail window; widen it or measure longer"
    x, ln_y, w2 = t[mask], np.log(y[mask]), y[mask]  # weights w = sqrt(n) -> w^2 = n
    s = w2.sum()
    sx, sy = (w2 * x).sum(), (w2 * ln_y).sum()
    sxx, sxy = (w2 * x * x).sum(), (w2 * x * ln_y).sum()
    denom = s * sxx - sx * sx
    if denom == 0:
        return None, "degenerate tail window (all counts in one bin)"
    slope = (s * sxy - sx * sy) / denom
    if slope >= 0:
        return None, "the counts do not decay within the tail window; move the window later"
    tau = -1.0 / slope
    return (
        float(tau),
        f"counts-weighted log-linear tail fit over {start:g}:{stop:g} ns "
        "(first-order estimate; a reconvolution-fit value can be entered alongside)",
    )


# -- the buffer background ----------------------------------------------------------------------

def background_rate_khz(*, photons, acquisition_time_s) -> tuple[float | None, str]:
    """Mean background count rate in kHz from photons over an acquisition time."""
    n, t = _number(photons), _number(acquisition_time_s)
    if n is None or t is None or t <= 0:
        return None, "the acquisition time must be a positive number of seconds"
    if n < 0:
        return None, "the photon number cannot be negative"
    return float(n) / t / 1e3, f"{n:g} photons over {t:g} s"


# -- the polarisation factor --------------------------------------------------------------------

def g_factor(*, i_par, i_perp, r_assumed) -> tuple[float | None, str]:
    """G from a reference with known anisotropy, using background-corrected intensities.

    The convention corrects the VH channel (Ströhl et al.,
    DOI: 10.1088/2050-6120/aa872e, Eq. 1). This alone does not calibrate
    high-NA polarization mixing or establish that the reference is appropriate.
    """
    par, perp, r = _number(i_par), _number(i_perp), _number(r_assumed)
    if perp is None or perp <= 0:
        return None, "the VH intensity must be positive"
    if par is None or par <= 0:
        return None, "the VV intensity must be positive"
    if r is None:
        return None, "set the assumed true anisotropy of the reference (0 for fast rotation)"
    if not -0.5 < r < 1.0:
        return None, "the assumed anisotropy must be greater than -0.5 and less than 1"
    g = (par / perp) * (1.0 - r) / (1.0 + 2.0 * r)
    if not np.isfinite(g) or g <= 0:
        return None, "the reference intensities and anisotropy do not yield a finite positive G"
    return (
        float(g),
        f"G = (I_par/I_perp)(1-r)/(1+2r) with assumed true anisotropy r = {r:g}; "
        "verify the reference's anisotropy for your dye and conditions",
    )


def apparent_anisotropy(*, i_par, i_perp) -> tuple[float | None, str]:
    """The raw anisotropy under the G = 1 assumption -- why the G factor is needed."""
    par, perp = _number(i_par), _number(i_perp)
    if par is None or perp is None or par + 2.0 * perp <= 0:
        return None, "set positive parallel and perpendicular intensities"
    return float((par - perp) / (par + 2.0 * perp)), "(I_par - I_perp) / (I_par + 2 I_perp), G = 1 assumed"


# -- PIE gamma ----------------------------------------------------------------------------------

def pie_gamma(
    *,
    i_dd=None,
    i_ad_raw=None,
    i_aa=None,
    alpha=None,
    delta=None,
    beta=None,
) -> tuple[dict | None, str]:
    """gamma (and the transfer efficiency) from one doubly-labelled PIE sample.

    Inputs are the background-corrected stream sums: ``i_dd`` donor emission
    under donor excitation, ``i_ad_raw`` acceptor emission under donor
    excitation (uncorrected), ``i_aa`` acceptor emission under acceptor
    excitation (uncorrected), and the correction factors ``alpha`` (donor
    leakage), ``delta`` (direct acceptor excitation) and ``beta`` (excitation
    normalisation). The derivation assumes exactly one donor and one acceptor
    per molecule. Returns a dict with the corrected streams, the FRET
    efficiency and gamma.
    """
    values = {"i_dd": i_dd, "i_ad_raw": i_ad_raw, "i_aa": i_aa,
              "alpha": alpha, "delta": delta, "beta": beta}
    numbers: dict[str, float] = {}
    for name in ("i_dd", "i_ad_raw", "i_aa", "alpha", "delta", "beta"):
        raw = values[name]
        if raw is None:
            return None, f"{name} is not set"
        value = _number(raw)
        if value is None:
            return None, f"{name} is not a number"
        numbers[name] = value
    if numbers["beta"] <= 0:
        return None, "beta (the excitation normalisation) must be positive"
    if numbers["i_dd"] <= 0:
        return None, "i_dd must be positive for a doubly-labelled sample"
    if numbers["i_aa"] <= 0:
        return None, "i_aa must be positive for a doubly-labelled sample"
    f_ad = numbers["i_ad_raw"] - numbers["alpha"] * numbers["i_dd"] - numbers["delta"] * numbers["i_aa"]
    f_aa = numbers["i_aa"] / numbers["beta"]
    if f_aa <= 0 or f_ad <= 0 or f_aa - f_ad <= 0:
        return None, (
            "the corrected streams are inconsistent with a 1:1 doubly-labelled sample "
            f"(sensitized F_AD = {f_ad:g}, directly excited F_AA = {f_aa:g}); check "
            "alpha, delta, beta and the sample"
        )
    out = {
        "f_ad": f_ad,
        "f_aa_corrected": f_aa,
        "fret_efficiency": f_ad / f_aa,
        "gamma": (f_aa - f_ad) / numbers["i_dd"],
    }
    detail = (
        "E = F_AD/F_AA and gamma = (F_AA - F_AD)/F_DD from one 1:1 doubly-labelled "
        "sample (Müller et al. 2005, DOI 10.1529/biophysj.105.064766; factor names "
        "per Hellenkamp et al. 2018, DOI 10.1038/s41592-018-0085-0)"
    )
    return out, detail


# -- histogram loading --------------------------------------------------------------------------

def load_histogram(path: str | Path):
    """A microtime histogram from ``.npy`` or text columns; ``None`` otherwise."""
    p = Path(path)
    suffix = p.suffix.lower()
    try:
        if suffix == ".npy":
            return np.load(p)
        if suffix in (".txt", ".csv", ".dat"):
            return np.loadtxt(p)
    except Exception:  # noqa: BLE001 - the caller shows the reason as a metric detail
        return None
    return None


def microtime_histogram(path: str | Path, micro_channels: int | None = None):
    """A microtime histogram from a TTTR recording (lazy tttrlib import).

    ``micro_channels`` selects routing channels (``None``: all events). This
    reads files; it never touches hardware.
    """
    import tttrlib

    data = tttrlib.TTTR(str(path))
    micro = np.asarray(data.micro_times, dtype=np.int64)
    if micro_channels is not None:
        routing = np.asarray(data.routing_channels)
        mask = np.isin(routing, [int(c) for c in micro_channels])
        micro = micro[mask]
    return np.bincount(micro)
