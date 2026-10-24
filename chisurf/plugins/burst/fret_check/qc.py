"""Quality control of a confocal smFRET measurement.

The question a user brings to "simple mode" is: *is this measurement usable,
and which bursts should I not trust?* Nothing here needs alternating
excitation; the checks that do (stoichiometry, ALEX-2CDE) are added only
when the data has it.

Basic quality (every measurement, cw or ALEX/PIE, one or two colours)
---------------------------------------------------------------------
* **burst rate** -- bursts per second after the size filter.
* **burst density** (occupancy) -- lambda = burst rate x mean burst duration,
  the mean number of molecules in the observation volume.
* **multi-molecule events** -- two estimates of the fraction of bursts holding
  two or more molecules:

  - from the occupancy, Poisson: P(>=2 | >=1) = (1 - e^-l - l e^-l) / (1 - e^-l);
  - from the gaps between bursts: molecule arrivals are Poisson, so the tail of
    the gap histogram is exponential with the arrival rate r (fitted beyond
    5 median burst durations, where blinking does not reach). A second
    molecule arrives during a burst of duration d with probability
    1 - e^(-r d); averaged over the bursts. It does not depend on the burst
    search having separated close molecules.

  Above ~5 % coincident bursts bridge populations in E/S histograms.
* **short gaps** -- gaps shorter than 2 median burst durations, observed over
  expected from the fitted arrivals. Well above 1: bursts are fragmented
  (blinking, a strict burst search) or molecules revisit the focus.
* **time in bursts**, **brightness** (in-burst count rate above background),
  **signal / background**, **background** per stream.
* **concentration** -- lambda / (N_A V_eff), for an assumed effective volume
  (1 fL by default), and the **dilution** that brings the coincidences down
  to 2 %.
* **signal stability** -- drift and spikes of the 1 s count-rate trace.
* **bright / long outliers** -- per burst, a Tukey fence (3 IQR, log scale)
  on count rate and duration: aggregates, sticking or coincident molecules.

Two colours
-----------
* **donor-only / acceptor-only** -- with ALEX/PIE from S (> 0.8 / < 0.25);
  with cw the low-E peak (E < 0.15: donor-only, plus very low FRET).
* **FRET-2CDE** > 30 (dynamics or a second molecule within the burst) and,
  with ALEX/PIE, **ALEX-2CDE** > 30 (blinking / bleaching, or a donor-only
  and an acceptor-only molecule together).

:func:`burst_flags` returns the per-burst flags so the plots can mark
suspicious bursts and the table can filter them out.
"""
from __future__ import annotations

import dataclasses

import numpy as np

from .detect import Experiment
from .pipeline import Bursts

__all__ = ["Check", "QCReport", "burst_flags", "count_rate_trace", "run_qc"]

OK, WARN, BAD, INFO = "ok", "warn", "bad", "info"

#: Flag bits per burst.
FLAG_BRIGHT = 1
FLAG_LONG = 2
FLAG_FRET_2CDE = 4
FLAG_ALEX_2CDE = 8
FLAG_NAMES = {
    FLAG_BRIGHT: "bright",
    FLAG_LONG: "long",
    FLAG_FRET_2CDE: "FRET-2CDE",
    FLAG_ALEX_2CDE: "ALEX-2CDE",
}

CDE_LIMIT = 30.0
#: Coincident-burst fraction the dilution advice aims for.
TARGET_P_MULTI = 0.02
AVOGADRO = 6.02214076e23


@dataclasses.dataclass
class Check:
    name: str
    level: str
    value: str
    detail: str
    group: str = "basic"  # "basic" | "two-colour"


