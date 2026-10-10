"""What a burst-diagnostic repaint costs on chiplot's emtk backend.

The work unit is **one repaint of one plot widget** holding a raw per-photon
series -- the delta-macro-time trace, the count-rate trace, the selection flag.
That is the fair unit because it is what the window pays on every settings
change, every tab switch and every resize, and because a burst-selection session
is mostly repaints: the burst search over 1.8 M photons is 0.04 s, while the
window that displays it was taking 0.29 s per frame.

The knobs measured are the ones that remain on the emtk backend: **point count**
(what "decimate the data" changes) and a **log y axis**. Viewport decimation,
antialiasing and pen width were pyqtgraph knobs (``setDownsampling``,
``setClipToView``, a wide Qt pen); the backend they belonged to is gone and
emtk draws the samples it is given, so the caller thins the data. The numbers
recorded in ``docs/development/benchmarks.md`` for those knobs were measured on
the old backend and are kept there as history.

Run it::

    QT_QPA_PLATFORM=offscreen python test/benchmarks/benchmark_burst_plots.py
"""

from __future__ import annotations

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

#: Widget size the numbers are quoted for. Paint cost scales with the area Qt
#: has to fill, so a size is part of the measurement, not an incidental.
WIDGET_SIZE = (1500, 400)

#: Repaints averaged per row, after one warm-up paint (the first builds caches).
REPEATS = 3


def _bench(n, log_y=False, repeats=REPEATS):
    """Return seconds per repaint of a chiplot plot holding *n* points."""
    from qtpy import QtWidgets

    from chisurf.gui import chiplot as cp

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    plot = cp.Plot()
    plot.resize(*WIDGET_SIZE)
    plot.show()
    plot.set_log(y=log_y)

    rng = np.random.default_rng(0)
    x = np.arange(n, dtype=np.float64)
    y = np.abs(rng.standard_normal(n)) + 1e-4
    plot.line(x, y, pen=(255, 255, 0), width=1)
    app.processEvents()
    plot.grab()  # warm-up

    start = time.perf_counter()
    for _ in range(repeats):
        plot.update()
        plot.grab()
    elapsed = (time.perf_counter() - start) / repeats
    plot.close()
    return elapsed


#: (points, log y)
CASES = (
    (66_000, False),
    (66_000, True),
    (660_000, False),
    (660_000, True),
)


def run(cases=CASES):
    """Measure every case and print a markdown table."""
    records = [
        {"points": n, "log_y": log_y, "seconds": _bench(n, log_y)} for n, log_y in cases
    ]
    print("| points | log y | s/repaint |")
    print("|---:|:---:|---:|")
    for r in records:
        print(f"| {r['points']:,} | {'yes' if r['log_y'] else 'no'} | {r['seconds']:.3f} |")
    return records


if __name__ == "__main__":
    run()
