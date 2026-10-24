"""The PDF report: one page that says what the measurement is.

The histograms, the background, the report values -- composed as an
:class:`emtk.figure.Figure` (vector, pure Python, so the page draws it too)
and handed to the app's ``download`` plumbing as ``application/pdf``.
"""
from __future__ import annotations

from typing import Any

_LEVEL_COLOR = {"ok": "#2e7d32", "warn": "#b26a00", "bad": "#b71c1c", "": "#333333"}


def _fmt(x: Any, digits: int = 3) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if f == int(f) and abs(f) < 1e6:
        return str(int(f))
    return f"{f:.{digits}g}"


def build_pdf_report(session) -> bytes:
    """The report page for a finished analysis: ``%PDF`` bytes.

    *session* is the app session (:class:`...app.session.Session`) with
    ``exp``, ``bursts`` and ``qc`` set -- the same state the verdict draws
    from. The layout: header with the verdict, E and S histograms, the
    count-rate trace, the inter-burst gaps, and the values table.
    """
    import datetime

    import numpy as np
    from emtk.figure import Figure

    qc = session.qc
    bursts = session.bursts
    exp = session.exp
    level = qc.level if qc is not None else ""
    n_bursts = bursts.n if bursts is not None else 0

    fig = Figure(rows=5, cols=2, size=(612.0, 792.0),
                 height_ratios=(0.9, 1.3, 1.0, 1.0, 1.6))

    # -- header: file, date, the verdict in its colour -----------------------
    head = fig.axes[0]
    head.hide()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    name = session.path if session.path else "simulated measurement"
    if name.startswith("simulated: "):
        name = name[11:]
    head.text(0.02, 0.72, "FRET check report", color="#111111")
    head.text(0.02, 0.50, name, color="#444444")
    head.text(0.02, 0.30, f"{now}   |   {n_bursts} bursts"
               + (f"   |   {exp.excitation.upper()}" if exp is not None else ""),
               color="#444444")
    verdict = {"ok": "usable", "warn": "use with care", "bad": "not usable"}.get(level, "")
    head.text(0.02, 0.06, f"Verdict: {verdict}" if verdict else "Verdict: --",
              color=_LEVEL_COLOR.get(level, "#333333"))

    # -- the FRET histograms -------------------------------------------------
    if bursts is not None and n_bursts:
        ax_e = fig.axes[1]
        ax_e.hist(np.clip(bursts.E, 0.0, 1.0), 50, range=(0.0, 1.0))
        ax_e.set_title("FRET efficiency E")
        ax_e.set_labels(x="E", y="bursts")
        ax_s = fig.axes[2]
        if bursts.S is not None:
            ax_s.hist(np.clip(bursts.S, 0.0, 1.0), 50, range=(0.0, 1.0))
            ax_s.set_title("Stoichiometry S")
            ax_s.set_labels(x="S", y="bursts")
        else:
            ax_s.hist(bursts.size, 40)
            ax_s.set_title("Burst size (photons)")
            ax_s.set_labels(x="photons", y="bursts")

    # -- the count-rate trace: stability at a glance --------------------------
    if qc is not None and len(qc.trace_t):
        ax_t = fig.axes[3]
        fig.axes[4].hide()
        ax_t.line(qc.trace_t, qc.trace_rate, width=1.2)
        mean = float(np.mean(qc.trace_rate)) if len(qc.trace_rate) else 0.0
        ax_t.hline(mean, color="#b26a00", dash="--")
        ax_t.set_title("Count rate (1 s bins; dashed: mean)")
        ax_t.set_labels(x="t (s)", y="kHz")

    # -- the inter-burst gaps: multi-molecule at a glance ---------------------
    if qc is not None and len(qc.gaps):
        ax_g = fig.axes[5]
        fig.axes[6].hide()
        g = qc.gaps[qc.gaps > 0]
        if g.size:
            ax_g.hist(np.log10(g), 40)
            ax_g.set_title("Inter-burst gaps (log10 s)")
            ax_g.set_labels(x="log10 gap (s)", y="count")

    # -- the values: every check, the background, the key numbers -------------
    table = fig.axes[7]
    table.hide()
    fig.axes[8].hide()
    fig.axes[9].hide()
    y = 0.97
    if qc is not None:
        table.text(0.0, y, "Checks", color="#111111")
        y -= 0.055
        for c in qc.checks:
            mark = {"ok": "+", "warn": "!", "bad": "x"}.get(c.level, " ")
            table.text(0.0, y, f"{mark}  {c.name}: {c.value}", color=_LEVEL_COLOR.get(c.level, "#333333"))
            y -= 0.045
        y -= 0.02
        table.text(0.0, y, "Values", color="#111111")
        y -= 0.055
        rows = [
            ("Burst rate", f"{_fmt(qc.burst_rate)} /s"),
            ("Occupancy (molecules in volume)", _fmt(qc.occupancy)),
            ("P(>=2 molecules | burst)", f"{_fmt(100 * qc.p_multi)} %"),
            ("  from inter-burst gaps", f"{_fmt(100 * qc.p_multi_gaps)} %"),
            ("Arrival rate", f"{_fmt(qc.arrival_rate)} /s"),
            ("Flagged bursts", f"{int((qc.flags != 0).sum())} of {qc.flags.size}"),
        ]
        for k, v in qc.metrics.items():
            rows.append((k, _fmt(v)))
        if bursts is not None:
            for stream, rate in sorted(bursts.background.items()):
                rows.append((f"Background {stream}", f"{_fmt(rate / 1e3)} kHz"))
        for k, v in rows:
            table.text(0.0, y, f"{k}: {v}", color="#333333")
            y -= 0.045
            if y < 0.02:
                break
    return fig.pdf_bytes()
