"""A simulated two-colour PIE measurement whose excitation windows are known.

The MT200 case that motivated the tool: 32 ps micro-time channels, 3125 per 100 ns sync period,
the donor laser pulsing at 2 ns and the acceptor laser at 52 ns. Donor excitation lights the
donor detector (routing channel 0) and, by FRET, the acceptor detector (channel 1); acceptor
excitation lights only the acceptor detector. A flat background sits under both.

:data:`TRUTH` holds the pulse positions; :func:`wrong_setup` is a detector setup whose windows
were made for another instrument (50 ps channels, 0–2048 / 2048–4095), the mismatch the check
reports. Nothing here is a measurement: the photons come from a seeded generator.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

STEM = "excitation_windows_demo.ptu"
RESOLUTION_S = 32e-12
N_MICRO = 3125
MACRO_S = RESOLUTION_S * N_MICRO
#: Where the pulses rise (ns) and which detectors they light.
TRUTH = {"donor_pulse_ns": 2.0, "acceptor_pulse_ns": 52.0, "donor_channel": 0,
         "acceptor_channel": 1}
SEED = 20261029


def demo_folder() -> Path:
    """The settings-owned folder of the demo."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "excitation_windows"


def photon_stream(n_photons: int = 300_000, duration_s: float = 3.0, seed: int = SEED):
    """``(macro, micro, routing)`` of the simulated PIE measurement."""
    rng = np.random.default_rng(seed)
    kind = rng.choice(4, n_photons, p=[0.45, 0.25, 0.25, 0.05])  # DD, DA, AA, background
    routing = np.where((kind == 0) | ((kind == 3) & (rng.random(n_photons) < 0.5)), 0, 1)
    t0 = np.where(kind == 2, TRUTH["acceptor_pulse_ns"], TRUTH["donor_pulse_ns"]) * 1e-9
    tau = np.where(kind == 0, 3.8e-9, np.where(kind == 1, 2.5e-9, 3.2e-9))
    t = t0 + rng.normal(0.0, 0.12e-9, n_photons) + rng.exponential(tau)
    t = np.where(kind == 3, rng.uniform(0.0, MACRO_S, n_photons), t)
    micro = np.floor((t % MACRO_S) / RESOLUTION_S).astype(np.uint16)
    macro = np.sort(rng.integers(0, int(duration_s / MACRO_S), n_photons)).astype(np.uint64)
    return macro, micro, routing.astype(np.int8)


def make_demo(folder: Path | None = None) -> Path:
    """Write (or reuse) the demo measurement as a PTU file; returns its path."""
    from chisurf.plugins.tttr import demo_lib

    folder = demo_folder() if folder is None else Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / STEM
    if path.is_file() and path.stat().st_size > 1000:
        return path
    macro, micro, routing = photon_stream()
    cfg = demo_lib.config(macro_resolution_s=MACRO_S, micro_resolution_s=RESOLUTION_S,
                          n_micro=N_MICRO, seed=SEED)
    demo_lib.write_ptu(path, cfg, macro, micro, routing)
    return path


def wrong_setup() -> dict:
    """A detector setup made for another TCSPC (SPC-130, 50 ps, 4096 channels)."""
    return {
        "detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}},
        "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
        "tttr_reading": {"micro_time_resolution": 50.0, "macro_time_resolution": 50.0},
    }
