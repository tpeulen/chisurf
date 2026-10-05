"""Canonical Fit and FitGroup presentation retains the scientific owners."""

import numpy as np
import pytest
from qtpy import QtWidgets

from chisurf.core.data import DataCurveGroup
from chisurf.core.fitting.fit import Fit, FitGroup
from chisurf.core.models.parse.parse import ParseModel
from chisurf.core.project.session import capture_session
from chisurf.core.project.ui_state import get_ui_state, set_ui_state
from chisurf.gui.widgets.fitting import FitSubWindow, FittingControllerWidget
from test.project.test_all_model_catalogue_roundtrip import _data


@pytest.fixture
def presentation(qtbot, monkeypatch, request):
    """Build real equation fits and the production controller and plot window."""
    import chisurf as cs
    from chisurf.gui.widgets.fitting import fitting_client

    monkeypatch.setattr(fitting_client, "_FITTING_CLIENT", None)
    monkeypatch.setattr(cs, "cs", None)
    data = _data({"experiment": "parse"}, ParseModel)
    if request.param == "group":
        other = _data({"experiment": "parse"}, ParseModel)
        fit = FitGroup(data=DataCurveGroup([data, other]), model_class=ParseModel)
        members = fit.grouped_fits
    else:
        fit = Fit(data=data, model_class=ParseModel)
        members = [fit]
    for index, member in enumerate(members):
        member.model.func = "a*x+b"
        member.fit_range = (3 + index, 40 + index)
        member.model.parameters_all_dict["a"].value = 2 + index
        member.model.update()
    if isinstance(fit, FitGroup):
        members[1].model.parameters_all_dict["b"].link = members[0].model.parameters_all_dict["b"]
        fit.selected_fit = 1
    before = capture_session([member.data for member in members], [fit])
    controller = FittingControllerWidget(fit=fit)
    qtbot.addWidget(controller)
    host = QtWidgets.QWidget()
    qtbot.addWidget(host)
    controls = QtWidgets.QVBoxLayout(host)
    window = FitSubWindow(fit=fit, control_layout=controls, fit_widget=controller)
    qtbot.addWidget(window)
    yield fit, members, controller, window, before


@pytest.mark.parametrize("presentation", ["single", "group"], indirect=True)
def test_controller_and_window_retain_canonical_science(presentation, qtbot):
    """Opening and plotting preserves exact graph, bounds, flags and predictions."""
    fit, members, controller, window, before = presentation
    identities = [(member, member.model, tuple(member.model.parameters_all)) for member in members]
    assert controller.fit is fit and window.fit is fit
    assert controller.selected_fit == (1 if isinstance(fit, FitGroup) else 0)
    assert (controller.xmin, controller.xmax) == fit.fit_range
    for index in range(len(window._plot_specs)):
        plot = window.ensure_plot_created(index)
        assert not isinstance(plot, QtWidgets.QLabel)
    qtbot.wait(1)
    after = capture_session([member.data for member in members], [fit])
    assert after.datasets == before.datasets
    assert after.fits == before.fits
    for member, model, parameters in identities:
        assert member.model is model
        assert all(
            current is previous for current, previous in zip(model.parameters_all, parameters)
        )


@pytest.mark.parametrize("presentation", ["single", "group"], indirect=True)
def test_selection_range_and_window_state_roundtrip(presentation, qtbot):
    """Selection, local range edits and plot capture address the original fit."""
    from types import SimpleNamespace

    fit, members, controller, window, _before = presentation
    controller.selected_fit = 0
    controller.onDatasetChanged()
    assert fit.model is members[0].model
    assert (controller.xmin, controller.xmax) == members[0].fit_range
    controller.onFitRangeChanged(None, xmin=7, xmax=35)
    assert all(member.fit_range == (7, 35) for member in members)
    if not isinstance(fit, FitGroup):
        assert "selected_fit" not in vars(fit)
    window.ensure_plot_created(0)
    qtbot.wait(1)
    main = SimpleNamespace(mdiarea=SimpleNamespace(subWindowList=lambda: [window]))
    state = get_ui_state(main)
    assert fit.unique_identifier in state["fit_windows"]
    window.setGeometry(11, 12, 400, 350)
    assert set_ui_state(main, state)
    from test.project.scientific_catalogue_probe import _differences

    recaptured = get_ui_state(main)
    assert recaptured == state, list(_differences(state, recaptured, "ui"))
    np.testing.assert_array_equal(fit.model.y, 2 * fit.model.x + 1)


@pytest.mark.parametrize("presentation", ["single"], indirect=True)
def test_declared_plot_failure_is_not_a_successful_placeholder(presentation):
    """A failed declared plot must abort presentation rather than fake success."""
    _fit, _members, _controller, window, _before = presentation

    def broken_plot(*args, **kwargs):
        """Expose a real construction error at the production plot boundary."""
        raise RuntimeError("declared plot failed")

    index = len(window._plot_specs)
    window._plot_specs.append((broken_plot, {}))
    window._plots_all.append(None)
    with pytest.raises(RuntimeError, match="declared plot failed"):
        window.ensure_plot_created(index)
    assert window._plots_all[index] is None


