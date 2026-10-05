"""Real input on the native package manager: pointer presses at the rectangles the controls were drawn in, typed text, Enter,
Escape, the wheel, drags. Nothing calls a model method to "click". All solver calls are fakes (``fakes.py``): each test reads the
command line that reached ``PackageManager._popen`` and the visible outcome.

Control -> test list: REPORT.md section "Real-input coverage (U2)". Drops: the window takes none (as the Qt dialog).
"""

from __future__ import annotations

import sys
import time

import pytest
from emtk import keys

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1000, 700)


class PkgDriver(Driver):
    def click_at(self, x, y, frames=1):
        self.app.pointer_move(x, y)
        self.draw(1)
        super().click_at(x, y, frames)

    def settle(self, timeout=30.0, extra=3):
        end = time.monotonic() + timeout
        self.draw(1)
        while (self.app.job.busy or self.app.model.busy) and time.monotonic() < end:
            time.sleep(0.01)
            self.draw(1)
        assert not self.app.job.busy
        return self.draw(extra)

    def shown(self, text):
        return any(text in s for s in self.draw(1).strings)

    def press_text(self, label):
        self.click(self.text_rect(label, last=True))

    def open_tab(self, name):
        self.click(f"tab_{name}")
        self.draw(3)

    def row(self, label):
        self.click(self.text_rect(label))

    def dialog_rect(self, name):
        return self.app.panel.dialog_form.rects[name]


@pytest.fixture
def app(fakes):
    from chisurf.plugins.core.updater.gui.package_app import PackageApp

    application = PackageApp()
    yield application
    application.close()


@pytest.fixture
def ui(app):
    driver = PkgDriver(app, SIZE)
    driver.draw(3)
    driver.settle()
    assert app.model.installed_rows
    app.panel.model.log.clear()
    return driver


def mutating(fakes):
    return fakes.mutating_solver_commands


def tooltip_shown(ui, name, text, frames=10):
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


# ---------------------------------------------------------------------------------------------- opening, tabs, Refresh
def test_opening_loads_the_three_lists_by_drawn_frames_alone(fakes, app):
    ui = PkgDriver(app, SIZE)
    ui.draw(3)
    ui.settle()
    assert ui.shown("numpy") and ui.shown(sys.prefix) and ui.shown("Loaded 5 packages.")
    assert [c[1:3] for c in fakes.solver_commands if c[1] in ("list", "env")] and mutating(fakes) == []


@pytest.mark.parametrize("tab, marker", [("search", "Package"), ("envs", "/fake/mambaforge"), ("channels", "conda-forge"), ("installed", "Filter")])
def test_each_tab_is_opened_by_a_press_on_its_title(ui, tab, marker):
    ui.open_tab("envs" if tab == "installed" else tab) if tab == "installed" else None
    ui.open_tab(tab)
    assert ui.app.model.tab == ["installed", "search", "envs", "channels"].index(tab) and ui.shown(marker)


def test_refresh_list_and_refresh_all_reload_and_change_nothing(ui, fakes):
    fakes.solver_commands.clear()
    ui.click("refresh_installed")
    ui.settle()
    assert fakes.solver_commands == [["/fake/bin/micromamba", "list", "--json", "-p", sys.prefix]] and ui.shown("Refreshing installed packages...")
    fakes.solver_commands.clear()
    ui.click("refresh_all")
    ui.settle()
    assert len(fakes.solver_commands) == 3 and mutating(fakes) == []


# ---------------------------------------------------------------------------------------------- installed page
def test_the_filter_is_typed_and_narrows_the_rows_and_clearing_restores_them(ui):
    ui.type_into("installed_filter", "NUM")
    assert ui.app.model.installed_filter == "NUM" and ui.shown("numpy") and not ui.shown("scipy")
    ui.click("installed_filter", fx=0.3)                       # empty it with Backspace (select-all + Enter alone keeps the text: emtk gap)
    ui.select_all()
    ui.key(keys.KEY_BACKSPACE, "")
    ui.click("log", fy=0.9)                                    # the box commits when the pointer goes down elsewhere
    assert ui.app.model.installed_filter == "" and ui.shown("scipy") and ui.shown("python")


