"""Small simulated photon streams with a known FCS answer, written as SPC files."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..demo import DEMO, photon_stream


def write_spc(folder: Path, name: str, macro, micro, routing) -> Path:
    """Write ``(macro, micro, routing)`` as an SPC-130 file with the demo's header."""
    import tttrlib

    stream = tttrlib.TTTR()
    stream.append_events(macro, micro, routing, np.zeros(len(macro), dtype=np.int8))
    header = stream.header
    header.set_macro_time_resolution(DEMO["macro_resolution_s"])
    header.set_micro_time_resolution(DEMO["micro_resolution_s"])
    path = Path(folder) / name
    assert stream.write(str(path), DEMO["format"], header)
    return path


def diffusion_spc(
    folder: Path, name: str, *, rate_hz: float, duration_s: float = 2.0, seed: int = 7
) -> Path:
    """Molecules crossing the focus at ``rate_hz`` (the demo's crossing, shorter run)."""
    config = DEMO.copy()
    config["molecule_rate_hz"] = rate_hz
    config["duration_s"] = duration_s
    return write_spc(folder, name, *photon_stream(seed, config=config))


def poisson_spc(
    folder: Path, name: str, *, rate_hz: float = 60000.0, duration_s: float = 2.0, seed: int = 3
) -> Path:
    """A constant-rate Poisson stream split at random over two detectors: G must be 1 at every lag."""
    rng = np.random.default_rng(seed)
    times = np.sort(rng.uniform(0.0, duration_s, rng.poisson(rate_hz * duration_s)))
    macro = np.round(times / DEMO["macro_resolution_s"]).astype(np.uint64)
    micro = rng.integers(0, DEMO["micro_channels"], len(macro)).astype(np.uint16)
    routing = rng.integers(0, 2, len(macro)).astype(np.int8)
    return write_spc(folder, name, macro, micro, routing)


def expected_amplitude(rate_hz: float) -> float:
    """G(0) - 1 for the demo's crossing, cross-correlating its two detectors (background included)."""
    sigma, photons = DEMO["transit_s"], DEMO["photons_per_transit"]
    n_effective = rate_hz * 2.0 * sigma * np.sqrt(np.pi)
    signal = rate_hz * photons
    return float((signal / (signal + DEMO["background_hz"])) ** 2 / n_effective)
