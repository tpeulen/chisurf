"""The what-if plot must not answer from a posterior that no longer exists.

``ConditionalScanPlot.update`` cleared its parameter combo *outside* the
``blockSignals`` pair, so the ``clear()`` emitted ``currentIndexChanged`` and
re-entered ``_rebuild`` (the page is drawn by emtk now; the selection is page
state, and the same rule holds for it) while the previous update's engine and parameter list
were still in place. Fixing parameters until fewer than two were free therefore
left the earlier sweep on screen -- title, curves and a table quoting means and
correlations for parameters that were no longer free -- with the "needs a
converged fit with at least two free parameters" message overwritten in the same
call.
"""

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtWidgets  # noqa: E402

import chisurf.core.data  # noqa: E402
import chisurf.core.fitting.fit  # noqa: E402
import chisurf.core.models.parse  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def quadratic_fit():
    """Return a converged three-parameter fit with a correlated posterior."""
    rng = np.random.default_rng(0)
    x = np.linspace(1.0, 2.0, 96)
    y = 1.0 + 2.0 * x + 0.5 * x**2 + rng.normal(0.0, 0.02, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.full_like(y, 0.02))
    fit = chisurf.core.fitting.fit.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = "c+a*x+b*x**2"
    fit.model.find_parameters()
    fit.run()
    return fit


def _fix(fit, *names) -> None:
    """Fix the named model parameters, leaving the rest free."""
    for parameter in fit.model.parameters_all:
        if parameter.name in names:
            parameter.fixed = True


def test_what_if_plot_answers_the_current_fit(app, quadratic_fit):
    """Three free parameters: every one of them is offered and swept."""
    from chisurf.gui.plots.conditional_scan import ConditionalScanPlot

    widget = ConditionalScanPlot(quadratic_fit)
    widget.update()

    assert len(widget.parameters) == 3
    assert widget._scan is not None
    assert len(widget._full_names) == 3


def test_what_if_plot_drops_the_stale_scan_when_it_degrades(app, quadratic_fit):
    """One free parameter left: no engine, no sweep, and the message survives.

    Regression: ``_scan`` stayed populated and the readout held the previous
    table, because clearing the combo re-ran the sweep on the dead engine.
    """
    from chisurf.gui.plots.conditional_scan import ConditionalScanPlot

    widget = ConditionalScanPlot(quadratic_fit)
    widget.update()
    assert widget._scan is not None, "precondition: the plot starts usable"

    _fix(quadratic_fit, "a", "b")
    widget.update()

    from chisurf.gui.plots import emtk_notes as N

    assert widget.parameters == []
    assert widget._scan is None
    assert widget._engine is None
    assert widget._full_names == []
    assert widget.held_text == ""
    assert "at least two free parameters" in N.as_text(widget.readout)
    # The stale table is what gave the dead posterior away: no parameter names,
    # no correlations, no "narrower" column may be left in the readout.
    assert not any(isinstance(note, N.Table) for note in widget.readout)


def test_what_if_plot_ignores_the_combo_once_it_has_degraded(app, quadratic_fit):
    """A selection change after degrading must not redraw from the old engine."""
    from chisurf.gui.plots.conditional_scan import ConditionalScanPlot

    widget = ConditionalScanPlot(quadratic_fit)
    widget.update()
    _fix(quadratic_fit, "a", "b")
    widget.update()

    widget.set_parameter(0)  # as a stale selection would

    assert widget._scan is None, "no sweep may come out of a dropped engine"


def test_what_if_readout_reads_the_held_value(app, quadratic_fit):
    """Moving the held value moves the 'would be' column, not the 'free' one."""
    from chisurf.gui.plots import emtk_notes as N
    from chisurf.gui.plots.conditional_scan import ConditionalScanPlot

    widget = ConditionalScanPlot(quadratic_fit)
    widget.update()
    table = [n for n in widget.readout if isinstance(n, N.Table)][0]
    at_optimum = [row[1:3] for row in table.rows]
    widget.set_held(1.5)
    table = [n for n in widget.readout if isinstance(n, N.Table)][0]
    assert [row[2] for row in table.rows] == [free for _, free in at_optimum]
    assert [row[1] for row in table.rows] != [would for would, _ in at_optimum]
    assert widget.held_text.startswith(widget.parameters[widget.parameter] + " = ")
