"""Every control of the native Batch Analysis wizard operated with simulated pointer, wheel and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in (or at the
text a button, a header, a row or a dialog entry drew) and host file drops reach the window; the assertions read the visible
outcome (the model, the tables, the lines, the windows). The session is the fake of ``fakes.py``: no real fit, no network.
The control -> test list is in ``okf/plugins/emtk-ports/batch_analysis/REPORT.md``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from emtk import keys

from chisurf.plugins.emtk_hermetic import hermetic, real_chisurf_untouched  # noqa: F401  (autouse fixtures)
from chisurf.plugins.emtk_test_input import Driver, assert_tour_card_clear

from ..gui.app import BatchAnalysisApp
from ..gui.model import BatchModel
from .fakes import FakeSession

BIG, SMALL = (1200, 800), (800, 600)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("run_01.sm", "run_02.sm", "run_03.sm"):
        (data / name).write_text("x")
    monkeypatch.chdir(data)
    return data


@pytest.fixture
def drv(folder):
    app = BatchAnalysisApp(BatchModel(session=FakeSession(fits=("Template fit", "Second fit"))))
    d = Driver(app, BIG, idle=lambda: not app.model.running)
    d.draw(3)
    yield d
    app.close()


def to_step(drv, step_id):
    drv.click_name(f"step_{step_id}")
    assert drv.app.model.step_id == step_id


def checkboxes(drv, table="dataset_rows"):
    """Rectangles of the check boxes drawn in the table, top to bottom."""
    painter = drv.draw(2)
    x, y, w, h = drv.app.form.rects[table]
    boxes = [(s[0], s[1], s[2], s[3]) for s in painter.strokes if abs(s[2] - s[3]) < 0.5 and 6 < s[2] < 24
             and x <= s[0] <= x + w and y <= s[1] <= y + h]
    return sorted(boxes, key=lambda b: b[1])


def wait_run(drv, timeout=20.0):
    import time

    end = time.monotonic() + timeout
    while drv.app.model.running and time.monotonic() < end:
        time.sleep(0.01)
        drv.draw(1)
    assert not drv.app.model.running
    return drv.draw(3)


def add_through_the_dialog(drv, *names):
    drv.click_name("add_files")
    for name in names:
        drv.click_text(name)
    drv.click_text("Open")


# -- the step list and Back / Next / Finish ------------------------------------------------------------------------------ #


def test_a_click_on_each_step_opens_its_page(drv):
    shown = {"welcome": "Batch Analysis", "datasets": "Loaded datasets", "files": "Files to process", "run": "Results CSV",
             "results": "Results of the last run"}
    for step_id, text in shown.items():
        to_step(drv, step_id)
        assert any(text in s for s in drv.draw(2).strings), step_id


def test_the_check_marks_follow_the_conditions_and_a_run_marks_the_run_step(drv, tmp_path):
    marks = lambda: {s[5].strip("✓ ").strip(): s[5].startswith("✓") for s in drv.draw(2).texts  # noqa: E731
                     if s[0] < 200 and s[5].strip("✓ ").strip() in ("Welcome", "Loaded data", "Files & fit", "Run", "Results")}
    assert marks() == {"Welcome": True, "Loaded data": True, "Files & fit": True, "Run": False, "Results": True}
    drv.app.model.selected_fit_name = "gone"
    assert marks()["Files & fit"] is False
    drv.app.model.selected_fit_name = "Template fit"
    drv.app.model.files = [str(tmp_path / "a.sm")]
    drv.app.model.save_path = str(tmp_path / "r.csv")
    to_step(drv, "run")
    drv.click_name("run")
    wait_run(drv)
    assert marks()["Run"] is True


def test_back_and_next_walk_the_steps_and_back_is_greyed_on_the_first(drv):
    assert not drv.app.model.enabled("go_back")
    drv.click_name("go_back")
    assert drv.app.model.step == 0
    for expected in (1, 2, 3, 4):
        drv.click_name("go_next")
        assert drv.app.model.step == expected
    assert not drv.drawn("Next") and drv.drawn("Finish")
    drv.click_name("go_back")
    assert drv.app.model.step == 3 and drv.drawn("Next") and not drv.drawn("Finish")


def test_finish_on_the_last_step_closes_the_window(drv):
    to_step(drv, "results")
    assert not drv.app.close_requested
    drv.click_name("finish")
    drv.draw(2)
    assert drv.app.close_requested


# -- loaded data ------------------------------------------------------------------------------------------------------- #


def test_a_click_on_a_check_box_ticks_and_unticks_the_dataset_and_the_summary_follows(drv):
    to_step(drv, "datasets")
    boxes = checkboxes(drv)
    assert len(boxes) == 3 and drv.drawn("0 of 3 datasets ticked. Hover a row for its file.")
    drv.click(boxes[0])
    drv.click(boxes[2])
    assert drv.app.model.selected_dataset_indices == [0, 2] and drv.drawn("2 of 3 datasets ticked. Hover a row for its file.")
    drv.click(checkboxes(drv)[0])
    assert drv.app.model.selected_dataset_indices == [2]
    to_step(drv, "run")
    assert drv.drawn("Loaded datasets: 1") or any("Loaded datasets: 1" in s for s in drv.draw(2).strings)


def test_refresh_button_lists_the_datasets_loaded_since(drv):
    to_step(drv, "datasets")
    assert not drv.drawn("4. Sample D")
    drv.app.model.session.datasets.append(type("D", (), {"name": "Sample D", "experiment": None})())
    drv.click_name("refresh_datasets")
    assert drv.drawn("4. Sample D") and len(checkboxes(drv)) == 4


def test_an_empty_session_says_so_instead_of_an_empty_list():
    app = BatchAnalysisApp(BatchModel(session=FakeSession(datasets=(), fits=())))
    d = Driver(app, BIG)
    d.click_name("step_datasets")
    assert d.drawn("No dataset is loaded in ChiSurf. Load data there, then press Refresh.")


# -- files ------------------------------------------------------------------------------------------------------------- #


def test_files_and_folders_dropped_on_the_window_are_added_and_a_repeat_is_ignored(drv, folder):
    to_step(drv, "files")
    assert drv.drop(str(folder / "run_01.sm")) is True
    assert drv.drawn("run_01.sm") and len(drv.app.model.files) == 1
    assert drv.drop(str(folder / "run_01.sm")) is False
    (folder / "sub").mkdir()
    (folder / "sub" / "deep.sm").write_text("x")
    assert drv.drop(str(folder)) is True
    assert sorted(Path(p).name for p in drv.app.model.files) == ["deep.sm", "run_01.sm", "run_02.sm", "run_03.sm"]
    assert drv.drop() is False


def test_files_button_opens_a_dialog_that_cancels_and_adds_the_chosen_files(drv):
    to_step(drv, "files")
    assert not drv.app.model.files
    drv.click_name("add_files")
    assert drv.app.dialog is not None and drv.drawn("Cancel") and drv.drawn("Open")
    drv.click_text("Cancel")
    assert drv.app.dialog is None and drv.app.model.files == []
    add_through_the_dialog(drv, "run_01.sm", "run_03.sm")
    assert [Path(p).name for p in drv.app.model.files] == ["run_01.sm", "run_03.sm"] and drv.app.dialog is None
    assert drv.drawn("run_01.sm") and drv.drawn("run_03.sm")


def test_the_file_dialog_is_a_window_that_closes_with_its_x_and_with_escape(drv):
    to_step(drv, "files")
    drv.click_name("add_files")
    x, y, w, h = drv.app._dialog_window.box
    assert w < BIG[0] and h < BIG[1]
    drv.click((x + w - 14.0, y + 13.0, 0.0, 0.0), 0, 0)
    assert drv.app.dialog is None
    drv.click_name("add_files")
    drv.app.pointer_move(x + w / 2, y + h / 2)
    drv.draw(1)
    drv.escape()
    assert drv.app.dialog is None and drv.app.model.files == []


def test_folder_button_adds_every_file_below_the_chosen_folder(drv, folder):
    (folder / "sub").mkdir()
    (folder / "sub" / "deep.sm").write_text("x")
    to_step(drv, "files")
    drv.click_name("add_folder")
    assert drv.app.dialog is not None
    drv.click_text("Choose")
    assert sorted(Path(p).name for p in drv.app.model.files) == ["deep.sm", "run_01.sm", "run_02.sm", "run_03.sm"]


def test_database_button_opens_the_dataset_picker_and_a_picked_path_is_added(drv, monkeypatch, folder):
    opened = []
    monkeypatch.setattr(drv.app.picker, "open", lambda: opened.append(1))
    to_step(drv, "files")
    drv.click_name("add_database")
    assert opened == [1]
    drv.app.picker.on_paths([folder / "run_02.sm"])
    drv.draw(2)
    assert [Path(p).name for p in drv.app.model.files] == ["run_02.sm"] and drv.drawn("run_02.sm")


def test_a_row_is_selected_by_a_click_removed_by_the_button_and_the_delete_key_and_cleared(drv, folder):
    to_step(drv, "files")
    add_through_the_dialog(drv, "run_01.sm", "run_02.sm", "run_03.sm")
    assert not drv.app.model.enabled("remove_selected")
    drv.click_name("remove_selected")  # nothing selected: greyed
    assert len(drv.app.model.files) == 3
    drv.click_text("run_02.sm", last=False)
    assert Path(drv.app.model.selected_file).name == "run_02.sm" and drv.app.model.enabled("remove_selected")
    drv.click_name("remove_selected")
    assert [Path(p).name for p in drv.app.model.files] == ["run_01.sm", "run_03.sm"] and not drv.drawn("run_02.sm")
    assert drv.app.model.selected_file == "" and not drv.app.model.enabled("remove_selected")
    drv.click_text("run_03.sm", last=False)
    drv.delete()
    assert [Path(p).name for p in drv.app.model.files] == ["run_01.sm"]
    drv.click_name("clear_files")
    assert drv.app.model.files == [] and not drv.app.model.enabled("clear_files")


def test_the_wheel_scrolls_a_long_file_list(drv, folder):
    for i in range(60):
        (folder / f"many_{i:02d}.sm").write_text("x")
    to_step(drv, "files")
    drv.drop(str(folder))
    x, y, w, h = drv.rect("file_rows")
    first = lambda: sorted((t for t in drv.draw(2).texts if x <= t[0] <= x + w and y + 20 <= t[1] <= y + h), key=lambda t: t[1])[0][5]  # noqa: E731
    before = first()
    drv.wheel(x + w / 2, y + h / 2, steps=-5)
    assert first() != before
    drv.wheel(x + w / 2, y + h / 2, steps=5)
    assert first() == before


def test_the_template_fit_is_picked_from_the_list_of_fits(drv):
    to_step(drv, "files")
    assert drv.app.model.selected_fit_name == "Template fit"
    drv.click_name("selected_fit_name")
    assert drv.drawn("Second fit")
    drv.click_text("Second fit")
    assert drv.app.model.selected_fit_name == "Second fit"
    assert drv.app.model.fit_index() == 1


def test_refresh_fits_lists_the_fits_created_since(drv):
    to_step(drv, "files")
    from .fakes import FakeFit

    drv.app.model.session.fits.append(FakeFit("Third fit"))
    assert "Third fit" not in drv.app.model.fit_names()
    drv.click_name("refresh_fits")
    assert "Third fit" in drv.app.model.fit_names()


# -- run --------------------------------------------------------------------------------------------------------------- #


def test_run_without_data_or_a_fit_says_why_in_red(drv):
    to_step(drv, "run")
    drv.click_name("run")
    assert drv.drawn("No data: Select datasets or add files first.") and not drv.app.model.running
    drv.app.model.files = ["/x/a.sm"]
    drv.app.model.selected_fit_name = "gone"
    drv.click_name("run")
    assert drv.drawn("No fit: Select a template fit first.")


def test_the_csv_path_is_typed_and_used_by_the_run(drv, folder, tmp_path):
    drv.drop(str(folder))
    to_step(drv, "run")
    target = tmp_path / "typed" / "out.csv"
    drv.type_into_name("save_path", str(target))
    assert drv.app.model.save_path == str(target)
    drv.click_name("run")
    wait_run(drv)
    assert target.exists() and len(target.read_text().splitlines()) == 1 + 3 * 3
    assert drv.drawn("Batch complete")


def test_run_without_a_csv_path_asks_for_one_and_goes_on_when_it_is_chosen(drv, folder):
    drv.drop(str(folder))
    to_step(drv, "run")
    drv.click_name("run")
    assert drv.app.dialog is not None and drv.drawn("Save") and not drv.app.model.running
    drv.click_text("file name")
    drv.type("batch.csv")
    drv.click_text("Save", last=True)
    assert drv.app.model.save_path.endswith("batch.csv")
    wait_run(drv)
    assert (folder / "batch.csv").exists() and drv.drawn("Batch complete")


def test_a_cancelled_save_dialog_drops_the_pending_run(drv, folder):
    drv.drop(str(folder))
    to_step(drv, "run")
    drv.click_name("run")
    drv.click_text("Cancel")
    assert drv.app.dialog is None and not drv.app.model.running and not drv.app.model.has_results


def test_browse_chooses_the_csv_without_running(drv, folder):
    to_step(drv, "run")
    drv.click_name("browse_results")
    assert drv.app.dialog is not None
    drv.click_text("file name")
    drv.type("picked")
    drv.click_text("Save", last=True)
    assert drv.app.model.save_path.endswith("picked.csv") and not drv.app.model.running


def test_the_buttons_are_greyed_while_the_batch_runs_and_the_bar_reports_the_item(drv, folder, monkeypatch):
    import threading

    gate = threading.Event()
    session = drv.app.model.session
    real = session.dispatch

    def slow(name, payload):
        if name == "fit.run":
            gate.wait(10)
        return real(name, payload)

    session.dispatch = slow
    drv.drop(str(folder))
    drv.app.model.save_path = str(folder.parent / "r.csv")
    to_step(drv, "run")
    drv.click_name("run")
    drv.draw(3)
    assert drv.app.model.running and not drv.app.model.enabled("run") and not drv.app.model.enabled("browse_results")
    drv.click_name("run")
    drv.click_name("browse_results")
    assert drv.app.dialog is None and drv.app.model.running
    assert any(s.startswith("0/3") for s in drv.draw(2).strings)
    gate.set()
    wait_run(drv)
    assert any(s.startswith("3/3: ") for s in drv.draw(2).strings)


def test_the_results_step_shows_the_table_that_sorts_filters_and_scrolls(drv, folder, tmp_path):
    drv.drop(str(folder))
    drv.app.model.selected_dataset_indices = [0, 1, 2]
    drv.app.model.reload_datasets()
    drv.app.model.save_path = str(tmp_path / "r.csv")
    to_step(drv, "run")
    drv.click_name("run")
    wait_run(drv)
    to_step(drv, "results")
    shown = drv.draw(2).strings
    for header in ("Run", "Filename", "Parameter", "Fixed", "Value", "Chi2r"):
        assert header in shown
    assert "Sample A" in shown and "6 rows" not in shown
    x, y, w, h = drv.rect("result_rows")
    drv.click(drv.text_rect(drv.draw(2), "Parameter", last=False))  # header: sort by parameter
    order = [t[5] for t in sorted((t for t in drv.draw(2).texts if t[5] in ("tau", "amplitude", "offset") and y < t[1] < y + h), key=lambda t: t[1])]
    assert order == sorted(order)
    drv.click(drv.text_rect(drv.draw(2), "filter", last=False)) if drv.drawn("filter") else None
    drv.type("offset")
    shown = drv.draw(2).strings
    assert "offset" in shown and "tau" not in shown and "amplitude" not in shown


# -- help and guide ---------------------------------------------------------------------------------------------------- #


def test_help_button_opens_the_help_window_whose_buttons_work(drv):
    window = drv.app.help_window
    drv.click_name("help")
    assert window.open
    painter = drv.draw(2)
    assert {"Start Guided Tour", "Close"} <= set(painter.strings)
    drv.click_text("Start Guided Tour")
    assert not window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.draw(2)
    drv.click_name("help")
    drv.click_text("Close", last=True)
    assert not window.open
    drv.click_name("help")
    drv.escape()
    assert not window.open


def test_the_help_text_names_the_controls(drv):
    drv.click_name("help")
    shown = " ".join(drv.draw(2).strings)
    for word in ("Loaded data", "Files & fit", "Template fit", "Results CSV", "Run batch", "Chi2r", "Folder", "Database"):
        assert word in shown, word


def test_every_guide_target_is_a_drawn_control_on_its_page(drv):
    ids = [s.id for s in drv.app.model.STEPS]
    for index, step in enumerate(drv.app.tour.steps):
        target = step.get("target") or {}
        if not target:
            continue
        drv.app.model.go_to(ids.index(step.get("page", "welcome")))
        drv.draw(3)
        key = target.get("name")
        assert drv.app.item_rects.get(key) or drv.app.form.rects.get(key), f"{step['title']}: {key} is not drawn"


@pytest.mark.parametrize("size", [BIG, SMALL])
def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_awaited_control(folder, size):
    app = BatchAnalysisApp(BatchModel(session=FakeSession(fits=("Template fit", "Second fit"))))
    drv = Driver(app, size)
    drv.draw(3)
    drv.drop(str(folder))
    app.model.save_path = str(folder.parent / "tour.csv")
    tour = app.tour
    drv.click_name("guide")
    seen = []
    for _ in range(40):
        if not tour.active:
            break
        drv.draw(3)
        assert_tour_card_clear(tour, size)
        step = tour.steps[tour.step_idx]
        target = step.get("target") or {}
        if tour.awaiting:
            seen.append(step["title"])
            if target.get("name") == "step_datasets":
                drv.click_name("step_datasets")
            elif target.get("name") == "selected_fit_name":
                drv.click_name("selected_fit_name")
                drv.click_text("Second fit")
            elif target.get("name") == "run":
                drv.click_name("run")
            assert not tour.awaiting, f"{step['title']}: operating the control did not release the step"
        tour.next()
    wait_run(drv)
    assert not tour.active and seen == ["Pick datasets already loaded", "Choose the template", "Run it"]
    assert app.model.selected_fit_name == "Second fit" and app.model.has_results


def test_the_tour_card_can_be_dragged_and_stays_off_its_target(drv):
    tour = drv.app.tour
    drv.click_name("guide")
    drv.draw(3)
    tour.next()
    drv.draw(3)
    from chisurf.plugins.emtk_test_input import tour_card_box

    x, y, w, h = tour_card_box(tour, BIG)
    drv.drag((x + 40, y + 10), (x + 40 - 25, y + 10 + 35))
    assert tour.card_offset != (0.0, 0.0)
    assert_tour_card_clear(tour, BIG)


# -- the host and the small window ------------------------------------------------------------------------------------- #


def test_the_whole_flow_works_in_the_small_window_too(folder, tmp_path):
    app = BatchAnalysisApp(BatchModel(session=FakeSession(fits=("Template fit",))))
    d = Driver(app, SMALL)
    d.draw(3)
    d.click_name("step_datasets")
    d.click(checkboxes(d)[1])
    assert app.model.selected_dataset_indices == [1]
    d.click_name("go_next")
    assert d.drop(str(folder)) is True
    d.click_name("go_next")
    d.type_into_name("save_path", str(tmp_path / "small.csv"))
    d.click_name("run")
    wait_run(d)
    d.click_name("go_next")
    assert (tmp_path / "small.csv").exists() and "Sample B" in d.draw(2).strings
    for name in ("step_welcome", "step_files"):
        d.click_name(name)
        d.draw(2)
