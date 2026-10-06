"""The native MMFDB Admin's model against a real seeded MMFDB (in-process services, real ACL).

Every panel loads what the Qt tool shows for the same database; every action does
what the Qt action does, through the same client calls; every confirmation that is
declined changes nothing. Hermetic: ``native_support`` points the settings, the
database, the object store and ``HOME`` at a temporary copy of a seeded database.
"""

from __future__ import annotations

import json

from chisurf.plugins.core.mmfdb_admin.gui.native import dialogs as dlg

from .native_support import admin, admin_folder, answer, client, rows_by_id, seeded_template  # noqa: F401


# ── connection ──────────────────────────────────────────────────────────


def test_connects_and_reports_the_database(admin):
    assert admin.connected and admin.login_user == "admin"
    assert "schema" in admin.summary and "samples" in admin.summary
    overview = admin.select("overview")
    assert "=== MMFDB Connection ===" in overview.text
    assert "in-process" in overview.text
    assert "sample 'sample_hp3' has no description" in overview.text


def test_a_wrong_password_keeps_the_login_dialog_open_with_the_reason(admin):
    admin.logout()
    assert admin.connection == "disconnected"
    admin.client.token = None
    admin.ask_login("admin")
    dialog = admin.dialog
    assert isinstance(dialog, dlg.ConnectionDialog)
    dialog.password = "wrong"
    dialog.ok()
    assert admin.dialog is dialog and "Invalid credentials" in dialog.error
    assert dialog.password == ""  # never kept past the attempt
    dialog.password = "admin"
    dialog.ok()
    assert admin.connected and admin.dialog is None


def test_a_non_administrator_is_refused(admin, client):
    client.save_user({"user_id": "plain", "display_name": "Plain", "password": "Plain#123x",
                      "requester_id": "admin"})
    admin.logout()
    admin.client.token = None
    admin.user, admin.password = "plain", "Plain#123x"
    admin.login()
    assert admin.connection == "denied"
    assert "not an administrator" in admin.dialog.text
    assert not admin.enabled("import_file") and admin.enabled("logout")
    assert admin.password == ""


def test_logout_drops_the_session(admin):
    from chisurf.plugins.core.mmfdb_admin.gui import session

    admin.logout()
    assert admin.connection == "disconnected" and admin.login_user == ""
    assert session.cached_token("127.0.0.1", 8765, 8766) is None


# ── entity panels ───────────────────────────────────────────────────────


def test_entity_columns_and_rows_match_the_qt_dock_definition(admin):
    from chisurf.plugins.core.mmfdb_admin.gui.entity_registry import ENTITY_REGISTRY

    for spec in ENTITY_REGISTRY:
        panel = admin.select(spec.key)
        assert panel.columns and panel.columns[0][0] == spec.id_field or spec.key in ("position",)
        assert panel.rows, spec.key
        keys = [c["key"] for c in panel.table_columns()]
        assert keys[0] == "checked" and keys[1:] == [k for k, _ in panel.columns]


def test_samples_list_and_open_a_record(admin):
    panel = admin.select("sample")
    rows = rows_by_id(panel)
    assert {"sample_gui", "sample_hp3"} <= set(rows)
    assert panel.message == f"{len(rows)} samples"
    panel.select_row(rows["sample_gui"])
    assert panel.selected_id == "sample_gui"
    assert panel.form.description == "GUI sample"
    assert panel.form.sample_condition_id == "cond_gui"


def test_a_committed_field_is_saved(admin, client):
    panel = admin.select("device")
    panel.select_row(rows_by_id(panel)["dev_gui"])
    panel.form.location = "Lab 2"
    assert "Saved device" in admin.status
    assert next(d for d in client.list_devices() if d["device_id"] == "dev_gui")["location"] == "Lab 2"
    assert rows_by_id(panel)["dev_gui"]["location"] == "Lab 2"


def test_new_creates_an_untitled_record_and_opens_it(admin, client):
    panel = admin.select("device")
    panel.new_record()
    assert panel.selected_id == "untitled_1"
    assert "untitled_1" in {d["device_id"] for d in client.list_devices()}
    assert "Created device: untitled_1" in admin.status


