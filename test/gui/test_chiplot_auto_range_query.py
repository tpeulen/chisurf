"""A panel says whether each axis still follows its data.

A saved session has to tell a view the user zoomed or panned from one that is
autoscaling: the first is restored to the saved range, the second keeps fitting
the data. ``get_range`` alone cannot tell them apart.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from chisurf.gui.chiplot import backends as _backends  # noqa: E402


@pytest.fixture(params=["emtk", "pyqtgraph"])
def plot(request, qapp):
    previous, previous_env = _backends._active, os.environ.get("CHISURF_PLOT_BACKEND")
    os.environ["CHISURF_PLOT_BACKEND"] = request.param
    _backends._active = None
    from chisurf.gui import chiplot as cp

    panel = cp.Plot()
    x = np.linspace(0.0, 25.0, 128)
    panel.line(x, 1000.0 * np.exp(-x / 4.0) + 5.0, name="decay")
    try:
        yield panel
    finally:
        panel.close()
        _backends._active = previous
        if previous_env is None:
            os.environ.pop("CHISURF_PLOT_BACKEND", None)
        else:
            os.environ["CHISURF_PLOT_BACKEND"] = previous_env


def test_axes_follow_the_data_until_a_range_is_set(plot):
    assert plot.is_auto_range() == (True, True)
    plot.set_range(x=(5.0, 10.0))
    assert plot.is_auto_range() == (False, True)
    plot.set_range(y=(1.0, 100.0))
    assert plot.is_auto_range() == (False, False)
    # Continuous autoscale is following the data again on every backend (a one-shot
    # fit holds its result on pyqtgraph, which is_auto_range reports truthfully).
    plot.autoscale(continuous=True)
    assert plot.is_auto_range() == (True, True)
