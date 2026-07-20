"""Headless GUI tests for the AutoForm parameter table's parameter actions.

The table must offer the same per-parameter actions as the row widgets it
replaces: a right-click link menu and a detail popup opened by clicking the
parameter name.  Both go through ``FittingParameterProxyController``.
"""

import numpy as np
import pytest
from qtpy import QtWidgets

import chisurf as cs
import chisurf.core.data
import chisurf.core.fitting.fit
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.gui.autoform.sections.parameter_table import (
    COL_NAME,
    COL_VALUE,
    ParameterGroupTableWidget,
)
from chisurf.gui.widgets.fitting.parameter_widgets import (
    FittingParameterDetailPopup,
    FittingParameterProxyController,
)


class _SimpleModel(ModelCurve):
    name = "SimpleModel"

    def __init__(self, fit):
        super().__init__(fit)
        self.p1 = FittingParameter(name="p1", value=2.0)
        self.p2 = FittingParameter(name="p2", value=3.0)
        self.find_parameters()

    def update_model(self, **kwargs):
        self.y = np.ones_like(self.x) * self.p1.value


@pytest.fixture
def params(qapp):
    data = cs.core.data.DataCurve(x=np.arange(10.0), y=np.arange(10.0))
    fit = cs.core.fitting.fit.Fit(model_class=_SimpleModel, data=data)
    cs.fits = [fit]
    return [fit.model.p1, fit.model.p2]


@pytest.fixture
def table(qtbot, params):
    w = ParameterGroupTableWidget(params)
    qtbot.addWidget(w)
    return w


def test_context_menu_offers_link_and_unlink(table):
    menu = QtWidgets.QMenu()
    table._add_link_actions(menu, 0)
    texts = [a.text() for a in menu.actions()]
    assert any("Link p1 to" in t for t in texts)
    assert any("Unlink" in t for t in texts)


def test_unlink_action_disabled_when_not_linked(table):
    menu = QtWidgets.QMenu()
    table._add_link_actions(menu, 0)
    unlink = next(a for a in menu.actions() if "Unlink" in a.text())
    assert not unlink.isEnabled()


def test_name_click_opens_detail_popup(table, qtbot):
    table._on_cell_clicked(table.table_model.index(0, COL_NAME))
    popup = table._detail_popup
    assert isinstance(popup, FittingParameterDetailPopup)
    assert popup.controller.fitting_parameter is table.parameters[0]
    qtbot.addWidget(popup)
    popup.hide()


def test_click_outside_name_column_opens_nothing(table):
    table._on_cell_clicked(table.table_model.index(0, COL_VALUE))
    assert table._detail_popup is None


def test_popup_edit_refreshes_the_table(table, qtbot):
    """An edit in the popup must repaint the row and fire the table's on_change.

    No fitting client is installed here, so the edit itself is a no-op; what is
    asserted is the refresh path the proxy controller wires up.
    """
    rows = []
    calls = []
    table._on_change = lambda: calls.append(1)
    table.table_model.dataChanged.connect(lambda tl, br: rows.append(tl.row()))
    table._on_cell_clicked(table.table_model.index(0, COL_NAME))
    popup = table._detail_popup
    qtbot.addWidget(popup)

    popup.cb_fixed.setChecked(True)

    assert calls, "the table's on_change callback was not invoked"
    assert rows, "the table did not repaint after the popup edit"
    popup.hide()


def test_proxy_controller_reports_parameter_context(params, qapp):
    """The proxy exposes the same context dict the row widget's actions use."""
    ctrl = FittingParameterProxyController(params[0])
    ctx = ctrl._parameter_context(params[0])
    assert set(ctx) == {
        "fit_group",
        "local_fit",
        "fit_uid",
        "local_fit_uid",
        "parameter_uid",
    }
    assert ctx["parameter_uid"] == str(params[0].unique_identifier)