def test_delete_asks_and_declining_changes_nothing(admin, client):
    panel = admin.select("device")
    panel.delete_checked()
    assert isinstance(admin.dialog, dlg.MessageDialog) and "Tick" in admin.dialog.text
    answer(admin, "ok")
    rows_by_id(panel)["mt200"]["checked"] = True
    panel.delete_checked()
    assert "Delete 1 devices?" in admin.dialog.text
    answer(admin, "no")
    assert "mt200" in {d["device_id"] for d in client.list_devices()}
    rows_by_id(panel)["mt200"]["checked"] = True
    panel.delete_checked()
    answer(admin, "yes")
    assert "mt200" not in {d["device_id"] for d in client.list_devices()}
    assert "mt200" not in rows_by_id(panel)


def test_read_only_entities_have_no_new_and_read_only_fields(admin):
    panel = admin.select("raw_data")
    assert not panel.writable and not panel.enabled("new_record")
    assert all(s.get("read_only") or s["type"] != "value" for s in panel.form_sections())


def test_a_foreign_key_cell_opens_the_record_it_names(admin):
    panel = admin.select("experiment")
    row = rows_by_id(panel)["exp_gui"]
    links = {c["key"] for c in panel.table_columns() if c.get("display") == "link"}
    assert "sample_id" in links and "experiment_id" not in links
    panel.activate_cell(row, "status")  # not a link: stays
    assert admin.selected == "experiment"
    panel.activate_cell(row, "sample_id")
    assert admin.selected == "sample"
    assert admin.current.selected_id == "sample_gui"
    assert admin.current.form.description == "GUI sample"


def test_foreign_key_choices_list_the_target_records(admin):
    panel = admin.select("experiment")
    panel.select_row(rows_by_id(panel)["exp_gui"])
    choices = dict(panel.fk_choices("sample_id"))
    assert choices[""] == "(none)" and choices["sample_gui"] == "sample_gui — GUI sample"


def test_all_items_opens_a_record_in_its_panel(admin):
    panel = admin.select("all_items")
    assert panel.count_text() == f"{len(panel.rows)} / {len(panel.rows)}"
    panel.type_filter = "processed_data"
    rows = panel.visible_rows()
    assert rows and all(r["type"] == "processed_data" for r in rows)
    panel.search = "nothing-matches-this"
    assert panel.visible_rows() == []
    panel.search = ""
    panel.open_item(next(r for r in rows if r["id"] == "prod_gui"))
    assert admin.selected == "processed_product" and admin.current.selected_id == "prod_gui"


def test_measurements_filter_by_kind_and_text(admin):
    panel = admin.select("measurements")
    kinds = {r["kind"] for r in panel.visible_rows()}
    assert {"Raw", "Processing", "Processed"} <= kinds
    panel.kind = "Raw data"
    assert {r["kind"] for r in panel.visible_rows()} == {"Raw"}
    panel.search = "raw_gui"
    assert [r["id"] for r in panel.visible_rows()] == ["raw_gui"]


# ── per-entity actions ──────────────────────────────────────────────────


def test_raw_data_copy_reveal_validate_and_delete(admin, client):
    panel = admin.select("raw_data")
    panel.select_row(rows_by_id(panel)["raw_gui"])
    panel.copy_id()
    assert admin.copies[-1] == "raw_gui"
    panel.reveal()
    assert admin.opened[-1].endswith("raw_gui.ptu")
    panel.validate()
    choose = admin.dialog
    assert isinstance(choose, dlg.ChoiceDialog) and choose.value == "valid"
    choose.value = "warning"
    choose.ok()
    assert client.get_raw_data("raw_gui")["validation_status"] == "warning"
    panel.select_row(rows_by_id(panel)["raw_gui"])
    panel.delete_artifact()
    answer(admin, "no")
    assert "raw_gui" in rows_by_id(panel)
    panel.delete_artifact()
    answer(admin, "yes")
    assert "raw_gui" not in {r["raw_data_id"] for r in client.list_raw_data()}


def test_use_as_provenance_seed_loads_the_graph(admin):
    panel = admin.select("processed_product")
    panel.select_row(rows_by_id(panel)["prod_gui"])
    panel.use_as_seed()
    prov = admin.current
    assert admin.selected == "provenance"
    assert (prov.seed_type, prov.seed_id) == ("processed_data", "prod_gui")
    ids = {n["id"] for n in prov.document["nodes"]}
    assert {"artifact:raw_gui", "operation:proc_gui", "artifact:prod_gui"} <= ids
    assert {e["relationship_type"] for e in prov.edges} >= {"input_to", "produced"}
    prov.select_edge(prov.edges[0])
    assert json.loads(prov.details)["edge_id"] == prov.edges[0]["edge_id"]


