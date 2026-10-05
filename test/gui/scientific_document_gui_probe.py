"""One actual Main/native-canvas lifetime over a canonical scientific archive."""

from __future__ import annotations

import importlib.abc
import json
import math
import os
import sys
import traceback
from pathlib import Path

import numpy as np


class _BlockMMFDB(importlib.abc.MetaPathFinder):
    """Make optional database imports impossible before any ordinary GUI import."""

    def __init__(self, report):
        """Record swallowed import failures that can silently remove GUI plots."""
        self.report = report

    def find_spec(self, fullname, path=None, target=None):
        """Reject the entire optional database package, including submodules."""
        if fullname == "mmfdb" or fullname.startswith("mmfdb."):
            self.report.setdefault("blocked_mmfdb_imports", []).append(
                {"module": fullname, "stack": traceback.format_stack()}
            )
            raise AssertionError(f"optional MMFDB import in actual Main: {fullname}")


def _parameters(project):
    """Index persisted scientific parameters by their exact portable identities."""
    return {
        parameter["uid"]: parameter
        for record in project.fits
        for model in (
            [member["model"] for member in record["members"]]
            + ([record["aggregate_model"]] if record.get("aggregate_model") else [])
        )
        for parameter in model["parameters"]
    }


def _members(fits):
    """Keep canonical scientific member ordering across presentation wrappers."""
    return [member for fit in fits for member in getattr(fit, "grouped_fits", [fit])]


def package_gui(directory):
    """Wrap existing real fits without reconstructing data, models or parameters.

    Canonical public single-Fit restoration is exercised separately and remains
    a failure when unsupported. This packaging is only for the additional real
    FitGroup GUI surface; it cannot replace that regression.
    """
    from chisurf.core.data import DataGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.project.session import capture_session, restore_session
    from chisurf.core.project.storage import load_file, save_file
    from test.project.scientific_catalogue_probe import scientific_observables

    wrapper_uids = {}
    for iteration in range(2):
        project = load_file(directory / f"science-{iteration}.cs.pto")
        restored = restore_session(project)
        expected = json.loads((directory / f"expected-{iteration}.json").read_text())
        canonical_members = _members(restored.fits)
        assert [scientific_observables(fit) for fit in canonical_members] == expected["observables"]
        groups = []
        for fit in restored.fits:
            if isinstance(fit, FitGroup):
                groups.append(fit)
                continue
            # The default model_class=type creates no scientific model. Replace
            # its provisional member with the existing canonical scientific fit.
            group = FitGroup(data=DataGroup([fit.data]))
            group.grouped_fits[:] = [fit]
            group._model.fits = group.grouped_fits
            group.name = fit.name
            wrapper_uids.setdefault(
                fit.unique_identifier, (group.unique_identifier, group._model.unique_identifier)
            )
            group.unique_identifier, group._model.unique_identifier = wrapper_uids[
                fit.unique_identifier
            ]
            groups.append(group)
        assert _members(groups) == canonical_members
        wrapped = capture_session(restored.datasets, groups)
        originals = {
            member["uid"]: member for record in project.fits for member in record["members"]
        }
        for record in wrapped.fits:
            for member in record["members"]:
                original = originals[member["uid"]]
                # Reference owner addresses change to the new wrapper; every
                # scientific model/parameter/native identity remains exact.
                assert member["model"]["uid"] == original["model"]["uid"]
                for parameter, previous in zip(
                    member["model"]["parameters"], original["model"]["parameters"]
                ):
                    assert {k: v for k, v in parameter.items() if k != "link_target"} == {
                        k: v for k, v in previous.items() if k != "link_target"
                    }
        destination = save_file(wrapped, directory / f"grouped-science-{iteration}.cs.pto")
        again = restore_session(load_file(destination))
        _assert_snapshot(wrapped, again.datasets, again.fits)
        assert [scientific_observables(fit) for fit in _members(again.fits)] == expected[
            "observables"
        ]


def _assert_snapshot(project, datasets, fits):
    """Keep topology, bounds, fixed flags, ranges, selections and links exact."""
    from chisurf.core.project.session import capture_session
    from test.project.scientific_catalogue_probe import _differences

    captured = capture_session(datasets, fits)
    assert captured.datasets == project.datasets, list(
        _differences(project.datasets, captured.datasets, "datasets")
    )[:10]
    assert captured.fits == project.fits, list(_differences(project.fits, captured.fits, "fits"))[
        :10
    ]


def _document_owned_parameter_index(fits):
    """Index exact parameter objects declared by the canonical document owner.

    Active optimizer vectors are deliberately narrower for models such as
    GeneralFCS.  The shared owner graph is also what public parameter services
    use; it includes inactive presets without traversing Qt or process-global
    registry state.
    """
    from types import SimpleNamespace

    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.core.project.session import owned_scientific_objects

    owner = SimpleNamespace(fits=list(fits))
    objects = owned_scientific_objects(owner, include_plugins=False)
    return {
        uid: parameter
        for uid, parameter in objects.items()
        if isinstance(parameter, FittingParameter)
    }


def _display_owner(model, binding):
    """Resolve the symbolic binding owner without retaining any Qt object."""
    if binding["owner"] == "model":
        return model
    if binding["owner"] == "fit.data":
        return getattr(getattr(model, "fit", None), "data", None)
    raise AssertionError(f"unsupported display binding owner: {binding['owner']!r}")


def _display_path_value(owner, path):
    """Read a dotted public property or metadata key from its declared owner."""
    value = owner
    for part in path.split("."):
        if isinstance(value, dict):
            value = value[part]
        else:
            value = getattr(value, part)
    return value


