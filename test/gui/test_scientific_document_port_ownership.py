"""Actual AutoForm tables distinguish canonical ports from declared displays."""

from __future__ import annotations

import pytest

pytest.importorskip("IMP.bff")

from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file
from chisurf.gui.widgets.models.model_editor import build_model_editor
from test.gui.scientific_document_gui_probe import _editor_bindings
from test.gui.test_classic_tcspc_editor import _fit


@pytest.fixture
def tcspc_editor(qapp):
    """A real classic TCSPC AutoForm editor over the persisted description model."""
    import chisurf as cs

    fit, model = _fit("tcspc_polarized")
    cs.fits.append(fit)
    editor = build_model_editor(model)
    editor.show()
    qapp.processEvents()
    try:
        yield fit, model, editor
    finally:
        cs.fits.remove(fit)
        editor.close()


def _value_cell(entries, name):
    cells = [cell for entry in entries for cell in entry["cells"]]
    return next(cell for cell in cells if cell["name"] == name and cell["field"] == "value")


def test_tcspc_display_rows_have_explicit_owner_path_kind_and_portable_scalar_state(
    tcspc_editor,
    tmp_path,
):
    """A table-only scalar is a declared persisted model state, not a fake port.

    ``rep`` is intentionally not in ``parameters_all``: it projects the
    description scalar ``period`` as MHz.  Its table cell must consequently
    identify the model scalar it owns, while ``PhB`` must identify a derived,
    read-only output.  The scalar edit must then survive an ordinary `.cs.pto`
    round trip, proving that the declared display path leads to portable state.
    """
    fit, model, editor = tcspc_editor
    live = {parameter.unique_identifier: parameter for parameter in model.parameters_all}

    entries = _editor_bindings(editor, live)
    rep = _value_cell(entries, "rep")
    background_photons = _value_cell(entries, "PhB")
    assert rep["display_binding"] == {
        "owner": "model",
        "kind": "model_scalar",
        "path": "period",
        "editable": True,
    }
    assert rep["editable"]
    rep_cells = [cell for entry in entries for cell in entry["cells"] if cell["name"] == "rep"]
    assert {cell["field"] for cell in rep_cells if cell["editable"]} == {"value"}
    assert background_photons["display_binding"] == {
        "owner": "model",
        "kind": "computed_output",
        "path": "generic.n_ph_bg",
        "editable": False,
    }
    assert not background_photons["editable"]

    row = next(parameter for parameter in model.convolve.parameters_all if parameter.name == "rep")
    row.value = 12.5
    assert model.get_scalar("period") == pytest.approx(80.0)

    member = fit.grouped_fits[0]
    project = capture_session([member.data], [fit], name="tcspc-display-binding")
    adapter_state = project.fits[0]["members"][0]["model"]["adapter_state"]
    assert adapter_state["scalars"]["period"] == pytest.approx(80.0)

    archive = save_file(project, tmp_path / "tcspc-display-binding.cs.pto")
    restored = restore_session(load_file(archive)).fits[0].grouped_fits[0].model
    assert restored.get_scalar("period") == pytest.approx(80.0)


def test_ics_timing_metadata_rows_are_declared_read_only_displays(qapp):
    """ICS scan timing is data metadata, not a stale scientific port."""
    import chisurf as cs
    from test.gui.test_ics_model_editor import _make_ics_fit

    fit = _make_ics_fit()
    cs.fits.append(fit)
    editor = build_model_editor(fit.model)
    editor.show()
    qapp.processEvents()
    try:
        live = {parameter.unique_identifier: parameter for parameter in fit.model.parameters_all}
        entries = _editor_bindings(editor, live)
        pixel_duration = _value_cell(entries, "pxl_dur")
        assert pixel_duration["display_binding"] == {
            "owner": "fit.data",
            "kind": "data_metadata",
            "path": "ics.pixel_duration_us",
            "editable": False,
        }
        timing_cells = [
            cell for entry in entries for cell in entry["cells"] if cell["name"] == "pxl_dur"
        ]
        assert not any(cell["editable"] for cell in timing_cells)
    finally:
        cs.fits.remove(fit)
        editor.close()