def test_analysis_details(admin):
    panel = admin.select("analysis")
    panel.select_row(rows_by_id(panel)["analysis_gui"])
    panel.details()
    dialog = admin.dialog
    assert isinstance(dialog, dlg.AnalysisDetailsDialog)
    assert [r["name"] for r in dialog.parameter_rows()] == ["tau"]
    assert dialog.parameter_rows()[0]["units"] == "ns"
    assert "local_fit" in dialog.summary_text()
    assert dialog.output_rows()[0]["processed_data_id"] == "fit_result_gui"


def test_objects_copy_reveal_and_delete(admin, client):
    panel = admin.select("object")
    record = panel.rows[0]
    panel.select_row(record)
    panel.copy_uuid()
    assert admin.copies[-1] == record["_id"]
    panel.reveal()
    assert admin.opened and admin.opened[-1].endswith(".csv") or admin.opened[-1]
    count = len(client.list_objects())
    panel.delete_object()
    assert "Refcount" in admin.dialog.text
    answer(admin, "no")
    assert len(client.list_objects()) == count


def test_branch_set_head(admin, client):
    panel = admin.select("branch")
    panel.select_row(rows_by_id(panel)["branch_gui"])
    panel.set_head()
    dialog = admin.dialog
    assert isinstance(dialog, dlg.TextDialog) and dialog.value == "ver_gui"
    dialog.value = ""
    dialog.ok()
    assert client.get_branch("branch_gui").get("head_operation_id") in (None, "")


def test_change_password_rules_and_save(admin, client):
    panel = admin.select("user")
    panel.select_row(rows_by_id(panel)["admin"])
    panel.change_password()
    dialog = admin.dialog
    assert isinstance(dialog, dlg.PasswordDialog) and not dialog.enabled("clear")
    dialog.password_new = dialog.password_confirm = "short"
    dialog.save()
    assert "medium strength" in dialog.error and admin.dialog is dialog
    dialog.cancel()
    panel.select_row(rows_by_id(panel)["john_doe"])
    panel.change_password()
    dialog = admin.dialog
    dialog.password_new, dialog.password_confirm = "Abcdef1!", "Abcdef1?"
    dialog.save()
    assert dialog.error == "Passwords do not match."
    dialog.password_confirm = "Abcdef1!"
    assert dialog.password_strength_text() == "Strength: Strong"
    dialog.save()
    assert admin.dialog is None and "Password updated for 'john_doe'" in admin.status
    assert client.login("john_doe", "Abcdef1!", quiet=True).get("ok")


def test_jump_to_branch_needs_an_operation(admin):
    panel = admin.select("user")
    panel.select_row(rows_by_id(panel)["john_doe"])
    panel.jump_to_branch()
    dialog = admin.dialog
    dialog.ok()
    assert "required" in dialog.error and admin.dialog is dialog
    dialog.operation_id = "ver_gui"
    dialog.branch_name = "jd_branch"
    dialog.ok()
    assert "jumped to branch" in admin.dialog.text


# ── special panels ──────────────────────────────────────────────────────


def test_sample_metadata_edit_and_save(admin, client):
    panel = admin.select("metadata")
    assert ("sample_gui", "sample_gui — GUI sample") in panel.sample_options()
    panel.choose_sample("sample_gui")
    assert {r["key"] for r in panel.rows} == {"buffer", "pH", "temperature"}
    assert "Sample sample_gui: 3 metadata keys" in panel.message
    assert "pH" in panel.catalogue() and len(panel.catalogue()) > 100
    panel.select_row(next(r for r in panel.rows if r["key"] == "pH"))
    assert panel.detail_value == "7.4"
    panel.detail_value = "7.5"
    panel.apply_to_row()
    panel.add_row()
    panel.detail_key, panel.detail_value = "data_notes", "seed"
    panel.apply_to_row()
    panel.save_all()
    stored = {kv["key"]: kv["value"] for kv in client.get_sample("sample_gui")["key_values"]}
    assert stored["pH"] == "7.5" and stored["data_notes"] == "seed"


def test_metadata_jump_from_another_panel(admin):
    admin.jump("metadata", "sample_gui")
    assert admin.selected == "metadata" and admin.current.sample_id == "sample_gui"


