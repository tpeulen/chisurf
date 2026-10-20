"""A deterministic µs-ALEX demonstration measurement the ALEX Suite can generate itself.

``make_demo(folder)`` writes ``alex_demo.spc`` (a Becker & Hickl SPC-130 file) holding a simulated µs-ALEX photon
stream whose alternation is still in the **macro time** (every micro-time is 0), which is what an unconverted
µs-ALEX measurement looks like: the alternation step must find the period, the gates and the channel assignment and
fold them into the micro-time before a burst search can use the excitation windows. Nothing here is a measurement;
the numbers are planted so the answer is known:

* macro-time tick 12.5 ns, alternation period :data:`PERIOD` = 8000 ticks (100 µs);
* donor laser on in phase [0, 3900), acceptor laser on in [4000, 7900) (100-tick laser-off gaps);
* donor detector = routing channel 0, acceptor detector = channel 1;
* single molecules crossing the focus (Gaussian envelope, 0.3 ms wide) at :data:`BURST_RATE` per second, of four
  species (:data:`SPECIES`): low FRET (E = 0.25), high FRET (E = 0.75), donor only and acceptor only, so the E-S
  histogram shows the classic four populations;
* a uniform background of :data:`BACKGROUND_HZ` photons per second over both detectors and every phase.

The photons are drawn from a seeded generator, so the file is the same on every run.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any, TypedDict

import numpy as np

SEED = 20261006
MACRO_RES = 12.5e-9
PERIOD = 8000
DONOR_GATE = (0, 3900)
ACCEPTOR_GATE = (4000, 7900)
DONOR_CHANNEL = 0
ACCEPTOR_CHANNEL = 1
SECONDS = 20.0
BURST_RATE = 25.0
BACKGROUND_HZ = 3000.0
#: (name, has donor, has acceptor, FRET efficiency, fraction of the molecules)
SPECIES = (
    ("low FRET", True, True, 0.25, 0.35),
    ("high FRET", True, True, 0.75, 0.35),
    ("donor only", True, False, 0.0, 0.15),
    ("acceptor only", False, True, 0.0, 0.15),
)
#: Photons a molecule emits on one crossing (uniform between the two).
PHOTONS_PER_BURST = (150, 450)
STREAM_NAME = "alex_demo.spc"


class DemoConfig(TypedDict):
    """The generator's parameters, as recorded in ``alex_demo.json`` (JSON shapes: lists)."""

    seed: int
    seconds: float
    macro_resolution_s: float
    period: int
    donor_gate: list[int]
    acceptor_gate: list[int]
    donor_channel: int
    acceptor_channel: int
    burst_rate: float
    background_hz: float
    species: list[list[Any]]
    photons_per_burst: list[int]


#: The declared fixture: :func:`photon_stream` draws from it and :func:`make_demo` regenerates
#: the stream whenever it differs from the one recorded beside the file.
DEMO: DemoConfig = {
    "seed": SEED,
    "seconds": SECONDS,
    "macro_resolution_s": MACRO_RES,
    "period": PERIOD,
    "donor_gate": list(DONOR_GATE),
    "acceptor_gate": list(ACCEPTOR_GATE),
    "donor_channel": DONOR_CHANNEL,
    "acceptor_channel": ACCEPTOR_CHANNEL,
    "burst_rate": BURST_RATE,
    "background_hz": BACKGROUND_HZ,
    "species": [list(species) for species in SPECIES],
    "photons_per_burst": list(PHOTONS_PER_BURST),
}


