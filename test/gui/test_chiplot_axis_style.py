"""chiplot axis styling verbs: axis colours, categorical tick labels, legend colour."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from chisurf.gui import chiplot as cp
from chisurf.gui.chiplot import backends


@pytest.fixture(params=["pyqtgraph", "emtk"])
def plot(request: Any, qapp: Any) -> Iterator[cp.Plot]:
    """Exercise both real renderers while restoring the process backend."""
    previous = backends._active
    previous_env = os.environ.get("CHISURF_PLOT_BACKEND")
    backends.set_backend(request.param)
    panel = cp.Plot()
    try:
        yield panel
    finally:
        panel.close()
        backends._active = previous
        if previous_env is None:
            os.environ.pop("CHISURF_PLOT_BACKEND", None)
        else:
            os.environ["CHISURF_PLOT_BACKEND"] = previous_env


def _is_pg() -> bool:
    return backends.get_backend().name == "pyqtgraph"


def test_axis_style_recolours_the_axes(plot: cp.Plot) -> None:
    assert plot.set_axis_style(line="#b0b0b0", text="#d0d0d0") is plot
    canvas: Any = plot._canvas
    if _is_pg():
        axis = canvas._pi.getAxis("bottom")
        assert axis.textPen().color().name() == "#d0d0d0"
        assert axis.pen().color().name() == "#b0b0b0"
    else:
        assert canvas._tick_text == canvas._label_text == (0xD0, 0xD0, 0xD0)
        assert canvas._axis_line == (0xB0, 0xB0, 0xB0)


def test_tick_labels_replace_numbers_and_can_be_restored(plot: cp.Plot) -> None:
    plot.bars([0, 1], [3.0, 5.0], width=0.6)
    plot.set_tick_labels("bottom", [(0, "D1"), (1, "D2")])
    canvas: Any = plot._canvas
    if _is_pg():
        assert canvas._pi.getAxis("bottom")._tickLevels is not None
    else:
        assert canvas._custom_ticks["bottom"] == [(0.0, "D1"), (1.0, "D2")]
    plot.set_tick_labels("bottom", None)
    if not _is_pg():
        assert "bottom" not in canvas._custom_ticks


def test_legend_style_is_accepted(plot: cp.Plot) -> None:
    plot.line(np.arange(3), np.arange(3), name="a")
    plot.legend()
    assert plot.set_legend_style(text="#d0d0d0") is plot
