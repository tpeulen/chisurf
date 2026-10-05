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


def test_a_log_spaced_lifetime_axis_is_drawn_uniform_in_log_tau(tmp_path):
    """A peak at tau = 1 ns sits at log10 = -9, not where a linear image put it."""
    from chisurf.plugins.tttr.audifier.lifetime_analysis import plot_lifetime_waterfall

    tau = np.logspace(-10, -7, 31)
    A = np.zeros((5, 31))
    A[:, 10] = 100.0  # tau[10] = 1e-9
    ax = plot_lifetime_waterfall(A, np.linspace(0.0, 4.0, 5), tau)
    (kind, data), = ax._items
    x0, x1, _, _ = data["extent"]
    assert (x0, x1) == (-10.0, -7.0)
    assert ax.xticks[1] == ["1e-10", "1e-9", "1e-8", "1e-7"]
    assert ax.colorbar["label"] == "ln(1 + counts)"
    assert ax.figure.save(tmp_path / "lt.png").read_bytes()[:4] == b"\x89PNG"
