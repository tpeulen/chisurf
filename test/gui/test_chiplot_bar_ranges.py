"""Bar-only native panels fit their rectangles, including the baseline and bin width."""

import numpy as np

from chisurf import chiplot as cp
from chisurf.chiplot import backends


def test_bar_only_panel_fits_real_histogram_rectangles(monkeypatch):
    """A histogram outside the unit square remains entirely reachable before and after paint."""
    from emtk.testing import PixelPainter

    monkeypatch.setenv("CHISURF_PLOT_BACKEND", "emtk")
    monkeypatch.setattr(backends, "_active", None)
    plot = cp.Panel()
    plot.bars([2.0, 4.0], [2.0, 7.0], width=1.0)
    for painted in (False, True):
        if painted:
            plot._canvas.draw(PixelPainter(900, 500), 0.0, 0.0, 900.0, 500.0)
        (x0, x1), (y0, y1) = plot.get_range()
        assert x0 <= 1.5 and x1 >= 4.5
        assert y0 <= 0.0 and y1 >= 7.0
    heights = plot._canvas._entries[0].state["height"]
    np.testing.assert_array_equal(heights, [2.0, 7.0])