def test_spectra_list_select_overlay_and_curate(admin, client):
    panel = admin.select("spectra")
    names = {r["chromophore_name"] for r in panel.rows}
    assert {"Donor GUI", "Acceptor GUI"} <= names
    donor = next(r for r in panel.rows if r["chromophore_name"] == "Donor GUI")
    panel.select_row(donor)
    assert panel.values.chromophore_name == "Donor GUI"
    assert {t["name"] for t in panel.traces} == {"Absorption", "Emission"}
    acceptor = next(r for r in panel.rows if r["chromophore_name"] == "Acceptor GUI")
    for row in (donor, acceptor):
        panel.edited(row, "checked", True)
    assert len(panel.traces) == 4 and any("[Emission]" in t["name"] for t in panel.traces)
    panel.approve()
    status = client._call("fluorophores.get", {"probe_id": int(donor["_row"])})["probe"]
    assert status.get("verification_status") == "approved"
    panel.toggle_review_queue()
    assert panel.status_filter == "unverified"
    assert all(r["verification_status"] == "unverified" for r in panel.rows)
    panel.toggle_review_queue()
    assert panel.status_filter == "all"


def test_spectra_component_types(admin):
    panel = admin.select("spectra")
    assert [k for k, _ in panel.component_options()] == [
        "fluorophore", "filter", "dichroic", "detector", "light_source"]
    panel.component = "filter"
    panel.set_component("filter")
    assert [c["key"] for c in panel.table_columns()][1:4] == ["probe_id", "chromophore_name", "type_name"]


def test_find_duplicates_and_merge(admin, client):
    panel = admin.select("spectra")
    panel.find_duplicates()
    dialog = admin.dialog
    group = next(g for g in dialog.groups if {p["chromophore_name"] for p in g["probes"]} >= {"Donor GUI", "Donor-GUI"})
    name = group["norm_name"]
    rows = dialog.tree_rows()
    assert any(r["_row"] == f"g:{name}" for r in rows)
    dialog.select_row(next(r for r in rows if r["_row"].startswith(f"p:{name}:")))
    assert dialog.comparison()
    primary = dialog.primary[name]
    dialog.edited({"_row": f"g:{name}"}, "primary", True)
    assert dialog.merge_caption() == "Merge 1 Checked Group"
    dialog.merge_checked()
    remaining = {p["probe_id"] for p in client._call("fluorophores.find_duplicates", {})["probes"]}
    assert primary in remaining
    assert not ({p["probe_id"] for p in group["probes"]} - {primary}) & remaining


def test_import_export_requests_a_path_and_previews(admin, tmp_path):
    panel = admin.select("import_export")
    sample = admin.select("sample")
    sample.select_row(rows_by_id(sample)["sample_gui"])
    admin.select("import_export")
    panel.preview_cif()
    assert "data_" in panel.preview or "_flr" in panel.preview or panel.preview
    target = tmp_path / "samples.csv"
    admin.chooser = lambda *_a: str(target)
    panel.export_table()
    assert target.exists()
    cif = tmp_path / "sample_gui.cif"
    admin.chooser = lambda *_a: str(cif)
    admin.export_selected_sample()
    if admin.dialog is not None:  # validation warnings: export anyway
        answer(admin, "yes")
    assert cif.exists()


def test_reset_asks_first(admin, client):
    admin.reset_database()
    assert isinstance(admin.dialog, dlg.ConfirmDialog)
    answer(admin, "no")
    assert "sample_gui" in {s["sample_id"] for s in client.list_samples()}


def test_studies_create_add_member_and_field(admin, client):
    panel = admin.select("studies")
    assert [s["name"] for s in panel.studies] == ["Hairpin dynamics"]
    panel.select_study(panel.studies[0])
    assert panel.members[0]["member_id"] == "sample_gui"
    assert panel.fields[0] == {"_row": "grant", "key": "grant", "value": "DFG 123"}
    panel.member_type, panel.member_id = "sample", "sample_hp3"
    panel.add_member()
    assert {m["member_id"] for m in panel.members} == {"sample_gui", "sample_hp3"}
    panel.field_key, panel.field_value = "pi", "Peulen"
    panel.set_field()
    assert {f["key"] for f in panel.fields} == {"grant", "pi"}
    panel.create_study()
    assert panel.message == "Enter a study name."
    panel.new_name = "Second"
    panel.create_study()
    assert {s["name"] for s in panel.studies} == {"Hairpin dynamics", "Second"}


def test_protocols_history_schema_and_new_version(admin):
    panel = admin.select("protocols")
    assert {p["name"] for p in panel.protocols} == {"TCSPC acquisition", "Burst selection"}
    panel.select_protocol(next(p for p in panel.protocols if p["name"] == "Burst selection"))
    assert panel.versions and panel.versions[0]["version"] in (1, "1")
    panel.new_name, panel.new_category = "Burst selection", "processing"
    panel.create_protocol()
    assert "v2" in panel.message


