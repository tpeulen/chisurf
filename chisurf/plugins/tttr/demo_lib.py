"""The shared synthetic TTTR photon stream of the ``tttr`` plugin family.

One deterministic simulation feeds every demonstration of the family: a µs-ALEX
measurement whose excitation alternation is still in the **macro time** — what
an unconverted measurement looks like — with donor and acceptor detectors,
single-molecule bursts over a weak background, and micro times from exponential
decays. Its structure serves every consumer:

* the alternation (period :data:`PERIOD` ticks, laser-on gates
  :data:`DONOR_GATE` / :data:`ACCEPTOR_GATE`) is what the ALEX creator detects
  and folds into the micro time;
* the bursts give the count-rate analysis, the time windows and the audifier's
  waterfall their time structure;
* the routing channels 0 (donor) and 1 (acceptor) are what the splitter
  separates and the LUT tools histogram per channel;
* the exponential micro times (donor :data:`DONOR_LIFETIME_NS`, acceptor
  :data:`ACCEPTOR_LIFETIME_NS`) are what the micro-time shifter aligns.

Nothing here is a measurement; the photons come from a seeded generator, so a
written file is byte-identical on every run. Each plugin's ``demo.py`` declares
its own parameter set (:func:`config`) and cache, and calls :func:`write_spc`
to materialise its stream as a Becker & Hickl SPC-130 file.
"""

from __future__ import annotations

import numpy as np

#: 12.5 ns macro ticks (SPC-130), 4096 micro-time bins across the same span.
TICK_S = 12.5e-9
N_MICRO = 4096
MICRO_RESOLUTION_S = TICK_S / N_MICRO
#: The alternation: 8000 ticks (100 µs), donor laser on in [0, 3900), acceptor
#: laser on in [4000, 7900); 100-tick laser-off gaps separate the phases.
PERIOD = 8000
DONOR_GATE = (0, 3900)
ACCEPTOR_GATE = (4000, 7900)
DONOR_CHANNEL = 0
ACCEPTOR_CHANNEL = 1
DONOR_LIFETIME_NS = 2.0
ACCEPTOR_LIFETIME_NS = 4.0
#: Micro-time bin where each channel's decay begins (the IRF rise). The offset
#: between the channels is what the micro-time shifter aligns away.
DONOR_RISE_BINS = 400
ACCEPTOR_RISE_BINS = 900
BURST_RATE_HZ = 25.0
BURST_WIDTH_MS = 0.3
#: Photons a molecule emits on one crossing (uniform between the two).
PHOTONS_PER_BURST = (150, 450)
#: Acceptor emission probability for a donor-excited burst photon (the FRET
#: efficiency of the single simulated population).
FRET_EFFICIENCY = 0.5
BACKGROUND_HZ = 3000.0
DURATION_S = 40.0
SEED = 20261022


def config(**overrides) -> dict:
    """Return a complete generator configuration, with *overrides* applied.

    The full parameter set is what each plugin's ``DEMO`` records beside its
    cached file: changing any value regenerates that plugin's stream.
    """
    values = {
        "seed": SEED,
        "duration_s": DURATION_S,
        "macro_resolution_s": TICK_S,
        "n_micro": N_MICRO,
        "micro_resolution_s": MICRO_RESOLUTION_S,
        "period": PERIOD,
        "donor_gate": list(DONOR_GATE),
        "acceptor_gate": list(ACCEPTOR_GATE),
        "donor_channel": DONOR_CHANNEL,
        "acceptor_channel": ACCEPTOR_CHANNEL,
        "donor_lifetime_ns": DONOR_LIFETIME_NS,
        "acceptor_lifetime_ns": ACCEPTOR_LIFETIME_NS,
        "donor_rise_bins": DONOR_RISE_BINS,
        "acceptor_rise_bins": ACCEPTOR_RISE_BINS,
        "burst_rate_hz": BURST_RATE_HZ,
        "burst_width_ms": BURST_WIDTH_MS,
        "photons_per_burst": list(PHOTONS_PER_BURST),
        "fret_efficiency": FRET_EFFICIENCY,
        "background_hz": BACKGROUND_HZ,
    }
    values.update(overrides)
    return values