def test_a_header_press_sorts_by_that_column_twice_reverses(ui):
    def names():
        return [t[5] for t in ui.draw(1).texts if t[5] in ("numpy", "scipy", "python", "chisurf", "Numba")]

    first = names()
    x, y, w, h = ui.text_rect("Name")
    ui.click_at(x + 5, y + 5)
    asc = names()
    ui.click_at(x + 5, y + 5)
    desc = names()
    assert asc != first or desc != first and asc == list(reversed(desc)) and len(asc) == 5


def test_a_row_press_selects_it_and_greys_in_the_buttons(ui):
    assert not ui.app.model.enabled("ask_remove_selected")
    ui.row("scipy")
    assert ui.app.model.sel_installed["name"] == "scipy" and ui.app.model.enabled("ask_update_selected")


def test_update_selected_runs_the_update_line_without_asking(ui, fakes):
    ui.row("scipy")
    ui.click("ask_update_selected")
    ui.settle()
    assert mutating(fakes) == [["/fake/bin/micromamba", "update", "-y", "-p", sys.prefix, "scipy"]]
    assert ui.shown("Updating scipy...") and ui.shown("Operation completed successfully.")


def test_update_all_asks_and_No_changes_nothing_Yes_runs_it(ui, fakes):
    ui.click("ask_update_all")
    assert ui.shown("Update all packages in the current environment?") and not ui.app.model.enabled("refresh_all")
    ui.press_text("No")
    assert mutating(fakes) == [] and ui.app.model.dialog == ""
    ui.click("ask_update_all")
    ui.press_text("Yes")
    ui.settle()
    assert mutating(fakes) == [["/fake/bin/micromamba", "update", "-y", "-p", sys.prefix, "--all"]]


def test_remove_selected_asks_and_the_close_button_and_Escape_decline(ui, fakes):
    ui.row("scipy")
    ui.click("ask_remove_selected")
    assert ui.shown("Are you sure you want to remove:") and ui.shown("scipy?")
    ui.press_text("×")
    assert ui.app.model.dialog == "" and mutating(fakes) == []
    ui.click("ask_remove_selected")
    ui.draw(3)
    box = ui.app.panel.message_window.box
    ui.app.pointer_move(box[0] + box[2] / 2, box[1] + box[3] / 2)
    ui.draw(2)
    ui.key(keys.KEY_ESCAPE, "")
    assert ui.app.model.dialog == "" and mutating(fakes) == []
    ui.click("ask_remove_selected")
    ui.press_text("Yes")
    ui.settle()
    assert mutating(fakes) == [["/fake/bin/micromamba", "remove", "-y", "-p", sys.prefix, "scipy"]]


def test_a_failed_removal_opens_one_error_naming_the_reason(ui, fakes):
    fakes.solver_fails = True
    ui.row("numpy")
    ui.click("ask_remove_selected")
    ui.press_text("Yes")
    ui.settle()
    assert ui.app.model.dialog == "notice" and ui.shown("The operation failed:") and ui.shown("fake solver: the operation is refused")
    ui.press_text("OK")
    assert ui.app.model.dialog == "" and ui.shown("Operation failed:")


# ---------------------------------------------------------------------------------------------- search & install
def test_search_by_enter_and_by_button_lists_rows_and_install_asks(ui, fakes):
    ui.open_tab("search")
    assert not ui.app.model.enabled("search_packages")
    ui.type_into("search_query", "numpy")                     # typed + Enter
    ui.settle()
    assert ui.shown("2.0.1") and ui.shown("1.26.3") and ui.shown("Found 3 results.")
    fakes.solver_commands.clear()
    ui.click("search_packages")                               # and the button
    ui.settle()
    assert fakes.solver_commands[0] == ["/fake/bin/micromamba", "search", "numpy", "--json"]
    assert not ui.app.model.enabled("ask_install_selected")
    ui.row("2.0.1")
    ui.click("ask_install_selected")
    assert ui.shown("Are you sure you want to install:")
    ui.press_text("No")
    assert mutating(fakes) == []
    ui.click("ask_install_selected")
    ui.press_text("Yes")
    ui.settle()
    assert mutating(fakes) == [["/fake/bin/micromamba", "install", "-y", "--update-deps", "-p", sys.prefix, "numpy"]]


