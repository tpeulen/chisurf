"""Real input on the native updater: pointer presses at the rectangles the controls were drawn in, the mouse wheel, drags, Escape.

Nothing here calls a model method to "click": each test presses and releases the pointer where a control was drawn (or at
the text it drew) and reads the visible outcome (strings of the frame, model fields the window edits, the settings file,
the command line that reached the fake runner). Everything runs on the fakes of ``fakes.py``: no update, install,
removal, environment change or network.

Control -> test list: REPORT.md section "Real-input coverage".
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from emtk import keys

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1000, 700)


class UpdaterDriver(Driver):
    """The imaging driver, waiting for the updater's own background job."""

    def click_at(self, x, y, frames=1):
        self.app.pointer_move(x, y)
        self.draw(1)
        super().click_at(x, y, frames)

    def settle(self, timeout=60.0, extra=2):
        end = time.monotonic() + timeout
        self.draw(1)
        while (self.app.job.busy or self.app.model.busy or self.app.model.updating) and time.monotonic() < end:
            time.sleep(0.01)
            self.draw(1)
        assert not self.app.job.busy, "the background job did not finish"
        return self.draw(extra)

    def press_text(self, label, last=True):
        self.click(self.text_rect(label, last=last))

    def shown(self, text):
        return any(text in s for s in self.draw(1).strings)


@pytest.fixture
def app():
    from chisurf.plugins.core.updater.gui.app import UpdaterApp
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    application = UpdaterApp(UpdaterModel(), auto_check=False)
    yield application
    application.close()


@pytest.fixture
def ui(app):
    driver = UpdaterDriver(app, SIZE)
    driver.draw(3)
    return driver


@pytest.fixture
def checked(ui):
    """The window after a press on Check for Updates."""
    ui.click("check_for_updates")
    ui.settle()
    assert ui.app.model.version_labels
    return ui


def tooltip_shown(ui, name, text, frames=10):
    """Rest the pointer on a control until its tooltip is drawn."""
    x, y, w, h = ui.rect(name)
    ui.app.pointer_move(1, 1)
    ui.draw(2)
    ui.app.pointer_move(x + w / 2, y + h / 2)
    for _ in range(frames):
        time.sleep(0.15)
        ui.draw(1)
        if any(text[:24] in s for s in ui.painter.strings):
            return True
    return False


# ---------------------------------------------------------------------------------------------- Check for Updates
@pytest.fixture
def gate(monkeypatch, fakes):
    """The fake release listing waits for ``gate['release']``, so a test can look at the window while the check runs."""
    from chisurf.plugins.core.updater import updater as up

    state = {"release": False, "calls": 0}

    def listing(self):
        state["calls"] += 1
        end = time.monotonic() + 20
        while not state["release"] and time.monotonic() < end:
            time.sleep(0.01)
        return fakes.list_remote_versions(self)

    monkeypatch.setattr(up.ChiSurfUpdater, "_list_remote_versions", listing)
    return state


def test_check_for_updates_press_runs_the_check_in_the_background_and_fills_the_window(ui, fakes, gate):
    assert ui.shown("Click 'Check for Updates' to check for available updates.")
    assert ui.app.model.version_labels == []
    ui.click("check_for_updates")
    ui.draw(3)
    assert ui.shown("Checking for updates...") and ui.app.job.busy      # the window stays alive while it runs
    gate["release"] = True
    ui.settle()
    assert ui.shown("Update available: version 26.10.02") and ui.shown("Version 26.10.02")
    assert ui.shown("Changes between 26.09.20 and 26.10.02:") and ui.shown("2026-10-01 Add the updater tour (by Ada)")
    assert fakes.remote_listings >= 1 and fakes.update_commands == []


def test_a_second_press_while_the_check_runs_does_nothing(ui, fakes, gate):
    """The button is greyed while the job runs (the Qt tool disabled it): no second job starts."""
    ui.click("check_for_updates")
    ui.draw(3)
    assert ui.app.job.busy and not ui.app.model.enabled("check_for_updates") and not ui.app.model.enabled("ask_update")
    calls = gate["calls"]
    ui.click("check_for_updates")
    ui.click("check_for_updates")
    gate["release"] = True
    ui.settle()
    assert gate["calls"] == calls + 0 or gate["calls"] <= 4          # one check's own listings (info, availability, info), not three more checks