def _declared_display_binding(editor, parameter):
    """Validate one table-only scalar/output against its real non-port owner."""
    binding = getattr(parameter, "display_binding", None)
    if binding is None:
        return None
    from chisurf.core.dataspec.display_binding import (
        COMPUTED_OUTPUT,
        DATA_METADATA,
        MODEL_SCALAR,
        validate_display_binding,
    )

    binding = validate_display_binding(binding)
    model = editor.model
    owner = _display_owner(model, binding)
    assert owner is not None, ("display binding owner is absent", binding)
    kind = binding["kind"]
    if kind == MODEL_SCALAR:
        assert owner is model
        assert binding["path"] in model.scalar_names(), (
            "declared scalar display path is not a persisted model scalar",
            binding,
        )
        assert not parameter.is_output
    elif kind == COMPUTED_OUTPUT:
        assert owner is model and parameter.is_output
        source_value = float(_display_path_value(owner, binding["path"]))
        shown_value = float(parameter.value)
        assert source_value == shown_value or (
            math.isnan(source_value) and math.isnan(shown_value)
        ), ("computed display row is stale", binding, source_value, shown_value)
    elif kind == DATA_METADATA:
        assert parameter.is_output
        metadata = getattr(owner, "meta_data", None) or {}
        assert binding["path"].split(".")[0] in metadata, (
            "declared metadata display has no source namespace",
            binding,
            metadata,
        )
    else:  # ``validate_display_binding`` makes this unreachable; retain a clear probe error.
        raise AssertionError(f"unsupported display binding kind: {kind!r}")
    return binding


def _editor_bindings(editor, live_parameters):
    """Inspect scientific controls against exact live scientific port owners."""
    from qtpy import QtCore, QtWidgets

    from chisurf.gui.autoform.sections.global_parameter_table import GlobalParameterTableModel
    from chisurf.gui.autoform.sections.parameter_table import (
        COLUMN_IDS,
        PairedParameterTableModel,
        ParameterGroupTableModel,
    )

    tables = []
    for table in editor.findChildren(QtWidgets.QTableView):
        raw_model = table.model()
        if isinstance(raw_model, QtCore.QSortFilterProxyModel):
            # ChiTableWidget installs a sort/filter proxy in front of the
            # scientific table model; inventory the scientific rows it fronts.
            model = raw_model.sourceModel()
        else:
            model = raw_model
        cells = []
        for row in range(model.rowCount()):
            for column in range(model.columnCount()):
                if isinstance(model, PairedParameterTableModel):
                    pair = model.param_at(row, column)
                    if pair is None:
                        continue
                    parameter, field = pair
                elif isinstance(model, ParameterGroupTableModel):
                    parameter, field = model.param_at(row), COLUMN_IDS[column]
                elif isinstance(model, GlobalParameterTableModel):
                    if column != 4:
                        continue
                    parameter, field = model.row_at(row).param, "value"
                else:
                    continue
                if parameter is None:
                    continue
                uid = parameter.unique_identifier
                display_binding = _declared_display_binding(editor, parameter)
                if display_binding is None:
                    assert live_parameters.get(uid) is parameter, (
                        "generated table bound to a foreign or stale scientific parameter",
                        uid,
                    )
                index = model.index(row, column)
                rendered = model.data(index, QtCore.Qt.EditRole)
                if field == "value" and rendered is not None:
                    shown, value = float(rendered), float(parameter.value)
                    # Optional derived cells can carry the archive's explicit
                    # unset-output sentinel. Primary scientific observables are
                    # still compared exactly and are never filled or replaced.
                    assert shown == value or (
                        parameter.is_output and math.isnan(shown) and math.isnan(value)
                    ), (uid, rendered, parameter.value)
                editable = bool(model.flags(index) & QtCore.Qt.ItemIsEditable)
                if display_binding is not None:
                    if display_binding["kind"] == "model_scalar":
                        assert editable is (field == "value"), (
                            "scalar display exposes an inert non-value control",
                            display_binding,
                            field,
                        )
                    else:
                        assert not editable, (
                            "read-only display binding is editable",
                            display_binding,
                            field,
                        )
                cells.append(
                    {
                        "parameter_uid": uid,
                        "name": parameter.name,
                        "field": field,
                        "row": row,
                        "column": column,
                        "edit_role": rendered,
                        "editable": editable,
                        "display_binding": display_binding,
                    }
                )
        tables.append({"model": type(model).__name__, "rows": model.rowCount(), "cells": cells})
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget

    for grid in editor.findChildren(RateMatrixWidget):
        cells = []
        values = grid._binding.values()
        for (row, column), spin in grid._spins.items():
            parameter = grid._binding.parameter(row, column)
            if parameter is None:
                continue
            uid = parameter.unique_identifier
            assert live_parameters.get(uid) is parameter, (
                "rate matrix bound to a foreign or stale scientific parameter",
                uid,
            )
            scientific_value = float(parameter.value)
            assert values[row * grid.table.columnCount() + column] == scientific_value
            cells.append(
                {
                    "parameter_uid": uid,
                    "name": parameter.name,
                    "field": "value",
                    "row": row,
                    "column": column,
                    "scientific_value": scientific_value,
                    "edit_role": spin.value(),
                    "editable": spin.isEnabled()
                    and not spin.isReadOnly()
                    and not parameter.is_output
                    and parameter.link is None,
                }
            )
        tables.append(
            {
                "model": type(grid).__name__,
                "target": grid._attr,
                "rows": grid.table.rowCount(),
                "cells": cells,
            }
        )

    # ``dynamic_group`` deliberately renders compact direct parameter widgets,
    # not a table model. They are still scientific controls: inventory them by
    # the exact object identity exposed by the document-owned port graph.
    from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterWidget
    from chisurf.gui.widgets.fitting.scientific_spinbox import ScientificDoubleSpinBox

    direct_cells = []
    for parameter_widget in editor.findChildren(FittingParameterWidget):
        parameter = getattr(parameter_widget, "fitting_parameter", None)
        if parameter is None:
            continue
        uid = parameter.unique_identifier
        display_binding = _declared_display_binding(editor, parameter)
        if display_binding is None:
            assert live_parameters.get(uid) is parameter, (
                "direct parameter widget bound to a foreign or stale scientific parameter",
                uid,
            )
        control = parameter_widget.widget_value
        assert isinstance(control, ScientificDoubleSpinBox)
        scientific_value = float(parameter.value)
        rendered = float(control.value())
        assert rendered == scientific_value or (
            parameter.is_output and math.isnan(rendered) and math.isnan(scientific_value)
        ), (
            uid,
            rendered,
            scientific_value,
        )
        editable = bool(
            control.isEnabled()
            and not control.isReadOnly()
            and not parameter.is_output
            and parameter.link is None
        )
        if display_binding is not None:
            if display_binding["kind"] == "model_scalar":
                assert editable, ("scalar direct widget is unexpectedly read-only", display_binding)
            else:
                assert not editable, (
                    "read-only direct display binding is editable",
                    display_binding,
                )
        elif parameter.is_output or parameter.link is not None:
            assert not editable, ("non-editable direct parameter role is editable", uid)
        direct_cells.append(
            {
                "parameter_uid": uid,
                "name": parameter.name,
                "field": "value",
                "scientific_value": scientific_value,
                "edit_role": rendered,
                "editable": editable,
                "display_binding": display_binding,
                "control": type(parameter_widget).__name__,
                "value_control": type(control).__name__,
            }
        )
    if direct_cells:
        tables.append(
            {
                "model": FittingParameterWidget.__name__,
                "rows": len(direct_cells),
                "cells": direct_cells,
            }
        )
    return tables


