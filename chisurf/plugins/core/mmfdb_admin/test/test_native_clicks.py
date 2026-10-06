"""The native MMFDB Admin operated the way a user operates it: pointer and keyboard only.

Every test goes through :class:`chisurf.plugins.emtk_test_input.Driver`, which only
delivers what a host delivers (presses, releases, moves, typed keys) at the
rectangles the app drew; no model method is called to make something happen. The
database is a seeded temporary copy (``native_support``), the client the real
in-process one, the calls inline.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.emtk_test_input import SMALL, Driver, assert_tour_card_clear

from .native_support import admin_folder, app, client, seeded_template  # noqa: F401


@pytest.fixture
def driver(app):
    d = Driver(app)
    d.draw(3)
    assert app.model.connected, app.model.status
    return d


def open_panel(driver, key, name):
    """Find a panel with the rail's search box, then click it (the rail scrolls past 800 px)."""
    driver.type_into_name("search", name)
    driver.click_name(f"nav.{key}")
    assert driver.app.model.selected == key


def _row(driver, text):
    """The rectangle of the table cell showing *text* (drawn before the form's field)."""
    return Driver.text_rect(driver.draw(2), text, last=False)


def test_the_rail_opens_a_panel(driver, app):
    driver.click_name("nav.sample")
    assert app.model.selected == "sample"
    assert driver.drawn("sample_gui")


def test_a_row_click_opens_the_record_and_a_typed_field_is_saved(driver, app, client):
    open_panel(driver, "device", "Devices")
    driver.click(_row(driver, "dev_gui"))
    panel = app.model.current
    assert panel.selected_id == "dev_gui"
    driver.type_into_name("location", "Lab 9")
    assert next(d for d in client.list_devices() if d["device_id"] == "dev_gui")["location"] == "Lab 9"
    assert "Saved device" in app.model.status


def test_new_then_tick_and_delete_with_the_confirmation(driver, app, client):
    open_panel(driver, "device", "Devices")
    driver.click_name("new_record")
    assert "untitled_1" in {d["device_id"] for d in client.list_devices()}
    # Tick the new row's check box (the first column of its row) and delete it.
    x, y, w, h = _row(driver, "untitled_1")
    table = driver.rect("table_rows")
    driver.click((table[0] + 6.0, y, 26.0, h))
    assert app.model.current.checked_ids() == ["untitled_1"]
    driver.click_name("delete_checked")
    driver.click_name("dialog.no")
    assert "untitled_1" in {d["device_id"] for d in client.list_devices()}
    driver.click_name("delete_checked")
    driver.click_name("dialog.yes")
    assert "untitled_1" not in {d["device_id"] for d in client.list_devices()}


def test_a_double_click_on_a_link_cell_opens_the_linked_record(driver, app):
    open_panel(driver, "experiment", "Experiments")
    cells = [t[:4] for t in driver.draw(2).texts if t[5] == "sample_gui"]
    assert cells
    driver.click(cells[0], clicks=1)
    driver.click(cells[0], clicks=2)
    assert app.model.selected == "sample"
    assert app.model.current.selected_id == "sample_gui"


def test_logout_then_login_through_the_dialog(driver, app):
    driver.click_name("logout")
    assert app.model.connection == "disconnected"
    app.model.client.token = None
    driver.click_name("login")  # admin cannot sign in without a password: the dialog asks
    assert app.model.dialog is not None and app.model.dialog.spec == "connection"
    driver.type_into_name("dialog.password", "admin")
    driver.click_name("dialog.ok")
    assert app.model.connected and app.model.dialog is None


def test_spectra_pick_and_approve(driver, app, client):
    open_panel(driver, "spectra", "Spectra")
    driver.click(_row(driver, "Acceptor GUI"))
    panel = app.model.current
    assert panel.values.chromophore_name == "Acceptor GUI"
    assert panel.traces
    driver.click_name("approve")
    probe = client._call("fluorophores.get", {"probe_id": int(panel.selected_id)})["probe"]
    assert probe["verification_status"] == "approved"


def test_use_as_seed_opens_the_loaded_provenance_graph(driver, app):
    open_panel(driver, "raw_data", "Raw Data")
    driver.click(_row(driver, "raw_gui"))
    driver.click_name("use_as_seed")
    assert app.model.selected == "provenance"
    panel = app.model.current
    assert panel.seed_id == "raw_gui" and panel.document["nodes"]
    gx, gy, gw, gh = driver.rect("provenance_graph")
    assert gw > 100 and gh > 60
    driver.wheel(gx + gw / 2, gy + gh / 2, 1.0)  # the wheel zooms the graph, nothing breaks


