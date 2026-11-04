"""A burst session with a known answer: a measurement, its buffer, an IRF and a reference dye.

``make_demo(folder)`` writes four simulated PTU files on one polarisation-resolved detector
(``G|G``: channel 0 parallel, 1 perpendicular) -- what a lab measures in one session:

* ``sample_dsDNA.ptu``: dilute molecules (3 ns) diffusing through the focus, giving bursts;
* ``buffer.ptu``: the buffer alone, a flat background of known rate;
* ``water_irf.ptu``: scatter -- the prompt, a narrow Gaussian -- on that background;
* ``Rh110_ref.ptu``: Rhodamine 110 at nanomolar concentration: 4 ns, rotating within 0.2 ns,
  diffusing with ``D = 430 µm²/s`` through a 3-D Gaussian focus ``w0 = 0.5 µm``,
  ``z0 = 1.5 µm``, the perpendicular channel detected with ``1 / G`` of the parallel's
  efficiency.

The answer is therefore known (:data:`TRUTH`): the reference dye's tail ratio is ``G``, its
correlation gives ``w0``, ``z0`` and ``V_eff = pi^(3/2) w0^2 z0``, the buffer's rate is
``B_G|G``. Diffusion is the TTTR library's photon simulator (3-D Brownian motion through the
focus); the polarisation of each photon is drawn from ``r(t) = r0 exp(-t / rho)`` at its delay,
the prompt is added to the delay. Nothing here is a measurement.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

#: One period of 1024 channels of 32 ps; the macro clock is the laser (32.768 ns).
CHANNELS = 1024
MICRO_S = 32e-12
MACRO_S = MICRO_S * CHANNELS

SETUP: dict[str, Any] = {
    "detectors": {
        "G|G": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}
    },
    "windows": {},
    "tttr_reading": {
        "file_type": "PTU",
        "micro_time_resolution": 32.0,
        "macro_time_resolution": 32.768,
        "micro_time_binning": 2,
        "override_timing": False,
    },
    "apply_lut": False,
    "channel_luts": {},
    "channel_shifts": {},
}

#: The simulation, in one place so the help, the tests and the guide agree.
TRUTH: dict[str, Any] = {
    "version": 3,
    "seed": 11,
    "g_factor": 1.15,
    "w0_um": 0.5,
    "z0_um": 1.5,
    "D_um2_s": 430.0,
    "tau_ns": 4.0,
    "rho_ns": 0.2,
    "r0": 0.38,
    "prompt_ns": 2.0,
    "prompt_sigma_ns": 0.08,
    #: buffer background of each channel, kHz (both detectors' channels: 1.4 kHz on G|G)
    "background_khz": [0.8, 0.6],
    "reference_photons": 600_000,
    "sample_photons": 120_000,
    "buffer_seconds": 20.0,
    "irf_seconds": 5.0,
    "irf_khz": 40.0,
}

FILES = {
    "measurement": "sample_dsDNA.ptu",
    "buffer": "buffer.ptu",
    "irf": "water_irf.ptu",
    "reference": "Rh110_ref.ptu",
}


def demo_folder() -> Path:
    """The settings-owned folder of the demonstration files."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "burst_analysis_samples"


def veff_fl(truth: dict | None = None) -> float:
    """The true effective volume of the simulated focus, fL (µm³)."""
    t = truth or TRUTH
    return float(np.pi ** 1.5 * t["w0_um"] ** 2 * t["z0_um"])


def _write(path: Path, seconds: np.ndarray, micro: np.ndarray, channel: np.ndarray) -> None:
    import tttrlib

    order = np.argsort(seconds, kind="stable")
    macro = np.round(seconds[order] / MACRO_S).astype(np.uint64)
    macro = np.maximum.accumulate(macro)
    stream = tttrlib.TTTR(
        macro,
        (np.asarray(micro)[order] % CHANNELS).astype(np.uint16),
        np.asarray(channel)[order].astype(np.int8),
        np.zeros(macro.size, dtype=np.int8),
    )
    stream.header.set_macro_time_resolution(MACRO_S)
    stream.header.set_micro_time_resolution(MICRO_S)
    stream.header.set_number_of_micro_time_channels(CHANNELS)
    if not stream.write(str(path), "PTU"):
        raise OSError(f"Could not write {path}.")