def demo_folder() -> Path:
    """Return the plugin's generated-data folder in the current settings tree."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "alex_suite"


def photon_stream(
    seed: int = SEED, seconds: float | None = None, *, config: DemoConfig | None = None
):
    """The simulated photons: ``(macro_times, routing_channels, species_of_each_burst)``.

    Drawn from *config* (the declared :data:`DEMO` by default); *seconds* overrides its duration.
    """
    values = DEMO.copy() if config is None else config
    macro_res = float(values["macro_resolution_s"])
    period = int(values["period"])
    donor_gate = values["donor_gate"]
    acceptor_gate = values["acceptor_gate"]
    donor_channel = int(values["donor_channel"])
    acceptor_channel = int(values["acceptor_channel"])
    species = values["species"]
    photons_per_burst = values["photons_per_burst"]
    seconds = float(values["seconds"] if seconds is None else seconds)
    rng = np.random.default_rng(seed)
    span = int(seconds / macro_res)
    n_bursts = int(rng.poisson(float(values["burst_rate"]) * seconds))
    edge = 0.002 / macro_res
    centres = np.sort(rng.uniform(edge, span - edge, n_bursts))
    weights = np.array([s[4] for s in species], dtype=float)
    kinds = rng.choice(len(species), n_bursts, p=weights / weights.sum())
    times: list[np.ndarray] = []
    channels: list[np.ndarray] = []
    for centre, kind in zip(centres, kinds):
        _name, has_donor, has_acceptor, efficiency, _w = species[kind]
        n = int(rng.integers(int(photons_per_burst[0]), int(photons_per_burst[1])))
        t = rng.normal(centre, 0.3e-3 / macro_res, n)
        phase = np.mod(t, period)
        donor_exc = (phase >= donor_gate[0]) & (phase < donor_gate[1])
        acceptor_exc = (phase >= acceptor_gate[0]) & (phase < acceptor_gate[1])
        detector = np.full(n, -1)
        u = rng.random(n)
        if has_donor:
            # donor excitation: the donor emits, or transfers to the acceptor with probability E
            detector[donor_exc] = np.where(
                u[donor_exc] < efficiency, acceptor_channel, donor_channel
            )
        else:
            # direct excitation of the acceptor by the donor laser (a few per cent)
            detector[donor_exc] = np.where(u[donor_exc] < 0.06, acceptor_channel, -1)
        if has_acceptor:
            detector[acceptor_exc] = acceptor_channel
        else:
            detector[acceptor_exc] = np.where(u[acceptor_exc] < 0.02, donor_channel, -1)
        keep = detector >= 0
        times.append(t[keep])
        channels.append(detector[keep])
    n_background = int(rng.poisson(float(values["background_hz"]) * seconds))
    times.append(rng.uniform(0, span, n_background))
    channels.append(rng.integers(0, 2, n_background))
    t = np.clip(np.concatenate(times), 0, span - 1).astype(np.uint64)
    c = np.concatenate(channels).astype(np.int8)
    order = np.argsort(t, kind="stable")
    return t[order], c[order], kinds


def make_demo(
    folder: str | Path | None = None, *, overwrite: bool = False, seed: int = SEED
) -> Path:
    """Write or reuse the known µs-ALEX stream, with its settings and integrity sidecar."""
    import tttrlib

    folder = Path(folder) if folder is not None else demo_folder()
    path = folder / STREAM_NAME
    sidecar = folder / "alex_demo.json"
    settings: DemoConfig = {**DEMO, "seed": seed}
    if not overwrite and path.is_file() and sidecar.is_file():
        try:
            metadata = json.loads(sidecar.read_text())
            if metadata.get("settings") == settings and metadata.get("files") == {
                STREAM_NAME: hashlib.sha256(path.read_bytes()).hexdigest()
            }:
                return path
        except (OSError, ValueError):
            pass
    folder.mkdir(parents=True, exist_ok=True)
    macro, routing, kinds = photon_stream(seed, config=settings)
    stream = tttrlib.TTTR()
    stream.append_events(
        macro, np.zeros(macro.size, dtype=np.uint16), routing, np.zeros(macro.size, dtype=np.int8)
    )
    header = stream.header
    header.set_macro_time_resolution(settings["macro_resolution_s"])
    header.set_micro_time_resolution(settings["macro_resolution_s"] / 4096)
    with tempfile.TemporaryDirectory(prefix=".alex-demo-", dir=folder) as temporary:
        generated = Path(temporary) / STREAM_NAME
        if not stream.write(str(generated), "SPC-130", header):
            raise OSError(f"could not write {path}")
        metadata = {
            "settings": settings,
            "files": {STREAM_NAME: hashlib.sha256(generated.read_bytes()).hexdigest()},
            "truth": {
                "species_counts": np.bincount(kinds, minlength=len(SPECIES)).tolist(),
                "qualification": "Synthetic input populations, not acquisition calibration.",
            },
        }
        record = Path(temporary) / sidecar.name
        record.write_text(json.dumps(metadata, indent=2) + "\n")
        generated.replace(path)
        record.replace(sidecar)
    return path


__all__ = ["DEMO", "DemoConfig", "PERIOD", "SPECIES", "demo_folder", "make_demo", "photon_stream"]
