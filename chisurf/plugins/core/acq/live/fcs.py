"""FCS acquisition: a point measurement whose live analysis is the correlation curve.

:class:`LiveFcs` feeds every photon to tttrlib's online multi-tau correlator
(``tttrlib.StreamingCorrelator``, A/B-tested against the batch correlator) and keeps the count
rate, so the curve and its amplitude build up during the run without re-reading photons.
:func:`fcs_qc` judges the measurement with the checks that apply to FCS (count-rate stability,
molecular brightness, molecules in focus, afterpulsing and detector saturation), in the traffic
lights the smFRET quality panel uses. :class:`FcsRecordSession` records the run as a photons
dataset; there is no burst run.

The simulated FCS sample is one freely diffusing species in the green channel (:func:`fcs_realism`
keeps the instrument's imperfections -- IRF, background, afterpulsing, dead time, drift -- and
drops the smFRET sample's extra populations and photophysics, so the answer is known):
:func:`fcs_truth` gives the diffusion time and the number of molecules in the focus from the
simulator's own focus and box.
"""

from __future__ import annotations

import logging
import math
from dataclasses import replace
from typing import Any

import numpy as np
import tttrlib

from .realism import Realism
from .session import RecordSession

_log = logging.getLogger(__name__)

__all__ = ["FcsRecordSession", "LiveFcs", "fcs_qc", "fcs_realism", "fcs_truth", "population_for"]

#: The simulator's box (an ellipsoid of these semi-axes, um): the population is the expected
#: number of molecules in it (tttrlib SimEngine's open volume).
BOX_XY_UM, BOX_Z_UM = 2.0, 4.0


def fcs_realism(realism: Realism, diffusion_um2_per_s: float) -> Realism:
    """An FCS sample under *realism*'s instrument: one diffusing species, no FRET extras."""
    return replace(
        realism,
        donor_only_fraction=0.0,
        acceptor_only_fraction=0.0,
        aggregate_fraction=0.0,
        brightness_cv=0.0,
        acceptor_bleach_per_ms=0.0,
        donor_bleach_per_ms=0.0,
        acceptor_blink_per_ms=0.0,
        diffusion_um2_per_s=float(diffusion_um2_per_s),
    )


def _v_eff_um3(realism: Realism) -> float:
    w0, z0 = realism.focus_w0_um, realism.focus_z0_um
    return math.pi**1.5 * w0 * w0 * z0


def _v_box_um3() -> float:
    return 4.0 / 3.0 * math.pi * BOX_XY_UM * BOX_XY_UM * BOX_Z_UM


def population_for(n_in_focus: float, realism: Realism) -> float:
    """The simulator's population (molecules per box) that puts *n_in_focus* in the focus."""
    return float(n_in_focus) * _v_box_um3() / _v_eff_um3(realism)


def fcs_truth(realism: Realism, population: float) -> dict:
    """What an FCS fit of the simulated sample must recover.

    Returns
    -------
    dict
        ``tau_d_s`` (w0^2 / 4D), ``n`` (molecules in the 3-D Gaussian focus),
        ``d_um2_per_s``, ``w0_um``, ``z0_um``.
    """
    w0 = realism.focus_w0_um
    d = realism.diffusion_um2_per_s
    return {
        "tau_d_s": w0 * w0 / (4.0 * d),
        "n": float(population) * _v_eff_um3(realism) / _v_box_um3(),
        "d_um2_per_s": d,
        "w0_um": w0,
        "z0_um": realism.focus_z0_um,
    }


