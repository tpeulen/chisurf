"""PIE / nsALEX: the excitation pulses in the micro time, and windows around them.

A pulsed laser shows in a micro-time histogram as a **rising edge** -- the instrument response --
followed by a decay. A decay never rises, so the number of rising edges is the number of
excitation pulses, whatever the lifetimes, the IRF shape or the background. With pulsed
interleaved excitation there are two (or more) of them, and the detectors tell which pulse is
which: under the acceptor pulse the donor detectors are dark.

The search, per detector and on their sum:

1. **Coarse bins.** The histogram is binned to about :data:`COARSE_BINS` bins so a rise is a step
   of many photons; the range is circular (a pulse near the end decays into the start of the
   range, the sync offset can put the rise anywhere).
2. **Rising edges.** A bin is a rise when it exceeds the lowest of the previous three bins by a
   sizeable fraction of the detector's dynamic range *and* by five Poisson sigmas. Adjacent rise
   bins are one edge. Edges of all detectors are merged.
3. **Refinement.** At full resolution the edge is where the smoothed signal first crosses 20 % of
   its step; the peak and the end of the pulse core (half height) follow.
4. **Windows.** Each window starts :data:`MARGIN_S` before its pulse's rise and ends where the next
   window starts, so the windows tile the whole period. Two pulses are ``prompt`` (donor
   excitation) and ``delayed`` (acceptor excitation); more are ``pulse1``, ``pulse2``, ...
5. **Roles.** Per window and detector the background-corrected rate; a detector below
   :data:`DARK` of its brightest window is dark there. The window where some detectors are dark is
   acceptor excitation, and those detectors are the donor's.

One rising edge is ``single`` (a donor-only sample, or no PIE: windows cannot be placed from the
data, and that is said, not raised); no edge, or too few photons, is ``unclear``.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from .result import ExcitationWindows, Pulse

__all__ = ["COARSE_BINS", "DARK", "MARGIN_S", "detect_pie_windows", "rising_edges"]

#: Coarse bins of the edge search.
COARSE_BINS = 256
#: Narrowest coarse bin of the edge search: a laser pulse rises over a few hundred ps, so on
#: fine channels (80 ps, 500 per period) no single channel step is steep enough to see it.
COARSE_MIN_S = 0.25e-9
#: How far before its pulse's rise a window starts.
MARGIN_S = 0.3e-9
#: A detector is dark under an excitation when its rate there is below this fraction of its rate
#: under its brightest excitation.
DARK = 0.15
#: Fewest photons the search looks at.
MIN_PHOTONS = 1000
#: Pulses closer than this are one pulse (an IRF with a reflection, a double-humped diode).
MIN_SEPARATION_S = 1.5e-9


def rising_edges(h: np.ndarray, frac: float = 0.15, sigmas: float = 5.0) -> list[tuple[int, float]]:
    """Bins where the circular histogram *h* rises steeply: ``[(bin, step in sigmas), ...]``.

    A rise is a step above the lowest of the previous three bins (so an edge spread over a few
    bins still counts), held over two bins (a single noisy bin is not a pulse), of at least *frac*
    of the histogram's dynamic range and *sigmas* Poisson sigmas of the difference. Rise bins within two of each other are one edge, reported at its first bin.
    """
    h = np.asarray(h, dtype=float)
    n = h.size
    if n < 4 or h.max() <= 0:
        return []
    prev = np.minimum.reduce([np.roll(h, k) for k in (1, 2, 3)])
    # the level after the edge, over two bins: a one-bin spike (a noise count) is not a pulse
    level = 0.5 * (h + np.roll(h, -1))
    step = level - prev
    span = h.max() - np.percentile(h, 10)
    noise = np.sqrt(np.maximum(prev, 1.0) + np.maximum(level, 1.0))
    rise = (h - prev > frac * span) & (step > frac * span) & (step > sigmas * noise)
    idx = list(np.flatnonzero(rise))
    groups: list[list[int]] = []
    for i in idx:
        if groups and i - groups[-1][-1] <= 2:
            groups[-1].append(i)
        else:
            groups.append([i])
    if len(groups) > 1 and groups[0][0] + n - groups[-1][-1] <= 2:
        groups[0] = groups.pop() + groups[0]
    return [(int(g[0]), float(max(step[i] / noise[i] for i in g))) for g in groups]


def _circ(h: np.ndarray, lo: int, hi: int) -> np.ndarray:
    """``h[lo:hi]`` on a circular array (indices may run past either end)."""
    return h[np.arange(lo, hi) % h.size]


def _smooth(h: np.ndarray, w: int) -> np.ndarray:
    """Circular boxcar of width *w*."""
    if w <= 1:
        return h.astype(float)
    k = np.ones(w) / w
    ext = np.concatenate([h[-w:], h, h[:w]]).astype(float)
    return np.convolve(ext, k, mode="same")[w:-w]


def _coarse(h: np.ndarray, k: int) -> np.ndarray:
    """*h* summed in bins of *k* channels; a partial last bin is scaled to a full one."""
    n = h.size
    nb = -(-n // k)
    pad = np.zeros(nb * k)
    pad[:n] = h
    c = pad.reshape(nb, k).sum(axis=1)
    rem = n - (nb - 1) * k
    if rem < k:
        c[-1] *= k / rem
    return c


def _refine(fine: np.ndarray, o: int, k: int, w: int) -> tuple[int, int, int]:
    """``(rise, peak, core_stop)`` in channels for the coarse edge *o* (bins of *k* channels)."""
    n = fine.size
    s = _smooth(fine, w)
    lo, hi = (o - 3) * k, (o + 4) * k
    seg = _circ(s, lo, hi)
    base_at = int(np.argmin(seg[: 4 * k]))
    base = float(seg[base_at])
    top_at = base_at + int(np.argmax(seg[base_at:]))
    top = float(seg[top_at])
    thr = base + 0.2 * (top - base)
    cross = base_at + int(np.argmax(seg[base_at : top_at + 1] >= thr))
    rise = (lo + cross) % n
    peak = (lo + top_at) % n
    # the core of the pulse: from the rise until the signal is below half height again
    half = base + 0.5 * (top - base)
    after = _circ(s, lo + top_at, lo + top_at + n // 2)
    below = np.flatnonzero(after < half)
    core = int(below[0]) if below.size else max(1, k)
    return int(rise), int(peak), int((peak + core) % n)


def _names(n_pulses: int) -> list[str]:
    return ["prompt", "delayed"] if n_pulses == 2 else [f"pulse{i + 1}" for i in range(n_pulses)]


def _window_bounds(rises: list[int], n: int, margin: int) -> list[tuple[int, int]]:
    """Circular ``(start, stop)`` per pulse: *margin* before its rise to the next one's start."""
    m = len(rises)
    starts = []
    for i, r in enumerate(rises):
        gap = (r - rises[i - 1]) % n if m > 1 else n
        starts.append((r - min(margin, max(gap // 4, 0))) % n)
    return [(starts[i], starts[(i + 1) % m]) for i in range(m)]


def _linear(start: int, stop: int, rise: int, peak: int, n: int) -> tuple[list[int], int]:
    """A circular window as one setup range ``[lo, hi)``, and the channels it had to drop.

    A window that wraps around the range end keeps the part holding its pulse's rise and peak.
    """
    if start < stop:
        return [start, stop], 0
    if stop == start:  # one window, the whole period
        return [0, n], 0
    head, tail = [start, n], [0, stop]
    keep = head if (start <= rise < n) else tail
    if keep is tail and not (0 <= peak < stop):
        keep = head
    dropped = (tail[1] - tail[0]) if keep is head else (head[1] - head[0])
    return keep, int(dropped)


def detect_pie_windows(
    histograms: Mapping[str, np.ndarray] | np.ndarray,
    resolution_s: float,
    *,
    n_channels: int | None = None,
    margin_s: float = MARGIN_S,
    min_photons: int = MIN_PHOTONS,
) -> ExcitationWindows:
    """Find the excitation pulses in per-detector micro-time histograms and propose windows.

    Parameters
    ----------
    histograms : mapping or array
        ``{detector: counts per micro-time channel}`` (or one histogram). Detector names are free
        (``"G|G"``, ``"ch 1"``); they are what :attr:`Pulse.excites` reports.
    resolution_s : float
        Micro-time channel width, in seconds.
    n_channels : int, optional
        Channels per sync period (the histograms are cut or zero-padded to it). Default: the
        histograms' length.
    margin_s : float
        How far before each pulse's rise its window starts.
    min_photons : int
        Below this many photons the result is ``unclear``.

    Returns
    -------
    ExcitationWindows
        ``kind`` ``"pie"`` with the windows, ``"single"`` (one pulse: a donor-only sample or no
        PIE), or ``"unclear"`` (no pulse, too few photons).
    """
    if not isinstance(histograms, Mapping):
        histograms = {"all": histograms}
    names = [str(k) for k in histograms]
    arrays = [np.asarray(histograms[k], dtype=float).ravel() for k in histograms]
    n = int(n_channels or max((a.size for a in arrays), default=0))
    H = np.zeros((len(arrays), n))
    for i, a in enumerate(arrays):
        H[i, : min(n, a.size)] = a[:n]
    res = float(resolution_s)
    total = float(H.sum())
    out = ExcitationWindows(
        kind="unclear", domain="micro", resolution_s=res, n_channels=n, n_photons=int(total)
    )
    if n < 8 or total < min_photons:
        out.message = (
            f"Too few photons ({int(total)}) to see the excitation pulses; "
            "measure longer and detect again."
        )
        return out
    k = max(1, n // COARSE_BINS, int(round(COARSE_MIN_S / res)) if res > 0 else 1)
    w = max(1, k // 2)
    sources = [(names[i], H[i]) for i in range(len(names)) if H[i].sum() >= min_photons / 4]
    nb = -(-n // k)
    min_sep = max(3, int(np.ceil(MIN_SEPARATION_S / res / k))) if res > 0 else 3

    def apart(a: int, b: int) -> int:
        return min(abs(a - b), nb - abs(a - b))

    def pulses_of(h: np.ndarray) -> list[tuple[int, float, np.ndarray]]:
        found: list[tuple[int, float, np.ndarray]] = []
        for o, sig in sorted(rising_edges(_coarse(h, k)), key=lambda e: -e[1]):
            if all(apart(o, m[0]) > min_sep for m in found):
                found.append((o, sig, h))
        return found

    # Pulses are counted within one detector, never across detectors: detectors differ by their
    # cable and electronics delays (a red and a green detector rise 1-2 ns apart under the same
    # laser pulse), and an edge of one beside an edge of the other is one pulse, not two. The
    # detector that sees the most pulses (the acceptor's, in PIE) says how many there are.
    per_source = [pulses_of(h) for _, h in sources]
    if not any(per_source) and len(sources) > 1:
        per_source = [pulses_of(H.sum(axis=0))]  # each too weak alone: their sum
    merged = max(per_source, key=lambda e: (len(e), sum(x[1] for x in e)), default=[])
    others = [e for found in per_source if found is not merged for e in found]
    if not merged:
        out.message = (
            "No excitation pulse in the micro time (flat: continuous-wave excitation, µs-ALEX "
            "or background only)."
        )
        return out
    pulses = []
    for o, sig, h in merged:
        rise, peak, core = _refine(h, o, k, w)
        # the same pulse rises earlier in another detector: its window starts at the earliest
        for oo, _sig, hh in others:
            if min(merged, key=lambda m: apart(oo, m[0]))[0] != o:
                continue  # an edge of another pulse
            other_rise = _refine(hh, oo, k, w)[0]
            if 0 < (rise - other_rise) % n < n // 2:
                rise = other_rise
        pulses.append((rise, peak, core, sig))
    pulses.sort(key=lambda p: p[0])
    out.confidence = float(min(p[3] for p in pulses))
    margin = max(1, int(round(margin_s / res))) if res > 0 else 1
    bounds = _window_bounds([p[0] for p in pulses], n, margin)

    # rates per window and detector, background corrected
    det = [(names[i], H[i]) for i in range(len(names)) if H[i].sum() > 0]
    bg = {d: float(np.percentile(_coarse(h, k), 10)) / k for d, h in det}
    rate: dict[str, list[float]] = {}
    count: dict[str, list[float]] = {}
    noise: dict[str, list[float]] = {}
    for d, h in det:
        rate[d], count[d], noise[d] = [], [], []
        for start, stop in bounds:
            seg = _circ(h, start, stop if stop > start else stop + n)
            sig = max(float(seg.sum()) - bg[d] * seg.size, 0.0)
            count[d].append(sig)
            rate[d].append(sig / max(seg.size, 1))
            noise[d].append(float(np.sqrt(bg[d] * seg.size + 1.0)))
    lit = {
        d: [r >= DARK * max(rate[d]) and count[d][j] > 5 * noise[d][j]
            for j, r in enumerate(rate[d])]
        for d in rate
    }
    out.pulses = [
        Pulse(
            rise=p[0],
            peak=p[1],
            core_stop=p[2],
            excites=[d for d in rate if lit[d][j]],
            share={d: count[d][j] / max(sum(count[d]), 1.0) for d in rate},
        )
        for j, p in enumerate(pulses)
    ]
    if len(pulses) == 1:
        out.kind = "single"
        p = out.pulses[0]
        out.message = (
            f"One excitation pulse (rise at channel {p.rise}, {p.rise * res * 1e9:.1f} ns): a "
            "donor-only sample or not a PIE measurement -- windows cannot be placed from it."
        )
        return out
    # roles: where some detectors are dark, the acceptor is excited directly
    dark_somewhere = [d for d in rate if not all(lit[d]) and any(lit[d])]
    for j, p in enumerate(out.pulses):
        dark = [d for d in dark_somewhere if not lit[d][j]]
        if dark and p.excites:
            p.role = "acceptor"
        elif dark_somewhere and p.excites:
            p.role = "donor"
    if any(p.role == "acceptor" for p in out.pulses):
        out.donor_detectors = sorted(
            {d for p in out.pulses if p.role == "acceptor" for d in dark_somewhere
             if d not in p.excites}
        )
        out.acceptor_detectors = [d for d in rate if d not in out.donor_detectors]
    order = list(range(len(pulses)))
    if len(pulses) == 2 and out.pulses[0].role == "acceptor" and out.pulses[1].role == "donor":
        order = [1, 0]  # prompt is the donor's pulse, whichever comes first in the range
    labels = _names(len(pulses))
    for label, j in zip(labels, order):
        p = out.pulses[j]
        p.window = label
        rng, dropped = _linear(bounds[j][0], bounds[j][1], p.rise, p.peak, n)
        out.windows[label] = rng
        if dropped > 0.05 * n:
            out.notes.append(
                f"window {label} wraps around the end of the range; {dropped} channels "
                f"({dropped * res * 1e9:.1f} ns) of it are left out -- a sync offset that keeps "
                "the pulses away from the range end avoids this"
            )
    out.windows = {lab: out.windows[lab] for lab in labels}
    out.kind = "pie"
    if len(pulses) > 2:
        roles = [p.role or "?" for p in out.pulses]
        out.notes.append(
            f"{len(pulses)} pulses per range ({', '.join(roles)}): a sync divider or more than two "
            "lasers; one window per pulse"
        )
    if not out.donor_detectors:
        out.notes.append(
            "no detector is dark under any pulse: which pulse excites the donor is not known "
            "from the data (one detector, or no acceptor in the sample); prompt = first pulse"
        )
    out.message = f"PIE: {len(pulses)} excitation pulses -- " + ", ".join(
        f"{p.window} at {p.rise * res * 1e9:.1f} ns" + (f" ({p.role})" if p.role else "")
        for p in sorted(out.pulses, key=lambda q: labels.index(q.window))
    )
    return out
