"""What the result windows draw: quality, E/S, bursts, time trace, micro times.

:class:`Plots` computes every histogram once per :attr:`Session.version`; the
``draw_*`` functions put them in the current window with :mod:`emtk.implot`.
Nothing here keeps state between frames.
"""
from __future__ import annotations

import numpy as np

from emtk import im
from emtk import implot as ip

from ..qc import BAD, INFO, OK, WARN

#: Smallest plot height: below it a window scrolls instead of squeezing the plot.
MIN_PLOT_H = 220.0
LEVEL_COLOUR = {OK: (0.40, 0.80, 0.45, 1.0), WARN: (0.95, 0.75, 0.25, 1.0), BAD: (0.95, 0.35, 0.30, 1.0),
                INFO: (0.60, 0.60, 0.60, 1.0)}
#: The time-trace window shows this many seconds at a time.
TRACE_SPAN_S = 10.0


def _hist(x, bins, rng):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    counts, edges = np.histogram(x, bins=bins, range=rng)
    return edges[:-1], counts.astype(float)


def _hist2d(x, y, bins, rng):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    h, _, _ = np.histogram2d(x[ok], y[ok], bins=bins, range=rng)
    return np.flipud(h.T)  # heatmap rows run top to bottom; histogram2d is [x, y]


class Plots:
    """Everything the result windows draw, computed once per result."""

    def __init__(self, s) -> None:
        b = s.bursts
        e, st = s.es()
        self.e_hist = _hist(e, 50, (-0.1, 1.1))
        self.es = None if st is None else _hist2d(e, st, (60, 60), ((-0.1, 1.1), (-0.1, 1.1)))
        self.s_hist = None if st is None else _hist(st, 50, (-0.1, 1.1))
        size = np.log10(np.maximum(b.size, 1))
        self.size_hist = _hist(size, 50, (np.log10(max(1, s.min_photons)), max(size.max(initial=1), 2.0)))
        dur = np.log10(np.maximum(b.duration * 1e3, 1e-3))
        self.dur_hist = _hist(dur, 50, (-1.0, max(dur.max(initial=1), 1.0)))
        rate = np.log10(np.maximum(b.count_rate * 1e-3, 1e-3))
        self.rate_hist = _hist(rate, 50, (rate.min(initial=0), rate.max(initial=1) + 1e-6))
        self.cde = None if b.fret_2cde is None else _hist2d(b.E, np.clip(b.fret_2cde, 0, 100), (50, 50),
                                                            ((-0.1, 1.1), (0, 100)))
        cols = b.extra
        self.tau = None
        if "Tau (green)" in cols:
            self.tau = _hist2d(cols["Tau (green)"], e if len(e) == b.n else b.E, (50, 50), ((0, 6), (-0.1, 1.1)))
        q = s.qc
        self.trace = (q.trace_t, q.trace_rate)
        # Inter-burst gaps on a log axis, with the fitted Poisson arrivals:
        # counts per bin of exp(-r g), scaled to the tail beyond 5 median durations.
        self.gaps = None
        if q.gaps.size >= 20 and np.any(q.gaps > 0):
            g = q.gaps[q.gaps > 0] * 1e3
            edges = np.logspace(np.log10(max(g.min(), 1e-3)), np.log10(g.max()), 50)
            counts, _ = np.histogram(g, edges)
            fit = None
            if q.arrival_rate > 0:
                r = q.arrival_rate * 1e-3  # per ms
                g0 = 5e3 * float(np.median(b.duration))
                n_tail = float(np.sum(g > g0))
                cdf = lambda x: 1.0 - np.exp(-r * np.maximum(x - g0, 0.0))  # noqa: E731
                fit = n_tail * (cdf(edges[1:]) - cdf(edges[:-1]))
            self.gaps = (np.log10(edges[:-1]), counts.astype(float), fit)


def hist_plot(title, hist, xlabel, size) -> None:
    if hist is None:
        return
    x, y = hist
    if ip.begin_plot(title, size):
        ip.setup_axes(xlabel, "bursts")
        ip.plot_stairs("bursts", x, y)
        ip.end_plot()


def heatmap(title, h, xlabel, ylabel, bounds, size) -> None:
    if h is None:
        return
    (x0, x1), (y0, y1) = bounds
    if ip.begin_plot(title, size):
        ip.setup_axes(xlabel, ylabel)
        ip.setup_axes_limits(x0, x1, y0, y1)
        rows, cols = h.shape
        ip.plot_heatmap("bursts", np.log1p(h).ravel(), rows, cols, label_fmt=None,
                        bounds_min=(x0, y0), bounds_max=(x1, y1))
        ip.end_plot()


def empty(text: str) -> None:
    im.text_wrapped(text)


