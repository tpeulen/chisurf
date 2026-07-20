"""Plots must be constructible outside the full GUI startup path.

Two defects found while building a headless harness that renders a fit's real
plot widgets:

* ``ResidualPlot`` iterated its ``fit`` argument, so a plain :class:`Fit` (as
  opposed to a :class:`FitGroup`) raised ``TypeError: 'Fit' object is not
  iterable`` and the plot could not be built at all.
* pyqtgraph >= 0.14 moved ``autoRangeEnabled`` from ``PlotWidget`` to
  ``ViewBox``. chisurf ships a compat shim, but it was only applied from
  ``get_win()`` -- so anything building a plot without full GUI startup hit a
  swallowed ``AttributeError`` and took a degraded path.
"""
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("pyqtgraph")
from qtpy import QtWidgets  # noqa: E402

import chisurf.core.data  # noqa: E402
from chisurf.core.fitting.fit import Fit  # noqa: E402
import chisurf.core.models.tcspc.lifetime as lifetime_model  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def single_fit():
    """A plain Fit -- deliberately NOT a FitGroup."""
    n = 256
    x = np.arange(n) * 0.032
    y = 1000 * np.exp(-x / 4.0) + 10
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0)))
    return Fit(model_class=lifetime_model.LifetimeModel, data=data, xmin=0, xmax=n - 1)


def test_autorange_compat_is_applied_on_import():
    """The shim must not depend on get_win() having run."""
    import pyqtgraph as pg
    assert hasattr(pg.PlotWidget, "autoRangeEnabled"), (
        "PlotWidget.autoRangeEnabled missing -- plots built outside GUI startup "
        "will hit a swallowed AttributeError and take a degraded path")


def test_residual_plot_accepts_a_plain_fit(app, single_fit):
    """Regression: this raised TypeError: 'Fit' object is not iterable."""
    from chisurf.gui.plots.wr_plot import ResidualPlot
    p = ResidualPlot(single_fit)
    assert len(p.curves) == 1, "a lone Fit is a group of one"
    p.update()


def test_residual_plot_member_fits_helper():
    from chisurf.gui.plots.wr_plot import _member_fits

    class _Group(list):
        pass

    assert _member_fits(_Group(["a", "b"])) == ["a", "b"]
    sentinel = object()
    assert _member_fits(sentinel) == [sentinel]
