"""Replacing a bar graph's data through its handle redraws the bars.

The emtk backend's generic entry wrote ``set_data`` into ``x``/``y`` while a bar
graph draws ``height``, so a histogram updated through the ``Bars`` handle kept
showing its first bars.
"""

from __future__ import annotations

import numpy as np


def test_bars_set_data_replaces_the_heights():
    from chisurf.chiplot.backends.emtk_backend import EmtkCanvas

    canvas = EmtkCanvas()
    bars = canvas.add_bars(np.arange(3.0), np.array([1.0, 2.0, 3.0]))
    bars.set_data(np.arange(4.0), np.array([4.0, 3.0, 2.0, 1.0]))
    x, height = bars.get_data()
    np.testing.assert_array_equal(x, [0.0, 1.0, 2.0, 3.0])
    np.testing.assert_array_equal(height, [4.0, 3.0, 2.0, 1.0])
    bars.set_data(np.arange(2.0), height=np.array([7.0, 8.0]))
    np.testing.assert_array_equal(bars.get_data()[1], [7.0, 8.0])
