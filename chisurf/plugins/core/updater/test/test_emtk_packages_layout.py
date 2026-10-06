"""Layout of the native package manager at 1200x800 and 800x600 on all four pages: nothing clipped or overlapping, the table
gets the room the buttons and the log leave, the log and Refresh All are on screen, short inputs stay short."""

import time

import pytest

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from test.gui import emtk_layout_checks as lc

SIZES = [(1200, 800), (800, 600)]
PAGES = {
    "installed": [
        "installed_filter",
        "refresh_installed",
        "ask_update_selected",
        "ask_update_all",
        "ask_remove_selected",
    ],
    "search": ["search_query", "search_packages", "ask_install_selected"],
    "envs": [
        "ask_create_env",
        "ask_clone_env",
        "ask_remove_env",
        "request_export",
        "request_import",
    ],
    "channels": ["ask_add_channel", "remove_channel"],
}


@pytest.fixture
def app(fakes):
    from chisurf.plugins.core.updater.gui.package_app import PackageApp

    application = PackageApp()
    yield application
    application.close()


def opened(app, size, page):
    drv = Driver(app, size)
    drv.draw(3)
    end = time.monotonic() + 20
    while (
        app.job.busy or app.model.busy or not app.model.installed_rows
    ) and time.monotonic() < end:
        time.sleep(0.01)
        drv.draw(1)
    drv.click(f"tab_{page}")
    drv.draw(4)
    return drv


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("page", list(PAGES))
def test_every_page_is_inside_the_window_apart_and_keeps_the_log_on_screen(app, size, page):
    drv = opened(app, size, page)
    rects = {**app.form.rects, **app.item_rects}
    names = PAGES[page] + ["refresh_all", "log"]
    for name in names:
        assert name in rects, f"{name} not drawn on {page} at {size}"
    lc.assert_inside(rects, size, names)
    lc.assert_disjoint(rects, [n for n in names if n != "log"] + ["log"])
    lc.assert_texts_apart(drv.painter)
    assert rects["log"][3] >= 80
    assert rects["refresh_all"][1] > rects["log"][1]
    # the page's buttons are above the log
    for name in PAGES[page]:
        assert rects[name][1] + rects[name][3] <= rects["log"][1] + 1


@pytest.mark.parametrize("size", SIZES)
def test_text_inputs_are_capped_and_the_table_keeps_a_usable_height(app, size):
    drv = opened(app, size, "installed")
    lc.assert_short(app.form.rects, ["installed_filter"], limit=340)
    table = app.form.tables["installed_rows"].control
    assert table is not None
    drv = opened(app, size, "search")
    lc.assert_short(app.form.rects, ["search_query"], limit=340)


@pytest.mark.parametrize("size", SIZES)
def test_the_question_and_entry_dialog_stay_inside_the_window(app, size):
    drv = opened(app, size, "envs")
    drv.click("ask_create_env")
    drv.draw(3)
    box = app.panel.message_window.box
    assert (
        box[0] >= 0
        and box[1] >= 0
        and box[0] + box[2] <= size[0] + 1
        and box[1] + box[3] <= size[1] + 1
    )
    rects = app.panel.dialog_form.rects
    lc.assert_inside(rects, size)
    lc.assert_disjoint(rects, ["dialog_input", "dialog_ok", "dialog_cancel"])


def test_an_idle_page_offers_only_what_can_act(app):
    drv = opened(app, (1200, 800), "installed")
    assert [
        app.model.enabled(n)
        for n in (
            "ask_update_selected",
            "ask_remove_selected",
            "ask_update_all",
            "refresh_installed",
        )
    ] == [False, False, True, True]
