"""Headless GUI tests for the AutoForm parameter table's parameter actions.

The table must offer the same per-parameter actions as the row widgets it
replaces: a right-click link menu and a detail popup opened by clicking the
parameter name.  Both go through ``FittingParameterProxyController``.
"""

import numpy as np
import pytest
from qtpy import QtCore, QtWidgets

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


def test_popup_edit_repaints_the_row_without_dispatching(table, qtbot):
    """A popup edit repaints the row but must not request a fit update.

    ``finalize()`` is called by the model *during* a recompute, so dispatching
    ``on_change`` from the repaint path would feed the recompute back into
    itself.  No fitting client is installed, so the edit itself is a no-op —
    what is asserted is the refresh wiring.
    """
    rows = []
    calls = []
    table._on_change = lambda: calls.append(1)
    table.table_model.dataChanged.connect(lambda tl, br: rows.append(tl.row()))
    table._on_cell_clicked(table.table_model.index(0, COL_NAME))
    popup = table._detail_popup
    qtbot.addWidget(popup)

    popup.cb_fixed.setChecked(True)

    assert rows == [0], "the popup edit did not repaint its own row"
    assert not calls, "a display refresh must not dispatch a fit update"
    popup.hide()


def test_table_claims_each_parameter_controller(table):
    """Table-rendered parameters get a controller, like row widgets do.

    Without it ``FittingParameter.update()`` is a silent no-op and
    ``FittingParameterGroup.finalize()`` logs "has no controller to finalize"
    for every parameter in the group.
    """
    for param in table.parameters:
        assert getattr(param, "controller", None) is not None
        assert param.controller.fitting_parameter is param


def test_group_finalize_is_quiet_for_table_rendered_parameters(params, qtbot, caplog):
    """The real symptom: ``model.finalize()`` warned once per table parameter."""
    import logging

    model = cs.fits[0].model
    with caplog.at_level(logging.WARNING):
        model.finalize()
    assert any(
        "has no controller to finalize" in r.message for r in caplog.records
    ), "expected the warning before a table claims the parameters"

    caplog.clear()
    w = ParameterGroupTableWidget([model.p1, model.p2])
    qtbot.addWidget(w)
    with caplog.at_level(logging.WARNING):
        model.finalize()
    noisy = [r.message for r in caplog.records if "has no controller" in r.message]
    assert not any("'p1'" in m or "'p2'" in m for m in noisy), noisy


def test_parameter_update_repaints_its_row(table):
    """``parameter.update()`` reaches the table through the controller."""
    rows = []
    table.table_model.dataChanged.connect(lambda tl, br: rows.append(tl.row()))
    table.parameters[1].update()
    assert rows == [1]


def test_parameter_update_does_not_request_a_fit_update(table):
    """The recompute → finalize → recompute feedback loop stays broken."""
    calls = []
    table._on_change = lambda: calls.append(1)
    table.parameters[0].update()
    assert not calls


def test_sync_does_not_dispatch_on_change(table):
    """``sync``/``refresh`` runs after a fit — it must not ask for another."""
    calls = []
    table._on_change = lambda: calls.append(1)
    table.sync()
    assert not calls


def test_cell_edit_still_dispatches_on_change(table):
    """A real user edit must still trigger the fit update."""
    calls = []
    table._on_change = lambda: calls.append(1)
    table.table_model.setData(
        table.table_model.index(0, COL_VALUE), "4.25", QtCore.Qt.EditRole
    )
    assert calls, "a cell edit should dispatch on_change"


