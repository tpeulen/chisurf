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

_LEVEL_COLOR = {"ok": "#2e7d32", "warn": "#b26a00", "bad": "#b71c1c", "": "#333333"}


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


def _draw_es_panel(fig, session) -> bool:
    """ndX's E/S density with its marginals, drawn into rows 1-2; True when drawn."""
    import numpy as np

    if draw_density_with_marginals is None or session.bursts is None:
        return False
    b = session.bursts
    if b.S is None or not b.n:
        return False
    x_e = np.linspace(0.0, 1.0, 51)
    y_s = np.linspace(0.0, 1.0, 51)
    H, _, _ = np.histogram2d(np.clip(b.E, 0.0, 1.0), np.clip(b.S, 0.0, 1.0),
                             bins=[x_e, y_s])
    _, x_cnt = np.histogram(np.clip(b.E, 0.0, 1.0), bins=x_e)
    _, y_cnt = np.histogram(np.clip(b.S, 0.0, 1.0), bins=y_s)
    draw_density_with_marginals(
        fig, fig.ax(2, 0), fig.ax(1, 0), fig.ax(2, 1),
        H.T, x_e, y_s,  # (n_y, n_x) like Histogram2D stores
        x_marginal=(x_e, x_cnt), y_marginal=(y_s, y_cnt),
        x_label="FRET efficiency E", y_label="Stoichiometry S",
    )
    return True


def build_pdf_report(session) -> bytes:
    """The report page for a finished analysis: ``%PDF`` bytes.

    *session* is the app session (:class:`...app.session.Session`) with
    ``exp``, ``bursts`` and ``qc`` set -- the same state the verdict draws
    from. The layout: header with the verdict, the ndX E/S panel, the
    count-rate trace, the inter-burst gaps, and the values table.
    """
    import datetime

    import numpy as np
    from emtk.figure import Figure, colorbar_space

    qc = session.qc
    bursts = session.bursts
    exp = session.exp
    level = qc.level if qc is not None else ""
    n_bursts = bursts.n if bursts is not None else 0
    width = 612.0
    side = width * 1.0 / 5.0 + colorbar_space(False)

    fig = Figure(rows=6, cols=2, size=(width, 792.0),
                 width_ratios=[width - side, side],
                 height_ratios=(0.9, 1.0, 4.0, 1.1, 1.1, 2.1))

    # -- header: file, date, the verdict in its colour -----------------------
    head = _bare(fig.ax(0, 0))
    fig.ax(0, 1).hide()
    head.set_xlim(0.0, 1.0)
    head.set_ylim(0.0, 1.0)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    name = session.path if session.path else "simulated measurement"
    if name.startswith("simulated: "):
        name = name[11:]
    head.text(0.5, 0.72, "FRET check report", color="#111111")
    head.text(0.5, 0.50, name, color="#444444")
    head.text(0.5, 0.30, f"{now}   |   {n_bursts} bursts"
               + (f"   |   {exp.excitation.upper()}" if exp is not None else ""),
               color="#444444")
    verdict = {"ok": "usable", "warn": "use with care", "bad": "not usable"}.get(level, "")
    head.text(0.5, 0.06, f"Verdict: {verdict}" if verdict else "Verdict: --",
              color=_LEVEL_COLOR.get(level, "#333333"))

    # -- the FRET panel: ndX's density with marginals -------------------------
    drew_es = _draw_es_panel(fig, session)
    if not drew_es:
        fig.ax(1, 0).hide()
        fig.ax(2, 1).hide()
        if bursts is not None and n_bursts:
            ax_e = fig.ax(2, 0)
            ax_e.hist(np.clip(bursts.E, 0.0, 1.0), 50, range=(0.0, 1.0))
            ax_e.set_title("FRET efficiency E")
            ax_e.set_labels(x="E", y="bursts")

    # -- the count-rate trace: stability at a glance --------------------------
    if qc is not None and len(qc.trace_t):
        ax_t = fig.ax(3, 0)
        ax_t.line(qc.trace_t, qc.trace_rate, width=1.2)
        mean = float(np.mean(qc.trace_rate)) if len(qc.trace_rate) else 0.0
        ax_t.hline(mean, color="#b26a00", dash="--")
        ax_t.set_title("Count rate (1 s bins; dashed: mean)")
        ax_t.set_labels(x="t (s)", y="kHz")

    # -- the inter-burst gaps: multi-molecule at a glance ---------------------
    if qc is not None and len(qc.gaps):
        ax_g = fig.ax(4, 0)
        g = qc.gaps[qc.gaps > 0]
        if g.size:
            ax_g.hist(np.log10(g), 40)
            ax_g.set_title("Inter-burst gaps (log10 s)")
            ax_g.set_labels(x="log10 gap (s)", y="count")

    # -- the values: every check, the background, the key numbers -------------
    table = _bare(fig.ax(5, 0))
    fig.ax(5, 1).hide()
    table.set_xlim(0.0, 1.0)
    table.set_ylim(0.0, 1.0)
    y = 0.985
    if qc is not None:
        table.text(0.5, y, "Checks", color="#111111")
        y -= 0.038
        for c in qc.checks:
            mark = {"ok": "+", "warn": "!", "bad": "x"}.get(c.level, " ")
            table.text(0.5, y, f"{mark}  {c.name}: {c.value}",
                       color=_LEVEL_COLOR.get(c.level, "#333333"))
            y -= 0.031
        y -= 0.012
        table.text(0.5, y, "Values", color="#111111")
        y -= 0.038
        # The checks above already carry the metrics (burst rate, occupancy,
        # P(multi), concentration, brightness, S/B, background summary); the
        # values repeat only what they do not show.
        rows = [
            ("Flagged bursts", f"{int((qc.flags != 0).sum())} of {qc.flags.size}"),
            ("Arrival rate", f"{_fmt(qc.arrival_rate)} /s"),
            ("Detection volume", f"{_fmt(qc.metrics.get('v_eff_fL', ''))} fL"),
        ]
        if bursts is not None:
            for stream, rate in sorted(bursts.background.items()):
                rows.append((f"Background {stream}", f"{_fmt(rate / 1e3)} kHz"))
        for k, v in rows:
            table.text(0.5, y, f"{k}: {v}", color="#333333")
            y -= 0.031
            if y < 0.02:
                break
    return fig.pdf_bytes()
