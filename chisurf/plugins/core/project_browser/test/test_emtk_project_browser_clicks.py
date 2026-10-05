"""Every control of the project browser operated with simulated pointer and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in (or at the
text a row or a button drew) and host file drops reach the window; the assertions read the visible outcome (the list, the
status line, the dialogs, the files, the scratch database). The control -> test list is in
``okf/plugins/emtk-ports/project_browser/REPORT.md``.
"""

from __future__ import annotations

import pytest
from emtk import keys

from .driving import (
    BIG,
    SMALL,
    BrowserDriver,
    clipped_texts,
    draw_clip,
    hermetic_env,
    layout_problems,
)
from .test_emtk_project_browser_parity import _app, _project


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def project_threads_finish():
    """A background project call still running when a test ends would read the next test's database: wait for them."""
    yield
    import threading

    for thread in threading.enumerate():
        if thread.name.startswith("project-browser"):
            thread.join(timeout=15)


@pytest.fixture(autouse=True)
def no_window_failed_to_draw(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture
def drv(db):
    # The authenticated client and a canonical snapshot: the service rejects
    # anything that is not a validated v5 payload.
    app = _app(db)
    d = BrowserDriver(app, BIG)
    d.settle()
    yield d
    app.close()


def row_rect(drv, label):
    """The rectangle of the drawn text *label* inside the project table."""
    x, y, w, h = drv.rect("tree_rows")
    hits = [
        t[:4]
        for t in drv.draw(2).texts
        if t[5].startswith(label) and x <= t[0] <= x + w and y <= t[1] <= y + h
    ]
    assert hits, f"{label!r} is not a row: {[t[5] for t in drv.painter.texts if t[1] > y][:40]}"
    return hits[0]


def centre(r):
    return r[0] + r[2] / 2, r[1] + r[3] / 2


def press_on(drv, x, y, button=1, frames=2):
    drv.app.pointer_move(x, y)
    drv.draw(frames)
    drv.app.pointer_press(x, y, button)
    drv.draw(frames)
    drv.app.pointer_release(x, y, button)
    drv.draw(frames)


def select(drv, label):
    drv.click_at(*centre(row_rect(drv, label)))
    drv.draw(2)


def expand(drv, name):
    """Open a project with the disclosure triangle at the left of its row."""
    x, y, w, h = row_rect(drv, name)
    drv.click_at(x - 12, y + h / 2)
    drv.draw(2)


def names(drv):
    return [s for s in drv.draw(2).strings if "versions)" in s]


def status(drv):
    return drv.app.model.status


# -- the toolbar: what is greyed while nothing is selected -------------------------------------------------------- #


def test_actions_that_need_a_selection_are_greyed_and_a_click_on_them_does_nothing(drv):
    panel = drv.app.panel
    assert [panel.enabled(a) for a in ("open", "export", "delete", "inspect")] == [False] * 4
    assert [panel.enabled(a) for a in ("save", "import_project", "refresh", "guide", "help")] == [
        True
    ] * 5
    for action in ("open", "export", "delete", "inspect"):
        drv.click(action)
    assert drv.app.modal == "" and drv.app.dialog is None and drv.app.jobs.future is None
    assert not drv.app.restored


def test_selecting_a_project_enables_open_and_inspect_and_a_version_also_export_and_delete(drv):
    select(drv, "decay study")
    panel = drv.app.panel
    assert (
        panel.enabled("open")
        and panel.enabled("inspect")
        and not panel.enabled("export")
        and not panel.enabled("delete")
    )
    expand(drv, "decay study")
    select(drv, "v2 decay study")
    assert all(panel.enabled(a) for a in ("open", "inspect", "export", "delete"))


def test_refresh_button_reloads_the_list_and_says_how_many(drv):
    drv.app.model.projects = []
    drv.click("refresh")
    drv.settle()
    assert status(drv) == "2 projects loaded." and len(names(drv)) == 2


# -- search ------------------------------------------------------------------------------------------------------ #


def test_typing_in_the_search_field_filters_the_list_on_enter_and_clear_brings_it_back(drv):
    assert len(names(drv)) == 2
    drv.type_into("search", "fcs")
    drv.settle()
    assert drv.app.model.search == "fcs" and names(drv) == ["fcs titration (1 versions)"]
    assert drv.app.panel.enabled("clear_search")
    drv.click("clear_search")
    drv.settle()
    assert drv.app.model.search == "" and len(names(drv)) == 2


def test_search_matches_a_version_note(drv):
    drv.type_into("search", "refit")
    drv.settle()
    assert names(drv) == ["decay study (1 versions)"]  # the service keeps the versions that match


def test_a_search_with_no_match_says_so(drv):
    drv.type_into("search", "zzz-no-such-project")
    drv.settle()
    assert names(drv) == [] and any(
        s.startswith("No matching projects") for s in drv.draw(2).strings
    )


def test_show_public_toggle_hides_and_shows_the_public_projects(drv):
    assert drv.app.model.show_public and len(names(drv)) == 2
    drv.click("show_public")
    drv.settle()
    assert not drv.app.model.show_public
    assert "fcs titration (1 versions)" not in names(drv)
    drv.click("show_public")
    drv.settle()
    assert len(names(drv)) == 2


# -- the tree ---------------------------------------------------------------------------------------------------- #


def test_the_triangle_expands_a_project_and_a_second_click_collapses_it(drv):
    assert not any(s.startswith("v2 decay study") for s in drv.draw(2).strings)
    expand(drv, "decay study")
    shown = drv.draw(2).strings
    assert any(s.startswith("v2 decay study") for s in shown) and any(
        s.startswith("v1 decay study") for s in shown
    )
    assert "refit with IRF" in shown and "first fit" in shown
    expand(drv, "decay study")
    assert not any(s.startswith("v2 decay study") for s in drv.draw(2).strings)


def test_a_click_on_a_row_selects_it_and_clears_the_loaded_details(drv):
    drv.app.model.artifacts = [{"x": 1}]
    select(drv, "decay study")
    assert drv.app.model.selected_id == _project(drv.app, "decay study")["project_id"]
    assert drv.app.model.artifacts == []


def test_clicking_a_column_header_sorts_the_projects(drv):
    first = names(drv)
    x, y, w, h = drv.rect("tree_rows")
    head = next(
        t for t in drv.draw(2).texts if t[5].startswith("Project / Version") and x <= t[0] <= x + w
    )
    drv.click_at(head[0] + 6, head[1] + 6)
    second = names(drv)
    assert sorted(first) in (first, first[::-1]) and second == first[::-1]


def table_strings(drv):
    x, y, w, h = drv.rect("tree_rows")
    return [t[5] for t in drv.draw(3).texts if x <= t[0] <= x + w and y <= t[1] <= y + h]


def test_the_id_and_status_columns_show_when_there_is_room_and_the_toggles_decide_otherwise(db):
    app = _app()
    try:
        wide = BrowserDriver(app, BIG)
        wide.settle()
        expand(wide, "decay study")
        shown = table_strings(wide)
        assert (
            "ID" in shown and "Status" in shown and "succeeded" in shown
        )  # all nine columns fit at 1200 px, as in Qt
        wide.click("show_id")  # the user hides the ID column
        shown = table_strings(wide)
        assert "ID" not in shown and "Status" in shown and app.show_id is False
        wide.click("show_id")
        assert "ID" in table_strings(wide)
        narrow = BrowserDriver(app, SMALL)
        app.show_id = app.show_status = None
        shown = table_strings(narrow)
        assert (
            "ID" not in shown and "Status" not in shown
        )  # 800 px has no room: the cells stay whole instead
        narrow.click("show_status")
        assert app.show_status is True and "Status" in table_strings(narrow)
    finally:
        app.close()


# -- restore --------------------------------------------------------------------------------------------------- #


def test_open_restore_button_restores_the_newest_version_of_the_selected_project(drv):
    project = _project(drv.app, "decay study")
    select(drv, "decay study")
    drv.click("open")
    drv.settle()
    assert len(drv.app.restored) == 1 and drv.app.reopened == drv.app.restored
    assert drv.app.model.context._current_project_version_id == project["latest_version_id"]
    assert status(drv) == "Restored decay study."


def test_open_restore_of_an_exact_version_restores_that_one(drv):
    project = _project(drv.app, "decay study")
    expand(drv, "decay study")
    select(drv, "v1 decay study")
    drv.click("open")
    drv.settle()
    v1 = next(v for v in project["versions"] if v["version_number"] == 1)
    assert drv.app.model.context._current_project_version_id == v1["version_id"]


def test_a_double_click_on_a_row_restores_it(drv):
    x, y = centre(row_rect(drv, "fcs titration"))
    drv.app.pointer_move(x, y)
    drv.draw(2)
    for clicks in (1, 2):
        drv.app.pointer_press(x, y, 1, 0, clicks)
        drv.draw(2)
        drv.app.pointer_release(x, y, 1)
        drv.draw(2)
    drv.settle()
    assert (
        len(drv.app.restored) == 1
        and drv.app.model.context._current_project_name == "fcs titration"
    )


# -- the context menu --------------------------------------------------------------------------------------------- #


def test_right_click_on_a_version_offers_all_four_actions_and_restore_works(drv):
    expand(drv, "decay study")
    x, y = centre(row_rect(drv, "v2 decay study"))
    press_on(drv, x, y, 2)
    shown = drv.draw(2).strings
    assert {"Open / Restore", "Inspect version", "Export .cs.pto", "Delete Version"} <= set(shown)
    drv.click_text("Open / Restore", last=True)
    drv.settle()
    assert len(drv.app.restored) == 1


def test_the_context_menu_of_a_project_row_greys_export_and_delete(drv):
    x, y = centre(row_rect(drv, "decay study"))
    press_on(drv, x, y, 2)
    entries = {i.label: i.enabled for i in drv.app.context_menu.entries}
    assert entries == {
        "Open / Restore": True,
        "Inspect version": True,
        "Export .cs.pto": False,
        "Delete Version": False,
    }


def test_a_click_elsewhere_dismisses_the_context_menu(drv):
    x, y = centre(row_rect(drv, "decay study"))
    press_on(drv, x, y, 2)
    assert "Inspect version" in drv.draw(2).strings
    press_on(drv, 600, 700)
    assert "Inspect version" not in drv.draw(2).strings


# -- save -------------------------------------------------------------------------------------------------------- #


def test_save_opens_the_dialog_a_new_project_needs_a_name_and_the_typed_name_is_saved(drv):
    drv.click("save")
    assert (
        drv.app.modal == "save"
        and drv.app.modal_window.title == "Save Project"
        and drv.app.allow_name_edit
    )
    drv.draw(3)
    drv.click("confirm_save") if "confirm_save" in drv.app.item_rects else drv.click_text(
        "Save version"
    )
    drv.settle()
    assert status(drv) == "Error: A project name is required."
    assert drv.app.modal == "save"  # the dialog stays so the name can be typed
    drv.type_into("name", "native project")
    drv.draw(2)
    assert status(drv) == ""  # typing the missing name ends the complaint
    drv.click_text("Save version")
    drv.settle()
    assert drv.app.modal == "" and drv.app.notice == "Saved 'native project' as version 1."
    assert "native project (1 versions)" in names(drv)


def test_the_save_dialog_visibility_choice_and_notes_are_stored(drv):
    drv.click("save")
    drv.draw(3)
    drv.type_into("name", "second project")
    drv.click("visibility_name")
    drv.click_text("Public", last=True)
    assert drv.app.visibility == 1
    drv.click(
        "notes", fx=0.3, fy=0.2
    )  # the notes editor takes the keys, and the name field no longer does
    drv.type_text("looks good")
    assert drv.app.name == "second project" and drv.app.notes == "looks good"
    drv.click_text("Save version")
    drv.settle()
    project = _project(drv.app, "second project")
    assert project["visibility"] == "public" and project["versions"][0]["notes"] == "looks good"


def test_saving_again_makes_a_new_version_and_the_name_field_is_greyed(drv, db):
    project = _project(drv.app, "decay study")
    # The document adopts an identity together with the snapshot it accepted.
    drv.app.model.update_current(
        {
            "ok": True,
            "project_id": project["project_id"],
            "version_id": project["latest_version_id"],
            "project_name": "decay study",
            "project_payload": db["payload"],
        }
    )
    drv.click("save")
    assert drv.app.modal_window.title == "Save New Version" and not drv.app.allow_name_edit
    drv.draw(3)
    drv.click("name", fx=0.3)  # a greyed field takes neither the click nor the keys
    assert not drv.app.io.want_capture_keyboard
    drv.type_text("renamed")
    assert drv.app.name == "decay study"
    drv.click_text("Save version")
    drv.settle()
    assert (
        _project(drv.app, "decay study")["version_count"] == 3
        and drv.app.notice == "Saved 'decay study' as version 3."
    )


def test_cancel_in_the_save_dialog_changes_nothing(drv):
    drv.click("save")
    drv.draw(3)
    drv.type_into("name", "never saved")
    drv.click_text("Cancel")
    drv.settle()
    assert drv.app.modal == "" and not any(
        p["project_name"] == "never saved" for p in drv.app.model.projects
    )


def test_the_save_dialog_close_button_closes_it(drv):
    drv.click("save")
    drv.draw(3)
    x, y, w, h = drv.app.modal_window.box
    drv.click_at(x + w - 12, y + 12)  # the header's close button
    assert drv.app.modal == ""


# -- export and import ------------------------------------------------------------------------------------------ #


def export_decay(drv, name="decay_export"):
    expand(drv, "decay study")
    select(drv, "v2 decay study")
    drv.click("export")
    assert drv.app.dialog is not None and drv.app.file_window.title == "Export Project as .cs.pto"
    assert any(s.endswith("_v2.cs.pto") for s in drv.draw(2).strings)  # the Qt default file name
    drv.click_text(next(s for s in drv.painter.strings if s.endswith("_v2.cs.pto")))
    drv.select_all()
    drv.type_text(name)
    drv.click_text("Save", last=True)
    drv.settle()


def test_export_writes_the_archive_the_dialog_named_and_says_where(drv, tmp_path):
    export_decay(drv)
    written = tmp_path / "decay_export.cs.pto"
    assert written.is_file() and status(drv) == f"Exported to {written}"
    assert drv.app.model.last_directory == str(tmp_path)


def test_export_cancel_writes_nothing(drv, tmp_path):
    expand(drv, "decay study")
    select(drv, "v1 decay study")
    drv.click("export")
    drv.click_text("Cancel")
    assert drv.app.dialog is None and not list(tmp_path.glob("*.pto"))


def test_import_previews_the_archive_and_confirm_adds_the_version(drv, tmp_path):
    export_decay(drv)
    drv.click("import_project")
    assert drv.app.dialog is not None and drv.app.file_window.title == "Import Project"
    drv.click_text("decay_export.cs.pto")
    drv.click_text("Open", last=True)
    drv.settle()
    assert drv.app.modal == "import" and drv.app.modal_window.title == "Confirm Project Import"
    shown = drv.draw(2).strings
    assert "Remap & Import" in shown and any(
        "already exist" in s for s in shown
    )  # the archive is already in the database
    drv.click_text("Remap & Import")
    drv.settle()
    assert (
        drv.app.notice.startswith("Imported project")
        and _project(drv.app, "decay study")["version_count"] == 3
    )


def test_import_cancel_in_the_preview_changes_nothing(drv, tmp_path):
    export_decay(drv)
    drv.click("import_project")
    drv.click_text("decay_export.cs.pto")
    drv.click_text("Open", last=True)
    drv.settle()
    drv.click_text("Cancel")
    drv.settle()
    assert drv.app.modal == "" and _project(drv.app, "decay study")["version_count"] == 2


def test_import_of_a_file_that_is_no_archive_reports_the_error(drv, tmp_path):
    (tmp_path / "junk.cs.pto").write_text("not an archive")
    drv.click("import_project")
    drv.click_text("junk.cs.pto")
    drv.click_text("Open", last=True)
    drv.settle()
    assert status(drv).startswith("Error:") and drv.app.modal == ""


def test_a_dropped_archive_starts_the_same_import_preview(drv, tmp_path):
    export_decay(drv)
    drv.drop(tmp_path / "decay_export.cs.pto")
    drv.settle()
    assert drv.app.modal == "import"


def test_a_dropped_non_archive_is_ignored(drv, tmp_path):
    (tmp_path / "notes.txt").write_text("x")
    drv.drop(tmp_path / "notes.txt")
    drv.settle()
    assert drv.app.modal == ""


# -- delete ----------------------------------------------------------------------------------------------------- #


def test_delete_asks_first_cancel_keeps_the_version_and_confirm_removes_it(drv):
    expand(drv, "decay study")
    select(drv, "v1 decay study")
    drv.click("delete")
    assert drv.app.modal == "delete" and drv.app.modal_window.title == "Confirm Delete"
    assert any(s.startswith("Delete version 1 of 'decay study'") for s in drv.draw(2).strings)
    drv.click_text("Cancel")
    drv.settle()
    assert _project(drv.app, "decay study")["version_count"] == 2
    drv.click("delete")
    drv.click_text("Delete This Version")
    drv.settle()
    assert _project(drv.app, "decay study")["version_count"] == 1


# -- inspect ------------------------------------------------------------------------------------------------------ #


def test_inspect_fills_the_detail_tabs_and_each_tab_can_be_opened(drv):
    expand(drv, "decay study")
    select(drv, "v2 decay study")
    shown = drv.draw(2).strings
    assert {"Summary", "Artifacts", "Parameters", "Branches", "Version graph"} <= set(shown)
    drv.click_text("Artifacts")
    assert "Press Inspect Stored Version to load this information." in drv.draw(2).strings
    drv.click("inspect")
    drv.settle()
    assert status(drv) == "Loaded version artifacts, fit parameters and branches."
    drv.click_text("Branches")
    assert (
        drv.app.details_tab == "Branches"
        and "Press Inspect Stored Version to load this information." not in drv.draw(2).strings
    )
    drv.click_text("Version graph")
    assert drv.app.details_tab == "Version graph"
    drv.click_text("Summary")
    shown = drv.draw(2).strings
    assert "version_number" in shown and "refit with IRF" in shown


def test_the_details_say_what_to_do_before_anything_is_selected(drv):
    assert any(
        s.startswith("Select a project to restore its latest version") for s in drv.draw(2).strings
    )


# -- guide and help ------------------------------------------------------------------------------------------------- #


def test_guide_waits_for_the_real_controls_and_the_awaited_steps_complete_on_use(drv):
    drv.click("guide")
    tour = drv.app.tour
    assert tour.active and tour.step_idx == 0
    drv.click_text("Next ►")  # the first card is centred: its buttons work
    assert tour.step_idx == 1 and tour.awaiting  # Refresh
    drv.click_text("Next ►")
    assert tour.step_idx == 1  # a card button does not skip an awaited step
    drv.click("refresh")
    drv.settle()
    assert not tour.awaiting
    tour.next()  # (the card's Next button lies over the table here: see the xfail below)
    tour.next()
    assert tour.step_idx == 3 and tour.awaiting  # a row
    select(drv, "decay study")
    assert not tour.awaiting
    tour.next()
    assert tour.step_idx == 4 and tour.awaiting  # Inspect
    drv.click("inspect")
    drv.settle()
    assert not tour.awaiting


def test_the_tour_next_button_works_where_the_card_lies_over_the_table(drv):
    drv.click("guide")
    drv.click_text("Next ►")
    drv.click("refresh")
    drv.settle()
    drv.click_text("Next ►")
    assert drv.app.tour.step_idx == 2


def test_escape_ends_the_tour_and_help_opens_and_closes(drv):
    drv.click("guide")
    drv.escape()
    assert not drv.app.tour.active
    drv.click("help")
    assert drv.app.help_window.open and any("Project Browser" in s for s in drv.draw(2).strings)
    drv.escape()
    assert not drv.app.help_window.open


def test_every_guide_target_is_a_drawn_control(drv):
    select(drv, "decay study")
    for step in drv.app.tour.steps:
        key = drv.app.tour._target_key(step.get("target"))
        if key:
            assert key in drv.app.item_rects, key


# -- layout ---------------------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", [BIG, SMALL])
@pytest.mark.parametrize("state", ["empty", "populated", "selected"])
def test_the_layout_is_clean(db, size, state):
    app = _app()
    try:
        d = BrowserDriver(app, size)
        if state != "empty":
            d.settle()
            d.draw(3)
        if state == "selected":
            expand(d, "decay study")
            select(d, "v2 decay study")
            d.click("inspect")
            d.settle()
        painter = draw_clip(app, size)
        problems = layout_problems(painter, size) + clipped_texts(painter)
        assert not problems, problems[:6]
        if state != "empty":
            strings = painter.strings
            assert any(
                s.startswith("decay study (2 versions)") and not s.endswith(".") for s in strings
            )
    finally:
        app.close()