def test_a_failing_server_shows_the_error_and_keeps_the_window_usable(ui, fakes):
    fakes.releases.clear()
    ui.click("check_for_updates")
    ui.settle()
    assert ui.shown("Error checking for updates: No update information available")
    assert not ui.app.model.enabled("ask_update")
    fakes.releases.extend([{"version": "26.10.02", "file_path": "https://downloads.invalid/x/chisurf-macos-26.10.02.conda",
                            "file_name": "chisurf-macos-26.10.02.conda"}])
    ui.click("check_for_updates")                                   # and a later check recovers
    ui.settle()
    assert ui.shown("Update available: version 26.10.02")


def test_a_check_that_raises_is_reported_as_failed_not_as_a_crash(ui, fakes, monkeypatch):
    from chisurf.plugins.core.updater import updater as up

    def boom(self):
        raise RuntimeError("server on fire")

    monkeypatch.setattr(up.ChiSurfUpdater, "_get_update_info", boom)
    ui.click("check_for_updates")
    ui.settle()
    assert ui.shown("Failed: server on fire") and ui.app.model.busy is False
    assert ui.app.model.enabled("check_for_updates")


# ---------------------------------------------------------------------------------------------- the version list
def test_the_version_list_is_greyed_until_versions_exist_and_a_press_on_it_does_nothing(ui):
    assert not ui.app.model.enabled("selected_version")
    ui.click("selected_version")
    assert not any(s == "Version 26.10.02" for s in ui.draw(2).strings)


def test_picking_a_version_in_the_list_shows_its_changelog(checked):
    ui = checked
    ui.click("selected_version")
    for label in ("Version 26.10.02", "Version 26.09.20", "Version 26.08.01"):
        assert ui.shown(label)
    ui.press_text("Version 26.09.20")
    ui.settle()
    assert ui.app.model.version_index == 1 and ui.app.model.selected_version == "Version 26.09.20"
    assert ui.shown("Changes between 26.08.01 and 26.09.20:")
    ui.click("selected_version")
    ui.press_text("Version 26.08.01")
    ui.settle()
    assert ui.app.model.version_index == 2 and ui.shown("Changes between ") and not ui.shown("26.08.01 and 26.09.20")


def test_the_picked_version_is_the_one_update_now_installs(checked, fakes):
    ui = checked
    ui.click("selected_version")
    ui.press_text("Version 26.08.01")
    ui.settle()
    ui.click("ask_update")
    ui.press_text("Yes")
    ui.settle()
    (url, local), = fakes.downloads
    assert url.endswith("chisurf-macos-26.08.01.conda") and fakes.update_commands == [
        ("separate_process", fakes.expected_update_commands(local))]


@pytest.mark.xfail(strict=True, reason="emtk gap: the wheel over a choice does not step it (a Qt combo box does); repro in REPORT.md")
def test_the_wheel_over_the_version_list_steps_it(checked):
    ui = checked
    x, y, w, h = ui.rect("selected_version")
    ui.wheel(x + w / 2, y + h / 2, -1)
    ui.settle()
    assert ui.app.model.version_index == 1


# ---------------------------------------------------------------------------------------------- Update Now
def test_update_now_is_greyed_before_a_check_and_a_press_opens_nothing(ui):
    assert not ui.app.model.enabled("ask_update")
    ui.click("ask_update")
    assert ui.app.model.dialog == "" and not ui.shown("Update Warning")


def test_update_now_asks_the_qt_question_and_No_leaves_everything_as_it_is(checked, fakes):
    ui = checked
    ui.click("ask_update")
    assert ui.app.model.dialog == "confirm_update" and ui.shown("The update process will close all ChiSurf windows")
    assert ui.shown("Do you want to continue?") and ui.shown("Yes") and ui.shown("No")
    assert not ui.app.model.enabled("check_for_updates")            # the question is modal: the window behind is greyed
    ui.press_text("No")
    assert ui.app.model.dialog == "" and ui.shown("Update cancelled by user.")
    assert fakes.update_commands == [] and fakes.downloads == []


def test_the_dialogs_close_button_and_escape_are_a_No(checked, fakes):
    ui = checked
    ui.click("ask_update")
    ui.press_text("\u00d7")
    assert ui.app.model.dialog == "" and ui.shown("Update cancelled by user.")
    ui.click("ask_update")
    ui.app.pointer_move(500, 350)
    ui.draw(2)
    ui.key(keys.KEY_ESCAPE, "")
    assert ui.app.model.dialog == "" and fakes.update_commands == []


