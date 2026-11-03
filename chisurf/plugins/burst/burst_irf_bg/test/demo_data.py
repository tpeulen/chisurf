"""A photon measurement whose IRF and background are known, for the tool's tests and captures.

``<root>/m000.spc`` (SPC-130, 12.5 ns macro ticks, 4096 micro-time channels over the same
12.5 ns): between bursts, scattered light (a Gaussian IRF at 2.0 ns, σ 0.08 ns) and a flat
dark background, on the green channel 0 and the red channel 1; 300 bursts of 1 ms at 100 kHz
whose photons decay with τ = 4 ns after the IRF. The non-burst photons the tool keeps should
give an IRF peaking at 2.0 ns on a flat floor.
"""

from __future__ import annotations

import pathlib

import numpy as np

TICK = 12.5e-9
CHANNELS = 4096
IRF_PEAK_NS = 2.0
IRF_SIGMA_NS = 0.08
TAU_NS = 4.0
DURATION_S = 20.0


def _micro(rng, n, kind):
    ns = TICK * 1e9
    if kind == "irf":
        t = rng.normal(IRF_PEAK_NS, IRF_SIGMA_NS, n)
    elif kind == "flat":
        t = rng.uniform(0.0, ns, n)
    else:  # fluorescence: the IRF, then an exponential decay
        t = rng.normal(IRF_PEAK_NS, IRF_SIGMA_NS, n) + rng.exponential(TAU_NS, n)
    return np.clip((np.mod(t, ns) / ns * CHANNELS).astype(int), 0, CHANNELS - 1)


def build(root: pathlib.Path, seed: int = 4) -> pathlib.Path:
    """Write the measurement under *root*; return its path."""
    import tttrlib

    rng = np.random.default_rng(seed)
    times, channels, micro = [], [], []
    for channel in (0, 1):
        for kind, rate_hz in (("irf", 1500.0), ("flat", 1000.0)):
            n = rng.poisson(rate_hz * DURATION_S)
            times.append(rng.uniform(0.0, DURATION_S, n))
            channels.append(np.full(n, channel))
            micro.append(_micro(rng, n, kind))
    for start in rng.uniform(0.05, DURATION_S - 0.05, 300):
        n = rng.poisson(100.0)
        times.append(start + rng.uniform(0.0, 1e-3, n))
        channels.append((rng.random(n) < 0.4).astype(int))
        micro.append(_micro(rng, n, "decay"))
    t = np.concatenate(times)
    order = np.argsort(t, kind="stable")
    ticks = np.round(t[order] / TICK).astype(np.uint64)
    keep = np.concatenate([[True], np.diff(ticks) > 0])  # one photon per macro tick
    data = tttrlib.TTTR()
    data.append_events(
        ticks[keep],
        np.concatenate(micro)[order][keep].astype(np.uint16),
        np.concatenate(channels)[order][keep].astype(np.int8),
        np.zeros(int(keep.sum()), np.int8),
        False,
        0,
    )
    data.header.set_macro_time_resolution(TICK)
    data.header.set_micro_time_resolution(TICK / CHANNELS)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "m000.spc"
    data.write(str(path))
    return path


#: Non-burst photons written per detector: the IRF scatter and the flat background, over the run.
NON_BURST_PER_DETECTOR = (1500.0 + 1000.0) * DURATION_S


def assert_rows_recover_the_demo(rows) -> None:
    """The tool's result rows recover what the measurement was built with.

    Per detector the prompt sits on the IRF peak and the non-burst count is the scatter plus the
    flat background written outside bursts (a few percent go to burst windows and to photons
    sharing a macro tick); burst photons were routed 60:40 to the first and second detector, and
    both detectors see the same non-burst stream, so their background rates agree.
    """
    assert len(rows) == 2
    for row in rows:
        assert abs(row["prompt_ns"] - IRF_PEAK_NS) < 0.15
        assert abs(row["n_bg"] - NON_BURST_PER_DETECTOR) < 0.1 * NON_BURST_PER_DETECTOR
        assert row["n_burst"] > 0
    assert rows[0]["n_burst"] > rows[1]["n_burst"]
    rates = [r["background_khz"] for r in rows]
    assert abs(rates[0] - rates[1]) / max(rates) < 0.05