def _capture(main, app, directory, stage):
    """Visit every registered plot and retain real/constrained Main renders."""
    main.dockWidgetAnalysis.show()
    main.dockWidgetAnalysis.raise_()
    app.processEvents()
    visited = []
    for window in main.mdiarea.subWindowList():
        main.mdiarea.setActiveSubWindow(window)
        declared = window.fit.model.view_spec().plots
        if len(window._plot_specs) != len(declared):
            for width, height in ((1500, 950), (900, 650)):
                main.resize(width, height)
                app.processEvents()
                path = (
                    directory / f"{stage}-{window.fit.unique_identifier}-missing-plots-{width}.png"
                )
                assert main.grab().save(str(path)), path
        assert len(window._plot_specs) == len(declared), (
            "registered plots were silently dropped",
            len(window._plot_specs),
            len(declared),
        )
        # A declared tool without plots still needs a render of its real editor.
        if not declared:
            for width, height in ((1500, 950), (900, 650)):
                main.resize(width, height)
                app.processEvents()
                path = directory / f"{stage}-{window.fit.unique_identifier}-editor-{width}.png"
                assert main.grab().save(str(path)), path
        for index in range(window.plot_tab_widget.count()):
            window.plot_tab_widget.setCurrentIndex(index)
            window.ensure_plot_created(index)
            window.refresh_current_plot()
            app.processEvents()
            assert window._plots_all[index] is not None, (window.fit.name, index)
            visited.append(
                {
                    "fit_uid": window.fit.unique_identifier,
                    "index": index,
                    "plot": type(window._plots_all[index]).__name__,
                }
            )
            for width, height in ((1500, 950), (900, 650)):
                main.resize(width, height)
                window.setGeometry(
                    0, 0, max(320, main.mdiarea.width() - 20), max(240, main.mdiarea.height() - 20)
                )
                app.processEvents()
                path = directory / f"{stage}-{window.fit.unique_identifier}-tab{index}-{width}.png"
                assert main.grab().save(str(path)), path
    assert main.mdiarea.subWindowList(), "ordinary restore did not publish a fit window"
    return visited