def test_Yes_starts_the_update_and_the_fake_runner_sees_the_install_line(checked, fakes):
    ui = checked
    ui.click("ask_update")
    ui.press_text("Yes")
    ui.settle()
    (url, local), = fakes.downloads
    assert url.endswith("chisurf-macos-26.10.02.tar.bz2")
    assert fakes.update_commands == [("separate_process", fakes.expected_update_commands(local))]
    assert ui.shown("The update was started in a separate window")
    assert fakes.mutating_solver_commands == [] and fakes.restarts == 0


def test_the_progress_window_shows_the_latest_step_while_the_update_is_prepared(checked, fakes, monkeypatch):
    """While the update runs, a window names its step (the Qt progress dialog's label); it closes when the update has been handed over."""
    from chisurf.plugins.core.updater import updater as up

    gate = {"release": False}

    def slow_runner(self, cmd, callback=None):
        fakes.update_commands.append(("separate_process", list(cmd)))
        callback("Preparing to run update in a separate process...")
        end = time.monotonic() + 10
        while not gate["release"] and time.monotonic() < end:
            time.sleep(0.01)
        return True, None

    monkeypatch.setattr(up.ChiSurfUpdater, "_run_update_in_separate_process", slow_runner)
    ui = checked
    ui.click("ask_update")
    ui.press_text("Yes")
    ui.draw(3)
    deadline = time.monotonic() + 5
    while not ui.shown("Preparing to run update in a separate process...") and time.monotonic() < deadline:
        time.sleep(0.02)
        ui.draw(1)
    assert ui.app.model.updating and ui.shown("Updating ChiSurf") and ui.shown("Preparing to run update")
    assert not ui.app.model.enabled("check_for_updates")
    gate["release"] = True
    ui.settle()
    assert not ui.app.model.updating and not ui.shown("Updating ChiSurf")


def test_a_failed_update_start_is_shown_in_the_status(checked, fakes, monkeypatch):
    from chisurf.plugins.core.updater import updater as up

    monkeypatch.setattr(up.ChiSurfUpdater, "_run_update_in_separate_process",
                        lambda self, cmd, callback=None: (False, "Error starting update process: disk full"))
    ui = checked
    ui.click("ask_update")
    ui.press_text("Yes")
    ui.settle()
    assert ui.shown("Update failed: Error starting update process: disk full")


# ---------------------------------------------------------------------------------------------- Package Manager, Development
def test_the_package_manager_button_is_greyed_and_a_press_opens_nothing(ui):
    assert not ui.app.model.enabled("open_package_manager")
    ui.click("open_package_manager")
    assert ui.app.model.request == ""
    assert tooltip_shown(ui, "open_package_manager", "Open the package manager to manage packages")
    assert "Greyed for now" in __import__("json").loads((Path(__file__).parent.parent / "gui" / "updater.view.json").read_text())["sections"][0]["sections"][2]["sections"][1]["buttons"][2]["description"]


def test_the_development_switch_is_on_and_a_press_does_not_turn_it_off(ui):
    assert ui.app.model.development and ui.app.model.updater.channel == "development"
    ui.click("development")
    assert ui.app.model.development and ui.app.model.updater.channel == "development"
    assert ui.shown("branch: development")


# ---------------------------------------------------------------------------------------------- startup switches
def test_the_startup_switches_toggle_with_a_press_and_are_saved_at_once(ui, tmp_path):
    saved = tmp_path / "settings" / "settings_chisurf.yaml"
    assert ui.app.model.check_on_startup is True and ui.app.model.ignore_updates is False
    ui.click("check_on_startup", fx=0.05)
    assert ui.app.model.check_on_startup is False
    assert yaml.safe_load(saved.read_text())["plugins"]["updater"]["check_on_startup"] is False
    ui.click("ignore_updates_on_startup", fx=0.05)
    assert ui.app.model.ignore_updates is True
    assert yaml.safe_load(saved.read_text())["plugins"]["updater"] == {"ignore_updates_on_startup": True, "check_on_startup": False}
    ui.click("check_on_startup", fx=0.05)                          # and back
    ui.click("ignore_updates_on_startup", fx=0.05)
    assert yaml.safe_load(saved.read_text())["plugins"]["updater"] == {"ignore_updates_on_startup": False, "check_on_startup": True}


def test_pressing_the_caption_of_a_switch_toggles_it_as_a_qt_checkbox_does(ui):
    text = ui.text_rect("Ignore updates (do not prompt on startup)")
    ui.click(text)
    assert ui.app.model.ignore_updates is True


