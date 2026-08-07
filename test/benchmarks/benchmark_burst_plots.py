"""What a burst-diagnostic repaint costs, and which knob actually moves it.

The work unit is **one repaint of one plot widget** holding a raw per-photon
series -- the delta-macro-time trace, the count-rate trace, the selection flag.
That is the fair unit because it is what the window pays on every settings
change, every tab switch and every resize, and because a burst-selection session
is mostly repaints: the burst search over 1.8 M photons is 0.04 s, while the
window that displays it was taking 0.29 s per frame.

Three knobs are measured against each other on the same synthetic trace, because
two of them look like the obvious answer and are not:

* **point count** -- what "decimate the data" changes;
* **viewport decimation** (``setDownsampling(auto, peak)`` + ``setClipToView``)
  -- what makes the cost depend on the *visible* range instead of the array;
* **pen width** -- a Qt pen wider than a pixel is not cosmetic, it strokes a
  real outline.

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


def _bench(n, width, antialias, downsample, log_y=False, repeats=REPEATS):
    """Return seconds per repaint for one configuration."""
    import pyqtgraph as pg
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widget = pg.PlotWidget()
    widget.resize(*WIDGET_SIZE)
    widget.show()
    item = widget.getPlotItem()
    item.setLogMode(False, log_y)
    if downsample:
        item.setDownsampling(auto=True, mode="peak")
        item.setClipToView(True)

    rng = np.random.default_rng(0)
    x = np.arange(n, dtype=np.float64)
    y = np.abs(rng.standard_normal(n)) + 1e-4
    widget.plot(x, y, pen=pg.mkPen((255, 255, 0), width=width), antialias=antialias)
    app.processEvents()
    widget.grab()  # warm-up

    start = time.perf_counter()
    for _ in range(repeats):
        item.getViewBox().update()
        widget.grab()
    elapsed = (time.perf_counter() - start) / repeats
    widget.close()
    return elapsed


#: (points, pen width, antialias, viewport decimation, log y)
CASES = (
    (66_000, 1, False, False, False),
    (66_000, 2, False, False, False),
    (66_000, 1, True, False, False),
    (66_000, 1, False, True, False),
    (66_000, 2, False, True, False),
    (66_000, 1, False, True, True),
    (660_000, 1, False, False, False),
    (660_000, 1, False, True, False),
    (660_000, 2, False, True, False),
)


def run(cases=CASES):
    """Measure every case and print a markdown table."""
    records = []
    for n, width, antialias, downsample, log_y in cases:
        records.append(
            {
                "points": n,
                "pen_width": width,
                "antialias": antialias,
                "downsample": downsample,
                "log_y": log_y,
                "seconds": _bench(n, width, antialias, downsample, log_y),
            }
        )

    print("| points | pen width | antialias | viewport decimation | log y | s/repaint |")
    print("|---:|---:|:---:|:---:|:---:|---:|")
    for r in records:
        print(
            f"| {r['points']:,} | {r['pen_width']} | {'yes' if r['antialias'] else 'no'} "
            f"| {'yes' if r['downsample'] else 'no'} | {'yes' if r['log_y'] else 'no'} "
            f"| {r['seconds']:.3f} |"
        )
    return records


if __name__ == "__main__":
    run()