def _edit_control(main, app, parameter_uid, value):
    """Commit through the live editor's actual scientific control."""
    from qtpy import QtCore, QtTest, QtWidgets

    from chisurf.gui.autoform.sections.global_parameter_table import (
        COL_VALUE as GLOBAL_COL_VALUE,
    )
    from chisurf.gui.autoform.sections.global_parameter_table import (
        GlobalParameterTableModel,
    )
    from chisurf.gui.autoform.sections.parameter_table import (
        COL_VALUE,
        PairedParameterTableModel,
        ParameterGroupTableModel,
    )
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget
    from chisurf.gui.widgets.fitting.parameter_widgets import FittingParameterWidget
    from chisurf.gui.widgets.fitting.scientific_spinbox import ScientificDoubleSpinBox
    from chisurf.gui.widgets.models.model_editor import model_editor_widget

    inspected = []
    for window in main.mdiarea.subWindowList():
        fit = window.fit
        members = getattr(fit, "grouped_fits", [fit])
        for member in members:
            editor = model_editor_widget(member.model)
            assert editor is not None and editor.model is member.model
            for parameter_widget in editor.findChildren(FittingParameterWidget):
                parameter = getattr(parameter_widget, "fitting_parameter", None)
                if parameter is None:
                    continue
                inspected.append(
                    {
                        "uid": parameter.unique_identifier,
                        "name": parameter.name,
                        "control": type(parameter_widget).__name__,
                    }
                )
                if parameter.unique_identifier != parameter_uid:
                    continue
                document_owned = _document_owned_parameter_index([member])
                assert document_owned.get(parameter_uid) is parameter, (
                    "foreign scientific direct-widget owner",
                )
                control = parameter_widget.widget_value
                assert isinstance(control, ScientificDoubleSpinBox)
                assert not parameter.is_output and parameter.link is None
                assert control.isEnabled() and not control.isReadOnly()
                assert math.isfinite(value)
                text = repr(float(value))
                assert float(text) == value, (
                    "scientific input cannot be represented by direct control",
                    value,
                    text,
                )
                main.mdiarea.setActiveSubWindow(window)
                main.dockWidgetAnalysis.show()
                main.dockWidgetAnalysis.raise_()
                editor.show()
                # Expand/show the real Main ancestry; this must exercise the
                # widget wired by AutoForm, never a detached stand-in.
                ancestor = parameter_widget.parentWidget()
                while ancestor is not None and ancestor is not main:
                    if callable(getattr(ancestor, "set_expanded", None)):
                        ancestor.set_expanded(True)
                    ancestor.show()
                    ancestor = ancestor.parentWidget()
                app.processEvents()
                line_edit = control.lineEdit()
                control.setFocus()
                line_edit.setFocus()
                line_edit.selectAll()
                QtTest.QTest.keyClicks(line_edit, text)
                QtTest.QTest.keyClick(line_edit, QtCore.Qt.Key_Return)
                app.processEvents()
                assert float(control.value()) == value, (
                    parameter_uid,
                    parameter.name,
                    control.value(),
                    value,
                )
                assert float(parameter.value) == value, (
                    parameter_uid,
                    parameter.name,
                    parameter.value,
                    value,
                )
                return {
                    "parameter_uid": parameter_uid,
                    "name": parameter.name,
                    "table_model": type(parameter_widget).__name__,
                    "control": type(control).__name__,
                    "requested_value": value,
                    "actual_value": float(parameter.value),
                }
            for grid in editor.findChildren(RateMatrixWidget):
                for (row, column), control in grid._spins.items():
                    parameter = grid._binding.parameter(row, column)
                    if parameter is None:
                        continue
                    inspected.append({"uid": parameter.unique_identifier, "name": parameter.name})
                    if parameter.unique_identifier != parameter_uid:
                        continue
                    live = {p.unique_identifier: p for p in member.model.parameters_all}
                    assert live.get(parameter_uid) is parameter, "foreign scientific control owner"
                    assert isinstance(control, QtWidgets.QDoubleSpinBox)
                    assert not parameter.is_output and parameter.link is None
                    assert control.isEnabled() and not control.isReadOnly()
                    assert math.isfinite(value) and control.minimum() <= value <= control.maximum()
                    text = control.locale().toString(value, "f", control.decimals())
                    assert control.locale().toDouble(text) == (value, True), (
                        "scientific input cannot be represented by control",
                        value,
                        text,
                    )
                    main.mdiarea.setActiveSubWindow(window)
                    main.dockWidgetAnalysis.show()
                    main.dockWidgetAnalysis.raise_()
                    editor.show()
                    ancestor = control.parentWidget()
                    while ancestor is not None and ancestor is not main:
                        if callable(getattr(ancestor, "set_expanded", None)):
                            ancestor.set_expanded(True)
                        ancestor.show()
                        ancestor = ancestor.parentWidget()
                    app.processEvents()
                    control.setFocus()
                    control.selectAll()
                    QtTest.QTest.keyClicks(control, text)
                    QtTest.QTest.keyClick(control, QtCore.Qt.Key_Return)
                    app.processEvents()
                    assert float(parameter.value) == value, (
                        parameter_uid,
                        parameter.name,
                        parameter.value,
                        value,
                    )
                    return {
                        "parameter_uid": parameter_uid,
                        "name": parameter.name,
                        "table_model": type(grid).__name__,
                        "target": grid._attr,
                        "row": row,
                        "column": column,
                        "control": type(control).__name__,
                        "requested_value": value,
                        "actual_value": float(parameter.value),
                    }
            for table in editor.findChildren(QtWidgets.QTableView):
                raw_model = table.model()
                if isinstance(raw_model, QtCore.QSortFilterProxyModel):
                    # ChiTableWidget fronts the scientific model with a
                    # sort/filter proxy: edit through the view's proxy index
                    # while addressing the parameter via the source model.
                    proxy = raw_model
                    model = proxy.sourceModel()
                else:
                    proxy = None
                    model = raw_model
                if not isinstance(
                    model,
                    (
                        ParameterGroupTableModel,
                        PairedParameterTableModel,
                        GlobalParameterTableModel,
                    ),
                ):
                    continue
                for row in range(model.rowCount()):
                    for column in range(model.columnCount()):
                        if isinstance(model, PairedParameterTableModel):
                            pair = model.param_at(row, column)
                            if pair is None or pair[1] != "value":
                                continue
                            parameter = pair[0]
                        elif isinstance(model, GlobalParameterTableModel):
                            if column != GLOBAL_COL_VALUE:
                                continue
                            parameter = model.row_at(row).param
                        else:
                            if column != COL_VALUE:
                                continue
                            parameter = model.param_at(row)
                        if parameter is None:
                            continue
                        inspected.append(
                            {"uid": parameter.unique_identifier, "name": parameter.name}
                        )
                        if parameter.unique_identifier != parameter_uid:
                            continue
                        index = model.index(row, column)
                        assert model.flags(index) & QtCore.Qt.ItemIsEditable
                        assert not parameter.is_output and parameter.link is None
                        if proxy is not None:
                            view_index = proxy.mapFromSource(index)
                            assert view_index.isValid(), (
                                "scientific row is filtered out of the live table view",
                                parameter.name,
                            )
                        else:
                            view_index = index
                        main.mdiarea.setActiveSubWindow(window)
                        main.dockWidgetAnalysis.show()
                        main.dockWidgetAnalysis.raise_()
                        editor.show()
                        # Expand the actual section ancestors, rather than detach a
                        # standalone editor from Main or bypass its event wiring.
                        ancestor = table.parentWidget()
                        while ancestor is not None and ancestor is not main:
                            if callable(getattr(ancestor, "set_expanded", None)):
                                ancestor.set_expanded(True)
                            ancestor.show()
                            ancestor = ancestor.parentWidget()
                        app.processEvents()
                        table.scrollTo(view_index)
                        table.setCurrentIndex(view_index)
                        table.edit(view_index)
                        app.processEvents()
                        control = table.findChild(QtWidgets.QAbstractSpinBox)
                        assert control is not None, "real table delegate did not open its control"
                        assert isinstance(control, ScientificDoubleSpinBox)
                        assert math.isfinite(value)
                        # A programmatic ``setValue`` refreshes the editor's
                        # compact display before Return reaches the delegate;
                        # it therefore erases a legitimate full-precision input
                        # (e.g. 55.550999999999995 -> 55.551).  Type the exact
                        # finite decimal through the real editor instead.
                        text = repr(float(value))
                        assert float(text) == value, (
                            "scientific input cannot be represented by table control",
                            value,
                            text,
                        )
                        control.setFocus()
                        control.selectAll()
                        QtTest.QTest.keyClicks(control, text)
                        QtTest.QTest.keyClick(control, QtCore.Qt.Key_Return)
                        app.processEvents()
                        assert float(control.value()) == value, (
                            parameter_uid,
                            parameter.name,
                            control.value(),
                            value,
                        )
                        assert float(parameter.value) == value, (
                            parameter_uid,
                            parameter.name,
                            parameter.value,
                            value,
                        )
                        return {
                            "parameter_uid": parameter_uid,
                            "name": parameter.name,
                            "table_model": type(model).__name__,
                            "row": row,
                            "column": column,
                            "control": type(control).__name__,
                            "requested_value": value,
                            "actual_value": float(parameter.value),
                        }
    raise AssertionError(
        f"canonical scientific input {parameter_uid} lacks a generated "
        f"editable scientific control; inspected {inspected}"
    )