# ---------------------------------------------------------------------------------------------- the changelog
def long_changelog(n=60):
    return "Changes between 1 and 2:\n" + "\n".join(f"- 2026-10-01 commit number {i} (by Ada)" for i in range(n)) + \
        "\nMore details: https://github.com/Fluorescence-Tools/chisurf/commits"


def test_a_long_changelog_scrolls_under_the_wheel(checked):
    ui = checked
    ui.app.model._show_changelog(long_changelog())
    ui.draw(3)

    def first_y():
        return [t[1] for t in ui.draw(1).texts if t[5] == "2026-10-01 commit number 0 (by Ada)"][0]

    at_start = first_y()
    x, y, w, h = ui.rect("changelog")
    ui.wheel(x + w / 2, y + h / 2, -6)
    ui.draw(3)
    assert first_y() < at_start - 20                                 # a turn down: later lines come into view
    ui.wheel(x + w / 2, y + h / 2, 12)
    ui.draw(3)
    assert abs(first_y() - at_start) < 1.0                           # and back


def test_a_link_in_the_changelog_opens_in_the_browser_when_pressed(checked):
    ui = checked
    opened = []
    ui.app.open_link = opened.append
    ui.press_text("https://github.com/Fluorescence-Tools/chisurf/commits")
    assert opened == ["https://github.com/Fluorescence-Tools/chisurf/commits"]


def test_changelog_text_shows_characters_as_written(checked):
    ui = checked
    ui.app.model._show_changelog("Changes a:\n- fix snake_case_name and *star* <b>x</b> [l](u)")
    assert ui.shown("fix snake_case_name and *star* <b>x</b> [l](u)")


def test_the_empty_changelog_says_what_to_do(ui):
    assert ui.shown("Changelog will appear here after checking for updates...")


# ---------------------------------------------------------------------------------------------- the start-up check, notice
def test_the_check_on_opening_starts_by_itself_and_its_notice_closes_with_OK(fakes):
    from chisurf.plugins.core.updater.gui.app import UpdaterApp
    from chisurf.plugins.core.updater.gui.model import UpdaterModel

    app = UpdaterApp(UpdaterModel(), auto_check=True, auto_check_delay=0.0)
    ui = UpdaterDriver(app, SIZE)
    ui.draw(3)
    ui.settle()
    assert ui.shown("Update available: version 26.10.02") and app.model.dialog == "notice"
    assert ui.shown("A new version of ChiSurf (26.10.02) is available.")
    ui.press_text("OK")
    assert app.model.dialog == "" and not ui.shown("is available.")
    app.close()


def test_the_check_on_opening_waits_a_moment_and_so_a_drawn_only_window_never_asks_the_network(fakes):
    from chisurf.plugins.core.updater.gui.app import make_app

    app = make_app()
    ui = UpdaterDriver(app, SIZE)
    ui.draw(5)
    assert fakes.remote_listings == 0 and fakes.http_requests == [] and app.model.auto_check_pending
    app.close()


# ---------------------------------------------------------------------------------------------- tooltips
@pytest.mark.parametrize("name, text", [
    ("check_for_updates", "Ask the update server which versions exist"),
    ("current_version_text", "The version of ChiSurf installed in this environment."),
    ("check_on_startup", "When enabled, ChiSurf will check for updates during startup."),
    ("ignore_updates_on_startup", "If enabled, ChiSurf will not prompt about updates during startup."),
    ("development", "ChiSurf currently has no stable release"),
    ("selected_version", "The versions the update server lists"),
    ("help", "Explain the version list"),
    ("guide", "Walk through checking for an update"),
])
def test_resting_the_pointer_on_a_control_shows_its_tooltip(ui, name, text):
    assert tooltip_shown(ui, name, text)


def test_update_now_tooltip_when_a_version_exists(checked):
    assert tooltip_shown(checked, "ask_update", "Install the selected version.")


# ---------------------------------------------------------------------------------------------- Help and Guide
def test_help_opens_the_help_window_and_closes(ui):
    ui.click("help")
    assert ui.app.help_window.open and ui.shown("Close Help")
    ui.press_text("Close Help")
    assert not ui.app.help_window.open