def _micro_times(rng: np.random.Generator, c: dict, channel: np.ndarray) -> np.ndarray:
    """Exponential decays that begin at each channel's rise bin, clipped into the TAC."""
    acceptor = channel == int(c["acceptor_channel"])
    lifetime_s = np.where(
        acceptor,
        float(c["acceptor_lifetime_ns"]) * 1e-9,
        float(c["donor_lifetime_ns"]) * 1e-9,
    )
    rise = np.where(acceptor, int(c["acceptor_rise_bins"]), int(c["donor_rise_bins"]))
    bins = rise + rng.exponential(lifetime_s / float(c["micro_resolution_s"]))
    return np.clip(bins, 0, int(c["n_micro"]) - 1).astype(np.uint16)


def photon_stream(c: dict | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Simulate the stream: ``(macro_ticks, micro_bins, routing_channels)``.

    The macro ticks ascend strictly (one event per tick, as SPC-130 stores
    them); the routing channels carry the detector; the micro bins carry the
    decay position after the laser pulse of the photon's alternation phase.
    """
    c = config() if c is None else c
    rng = np.random.default_rng(int(c["seed"]))
    macro_res = float(c["macro_resolution_s"])
    period = int(c["period"])
    donor_gate = c["donor_gate"]
    acceptor_gate = c["acceptor_gate"]
    donor_ch = int(c["donor_channel"])
    acceptor_ch = int(c["acceptor_channel"])
    duration = float(c["duration_s"])
    span = duration / macro_res

    def phases(ticks: np.ndarray) -> np.ndarray:
        return np.mod(ticks, period)

    # ── bursts ────────────────────────────────────────────────────────────
    n_bursts = int(rng.poisson(float(c["burst_rate_hz"]) * duration))
    edge = 4.0 * float(c["burst_width_ms"]) * 1e-3 / macro_res
    centres = rng.uniform(edge, span - edge, n_bursts)
    widths = np.full(n_bursts, float(c["burst_width_ms"]) * 1e-3 / macro_res)
    sizes = rng.integers(int(c["photons_per_burst"][0]), int(c["photons_per_burst"][1]), n_bursts)
    # intp repeats: numpy 2 on wasm32 refuses a safe int64->int32 cast here,
    # which breaks every Load-example built on this generator in the browser.
    sizes = sizes.astype(np.intp, copy=False)
    ticks = rng.normal(np.repeat(centres, sizes), np.repeat(widths, sizes))
    u = rng.random(ticks.size)
    burst_channel = np.where(u < float(c["fret_efficiency"]), acceptor_ch, donor_ch)
    burst_channel = burst_channel.astype(np.int8)

    # ── background over both detectors and every phase ────────────────────
    n_background = int(rng.poisson(float(c["background_hz"]) * duration))
    background_ticks = rng.uniform(0.0, span, n_background)
    background_channel = rng.integers(0, 2, n_background).astype(np.int8)

    macro = np.concatenate([ticks, background_ticks])
    channel = np.concatenate([burst_channel, background_channel])
    order = np.argsort(macro, kind="stable")
    macro, channel = macro[order], channel[order]
    ticks = np.round(macro).astype(np.int64)
    np.clip(ticks, 0, None, out=ticks)
    # SPC-130 stores one event per ascending macro tick: keep the first event.
    keep = np.concatenate([[True], np.diff(ticks) > 0])
    ticks, channel = ticks[keep], channel[keep]
    phase = phases(ticks)
    # A detector only sees light while its laser is on (a few per cent of
    # acceptor-laser photons leak onto the donor detector, as measured).
    in_donor = (phase >= donor_gate[0]) & (phase < donor_gate[1])
    in_acceptor = (phase >= acceptor_gate[0]) & (phase < acceptor_gate[1])
    donor_emission = channel == donor_ch
    acceptor_emission = channel == acceptor_ch
    donor_seen = (in_donor & donor_emission) | (in_acceptor & acceptor_emission & (rng.random(ticks.size) < 0.02))
    acceptor_seen = (in_donor & acceptor_emission) | (in_acceptor & acceptor_emission)
    seen = donor_seen | acceptor_seen
    channel = np.where(donor_seen, donor_ch, acceptor_ch).astype(np.int8)
    ticks, phase = ticks[seen], phase[seen]
    channel = channel[seen]
    micro = _micro_times(rng, c, channel)
    final = np.argsort(ticks, kind="stable")
    return ticks[final].astype(np.uint64), micro[final], channel[final]


def expected_counts(c: dict | None = None) -> dict[str, int]:
    """Return ``{"total", "donor", "acceptor"}`` photon counts of the stream.

    The numbers come from the same deterministic draw :func:`photon_stream`
    makes, so the tests can assert them without restating the simulation.
    """
    c = config() if c is None else c
    _, _, routing = photon_stream(c)
    donor = int(np.count_nonzero(routing == int(c["donor_channel"])))
    return {
        "total": int(routing.size),
        "donor": donor,
        "acceptor": int(routing.size) - donor,
    }


def write_spc(path, c: dict, macro: np.ndarray, micro: np.ndarray, routing: np.ndarray) -> dict:
    """Write the stream to *path* as SPC-130; return the written-stream truth.

    The truth reports the exact counts on disk (after the one-event-per-tick
    deduplication) so a demo's sidecar and its tests agree with the file.
    """
    return _write(path, c, macro, micro, routing, "SPC-130")


def write_ptu(path, c: dict, macro: np.ndarray, micro: np.ndarray, routing: np.ndarray) -> dict:
    """Write the stream to *path* as a PicoQuant PTU (the header editor's format)."""
    return _write(path, c, macro, micro, routing, "PTU")


def _write(
    path, c: dict, macro: np.ndarray, micro: np.ndarray, routing: np.ndarray, container: str
) -> dict:
    import tttrlib

    stream = tttrlib.TTTR()
    stream.append_events(
        macro, micro, routing.astype(np.int8), np.zeros(macro.size, dtype=np.int8)
    )
    header = stream.header
    header.set_macro_time_resolution(float(c["macro_resolution_s"]))
    header.set_micro_time_resolution(float(c["micro_resolution_s"]))
    header.set_number_of_micro_time_channels(int(c["n_micro"]))
    if not stream.write(str(path), container, header):
        raise OSError(f"could not write the demonstration stream to {path}")
    donor, acceptor = int(c["donor_channel"]), int(c["acceptor_channel"])
    return {
        "n_photons": int(macro.size),
        "donor_channel": donor,
        "acceptor_channel": acceptor,
        "donor_rise_bins": int(c["donor_rise_bins"]),
        "acceptor_rise_bins": int(c["acceptor_rise_bins"]),
        "period": int(c["period"]),
        "donor_gate": list(c["donor_gate"]),
        "acceptor_gate": list(c["acceptor_gate"]),
        "duration_s": float(macro[-1] - macro[0]) * float(c["macro_resolution_s"]),
    }


__all__ = [
    "ACCEPTOR_CHANNEL",
    "ACCEPTOR_GATE",
    "ACCEPTOR_LIFETIME_NS",
    "BURST_RATE_HZ",
    "DONOR_CHANNEL",
    "DONOR_GATE",
    "DONOR_LIFETIME_NS",
    "DURATION_S",
    "FRET_EFFICIENCY",
    "MICRO_RESOLUTION_S",
    "N_MICRO",
    "PERIOD",
    "SEED",
    "TICK_S",
    "config",
    "expected_counts",
    "photon_stream",
    "write_ptu",
    "write_spc",
]