def draw_quality(s, p) -> None:
    q = s.qc
    im.text_colored(LEVEL_COLOUR[q.level], f"Overall: {q.level.upper()}")
    im.same_line()
    e = s.exp
    im.text_disabled(f"  {e.kind}" + (" · no ALEX/PIE: stoichiometry checks n/a" if e.excitation == "cw" else ""))
    for group, title in (("basic", "Basic quality"), ("two-colour", "Two-colour")):
        rows = [c for c in q.checks if c.group == group]
        if not rows:
            continue
        im.separator_text(title)
        if im.begin_table(f"checks-{group}", 3):
            for c in rows:
                im.table_next_row()
                im.table_next_column()
                im.text_colored(LEVEL_COLOUR[c.level], c.level.upper())
                im.table_next_column()
                im.text(c.name)
                im.set_item_tooltip(c.detail)
                im.table_next_column()
                im.text(c.value)
                im.set_item_tooltip(c.detail)
            im.end_table()
    avail_w, avail_h = im.get_content_region_avail()
    size = (avail_w / 2 - 6, max(avail_h - 8.0, MIN_PLOT_H))
    t, rate = p.trace
    if ip.begin_plot("Count rate (1 s bins)", size):
        ip.setup_axes("time (s)", "count rate (kHz)")
        ip.plot_line("total", t, rate)
        ip.end_plot()
    im.same_line()
    if p.gaps is not None and ip.begin_plot("Gaps between bursts", size):
        x, counts, fit = p.gaps
        ip.setup_axes("log10 gap (ms)", "bursts")
        ip.plot_stairs("observed", x, counts)
        if fit is not None:
            ip.plot_line("Poisson arrivals", x, fit)
        ip.end_plot()


def draw_es(s, p) -> None:
    avail_w, avail_h = im.get_content_region_avail()
    if p.es is None:
        hist_plot("E (proximity ratio)", p.e_hist, "E", (avail_w, max(avail_h - 8.0, MIN_PLOT_H)))
        return
    side = max(min(avail_w * 0.62, avail_h - 8.0), MIN_PLOT_H)
    heatmap("E-S", p.es, "E", "S", ((-0.1, 1.1), (-0.1, 1.1)), (side, side))
    im.same_line()
    im.begin_group()
    w = max(avail_w - side - 10, 160.0)
    hist_plot("E", p.e_hist, "E", (w, side / 2 - 4))
    hist_plot("S", p.s_hist, "S", (w, side / 2 - 4))
    im.end_group()


def draw_bursts(s, p) -> None:
    avail_w, avail_h = im.get_content_region_avail()
    size = (avail_w / 2 - 6, max(avail_h / 2 - 8.0, MIN_PLOT_H))
    hist_plot("Burst size", p.size_hist, "log10 photons", size)
    im.same_line()
    hist_plot("Duration", p.dur_hist, "log10 duration (ms)", size)
    hist_plot("Count rate", p.rate_hist, "log10 count rate (kHz)", size)
    im.same_line()
    if p.tau is not None:
        heatmap("E vs donor lifetime", p.tau, "Tau (green) (ns)", "E", ((0, 6), (-0.1, 1.1)), size)
    else:
        heatmap("FRET-2CDE vs E", p.cde, "E", "FRET-2CDE", ((-0.1, 1.1), (0, 100)), size)


STREAM_LABEL = {"DD": "DD (green)", "DA": "DA (red)", "AA": "AA (acceptor exc.)"}


def draw_trace(s, width: float) -> None:
    """The count-rate trace of each stream in 1 ms bins, bursts shaded."""
    rates = getattr(s, "trace_rates", None)
    if not rates:
        empty("No data yet.")
        return
    bin_s = s.trace_bin_s
    n = len(next(iter(rates.values())))
    i0 = int(max(0.0, min(float(s.trace_start_s), n * bin_s - TRACE_SPAN_S)) / bin_s)
    i1 = min(n, i0 + int(TRACE_SPAN_S / bin_s))
    t = np.arange(i0, i1) * bin_s
    _, avail_h = im.get_content_region_avail()
    if ip.begin_plot("Count rate (1 ms bins)", (width, max(avail_h - 8.0, MIN_PLOT_H))):
        ip.setup_axes("time (s)", "count rate (kHz)")
        ip.setup_axes_limits(float(t[0]) if t.size else 0.0, float(t[-1]) if t.size else 1.0,
                             0.0, float(max((r[i0:i1].max(initial=1.0) for r in rates.values()))) * 1.05,
                             ip.COND_ALWAYS if hasattr(ip, "COND_ALWAYS") else 1)
        top = max(float(r[i0:i1].max(initial=1.0)) for r in rates.values())
        spans = s.trace_bursts
        if spans.size:
            sel = (spans[:, 1] >= t[0]) & (spans[:, 0] <= t[-1]) if t.size else np.zeros(len(spans), bool)
            xs, ys = [], []
            for a, b in spans[sel]:
                xs += [a, a, b, b]
                ys += [0.0, top, top, 0.0]
            if xs:
                ip.plot_shaded("bursts", np.asarray(xs), np.asarray(ys))
        for k, r in rates.items():
            ip.plot_line(STREAM_LABEL.get(k, k), t, r[i0:i1])
        ip.end_plot()


def draw_micro(s, width: float) -> None:
    """Micro-time (or µsALEX phase) histogram of every channel, windows marked."""
    hists = getattr(s, "micro_hist", None)
    if not hists:
        empty("No micro time in this file (cw without TCSPC).")
        return
    exp = s.exp
    if ip.begin_plot("Micro time per channel", (width, MIN_PLOT_H + 40)):
        unit = "phase (ticks)" if exp.alex_period else "micro-time channel"
        ip.setup_axes(unit, "photons")
        if hasattr(ip, "setup_axis_scale") and hasattr(ip, "SCALE_LOG10"):
            ip.setup_axis_scale(ip.AXIS_Y1, ip.SCALE_LOG10)
        for c, (edges, counts) in hists.items():
            role = ("donor" if c in exp.donor_channels else "acceptor" if c in exp.acceptor_channels
                    else "unassigned")
            ip.plot_stairs(f"ch {c} ({role})", edges[:-1], np.maximum(counts, 0.5))
        for w in exp.windows:
            ip.plot_inf_lines(f"{w.name} window", np.asarray([w.start, w.stop], float))
        ip.end_plot()
