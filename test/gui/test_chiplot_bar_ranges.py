"""Bar-only native panels fit their rectangles, including the baseline and bin width."""

import numpy as np

from chisurf.chiplot import backends
from chisurf.gui import chiplot as cp


def test_bar_only_panel_fits_real_histogram_rectangles(qapp, monkeypatch):
    """A histogram outside the unit square remains entirely reachable before and after paint."""
    monkeypatch.setenv("CHISURF_PLOT_BACKEND", "emtk")
    monkeypatch.setattr(backends, "_active", None)
    plot = cp.Panel()
    widget = cp.host(plot)
    try:
        plot.bars([2.0, 4.0], [2.0, 7.0], width=1.0)
        for painted in (False, True):
            if painted:
                widget.resize(900, 500)
                widget.show()
                qapp.processEvents()
                widget.grab()
            (x0, x1), (y0, y1) = plot.get_range()
            assert x0 <= 1.5 and x1 >= 4.5
            assert y0 <= 0.0 and y1 >= 7.0
        heights = plot._canvas._entries[0].state["height"]
        np.testing.assert_array_equal(heights, [2.0, 7.0])
    finally:
        widget.close()
        qapp.processEvents()