def _structural_coordinates(state):
    """Extract structure coordinates from a ProteinMC-style adapter payload."""
    payload = state.get("proteinmc") or {}
    structure = payload.get("structure") or payload.get("current_structure") or {}
    atoms = structure.get("atoms") or {}
    for field in atoms.get("fields", []):
        if field.get("name") == "xyz":
            array = field.get("array") or {}
            values = array.get("values")
            if values is None and "value" in array:
                values = [array["value"]]
            if values is not None:
                return values
    return structure.get("xyz")


def _model_inputs(model):
    """Model record minus adapter state and the values of declared outputs.

    Output parameters (``is_output``) are recomputed from the structure, so a
    coordinate edit legitimately changes their values.
    """
    record = {k: v for k, v in model.items() if k not in {"adapter_state", "parameters"}}
    record["parameters"] = [
        {k: v for k, v in parameter.items() if k != "value"}
        if parameter.get("is_output")
        else parameter
        for parameter in model.get("parameters", [])
    ]
    return record


def _structural_edit(first, second):
    """Detect a coordinate-only scientific edit between canonical archives.

    Some producers edit structural model state (ProteinMCModel shifts an atom
    and the recomputed distances are declared outputs). Their parameter diff is
    empty by design. Returns ``(member_uid, coordinates)`` for the changed
    member when the adapter structure coordinates differ and everything else
    about the member except declared output values is identical; ``None``
    otherwise. Accepts either a
    :class:`~chisurf.core.project.storage.Project` (``.fits``) or an already
    unwrapped fits list/dict payload.
    """
    first_records = first.fits if hasattr(first, "fits") else first["fits"]
    second_records = second.fits if hasattr(second, "fits") else second["fits"]
    for record_first, record_second in zip(first_records, second_records):
        for member_first, member_second in zip(record_first["members"], record_second["members"]):
            model_first, model_second = member_first["model"], member_second["model"]
            if _model_inputs(model_first) != _model_inputs(model_second):
                continue
            state_first = model_first.get("adapter_state") or {}
            state_second = model_second.get("adapter_state") or {}
            if state_first == state_second:
                continue
            changed = {
                key
                for key in state_first.keys() | state_second.keys()
                if state_first.get(key) != state_second.get(key)
            }
            if len(changed) != 1:
                continue
            key = next(iter(changed))
            coordinates_first = _structural_coordinates({key: state_first.get(key) or {}})
            coordinates_second = _structural_coordinates({key: state_second.get(key) or {}})
            if coordinates_second is None or coordinates_second == coordinates_first:
                # A non-structural adapter change (settings, traces) is not the
                # producer's coordinate edit.
                continue
            return member_first["uid"], coordinates_second
    return None


def _observables_close(actual, expected, rtol=1e-6, atol=1e-6):
    """Compare observables with a bound for PDB-precision structural edits.

    A structural edit reaches the live model through PDB text, which stores
    coordinates to ~1e-7 Å, so coordinate-derived observables differ from the
    archive's full-precision values at ~1e-8. Structure (keys, lengths, types)
    must still match exactly; only floating-point leaves use ``rtol``/``atol``.
    Scalar-port edits keep the exact ``==`` comparison in :func:`run`.
    """
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(_observables_close(actual[k], expected[k], rtol, atol) for k in expected)
        )
    if isinstance(expected, (list, tuple)):
        return (
            isinstance(actual, (list, tuple))
            and len(actual) == len(expected)
            and all(_observables_close(a, e, rtol, atol) for a, e in zip(actual, expected))
        )
    if isinstance(expected, float) or isinstance(actual, float):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and bool(np.isclose(actual, expected, rtol=rtol, atol=atol))
        )
    return actual == expected


def _structural_reference(fits, member_uid, committed_path):
    """The producer archive as the structural GUI edit legitimately records it.

    The producer shifts coordinates in memory; the GUI performs the same
    scientific operation by loading a PDB through the Structure control. That
    load deliberately records the file as ``structure_source`` (and as the
    structure's own ``filename``) and seeds the sampler's
    ``current_structure`` with a copy of the loaded structure. Every
    other field must match the archive (numbers to PDB precision, see
    :func:`_observables_close`).
    """
    import copy

    reference = copy.deepcopy(fits)
    for record in reference:
        for member in record["members"]:
            if member["uid"] != member_uid:
                continue
            payload = member["model"]["adapter_state"]["proteinmc"]
            payload["structure_source"] = str(committed_path)
            if isinstance(payload.get("structure"), dict) and "filename" in payload["structure"]:
                payload["structure"]["filename"] = str(committed_path)
            payload["current_structure"] = copy.deepcopy(payload["structure"])
    return reference


