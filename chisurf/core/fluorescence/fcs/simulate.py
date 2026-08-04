"""Photon-stream simulator for lifetime-FCS (FLCS) validation and examples.

Wraps ``tttrlib.SimEngine`` to generate a confocal single-molecule photon stream of
several **diffusing** species, each with its own fluorescence lifetime and (optionally)
spontaneous interconversion between states. The output arrays plug straight into the
Qt-free FLCS core :mod:`chisurf.core.fluorescence.fcs.filtered`
(:func:`~chisurf.core.fluorescence.fcs.filtered.calc_ffcs_filters` +
:func:`~chisurf.core.fluorescence.fcs.filtered.species_filtered_correlation`), so the
loop closes: simulate species with distinct lifetimes and diffusion/kinetics, then
recover them by lifetime-filtered correlation.

Unlike the state-exchange simulator in the 2D-FLC plugin (``flc_2d/simulate.py``),
which models only the TCSPC/kinetics axis, this simulator resolves true 3-D diffusion
through a Gaussian focus, so the recovered species carry physical FCS diffusion terms.

Notes
-----
The absolute macro-time is reconstructed from the engine's window index and the
within-window arrival offset (``macro_window * dt + arrival_time``); the micro-times
are read directly from the engine. This native-array path is used instead of the
``SimEngine.to_tttr`` SPC round-trip purely for simplicity and speed — it keeps the
decay on the exact simulated TAC axis and avoids building/reading a hardware record
stream. (``to_tttr`` itself is faithful and yields equally well-conditioned filters.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from chisurf.core.fluorescence.simulation import seeds

__all__ = ["SimulatedLifetimeFCS", "simulate_lifetime_fcs"]


@dataclass
class SimulatedLifetimeFCS:
    """A simulated lifetime-FCS photon stream with ground-truth species labels.

    Attributes
    ----------
    macro_times : numpy.ndarray
        Absolute macro time per photon in ticks of ``macro_time_resolution_s``
        (``uint64``, ascending).
    micro_times : numpy.ndarray
        Micro-time (TAC) channel index per photon.
    species : numpy.ndarray
        Ground-truth emitting species (``0..n_species-1``) per photon.
    macro_time_resolution_s : float
        Seconds per macro-time tick (calibrates the correlation lag axis).
    micro_time_resolution_ns : float
        Nanoseconds per micro-time channel.
    n_microtime_channels : int
        Number of micro-time (TAC) channels.
    reference_decays : list of numpy.ndarray
        Per-species micro-time decay patterns (ground truth); the lifetime-filter
        references. Experimentally these come from pure-species calibration.
    total_decay : numpy.ndarray
        Summed micro-time decay of all species.
    """

    macro_times: np.ndarray
    micro_times: np.ndarray
    species: np.ndarray
    macro_time_resolution_s: float
    micro_time_resolution_ns: float
    n_microtime_channels: int
    reference_decays: list = field(default_factory=list)
    total_decay: np.ndarray = None


def simulate_lifetime_fcs(
    lifetimes_ns,
    diffusion_um2_ms,
    *,
    exchange_rate_ms: float = 0.0,
    brightness_cps=None,
    n_photons: int = 1_000_000,
    seed: int = 1,
    n_microtime_channels: int = 2048,
    micro_time_resolution_ns: float = 0.016,
    macro_time_step_ms: float = 0.005,
    macro_time_resolution_s: float = 1e-7,
    beam_waist_um: float = 0.3,
    box_xy_um: float = 1.5,
    box_z_um: float = 3.0,
    population=None,
    background_cps: float = 2.0,
) -> SimulatedLifetimeFCS:
    """Simulate diffusing lifetime species (with optional interconversion).

    Parameters
    ----------
    lifetimes_ns : sequence of float
        Fluorescence lifetime (ns) of each species.
    diffusion_um2_ms : sequence of float
        Translational diffusion coefficient (um^2/ms) of each species. Its diffusion
        time through the focus is ``tau_D = beam_waist_um**2 / (4 * D)`` (ms).
    exchange_rate_ms : float, optional
        Spontaneous symmetric interconversion rate ``i<->j`` (1/ms) applied to every
        off-diagonal species pair. ``0`` (default) keeps the species static/independent.
    brightness_cps : sequence of float, optional
        Per-species molecular brightness (counts/s). Defaults to ``120`` for each.
    n_photons : int, optional
        Photon budget (the simulation stops once reached).
    seed : int, optional
        RNG seed (deterministic output).
    n_microtime_channels, micro_time_resolution_ns : int, float, optional
        TCSPC/TAC axis. The laser period is ``n_microtime_channels *
        micro_time_resolution_ns``.
    macro_time_step_ms : float, optional
        Simulation integration step (ms).
    macro_time_resolution_s : float, optional
        Tick used for the reconstructed macro-time axis / correlation lags (s).
    beam_waist_um, box_xy_um, box_z_um : float, optional
        Gaussian focus 1/e^2 lateral waist and simulation box dimensions (um).
    population : sequence of float, optional
        Mean number of molecules of each species in the box. Defaults to ``1.5`` each.
    background_cps : float, optional
        Uncorrelated background count rate (counts/s).

    Returns
    -------
    SimulatedLifetimeFCS
    """
    import tttrlib

    tau = [float(t) for t in lifetimes_ns]
    diff = [float(d) for d in diffusion_um2_ms]
    n_species = len(tau)
    if len(diff) != n_species:
        raise ValueError("lifetimes_ns and diffusion_um2_ms must have equal length")
    q = [120.0] * n_species if brightness_cps is None else [float(b) for b in brightness_cps]
    pop = [1.5] * n_species if population is None else [float(p) for p in population]

    laser_ns = n_microtime_channels * micro_time_resolution_ns
    k = float(exchange_rate_ms)
    k_nrad = [0.0 if i == j else k for i in range(n_species) for j in range(n_species)]

    cfg = {
        "settings": {
            "dt": float(macro_time_step_ms), "n_ph_max": int(n_photons), "n_channels": 1,
            "n_microtime_channels": int(n_microtime_channels),
            "microtime_resolution": float(micro_time_resolution_ns),
            "laser_period": float(laser_ns), "fast_grid_bbox": True,
            "active_margin": 1.0,
            # The engine draws molecules and photons from two independent
            # streams, so it takes two seeds. This block used to say "seed",
            # which it never read: every call ran on the defaults and the seed
            # argument did nothing.
            **seeds(int(seed)),
        },
        "box": {"xy": float(box_xy_um), "z": float(box_z_um)},
        "species": [
            {"D": diff[i], "q": [q[i]], "decay": {"lifetimes": [tau[i]]}}
            for i in range(n_species)
        ],
        "k_rad": [0.0] * (n_species * n_species),
        "k_nrad": k_nrad,
        "background": [float(background_cps) / 1000.0],
        "population": pop,
        "excitation": {
            "type": "gaussian3d", "w0": float(beam_waist_um), "z0": 2.0,
            "extent_xy": float(box_xy_um), "extent_z": float(box_z_um), "spacing": 0.1,
        },
    }

    engine = tttrlib.SimEngine.from_dict(cfg)
    engine.run()

    species = np.asarray(engine.emitting_species()).astype(np.int64)
    micro = np.asarray(engine.micro_time()).astype(np.int64)
    # Absolute macro time = window index * step + within-window arrival offset (ms).
    t_ms = (np.asarray(engine.macro_window()).astype(np.float64) * macro_time_step_ms
            + np.asarray(engine.arrival_time()))
    ticks = np.round(t_ms * 1e-3 / macro_time_resolution_s).astype(np.uint64)
    ticks = np.maximum.accumulate(ticks)  # correlation requires ascending macro-times

    # Ground-truth reference decays (only real emitting species; the engine may label
    # background photons with an extra index, which we drop from the references).
    nb = int(n_microtime_channels)
    decays = [
        np.bincount(micro[species == s], minlength=nb)[:nb].astype(float)
        for s in range(n_species)
    ]
    total = np.sum(decays, axis=0)

    return SimulatedLifetimeFCS(
        macro_times=ticks,
        micro_times=micro,
        species=species,
        macro_time_resolution_s=float(macro_time_resolution_s),
        micro_time_resolution_ns=float(micro_time_resolution_ns),
        n_microtime_channels=nb,
        reference_decays=decays,
        total_decay=total,
    )
