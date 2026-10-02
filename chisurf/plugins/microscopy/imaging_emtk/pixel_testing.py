"""Deterministic photon-stream inputs shared by the imaging pixel family tests and evidence (img_pixel_*, img_coloc).

``flim_ptu(path)`` writes a small confocal photon stream with two lifetimes (left half 1.0 ns, right half 3.0 ns), an
intensity gradient, an optional second detector and the scanner markers a reader needs. Everything is simulated from a seed,
so the numbers a Qt capture and an emtk test see are the same.
"""
from __future__ import annotations

import pathlib
import numpy as np

TY_INT8 = 0x10000008
LINES = PIX = 32
FRAMES = 12
DWELL = 20.0e-6
TAU_LEFT_NS, TAU_RIGHT_NS = 1.0, 3.0
#: laser period of the simulated stream (40 MHz): the macro-time clock ticks once per sync pulse, as a real TCSPC file's
LASER_PERIOD = 25e-9
K_TICKS = int(round(0.5 * DWELL / LASER_PERIOD))  # sync pulses per half pixel dwell
MICRO_RES = 0.032e-9  # 32 ps bins, 256 bins = 8.2 ns
SEED = 7


def counts(n_channels: int = 1, seed: int = SEED) -> np.ndarray:
    """``(channel, frame, line, pixel)`` Poisson photon counts: a gradient along y, a brighter disc in the middle."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:LINES, 0:PIX]
    base = 1.0 + 3.0 * (y / (LINES - 1))
    base = base + 4.0 * np.exp(-(((x - PIX * 0.5) ** 2 + (y - LINES * 0.5) ** 2) / (2 * 5.0 ** 2)))
    out = [rng.poisson(base * (1.0 if c == 0 else 0.7 + 0.01 * x), size=(FRAMES, LINES, PIX)) for c in range(n_channels)]
    return np.asarray(out)


def flim_ptu(path, n_channels: int = 1, seed: int = SEED) -> str:
    """Write the photon stream; routing channels 0..n-1 are detectors, 4/1/2 the frame / line markers (as the plugins' demo)."""
    import tttrlib

    c = counts(n_channels, seed)
    rng = np.random.default_rng(seed + 1)
    ch, frames, lines, pixels = c.shape
    period = np.uint64(2 * pixels + 2)
    bases = np.arange(frames * lines, dtype=np.uint64) * period
    line_starts = bases + np.uint64(1)
    frame_starts = bases[::lines]
    pixel_ticks = (line_starts[:, None] + np.uint64(1) + np.uint64(2) * np.arange(pixels, dtype=np.uint64)[None, :]).reshape(-1)
    macros, micros, chans = [], [], []
    xs = np.tile(np.arange(pixels), frames * lines)
    for k in range(ch):
        flat = c[k].reshape(-1).astype(np.int64)
        macro = np.repeat(pixel_ticks, flat)
        x = np.repeat(xs, flat)
        tau = np.where(x < pixels // 2, TAU_LEFT_NS, TAU_RIGHT_NS) * 1e-9
        t = rng.exponential(tau)
        bins = np.minimum((t / MICRO_RES).astype(np.int64) + 20, 255).astype(np.uint16)
        macros.append(macro); micros.append(bins); chans.append(np.full(macro.size, k, np.int8))
    n_ph = sum(m.size for m in macros)
    marker_macro = np.concatenate([line_starts, line_starts + np.uint64(2 * pixels), frame_starts])
    marker_chan = np.concatenate([np.full(line_starts.size, 1, np.int8), np.full(line_starts.size, 2, np.int8), np.full(frame_starts.size, 4, np.int8)])
    kk = np.uint64(K_TICKS)
    macro = np.concatenate([m * kk for m in macros] + [marker_macro * kk])
    micro = np.concatenate(micros + [np.zeros(marker_macro.size, np.uint16)])
    chan = np.concatenate(chans + [marker_chan])
    event = np.concatenate([np.zeros(n_ph, np.int8), np.ones(marker_macro.size, np.int8)])
    priority = np.concatenate([np.zeros(n_ph, np.int8), np.ones(marker_macro.size, np.int8)])
    order = np.lexsort((priority, macro))
    tttr = tttrlib.TTTR(macro[order], micro[order], chan[order], event[order])
    h = tttr.header
    h.set_macro_time_resolution(LASER_PERIOD)
    h.set_micro_time_resolution(MICRO_RES)
    h.set_number_of_micro_time_channels(256)
    for name, value in (("ImgHdr_LineStart", 1), ("ImgHdr_LineStop", 2), ("ImgHdr_Frame", 3), ("ImgHdr_PixX", pixels), ("ImgHdr_PixY", lines), ("ImgHdr_BiDirect", 0)):
        h.set_tag(name, int(value), TY_INT8)
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not tttr.write(str(path), "PTU"):
        raise RuntimeError(f"cannot write {path}")
    return str(path)


def irf_ptu(path, seed: int = SEED + 5) -> str:
    """A plain (marker-free) photon stream with a narrow IRF-like micro-time peak, as an IRF measurement."""
    import tttrlib

    rng = np.random.default_rng(seed)
    n = 200000
    micro = np.clip(rng.normal(40, 2.0, n), 0, 255).astype(np.uint16)
    macro = np.cumsum(rng.integers(1, 40, n)).astype(np.uint64)
    tttr = tttrlib.TTTR(macro, micro, rng.integers(0, 2, n).astype(np.int8), np.zeros(n, np.int8))
    tttr.header.set_macro_time_resolution(LASER_PERIOD)
    tttr.header.set_micro_time_resolution(MICRO_RES)
    tttr.header.set_number_of_micro_time_channels(256)
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not tttr.write(str(path), "PTU"):
        raise RuntimeError(f"cannot write {path}")
    return str(path)


def tiff_pair(path, seed: int = SEED):
    """A two-channel TIFF (channel B = channel A partly shifted + noise) for the colocalization tool."""
    from chisurf.core.fio.image import imwrite

    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:64, 0:64]
    a = 20 + 80 * np.exp(-(((x - 24) ** 2 + (y - 28) ** 2) / (2 * 6.0 ** 2))) + 60 * np.exp(-(((x - 46) ** 2 + (y - 16) ** 2) / (2 * 4.0 ** 2)))
    b = 15 + 90 * np.exp(-(((x - 27) ** 2 + (y - 30) ** 2) / (2 * 6.0 ** 2))) + 50 * np.exp(-(((x - 12) ** 2 + (y - 50) ** 2) / (2 * 4.0 ** 2)))
    stack = np.stack([rng.poisson(a), rng.poisson(b)]).astype(np.float32)
    imwrite(path, stack)
    return str(path)


def real_settings_state() -> dict:
    """``{path: (size, mtime)}`` of the real ``~/.chisurf`` (taken at import, before a test sets HOME): a hermetic test leaves it as it was."""
    import os

    root = _REAL_HOME / ".chisurf"
    state = {}
    if root.exists():
        for dirpath, _dirs, files in os.walk(root):
            for name in files:
                f = pathlib.Path(dirpath) / name
                try:
                    st = f.stat()
                    state[str(f)] = (st.st_size, st.st_mtime_ns)
                except OSError:
                    pass
    return state


_REAL_HOME = pathlib.Path.home()
