"""The Reagent Lots panel of the native MMFDB Admin (ported from the Qt ``ReagentLotsView`` tests).

List lots, filter by kind, show expired lots on request, show a lot's details on a row
click, create a lot and refuse a blank name -- through the emtk Driver over a seeded
temporary MMFDB (which holds the lots ``Alexa 488`` and ``PBS``).
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


def _names(panel) -> set[str]:
    return {r["name"] for r in panel.lots}


def test_view_lists_lots(driver, app):  # noqa: F811
    panel = open_panel(driver, "reagents", "Reagent Lots")
    assert _names(panel) == {"Alexa 488", "PBS"}
    assert driver.drawn("Alexa 488")


def test_view_kind_filter(driver, app):  # noqa: F811
    panel = open_panel(driver, "reagents", "Reagent Lots")
    panel.kind_filter = "buffer"
    panel.set_filter("buffer")  # the choice's call
    assert _names(panel) == {"PBS"}


def test_view_show_expired_toggle(driver, app, client):  # noqa: F811
    client.create_reagent_lot("buffer", "fresh", expiry="2999-01-01")
    client.create_reagent_lot("buffer", "old", expiry="2000-01-01")
    panel = open_panel(driver, "reagents", "Reagent Lots")
    assert "fresh" in _names(panel) and "old" not in _names(panel)  # expired hidden by default
    driver.click_name("show_expired")
    assert panel.show_expired
    assert {"fresh", "old"} <= _names(panel)


def test_view_select_shows_detail(driver, app, client):  # noqa: F811
    client.create_reagent_lot("fluorophore", "Cy3", lot_number="L-7", vendor="GE")
    panel = open_panel(driver, "reagents", "Reagent Lots")
    driver.click(Driver.text_rect(driver.draw(2), "Cy3", last=False))
    detail = {r["field"]: r["value"] for r in panel.detail_rows()}
    assert detail["name"] == "Cy3"
    assert detail["lot_number"] == "L-7"
    assert detail["vendor"] == "GE"
    assert driver.drawn("L-7")


def test_view_create_adds_lot(driver, app):  # noqa: F811
    panel = open_panel(driver, "reagents", "Reagent Lots")
    panel.new_kind = "kit"
    driver.type_into_name("new_name", "Click-iT kit")
    driver.type_into_name("new_lot_number", "K-99")
    driver.click_name("create_lot")
    assert "Click-iT kit" in _names(panel)
    assert panel.message == "Created lot Click-iT kit."


def test_view_create_rejects_blank_name(driver, app):  # noqa: F811
    panel = open_panel(driver, "reagents", "Reagent Lots")
    driver.type_into_name("new_name", "   ")
    driver.click_name("create_lot")
    assert panel.message == "Enter a lot name."
    assert _names(panel) == {"Alexa 488", "PBS"}
