"""Simulated confocal smFRET measurements (tttrlib's photon simulator).

Each :class:`Scenario` is one instrument and sample: excitation (cw, PIE with
any two pulse positions, µsALEX with or without micro times), detectors
(routing numbers, polarization, extra dark/scatter channels) and the sample
(FRET populations, donor-only, acceptor-only, background). :func:`simulate`
turns it into a ``tttrlib.TTTR``. The tests run detection over a matrix of
them; the page offers them as demo data.

How each excitation is made with ``tttrlib.SimEngine``:

* **cw** -- one run, every species emitting under the donor laser.
* **µsALEX** -- one run with two excitation grids and ``alex_period``; each
  species has ``q_alex = [[DD, DA], [AD, AA]]`` rows per laser.
* **PIE** -- one run whose channels are detector x PIE window (the
  simulator's own convention): channels ``0..n-1`` carry each molecule's
  emission after the donor pulse, ``n..2n-1`` after the acceptor pulse. The
  latter are shifted in micro time by the pulse delay and folded back onto
  their detector, so both pulses see the very same molecule.
"""
from __future__ import annotations

import dataclasses

import numpy as np

__all__ = ["Scenario", "SCENARIOS", "simulate"]

#: Macro-time clock of the synthetic files (80 MHz, as PicoQuant/BH).
MACRO_RES = 12.5e-9
DT_MS = 0.01  # simulator window: 10 µs


@dataclasses.dataclass
class Scenario:
    name: str
    excitation: str = "cw"  # "cw" | "pie" | "usalex"
    #: Routing numbers of the donor and acceptor detectors; two per colour =
    #: polarization resolved, ``[parallel, perpendicular]``.
    donor: tuple = (0,)
    acceptor: tuple = (1,)
    #: Extra channels with only uncorrelated counts: ``{routing: rate_hz}``.
    extra: dict = dataclasses.field(default_factory=dict)
    #: FRET populations: ``(E, fraction)``.
    populations: tuple = ((0.25, 0.4), (0.75, 0.4))
    donor_only: float = 0.2
    acceptor_only: float = 0.0
    laser_period_ns: float = 32.0
    donor_pulse_ns: float = 2.0
    acceptor_pulse_ns: float = 18.0
    alex_period_us: float = 100.0
    #: µsALEX only: keep the TCSPC micro time (else zero, like a .sm file).
    keep_micro: bool = True
    duration_s: float = 5.0
    molecules: float = 2.0  # mean molecules in the simulation box
    brightness: float = 1000.0  # per window at the focus centre, donor excitation
    background: float = 0.02
    seed: int = 1

    @property
    def n_det(self) -> int:
        return len(self.donor) + len(self.acceptor)


def _split(n: int, par: float) -> list[float]:
    return [1.0] if n == 1 else [par, 1.0 - par]


def _species(sc: Scenario):
    """``(fraction, green_q, red_q, tau_green, tau_red)`` per species."""
    b, nd, na = sc.brightness, len(sc.donor), len(sc.acceptor)
    sd, sa = _split(nd, 0.6), _split(na, 0.55)
    leak, direct, b_aa = 0.06, 0.05, 0.8 * sc.brightness
    out = []
    for e, frac in sc.populations:
        green = [(1 - e) * b * f for f in sd] + [(e + leak * (1 - e)) * b * f for f in sa]
        red = [0.0] * nd + [b_aa * f for f in sa]
        out.append((frac, green, red, max(4.0 * (1 - e), 0.3), 3.0))
    if sc.donor_only > 0:
        out.append((sc.donor_only, [b * f for f in sd] + [leak * b * f for f in sa], [0.0] * nd + [0.0] * na,
                    4.0, 3.0))
    if sc.acceptor_only > 0:
        out.append((sc.acceptor_only, [0.0] * nd + [direct * b_aa * f for f in sa],
                    [0.0] * nd + [b_aa * f for f in sa], 3.0, 3.0))
    return out


def _config(sc: Scenario, species, alex=False, pie=False):
    n = sc.n_det * (2 if pie else 1)
    total = sum(s[0] for s in species)
    cfg = {
        "settings": {
            "dt": DT_MS, "n_channels": n, "n_microtime_channels": 4096,
            "microtime_resolution": sc.laser_period_ns / 4096, "laser_period": sc.laser_period_ns,
            "max_windows": int(round(sc.duration_s / (DT_MS * 1e-3))), "per_molecule_skip": True,
            "active_margin": 1.0, "fast_grid_bbox": True,
            "seed_diffusion": 1000 + sc.seed, "seed_emission": 5000 + sc.seed,
        },
        "box": {"xy": 2.0, "z": 4.0},
        "k_rad": [0, 0, 0, 0], "k_nrad": [0, 0, 0, 0],
        "background": [sc.background / (2 if pie else 1)] * n,
        "background_decay": {"pattern": [1.0], "dt": sc.laser_period_ns},
        "population": [sc.molecules * s[0] / total for s in species],
        "species": [],
    }
    grid = {"type": "gaussian3d", "w0": 0.3, "z0": 2.0, "extent_xy": 2.0, "extent_z": 4.0, "spacing": 0.1}
    for frac, green, red, tau_g, tau_r in species:
        sp = {"D": 0.05, "decay": {"lifetimes": [tau_g], "amplitudes": [1.0], "dt": 0.008,
                                    "t0": sc.donor_pulse_ns}}
        if alex:
            sp["q_alex"] = [green, red]
        elif pie:
            sp["q"] = [max(v, 1e-9) for v in green + red]
        else:
            sp["q"] = [max(v, 1e-9) for v in green]
        cfg["species"].append(sp)
    if alex:
        cfg["settings"]["alex_period"] = sc.alex_period_us * 1e-3  # ms, the dt unit
        cfg["excitation"] = [grid, dict(grid, w0=0.32, z0=2.1)]
    else:
        cfg["excitation"] = grid
    return cfg


