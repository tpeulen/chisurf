"""The experiment-data sub-table, Validate setup, project Restore/Delete version and the row
helpers of the native MMFDB Admin, operated by pointer only (scratch MMFDB, see native_support)."""

from __future__ import annotations

import sqlite3

import pytest

from chisurf.plugins.emtk_test_input import Driver

from .native_support import admin_folder, app, client, seeded_template  # noqa: F401


@pytest.fixture
def driver(app):
    d = Driver(app)
    d.draw(3)
    assert app.model.connected, app.model.status
    return d


def open_panel(driver, key, name):
    driver.type_into_name("search", name)
    driver.click_name(f"nav.{key}")
    assert driver.app.model.selected == key
    driver.draw(2)


def _row(driver, text):
    return Driver.text_rect(driver.draw(2), text, last=False)


def _versions(client, project_id):
    return [p for p in client._call("mmfdb.projects.list", None)["projects"]
            if p["project_id"] == project_id]


def _save_versions(client):
    from chisurf.core.project import capture_session
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    pb = ProjectBrowserClient(mmfdb_client=client)
    payload = capture_session([], [], name="Arch").to_dict()
    v1 = pb.save_project("Arch", payload, notes="first")
    p2 = dict(payload, ui={"marker": "second"})
    v2 = pb.save_project(
        "Arch", p2, project_id=v1["project_id"], parent_version_id=v1["version_id"], notes="second"
    )
    return v1, v2


def test_experiment_data_subtable_lists_adds_saves_and_deletes(driver, app, client, tmp_path):
    client.save_experiment_data(
        {"experiment_id": "exp_gui", "data_type": "tttr", "storage_mode": "link",
         "file_path": "/tmp/seed.ptu"}
    )
    open_panel(driver, "experiment", "Experiments")
    driver.click(_row(driver, "exp_gui"))
    panel = app.model.current
    assert [r["data_type"] for r in panel.data_rows] == ["tttr"]
    assert driver.drawn("/tmp/seed.ptu")  # the sub-table shows the linked data
    # Add a row, give it a type through its cell, save it.
    driver.click_name("x_data_add")
    assert len(panel.data_rows) == 2
    new = panel.data_rows[-1]
    new["data_type"] = "irf"
    new["location"] = str(tmp_path / "irf.txt")
    driver.click_name("x_data_save")
    stored = client.get_experiment("exp_gui")["data"]
    assert sorted(d["data_type"] for d in stored) == ["irf", "tttr"]
    assert len(panel.data_rows) == 2
    # Delete one: asks first.
    panel.data_selected = str(next(r for r in panel.data_rows if r["data_type"] == "irf")["_id"])
    driver.click_name("x_data_delete")
    driver.click_name("dialog.no")
    assert len(client.get_experiment("exp_gui")["data"]) == 2
    driver.click_name("x_data_delete")
    driver.click_name("dialog.yes")
    assert [d["data_type"] for d in client.get_experiment("exp_gui")["data"]] == ["tttr"]


def test_data_save_refuses_a_row_without_type(driver, app, client):
    open_panel(driver, "experiment", "Experiments")
    driver.click(_row(driver, "exp_gui"))
    driver.click_name("x_data_add")
    driver.click_name("x_data_save")
    assert "Data type is required" in app.model.status
    assert client.get_experiment("exp_gui")["data"] == []


def test_validate_setup_reports_a_known_bad_setup(driver, app, client, admin_folder):
    open_panel(driver, "setup", "Setups")
    driver.click(_row(driver, "setup_gui"))
    driver.click_name("x_validate_setup")
    assert "Validation OK" in app.model.current.validation_text
    # A setup the server accepted but that is no longer valid: blank its name in the store.
    con = sqlite3.connect(str(admin_folder / "mmfdb.db"))
    con.execute("UPDATE mmfdb_setup SET name='' WHERE setup_id='setup_gui'")
    con.commit()
    con.close()
    driver.click_name("x_validate_setup")
    assert "Validation FAIL" in app.model.current.validation_text
    assert "name is required" in app.model.current.validation_text
    assert driver.drawn("Validation FAIL: name is required")


def test_restore_returns_the_archived_version_content(driver, app, client):
    v1, v2 = _save_versions(client)
    app.model.restored = []
    app.model.restorer = lambda pid, vid, payload: app.model.restored.append((pid, vid, payload))
    open_panel(driver, "project", "Projects")
    driver.click(_row(driver, "Arch"))
    panel = app.model.current
    assert {r["version_id"] for r in panel.version_rows} == {v1["version_id"], v2["version_id"]}
    first = next(r for r in panel.version_rows if r["version_id"] == v1["version_id"])
    driver.click(_row(driver, v1["version_id"]))
    assert panel.version_selected == first["version_id"]
    driver.click_name("x_restore_version")
    (pid, vid, payload), = app.model.restored
    assert vid == v1["version_id"] and pid == v1["project_id"]
    assert payload["project_payload"] == v1["project_payload"]  # content equal
    assert payload["project_payload"]["ui"] != v2["project_payload"]["ui"]


def test_delete_archived_version_removes_only_the_chosen_one(driver, app, client):
    v1, v2 = _save_versions(client)
    open_panel(driver, "project", "Projects")
    driver.click(_row(driver, "Arch"))
    driver.click(_row(driver, v1["version_id"]))
    driver.click_name("x_delete_version")
    driver.click_name("dialog.no")
    assert len(_versions(client, v1["project_id"])) == 2
    driver.click_name("x_delete_version")
    driver.click_name("dialog.yes")
    left = {p["version_id"] for p in _versions(client, v1["project_id"])}
    assert left == {v2["version_id"]}
    restored = client.restore_project(v2["version_id"])
    assert restored["project_payload"] == v2["project_payload"]  # the other is intact


def test_row_helpers_copy_and_tick(driver, app):
    copied = []
    original = app.model.copy
    app.model.copy = lambda text: (copied.append(str(text)), original(text))
    open_panel(driver, "device", "Devices")
    driver.click(_row(driver, "dev_gui"))
    driver.click_name("x_copy_row")
    assert "dev_gui" in copied[-1] and "\t" in copied[-1]
    driver.click_name("x_check_all")
    n = len(app.model.current.rows)
    assert len(app.model.current.checked_ids()) == n
    driver.click_name("x_copy_checked")
    assert copied[-1].splitlines() == app.model.current.checked_ids()
    driver.click_name("x_invert_checks")
    assert app.model.current.checked_ids() == []
    driver.click_name("x_check_all")
    driver.click_name("x_uncheck_all")
    assert app.model.current.checked_ids() == []
