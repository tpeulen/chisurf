"""Navigation of the native MMFDB Admin (ported from the Qt ``MMFDBWidget`` navigation tests).

The rail flattens the entity panels under group headings, surfaces the workflow views,
the Spectra curation and eLabFTW, gives every entry a pictogram, builds every panel, and
the Overview reports the connection mode and the database type. The app runs over a seeded
temporary MMFDB with the real in-process services.
"""

from __future__ import annotations

from chisurf.plugins.core.mmfdb_admin.gui.native import panels as native_panels
from chisurf.plugins.core.mmfdb_admin.gui.native.entity import EntityPanel
from chisurf.plugins.core.mmfdb_admin.gui.native.spectra import SpectraPanel

from .native_support import (  # noqa: F401
    admin_folder,
    app,
    client,
    driver,
    open_panel,
    seeded_template,
)


def test_the_window_is_a_rail_and_a_panel(driver, app):  # noqa: F811
    assert "search" in app.item_rects and "nav.overview" in app.item_rects
    driver.click_name("nav.sample")
    assert app.model.selected == "sample" and driver.drawn("sample_gui")


def test_panels_flattened_with_group_headings_and_views(app):  # noqa: F811
    model = app.model
    rail = model.rail()
    names = [model.panel_name(v) for kind, v in rail if kind == "panel"]
    for n in ("Overview", "All items", "Measurements"):
        assert n in names
    assert sum(1 for kind, _ in rail if kind == "group") >= 4
    assert sum(1 for kind, v in rail if kind == "panel" and v in model.registry) >= 15
    for n in ("Studies", "Protocols", "Lifecycle", "Calibrations", "Reagent Lots", "Pipelines"):
        assert n in names
    assert "Spectra" in names and "eLabFTW" in names
    # every rail entry and heading carries a pictogram
    assert all(model.panel_icon(v) for _kind, v in rail)


def test_the_rail_draws_the_pictograms(driver, app):  # noqa: F811
    strings = " ".join(driver.draw(2).strings)
    # a heading carries its pictogram in its text; an entry draws it in a slot of its own
    assert app.model.panel_icon("Samples & chemistry") in strings


def test_fluorophore_panel_and_rpc_integrated(driver, app):  # noqa: F811
    panel = open_panel(driver, "spectra", "Spectra")
    assert isinstance(panel, SpectraPanel)
    res = app.model.client._call("fluorophores.list", {"limit": 1})
    assert "probes" in res and "total" in res


def test_every_panel_builds(driver, app):  # noqa: F811
    for key in app.model.panel_keys():
        app.model.select(key)
        driver.draw(2)
        assert driver.drawn(app.model.panel_name(key)), key


def test_entity_panels_are_generated_from_the_dictionary(driver, app):  # noqa: F811
    panel = open_panel(driver, "sample", "Samples")
    assert isinstance(panel, EntityPanel)
    sections = panel.form_sections()
    assert {s.get("attr") for s in sections} >= {"sample_id", "description"}


def test_overview_shows_connection_mode_and_database_type(driver, app):  # noqa: F811
    panel = open_panel(driver, "overview", "Overview")
    text = panel.overview()
    assert "Mode:" in text
    assert "embedded" in text  # in-process (embedded, no socket)
    assert "SQLite" in text
    assert "Object store:" in text
    assert "=== MMFDB Connection ===" in " ".join(driver.draw(2).strings)


def test_connection_labels_reflect_remote_mode():
    class Remote:
        mode = "remote"
        inprocess = False
        base_url = "http://mmfdb.example.org:8080"

    assert "remote" in native_panels.connection_mode_label(Remote())
    assert native_panels.connection_endpoint_label(Remote()) == "http://mmfdb.example.org:8080"
    assert native_panels.database_type_label({"database_dialect": "postgresql"}) == "PostgreSQL"