@dataclasses.dataclass
class QCReport:
    checks: list[Check]
    flags: np.ndarray  # per burst, FLAG_* bits
    burst_rate: float  # bursts/s
    occupancy: float  # mean molecules in the volume (lambda)
    p_multi: float  # P(>=2 molecules | burst), from the occupancy
    p_multi_gaps: float  # the same from the inter-burst gaps
    arrival_rate: float  # molecules/s from the gap tail
    gaps: np.ndarray  # s, between consecutive bursts
    trace_t: np.ndarray  # s
    trace_rate: np.ndarray  # kHz, 1 s bins
    metrics: dict = dataclasses.field(default_factory=dict)

    @property
    def level(self) -> str:
        levels = [c.level for c in self.checks]
        return BAD if BAD in levels else WARN if WARN in levels else OK

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "n_flagged": int((self.flags != 0).sum()),
            "metrics": self.metrics,
            "checks": [dataclasses.asdict(c) for c in self.checks],
        }


def _upper_fence(x: np.ndarray, k: float = 3.0) -> float:
    """Tukey's upper fence on log10(x)."""
    lx = np.log10(x[x > 0])
    if lx.size < 10:
        return np.inf
    q1, q3 = np.percentile(lx, [25, 75])
    return float(10 ** (q3 + k * (q3 - q1)))


def burst_flags(b: Bursts) -> np.ndarray:
    flags = np.zeros(b.n, np.int32)
    if b.n == 0:
        return flags
    flags[b.count_rate > _upper_fence(b.count_rate)] |= FLAG_BRIGHT
    flags[b.duration > _upper_fence(b.duration)] |= FLAG_LONG
    if b.fret_2cde is not None:
        flags[np.nan_to_num(b.fret_2cde) > CDE_LIMIT] |= FLAG_FRET_2CDE
    if b.alex_2cde is not None:
        flags[np.nan_to_num(b.alex_2cde) > CDE_LIMIT] |= FLAG_ALEX_2CDE
    return flags


def count_rate_trace(data, exp: Experiment, bin_s: float = 1.0):
    """Total count rate (kHz) in ``bin_s`` bins."""
    macro = np.asarray(data.macro_times)
    t = (macro - macro[0]) * exp.macro_time_resolution_s
    n = max(1, int(np.ceil(t[-1] / bin_s))) if t.size else 1
    counts = np.bincount(np.minimum((t / bin_s).astype(np.int64), n - 1), minlength=n)
    return (np.arange(n) + 0.5) * bin_s, counts / bin_s * 1e-3


def _p_multi(lam: float) -> float:
    if lam <= 0:
        return 0.0
    e = np.exp(-lam)
    return float((1 - e - lam * e) / (1 - e))


def _lambda_for(p_target: float) -> float:
    """The occupancy at which :func:`_p_multi` equals *p_target* (bisection)."""
    lo, hi = 1e-9, 10.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        lo, hi = (mid, hi) if _p_multi(mid) < p_target else (lo, mid)
    return 0.5 * (lo + hi)


def _gap_analysis(b: Bursts):
    """``(gaps, arrival_rate, p_multi_gaps, short_gap_excess)``."""
    if b.n < 20:
        return np.zeros(0), 0.0, float("nan"), float("nan")
    order = np.argsort(b.t_start)
    start = b.t_start[order]
    end = start + b.duration[order]
    gaps = np.maximum(start[1:] - end[:-1], 0.0)
    med = float(np.median(b.duration))
    g0 = 5.0 * med
    tail = gaps[gaps > g0] - g0
    if tail.size < 10 or tail.mean() <= 0:
        return gaps, 0.0, float("nan"), float("nan")
    rate = 1.0 / float(tail.mean())  # MLE of an exponential tail
    p_gaps = float(np.mean(1.0 - np.exp(-rate * b.duration)))
    tau = 2.0 * med
    expected = 1.0 - np.exp(-rate * tau)
    excess = float(np.mean(gaps < tau) / expected) if expected > 0 else float("nan")
    return gaps, rate, p_gaps, excess


def _level(value, ok, warn):
    if not np.isfinite(value):
        return INFO
    return OK if value < ok else WARN if value < warn else BAD


