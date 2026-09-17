"""Photon-stream simulator for 2D-FLC (port of ``TK_MyMain_Simu_PhotonStream``).

Generates a TTTR-like single-molecule photon stream from an ``n``-state exchange process:
each state has a fluorescence lifetime and brightness, and the states interconvert
according to a rate matrix. The output is exactly what the rest of the plugin consumes —
macro-time ticks, micro-time (TCSPC) ticks and the (ground-truth) state per photon — so it
closes the loop for validation: simulate, then recover the lifetimes and rate matrix.

The MATLAB reference advances a fixed ``Tstep`` and tests for a transition/emission every
step. The physics is not implemented here: it is expressed for the photon simulator in the
TTTR library, which walks the continuous-time Markov chain itself and draws each photon's
micro time from that state's decay.

The expression is the whole content of this module. A 2D-FLC measurement is one
**immobile** molecule — no diffusion, no focus to cross — so each conformational state
becomes a species with its own brightness and its own IRF-convolved decay, the states are
connected by ``k_nrad`` (spontaneous, not excitation-scaled), and the molecule is placed as
a discrete emitter rather than drawn from a population. See
``okf/references/simengine-species-encoding.md``: the recurring mistake is to look for a
parameter named after the phenomenon rather than to encode it.

One conversion is load-bearing. This module's rate matrix is ``K[from, to]`` — the
row convention the MATLAB reference used and the transpose of the one the rest of ChiSurf
uses — and the engine wants row-major source-to-target per macro-time unit, so the values
pass through unchanged in *orientation* while being rescaled from 1/s.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .fit.kinetics import equilibrium_populations

__all__ = ["SimulatedStream", "simulate_photon_stream", "dwell_time_histogram"]


@dataclass
class SimulatedStream:
    """A simulated TTTR photon stream with ground-truth state labels."""

    macro_times: np.ndarray  # int64 macro ticks (resolution = macro_time_resolution_s)
    micro_times: np.ndarray  # int64 TCSPC channel indices (resolution = tstep_ns)
    states: np.ndarray  # int per-photon state (ground truth)
    macro_time_resolution_s: float
    micro_time_resolution_ns: float
    n_microtime_channels: int
    equilibrium_populations: np.ndarray


def simulate_photon_stream(
    rate_matrix: np.ndarray,
    lifetimes_ns,
    intensities_cps,
    *,
    total_time_s: float = 100.0,
    irf: np.ndarray | None = None,
    irf_time_ns: np.ndarray | None = None,
    macro_time_resolution_s: float = 1e-6,
    tstep_ns: float = 0.004,
    n_microtime_channels: int = 3127,
    seed: int = 0,
    max_photons: int = 50_000_000,
) -> SimulatedStream:
    """Simulate a single-molecule photon stream from an n-state exchange process.

    Parameters
    ----------
    rate_matrix
        ``K[n, m]`` = rate of ``n -> m`` (1/s); diagonal ignored.
    lifetimes_ns
        Fluorescence lifetime of each state (ns).
    intensities_cps
        Brightness of each state (counts per second).
    total_time_s
        Total acquisition time to simulate.
    irf, irf_time_ns
        Optional instrument response and its ns axis. Without an IRF a delta at t=0 is used.
    macro_time_resolution_s, tstep_ns, n_microtime_channels
        TTTR/TCSPC calibration of the output.
    seed
        RNG seed (deterministic output).
    max_photons
        Safety cap on the number of photons generated (stops early if exceeded).
    """
    from chisurf.core.fluorescence.simulation import build_engine, seeds

    K = np.asarray(rate_matrix, dtype=float)
    n_states = K.shape[0]
    tau = np.asarray(lifetimes_ns, dtype=float)
    inten = np.asarray(intensities_cps, dtype=float)
    p_eq = equilibrium_populations(K)

    # The engine's clock. One macro-time unit is the output tick, so a rate in
    # 1/s becomes a rate per tick, and a brightness in counts/s likewise.
    dt_s = float(macro_time_resolution_s)

    # k_nrad is row-major source -> target, which is this module's own
    # orientation; only the diagonal is dropped and the scale converted.
    exchange = K.copy()
    np.fill_diagonal(exchange, 0.0)
    exchange = exchange * dt_s

    # The engine draws a micro time from a pattern of finite length, so a pattern
    # exactly as long as the output window *truncates* the decay and its mean
    # comes out short (3.00 ns reads as 2.80). This simulator has always drawn an
    # unbounded exponential and clipped it into the last channel, which is a
    # different estimator, so the pattern is built far longer than the window and
    # the clip below does the rest.
    n_pattern = int(n_microtime_channels) * 64
    decay = {"dt": float(tstep_ns), "n_bins": n_pattern}
    if irf is not None and irf_time_ns is not None:
        # The engine convolves with a pattern on its own micro-time grid, so the
        # response is resampled onto that grid rather than being sampled from.
        weights = np.clip(np.asarray(irf, dtype=float), 0.0, None)
        axis = np.asarray(irf_time_ns, dtype=float)
        grid = np.arange(int(n_microtime_channels)) * float(tstep_ns)
        resampled = np.interp(grid, axis, weights, left=0.0, right=0.0)
        total = float(resampled.sum())
        if total > 0:
            decay["irf"] = [float(v) for v in resampled / total]

    config = {
        "settings": {
            "dt": 1.0,  # one macro-time unit per output tick
            "n_ph_max": int(max_photons),
            "max_windows": max(1, int(round(float(total_time_s) / dt_s))),
            "n_channels": 1,
            "n_microtime_channels": n_pattern,
            "microtime_resolution": float(tstep_ns),
            # Matches the pattern, so nothing wraps either; the window is the
            # clip below, as it always was here.
            "laser_period": float(n_pattern) * float(tstep_ns),
            **seeds(int(seed)),
        },
        "box": {"xy": 1.0, "z": 1.0},
        "species": [
            {
                "D": 0.0,
                "q": [float(inten[i]) * dt_s],
                "decay": {**decay, "lifetimes": [float(tau[i])]},
            }
            for i in range(n_states)
        ],
        "k_rad": [0.0] * (n_states * n_states),
        "k_nrad": [float(v) for v in exchange.reshape(-1)],
        "background": [0.0],
        # One immobile molecule, started in a state drawn from equilibrium. A
        # population would let molecules enter and leave, which is diffusion.
        "emitters": [
            {
                "x": 0.0,
                "y": 0.0,
                "z": 0.0,
                "species": int(np.random.default_rng(seed).choice(n_states, p=p_eq)),
                "mobile": False,
            }
        ],
        "excitation": {"type": "uniform", "value": 1.0},
    }

    engine = build_engine(config)
    engine.run()

    window = np.asarray(engine.macro_window(), dtype=np.float64)
    arrival = np.asarray(engine.arrival_time(), dtype=np.float64)
    macro = np.rint(window + arrival).astype(np.int64)
    micro = np.asarray(engine.micro_time(), dtype=np.int64)
    states = np.asarray(engine.emitting_species(), dtype=np.int16)

    # Background photons carry a species index past the real ones; there is no
    # background here, but the guard keeps a stray one out of the ground truth.
    real = states < n_states
    macro, micro, states = macro[real], micro[real], states[real]

    order = np.argsort(macro, kind="stable")  # macro times must be ascending
    macro, micro, states = macro[order], micro[order], states[order]
    np.clip(micro, 0, int(n_microtime_channels) - 1, out=micro)

    return SimulatedStream(
        macro_times=macro,
        micro_times=micro,
        states=states,
        macro_time_resolution_s=macro_time_resolution_s,
        micro_time_resolution_ns=tstep_ns,
        n_microtime_channels=n_microtime_channels,
        equilibrium_populations=p_eq,
    )


def dwell_time_histogram(
    states: np.ndarray,
    macro_times: np.ndarray,
    macro_time_resolution_s: float,
    *,
    bin_s: float = 0.01,
    n_states: int | None = None,
):
    """Per-transition dwell-time histograms (port of the simulator's dwell check).

    Returns ``(centers_s, hist)`` where ``hist[n, m]`` is the dwell-time histogram of
    sojourns in state ``n`` that end in a transition to state ``m``.
    """
    states = np.asarray(states)
    t = np.asarray(macro_times, dtype=float) * macro_time_resolution_s
    if n_states is None:
        n_states = int(states.max()) + 1 if states.size else 1
    change = np.flatnonzero(np.diff(states) != 0)
    dwells = {}  # (n, m) -> list of dwell times
    start_t = t[0] if t.size else 0.0
    prev = states[0] if states.size else 0
    for idx in change:
        n = int(prev)
        m = int(states[idx + 1])
        dwell = t[idx] - start_t
        dwells.setdefault((n, m), []).append(dwell)
        start_t = t[idx + 1]
        prev = m

    all_d = [d for lst in dwells.values() for d in lst]
    t_max = max(all_d) if all_d else bin_s
    edges = np.arange(0.0, t_max + bin_s, bin_s)
    centers = 0.5 * (edges[:-1] + edges[1:])
    hist = np.zeros((n_states, n_states, centers.size))
    for (n, m), lst in dwells.items():
        hist[n, m] = np.histogram(lst, bins=edges)[0]
    return centers, hist