class _RecordingClient:
    """Stand-in fitting client that records the RPCs a widget sends."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(**kwargs):
            self.calls.append((name, kwargs))
            return {"ok": True}

        return call


def test_cell_edit_reaches_the_backend_and_the_trace(table, params, monkeypatch):
    """Regression: table edits were local-only — invisible to backend and history.

    The row widgets push every edit to the fitting client and record it in the
    provenance trace; the table wrote the attribute and stopped there, so a
    parameter changed in a model editor never reached a remote backend and left
    no history entry.  Both now go through the parameter's controller.
    """
    from chisurf.gui.widgets.fitting import parameter_widgets

    client = _RecordingClient()
    traced = []
    monkeypatch.setattr(parameter_widgets, "get_fitting_client", lambda: client)
    monkeypatch.setattr(
        parameter_widgets.ParameterActionsMixin,
        "_trace_operation",
        lambda self, action_type, summary, payload=None: traced.append(
            (action_type, payload or {})
        ),
    )

    table.table_model.setData(
        table.table_model.index(0, COL_VALUE), "4.25", QtCore.Qt.EditRole
    )

    assert params[0].value == 4.25, "the local echo must still happen"
    assert ("set_parameter_value", {
        "parameter_name": "p1", "value": 4.25, "fit_uid": client.calls[0][1]["fit_uid"],
    }) in client.calls
    actions = [a for a, _ in traced]
    assert "parameter_value" in actions
    payload = dict(traced[actions.index("parameter_value")][1])
    assert payload["new_value"] == 4.25 and payload["old_value"] == 2.0


def test_checkbox_edit_reaches_the_backend_and_the_trace(table, params, monkeypatch):
    """The fixed flag takes the same route as the value."""
    from chisurf.gui.widgets.fitting import parameter_widgets
    from chisurf.gui.autoform.sections.parameter_table import COL_FIXED

    client = _RecordingClient()
    traced = []
    monkeypatch.setattr(parameter_widgets, "get_fitting_client", lambda: client)
    monkeypatch.setattr(
        parameter_widgets.ParameterActionsMixin,
        "_trace_operation",
        lambda self, action_type, summary, payload=None: traced.append(action_type),
    )

    table.table_model.setData(
        table.table_model.index(0, COL_FIXED), "True", QtCore.Qt.EditRole
    )

    assert params[0].fixed is True
    assert [name for name, _ in client.calls] == ["set_parameter_fixed"]
    assert traced == ["parameter_fixed"]


def test_popup_edit_echoes_locally_without_a_backend(table, qtbot, params):
    """Regression: the detail popup only RPC'd, so an edit was lost without a server.

    ChiSurf starts (with a warning) when its RPC server is unreachable; in that
    state every popup edit vanished and the popup snapped back on refresh.
    """
    table._on_cell_clicked(table.table_model.index(0, COL_NAME))
    popup = table._detail_popup
    qtbot.addWidget(popup)

    popup.sb_value.setValue(7.5)
    popup.sb_value.editingFinished.emit()

    assert params[0].value == 7.5
    popup.hide()


def test_controllers_released_when_the_table_dies(params, qapp):
    """A dead table must not leave a deleted proxy on the parameters."""
    w = ParameterGroupTableWidget(params)
    assert params[0].controller is not None
    w.deleteLater()
    # ``processEvents`` does not run DeferredDelete events — post them explicitly
    # so the destroyed signal fires deterministically here.
    qapp.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    assert getattr(params[0], "controller", None) is None


def test_proxy_satisfies_the_popup_controller_contract(params, qapp):
    """Every ``self.controller.X`` the popup uses must exist on the proxy.

    The popup is written against ``FittingParameterWidget``; the proxy stands in
    for it.  Parsing the popup keeps the two in sync as it grows — a new
    controller call that only the row widget has fails here instead of at
    runtime (as ``_trigger_model_update`` once did).
    """
    import ast
    import inspect

    from chisurf.gui.widgets.fitting import parameter_widgets as pw

    tree = ast.parse(inspect.getsource(pw))
    popup = next(
        c for c in tree.body
        if isinstance(c, ast.ClassDef) and c.name == "FittingParameterDetailPopup"
    )
    used = {
        n.attr for n in ast.walk(popup)
        if isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Attribute)
        and n.value.attr == "controller"
    }
    assert used, "no controller attributes found — the parse is wrong"
    ctrl = FittingParameterProxyController(params[0])
    missing = sorted(a for a in used if not hasattr(ctrl, a))
    assert not missing, f"proxy controller is missing: {missing}"


def test_popup_value_edit_does_not_crash_on_the_proxy(table, qtbot):
    """Editing the value routes through ``_trigger_model_update`` on the proxy."""
    table._on_cell_clicked(table.table_model.index(0, COL_NAME))
    popup = table._detail_popup
    qtbot.addWidget(popup)

    popup.sb_value.setValue(7.5)
    popup.sb_value.editingFinished.emit()

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
