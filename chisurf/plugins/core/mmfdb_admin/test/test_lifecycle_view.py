"""The Lifecycle panel of the native MMFDB Admin (ported from the Qt ``LifecycleView`` tests).

Load the definitions, show an entity's state and history, drive a transition and surface an
illegal jump -- typed and pressed through the emtk Driver over a seeded temporary MMFDB.
"""

from __future__ import annotations

from .native_support import (  # noqa: F401
    admin_folder,
    app,
    client,
    driver,
    open_panel,
    seeded_template,
)


def _load(driver, entity_type: str, entity_id: str):  # noqa: F811
    panel = open_panel(driver, "lifecycle", "Lifecycle")
    panel.entity_type = entity_type
    driver.type_into_name("entity_id", entity_id)
    driver.click_name("load")
    driver.draw(2)
    return panel


def test_view_constructs_and_loads_definitions(driver, app):  # noqa: F811
    panel = open_panel(driver, "lifecycle", "Lifecycle")
    assert {"sample", "artifact", "operation"} <= set(panel.type_options())


def test_view_refresh_shows_state_and_next_states(driver, app, client):  # noqa: F811
    client.lifecycle_transition("sample", "s1", "registered")
    panel = _load(driver, "sample", "s1")
    assert panel.state_text() == "Current state: registered"
    assert driver.drawn("Current state: registered")
    assert "measured" in panel.next_states()  # registered -> measured is the legal next step
    assert len(panel.history) == 1


def test_view_apply_transition_advances_state(driver, app, client):  # noqa: F811
    client.lifecycle_transition("sample", "s2", "registered")
    panel = _load(driver, "sample", "s2")
    panel.to_state = "measured"
    driver.click_name("apply_transition")
    assert panel.state_text() == "Current state: measured"
    assert panel.message == "Transitioned to measured."
    assert len(panel.history) == 2


def test_view_surfaces_illegal_transition(driver, app, client):  # noqa: F811
    client.lifecycle_transition("sample", "s3", "registered")
    panel = _load(driver, "sample", "s3")
    panel.to_state = "archived"  # a target the choice would not offer
    driver.click_name("apply_transition")
    assert panel.message.startswith("Rejected")
    assert panel.state_text() == "Current state: registered"
