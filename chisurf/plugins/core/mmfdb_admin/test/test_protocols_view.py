"""The Protocols panel of the native MMFDB Admin (ported from the Qt ``ProtocolsView`` tests).

List the latest version per name, show a protocol's history and the parameter schema of
its operation type on a row click, and create one -- through the emtk Driver over a seeded
temporary MMFDB.
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


def test_view_lists_latest_protocols(driver, app, client):  # noqa: F811
    client.create_protocol("acq", "measurement", operation_type="measurement_import")
    client.create_protocol("acq", "measurement", operation_type="measurement_import")
    panel = open_panel(driver, "protocols", "Protocols")
    acq = [p for p in panel.protocols if p["name"] == "acq"]
    assert len(acq) == 1  # latest per name
    assert str(acq[0]["version"]) == "2"


def test_view_shows_versions_and_schema_on_select(driver, app, client):  # noqa: F811
    client.create_protocol("burst", "processing", operation_type="burst_selection")
    client.create_protocol("burst", "processing", operation_type="burst_selection")
    panel = open_panel(driver, "protocols", "Protocols")
    driver.click(Driver.text_rect(driver.draw(2), "burst", last=False))
    assert panel.selected == "burst"
    assert len(panel.versions) == 2
    assert "min_photons" in {r["name"] for r in panel.schema}
    assert driver.drawn("min_photons")


def test_view_create_adds_protocol(driver, app):  # noqa: F811
    panel = open_panel(driver, "protocols", "Protocols")
    driver.type_into_name("new_name", "new_proto")
    panel.new_category = "analysis"
    driver.click_name("create_protocol")
    assert panel.message == "Created new_proto v1."
    assert "new_proto" in {p["name"] for p in panel.protocols}
