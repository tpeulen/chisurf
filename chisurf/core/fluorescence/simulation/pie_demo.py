"""A simulated two-colour PIE measurement whose excitation windows are known (PTU, tttrlib).

The MT200 case that motivated the tool: 32 ps micro-time channels, 3125 per 100 ns sync period,
the donor laser pulsing at 2 ns and the acceptor laser at 52 ns. Donor excitation lights the
donor detector (routing channel 0) and, by FRET, the acceptor detector (channel 1); acceptor
excitation lights only the acceptor detector. A flat background sits under both.

:data:`TRUTH` holds the pulse positions; :func:`wrong_setup` is a detector setup whose windows
were made for another instrument (50 ps channels, 0–2048 / 2048–4095), the mismatch the check
reports. Nothing here is a measurement: the photons come from a seeded generator. The Excitation
Windows tool's *Load example* and the window pre-flight tests of every tool use it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from chisurf.core.fluorescence.detector_names import ACCEPTOR, DONOR

STEM = "excitation_windows_demo.ptu"
DONOR_ONLY_STEM = "excitation_windows_demo_donor_only.ptu"
RESOLUTION_S = 32e-12
N_MICRO = 3125
MACRO_S = RESOLUTION_S * N_MICRO
#: Where the pulses rise (ns) and which detectors they light.
TRUTH = {"donor_pulse_ns": 2.0, "acceptor_pulse_ns": 52.0, "donor_channel": 0,
         "acceptor_channel": 1}
SEED = 20261029


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


def make_demo(folder: Path, *, donor_only: bool = False, n_photons: int = 300_000,
              name: str | None = None) -> Path:
    """Write (or reuse) the simulated PIE measurement as a PTU file in *folder*; its path.

    *donor_only* drops the acceptor-excitation photons (a donor-only sample: one pulse).
    """
    import tttrlib

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name or (DONOR_ONLY_STEM if donor_only else STEM))
    if path.is_file() and path.stat().st_size > 1000:
        return path
    macro, micro, routing = photon_stream(n_photons)
    if donor_only:
        t_ns = micro.astype(float) * RESOLUTION_S * 1e9
        keep = ~((routing == TRUTH["acceptor_channel"]) & (t_ns > TRUTH["acceptor_pulse_ns"] - 1))
        macro, micro, routing = macro[keep], micro[keep], routing[keep]
    stream = tttrlib.TTTR()
    stream.append_events(macro, micro, routing.astype(np.int8), np.zeros(macro.size, np.int8))
    header = stream.header
    header.set_macro_time_resolution(MACRO_S)
    header.set_micro_time_resolution(RESOLUTION_S)
    header.set_number_of_micro_time_channels(N_MICRO)
    if not stream.write(str(path), "PTU", header):
        raise OSError(f"could not write the PIE demo to {path}")
    return path


def wrong_setup() -> dict:
    """A detector setup made for another TCSPC (SPC-130, 50 ps, 4096 channels)."""
    return {
        "detectors": {DONOR: {"chs": [0]}, ACCEPTOR: {"chs": [1]}},
        "windows": {"prompt": [0, 2048], "delayed": [2048, 4095]},
        "tttr_reading": {"micro_time_resolution": 50.0, "macro_time_resolution": 50.0},
    }