def _adopt_loaded_structure_identities(reference_fits, captured_fits, member_uid):
    """Take the freshly loaded structures' object ``uid`` from the live capture.

    Loading a file creates new structure objects, so their identities cannot
    be predicted from the producer archive. Adopting them here (and only them)
    keeps the later save/readback comparison checking that they persist.
    """
    for record, live_record in zip(reference_fits, captured_fits):
        for member, live_member in zip(record["members"], live_record["members"]):
            if member["uid"] != member_uid:
                continue
            payload = member["model"]["adapter_state"]["proteinmc"]
            live = live_member["model"]["adapter_state"]["proteinmc"]
            for key in ("structure", "current_structure"):
                if (
                    isinstance(payload.get(key), dict)
                    and isinstance(live.get(key), dict)
                    and "uid" in live[key]
                ):
                    payload[key]["uid"] = live[key]["uid"]


def _assert_structural_snapshot(reference_fits, reference_datasets, datasets, fits, member_uid):
    """Exact datasets; fits equal ``reference_fits`` to PDB precision."""
    from chisurf.core.project.session import capture_session
    from test.project.scientific_catalogue_probe import _differences

    captured = capture_session(datasets, fits)
    _adopt_loaded_structure_identities(reference_fits, captured.fits, member_uid)
    assert captured.datasets == reference_datasets, list(
        _differences(reference_datasets, captured.datasets, "datasets")
    )[:10]
    assert _observables_close(captured.fits, reference_fits), list(
        _differences(reference_fits, captured.fits, "fits")
    )[:10]


def _edit_structural_control(main, app, structural, directory):
    """Commit the archive's structure through the real Structure file control."""
    from qtpy import QtCore, QtTest, QtWidgets

    from chisurf.core.fio.structure.coordinates import write_pdb

    member_uid, coordinates = structural
    for window in main.mdiarea.subWindowList():
        for member in getattr(window.fit, "grouped_fits", [window.fit]):
            if member.unique_identifier != member_uid:
                continue
            from chisurf.gui.widgets.models.model_editor import model_editor_widget

            editor = model_editor_widget(member.model)
            assert editor is not None and editor.model is member.model
            # Write the archive's exact coordinates as a single-model PDB next
            # to the report. The atom table (names/residues/chain) is the live
            # model's own, so only the coordinates can differ from its file.
            atoms = member.model.structure.atoms.copy()
            atoms["xyz"] = [[float(v) for v in row] for row in coordinates]
            path = directory / f"structure-edit-{member_uid}.pdb"
            write_pdb(str(path), atoms, append_model=False)
            section = None
            for field in editor.findChildren(QtWidgets.QWidget):
                if getattr(field, "is_form_field", False):
                    candidate = getattr(field, "_section", None)
                    if candidate is not None and getattr(candidate, "attr", "") == "structure_file":
                        section = field
                        break
            assert section is not None, "Structure file control is not in the generated editor"
            line_edit = section.editor
            assert isinstance(line_edit, QtWidgets.QLineEdit)
            assert str(path) != str(member.model.structure_file or "")
            main.mdiarea.setActiveSubWindow(window)
            main.dockWidgetAnalysis.show()
            main.dockWidgetAnalysis.raise_()
            editor.show()
            ancestor = section.parentWidget()
            while ancestor is not None and ancestor is not main:
                if callable(getattr(ancestor, "set_expanded", None)):
                    ancestor.set_expanded(True)
                ancestor.show()
                ancestor = ancestor.parentWidget()
            app.processEvents()
            line_edit.setFocus()
            line_edit.selectAll()
            # An exact temporary path cannot be typed character-perfect through
            # keyClicks reliably; paste it exactly as a user would.
            QtWidgets.QApplication.clipboard().setText(str(path))
            QtTest.QTest.keyClick(
                line_edit, QtCore.Qt.Key.Key_V, QtCore.Qt.KeyboardModifier.ControlModifier
            )
            app.processEvents()
            assert line_edit.text() == str(path), (
                "Structure control did not receive the edited path",
                line_edit.text(),
                path,
            )
            # editingFinished commits on Return; the control's real wiring then
            # calls load_starting_structure and recomputes the distances.
            QtTest.QTest.keyClick(line_edit, QtCore.Qt.Key_Return)
            app.processEvents()
            live = member.model._active_coordinates()
            assert (
                live is not None
                and max(
                    abs(float(a) - float(b))
                    for row_a, row_b in zip(np.asarray(live).tolist(), atoms["xyz"])
                    for a, b in zip(row_a, row_b)
                )
                < 1e-6
            ), "Structure control did not load the edited coordinates"
            assert member.model._distance_parameters, (
                "structural edit did not reach the declared distance outputs"
            )
            return {
                "parameter_uid": member_uid,
                "name": "structure coordinates",
                "table_model": type(section).__name__,
                "control": type(line_edit).__name__,
                "committed_path": str(path),
                "actual_value": float(next(iter(member.model._distance_parameters.values())).value),
            }
    raise AssertionError(f"structural edit target {member_uid} has no open editor window")