@pytest.mark.parametrize("presentation", ["single"], indirect=True)
def test_controller_state_capture_failure_is_explicit(presentation, monkeypatch):
    """An unreadable visible controller cannot disappear from the snapshot."""
    _fit, _members, _controller, window, _before = presentation
    plot = window.ensure_plot_created(0)

    def reject():
        """Simulate a failing real controller capture hook."""
        raise RuntimeError("capture controller failed")

    monkeypatch.setattr(plot.plot_controller, "get_state", reject)
    with pytest.raises(RuntimeError, match="capture controller failed"):
        window.get_project_plot_state()


@pytest.mark.parametrize("presentation", ["single"], indirect=True)
def test_controller_state_apply_failure_is_explicit(presentation, monkeypatch):
    """A rejected saved controller state cannot report successful publication."""
    _fit, _members, _controller, window, _before = presentation
    plot = window.ensure_plot_created(0)
    state = window.get_project_plot_state()

    def reject(state):
        """Simulate a failing real controller publication hook."""
        raise RuntimeError("apply controller failed")

    monkeypatch.setattr(plot.plot_controller, "set_state", reject)
    with pytest.raises(RuntimeError, match="apply controller failed"):
        window.set_project_plot_state(state)


@pytest.mark.parametrize("grouped", [False, True], ids=["single", "group"])
def test_generated_editor_edits_authoritative_parameter_and_saves_exactly(
    grouped, qtbot, monkeypatch
):
    """A table edit changes the live prediction and preserves canonical science."""
    from qtpy import QtCore

    import chisurf as cs
    from chisurf.core.models.pda2c.simple import Pda2cSimpleModel
    from chisurf.core.project.session import restore_session
    from chisurf.gui.autoform.sections.parameter_table import (
        COL_VALUE,
        PairedParameterTableModel,
        ParameterGroupTableModel,
    )
    from chisurf.gui.widgets.fitting import fitting_client
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    monkeypatch.setattr(fitting_client, "_FITTING_CLIENT", None)
    data = _data({"experiment": "pda"}, Pda2cSimpleModel)
    if grouped:
        other = _data({"experiment": "pda"}, Pda2cSimpleModel)
        fit = FitGroup(data=DataCurveGroup([data, other]), model_class=Pda2cSimpleModel)
        fit.selected_fit = 1
        members = fit.grouped_fits
    else:
        fit = Fit(data=data, model_class=Pda2cSimpleModel)
        members = [fit]
    monkeypatch.setattr(cs, "fits", [fit])
    monkeypatch.setattr(cs, "imported_datasets", [member.data for member in members])
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    model = fit.model
    parameter = model.parameters_all_dict["bg0"]
    model.update()
    before = model.y.copy()
    editor = build_model_editor(model)
    qtbot.addWidget(editor)
    editor.show()
    cells = []
    for view in editor.findChildren(QtWidgets.QTableView):
        table = view.model()
        for row in range(table.rowCount()):
            if isinstance(table, ParameterGroupTableModel) and table.param_at(row) is parameter:
                cells.append((table, table.index(row, COL_VALUE)))
            elif isinstance(table, PairedParameterTableModel):
                for column in range(table.columnCount()):
                    pair = table.param_at(row, column)
                    if pair is not None and pair[0] is parameter and pair[1] == "value":
                        cells.append((table, table.index(row, column)))
    assert len(cells) == 1
    table, cell = cells[0]
    assert table.setData(cell, 0.001, QtCore.Qt.EditRole)
    assert model.parameters_all_dict["bg0"] is parameter
    assert parameter.value == 0.001
    qtbot.waitUntil(lambda: not np.array_equal(model.y, before))
    assert not np.array_equal(model.y, before)
    snapshot = capture_session([member.data for member in members], [fit])
    restored = restore_session(snapshot)
    recaptured = capture_session(restored.datasets, restored.fits)
    assert recaptured.datasets == snapshot.datasets
    assert recaptured.fits == snapshot.fits
    np.testing.assert_array_equal(restored.fits[0].model.y, model.y)


@pytest.mark.parametrize("presentation", ["single", "group"], indirect=True)
def test_active_main_binding_shows_the_actual_selected_editor(presentation, qtbot):
    """MDI activation must reveal the single editor as well as selected groups."""
    from chisurf.gui.main import Main
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit, members, _controller, _window, _before = presentation
    editors = [build_model_editor(member.model) for member in members]
    for editor in editors:
        qtbot.addWidget(editor)
        editor.hide()
    Main._show_only_selected_member_editor(None, fit)
    selected = fit.selected_fit_index if isinstance(fit, FitGroup) else 0
    assert [editor.isHidden() for editor in editors] == [i != selected for i in range(len(editors))]


@pytest.mark.parametrize("presentation", ["single"], indirect=True)
def test_unknown_saved_plot_is_rejected_before_window_mutation(presentation):
    """An invalid plot target cannot succeed merely by applying its geometry."""
    import copy

    _fit, _members, _controller, window, _before = presentation
    window.ensure_plot_created(0)
    original = window.get_project_plot_state()
    invalid = copy.deepcopy(original)
    invalid["plots"][0]["index"] = len(window._plot_specs)
    invalid["geometry"] = [10, 20, 300, 350]
    with pytest.raises(ValueError, match="plot"):
        window.set_project_plot_state(invalid)
    assert window.get_project_plot_state() == original
