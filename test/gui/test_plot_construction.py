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
import chisurf.core.models.description as lifetime_model  # noqa: E402
from chisurf.core.fitting.fit import Fit  # noqa: E402


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
    return Fit(model_class=lifetime_model.tcspc_lifetime, data=data, xmin=0, xmax=n - 1)


def test_autorange_compat_is_applied_on_import():
    """The shim must not depend on get_win() having run: loading the plot backend applies it."""
    import pyqtgraph as pg

    import chisurf.gui.chiplot.backends.pyqtgraph_backend  # noqa: F401

    assert hasattr(pg.PlotWidget, "autoRangeEnabled"), (
        "PlotWidget.autoRangeEnabled missing -- plots built outside GUI startup "
        "will hit a swallowed AttributeError and take a degraded path"
    )


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


class _PlotModel:
    """Minimal model exposing the series source a PlotSection reads."""

    def series(self):
        return [{"x": [0, 1, 2], "y": [1, 2, 3], "name": "s"}]


def test_inline_plot_context_menu_on_by_default(app):
    """A PlotSection keeps the right-click menu unless it opts out.

    Asked through chiplot's own ``menu_enabled()`` rather than the renderer's
    spelling: the point of the seam is that a plot answers this without the
    caller knowing which library draws it.
    """
    from chisurf.core.dataspec import PlotSection
    from chisurf.gui.autoform.sections.builtin import PlotWidget

    widget = PlotWidget(_PlotModel(), PlotSection(source="series"))
    assert widget.plot.menu_enabled() is True


def test_inline_plot_context_menu_can_be_disabled(app):
    """``context_menu: false`` suppresses the per-axis/log/export menu."""
    from chisurf.core.dataspec import PlotSection
    from chisurf.gui.autoform.sections.builtin import PlotWidget

    widget = PlotWidget(_PlotModel(), PlotSection(source="series", context_menu=False))
    assert widget.plot.menu_enabled() is False
