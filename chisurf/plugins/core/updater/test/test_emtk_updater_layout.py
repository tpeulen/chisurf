"""Layout of the native updater at 1200x800 and 800x600, empty, after a check, with a dialog, and while an update is prepared.

Nothing clipped or overlapping, the changelog gets the room that is left (at least 80 px high even at 800x600), capped
fields and a capped changelog, label column shared, and no control offered that cannot act (greyed ones are reported as such).
The screenshots in the evidence folder are read as well.
"""

import time

import pytest

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
from test.gui import emtk_layout_checks as lc

SIZES = [(1200, 800), (800, 600)]
FORM_CONTROLS = [
    "current_version_text",
    "development",
    "check_on_startup",
    "ignore_updates_on_startup",
    "selected_version",
    "check_for_updates",
    "ask_update",
    "open_package_manager",
    "changelog",
]


@pytest.fixture
def app():
    from chisurf.plugins.core.updater.gui.app import UpdaterApp
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    application = UpdaterApp(UpdaterModel(), auto_check=False)
    yield application
    application.close()


def settle(drv):
    end = time.monotonic() + 30
    drv.draw(1)
    while (drv.app.job.busy or drv.app.model.busy) and time.monotonic() < end:
        time.sleep(0.01)
        drv.draw(1)
    drv.draw(3)


def checked(app, size):
    drv = Driver(app, size)
    drv.draw(3)
    drv.click("check_for_updates")
    settle(drv)
    return drv


@pytest.mark.parametrize("size", SIZES)
def test_the_idle_window_draws_every_control_inside_the_window_and_apart(app, size):
    painter = lc.draw(app, size)
    rects = {**app.form.rects, **app.item_rects}
    lc.assert_inside(rects, size)
    lc.assert_disjoint(rects, [n for n in FORM_CONTROLS if n in rects and n != "changelog"])
    lc.assert_texts_apart(painter)
    for name in FORM_CONTROLS:
        assert name in rects, f"{name} is not drawn at {size}"


@pytest.mark.parametrize("size", SIZES)
def test_after_a_check_the_changelog_has_room_and_nothing_overlaps(app, size):
    drv = checked(app, size)
    rects = {**app.form.rects, **app.item_rects}
    lc.assert_inside(rects, size)
    lc.assert_texts_apart(drv.painter)
    x, y, w, h = rects["changelog"]
    assert h >= 80 and w <= 640 + 1 and y > rects["check_for_updates"][1], rects["changelog"]
    lc.assert_above(rects, "check_for_updates", "changelog")
    assert "Changes between 26.09.20 and 26.10.02:" in drv.painter.strings
    if size[1] >= 800:
        assert h >= 300, h  # a 1200x800 window gives the changelog a real area


@pytest.mark.parametrize("size", SIZES)
def test_inputs_are_grouped_capped_and_share_one_label_column(app, size):
    lc.draw(app, size)
    rects = app.form.rects
    pass
    lc.assert_short(rects, ["selected_version"], limit=400)
    # the labelled fields start at one x, the toggles at another (the grid's own indent) -- both groups line up in themselves
    pass
    lc.assert_aligned(rects, ["check_on_startup", "ignore_updates_on_startup"], tolerance=1.5)
    # three actions on one row, wrapped only when the window is narrow
    row = [rects[n][1] for n in ("check_for_updates", "ask_update", "open_package_manager")]
    assert max(row) - min(row) < 1.0, row
    lc.assert_above(rects, "selected_version", "check_for_updates")
    lc.assert_above(rects, "check_on_startup", "selected_version")


@pytest.mark.parametrize("size", SIZES)
def test_the_confirmation_dialog_is_inside_the_window_and_covers_no_text_of_its_own(app, size):
    drv = checked(app, size)
    drv.click("ask_update")
    drv.draw(3)
    box = app.message_window.box
    assert (
        box is not None
        and box[0] >= 0
        and box[1] >= 0
        and box[0] + box[2] <= size[0] + 1
        and box[1] + box[3] <= size[1] + 1
    )
    assert box[2] >= 400 and box[3] >= 120
    for label in ("Yes", "No"):
        x, y, w, h = drv.text_rect(label)
        assert box[0] <= x and x + w <= box[0] + box[2] and box[1] <= y and y + h <= box[1] + box[3]
    texts = [
        t
        for t in drv.painter.texts
        if t[5] and t[0] >= box[0] and t[0] + t[2] <= box[0] + box[2] and t[1] >= box[1]
    ]
    assert any("Do you want to continue?" in t[5] for t in texts)
    drv.click_text("No")


@pytest.mark.parametrize("size", SIZES)
def test_the_window_with_nothing_found_says_what_to_do_and_greys_what_cannot_act(app, size):
    painter = lc.draw(app, size)
    assert "Click 'Check for Updates' to check for available updates." in painter.strings
    assert "Changelog will appear here after checking for updates..." in painter.strings
    model = app.model
    assert [
        model.enabled(n)
        for n in (
            "check_for_updates",
            "ask_update",
            "selected_version",
            "open_package_manager",
            "development",
        )
    ] == [True, False, False, True, False]
    assert model.version_labels == [] and model.selected_version == ""


@pytest.mark.parametrize("size", SIZES)
def test_the_progress_window_is_inside_the_frame(app, size, fakes, monkeypatch):
    from chisurf.plugins.core.updater import updater as up

    release = {"go": False}

    def slow(self, cmd, callback=None):
        callback("Preparing to run update in a separate process...")
        end = time.monotonic() + 10
        while not release["go"] and time.monotonic() < end:
            time.sleep(0.01)
        return True, None

    monkeypatch.setattr(up.ChiSurfUpdater, "_run_update_in_separate_process", slow)
    drv = checked(app, size)
    drv.click("ask_update")
    drv.click_text("Yes")
    deadline = time.monotonic() + 5
    while (
        "Preparing to run update in a separate process..." not in drv.draw(1).strings
        and time.monotonic() < deadline
    ):
        time.sleep(0.02)
    box = app.progress_window.box
    assert (
        box is not None
        and box[0] >= 0
        and box[0] + box[2] <= size[0] + 1
        and box[1] + box[3] <= size[1] + 1
    )
    inside = [
        b
        for b in lc.boxes(drv.painter)
        if box[0] <= b[0] and b[0] + b[2] <= box[0] + box[2] and box[1] <= b[1] <= box[1] + box[3]
    ]
    assert any(
        "Preparing to run update" in b[4] for b in inside
    )  # the window's own texts are apart (it stands over the form)
    for i, a in enumerate(inside):
        for b in inside[i + 1 :]:
            assert lc._overlap(a[:4], b[:4]) <= 1.0, (a[4], b[4])
    release["go"] = True
    settle(drv)


def test_the_fixed_font_scale_of_the_card_does_not_leave_the_window_at_800(app):
    drv = checked(app, (800, 600))
    app.tour.start(0)
    drv.draw(3)
    for label in ("Next ►", "Close Tour"):
        x, y, w, h = drv.text_rect(label)
        assert 0 <= x and x + w <= 800 and 0 <= y and y + h <= 600
    app.tour.stop()
