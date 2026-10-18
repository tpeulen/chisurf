"""Plots must be constructible outside the full GUI startup path.

A defect found while building a headless harness that renders a fit's real
plot widgets:

* ``ResidualPlot`` iterated its ``fit`` argument, so a plain :class:`Fit` (as
  opposed to a :class:`FitGroup`) raised ``TypeError: 'Fit' object is not
  iterable`` and the plot could not be built at all.
"""

import numpy as np
import pytest

import chisurf.core.data
import chisurf.core.models.description as lifetime_model
from chisurf.core.fitting.fit import Fit


@pytest.fixture
def single_fit():
    """A plain Fit -- deliberately NOT a FitGroup."""
    n = 256
    x = np.arange(n) * 0.032
    y = 1000 * np.exp(-x / 4.0) + 10
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.sqrt(np.maximum(y, 1.0)))
    return Fit(model_class=lifetime_model.tcspc_lifetime, data=data, xmin=0, xmax=n - 1)


def test_residual_plot_accepts_a_plain_fit(single_fit):
    """Regression: this raised TypeError: 'Fit' object is not iterable."""
    from chisurf.emtk.fit_pages.pages.wr_plot import ResidualPlot

    p = ResidualPlot(single_fit)
    assert len(p.curves) == 1, "a lone Fit is a group of one"
    p.update()


def test_residual_plot_member_fits_helper():
    from chisurf.emtk.fit_pages.pages.wr_plot import _member_fits

    class _Group(list):
        pass

    assert _member_fits(_Group(["a", "b"])) == ["a", "b"]
    sentinel = object()
    assert _member_fits(sentinel) == [sentinel]