# ---------------------------------------------------------------------------------------------- environments
def type_in_dialog(ui, text):
    x, y, w, h = ui.dialog_rect("dialog_input")
    ui.click_at(x + 10, y + h / 2)
    assert ui.app.io.want_capture_keyboard
    ui.select_all()
    ui.type_text(text)
    ui.enter()


def test_create_new_asks_for_a_typed_name_and_OK_runs_it(ui, fakes):
    ui.open_tab("envs")
    ui.click("ask_create_env")
    assert ui.shown("Enter environment name:")
    type_in_dialog(ui, "scratch")
    ui.press_text("OK")
    ui.settle()
    assert mutating(fakes) == [["/fake/bin/micromamba", "create", "-y", "-n", "scratch"]]


def test_create_new_Cancel_and_an_empty_name_run_nothing(ui, fakes):
    ui.open_tab("envs")
    ui.click("ask_create_env")
    ui.press_text("Cancel")
    ui.click("ask_create_env")
    ui.press_text("OK")
    ui.settle()
    assert mutating(fakes) == []


def test_clone_and_remove_need_a_selected_environment_and_run_the_qt_lines(ui, fakes):
    ui.open_tab("envs")
    assert not ui.app.model.enabled("ask_clone_env") and not ui.app.model.enabled("ask_remove_env")
    ui.row("/fake/mambaforge/envs/analysis")
    ui.click("ask_clone_env")
    assert ui.shown("Enter new name for clone of '/fake/mambaforge/envs/analysis':")
    type_in_dialog(ui, "analysis-copy")
    ui.press_text("OK")
    ui.settle()
    ui.open_tab("envs")
    ui.row("/fake/mambaforge/envs/arm64")
    ui.click("ask_remove_env")
    assert ui.shown("Remove environment '/fake/mambaforge/envs/arm64'?")
    ui.press_text("No")
    ui.click("ask_remove_env")
    ui.press_text("Yes")
    ui.settle()
    assert mutating(fakes) == [["/fake/bin/micromamba", "create", "-y", "-n", "analysis-copy", "--clone", "/fake/mambaforge/envs/analysis"],
                               ["/fake/bin/micromamba", "env", "remove", "-y", "-p", "/fake/mambaforge/envs/arm64"]]


def test_export_to_file_opens_a_save_dialog_and_writes_the_typed_name(ui, fakes, tmp_path):
    ui.open_tab("envs")
    ui.row("/fake/mambaforge/envs/analysis")
    ui.click("request_export")
    ui.draw(3)
    assert ui.app.panel.dialog is not None and ui.shown("Cancel")
    ui.press_text("Cancel")
    assert ui.app.panel.dialog is None and not list(tmp_path.glob("out*"))
    ui.click("request_export")
    ui.draw(3)
    ui.click(ui.text_rect("environment.yaml"), fx=0.3)
    ui.select_all()
    ui.type_text(str(tmp_path / "out.yaml"))
    ui.press_text("Save")
    ui.settle()
    assert (tmp_path / "out.yaml").read_text().startswith("name: fake") and ui.shown("Exported successfully to")


def test_import_from_file_picks_a_file_then_asks_for_a_name(ui, fakes, tmp_path):
    (tmp_path / "env.yaml").write_text("name: imported\n")
    ui.open_tab("envs")
    ui.app.panel.dialog = None
    ui.click("request_import")
    ui.draw(3)
    ui.app.panel.dialog.directory = str(tmp_path)
    ui.app.panel.dialog.refresh() if hasattr(ui.app.panel.dialog, "refresh") else None
    ui.draw(3)
    ui.press_text("env.yaml")
    ui.press_text("Open")
    assert ui.shown("Enter name for new environment (optional):")
    type_in_dialog(ui, "imported")
    ui.press_text("OK")
    ui.settle()
    assert mutating(fakes) == [["/fake/bin/micromamba", "env", "create", "-f", str(tmp_path / "env.yaml"), "-n", "imported"]]


