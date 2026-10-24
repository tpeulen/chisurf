"""The PDF report: one page that says what the measurement is.

The FRET panel is ndX's -- :func:`ndxplorer.export.publication_figure.
draw_density_with_marginals` draws the same density-with-marginals picture
the ndX export prints, into this page's grid; fret_check does not keep a
second composer for the same science. The report values, the background and
the checks are fret_check's own content: header with the verdict, the
count-rate trace, the inter-burst gaps, the values table. Everything is
:class:`emtk.figure` vector drawing, so the page writes it as ``application/pdf``.
"""
from __future__ import annotations

from typing import Any

try:  # the page ships ndxplorer beside chisurf; a chisurf without it reports one-colour
    from ndxplorer.export.publication_figure import draw_density_with_marginals
except ImportError:  # pragma: no cover - the bundle guarantees ndxplorer
    draw_density_with_marginals = None

_LEVEL_COLOR = {"ok": "#1b5e20", "warn": "#6b4300", "bad": "#b71c1c", "": "#333333"}


def _fmt(x: Any, digits: int = 3) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if f == int(f) and abs(f) < 1e6:
        return str(int(f))
    return f"{f:.{digits}g}"


def _bare(ax):
    """A text-only cell on emtk with ``set_bare`` (0.1.33+); older emtk hides it."""
    return ax.set_bare() if hasattr(ax, "set_bare") else ax.hide()


def _draw_es_panel(fig, session, row_marginal: int, row_density: int) -> bool:
    """ndX's E/S density with its marginals into the page's rows; True when drawn."""
    import numpy as np

    if draw_density_with_marginals is None or session.bursts is None:
        return False
    b = session.bursts
    if b.S is None or not b.n:
        return False
    inside = ((b.E >= 0.0) & (b.E <= 1.0) & (b.S >= 0.0) & (b.S <= 1.0))
    x_e = np.linspace(0.0, 1.0, 51)
    y_s = np.linspace(0.0, 1.0, 51)
    H, _, _ = np.histogram2d(b.E[inside], b.S[inside], bins=[x_e, y_s])
    x_cnt, _ = np.histogram(b.E[inside], bins=x_e)
    y_cnt, _ = np.histogram(b.S[inside], bins=y_s)
    draw_density_with_marginals(
        fig, fig.ax(row_density, 0, span=3), fig.ax(row_marginal, 0, span=3),
        fig.ax(row_density, 3, span=2),
        H.T, x_e, y_s,  # (n_y, n_x) like Histogram2D stores
        x_marginal=(x_e, x_cnt), y_marginal=(y_s, y_cnt),
        x_label="FRET efficiency E", y_label="Stoichiometry S",
        z_log=True, count_labels=False,
    )
    density = fig.ax(row_density, 0)
    density.set_grid(False)
    density.set_xticks([0.0, 0.25, 0.5, 0.75, 1.0])
    density.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])
    fig.ax(row_marginal, 0).set_ylim(0.0, 1.2 * float(x_cnt.max()))
    fig.ax(row_density, 3).set_xlim(0.0, 1.2 * float(y_cnt.max()))
    fig.ax(row_density, 3).set_xticks(
        [0.0, float(int(round(1.2 * float(y_cnt.max()))))])
    fig.ax(row_density, 3).set_labels(x=" ")
    return True


import numpy as np


