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

from pathlib import Path

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


def photon_stream(seed: int = SEED, seconds: float = SECONDS):
    """The simulated photons: ``(macro_times, routing_channels, species_of_each_burst)``."""
    rng = np.random.default_rng(seed)
    span = int(seconds / MACRO_RES)
    n_bursts = int(rng.poisson(BURST_RATE * seconds))
    edge = 0.002 / MACRO_RES
    centres = np.sort(rng.uniform(edge, span - edge, n_bursts))
    weights = np.array([s[4] for s in SPECIES], dtype=float)
    kinds = rng.choice(len(SPECIES), n_bursts, p=weights / weights.sum())
    times, channels = [], []
    for centre, kind in zip(centres, kinds):
        _name, has_donor, has_acceptor, efficiency, _w = SPECIES[kind]
        n = int(rng.integers(*PHOTONS_PER_BURST))
        t = rng.normal(centre, 0.3e-3 / MACRO_RES, n)
        phase = np.mod(t, PERIOD)
        donor_exc = (phase >= DONOR_GATE[0]) & (phase < DONOR_GATE[1])
        acceptor_exc = (phase >= ACCEPTOR_GATE[0]) & (phase < ACCEPTOR_GATE[1])
        detector = np.full(n, -1)
        u = rng.random(n)
        if has_donor:
            # donor excitation: the donor emits, or transfers to the acceptor with probability E
            detector[donor_exc] = np.where(u[donor_exc] < efficiency, ACCEPTOR_CHANNEL, DONOR_CHANNEL)
        else:
            # direct excitation of the acceptor by the donor laser (a few per cent)
            detector[donor_exc] = np.where(u[donor_exc] < 0.06, ACCEPTOR_CHANNEL, -1)
        if has_acceptor:
            detector[acceptor_exc] = ACCEPTOR_CHANNEL
        else:
            detector[acceptor_exc] = np.where(u[acceptor_exc] < 0.02, DONOR_CHANNEL, -1)
        keep = detector >= 0
        times.append(t[keep])
        channels.append(detector[keep])
    n_background = int(rng.poisson(BACKGROUND_HZ * seconds))
    times.append(rng.uniform(0, span, n_background))
    channels.append(rng.integers(0, 2, n_background))
    t = np.clip(np.concatenate(times), 0, span - 1).astype(np.uint64)
    c = np.concatenate(channels).astype(np.int8)
    order = np.argsort(t, kind="stable")
    return t[order], c[order], kinds


def make_demo(folder, seed: int = SEED) -> Path:
    """Write the demonstration µs-ALEX measurement into *folder*; return its path."""
    import tttrlib

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    macro, routing, _kinds = photon_stream(seed)
    stream = tttrlib.TTTR()
    stream.append_events(macro, np.zeros(macro.size, dtype=np.uint16), routing, np.zeros(macro.size, dtype=np.int8))
    header = stream.header
    header.set_macro_time_resolution(MACRO_RES)
    header.set_micro_time_resolution(MACRO_RES / 4096)
    path = folder / STREAM_NAME
    if not stream.write(str(path), "SPC-130", header):
        raise OSError(f"could not write {path}")
    return path


__all__ = ["PERIOD", "SPECIES", "make_demo", "photon_stream"]