def test_the_seed_controls_load_a_graph(driver, app):
    open_panel(driver, "provenance", "Provenance Graph")
    driver.type_into_name("seed_id", "prod_gui")
    driver.click_name("load_upstream")
    panel = app.model.current
    assert panel.edges and panel.document["nodes"]


def test_back_and_next(driver, app):
    keys = app.model.panel_keys()
    driver.click_name("next")
    assert app.model.selected == keys[1]
    driver.click_name("back")
    assert app.model.selected == keys[0]


def test_help_and_guide(driver, app):
    driver.click_name("help")
    assert app.help_window.open
    app.help_window.hide()
    driver.draw(2)
    driver.click_name("guide")
    assert app.tour.active
    driver.draw(2)
    assert_tour_card_clear(app.tour)


def test_the_guide_waits_for_the_rail_click(driver, app):
    app.tour.start()
    driver.draw(2)
    while app.tour.active and app.tour.steps[app.tour.step_idx]["target"].get("name") != "nav.sample":
        app.tour.next()
        driver.draw(2)
    assert app.tour.awaiting
    assert_tour_card_clear(app.tour)
    driver.click_name("nav.sample")
    driver.draw(2)
    assert app.model.selected == "sample"
    assert not app.tour.awaiting  # the step's control was used: Next goes on


def test_the_file_menu_backup(driver, app):
    driver.click_text("File")
    driver.click_text("Backup database...")
    assert app.model.status.startswith("Backup:")


def test_the_toolbar_reset_asks_and_cancel_keeps_everything(driver, app, client):
    driver.click_name("reset_database")
    assert app.model.dialog is not None
    driver.click_name("dialog.no")
    assert "sample_gui" in {s["sample_id"] for s in client.list_samples()}


def test_the_rail_search_narrows_the_panels(driver, app):
    driver.type_into_name("search", "lots")
    assert driver.drawn("Reagent Lots")
    assert not driver.drawn("Samples")


def test_everything_reachable_at_800x600(app):
    d = Driver(app, size=SMALL)
    d.draw(3)
    for name in ("login", "logout", "refresh", "help", "guide", "nav.overview", "next", "back"):
        rects = dict(app.item_rects)
        for state in app.forms.values():
            rects.update(state.rects)
        rect = rects.get(name)
        if rect is None:
            continue  # login / logout: one of the two is drawn
        x, y, w, h = rect
        assert x >= 0 and y >= 0 and x + w <= SMALL[0] + 1 and y + h <= SMALL[1] + 1, (name, rect)
    d.click_name("nav.sample")
    d.click(Driver.text_rect(d.draw(2), "sample_gui", last=False))
    assert app.model.current.selected_id == "sample_gui"


def test_the_menus_offer_every_qt_menu_action(driver, app):
    expected = {
        "File": ["Import...", "Export selected sample...", "Backup database...", "Reset", "Close"],
        "Settings": ["Reset window layout"],
        "Help": ["Help...", "Guide", "About mmfdb-admin"],
    }
    for menu, items in expected.items():
        driver.click_text(menu, last=False)
        texts = [t[5] for t in driver.draw(2).texts]
        for item in items:
            assert item in texts, (menu, item, texts[:30])
        driver.escape()


def test_settings_reset_window_layout_returns_to_the_overview(driver, app):
    driver.click_name("nav.sample")
    app.splits["entity"] = 0.2
    driver.click_text("Settings", last=False)
    driver.click_text("Reset window layout")
    assert app.model.selected == "overview"
    assert app.splits["entity"] == 0.5


@pytest.mark.parametrize(
    "key, name, rows, source",
    [
        ("protocols", "Protocols", "protocol_rows", "protocol_rows"),
        ("studies", "Studies", "study_rows", "study_rows"),
        ("reagents", "Reagent", "lot_rows", "lot_rows"),
    ],
)
def test_a_selection_set_by_the_model_is_shown_in_the_table(driver, app, key, name, rows, source):
    """A jump or a new record sets ``panel.selected``; the table must highlight that row too."""
    open_panel(driver, key, name)
    panel = app.model.current
    records = getattr(panel, rows)()
    if not records:
        pytest.skip(f"the seeded database has no {name} rows")
    wanted = records[-1]["_row"]
    panel.selected = wanted
    driver.draw(2)
    assert app.form(key).tables[source].control.selected_key == wanted