class LiveFcs:
    """The live analysis of an FCS run: the correlation curve and the count rate.

    Parameters
    ----------
    macro_clock_s : float
        Duration of one macro-time tick.
    channels : sequence of int, optional
        Routing channels correlated (all when ``None``).
    """

    def __init__(self, macro_clock_s: float, channels=None, *, n_bins: int = 8, n_casc: int = 25):
        self.macro_clock_s = float(macro_clock_s)
        self.channels = None if channels is None else np.asarray(list(channels), np.int64)
        self._n_bins, self._n_casc = int(n_bins), int(n_casc)
        self.clear()

    def clear(self) -> None:
        self.correlator = tttrlib.StreamingCorrelator(self._n_bins, self._n_casc, 1.0)
        self.photons = 0
        self._first: int | None = None
        self._last: int | None = None

    def push_np(self, macro, micro=None, channel=None) -> None:
        macro = np.asarray(macro, dtype=np.uint64)
        if self.channels is not None and channel is not None:
            macro = macro[np.isin(np.asarray(channel, np.int64), self.channels)]
        if macro.size == 0:
            return
        self.correlator.push_np(macro)
        self.photons += int(macro.size)
        if self._first is None:
            self._first = int(macro[0])
        self._last = int(macro[-1])

    def flush(self) -> None:
        self.correlator.flush()

    def table(self) -> dict:
        return {}

    def snapshot(self) -> dict[str, Any]:
        """``tau_s``, ``g`` (G(tau) - 1, normalised), count rate, the amplitude's N."""
        elapsed = (
            (self._last - self._first) * self.macro_clock_s
            if self._first is not None and self._last is not None
            else 0.0
        )
        tau = np.asarray(self.correlator.get_x_axis(), dtype=float) * self.macro_clock_s
        g = np.asarray(self.correlator.get_correlation_normalized(), dtype=float)
        n = min(tau.size, g.size)
        tau, g = tau[:n], g[:n]
        keep = (tau > 0) & np.isfinite(g)
        tau, g = tau[keep], g[keep] - 1.0
        rate = self.photons / elapsed if elapsed > 0 else 0.0
        amp = _amplitude(tau, g)
        n_focus = 1.0 / amp if amp > 0 else float("nan")
        return {
            "photons": self.photons,
            "bursts": 0,
            "elapsed_s": float(elapsed),
            "background_cps": {},
            "histograms": {},
            "correlation": {"tau_s": tau, "g": g},
            "count_rate_hz": float(rate),
            "n_focus": float(n_focus),
            "brightness_hz": float(rate / n_focus) if np.isfinite(n_focus) and n_focus > 0 else 0.0,
        }


def _amplitude(tau: np.ndarray, g: np.ndarray) -> float:
    """G(0)-1 read on the plateau between 10 us and 50 us (past afterpulsing, before diffusion)."""
    sel = (tau >= 1e-5) & (tau <= 5e-5) & np.isfinite(g)
    if not sel.any():
        sel = np.isfinite(g) & (tau > 0)
        if not sel.any():
            return 0.0
        return float(np.nanmax(g[sel]))
    return float(np.nanmedian(g[sel]))


def _light(value: float, ok, warn) -> str:
    lo_ok, hi_ok = ok
    lo_w, hi_w = warn
    if lo_ok <= value <= hi_ok:
        return "green"
    if lo_w <= value <= hi_w:
        return "amber"
    return "red"