def _run(cfg):
    import tttrlib  # noqa: PLC0415

    eng = tttrlib.SimEngine.from_dict(cfg)
    eng.run()
    ph = eng.photons()
    m = np.asarray(ph["event_type"]) == 0
    t_ms = np.asarray(ph["macro_window"])[m] * DT_MS + np.asarray(ph["arrival_time"])[m]
    return t_ms * 1e-3, np.asarray(ph["micro_time"])[m], np.asarray(ph["channel"])[m]


def simulate(sc: Scenario):
    """The scenario as a ``tttrlib.TTTR`` (in memory)."""
    import tttrlib  # noqa: PLC0415

    species = _species(sc)
    if sc.excitation == "cw":
        parts = [_run(_config(sc, species))]
    elif sc.excitation == "pie":
        t, micro, ch = _run(_config(sc, species, pie=True))
        late = ch >= sc.n_det
        shift = int(round((sc.acceptor_pulse_ns - sc.donor_pulse_ns) * 4096 / sc.laser_period_ns))
        micro = np.where(late, (micro.astype(np.int64) + shift) % 4096, micro)
        parts = [(t, micro, np.where(late, ch - sc.n_det, ch))]
    elif sc.excitation == "usalex":
        parts = [_run(_config(sc, species, alex=True))]
    else:
        raise ValueError(f"unknown excitation {sc.excitation!r}")
    t = np.concatenate([p[0] for p in parts])
    micro = np.concatenate([p[1] for p in parts]).astype(np.int64)
    sim_ch = np.concatenate([p[2] for p in parts]).astype(np.int64)
    routing_of = np.array(list(sc.donor) + list(sc.acceptor), np.int64)
    routing = routing_of[sim_ch]
    # Extra channels: uncorrelated counts, flat in time and micro time.
    rng = np.random.default_rng(sc.seed + 99)
    for ch, rate in sc.extra.items():
        n = rng.poisson(rate * sc.duration_s)
        t = np.concatenate([t, rng.uniform(0, sc.duration_s, n)])
        micro = np.concatenate([micro, rng.integers(0, 4096, n)])
        routing = np.concatenate([routing, np.full(n, ch)])
    if sc.excitation == "usalex" and not sc.keep_micro:
        micro = np.zeros_like(micro)
    order = np.argsort(t, kind="stable")
    macro = np.floor(t[order] / MACRO_RES).astype(np.uint64)
    data = tttrlib.TTTR(macro, micro[order].astype(np.uint16), routing[order].astype(np.int8),
                        np.zeros(macro.size, np.int8))
    data.header.set_macro_time_resolution(MACRO_RES)
    data.header.set_micro_time_resolution(sc.laser_period_ns * 1e-9 / 4096)
    return data


#: The matrix the tests run and the page offers.
SCENARIOS = [
    Scenario("cw 2c"),
    Scenario("cw 2c, donor on the higher channel", donor=(2,), acceptor=(0,)),
    Scenario("cw 2c, no donor-only", donor_only=0.0),
    Scenario("cw 2c + dark-count channel", extra={3: 300.0}),
    Scenario("cw MFD (BH 0/8, 1/9)", donor=(0, 8), acceptor=(1, 9)),
    Scenario("cw MFD + two noise channels", donor=(0, 1), acceptor=(2, 3), extra={4: 500.0, 5: 200.0}),
    Scenario("PIE 2c", excitation="pie", acceptor_only=0.15),
    Scenario("PIE, acceptor pulse first", excitation="pie", donor_pulse_ns=20.0, acceptor_pulse_ns=4.0,
             acceptor_only=0.15),
    Scenario("PIE, pulses 8 ns apart", excitation="pie", donor_pulse_ns=6.0, acceptor_pulse_ns=14.0,
             acceptor_only=0.15),
    Scenario("PIE, 50 ns period", excitation="pie", laser_period_ns=50.0, donor_pulse_ns=5.0,
             acceptor_pulse_ns=30.0, acceptor_only=0.15),
    Scenario("PIE MFD (0/8, 1/9)", excitation="pie", donor=(0, 8), acceptor=(1, 9), acceptor_only=0.15),
    Scenario("PIE + dark-count channel", excitation="pie", extra={5: 400.0}, acceptor_only=0.15),
    Scenario("µsALEX with micro time", excitation="usalex", acceptor_only=0.15),
    Scenario("µsALEX, no micro time (.sm)", excitation="usalex", keep_micro=False, acceptor_only=0.15),
    Scenario("µsALEX, 50 µs period, donor on ch 1", excitation="usalex", keep_micro=False,
             alex_period_us=50.0, donor=(1,), acceptor=(0,), acceptor_only=0.15),
    Scenario("1c (donor only)", populations=(), donor_only=1.0, acceptor=()),
]
