"""The shared Main probe must recognize real rich AutoForm scientific controls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qtpy import QtCore, QtWidgets

from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget
from chisurf.gui.widgets.models.model_editor import build_model_editor
from test.gui.scientific_document_gui_probe import _edit_control, _editor_bindings
from test.project.test_fcs_snapshot_science_edits import (
    _measured_fcs_fit,
    configure_fcs_science,
    fcs_scientific_observables,
)


@pytest.fixture(scope="session")
def qapp():
    """Keep the actual application alive for the entire native test session."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def rich_main_surface(qapp):
    """Use real MDI/dock ownership and the existing measured FCS model editor."""
    fit = _measured_fcs_fit("FCSKineticsModel")
    configure_fcs_science(fit.model)
    fit.model.update()
    main = QtWidgets.QMainWindow()
    main.mdiarea = QtWidgets.QMdiArea(main)
    main.setCentralWidget(main.mdiarea)
    window = main.mdiarea.addSubWindow(QtWidgets.QWidget())
    window.fit = fit
    editor = build_model_editor(fit.model)
    main.dockWidgetAnalysis = QtWidgets.QDockWidget("Scientific controls", main)
    main.dockWidgetAnalysis.setWidget(editor)
    main.addDockWidget(QtCore.Qt.RightDockWidgetArea, main.dockWidgetAnalysis)
    main.resize(1100, 800)
    main.show()
    qapp.processEvents()
    grid = next(
        g for g in editor.findChildren(RateMatrixWidget) if g._attr == "saturation.dark.rate_values"
    )
    yield main, fit, editor, grid
    main.hide()
    editor.hide()


def test_probe_edits_the_rich_control_for_the_exact_live_parameter(qapp, rich_main_surface):
    """A flat-table-only test is not evidence that a rich scientific input is missing."""
    main, fit, _, grid = rich_main_surface
    parameter = grid._binding.parameter(2, 0)
    uid = parameter.unique_identifier
    initial = fcs_scientific_observables(fit.model)
    result = _edit_control(main, qapp, uid, 750.0)
    assert result["parameter_uid"] == uid
    assert result["name"] == parameter.name
    assert result["control"] == "QDoubleSpinBox"
    assert result["actual_value"] == parameter.value == 750.0
    assert result["row"] == 2 and result["column"] == 0
    assert parameter is grid._binding.parameter(2, 0)
    assert parameter.unique_identifier == uid
    changed = fcs_scientific_observables(fit.model)
    assert changed["prediction"] != initial["prediction"]
    assert changed["relaxation_modes"] != initial["relaxation_modes"]


def test_inventory_includes_rich_parameters_with_exact_live_ownership(rich_main_surface):
    """Rich sections undergo the same scientific UID/owner checks as ordinary tables."""
    _, fit, editor, grid = rich_main_surface
    live = {p.unique_identifier: p for p in fit.model.parameters_all}
    parameter = grid._binding.parameter(2, 0)
    entries = _editor_bindings(editor, live)
    cells = [cell for entry in entries for cell in entry["cells"]]
    rate_cell = next(
        (cell for cell in cells if cell["parameter_uid"] == parameter.unique_identifier), None
    )
    assert rate_cell is not None, "real scientific rate-matrix controls were omitted from inventory"
    assert rate_cell["name"] == parameter.name
    assert rate_cell["row"] == 2 and rate_cell["column"] == 0
    assert rate_cell["editable"]
    assert rate_cell["scientific_value"] == parameter.value
    assert rate_cell["edit_role"] == grid._spins[(2, 0)].value()


def test_inventory_rejects_foreign_rich_owner_with_identical_uid_and_value(
    rich_main_surface,
    monkeypatch,
):
    """Matching scientific metadata cannot substitute for exact live ownership."""
    _, fit, editor, grid = rich_main_surface
    live = {p.unique_identifier: p for p in fit.model.parameters_all}
    bound_parameter = grid._binding.parameter
    parameter = bound_parameter(2, 0)
    foreign = SimpleNamespace(
        unique_identifier=parameter.unique_identifier,
        name=parameter.name,
        value=parameter.value,
        is_output=parameter.is_output,
        link=parameter.link,
    )
    before = grid._binding.values()
    monkeypatch.setattr(
        grid._binding,
        "parameter",
        lambda row, column: foreign if (row, column) == (2, 0) else bound_parameter(row, column),
    )
    with pytest.raises(AssertionError, match="foreign or stale scientific parameter"):
        _editor_bindings(editor, live)
    assert grid._binding.values() == before
    assert live[parameter.unique_identifier] is parameter