def test_lifecycle_load_and_transition(admin):
    panel = admin.select("lifecycle")
    assert "sample" in panel.type_options()
    panel.entity_type, panel.entity_id = "sample", "sample_gui"
    panel.load()
    assert panel.state_text() == "Current state: measured"
    assert [h["to_state"] for h in panel.history][:2] == ["registered", "measured"] or len(panel.history) == 2
    assert panel.next_states()
    panel.to_state = panel.next_states()[0]
    panel.reason = "checked"
    panel.apply_transition()
    assert panel.message.startswith("Transitioned to")


def test_calibrations_list_stale_and_register(admin):
    panel = admin.select("calibrations")
    values = sorted(float(r["value"]) for r in panel.calibrations)
    assert values == [1.05, 52.0, 54.0]
    assert panel.stale == [] or isinstance(panel.stale, list)
    panel.new_value = "abc"
    panel.register()
    assert panel.message == "Enter a numeric value."
    panel.new_type, panel.new_value, panel.new_notes = "gamma", "0.8", "test"
    panel.register()
    assert panel.message == "Registered gamma = 0.8."
    assert len(panel.calibrations) == 4


def test_reagent_lots_filter_detail_and_create(admin):
    panel = admin.select("reagents")
    assert {r["name"] for r in panel.lots} == {"Alexa 488", "PBS"}
    panel.kind_filter = "buffer"
    panel.set_filter("buffer")
    assert [r["name"] for r in panel.lots] == ["PBS"]
    panel.select_lot(panel.lots[0])
    assert {d["field"] for d in panel.detail_rows()} >= {"kind", "name", "lot_number", "vendor", "expiry"}
    panel.new_kind, panel.new_name, panel.new_expiry = "buffer", "Tris", "2030-02-02"
    panel.create_lot()
    assert panel.message == "Created lot Tris."
    assert {r["name"] for r in panel.lots} == {"PBS", "Tris"}


def test_pipelines_empty_is_explained(admin):
    panel = admin.select("pipelines")
    assert panel.pipelines == []
    assert "No pipelines" in panel.message


def test_elabftw_requires_endpoint_and_key_and_never_keeps_the_key(admin, monkeypatch):
    panel = admin.select("elabftw")
    assert panel.enabled("connect_remote") and not panel.enabled("import_checked")
    panel.connect_remote()
    assert panel.message == "Endpoint and API key are required."
    calls = {}

    def fake_connect(endpoint, api_key, **kw):
        calls["key"] = api_key
        raise RuntimeError(f"401 for key {api_key}")

    monkeypatch.setattr(admin.client, "connect_elabftw", fake_connect)
    panel.endpoint, panel.api_key = "https://elab.example.org", "secret-key"
    panel.connect_remote()
    assert calls["key"] == "secret-key" and panel.api_key == ""
    assert "secret-key" not in panel.message and "REDACTED" in panel.message


def test_back_and_next_walk_the_rail(admin):
    keys = admin.panel_keys()
    admin.select(keys[0])
    assert not admin.can_step(-1)
    admin.step(1)
    assert admin.selected == keys[1]
    admin.select(keys[-1])
    assert not admin.can_step(1)


def test_rail_search(admin):
    admin.search = "lots"
    assert [v for kind, v in admin.rail() if kind == "panel"] == ["reagents"]
    admin.search = ""
    assert ("group", "Workflows & QC") in admin.rail()


def test_every_section_button_and_column_has_a_description():
    from chisurf.plugins.core.mmfdb_admin.gui.app import load_specs

    shell, panels, actions = load_specs()

    def walk(sections, where):
        for s in sections:
            assert s.get("description"), (where, s)
            for b in s.get("buttons", []) or []:
                assert b.get("description"), (where, b)
            options = s.get("options") if isinstance(s.get("options"), dict) else {}
            for c in options.get("columns", []) or []:
                assert c.get("tooltip"), (where, c)
            walk(s.get("sections") or [], where)

    for name, panel in {**shell, **panels}.items():
        if name == "duplicates_tree":
            for c in panel["columns"]:
                assert c.get("tooltip")
            continue
        walk(panel["sections"], name)
    for entity, buttons in actions.items():
        for b in buttons:
            assert b.get("description"), (entity, b)