def _background(rng, seconds: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    times, micro, channel = [], [], []
    for ch, khz in enumerate(TRUTH["background_khz"]):
        n = rng.poisson(khz * 1e3 * seconds)
        times.append(rng.uniform(0.0, seconds, n))
        micro.append(rng.integers(0, CHANNELS, n))
        channel.append(np.full(n, ch))
    return np.concatenate(times), np.concatenate(micro), np.concatenate(channel)


def _diffusing(seed: int, *, tau_ns: float, n_photons: int, population: float, q: float,
               truth: dict | None = None):
    """Times [s] and delays [ns] of photons of molecules diffusing through the focus of *truth*."""
    t = truth or TRUTH
    from chisurf.core.fluorescence.simulation import build_engine, seeds

    cfg = {
        "settings": {
            "dt": 0.002, "n_ph_max": int(n_photons), "max_windows": 10**9, **seeds(seed),
            "n_channels": 1, "per_molecule_skip": False, "n_microtime_channels": CHANNELS,
            "microtime_resolution": MICRO_S * 1e9, "laser_period": MACRO_S * 1e9,
        },
        "box": {"xy": 2.5, "z": 5.0},
        "species": [{"D": t["D_um2_s"] * 1e-3, "q": [float(q)], "decay": {"lifetimes": [tau_ns]}}],
        "k_rad": [0.0], "k_nrad": [0.0], "background": [0.0], "population": [float(population)],
        "excitation": {
            "type": "analytic_gaussian3d", "w0": t["w0_um"], "z0": t["z0_um"], "amplitude": 1.0,
        },
    }
    engine = build_engine(cfg)
    engine.run()
    photons = engine.photons()
    # the window a photon came in and its arrival inside it, both in ms
    window_ms = np.asarray(photons["macro_window"], dtype=float) * cfg["settings"]["dt"]
    seconds = (window_ms + np.asarray(photons["arrival_time"], dtype=float)) * 1e-3
    delay = np.asarray(photons["micro_time"], dtype=float) * MICRO_S * 1e9
    return seconds, delay


def _polarised(rng, delay_ns: np.ndarray, rho_ns: float, truth: dict | None = None):
    """Micro-time channels (prompt added), detection channels (0 VV, 1 VH) and the detected
    mask of photons emitted *delay_ns* after the pulse by a dye rotating with *rho_ns*."""
    t = truth or TRUTH
    r = t["r0"] * np.exp(-delay_ns / rho_ns)
    vv, vh = 1.0 + 2.0 * r, 1.0 - r
    channel = np.where(rng.random(delay_ns.size) < vv / (vv + vh), 0, 1)
    # the channels detect with efficiencies whose ratio is G (the less efficient one is thinned)
    g = float(t["g_factor"])
    efficiency = np.where(channel == 0, min(1.0, g), min(1.0, 1.0 / g))
    detected = rng.random(delay_ns.size) < efficiency
    prompt = rng.normal(t["prompt_ns"], t["prompt_sigma_ns"], delay_ns.size)
    micro = np.round((delay_ns + prompt) / (MICRO_S * 1e9)).astype(np.int64)
    return micro[detected], channel[detected], detected


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> dict[str, Path]:
    """Write the four files (reused when they were written with the same :data:`TRUTH`).

    Returns
    -------
    dict
        ``{sample type: path}``.
    """
    folder = Path(folder) if folder is not None else demo_folder()
    folder.mkdir(parents=True, exist_ok=True)
    paths = {kind: folder / name for kind, name in FILES.items()}
    manifest = folder / "demo.json"
    if not overwrite and manifest.is_file() and all(p.is_file() for p in paths.values()):
        try:
            recorded = json.loads(manifest.read_text())
            hashes = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in paths.items()}
            if recorded.get("truth") == TRUTH and recorded.get("files") == hashes:
                return paths
        except (OSError, ValueError):
            pass
    t = TRUTH
    rng = np.random.default_rng(t["seed"])

    # the reference dye: nanomolar, bright, fast-rotating
    seconds, delay = _diffusing(t["seed"], tau_ns=t["tau_ns"], n_photons=t["reference_photons"],
                                population=20.0, q=400.0)
    micro, channel, kept = _polarised(rng, delay, t["rho_ns"])
    seconds = seconds[kept]
    bt, bm, bc = _background(rng, float(seconds[-1]) if seconds.size else 1.0)
    _write(paths["reference"], np.concatenate([seconds, bt]), np.concatenate([micro, bm]),
           np.concatenate([channel, bc]))

    # the sample: dilute, slower rotation, its bursts on the buffer's background
    seconds, delay = _diffusing(t["seed"] + 1, tau_ns=3.0, n_photons=t["sample_photons"],
                                population=0.15, q=600.0)
    micro, channel, kept = _polarised(rng, delay, 1.5)
    seconds = seconds[kept]
    bt, bm, bc = _background(rng, float(seconds[-1]) if seconds.size else 1.0)
    _write(paths["measurement"], np.concatenate([seconds, bt]), np.concatenate([micro, bm]),
           np.concatenate([channel, bc]))

    # the buffer alone
    _write(paths["buffer"], *_background(rng, t["buffer_seconds"]))

    # scatter: the prompt, both polarisations, on the background
    n = rng.poisson(t["irf_khz"] * 1e3 * t["irf_seconds"])
    st = rng.uniform(0.0, t["irf_seconds"], n)
    sm = np.round(rng.normal(t["prompt_ns"], t["prompt_sigma_ns"], n) / (MICRO_S * 1e9)).astype(np.int64)
    sc = rng.integers(0, 2, n)
    bt, bm, bc = _background(rng, t["irf_seconds"])
    _write(paths["irf"], np.concatenate([st, bt]), np.concatenate([sm, bm]), np.concatenate([sc, bc]))

    hashes = {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in paths.items()}
    manifest.write_text(json.dumps({"truth": t, "setup": SETUP, "files": hashes}, indent=2) + "\n")
    return paths


