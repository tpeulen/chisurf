"""Photon sources for live recording: something that hands out decoded photons in time order.

A source is what the Record tool measures from. It is started, read in batches while it runs, and
stopped; it says what its clocks are (:class:`SourceInfo`) and how it is doing (:meth:`status`).
Three exist:

* :class:`SimulatedPieSource` -- a PIE smFRET measurement simulated by tttrlib's ``SimEngine``,
  handed out at the pace a real one would arrive. Populations are given by their FRET efficiency
  E and stoichiometry S, so a run has a known answer.
* :class:`FileReplaySource` -- a recorded measurement played back at measurement speed.
* a device -- :class:`~.devices.DeviceSource`, a TCSPC unit through libphacq, implements this same
  interface (and :class:`~.scanning.ScannedSource` a device recording while the scanner rasters).

The simulator models two lasers per molecule the way tttrlib does for ALEX (one excitation grid
and one brightness row per laser, alternating every ``dt``), then places each photon of the red
(acceptor-exciting) laser into the second half of the laser period. Per molecule this is what
pulsed interleaved excitation produces: the same molecule excited alternately by both lasers,
separated in micro-time -- prompt window for the green pulse, delay window for the red one.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import tttrlib

from .realism import IDEAL, Realism

__all__ = [
    "FileReplaySource",
    "PhotonBatch",
    "PhotonSource",
    "Population",
    "SimulatedPieSource",
    "SourceInfo",
    "SourceUnavailable",
]


class SourceUnavailable(RuntimeError):
    """The source cannot run here (no driver, no file)."""


@dataclass(frozen=True)
class SourceInfo:
    """The clocks of a source's photons.

    Attributes
    ----------
    name : str
        What the Record tool shows.
    macro_clock_s : float
        Seconds per macro-time tick.
    micro_res_s : float
        Seconds per micro-time channel.
    n_micro : int
        Micro-time channels in one laser period (the PIE period).
    """

    name: str
    macro_clock_s: float
    micro_res_s: float
    n_micro: int


@dataclass
class PhotonBatch:
    """Decoded photons in time order: macro-time ticks, micro-time channels, routing channels.

    ``truth`` is the simulator's population index per photon (background is the index after the
    last population); real sources leave it ``None``. ``raw`` is the device's undecoded records the
    batch came from, when there were any (what a device recording writes). ``event`` is the event
    type per entry (0 a photon, 1 a marker -- a scan's line and frame markers, whose ``channel`` is
    the marker bit); ``None`` means every entry is a photon.
    """

    macro: np.ndarray
    micro: np.ndarray
    channel: np.ndarray
    truth: np.ndarray | None = None
    raw: np.ndarray | None = None
    event: np.ndarray | None = None

    def photons(self) -> PhotonBatch:
        """The photons only (markers dropped) -- what a burst analysis takes."""
        if self.event is None or not np.any(self.event):
            return self
        keep = self.event == 0
        truth = self.truth[keep] if self.truth is not None else None
        return PhotonBatch(self.macro[keep], self.micro[keep], self.channel[keep], truth)

    def cut(self, n: int) -> None:
        """Keep the first *n* entries (the run's duration ended inside the batch)."""
        self.macro, self.micro, self.channel = self.macro[:n], self.micro[:n], self.channel[:n]
        if self.truth is not None:
            self.truth = self.truth[:n]
        if self.event is not None:
            self.event = self.event[:n]

    def __len__(self) -> int:
        return len(self.macro)


class PhotonSource:
    """The interface every source implements. One thread reads; :meth:`stop` may come from any."""

    info: SourceInfo

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def read(self, timeout: float = 0.2) -> PhotonBatch | None:
        """The photons that arrived since the last read; ``None`` when nothing came in *timeout*."""
        raise NotImplementedError

    @property
    def finished(self) -> bool:
        """Nothing more will come (stopped, or the data ran out)."""
        raise NotImplementedError

    def status(self) -> dict[str, Any]:
        """Health for the Record tool: ``queued`` batches, ``dropped`` batches, ``error``."""
        return {"queued": 0, "dropped": 0, "error": ""}


@dataclass(frozen=True)
class Population:
    """A simulated FRET population.

    Attributes
    ----------
    E, S : float
        FRET efficiency and stoichiometry of a molecule (with gamma = beta = 1).
    concentration : float
        Molecules per simulation box (tttrlib's ``population``).
    brightness : float
        Photons per ms under the green laser at the focus centre (donor + acceptor channel).
    """

    E: float
    S: float = 0.5
    concentration: float = 1.5
    brightness: float = 300.0


@dataclass
class _Clock:
    """Wall-clock pacing: how much measurement time may have arrived by now."""

    speed: float = 1.0
    realtime: bool = True
    t0: float = field(default_factory=time.monotonic)

    def allowed_s(self) -> float:
        return (time.monotonic() - self.t0) * self.speed if self.realtime else float("inf")


#: The simulator's time base (tttrlib's convention: one macro unit = 1 ms).
_DT_MS = 0.01  # one simulation window = 10 us
_MACRO_TICK_MS = _DT_MS / 1024  # ~9.77 ns, as tttrlib's own ALEX example
_LASER_PERIOD_NS = 32.0
_MICRO_RES_NS = 0.008
_N_MICRO = int(round(_LASER_PERIOD_NS / _MICRO_RES_NS))  # 4000 channels per period
_HALF = _N_MICRO // 2
#: The instrument delay of a simulated pulse: 1.5 ns, in micro-time channels.
_PULSE_DELAY_CHANNELS = int(round(1.5 / _MICRO_RES_NS))


#: Excitation schemes the simulator measures.
SCHEMES = ("pie", "two_color")


class SimulatedPieSource(PhotonSource):
    """A PIE smFRET measurement from tttrlib's ``SimEngine``, delivered at measurement pace.

    Parameters
    ----------
    populations : sequence of Population
        The FRET species; each molecule carries donor and acceptor.
    duration_s : float, optional
        Length of the measurement; ``None`` runs until :meth:`stop`.
    background_khz : (float, float)
        Background count rate per detector (donor, acceptor), uniform in micro-time.
    seed : int
        Seeds diffusion and emission; segment *k* uses ``seed + k``, so a run is reproducible.
    batch_s : float
        Measurement time per batch handed to the reader.
    speed : float
        1 is real time; larger plays faster.
    realtime : bool
        ``False`` hands batches out as fast as they are simulated (tests).
    segment_s : float
        Measurement time simulated per engine run. Molecules are re-seeded at a segment boundary,
        which may cut a burst; long segments make that rare.

    Notes
    -----
    Routing channel 0 is the donor detector, 1 the acceptor detector. The prompt window is the
    first half of the 32 ns period, the delay window the second.
    """

    def __init__(
        self,
        populations=(Population(0.2), Population(0.8)),
        *,
        duration_s: float | None = 10.0,
        background_khz=(0.5, 0.5),
        seed: int = 1,
        batch_s: float = 0.1,
        speed: float = 1.0,
        realtime: bool = True,
        segment_s: float = 5.0,
        scheme: str = "pie",
        realism: Realism = IDEAL,
    ):
        if scheme not in SCHEMES:
            raise ValueError(f"scheme {scheme!r} is not one of {SCHEMES}")
        self.scheme = scheme
        self.realism = realism
        self.populations = tuple(populations)
        self.duration_s = duration_s
        self.background_khz = tuple(background_khz)
        self.seed = int(seed)
        self.batch_s = float(batch_s)
        self.segment_s = float(segment_s)
        self._clock = _Clock(speed=float(speed), realtime=bool(realtime))
        self.info = SourceInfo(
            name="Simulator (PIE smFRET)" if scheme == "pie" else "Simulator (two-colour smFRET)",
            macro_clock_s=_MACRO_TICK_MS * 1e-3,
            micro_res_s=_MICRO_RES_NS * 1e-9,
            n_micro=_N_MICRO,
        )
        self._queue: queue.Queue = queue.Queue(maxsize=8)
        self._stop = threading.Event()
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending: PhotonBatch | None = None
        self._released_s = 0.0
        self.error = ""

    # -- the simulation ---------------------------------------------------------------------
    def config(self, segment: int) -> dict:
        """The ``SimEngine`` configuration of one segment (public: the tests read the truth)."""
        if not self.realism.ideal:
            return self._realistic_config(segment)
        species = []
        pie = self.scheme == "pie"
        for p in self.populations:
            green = float(p.brightness)
            red = green * (1.0 - p.S) / max(p.S, 1e-9)
            # PIE: a brightness row per laser (green: donor + FRET; red: the acceptor directly);
            # two colour: the green laser only
            q = (
                {"q_alex": [[(1.0 - p.E) * green, p.E * green], [0.0, red]]}
                if pie
                else {"q": [(1.0 - p.E) * green, p.E * green]}
            )
            species.append(
                {
                    "D": 0.05,
                    **q,
                    "decay": {
                        "lifetimes": [4.0 * (1.0 - p.E) + 0.1],
                        "amplitudes": [1.0],
                        "dt": _MICRO_RES_NS,
                    },
                }
            )
        n = len(species)
        bg_pattern = [1.0] * (_HALF if pie else _N_MICRO)
        green_focus = {
            "type": "gaussian3d",
            "w0": 0.3,
            "z0": 2.0,
            "extent_xy": 2.0,
            "extent_z": 4.0,
            "spacing": 0.1,
        }
        red_focus = dict(green_focus, w0=0.32, z0=2.1)
        cfg = {
            "settings": {
                "dt": _DT_MS,
                "n_ph_max": 50_000_000,
                "n_channels": 2,
                "n_microtime_channels": _N_MICRO,
                "microtime_resolution": _MICRO_RES_NS,
                "laser_period": _LASER_PERIOD_NS,
                "alex_period": 2 * _DT_MS,
                "alex_markers": False,
                "active_margin": 1.0,
                "fast_grid_bbox": True,
                "max_windows": int(round(self.segment_s * 1000.0 / _DT_MS)),
                "seed_diffusion": self.seed + 7919 * segment,
                "seed_emission": self.seed + 104729 * segment + 1,
            },
            "box": {"xy": 2.0, "z": 4.0},
            "species": species,
            "k_rad": [0.0] * (n * n),
            "k_nrad": [0.0] * (n * n),
            # tttrlib's background is a rate per macro unit (ms) and channel.
            "background": [float(b) for b in self.background_khz],
            "background_decay": {"pattern": bg_pattern, "dt": _MICRO_RES_NS},
            "population": [float(p.concentration) for p in self.populations],
            "excitation": [green_focus, red_focus] if pie else green_focus,
        }
        if not pie:
            for key in ("alex_period", "alex_markers"):
                cfg["settings"].pop(key)
        return cfg

    def simulate_segment(self, segment: int) -> PhotonBatch:
        """All photons of one segment, PIE-encoded and sorted; macro times start at the segment."""
        if not self.realism.ideal:
            return self._realistic_segment(segment)
        engine = tttrlib.SimEngine.from_dict(self.config(segment))
        engine.run()
        ph = engine.photons()
        keep = np.asarray(ph["event_type"]) == 0
        window = np.asarray(ph["macro_window"])[keep].astype(np.int64)
        arrival = np.asarray(ph["arrival_time"])[keep]
        t_ms = window * _DT_MS + arrival
        macro = np.floor(t_ms / _MACRO_TICK_MS).astype(np.uint64)
        macro += np.uint64(int(round(segment * self.segment_s * 1000.0 / _MACRO_TICK_MS)))
        # A real TCSPC channel sees each pulse after the cable/electronics delay, so the pulse
        # (and its IRF's leading edge) lies inside its window; without it the leading edge wrapped
        # to the end of the period and the window detection named the pulses the wrong way round.
        raw_micro = np.asarray(ph["micro_time"])[keep].astype(np.int64) + _PULSE_DELAY_CHANNELS
        if self.scheme == "pie":
            # The laser of a window alternates every dt (alex_period = 2 dt): odd windows are red.
            red = (window % 2) == 1
            micro = (raw_micro % _HALF) + np.where(red, _HALF, 0)
        else:
            micro = raw_micro % _N_MICRO
        channel = np.asarray(ph["channel"])[keep].astype(np.int8)
        species = np.asarray(ph["species"])[keep].astype(np.int16)
        order = np.argsort(macro, kind="stable")
        return PhotonBatch(
            macro[order], micro[order].astype(np.uint16), channel[order], species[order]
        )

    # -- realism (see live.realism) -------------------------------------------------------------
    def _realistic_config(self, segment: int) -> dict:
        """SimEngine configuration with the sample's populations, photophysics and detection.

        Per FRET population four molecular states: active, acceptor bleached (emits as donor
        only), donor bleached (acceptor only, under its own laser), acceptor dark (blinking).
        Donor-only, acceptor-only and aggregate molecules are populations of their own. The
        brightness rows hold gamma, alpha and delta, so the accurate-FRET corrections with these
        factors return each population's true E and S. ``self._states`` keeps per species what the
        record level needs (lifetimes, which population it belongs to).
        """
        r = self.realism
        pie = self.scheme == "pie"
        g, a, d, b_ = r.gamma, r.alpha, r.delta, r.beta
        boost = 1.0 + 3.0 * r.brightness_cv  # molecules are thinned by their brightness factor
        states: list[dict] = []
        species: list[dict] = []

        def add(green_row, red_row, label, kind, tau_donor):
            q = {"q_alex": [list(green_row), list(red_row)]} if pie else {"q": list(green_row)}
            species.append({"D": r.diffusion_um2_per_s / 1000.0, **q,
                            "decay": {"lifetimes": [1.0], "amplitudes": [1.0], "dt": _MICRO_RES_NS}})  # fmt: skip
            states.append({"label": label, "kind": kind, "tau_donor": tau_donor})
            return len(species) - 1

        transitions: list[tuple[int, int, float, bool]] = []  # (from, to, rate, radiative)
        fret_conc = sum(p.concentration for p in self.populations)
        rest = max(
            1e-9, 1.0 - r.donor_only_fraction - r.acceptor_only_fraction - r.aggregate_fraction
        )
        populations = []
        for i, p in enumerate(self.populations):
            b = float(p.brightness) * boost
            aa = b_ * g * b * (1.0 - p.S) / max(p.S, 1e-9)
            dd, da = b * (1.0 - p.E), g * b * p.E + a * b * (1.0 - p.E) + d * aa
            active = add((dd, da), (0.0, aa), i, "fret", r.tau_donor_ns * (1.0 - p.E))
            bleached_a = add((b, a * b), (0.0, 0.0), i, "donor", r.tau_donor_ns)
            bleached_d = add((0.0, d * aa), (0.0, aa), i, "acceptor", None)
            dark_a = add((b, a * b), (0.0, 0.0), i, "donor", r.tau_donor_ns)
            transitions += [
                (active, bleached_a, r.acceptor_bleach_per_ms, True),
                (active, bleached_d, r.donor_bleach_per_ms, True),
                (active, dark_a, r.acceptor_blink_per_ms, True),
                (dark_a, active, r.acceptor_recover_per_ms, False),
            ]
            populations += [p.concentration, 0.0, 0.0, 0.0]
        n_pop = len(self.populations)
        b = float(self.populations[0].brightness) * boost if self.populations else 300.0
        aa = b_ * g * b  # S = 0.5 brightness for the single-dye molecules
        add((b, a * b), (0.0, 0.0), n_pop, "donor", r.tau_donor_ns)
        populations.append(fret_conc * r.donor_only_fraction / rest)
        add((0.0, d * aa), (0.0, aa), n_pop + 1, "acceptor", None)
        populations.append(fret_conc * r.acceptor_only_fraction / rest)
        k = r.aggregate_brightness
        agg = add(
            (k * b * 0.5, k * b * 0.5),
            (0.0, k * aa * 0.5),
            n_pop + 2,
            "aggregate",
            r.tau_donor_ns * 0.6,
        )
        species[agg]["D"] = species[agg]["D"] * 0.1
        populations.append(fret_conc * r.aggregate_fraction / rest)
        n = len(species)
        k_rad, k_nrad = [0.0] * (n * n), [0.0] * (n * n)
        for i, j, rate, radiative in transitions:
            (k_rad if radiative else k_nrad)[i * n + j] = float(rate)
        self._states = states
        focus = {"type": "gaussian3d", "w0": r.focus_w0_um, "z0": r.focus_z0_um,
                 "extent_xy": 2.0, "extent_z": 4.0, "spacing": 0.1}  # fmt: skip
        cfg = {
            "settings": {
                "dt": _DT_MS,
                "n_ph_max": 50_000_000,
                "n_channels": 2,
                "n_microtime_channels": _N_MICRO,
                "microtime_resolution": _MICRO_RES_NS,
                "laser_period": _LASER_PERIOD_NS,
                "alex_period": 2 * _DT_MS,
                "alex_markers": False,
                "active_margin": 1.0,
                "fast_grid_bbox": True,
                "max_windows": int(round(self.segment_s * 1000.0 / _DT_MS)),
                "seed_diffusion": self.seed + 7919 * segment,
                "seed_emission": self.seed + 104729 * segment + 1,
            },
            "box": {"xy": 2.0, "z": 4.0},
            "species": species,
            "k_rad": k_rad,
            "k_nrad": k_nrad,
            "background": [r.background_donor_khz, r.background_acceptor_khz],
            "background_decay": {"pattern": [1.0] * _N_MICRO, "dt": _MICRO_RES_NS},
            "population": populations,
            "excitation": [focus, dict(focus, w0=r.focus_w0_um * 1.07)] if pie else focus,
        }
        if not pie:
            for key in ("alex_period", "alex_markers"):
                cfg["settings"].pop(key)
        return cfg

    def _realistic_segment(self, segment: int) -> PhotonBatch:
        """A segment with the record-level imperfections: micro times from the instrument response
        and the lifetimes of each state, brightness heterogeneity, drift, scatter, afterpulses and
        detector dead time. ``truth`` is the population (FRET populations, then donor-only,
        acceptor-only, aggregate); -1 for background, scatter and afterpulses."""
        r = self.realism
        pie = self.scheme == "pie"
        rng = np.random.default_rng([self.seed, segment, 7])
        engine = tttrlib.SimEngine.from_dict(self.config(segment))
        engine.run()
        ph = engine.photons()
        keep = np.asarray(ph["event_type"]) == 0
        window = np.asarray(ph["macro_window"])[keep].astype(np.int64)
        t_ms = window * _DT_MS + np.asarray(ph["arrival_time"])[keep]
        channel = np.asarray(ph["channel"])[keep].astype(np.int64)
        species = np.asarray(ph["species"])[keep].astype(np.int64)
        molecule = np.asarray(ph["molecule"])[keep].astype(np.int64)
        red = ((window % 2) == 1) if pie else np.zeros(len(window), bool)
        n_species = len(self._states)
        signal = (species >= 0) & (species < n_species)
        # brightness heterogeneity and drift: thin each molecule's photons
        keep_p = np.ones(len(t_ms))
        if r.brightness_cv > 0:
            ids, inv = np.unique(molecule[signal], return_inverse=True)
            sigma = np.sqrt(np.log(1.0 + r.brightness_cv**2))
            m_rng = np.random.default_rng([self.seed, 11])
            # a molecule's factor is fixed by its id (and the seed), across segments alike
            factor = np.exp(
                sigma * m_rng.standard_normal(int(ids.max()) + 1 if ids.size else 1) - sigma**2 / 2
            )
            keep_p[signal] = np.minimum(1.0, factor[ids][inv] / (1.0 + 3.0 * r.brightness_cv))
        t_abs_min = (segment * self.segment_s * 1000.0 + t_ms) / 60_000.0
        if r.drift_per_minute:
            # relative intensity 1 + drift x minutes; a rising drift is normalised to its 10-min value
            ref = 1.0 + max(r.drift_per_minute, 0.0) * 10.0
            keep_p[signal] *= np.clip(
                (1.0 + r.drift_per_minute * t_abs_min[signal]) / ref, 0.0, 1.0
            )
        kept = rng.random(len(t_ms)) < keep_p
        t_ms, channel, species, red = t_ms[kept], channel[kept], species[kept], red[kept]
        signal = (species >= 0) & (species < n_species)

        # micro times: pulse + IRF + jitter + the state's decay(s)
        n = len(t_ms)
        sigma_irf = r.irf_fwhm_ns / 2.3548
        jitter = np.where(channel == 0, r.jitter_donor_ns, r.jitter_acceptor_ns)

        def irf(k):
            x = rng.normal(0.0, 1.0, k) * sigma_irf
            tail = rng.random(k) < r.irf_tail_fraction
            x[tail] += rng.exponential(r.irf_tail_ns, int(tail.sum()))
            return x

        t0 = 0.5 + np.where(red, _LASER_PERIOD_NS / 2.0, 0.0)
        t_ns = t0 + irf(n) + rng.normal(0.0, 1.0, n) * jitter
        kind = np.array([s["kind"] for s in self._states] + ["bg"])
        tau_d = np.array(
            [s["tau_donor"] or r.tau_donor_ns for s in self._states] + [r.tau_donor_ns]
        )
        st = np.where(signal, species, n_species)
        sk = kind[st]
        donor_emits = signal & ~red & (channel == 0)
        t_ns[donor_emits] += rng.exponential(tau_d[st[donor_emits]])
        acc_green = signal & ~red & (channel == 1)
        fret = acc_green & (sk == "fret")  # sensitised: donor decay, then the acceptor's
        t_ns[fret] += rng.exponential(tau_d[st[fret]]) + rng.exponential(
            r.tau_acceptor_ns, int(fret.sum())
        )
        leak = acc_green & ((sk == "donor") | (sk == "aggregate"))
        t_ns[leak] += rng.exponential(tau_d[st[leak]])
        direct = (acc_green & (sk == "acceptor")) | (signal & red)
        t_ns[direct] += rng.exponential(r.tau_acceptor_ns, int(direct.sum()))
        t_ns[~signal] = rng.uniform(
            0.0, _LASER_PERIOD_NS, int((~signal).sum())
        )  # uncorrelated background

        # scatter of the donor laser: prompt window, the instrument response only
        span_ms = self.segment_s * 1000.0
        extra_t, extra_ch, extra_micro = [t_ms], [channel], [t_ns]
        for ch, khz in ((0, r.scatter_donor_khz), (1, r.scatter_acceptor_khz)):
            k = int(rng.poisson(khz * span_ms))
            if k:
                ts = np.sort(rng.uniform(0.0, span_ms, k))
                if pie:  # only while the donor laser pulses
                    ts = ts[(np.floor(ts / _DT_MS).astype(np.int64) % 2) == 0]
                extra_t.append(ts)
                extra_ch.append(np.full(len(ts), ch))
                extra_micro.append(0.5 + irf(len(ts)))
        t_ms = np.concatenate(extra_t)
        channel = np.concatenate(extra_ch)
        t_ns = np.concatenate(extra_micro)
        truth = np.full(len(t_ms), -1, np.int64)
        labels = np.array([s["label"] for s in self._states] + [-1], dtype=np.int64)
        truth[: len(st)] = labels[st]
        # afterpulses: a fraction of detections repeats on the same detector a little later
        if r.afterpulse_probability > 0:
            ap = rng.random(len(t_ms)) < r.afterpulse_probability
            k = int(ap.sum())
            t_ms = np.concatenate(
                [t_ms, t_ms[ap] + rng.exponential(r.afterpulse_delay_us * 1e-3, k)]
            )
            channel = np.concatenate([channel, channel[ap]])
            t_ns = np.concatenate([t_ns, rng.uniform(0.0, _LASER_PERIOD_NS, k)])
            truth = np.concatenate([truth, np.full(k, -1, np.int64)])
        order = np.argsort(t_ms, kind="stable")
        t_ms, channel, t_ns, truth = t_ms[order], channel[order], t_ns[order], truth[order]
        # detector dead time: a detection within the dead time after the previous one is lost
        if r.dead_time_ns > 0:
            lost = np.zeros(len(t_ms), bool)
            dead_ms = r.dead_time_ns * 1e-6
            for ch in (0, 1):
                idx = np.flatnonzero(channel == ch)
                gaps = np.diff(t_ms[idx], prepend=-np.inf)
                lost[idx[gaps < dead_ms]] = True
            t_ms, channel, t_ns, truth = t_ms[~lost], channel[~lost], t_ns[~lost], truth[~lost]
        t_ms = t_ms[t_ms < span_ms]
        n = len(t_ms)
        channel, t_ns, truth = channel[:n], t_ns[:n], truth[:n]
        micro = np.floor(np.mod(t_ns, _LASER_PERIOD_NS) / _MICRO_RES_NS).astype(np.int64) % _N_MICRO
        macro = np.floor(t_ms / _MACRO_TICK_MS).astype(np.uint64)
        macro += np.uint64(int(round(segment * self.segment_s * 1000.0 / _MACRO_TICK_MS)))
        return PhotonBatch(
            macro, micro.astype(np.uint16), channel.astype(np.int8), truth.astype(np.int16)
        )

    def _produce(self) -> None:
        try:
            segment = 0
            while not self._stop.is_set():
                if self.duration_s is not None and segment * self.segment_s >= self.duration_s:
                    break
                batch = self.simulate_segment(segment)
                if self.duration_s is not None:
                    limit = int(self.duration_s * 1000.0 / _MACRO_TICK_MS)
                    cut = int(np.searchsorted(batch.macro, np.uint64(limit)))
                    batch = PhotonBatch(
                        batch.macro[:cut], batch.micro[:cut], batch.channel[:cut], batch.truth[:cut]
                    )
                while not self._stop.is_set():
                    try:
                        self._queue.put(batch, timeout=0.2)
                        break
                    except queue.Full:
                        continue
                segment += 1
        except Exception as exc:  # noqa: BLE001 - reported through status(), the reader stops
            self.error = f"{type(exc).__name__}: {exc}"
        finally:
            self._done.set()

    # -- the source interface -----------------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._done.clear()
        self._clock = _Clock(speed=self._clock.speed, realtime=self._clock.realtime)
        self._released_s = 0.0
        self._thread = threading.Thread(target=self._produce, name="sim-pie-source", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def finished(self) -> bool:
        return (
            (self._stop.is_set() or self._done.is_set())
            and self._queue.empty()
            and self._pending is None
        )

    def status(self) -> dict[str, Any]:
        return {"queued": self._queue.qsize(), "dropped": 0, "error": self.error}

    def read(self, timeout: float = 0.2) -> PhotonBatch | None:
        deadline = time.monotonic() + timeout
        while True:
            if self._pending is None:
                try:
                    self._pending = self._queue.get(timeout=max(0.0, deadline - time.monotonic()))
                except queue.Empty:
                    return None
            if self._stop.is_set():
                self._pending = None
                return None
            allowed = self._clock.allowed_s()
            upto = (
                min(allowed, self._released_s + self.batch_s)
                if self._clock.realtime
                else float("inf")
            )
            pending = self._pending
            if upto == float("inf"):
                cut = len(pending)
            else:
                cut = int(
                    np.searchsorted(pending.macro, np.uint64(int(upto / self.info.macro_clock_s)))
                )
            if cut == 0 and len(pending):
                if time.monotonic() >= deadline:
                    return None
                time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
                continue
            out = PhotonBatch(
                pending.macro[:cut], pending.micro[:cut], pending.channel[:cut], pending.truth[:cut]
            )
            rest = PhotonBatch(
                pending.macro[cut:], pending.micro[cut:], pending.channel[cut:], pending.truth[cut:]
            )
            self._pending = rest if len(rest) else None
            if upto != float("inf"):
                self._released_s = upto
            return out


class FileReplaySource(PhotonSource):
    """A recorded measurement played back at measurement speed.

    Parameters
    ----------
    path : str or Path
        A TTTR file or a container member address (``m000.pto/m000.ptu``).
    speed, realtime, batch_s : see :class:`SimulatedPieSource`.
    """

    def __init__(self, path, *, speed: float = 1.0, realtime: bool = True, batch_s: float = 0.1):
        self.path = str(path)
        try:
            from chisurf.core.fio.staging import open_tttr

            self._tttr = open_tttr(self.path)
        except Exception:  # noqa: BLE001 - a plain file opens directly
            self._tttr = tttrlib.TTTR(self.path)
        if self._tttr is None or len(self._tttr) == 0:
            raise SourceUnavailable(f"no photons in {self.path}")
        header = self._tttr.header
        micro_res = float(header.micro_time_resolution) or 1e-12
        n_micro = int(getattr(header, "number_of_micro_time_channels", 0) or 0)
        if n_micro <= 0:
            micro = np.asarray(self._tttr.micro_times)
            n_micro = int(micro.max()) + 1 if len(micro) else 1
        self.info = SourceInfo(
            name=f"Replay: {Path(self.path).name}",
            macro_clock_s=float(header.macro_time_resolution),
            micro_res_s=micro_res,
            n_micro=n_micro,
        )
        self._macro = np.asarray(self._tttr.macro_times).astype(np.uint64)
        self._micro = np.asarray(self._tttr.micro_times).astype(np.uint16)
        self._channel = np.asarray(self._tttr.routing_channels).astype(np.int8)
        #: event type per entry: a scan's markers (type 1) replay with the photons
        self._event = np.asarray(self._tttr.event_types).astype(np.int8)
        self.has_markers = bool(np.any(self._event != 0))
        self._t0 = int(self._macro[0])
        self._clock = _Clock(speed=float(speed), realtime=bool(realtime))
        self.batch_s = float(batch_s)
        self._pos = 0
        self._stop = threading.Event()

    def start(self) -> None:
        self._pos = 0
        self._stop.clear()
        self._clock = _Clock(speed=self._clock.speed, realtime=self._clock.realtime)

    def stop(self) -> None:
        self._stop.set()

    @property
    def finished(self) -> bool:
        return self._stop.is_set() or self._pos >= len(self._macro)

    def read(self, timeout: float = 0.2) -> PhotonBatch | None:
        if self.finished:
            return None
        deadline = time.monotonic() + timeout
        while True:
            if self._clock.realtime:
                upto = self._t0 + int(self._clock.allowed_s() / self.info.macro_clock_s)
                end = int(np.searchsorted(self._macro, np.uint64(upto), side="right"))
            else:
                end = min(len(self._macro), self._pos + 100_000)
            if end > self._pos:
                s = slice(self._pos, end)
                self._pos = end
                return PhotonBatch(
                    self._macro[s], self._micro[s], self._channel[s], event=self._event[s]
                )
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.02)