def press_next(ui):
    """Press Next on the tour card. Where the card lies over a control that takes the press first (an emtk gap: the card does
    not block what is under it), drag the card by its handle to the empty top right of the window, as a user would, and press again.
    Returns whether the first press was dead."""
    here = ui.app.tour.step_idx
    ui.press_text("Next \u25ba")
    if ui.app.tour.step_idx == here + 1:
        return False
    handle = ui.text_rect("drag here to move")
    ui.drag((handle[0] + 20, handle[1] + 5), (ui.size[0] - 260, 60))
    ui.press_text("Next \u25ba")
    assert ui.app.tour.step_idx == here + 1, f"the Next button of step {here + 1} stayed dead after the card was dragged away"
    return True


def test_guide_walks_the_tour_with_the_user_operating_the_awaited_controls(app, fakes):
    ui = UpdaterDriver(app, (1200, 800))
    ui.draw(3)
    ui.click("guide")
    steps = len(ui.app.tour.steps)
    assert ui.app.tour.active and ui.shown(f"Step 1 of {steps}")
    ui.press_text("Next \u25ba")
    assert ui.app.tour.step_idx == 1 and ui.shown("Look for a newer version")
    # an awaited step: the tour waits for the real press of the button it points at
    ui.press_text("Next \u25ba")
    assert ui.app.tour.step_idx == 1, "the tour must wait for Check for Updates"
    assert ui.app.tour.awaiting
    ui.click("check_for_updates")
    ui.settle()
    assert not ui.app.tour.awaiting and ui.app.tour.step_idx == 1    # the press released the step; Next is the user's
    ui.press_text("Next \u25ba")
    assert ui.app.tour.step_idx == 2 and ui.shown("Pick a version") and ui.app.tour.awaiting
    ui.click("selected_version")
    ui.press_text("Version 26.09.20")
    ui.settle()
    assert not ui.app.tour.awaiting
    ui.press_text("Next \u25ba")
    assert ui.app.tour.step_idx == 3
    for _ in range(steps):
        if ui.app.tour.step_idx >= steps - 1:
            break
        press_next(ui)
    assert ui.app.tour.step_idx == steps - 1 and ui.shown("Package Manager")
    assert fakes.update_commands == [] and ui.app.model.dialog == ""   # the tour never presses Update Now for the user


def test_the_tour_card_can_be_dragged_away(ui):
    ui.click("guide")
    ui.draw(3)
    handle = ui.text_rect("drag here to move")
    before = ui.app.tour.card_offset
    ui.drag((handle[0] + 20, handle[1] + 5), (handle[0] - 60, handle[1] + 80))
    assert ui.app.tour.card_offset != before


def test_every_guide_target_is_drawn_and_the_card_does_not_cover_it(checked):
    from chisurf.emtk.help_guide import place_tour_card

    ui = checked
    W, H = float(ui.size[0]), float(ui.size[1])
    for index, step in enumerate(ui.app.tour.steps):
        target = step.get("target") or {}
        ui.app.tour.start(index)
        key = ui.app.tour._target_key(target)
        ui.draw(3)
        rect = ui.app.tour.get_target_rect(key)
        assert rect and rect[2] > 0 and rect[3] > 0, f"{step['title']}: nothing drawn for {key!r}"
        card_w = min(480.0, W - 40.0)
        x, y = place_tour_card(rect, W, H, card_w, 150.0)
        clear = x + card_w <= rect[0] or x >= rect[0] + rect[2] or y + 150.0 <= rect[1] or y >= rect[1] + rect[3]
        free_side = (rect[0] + rect[2] + card_w + 16 <= W or rect[0] - card_w - 16 >= 0 or rect[1] + rect[3] + 150 + 16 <= H
                     or rect[1] - 150 - 16 >= 0)
        assert clear or not free_side, f"{step['title']}: the card would cover its target although room was free"
    ui.app.tour.stop()


# ---------------------------------------------------------------------------------------------- window, host
def test_the_dialog_window_is_dragged_by_its_title_bar(checked):
    ui = checked
    ui.click("ask_update")
    ui.draw(3)
    box = ui.app.message_window.box
    assert box is not None
    start = (box[0] + 60, box[1] + 10)
    ui.drag(start, (start[0] - 120, start[1] + 90))
    moved = ui.app.message_window.box
    assert moved[0] < box[0] - 50 and moved[1] > box[1] + 50
    ui.press_text("No")


def test_there_is_nothing_to_drop_and_the_host_hook_is_absent_as_in_the_qt_tool(app):
    assert not hasattr(app, "on_files_dropped") or app.on_files_dropped([]) in (None, False)


def test_the_window_closes_cleanly(app):
    app.close()
    assert app.model._observers == []