def run_qc(data, exp: Experiment, b: Bursts, v_eff_fl: float = 1.0, trace=None) -> QCReport:
    """Every check for one measurement.

    ``trace`` -- ``(t_s, rate_kHz)`` in 1 s bins -- replaces reading the count
    rate from *data*; a measurement analysed in chunks
    (:mod:`chisurf.plugins.burst.fret_check.chunked`) passes it and ``data=None``.
    """
    checks: list[Check] = []
    duration = max(exp.duration_s, 1e-9)
    n = max(b.n, 1)

    # -- burst rate and density ---------------------------------------------
    burst_rate = b.n / duration
    mean_dur = float(np.mean(b.duration)) if b.n else 0.0
    lam = burst_rate * mean_dur
    p_occ = _p_multi(lam)
    gaps, arrivals, p_gaps, excess = _gap_analysis(b)
    checks.append(Check("bursts", OK if b.n >= 500 else WARN if b.n >= 100 else BAD,
                        f"{b.n} ({burst_rate:.1f}/s)", "bursts after the size filter, and their rate"))
    checks.append(Check("burst density", _level(lam, 0.05, 0.2), f"{lam:.3f} molecules in focus",
                        f"occupancy = {burst_rate:.1f} bursts/s x {1e3 * mean_dur:.2f} ms mean duration"))

    # -- multi-molecule events ----------------------------------------------
    p_worst = max(p_occ, p_gaps if np.isfinite(p_gaps) else 0.0)
    gap_text = f"{100 * p_gaps:.1f} % (gaps)" if np.isfinite(p_gaps) else "n/a (gaps)"
    checks.append(Check(
        "multi-molecule events", _level(p_worst, 0.05, 0.15),
        f"{100 * p_occ:.1f} % (occupancy) · {gap_text}",
        "P(>=2 molecules | burst): Poisson from the occupancy, and from the molecule arrival "
        f"rate fitted to the inter-burst gaps ({arrivals:.1f}/s). Keep below ~5 %.",
    ))
    if np.isfinite(excess):
        checks.append(Check(
            "short gaps", _level(excess, 2.0, 5.0) if b.n >= 300 else INFO, f"{excess:.1f}x expected",
            "gaps < 2 median burst durations, observed / expected from Poisson arrivals: "
            "high means fragmented bursts (blinking, strict burst search) or revisiting molecules",
        ))

    # -- concentration and dilution -----------------------------------------
    conc_pm = lam / (AVOGADRO * v_eff_fl * 1e-15) * 1e12
    lam_target = _lambda_for(TARGET_P_MULTI)
    dilution = lam / lam_target if lam_target > 0 else float("nan")
    checks.append(Check(
        "concentration", INFO, f"~{conc_pm:.0f} pM",
        f"occupancy / (N_A x V_eff), V_eff = {v_eff_fl:g} fL assumed; scale by your volume",
    ))
    checks.append(Check(
        "dilution", INFO if dilution <= 1 else WARN if dilution < 3 else BAD,
        "none needed" if dilution <= 1 else f"{dilution:.1f}x",
        f"to bring multi-molecule events to {100 * TARGET_P_MULTI:.0f} % "
        f"(occupancy {lam_target:.3f})",
    ))

    # -- time, brightness, background ----------------------------------------
    busy = float(np.sum(b.duration)) / duration
    checks.append(Check("time in bursts", _level(busy, 0.1, 0.3), f"{100 * busy:.1f} %",
                        "fraction of the measurement inside bursts; high means too concentrated (or bulk data)"))
    bg_total = float(sum(b.background.values()))
    brightness = float(np.median(b.count_rate)) - bg_total if b.n else 0.0
    sbr = brightness / bg_total if bg_total > 0 else float("inf")
    checks.append(Check("brightness", INFO, f"{brightness * 1e-3:.1f} kHz",
                        "median in-burst count rate above background, all streams"))
    if np.isfinite(sbr):
        checks.append(Check("signal / background", OK if sbr > 10 else WARN if sbr > 3 else BAD,
                            f"{sbr:.1f}", "brightness over the out-of-burst count rate"))
    else:
        # Nothing outside bursts to measure the background in (bulk data):
        # no verdict, rather than an "infinite" one rated OK.
        checks.append(Check("signal / background", INFO, "n/a",
                            "no time outside bursts to measure the background in"))
    bg = ", ".join(f"{k} {v * 1e-3:.2f}" for k, v in b.background.items())
    checks.append(Check("background (kHz)", INFO, bg, "count rate outside bursts per stream"))

    # -- stability ------------------------------------------------------------
    tt, rate = trace if trace is not None else count_rate_trace(data, exp)
    if rate.size >= 10:
        full = rate[:-1]  # the last bin is partial
        x = tt[: full.size]
        slope, _ = np.polyfit(x, full, 1)
        drift = slope * x[-1] / max(np.mean(full), 1e-9)
        med = np.median(full)
        mad = np.median(np.abs(full - med)) * 1.4826 + 1e-9
        spikes = int(np.sum(full > med + 8 * mad))
        level = OK if abs(drift) < 0.15 and spikes == 0 else WARN if abs(drift) < 0.4 and spikes < 3 else BAD
        checks.append(Check("signal stability", level, f"{100 * drift:+.0f} % drift, {spikes} spikes",
                            "1 s count-rate trace: drift from evaporation/bleaching/focus, spikes from aggregates"))

    # -- outliers -------------------------------------------------------------
    flags = burst_flags(b)
    for bit, what in ((FLAG_BRIGHT, "count rate"), (FLAG_LONG, "duration")):
        frac = float(((flags & bit) != 0).sum()) / n
        checks.append(Check(f"{FLAG_NAMES[bit]} bursts", _level(frac, 0.02, 0.05), f"{100 * frac:.1f} %",
                            f"bursts with {what} > Q3 + 3 IQR (log): aggregates, sticking or coincident molecules"))

    # -- two colours ----------------------------------------------------------
    if exp.acceptor_channels and b.n:
        if b.S is not None:
            do = float(np.mean(b.S > 0.8))
            ao = float(np.mean(b.S < 0.25))
            checks.append(Check("donor-only / acceptor-only", _level(max(do, ao), 0.4, 0.7),
                                f"{100 * do:.0f} % / {100 * ao:.0f} %",
                                "from S (> 0.8 / < 0.25): labelling, bleaching", "two-colour"))
        else:
            low = float(np.mean(b.E < 0.15))
            checks.append(Check("low-E / donor-only", _level(low, 0.4, 0.7), f"{100 * low:.0f} %",
                                "E < 0.15 without ALEX: donor-only (no or bleached acceptor) and very low FRET "
                                "cannot be told apart", "two-colour"))
        for bit, arr in ((FLAG_FRET_2CDE, b.fret_2cde), (FLAG_ALEX_2CDE, b.alex_2cde)):
            if arr is None:
                continue
            frac = float(((flags & bit) != 0).sum()) / n
            detail = ("FRET changes within bursts (dynamics or two molecules)" if bit == FLAG_FRET_2CDE
                      else "acceptor blinking/bleaching or donor-only + acceptor-only coincidence")
            checks.append(Check(f"{FLAG_NAMES[bit]} > {CDE_LIMIT:.0f}", _level(frac, 0.15, 0.35),
                                f"{100 * frac:.1f} %", detail, "two-colour"))

    metrics = {
        "bursts": b.n, "burst_rate_per_s": burst_rate, "occupancy": lam,
        "p_multi_occupancy": p_occ, "p_multi_gaps": p_gaps, "arrival_rate_per_s": arrivals,
        "short_gap_excess": excess, "concentration_pM": conc_pm, "v_eff_fL": v_eff_fl,
        "dilution": dilution, "time_in_bursts": busy, "brightness_kHz": brightness * 1e-3,
        "signal_to_background": sbr, "background_kHz": {k: v * 1e-3 for k, v in b.background.items()},
    }
    return QCReport(checks, flags, burst_rate, lam, p_occ, p_gaps, arrivals, gaps, tt, rate, metrics)