def test_general_fcs_inactive_preset_table_uses_canonical_document_inventory(qapp):
    """An inactive preset visible in AutoForm remains a real session-owned port."""
    import chisurf as cs
    from chisurf.core.fitting.fit import Fit
    from test.gui.scientific_document_gui_probe import _document_owned_parameter_index
    from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _data, _resolve

    entry = next(item for item in CATALOGUE if item["configured_path"].endswith(".GeneralFCSModel"))
    model_class = _resolve(entry["configured_path"])
    fit = Fit(data=_data(entry, model_class), model_class=model_class)
    fit.xmin, fit.xmax = 0, len(fit.data.y)
    fit.model.diffusion_mode = "species"
    fit.model.species.append()
    fit.model.update()
    inactive = fit.model.mdf_physical._D
    cs.fits.append(fit)
    editor = build_model_editor(fit.model)
    editor.show()
    qapp.processEvents()
    try:
        active = {parameter.unique_identifier: parameter for parameter in fit.model.parameters_all}
        assert inactive.unique_identifier not in active
        document_owned = _document_owned_parameter_index([fit])
        assert document_owned[inactive.unique_identifier] is inactive
        entries = _editor_bindings(editor, document_owned)
        cells = [cell for entry in entries for cell in entry["cells"]]
        assert any(cell["parameter_uid"] == inactive.unique_identifier for cell in cells)
    finally:
        cs.fits.remove(fit)
        editor.close()


def test_general_fcs_species_grid_exposes_active_document_port(qapp):
    """A non-table AutoForm field must retain exact active-port identity."""
    import chisurf as cs
    from chisurf.core.fitting.fit import Fit
    from test.gui.scientific_document_gui_probe import _document_owned_parameter_index
    from test.project.test_all_model_catalogue_roundtrip import CATALOGUE, _data, _resolve

    entry = next(item for item in CATALOGUE if item["configured_path"].endswith(".GeneralFCSModel"))
    model_class = _resolve(entry["configured_path"])
    fit = Fit(data=_data(entry, model_class), model_class=model_class)
    fit.xmin, fit.xmax = 0, len(fit.data.y)
    fit.model.diffusion_mode = "species"
    fit.model.species.append()
    fit.model.update()
    active = fit.model.species._N
    cs.fits.append(fit)
    editor = build_model_editor(fit.model)
    editor.show()
    qapp.processEvents()
    try:
        document_owned = _document_owned_parameter_index([fit])
        assert document_owned[active.unique_identifier] is active
        entries = _editor_bindings(editor, document_owned)
        cells = [cell for entry in entries for cell in entry["cells"]]
        control = next(
            cell
            for cell in cells
            if cell["parameter_uid"] == active.unique_identifier and cell["field"] == "value"
        )
        assert control["control"] == "FittingParameterWidget"
        assert control["editable"]
        assert control["edit_role"] == pytest.approx(float(active.value))
    finally:
        cs.fits.remove(fit)
        editor.close()


def test_maxent_generic_output_display_handles_an_absent_background_slot(qapp):
    """A read-only photon-count display cannot dereference an undeclared source."""
    import math

    import chisurf as cs
    from test.project.test_maxent_snapshot_contracts import _description_fit

    fit = _description_fit("tcspc_maxent_lifetime")
    model = fit.model
    assert not model.has_dataset("background_pattern")
    assert model.generic.background_curve is None
    cs.fits.append(fit)
    editor = build_model_editor(model)
    editor.show()
    qapp.processEvents()
    try:
        live = {parameter.unique_identifier: parameter for parameter in model.parameters_all}
        entries = _editor_bindings(editor, live)
        background_photons = _value_cell(entries, "PhB")
        assert background_photons["display_binding"] == {
            "owner": "model",
            "kind": "computed_output",
            "path": "generic.n_ph_bg",
            "editable": False,
        }
        assert math.isfinite(float(background_photons["edit_role"]))
    finally:
        cs.fits.remove(fit)
        editor.close()