# ---------------------------------------------------------------------------------------------- channels
def test_add_channel_types_a_name_and_remove_needs_a_selection(ui, fakes):
    ui.open_tab("channels")
    assert not ui.app.model.enabled("remove_channel")
    ui.click("ask_add_channel")
    assert ui.shown("Enter channel name or URL:")
    type_in_dialog(ui, "bioconda")
    ui.press_text("OK")
    ui.settle()
    ui.open_tab("channels")
    ui.row("conda-forge")
    ui.click("remove_channel")
    ui.settle()
    assert mutating(fakes) == [["/fake/bin/micromamba", "config", "--add", "channels", "bioconda"],
                               ["/fake/bin/micromamba", "config", "--remove", "channels", "conda-forge"]]


# ---------------------------------------------------------------------------------------------- the log, wheel, tooltips, help
def log_line_visible(ui, text):
    """Whether the log line *text* was drawn inside the log's own rectangle (a clipped line is recorded as drawn, outside it)."""
    x, y, w, h = ui.app.item_rects["log"]
    return any(t[5].endswith(text) and y <= t[1] and t[1] + t[3] <= y + h + 1 for t in ui.draw(1).texts)


def test_the_log_scrolls_under_the_wheel_and_follows_new_lines(ui):
    for i in range(40):
        ui.app.model.append_log(f"line {i}")
    ui.draw(4)
    x, y, w, h = ui.rect("log")
    assert log_line_visible(ui, "line 39") and not log_line_visible(ui, "line 0")      # follows the newest line
    ui.wheel(x + w / 2, y + h / 2, 60)
    ui.draw(3)
    assert log_line_visible(ui, "line 1") and not log_line_visible(ui, "line 39")


def test_the_wheel_scrolls_a_long_table(ui):
    ui.app.model.installed_all = [{"name": f"pkg{i:03d}", "version": "1", "channel": "c"} for i in range(80)]
    ui.app.model.apply_filter()
    ui.draw(3)
    assert ui.shown("pkg000") and not ui.shown("pkg079")
    x, y, w, h = ui.text_rect("pkg000")
    ui.wheel(x + 40, y + 20, -40)
    ui.draw(3)
    assert not ui.shown("pkg000")


@pytest.mark.parametrize("name, text", [
    ("refresh_installed", "Reload the installed packages"), ("ask_update_all", "Update every package"),
    ("installed_filter", "Show only the installed packages"), ("refresh_all", "Reload the installed packages, environments"),
    ("help", "Explain the four pages"), ("guide", "Walk through finding"),
])
def test_resting_the_pointer_on_a_control_shows_its_tooltip(ui, name, text):
    assert tooltip_shown(ui, name, text)


def test_help_and_guide(ui):
    ui.click("help")
    assert ui.app.help_window.open
    ui.press_text("Close Help")
    assert not ui.app.help_window.open
    ui.click("guide")
    assert ui.app.tour.active and ui.shown("Step 1 of 5") and ui.shown("Installed Packages")
    ui.app.tour.start(1)                                       # step 2 awaits the press on the Search & Install title
    ui.draw(3)
    assert ui.app.tour.awaiting
    ui.click("tab_search")
    assert not ui.app.tour.awaiting and ui.app.model.tab == 1
    ui.app.tour.stop()


def test_the_tour_cards_next_button_answers_over_the_table(ui):
    ui.click("guide")
    ui.press_text("Next \u25ba")
    assert ui.app.tour.step_idx == 1


def test_nothing_in_the_real_home_is_touched(ui, tmp_path):
    """Hermetic: HOME and the settings folders are the test's temporary ones, and every file the run made is under tmp_path."""
    import os
    from pathlib import Path

    assert Path.home() == tmp_path / "home" and os.environ["CHISURF_SETTINGS_DIR"].startswith(str(tmp_path))
    for name in ("MMFDB_SETTINGS_DIR", "MMFDB_DATABASE_PATH"):
        assert os.environ[name].startswith(str(tmp_path))
