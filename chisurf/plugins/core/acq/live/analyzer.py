"""The live burst analyzer is tttrlib's ``StreamingBurstAnalyzer``; this module keeps the batch reference.

tttrlib's class (``modules/streaming``) analyses any detection scheme live -- single colour, two
colour, PIE, µs-ALEX, MFD, three-colour PIE -- from the shared channel definition, with
``from_setup(setup, preset=...)`` (its docstring is the reference: detectors with half-open
micro-time gates, windows as half-open micro-time ranges or macro-time phase ranges, streams
``"<window> <detector>"`` and ``"<detector>"``). :func:`make_analyzer` is that call.
:func:`analyze_offline` is the independent batch reference the live table is held to.
"""

from __future__ import annotations

import numpy as np
import tttrlib

from chisurf.core.fluorescence.excitation import micro_mask

__all__ = ["PRESETS", "analyze_offline", "make_analyzer"]

#: The detection schemes ("presets") the analyzer knows.
PRESETS = tuple(tttrlib.StreamingBurstAnalyzer.PRESETS)


def make_analyzer(setup: dict, preset: str, **kw):
    """``tttrlib.StreamingBurstAnalyzer.from_setup(setup, preset, **kw)``."""
    return tttrlib.StreamingBurstAnalyzer.from_setup(setup, preset, **kw)


def analyze_offline(tttr, setup: dict, preset: str, *, min_photons=20, window_photons=10, window_time=5e-4,
                    donor="green", acceptor="red", prompt="prompt", delay="delayed") -> dict:  # fmt: skip
    """The batch reference: burst selection's search over a whole file, counted per stream.

    Written independently of both analyzers -- the photons of the detector channels selected,
    ``TTTR.burst_search`` on them, counts per stream by membership, the preset's ratios without
    background. The guard holds every live analyzer's table to this for the columns it gives.
    """
    detectors = setup.get("detectors") or {}
    windows = setup.get("windows") or {}
    chs = sorted({int(c) for d in detectors.values() for c in d.get("chs", [])})
    channel = np.asarray(tttr.routing_channels)
    sel = np.flatnonzero(np.isin(channel, chs))
    sub = tttr[sel] if len(sel) != len(tttr) else tttr
    macro = np.asarray(sub.macro_times, dtype=np.int64)
    micro = np.asarray(sub.micro_times, dtype=np.int64)
    ch = np.asarray(sub.routing_channels, dtype=np.int64)
    idx = np.asarray(
        sub.burst_search(int(min_photons), int(window_photons), float(window_time))
    ).reshape(-1, 2)

    def member(det, win=None):
        d = detectors[det]
        m = np.isin(ch, d.get("chs", []))
        if win is not None:
            m &= micro_mask(micro, [windows[win]])
        return m

    cum = {}

    def count(det, win=None):
        key = (det, win)
        if key not in cum:
            cum[key] = np.concatenate([[0], np.cumsum(member(det, win))])
        c = cum[key]
        return (c[idx[:, 1] + 1] - c[idx[:, 0]]).astype(float)

    clock = float(tttr.header.macro_time_resolution)
    out = {
        "First Photon": idx[:, 0].astype(np.int64),
        "Last Photon": idx[:, 1].astype(np.int64),
        "Number of Photons": (idx[:, 1] - idx[:, 0] + 1).astype(np.int64),
        "Duration (ms)": (macro[idx[:, 1]] - macro[idx[:, 0]]) * clock * 1e3,
    }
    for det in detectors:
        out[f"Number of Photons ({det})"] = count(det).astype(np.int64)

    def ratio(num, den):
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(den != 0, num / np.where(den != 0, den, 1), 0.0)

    if preset == "two_color":
        out["Proximity Ratio"] = ratio(count(acceptor), count(donor) + count(acceptor))
    elif preset == "pie":
        dd, da, aa = count(donor, prompt), count(acceptor, prompt), count(acceptor, delay)
        out["Proximity Ratio"] = ratio(da, dd + da)
        out["Stoichiometry"] = ratio(dd + da, dd + da + aa)
    return out