def _rebin(rate: np.ndarray, factor: int) -> np.ndarray:
    """Mean over every *factor* bins (1 ms bins to 10 ms / 1 s for the page)."""
    if factor < 2:
        return np.asarray(rate, float)
    n = (len(rate) // factor) * factor
    return np.asarray(rate, float)[:n].reshape(-1, factor).mean(axis=1)


_STREAM_HEX = {"DD": "#28a03c", "DA": "#b8860b", "AA": "#d2372d"}
_STREAM_NAME = {"DD": "DD (green)", "DA": "DA (yellow)", "AA": "AA (red)"}


def _draw_example_trace(fig, r: int, session) -> None:
    """The example photon trace: donor streams up, acceptor streams down."""
    from .app.plots import _trace_sides

    rates = getattr(session, "trace_rates", None) or {}
    if not rates:
        return
    bin_s = float(session.trace_bin_s)
    span_s = 10.0
    n = len(next(iter(rates.values())))
    i1 = min(n, int(span_s / bin_s))
    f10 = max(1, int(0.01 / bin_s))
    up, down = _trace_sides(rates)
    t = (np.arange(0, len(_rebin(next(iter(rates.values())), f10))) + 0.5) * bin_s * f10
    ax = fig.ax(r, 0, span=6)
    for k in up + down:
        y = _rebin(rates[k][:i1], f10)
        ax.line(t, y if k in up else -y, color=_STREAM_HEX.get(k, "#333333"), width=1.0)
    ax.set_xlim(0.0, float(t[-1] + bin_s * f10))
    top = max(float(_rebin(rates[k][:i1], f10).max(initial=1.0)) for k in up)
    bottom = max(float(_rebin(rates[k][:i1], f10).max(initial=1.0)) for k in down)
    spans = getattr(session, "trace_bursts", None)
    if spans is not None and spans.size and t.size:
        for a, b in spans[(spans[:, 1] >= t[0]) & (spans[:, 0] <= t[-1])]:
            ax.fill_between([a, b], [-bottom * 1.08, -bottom * 1.08],
                            [top * 1.08, top * 1.08], color="#9ec5e8", alpha=0.35)
    ax.hline(0.0, color="#666666", dash=":")
    ax.set_title("Photon trace, 10 ms bins (t in s): DD green, DA yellow up; AA red down")
    ax.set_labels(x="", y="kHz")
    ax.set_xticks(np.arange(0.0, float(t[-1]) + 1.0, 1.0))
    ax.set_xlim(t[0], t[-1] + 1e-9)
    ax.set_ylim(-bottom * 1.15, top * 1.15)


def _draw_log_cr(fig, r: int, session) -> None:
    """Each stream's count rate on a log scale: bleaching and drops at a glance."""
    rates = getattr(session, "trace_rates", None) or {}
    if not rates:
        return
    bin_s = float(session.trace_bin_s)
    f1 = max(1, int(1.0 / bin_s))
    ax = fig.ax(r, 0, span=6)
    ax.set_log(y=True)
    for k, rate in rates.items():
        y = np.maximum(_rebin(rate, f1), 0.05)
        t = (np.arange(len(y), dtype=float) + 0.5) * bin_s * f1
        ax.line(t, y, color=_STREAM_HEX.get(k, "#333333"), width=1.2)
    ax.set_title("Count rate per stream, 1 s bins (t in s, log): DD green, DA yellow, AA red")
    ax.set_labels(x="", y="kHz")
    ax.set_xticks(np.arange(0.0, float(t[-1]) + 1.0, 1.0))
    binned = [np.maximum(_rebin(v, f1), 0.05) for v in rates.values() if np.any(v > 0)]
    peak = max(float(np.max(b)) for b in binned)
    floor = 0.5 * min(float(b[b > 0].min()) for b in binned)
    ax.set_ylim(max(floor, 0.01), 2.0 * peak)
    ax.set_xlim(0.0, float(t[-1] + bin_s * f1))


def _scatter(fig, r: int, c: int, x, y, title: str, x_label: str, y_label: str,
             color: str = "#1f4e8c", span: int = 1) -> bool:
    """A burst-wise scatter panel; False (and the cell stays empty) without data."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return False
    x, y = x[ok], y[ok]
    if len(x) > 1500:  # a page carries markers, not a point cloud
        idx = np.linspace(0, len(x) - 1, 1500).astype(int)
        x, y = x[idx], y[idx]
    ax = fig.ax(r, c, span=span)
    ax.scatter(x, y, size=1.2, color=color, alpha=0.45)
    ax.set_title(title)
    ax.set_labels(x=x_label, y=y_label)
    if "static FRET" in title:  # tau_D(E) = tau_D0 (1 - E), the MFD reference
        donor_only = x[y < 0.2]  # x is tau_D, y is E here
        tau0 = float(np.nanmedian(donor_only)) if donor_only.size >= 5 \
            else float(np.nanpercentile(x, 95))
        e_grid = np.linspace(0.0, 1.0, 64)
        ax.line(np.clip(tau0 * (1.0 - e_grid), 0.0, None), e_grid,
                color="#888888", width=1.2)
        ax.set_yticks([0.0, 0.25, 0.5, 0.75, 1.0])
    elif title.startswith("Tg-Tr"):
        lo, hi = np.percentile(y, [1.0, 99.0])  # outliers stay, scale does not stretch
        pad = 0.1 * (hi - lo)
        ax.set_ylim(lo - pad, hi + pad)
        step = (hi - lo) / 2.0
        ax.set_yticks([round(lo, 2), round(lo + step, 2), round(hi, 2)])
    elif title.startswith("r vs"):
        lo, hi = float(y.min()), float(y.max())
        step = (hi - lo) / 2.0
        ax.set_yticks([round(lo, 2), round(lo + step, 2), round(hi, 2)])
    x0, x1 = float(x.min()), float(x.max())
    y0, y1 = float(y.min()), float(y.max())
    ax.set_xlim(x0 - 0.06 * max(x1 - x0, 1e-6), x1 + 0.06 * max(x1 - x0, 1e-6))
    ax.set_ylim(y0 - 0.08 * max(y1 - y0, 1e-6), y1 + 0.08 * max(y1 - y0, 1e-6))
    return True


def build_pdf_report(session) -> bytes:
    """The report page for a finished analysis: ``%PDF`` bytes.

    *session* is the app session (:class:`...app.session.Session`) with
    ``exp``, ``bursts`` and ``qc`` set -- the same state the verdict draws
    from. The A4/Letter page carries the diagnostics the app shows: the ndX
    E/S panel, the example photon trace (donor up, acceptor down), each
    stream's count rate on a log scale, the MFD panels the data supports
    (Tg-Tr vs E, E vs donor lifetime, anisotropy vs lifetime), the
    inter-burst gaps, and the checks/values table.
    """
    import datetime

    import numpy as np
    from emtk.figure import Figure, colorbar_space

    qc = session.qc
    bursts = session.bursts
    exp = session.exp
    level = qc.level if qc is not None else ""
    verdict = {"ok": "usable", "warn": "use with care", "bad": "not usable"}.get(level, "")
    n_bursts = bursts.n if bursts is not None else 0
    width, height = 816.0, 1056.0  # US Letter at 96 px/inch -> 612x792 pt page
    sixth = width / 6.0

    extra = bursts.extra if bursts is not None else {}
    tg = extra.get("TGX-TRR")
    tau_g = extra.get("Tau (green)")
    r_g = extra.get("r Experimental (green)")
    e = bursts.E if bursts is not None else np.zeros(0)
    has_trace = bool(getattr(session, "trace_rates", None))
    has_bursts = bursts is not None and n_bursts

    # Histograms fill the E/S block's side cells (beside the E marginal and
    # the density); the MFD scatters fill whole rows below, three at a time.
    hists: list[tuple] = []
    if qc is not None and len(qc.gaps) and np.any(qc.gaps > 0):
        hists.append(("gaps", np.log10(qc.gaps[qc.gaps > 0]), "Inter-burst gaps", "log10 s"))
    if has_bursts:
        hists.append(("duration", np.log10(np.maximum(bursts.duration * 1e3, 1e-2)),
                      "Burst duration", "log10 ms"))

    scatters: list[tuple] = []
    if tg is not None:
        scatters.append((e, tg, "Tg-Tr vs E", "E", "Tg-Tr (ms)", "#1f4e8c"))
    if tau_g is not None:
        scatters.append((tau_g, e, "E vs tau_D (static FRET)",
                         "Tau green (ns)", "E", "#7a1f1f"))
    if r_g is not None and tau_g is not None:
        scatters.append((tau_g, r_g, "r vs tau_D", "Tau green (ns)", "r green", "#1f6e4a"))
    if has_bursts:  # the half-width cell beside the density carries the sizes
        hists = hists  # size drawn in the block below
    n_diag = len(scatters) + len(hists)

    rows: list[tuple[float, str]] = [(2.4, "marginal"), (5.6, "density")]
    if has_trace:
        rows.append((3.2, "trace"))
        rows.append((3.2, "log_cr"))
    if n_diag:
        rows.append((3.6, "diag_a"))
    if n_diag > 3:
        rows.append((3.6, "diag_b"))
    rows.append((4.0, "table"))
    fig = Figure(rows=len(rows), cols=6, size=(width, height), margin=40.0,
                 width_ratios=[sixth] * 6, height_ratios=[r for r, _ in rows])
    at = {name: i for i, (_, name) in enumerate(rows)}
    at["header"] = at["marginal"]  # header text lives beside the E marginal

    # -- header: file, date, the verdict in its colour -----------------------
    head = _bare(fig.ax(at["header"], 3, span=3))
    head.set_xlim(0.0, 1.0)
    head.set_ylim(0.0, 1.0)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    name = session.path if session.path else "simulated measurement"
    if name.startswith("simulated: "):
        name = name[11:]
    title = "FRET check report"
    if exp is not None and exp.excitation:
        title += f" ({exp.excitation.lower()})"
    head.text(0.06, 0.88, title, color="#111111", align="left")
    head.text(0.06, 0.58, name, color="#444444", align="left")
    head.text(0.06, 0.30, now, color="#333333", align="left")
    head.text(0.55, 0.30, f"QC: {verdict}" if verdict else "QC: --",
              color=_LEVEL_COLOR.get(level, "#333333"), align="left")

    # -- the FRET panel: ndX's density with marginals -------------------------
    r_m, r_d = at["marginal"], at["density"]
    drew_es = _draw_es_panel(fig, session, row_marginal=r_m, row_density=r_d)
    if not drew_es:
        if bursts is not None and n_bursts:
            ax_e = fig.ax(r_d, 0, span=3)
            ax_e.hist(np.clip(bursts.E, 0.0, 1.0), 50, range=(0.0, 1.0))
            ax_e.set_title("FRET efficiency E")
            ax_e.set_labels(x="E", y="bursts")
        else:
            fig.ax(r_d, 0).hide()
        for c in (3, 4):
            fig.ax(r_d, c).hide()

    if has_bursts:  # the last cell of the density row carries the burst sizes
        ax_s = fig.ax(r_d, 5)
        ax_s.hist(np.log10(np.maximum(bursts.size, 1)), 40)
        ax_s.set_title("Burst size")
        ax_s.set_labels(x="log10 photons", y="")
        ax_s.set_xticks([1.5, 2.5, 3.5])
    else:
        fig.ax(r_d, 5).hide()

    # -- diagnostics: example trace, per-stream log count rate ----------------
    if has_trace:
        _draw_example_trace(fig, at["trace"], session)
        _draw_log_cr(fig, at["log_cr"], session)

    # -- MFD diagnostics the data supports: half-width slots, three to a row --
    diag_rows = [at[k] for k in ("diag_a", "diag_b") if k in at]
    packed = scatters + hists
    packed = packed[:len(diag_rows) * 3]
    row_size = [min(3, max(0, len(packed) - 3 * j)) for j in range(len(diag_rows))]

    def slot_starts(n: int) -> list[int]:
        # equal-width slots: 1 -> [0], 2 -> [0, 3], 3 -> [0, 2, 4]
        return [round(j * 6 / n) for j in range(n)]

    for j, r in enumerate(diag_rows):
        starts = slot_starts(row_size[j])
        span = 6 // row_size[j] if row_size[j] else 0
        for slot in range(3):
            i = 3 * j + slot
            if i >= len(packed) or slot >= row_size[j]:
                if slot < 3:
                    fig.ax(r, round(slot * 6 / 3), span=2).hide()
                continue
            spec = packed[i]
            if len(spec) == 6:
                xs, ys, title, xl, yl, color = spec
                if not _scatter(fig, r, starts[slot], xs, ys, title, xl, yl,
                                color=color, span=span):
                    fig.ax(r, starts[slot], span=span).hide()
            else:
                _, values, title, unit = spec
                ax_h = fig.ax(r, starts[slot], span=span)
                ax_h.hist(values, 40)
                ax_h.set_title(title)
                ax_h.set_labels(x=unit, y="count")

    # -- the values: every check, the background, the key numbers -------------
    table = _bare(fig.ax(at["table"], 0, span=6))
    table.set_xlim(0.0, 1.0)
    table.set_ylim(0.0, 1.0)
    if qc is not None:
        # The checks flow through both columns (half each), the values
        # continue in the second below them -- balanced, one line per pitch.
        checks = list(qc.checks)
        half = (len(checks) + 1) // 2
        y0 = 0.955
        y_end = {0.06: y0, 0.56: y0}
        for x, group in ((0.06, checks[:half]), (0.56, checks[half:])):
            y = y0
            table.text(x, y, "Checks" if x < 0.5 else "Checks (cont.)", color="#111111", align="left")
            y -= 0.078
            for c in group:
                mark = {"ok": "+", "warn": "!", "bad": "x", "": "·"}.get(c.level, "·")
                color = _LEVEL_COLOR.get(c.level, "#333333")
                line = f"{mark} {c.name}: {c.value}"
                if len(line) > 40:  # a value that outruns the column: two rows
                    table.text(x, y, f"{mark} {c.name}", color=color, align="left")
                    y -= 0.078
                    if y < 0.04:
                        break
                    line = f"    {c.value}"
                table.text(x, y, line, color=color, align="left")
                y -= 0.078
                if y < 0.28:
                    break
            y_end[x] = y
        # Values: a reserved baseline of its own, so a long checks column
        # can never push the concentration metrics off the page.
        joined = (f"Flagged: {int((qc.flags != 0).sum())} of {qc.flags.size}"
                  f" \u00b7 Arrival (corr.): {_fmt(qc.arrival_rate)} /s"
                  f" \u00b7 Volume: {_fmt(qc.metrics.get('v_eff_fL', ''))} fL")
        table.text(0.06, 0.19, "Values", color="#111111", align="left")
        table.text(0.06, 0.07, joined, color="#333333", align="left")
    from emtk import implot as _eimpl
    _gp = _eimpl.gp
    _saved = (_gp.style.plot_padding, _gp.style.label_padding)
    _gp.style.plot_padding = (5.0, 5.0)
    _gp.style.label_padding = (3.0, 3.0)
    try:
        return fig.pdf_bytes()
    finally:
        _gp.style.plot_padding, _gp.style.label_padding = _saved
