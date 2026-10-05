"""The microtime waterfall plot draws with emtk.figure: time downwards, as an image."""

from __future__ import annotations

import numpy as np


def test_the_waterfall_is_an_image_with_time_running_down(tmp_path):
    from chisurf.plugins.tttr.audifier.core import plot_waterfall

    W = np.arange(12, dtype=float).reshape(4, 3)
    ax = plot_waterfall(W, np.array([0.0, 1.0, 2.0, 3.0]), np.array([0.0, 1.0, 2.0]))
    (kind, data), = ax._items
    assert kind == "heatmap" and data["rows"] == 4 and data["cols"] == 3
    assert ax.yinvert, "the first macro-time bin belongs at the top"
    assert ax.figure.save(tmp_path / "w.png").read_bytes()[:4] == b"\x89PNG"
