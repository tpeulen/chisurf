"""The Studies panel of the native MMFDB Admin (ported from the Qt ``StudiesView`` tests).

List studies, show a study's members and fields on a row click, and create one -- through
the emtk Driver over a seeded temporary MMFDB.
"""

from __future__ import annotations

from chisurf.plugins.emtk_test_input import Driver

from .native_support import (  # noqa: F401
    admin_folder,
    app,
    client,
    driver,
    open_panel,
    seeded_template,
)


def test_view_lists_studies(driver, app, client):  # noqa: F811
    client.create_study("Alpha")
    client.create_study("Beta")
    panel = open_panel(driver, "studies", "Studies")
    assert {"Alpha", "Beta"} <= {s["name"] for s in panel.studies}
    assert driver.drawn("Beta")


def test_view_shows_members_and_fields_on_select(driver, app, client):  # noqa: F811
    sid = client.create_study("Gamma")["study_id"]
    client.add_study_member(sid, "sample", "s1")
    client.set_study_field(sid, "grant", "NIH-9")
    panel = open_panel(driver, "studies", "Studies")
    driver.click(Driver.text_rect(driver.draw(2), "Gamma", last=False))
    assert panel.selected == sid
    assert [m["member_id"] for m in panel.members] == ["s1"]
    assert [f["key"] for f in panel.fields] == ["grant"]
    assert driver.drawn("NIH-9")


def test_view_create_adds_study(driver, app):  # noqa: F811
    panel = open_panel(driver, "studies", "Studies")
    driver.type_into_name("new_name", "Delta")
    driver.click_name("create_study")
    assert "Delta" in {s["name"] for s in panel.studies}
    assert panel.message == "Created study Delta."