#: A two-colour PIE setup over the same files: green on channels 0 / 1 in the first half of the
#: period, red on 2 / 3, under green excitation (R|G, first half) and red excitation (R|R,
#: second half).
SETUP_PIE: dict[str, Any] = {
    **SETUP,
    "detectors": {
        "G|G": {"chs": [0, 1], "micro_time_ranges": [[0, 512]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "R|G": {"chs": [2, 3], "micro_time_ranges": [[0, 512]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "R|R": {"chs": [2, 3], "micro_time_ranges": [[512, 1024]], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
    },
}

#: The red reference dye of the PIE setup: Alexa 647 under the red pulse (half a period later),
#: on the red detectors (channels 2 / 3) of a slightly larger red focus.
TRUTH_RED: dict[str, Any] = {
    **TRUTH,
    "seed": 17,
    "g_factor": 0.92,
    "w0_um": 0.6,
    "z0_um": 1.8,
    "D_um2_s": 330.0,
    "tau_ns": 1.0,
    "rho_ns": 0.4,
    "prompt_ns": 18.4,
    "reference_photons": 500_000,
}
RED_FILE = "Alexa647_ref.ptu"


def make_red_reference(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Write the red reference dye of :data:`SETUP_PIE` (:data:`TRUTH_RED`) beside the demo."""
    folder = Path(folder) if folder is not None else demo_folder()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / RED_FILE
    manifest = folder / "demo_red.json"
    if not overwrite and path.is_file() and manifest.is_file():
        try:
            recorded = json.loads(manifest.read_text())
            if recorded.get("truth") == TRUTH_RED and recorded.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest():
                return path
        except (OSError, ValueError):
            pass
    t = TRUTH_RED
    rng = np.random.default_rng(t["seed"])
    seconds, delay = _diffusing(t["seed"], tau_ns=t["tau_ns"], n_photons=t["reference_photons"],
                                population=30.0, q=300.0, truth=t)
    micro, channel, kept = _polarised(rng, delay, t["rho_ns"], truth=t)
    seconds = seconds[kept]
    bt, bm, bc = _background(rng, float(seconds[-1]) if seconds.size else 1.0)
    _write(path, np.concatenate([seconds, bt]), np.concatenate([micro, bm]),
           np.concatenate([channel + 2, bc + 2]))
    manifest.write_text(json.dumps({"truth": t, "setup": SETUP_PIE,
                                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}, indent=2) + "\n")
    return path


__all__ = [
    "FILES", "RED_FILE", "SETUP", "SETUP_PIE", "TRUTH", "TRUTH_RED",
    "demo_folder", "make_demo", "make_red_reference", "veff_fl",
]
