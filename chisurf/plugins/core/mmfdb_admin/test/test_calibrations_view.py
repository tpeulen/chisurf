"""The Calibrations panel of the native MMFDB Admin (ported from the Qt ``CalibrationsView`` tests).

The app runs over a seeded temporary MMFDB (``native_support``) with the real in-process
services; values are typed and Register is pressed through the emtk Driver.
"""

from __future__ import annotations

from mmfdb.lifecycle.staleness import record_calibration_use

from .native_support import (  # noqa: F401
    admin_folder,
    app,
    client,
    database,
    driver,
    open_panel,
    seeded_template,
)


def _types(panel) -> set[str]:
    return {r["calibration_type"] for r in panel.calibrations}


def test_view_lists_calibrations(driver, app, client):  # noqa: F811
    client.create_calibration("gamma", 0.9)
    panel = open_panel(driver, "calibrations", "Calibrations")
    assert _types(panel) == {"forster_radius", "g_factor", "gamma"}
    assert driver.drawn("gamma")


def test_view_create_adds_calibration(driver, app):  # noqa: F811
    panel = open_panel(driver, "calibrations", "Calibrations")
    panel.new_type = "forster_radius"
    driver.type_into_name("new_value", "54.5")
    driver.type_into_name("new_notes", "Hellenkamp 2018")
    driver.click_name("register")
    assert panel.message == "Registered forster_radius = 54.5."
    assert 54.5 in {float(r["value"]) for r in panel.calibrations}
    assert driver.drawn("Hellenkamp 2018")


def test_view_rejects_non_numeric_value(driver, app):  # noqa: F811
    panel = open_panel(driver, "calibrations", "Calibrations")
    before = len(panel.calibrations)
    driver.type_into_name("new_value", "not-a-number")
    driver.click_name("register")
    assert panel.message == "Enter a numeric value."
    assert len(panel.calibrations) == before


def test_view_shows_stale_uses(driver, app, client, database):  # noqa: F811
    old = client.create_calibration("gamma", 1.02)["artifact_id"]
    record_calibration_use(
        database, used_by_id="fit-1", calibration_artifact_id=old, used_by_type="artifact"
    )
    client.create_calibration("gamma", 1.05)  # supersedes
    panel = open_panel(driver, "calibrations", "Calibrations")
    stale = [r for r in panel.stale if r["used_by_id"] == "fit-1"]
    assert len(stale) == 1 and stale[0]["calibration_type"] == "gamma"
    assert driver.drawn("fit-1")