def _shutdown_qt_process(report):
    """Tear down the child's Qt state before interpreter exit.

    The repo's pytest harness documents that every pyqtgraph ViewBox connects
    its ``destroyed`` signal to a Python lambda and that ``pyqtgraph.cleanup()``
    must run before Python garbage collection unloads those callbacks; a GUI
    child that ends with only ``main.hide()`` can segfault or bus-error while
    Python tears down live plots (observed as SIGBUS/SIGSEGV in the ParseFCS
    actual-Main child). This mirrors the harness's ``pytest_sessionfinish``
    cleanup and the stronger per-test shutdown used by GUI lifetime tests:
    hide, delete the window, flush DeferredDelete events, then run pyqtgraph's
    exit cleanup while the QApplication still exists.
    """
    pyqtgraph = sys.modules.get("pyqtgraph")
    report["shutdown"] = {"pyqtgraph_cleanup": False}
    app = None
    try:
        from qtpy import QtWidgets

        app = QtWidgets.QApplication.instance()
    except Exception:
        app = None
    if pyqtgraph is not None:
        try:
            pyqtgraph.cleanup()
            report["shutdown"]["pyqtgraph_cleanup"] = True
        except Exception as exc:  # pragma: no cover - defensive
            report["shutdown"]["pyqtgraph_cleanup_error"] = repr(exc)
    if app is not None:
        app.processEvents()


def _exit_after_report(report):
    """Exit the child immediately once its evidence report is safely on disk.

    Everything the parent consumes (exit-code-as-verdict plus the JSON report
    and captures) is written before this runs. Returning into normal
    interpreter teardown is the remaining hazard: Python unloads ~170 native
    extensions while Qt/pyqtgraph objects are still alive, which observably
    killed completed ParseFCS children with SIGBUS *after* ``phase: complete``
    was recorded. ``os._exit`` skips that teardown by design; buffers are
    flushed by the explicit writes above, and stdout/stderr carry no evidence.
    """
    os._exit(0)


