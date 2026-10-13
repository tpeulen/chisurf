"""MMFDB Admin entity panels driven with real sample data (ported from the Qt ``EntityDock`` tests).

Each test opens a panel from the rail, picks a seeded row, edits a field (typed and
committed through the emtk Driver: the auto-save), creates, ticks and deletes records,
and runs the per-entity actions (copy, reveal, validate, delete, details, provenance
seed), then reads the database directly to see that the change landed. The database is a
seeded temporary copy (``native_support``); the client the real in-process one.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.plugins.core.mmfdb_admin.gui.native import dialogs as dlg
from chisurf.plugins.emtk_test_input import Driver

from .native_support import (  # noqa: F401
    admin_folder,
    answer,
    app,
    client,
    database,
    driver,
    open_panel,
    seeded_template,
)


def _select(driver, panel, record_id: str) -> dict:  # noqa: F811
    """Click the row showing *record_id* (or jump to it when the id is not a unique text)."""
    texts = [t for t in driver.draw(2).texts if t[5] == record_id]
    if texts:
        driver.click(texts[0][:4])
    else:
        panel.jump_to(record_id)
    driver.draw(2)
    assert panel.selected_id == record_id
    data = panel.form.data()
    assert data
    return data


def _type(driver, panel, attr: str, text: str) -> None:  # noqa: F811
    """Type *text* into the form field *attr* and commit it as a user does.

    A single-line field commits on Enter; a multi-line one (``kind: "text"``) takes Enter
    as a new line and commits when the pointer goes down elsewhere.
    """
    section = next(s for s in panel.form_sections() if s.get("attr") == attr)
    if section.get("kind") == "text":
        driver.type_into_name(attr, text, commit=False)
        driver.click_name("status")
    else:
        driver.type_into_name(attr, text)


def _tick_and_delete(driver, panel, record_id: str) -> None:  # noqa: F811
    for row in panel.rows:
        row["checked"] = row["_id"] == record_id
    driver.click_name("delete_checked")
    driver.click_name("dialog.yes")


def _curve_object(panel) -> str:
    """The id of the seeded ``sample_curve.csv`` object (the seed stores others too)."""
    return next(r["_id"] for r in panel.rows if r.get("original_filename") == "sample_curve.csv")


def _copies(app):  # noqa: F811
    copied: list[str] = []
    app.model.copy = copied.append
    return copied


def test_sample_entity_dock_selects_and_auto_saves_sample(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "sample", "Samples")
    assert _select(driver, panel, "sample_gui")["description"] == "GUI sample"
    _type(driver, panel, "description", "GUI sample updated")
    assert database.get_sample("sample_gui")["description"] == "GUI sample updated"


def test_entity_probe_position_and_fret_pair_docks_browse_and_save_seeded_data(
    driver,  # noqa: F811
    app,  # noqa: F811
    database,  # noqa: F811
):
    panel = open_panel(driver, "entity", "Entities")
    assert _select(driver, panel, "entity_gui")["entity_id"] == "entity_gui"

    donor_id = str(
        database.conn.execute(
            "SELECT probe_id FROM probes WHERE chromophore_name = ?", ("Donor GUI",)
        ).fetchone()["probe_id"]
    )
    panel = open_panel(driver, "probe", "Probes")
    assert _select(driver, panel, donor_id)["chromophore_name"] == "Donor GUI"
    _type(driver, panel, "description", "GUI donor updated")

    position_id = str(
        database.conn.execute(
            "SELECT id FROM flr_poly_probe_position WHERE auth_name = ?", ("C2",)
        ).fetchone()["id"]
    )
    panel = open_panel(driver, "position", "Label Positions")
    data = _select(driver, panel, position_id)
    assert data["entity_id"] == "entity_gui" and data["auth_name"] == "C2"

    panel = open_panel(driver, "fret_pair", "FRET Pairs")
    data = _select(driver, panel, "fr_gui")
    assert data["sample_id"] == "sample_gui"
    assert str(data["donor_probe_id"]) == donor_id

    donor = database.conn.execute(
        "SELECT description FROM probes WHERE chromophore_name = ?", ("Donor GUI",)
    ).fetchone()
    assert donor["description"] == "GUI donor updated"


def test_sample_metadata_dock_loads_edits_and_saves_metadata(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "metadata", "Sample Metadata")
    panel.sample_id = "sample_gui"
    panel.choose_sample("sample_gui")
    driver.draw(2)
    assert len(panel.rows) == 3  # buffer, pH, temperature
    driver.click(Driver.text_rect(driver.draw(2), "initial buffer", last=False))
    assert panel.detail_key == "buffer"
    driver.type_into_name("detail_value", "HEPES")
    driver.type_into_name("detail_details", "edited buffer")
    driver.click_name("apply_to_row")
    driver.click_name("save_all")
    values = {row["key"]: row for row in database.get_sample_key_values("sample_gui")}
    assert values["buffer"]["value"] == "HEPES"
    assert values["buffer"]["details"] == "edited buffer"


def test_experiment_entity_dock_selects_and_auto_saves_status(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "experiment", "Experiments")
    assert _select(driver, panel, "exp_gui")["sample_id"] == "sample_gui"
    panel.form.status = "reviewed"  # the status choice committed
    assert dict(database.get_experiment("exp_gui"))["status"] == "reviewed"


def test_condition_device_experiment_type_and_setup_docks_auto_save(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "condition", "Sample Conditions")
    assert _select(driver, panel, "cond_gui")["buffer_composition"] == "PBS"
    _type(driver, panel, "ph", "7.8")

    panel = open_panel(driver, "device", "Devices")
    assert _select(driver, panel, "dev_gui")["name"] == "GUI Detector"
    _type(driver, panel, "model", "GUI-Model")

    type_id = str(
        next(t for t in database.get_experiment_types() if t["name"] == "TCSPC")["type_id"]
    )
    panel = open_panel(driver, "experiment_type", "Experiment Types")
    panel.jump_to(type_id)
    driver.draw(2)
    assert panel.form.data()["name"] == "TCSPC"
    _type(driver, panel, "description", "GUI experiment type")

    panel = open_panel(driver, "setup", "Setups")
    assert _select(driver, panel, "setup_gui")["name"] == "GUI Setup"
    _type(driver, panel, "details", "updated setup")

    condition = database.conn.execute(
        "SELECT ph FROM flr_sample_condition WHERE condition_id = ?", ("cond_gui",)
    ).fetchone()
    assert condition["ph"] == 7.8
    assert next(d for d in database.get_devices() if d["device_id"] == "dev_gui")["model"] == (
        "GUI-Model"
    )
    tcspc = next(t for t in database.get_experiment_types() if t["name"] == "TCSPC")
    assert tcspc["description"] == "GUI experiment type"
    assert "updated setup" in database.get_setup("setup_gui")["configuration_json"]


def test_condition_and_device_docks_create_update_and_delete_records(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "condition", "Sample Conditions")
    count = len(panel.rows)
    driver.click_name("new_record")
    condition_id = panel.selected_id
    assert condition_id and len(panel.rows) == count + 1
    _type(driver, panel, "ph", "6.9")
    row = database.conn.execute(
        "SELECT ph FROM flr_sample_condition WHERE condition_id = ? AND deleted_at IS NULL",
        (condition_id,),
    ).fetchone()
    assert row["ph"] == 6.9
    _tick_and_delete(driver, panel, condition_id)
    assert (
        database.conn.execute(
            "SELECT 1 FROM flr_sample_condition WHERE condition_id = ? AND deleted_at IS NULL",
            (condition_id,),
        ).fetchone()
        is None
    )

    panel = open_panel(driver, "device", "Devices")
    count = len(panel.rows)
    driver.click_name("new_record")
    device_id = panel.selected_id
    assert device_id and len(panel.rows) == count + 1
    _type(driver, panel, "name", "GUI Created Device")
    row = database.conn.execute(
        "SELECT name FROM flr_sample_devices WHERE device_id = ? AND deleted_at IS NULL",
        (device_id,),
    ).fetchone()
    assert row["name"] == "GUI Created Device"
    _tick_and_delete(driver, panel, device_id)
    assert (
        database.conn.execute(
            "SELECT 1 FROM flr_sample_devices WHERE device_id = ? AND deleted_at IS NULL",
            (device_id,),
        ).fetchone()
        is None
    )


def test_experiment_type_dock_creates_updates_and_deletes_type(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "experiment_type", "Experiment Types")
    count = len(panel.rows)
    driver.click_name("new_record")
    type_id = panel.selected_id
    assert type_id and len(panel.rows) == count + 1
    created = database.conn.execute(
        "SELECT * FROM flr_experiment_type WHERE type_id = ? AND deleted_at IS NULL",
        (int(type_id),),
    ).fetchone()
    assert created is not None and created["name"].startswith("untitled_experiment_type_")
    _type(driver, panel, "description", "created and updated from GUI")
    updated = database.conn.execute(
        "SELECT description FROM flr_experiment_type WHERE type_id = ? AND deleted_at IS NULL",
        (int(type_id),),
    ).fetchone()
    assert updated["description"] == "created and updated from GUI"
    _tick_and_delete(driver, panel, type_id)
    assert (
        database.conn.execute(
            "SELECT 1 FROM flr_experiment_type WHERE type_id = ? AND deleted_at IS NULL",
            (int(type_id),),
        ).fetchone()
        is None
    )


def test_setup_child_docks_browse_seeded_detector_pie_and_fcs_rows(driver, app):  # noqa: F811
    panel = open_panel(driver, "detector_channel", "Detector Channels")
    assert len(panel.rows) == 1
    data = _select(driver, panel, panel.rows[0]["_id"])
    assert data["setup_id"] == "setup_gui" and data["name"] == "green"
    assert "0" in str(data["channels"])

    panel = open_panel(driver, "pie_window", "PIE Windows")
    assert len(panel.rows) == 1
    data = _select(driver, panel, panel.rows[0]["_id"])
    assert data["setup_id"] == "setup_gui" and data["name"] == "donor_excitation"
    assert int(data["start"]) == 10 and int(data["end"]) == 90

    panel = open_panel(driver, "fcs_pair", "FCS Pairs")
    assert len(panel.rows) == 1
    data = _select(driver, panel, panel.rows[0]["_id"])
    assert data["setup_id"] == "setup_gui" and data["name"] == "green_auto"
    assert data["channel_a"] == "green" and data["channel_b"] == "green"


def test_user_entity_dock_selects_and_auto_saves_display_name(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "user", "Users")
    stored = {row["user_id"]: row for row in database.get_users()}["user_default"]
    assert _select(driver, panel, "user_default")["display_name"] == stored["display_name"]
    _type(driver, panel, "display_name", "GUI Default User")
    users = {row["user_id"]: row for row in database.get_users()}
    assert users["user_default"]["display_name"] == "GUI Default User"


def test_user_entity_dock_creates_renames_and_deletes_user(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "user", "Users")
    count = len(panel.rows)
    driver.click_name("new_record")
    created_id = panel.selected_id
    assert created_id
    users = {row["user_id"]: row for row in database.get_users()}
    assert users[created_id]["display_name"] == created_id
    _type(driver, panel, "display_name", "GUI Created User")
    panel.form.user_id = "gui_created_user"  # the id committed in the form: a rename
    users = {row["user_id"]: row for row in database.get_users()}
    assert created_id not in users
    assert users["gui_created_user"]["display_name"] == "GUI Created User"
    assert len(panel.rows) == count + 1
    assert panel.selected_id == "gui_created_user"
    _tick_and_delete(driver, panel, "gui_created_user")
    assert "gui_created_user" not in {row["user_id"] for row in database.get_users()}


def test_user_entity_dock_prevents_builtin_user_delete(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "user", "Users")
    _select(driver, panel, "user_default")
    _tick_and_delete(driver, panel, "user_default")
    warning = app.model.dialog
    assert isinstance(warning, dlg.MessageDialog)
    assert "built-in user" in warning.text
    assert "user_default" in {row["user_id"] for row in database.get_users()}


def test_object_project_and_branch_entity_docks_browse_seeded_data(driver, app):  # noqa: F811
    panel = open_panel(driver, "object", "Objects")
    curve = _curve_object(panel)
    assert _select(driver, panel, curve)["original_filename"] == "sample_curve.csv"

    panel = open_panel(driver, "project", "Projects")
    assert _select(driver, panel, "proj_gui")["name"] == "GUI Project"

    panel = open_panel(driver, "branch", "Branches")
    assert _select(driver, panel, "branch_gui")["name"] == "gui_branch"


def test_object_entity_dock_copies_reveals_and_deletes_seeded_object(driver, app, database):  # noqa: F811
    copied = _copies(app)
    panel = open_panel(driver, "object", "Objects")
    count = len(panel.rows)
    object_id = _curve_object(panel)
    data = _select(driver, panel, object_id)
    assert data["original_filename"] == "sample_curve.csv"
    assert data.get("storage_path") is None  # the server's path is never shown

    driver.click_name("x_copy_uuid") if "x_copy_uuid" in app.item_rects else panel.copy_uuid()
    assert copied[-1] == object_id

    driver.click_name("reveal")
    revealed = Path(app.model.opened[-1])
    assert revealed.name.endswith("sample_curve.csv")
    assert revealed.read_bytes() == b"time,intensity\n0,10\n"

    driver.click_name("delete_object")
    driver.click_name("dialog.yes")
    assert database.get_object_info(object_id) is None
    assert len(panel.rows) == count - 1
    assert object_id not in {r["_id"] for r in panel.rows}
    assert "Object delete result" in panel.message


def test_branch_entity_dock_creates_updates_and_deletes_branch(driver, app, database):  # noqa: F811
    panel = open_panel(driver, "branch", "Branches")
    count = len(panel.rows)
    driver.click_name("new_record")
    created_id = panel.selected_id
    assert created_id and len(panel.rows) == count + 1
    assert database.get_branch(created_id)["name"].startswith("untitled_branch_")
    _type(driver, panel, "description", "created and updated from GUI")
    assert database.get_branch(created_id)["description"] == "created and updated from GUI"
    _tick_and_delete(driver, panel, created_id)
    assert database.get_branch(created_id) is None


def test_data_product_and_analysis_entity_docks_browse_seeded_data(driver, app):  # noqa: F811
    panel = open_panel(driver, "raw_data", "Raw Data")
    data = _select(driver, panel, "raw_gui")
    assert data["experiment_id"] == "exp_gui" and data["data_type"] == "tcspc"

    panel = open_panel(driver, "processing_run", "Processing Runs")
    data = _select(driver, panel, "proc_gui")
    assert data["experiment_id"] == "exp_gui" and data["type"] == "filtering"

    panel = open_panel(driver, "processed_product", "Processed Products")
    data = _select(driver, panel, "prod_gui")
    assert data["processing_id"] == "proc_gui" and data["product_type"] == "processed_data"

    panel = open_panel(driver, "analysis", "Analyses")
    data = _select(driver, panel, "analysis_gui")
    assert data["experiment_id"] == "exp_gui" and data["model_name"] == "GUI Fit"


def test_data_product_and_analysis_entity_dock_actions_use_seeded_data(driver, app):  # noqa: F811
    copied = _copies(app)
    model = app.model

    panel = open_panel(driver, "raw_data", "Raw Data")
    for name in ("copy_id", "reveal", "use_as_seed", "validate", "delete_artifact"):
        assert name in app.form("entity:raw_data").rects, name
    assert _select(driver, panel, "raw_gui")["location"].endswith("raw_gui.ptu")
    driver.click_name("copy_id")
    assert copied[-1] == "raw_gui"
    driver.click_name("reveal")
    assert model.opened[-1].endswith("raw_gui.ptu")
    driver.click_name("use_as_seed")
    prov = model.current
    assert model.selected == "provenance"
    assert (prov.seed_type, prov.seed_id) == ("raw_data", "raw_gui")

    panel = open_panel(driver, "processed_product", "Processed Products")
    assert _select(driver, panel, "prod_gui")["location"].endswith("prod_gui.json")
    driver.click_name("copy_id")
    assert copied[-1] == "prod_gui"
    driver.click_name("reveal")
    assert model.opened[-1].endswith("prod_gui.json")
    driver.click_name("use_as_seed")
    assert (model.current.seed_type, model.current.seed_id) == ("processed_data", "prod_gui")

    panel = open_panel(driver, "analysis", "Analyses")
    for name in ("copy_id", "details", "use_as_seed"):
        assert name in app.form("entity:analysis").rects, name
    _select(driver, panel, "analysis_gui")
    driver.click_name("copy_id")
    assert copied[-1] == "analysis_gui"
    driver.click_name("details")
    details = model.dialog
    assert isinstance(details, dlg.AnalysisDetailsDialog)
    params = details.parameter_rows()
    assert len(params) == 1 and params[0]["name"] == "tau" and float(params[0]["value"]) == 3.8
    assert details.input_rows() == []
    outputs = details.output_rows()
    assert len(outputs) == 1
    assert "fit_result_gui" in outputs[0].values() and "valid" in outputs[0].values()
    assert driver.drawn("tau")
    details.close_dialog()
    driver.click_name("use_as_seed")
    assert (model.current.seed_type, model.current.seed_id) == ("analysis_run", "analysis_gui")


def test_raw_and_processed_entity_dock_validate_and_delete_seeded_artifacts(
    driver,  # noqa: F811
    app,  # noqa: F811
    database,  # noqa: F811
):
    panel = open_panel(driver, "raw_data", "Raw Data")
    _select(driver, panel, "raw_gui")
    driver.click_name("validate")
    choice = app.model.dialog
    assert isinstance(choice, dlg.ChoiceDialog)
    choice.value = "warning" if "warning" in choice.options else choice.options[-1]
    status = choice.value
    choice.ok()
    assert database.get_artifact("raw_gui")["validation_status"] == status
    assert f"validation set to {status}" in panel.message

    driver.click_name("delete_artifact")
    driver.click_name("dialog.yes")
    assert database.get_artifact("raw_gui")["deleted_at"] is not None
    assert panel.rows == []
    link = database.conn.execute(
        "SELECT deleted_at FROM mmfdb_operation_artifact "
        "WHERE operation_id = 'proc_gui' AND artifact_id = 'raw_gui'"
    ).fetchone()
    assert link["deleted_at"] is not None

    panel = open_panel(driver, "processed_product", "Processed Products")
    _select(driver, panel, "prod_gui")
    driver.click_name("validate")
    choice = app.model.dialog
    choice.value = "invalid"
    choice.ok()
    assert database.get_artifact("prod_gui")["validation_status"] == "invalid"
    assert "validation set to invalid" in panel.message

    driver.click_name("delete_artifact")
    driver.click_name("dialog.yes")
    assert database.get_artifact("prod_gui")["deleted_at"] is not None
    visible = {r["_id"] for r in panel.rows} | {
        str(r.get("processed_data_id", "")) for r in panel.rows
    }
    assert "prod_gui" not in visible
    assert "fit_result_gui" in visible
    link = database.conn.execute(
        "SELECT deleted_at FROM mmfdb_operation_artifact "
        "WHERE operation_id = 'proc_gui' AND artifact_id = 'prod_gui'"
    ).fetchone()
    assert link["deleted_at"] is not None


def test_measurements_panel_refreshes_and_filters_seeded_data(driver, app):  # noqa: F811
    panel = open_panel(driver, "measurements", "Measurements")
    rows = {(r["kind"], r["id"]) for r in panel.visible_rows()}
    assert {
        ("Raw", "raw_gui"),
        ("Processing", "proc_gui"),
        ("Processed", "prod_gui"),
        ("Processed", "fit_result_gui"),
    } <= rows
    assert panel.status_line() == f"Measurements: {len(panel.visible_rows())} rows"
    panel.kind = "Raw data"
    assert [(r["kind"], r["id"]) for r in panel.visible_rows()] == [("Raw", "raw_gui")]
    panel.kind = "All"
    panel.search = "prod_gui"
    assert [(r["kind"], r["id"]) for r in panel.visible_rows()] == [("Processed", "prod_gui")]


def test_provenance_graph_loads_seeded_processing_graph(driver, app):  # noqa: F811
    app.model.provenance_seed("processed_data", "prod_gui")
    driver.draw(2)
    panel = app.model.current
    assert (panel.seed_type, panel.seed_id) == ("processed_data", "prod_gui")
    assert len(panel.edges) == 2
    edges = {
        (
            e["source_node_type"],
            e["source_node_id"],
            e["relationship_type"],
            e["target_node_type"],
            e["target_node_id"],
        )
        for e in panel.edges
    }
    assert ("artifact", "raw_gui", "input_to", "operation", "proc_gui") in edges
    assert ("operation", "proc_gui", "produced", "artifact", "prod_gui") in edges
    assert {n["id"] for n in panel.document["nodes"]} == {
        "artifact:prod_gui",
        "artifact:raw_gui",
        "operation:proc_gui",
    }
    assert len(panel.document["edges"]) == 2
    assert {n.id for n in app.graph.document.nodes} == {n["id"] for n in panel.document["nodes"]}
    panel.select_edge(panel.edges[0])
    assert "relationship_type" in panel.details and "proc_gui" in panel.details


def test_import_export_panel_validates_previews_and_exports_seeded_sample(
    driver,  # noqa: F811
    app,  # noqa: F811
    database,  # noqa: F811
    tmp_path,  # noqa: F811
):
    model = app.model
    open_panel(driver, "sample", "Samples")
    _select(driver, model.current, "sample_gui")
    sample_path = tmp_path / "sample_gui.cif"
    table_path = tmp_path / "samples.csv"
    paths = iter([str(sample_path), str(table_path)])
    model.chooser = lambda *a: next(paths)

    panel = open_panel(driver, "import_export", "Import / Export")
    driver.click_name("preview_cif")
    assert panel.message == "CIF preview for sample_gui"

    driver.click_name("export_selected_sample")
    if model.dialog is not None:  # the export was validated: warnings ask first
        assert isinstance(model.dialog, dlg.ConfirmDialog)
        assert "issues were found" in model.dialog.text
        driver.click_name("dialog.yes")
    assert sample_path.exists()
    assert model.status == f"Exported {sample_path}"

    driver.click_name("export_table")
    assert table_path.exists()
    assert panel.message == f"Exported {table_path}"
    assert "sample_gui" in table_path.read_text(encoding="utf-8")

    import_path = tmp_path / "gui_import_sample.cif"
    import_path.write_text("data_gui_import_sample\n#\n", encoding="utf-8")
    driver.type_into_name("path", str(import_path))
    assert panel.path == str(import_path)
    # The panel's Import file; the toolbar's Import is the same action name in another
    # form -- they shared one widget id and this press did nothing until emtk 0.1.12.
    driver.click(app.form("import_export").rects["import_file"])
    assert panel.message == "Imported gui_import_sample.cif."
    assert database.get_sample("gui_import_sample") is not None
    assert "gui_import_sample" in panel.preview