def fcs_qc(snap: dict, trace: tuple[np.ndarray, np.ndarray] | None = None) -> dict:
    """The FCS quality verdict: the checks that apply to a correlation measurement.

    Returns
    -------
    dict
        As the smFRET verdict: ``ready``, ``level`` (worst light), ``checks`` (``name``, ``level``,
        ``value``, ``detail``), ``metrics``.
    """
    elapsed = float(snap.get("elapsed_s", 0.0))
    if elapsed < 2.0 or snap.get("photons", 0) < 2000:
        return {"ready": False, "level": "grey", "checks": [], "metrics": {},
                "why": "collecting (needs 2 s and 2000 photons)"}  # fmt: skip
    checks = []
    rate = float(snap.get("count_rate_hz", 0.0))
    n_focus = float(snap.get("n_focus", float("nan")))
    bright = float(snap.get("brightness_hz", 0.0))
    if trace is not None and len(trace[1]) >= 3:
        series = np.asarray(trace[1][:-1], dtype=float)  # the last second is partial
        cv = float(np.std(series) / np.mean(series)) if np.mean(series) > 0 else 1.0
        checks.append({"name": "count-rate stability", "light": _light(cv, (0, 0.1), (0, 0.25)),
                       "value": f"{100 * cv:.0f} % CV",
                       "detail": "Drift or spikes distort the curve: check focus, evaporation, "
                                 "aggregates."})  # fmt: skip
    checks.append({"name": "molecules in focus", "light": _light(n_focus, (0.5, 50), (0.1, 200)),
                   "value": f"N ≈ {n_focus:.2g}" if np.isfinite(n_focus) else "N ?",
                   "detail": "FCS works best with 0.5-50 molecules in the focus: dilute or "
                             "concentrate the sample."})  # fmt: skip
    checks.append({"name": "brightness", "light": _light(bright, (5e3, 1e7), (1e3, 1e8)),
                   "value": f"{bright / 1e3:.1f} kHz per molecule",
                   "detail": "Dim molecules give a noisy curve: raise the laser power within "
                             "the saturation limit."})  # fmt: skip
    checks.append({"name": "detector saturation", "light": _light(rate, (0, 1e6), (0, 3e6)),
                   "value": f"{rate / 1e3:.0f} kHz",
                   "detail": "Above ~1 MHz dead time flattens the count rate: lower the power "
                             "or the concentration."})  # fmt: skip
    corr = snap.get("correlation") or {}
    tau, g = np.asarray(corr.get("tau_s", ())), np.asarray(corr.get("g", ()))
    early = (tau > 0) & (tau < 2e-6) & np.isfinite(g)
    plateau = _amplitude(tau, g)
    if early.any() and plateau > 0:
        excess = float(np.nanmedian(g[early]) / plateau - 1.0)
        checks.append({"name": "afterpulsing", "light": _light(excess, (-1, 0.2), (-1, 1.0)),
                       "value": f"{100 * excess:+.0f} % below 2 µs",
                       "detail": "Afterpulses raise the curve below a few µs: correlate two "
                                 "detectors (cross-correlation) or ignore those lags."})  # fmt: skip
    for check in checks:  # what to do, for the lights that ask for something (the panel's tooltip)
        check["action"] = check["detail"] if check["light"] in ("amber", "red") else ""
    order = {"green": 0, "amber": 1, "red": 2}
    level = max((c["light"] for c in checks), key=lambda v: order[v], default="grey")
    return {
        "ready": True,
        "level": level,
        "checks": checks,
        "metrics": {"count_rate_hz": rate, "n_focus": n_focus, "brightness_hz": bright},
    }


class FcsRecordSession(RecordSession):
    """A recording whose live analysis is :class:`LiveFcs`; it becomes a photons dataset."""

    dataset_kind = "photons"

    def __init__(self, source, experiment=None, *, channels=None, truth: dict | None = None,
                 **kwargs):
        self._channels = channels
        #: the simulated sample's known answer (``fcs_truth``), kept with the recording
        self.truth = dict(truth or {})
        super().__init__(source, experiment, **kwargs)

    def _make_analyzer(self):
        return LiveFcs(self.source.info.macro_clock_s, self._channels)

    def _push(self, batch) -> None:
        photons = batch.photons()
        self.analyzer.push_np(photons.macro, photons.micro, photons.channel)
        if self.trace is not None:
            self.trace.push(photons.macro, photons.micro, photons.channel)
        self._count_seconds(photons.macro, self.source.info.macro_clock_s)

    def table(self) -> dict:
        return {}

    def _update_qc(self, table: dict | None = None) -> None:
        with self._lock:
            snap = self.analyzer.snapshot()
            trace = self.trace_1s()
        try:
            qc = fcs_qc(snap, trace)
        except Exception as exc:  # noqa: BLE001 - no verdict is shown as such, the run goes on
            _log.exception("FCS quality check failed")
            qc = {"ready": False, "level": "grey", "checks": [], "metrics": {}, "why": str(exc)}
        with self._lock:
            self.qc = qc

    def register(self):
        """The recording into the workspace (a photons dataset, no burst run); the sample's truth
        and the verdict are kept with it."""
        if self._dataset is not None:
            meta = getattr(self._dataset, "meta_data", None)
            if isinstance(meta, dict):
                if self.truth:
                    meta["simulated_truth"] = dict(self.truth)
                if self.result is not None and self.result.qc:
                    from .session import quality_record

                    meta["acquisition_quality"] = quality_record(self.result.qc)
        return super().register()