def run(directory, stage, report):
    """Load through the ordinary API and save through the ordinary document macro."""
    structural = None
    assert not any(name == "mmfdb" or name.startswith("mmfdb.") for name in sys.modules)
    sys.meta_path.insert(0, _BlockMMFDB(report))
    from qtpy import QtCore, QtWidgets

    import chisurf as cs
    import chisurf.gui as gui
    from chisurf.core.api import ChiSurfAPI
    from chisurf.core.project.lifecycle import SaveDecision
    from chisurf.core.project.project import ResourceContext
    from chisurf.core.project.storage import load_file
    from chisurf.gui.main import Main
    from chisurf.gui.widgets.models.model_editor import model_editor_widget
    from chisurf.macros.core_fit import save_project
    from test.project.scientific_catalogue_probe import original_sources, scientific_observables

    report["phase"] = "source-read"
    source = (
        directory
        / {
            "canonical": "science-0.cs.pto",
            "before": "grouped-science-0.cs.pto",
            "control": "grouped-science-0.cs.pto",
            "restored": "gui-before.cs.pto",
            "edited": "gui-edited.cs.pto",
        }[stage]
    )
    expected_path = directory / (
        "gui-edited-expected.json" if stage == "edited" else "expected-0.json"
    )
    expected = json.loads(expected_path.read_text())
    blocked = set(expected.get("source_paths", []))

    def forbid_source_reads(event, arguments):
        """Forbid original scientific inputs throughout ordinary GUI restoration."""
        if event == "open" and isinstance(arguments[0], (str, bytes)):
            path = arguments[0]
            path = path.decode() if isinstance(path, bytes) else path
            assert str(Path(path).resolve()) not in blocked, f"original source reread: {path}"

    sys.addaudithook(forbid_source_reads)
    project = load_file(source)
    blocked.update(original_sources(project))
    report["canonical_modes"] = [
        {
            "fit_uid": member["uid"],
            "model": member["model"]["model_class"],
            "adapter_state": member["model"]["adapter_state"],
            "fit_range": member["fit_range"],
        }
        for record in project.fits
        for member in record["members"]
    ]
    report["science_expected"] = expected["observables"]
    report["phase"] = "main-construction"
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    settings_type = QtCore.QSettings

    class IsolatedSettings(settings_type):
        """Keep all actual Main preferences inside this native scenario."""

        def __init__(self, *args, **kwargs):
            super().__init__(str(directory / stage / "main.ini"), settings_type.IniFormat)

    QtCore.QSettings = IsolatedSettings
    cs.fits, cs.imported_datasets, gui.fit_windows = [], [], []
    cs.__client__ = None
    cs.project_resources = ResourceContext()
    cs.console = gui.widgets.ipython.QIPythonWidget()
    cs.console.history_widget = None
    main = Main()
    cs.cs = main
    main.init_setups()
    main.define_actions()
    main.arrange_widgets()
    main._save_decision = lambda: SaveDecision.DISCARD
    main.resize(1500, 950)
    main.show()
    report["phase"] = "ordinary-api-load"
    api = ChiSurfAPI(mode="local")
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.gui.widgets.fitting.fitting_client import install_fitting_client
    from chisurf.server.dispatcher import ServiceDispatcher

    dispatcher = ServiceDispatcher(api._state)
    dispatcher._build_default_registry()
    install_fitting_client(InProcessClient(dispatcher))

    def trace_publication(frame, event, argument):
        """Retain the source traceback hidden by the public service envelope."""
        if event == "exception" and isinstance(argument[1], (TypeError, AssertionError)):
            filename = frame.f_code.co_filename
            if "/chisurf/core/project/" in filename or "/chisurf/gui/" in filename:
                report.setdefault("publication_exceptions", []).append(
                    "".join(traceback.format_exception(*argument))
                )
        return trace_publication

    sys.settrace(trace_publication)
    try:
        result = api.load_project(str(source))
    finally:
        sys.settrace(None)
    report["load_result"] = result
    if result.get("ok") is not True:
        report["failure_capture"] = str(directory / f"{stage}-publication-failure.png")
        app.processEvents()
        assert main.grab().save(report["failure_capture"])
    assert result["ok"] is True, result
    app.processEvents()
    report["phase"] = "exact-scientific-readback"
    _assert_snapshot(project, cs.imported_datasets, cs.fits)
    actual = [scientific_observables(fit) for fit in _members(cs.fits)]
    assert actual == expected["observables"]
    report["science_before"] = actual
    report["bindings"] = []
    live_parameters = _document_owned_parameter_index(cs.fits)
    assert len(main.mdiarea.subWindowList()) == len(cs.fits)
    for fit in cs.fits:
        for member in getattr(fit, "grouped_fits", [fit]):
            editor = model_editor_widget(member.model)
            assert editor is not None and editor.model is member.model
            report["bindings"].append(
                {
                    "fit_uid": member.unique_identifier,
                    "model": type(member.model).__name__,
                    "editor": type(editor).__name__,
                    "tables": _editor_bindings(editor, live_parameters),
                }
            )
    if stage != "control":
        report["phase"] = "registered-tab-capture"
        report["visited_tabs"] = _capture(main, app, directory, stage)
        _assert_snapshot(project, cs.imported_datasets, cs.fits)
    if stage in {"restored", "control"}:
        report["phase"] = "generated-control-edit"
        # The canonical producer already proves a legitimate, scientifically
        # effective input edit. Address that exact input by UID in the real UI.
        second = load_file(directory / "grouped-science-1.cs.pto")
        before_parameters, after_parameters = _parameters(project), _parameters(second)
        changes = [
            (uid, parameter)
            for uid, parameter in after_parameters.items()
            if uid in before_parameters
            and parameter["value"] != before_parameters[uid]["value"]
            and not parameter.get("is_output", False)
            and not parameter.get("link_target")
        ]
        if len(changes) == 1:
            uid, changed_parameter = changes[0]
            report["control"] = _edit_control(main, app, uid, float(changed_parameter["value"]))
        else:
            # A producer edit may live in structural model state rather than a
            # scalar port (ProteinMCModel: the coordinates shifted, recomputing
            # the is_output distances). The declared GUI control for that
            # scientific operation is the view's Structure file input: commit a
            # PDB carrying the archive's exact coordinates through the real
            # QLineEdit (editingFinished -> _commit_file -> load_starting_
            # structure -> update_distance_values), then verify the observable
            # state equals the producer's archive exactly.
            structural = _structural_edit(project, second)
            assert structural is not None, (
                f"requires an explicit exposed scientific edit: {changes}"
            )
            report["control"] = _edit_structural_control(main, app, structural, directory)
        # Do not manually call update here: the actual control must recompute.
        changed = [scientific_observables(fit) for fit in _members(cs.fits)]
        expected_second = json.loads((directory / "expected-1.json").read_text())
        assert changed != actual, "GUI edit did not recompute dependent scientific outputs"
        if structural is None:
            assert changed == expected_second["observables"]
        else:
            if not _observables_close(changed, expected_second["observables"]):
                (directory / "structural-observables-actual.json").write_text(json.dumps(changed))
                raise AssertionError(
                    "structural GUI edit did not reproduce the producer's observables"
                )
        if structural is None:
            reference_fits = second.fits
            _assert_snapshot(second, cs.imported_datasets, cs.fits)
        else:
            reference_fits = _structural_reference(
                second.fits, structural[0], report["control"]["committed_path"]
            )
            _assert_structural_snapshot(
                reference_fits, second.datasets, cs.imported_datasets, cs.fits, structural[0]
            )
        report["science_after"] = changed
        report["edited_tabs"] = _capture(main, app, directory, "control-edited")
        expected_path = directory / "gui-edited-expected.json"
        # A structural edit's GUI-saved truth is what the GUI produced (already
        # bounded against the producer above); the reopened file must match it
        # exactly.
        expected_path.write_text(
            json.dumps(
                expected_second
                if structural is None
                else {**expected_second, "observables": changed}
            )
        )
    report["phase"] = "ordinary-macro-save"
    from chisurf.core.project.ui_state import get_ui_state

    expected_ui = get_ui_state(main)
    destination = directory / (
        "gui-edited.cs.pto" if stage in {"restored", "control"} else f"gui-{stage}.cs.pto"
    )
    saved = save_project(str(destination))
    readback = load_file(saved)
    reference = second if stage in {"restored", "control"} else project
    assert readback.datasets == reference.datasets
    if structural is None:
        assert readback.fits == reference.fits
    else:
        assert _observables_close(readback.fits, reference_fits)
    assert readback.ui_state["fit_windows"] == expected_ui["fit_windows"]
    report["saved"] = str(saved)
    assert not any(name == "mmfdb" or name.startswith("mmfdb.") for name in sys.modules)
    report["phase"] = "complete"
    main.hide()


def main():
    """Retain precise GUI/scientific failure phase even after a child failure."""
    directory, stage = Path(sys.argv[1]), sys.argv[2]
    (directory / stage).mkdir(parents=True, exist_ok=True)
    report = {
        "stage": stage,
        "configured_entry": json.loads((directory / "entry.json").read_text()),
    }
    try:
        if stage == "package":
            report["phase"] = "preserve-scientific-graph-group-packaging"
            package_gui(directory)
            report["phase"] = "complete"
        else:
            run(directory, stage, report)
    except BaseException:
        report["traceback"] = traceback.format_exc()
        raise
    finally:
        (directory / f"{stage}-report.json").write_text(json.dumps(report, indent=2))
        if stage != "package":
            # Every GUI-bearing child exits through the shared teardown before
            # Python garbage collection can destroy live plots with dead
            # pyqtgraph callbacks (see _shutdown_qt_process).
            _shutdown_qt_process(report)
            (directory / f"{stage}-report.json").write_text(json.dumps(report, indent=2))
            # The report is on disk and every lifecycle verdict is inside it;
            # skip native interpreter teardown, which is the only remaining
            # way this child can fail (SIGBUS after phase: complete).
            if report.get("phase") == "complete":
                _exit_after_report(report)


if __name__ == "__main__":
    main()
