"""Real input on the emtk TTTR image browser: pointer presses at the rectangles the controls were drawn in, typed text,
Enter, the mouse wheel over the image, drags, host file drops. Nothing here calls a model method to "click"; each test
reads the visible outcome (the model's answer to the input, the strings drawn, the files written).

Control -> test list: REPORT.md section 6a.
"""

import json
import pathlib
import time

import numpy as np
import pytest
from emtk import keys
from emtk.testing import PixelPainter

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, dialog_open, numeric_ticks, walk

from .conftest import two_detector_setup

pytestmark = pytest.mark.usefixtures("hermetic")

SP8 = "Leica_SP8.ptu"


class BrowserDriver(Driver):
    """The imaging driver, waiting for the browser's own workers (scan, mosaic load) as well.

    A press is preceded by the pointer arriving (a person moves before pressing): a press that teleports makes
    implot read the jump as a drag and pan the image.
    """

    def click_at(self, x: float, y: float, frames: int = 1) -> None:
        self.app.pointer_move(x, y)
        self.draw(1)
        super().click_at(x, y, frames)

    def busy(self) -> bool:
        app = self.app
        return bool(app.job.busy or app.load_job.busy or app._queue or app.model.wanted_image())

    def settle(self, timeout: float = 120.0, extra: int = 2):
        end = time.monotonic() + timeout
        self.draw(2)
        while self.busy() and time.monotonic() < end:
            time.sleep(0.02)
            self.draw(1)
        assert not self.busy(), "a worker did not finish"
        return self.draw(extra)


@pytest.fixture
def app():
    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

    application = make_app()
    yield application
    application.close()


@pytest.fixture
def drv(app):
    return BrowserDriver(app, (1000, 700))


@pytest.fixture
def opened(app, drv, photon_folder):
    """The app with the photon folder opened by a drop (the host's verb) and the two-detector setup in use."""
    app.model.apply_setup_settings(two_detector_setup())
    assert drv.drop(str(photon_folder))
    drv.settle()
    assert app.model.current_folder == str(photon_folder)
    return photon_folder


@pytest.fixture
def shown(app, drv, opened):
    """... and the SP8 file picked with a click on its row, its mosaic drawn."""
    drv.click_text(SP8)
    drv.settle()
    assert app.model.current_file == str(opened / SP8) and app.model.current_image() is not None
    return opened


def strings(drv):
    return list(drv.draw(1).strings)


def pixels(app, size=(1000, 700)):
    p = PixelPainter(*size)
    app.draw(p, 0, 0, *size)
    return np.frombuffer(bytes(p.px), dtype=np.uint8).reshape(size[1], size[0], 4)


# ---------------------------------------------------------------------------------------------------- toolbar: Open folder
def test_open_folder_opens_the_chooser_and_a_picked_folder_is_listed(app, drv, photon_folder):
    app.model.folder = str(photon_folder.parent)  # where the chooser starts: the remembered folder
    drv.click("choose_folder")
    assert dialog_open(drv) and app.dialog_kind == "folder"
    drv.click_text(f"[{photon_folder.name}]")
    drv.click_text("Choose", last=True)
    drv.settle()
    assert app.dialog is None and app.model.current_folder == str(photon_folder)
    assert "corrupt.ptu" in strings(drv) and SP8 in strings(drv)
    assert "2 image(s) in imgs" in strings(drv)


def test_the_folder_chooser_cancel_the_cross_and_escape_change_nothing(app, drv, photon_folder):
    app.model.folder = str(photon_folder.parent)
    for how in ("Cancel", "x", "escape"):
        drv.click("choose_folder")
        assert dialog_open(drv)
        if how == "Cancel":
            drv.click_text("Cancel", last=True)
        elif how == "x":
            drv.click_text("×", last=True)
        else:
            x, y, w, h = app.dialog_window.box
            drv.hover(x + w / 2, y + h / 2)  # Escape closes the window the pointer is over
            drv.escape()
        assert app.dialog is None, how
    assert app.model.current_folder is None


# ---------------------------------------------------------------------------------------------------- toolbar: Clear
def test_clear_empties_the_list_and_deletes_nothing_and_is_greyed_when_there_is_nothing(app, drv, shown):
    app.model.rate_1()
    drv.click("clear")
    assert app.model.file_entries() == [] and app.model.current_file is None
    assert SP8 not in strings(drv) and "Select a file in the list" in " ".join(strings(drv))
    assert (shown / SP8).is_file() and (shown / "corrupt.ptu").is_file()
    assert json.loads((shown / ".image_browser_meta.json").read_text())[SP8]["rating"] == 1  # the rating is kept
    status = app.model.status_line
    drv.click("clear")  # greyed now: a press changes nothing
    assert app.model.status_line == status and not app.model.enabled("clear")


# ---------------------------------------------------------------------------------------------------- toolbar: Clear caches
def test_clear_caches_removes_the_cache_folders_and_the_shown_mosaic_is_rebuilt(app, drv, shown):
    assert [p.name for p in shown.rglob(".tttr_image_cache")] != []
    drv.click("clear_caches")
    assert list(shown.rglob(".tttr_image_cache")) == []  # gone at once, in memory and on disk
    assert app.model.status_line == "Image caches cleared." and app.model.current_image() is None
    drv.settle()  # the shown file asks for its mosaic again and is rebuilt
    assert app.model.current_image() is not None and list(shown.glob(".tttr_image_cache/*.npz"))


def test_clear_caches_is_greyed_without_a_folder(app, drv):
    drv.draw(2)
    status = app.model.status_line
    drv.click("clear_caches")
    assert not app.model.enabled("clear_caches") and app.model.status_line == status


# ---------------------------------------------------------------------------------------------------- toolbar: Include subfolders
def test_include_subfolders_lists_the_files_below(app, drv, opened):
    assert [e["label"] for e in app.model.file_entries()] == ["corrupt.ptu", SP8]
    drv.click("recursive")
    drv.settle()
    assert app.model.recursive is True
    assert [e["label"] for e in app.model.file_entries()] == ["corrupt.ptu", "sub/Leica_SP5.ptu", SP8]
    assert "sub/Leica_SP5.ptu" in strings(drv)
    drv.click("recursive")
    drv.settle()
    assert [e["label"] for e in app.model.file_entries()] == ["corrupt.ptu", SP8]


# ---------------------------------------------------------------------------------------------------- toolbar: exports
def choose_in_dialog(drv, app, parent, name, button):
    """Operate the open file chooser: start in *parent*, click the folder row *name*, press *button*."""
    drv.draw(2)
    app.dialog.directory = str(parent)
    drv.draw(2)
    if name:
        drv.click_text(f"[{name}]")
    drv.click_text(button, last=True)
    drv.draw(2)


def test_copy_raw_files_asks_for_a_folder_and_copies_the_selection(app, drv, shown, tmp_path):
    dest = tmp_path / "out"
    dest.mkdir()
    drv.click("copy_files")
    assert dialog_open(drv) and app.dialog_kind == "copy"
    choose_in_dialog(drv, app, tmp_path, "out", "Choose")
    drv.settle()
    assert (dest / SP8).read_bytes() == (shown / SP8).read_bytes()
    assert "Copied 1 raw file(s)" in app.model.status_line and "Copied 1 raw file(s)" in " ".join(strings(drv))


def test_copy_raw_files_and_tiff_are_greyed_until_a_file_is_selected(app, drv, opened):
    for action in ("copy_files", "export_tiff"):
        drv.click(action)
        assert app.dialog is None and not app.model.enabled(action), action
    drv.click_text(SP8)
    drv.settle()
    assert app.model.enabled("copy_files") and app.model.enabled("export_tiff")


def test_tiff_writes_the_stacks_of_the_selected_file(app, drv, shown, tmp_path):
    import tifffile

    (tmp_path / "tiffs").mkdir()
    drv.click("export_tiff")
    assert dialog_open(drv) and app.dialog_kind == "tiff"
    choose_in_dialog(drv, app, tmp_path, "tiffs", "Choose")
    drv.settle()
    names = sorted(p.name for p in (tmp_path / "tiffs").iterdir())
    assert names == ["Leica_SP8_green.tiff", "Leica_SP8_red.tiff"]
    assert tifffile.imread(tmp_path / "tiffs" / names[0]).shape == (93, 512, 512)
    assert "Wrote 2 TIFF stack(s)" in app.model.status_line


def test_docx_writes_a_report_to_the_typed_name(app, drv, shown, tmp_path):
    drv.click("export_docx")
    assert dialog_open(drv) and app.dialog_kind == "docx"
    assert app.dialog.filename == "imgs.docx"  # the Qt tool wrote <folder>.docx into the folder
    app.dialog.directory = str(tmp_path)
    drv.draw(2)
    # the file-name field is the one with the keyboard after a click on it
    field = [t for t in drv.draw(1).texts if t[5] == "imgs.docx"][0][:4]
    drv.click_at(field[0] + 5, field[1] + field[3] / 2)
    drv.select_all()
    drv.type_text("report")
    drv.click_text("Save", last=True)
    drv.settle()
    out = tmp_path / "report.docx"
    assert out.is_file() and out.stat().st_size > 1000
    assert "Saved report" in app.model.status_line


def test_docx_is_greyed_without_a_folder(app, drv):
    drv.click("export_docx")
    assert app.dialog is None and not app.model.enabled("export_docx")


def test_a_failing_export_reports_instead_of_raising(app, drv, shown, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    app.queue("do_copy_files", str(blocker / "inside"))
    drv.settle()
    assert app.model.status_line.startswith("Failed:")


# ---------------------------------------------------------------------------------------------------- toolbar: Next
def test_next_is_greyed_inside_a_standalone_window(app, drv, shown):
    drv.click("next_step")
    assert not app.model.enabled("next_step") and "Sent to" not in app.model.status_line


def test_next_hands_the_image_to_the_pipeline(photon_folder, hermetic):
    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

    calls = []

    class Coordinator:
        def set_pipeline(self, **kw):
            calls.append(("set_pipeline", pathlib.Path(kw["source"]).name))

        def goto_role(self, role):
            calls.append(("goto_role", role))

        def autorun_role(self, role):
            calls.append(("autorun_role", role))

    app = make_app(coordinator=Coordinator())
    drv = BrowserDriver(app, (1000, 700))
    assert drv.drop(str(photon_folder))
    drv.settle()
    drv.click_text(SP8)
    drv.settle()
    assert ("set_pipeline", SP8) in calls  # picking a file already told the pipeline (the Qt tool did too)
    del calls[:]
    drv.click("next_step")
    drv.draw(2)
    assert calls == [("set_pipeline", SP8), ("goto_role", "pixel_intensity"), ("autorun_role", "pixel_intensity")]
    assert "Sent to the Intensity step" in app.model.status_line


# ---------------------------------------------------------------------------------------------------- help and guide
def test_help_opens_the_help_window_and_closes(app, drv):
    drv.click("show_help")
    drv.draw(2)
    assert app.help_window.open
    assert {"Start Guided Tour", "Close"} <= set(drv.draw(2).strings)
    drv.click_text("Close")
    assert not app.help_window.open


def test_help_start_guided_tour_starts_the_tour(app, drv):
    drv.click("show_help")
    drv.draw(2)
    drv.click_text("Start Guided Tour")
    drv.draw(2)
    assert app.tour.active


def test_guide_button_starts_the_tour_and_close_tour_ends_it(app, drv):
    drv.click("start_guide")
    drv.draw(2)
    assert app.tour.active
    drv.click_text("Close Tour")
    assert not app.tour.active


def operate_step(app, drv, folder, tmp_path):
    """Do what the awaited step asks, with real input."""
    step = app.tour.steps[app.tour.step_idx]
    target = step.get("target") or {}
    if target.get("name") == "choose_folder":
        app.model.folder = str(folder.parent)
        drv.click("choose_folder")
        drv.click_text(f"[{folder.name}]")
        drv.click_text("Choose", last=True)
        drv.settle()
    elif target.get("name") == "rows":
        drv.click_text(SP8)
        drv.settle()
    elif target.get("attr") == "current_rating":
        drv.click("current_rating.2")
    else:
        raise AssertionError(f"no way to operate {step['title']!r}")
    drv.draw(2)


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_awaited_control(app, drv, photon_folder, tmp_path):
    drv.click("start_guide")
    drv.draw(2)
    assert app.tour.active
    guard = 0
    while app.tour.active and guard < 40:
        guard += 1
        drv.draw(2)
        if app.tour.awaiting:
            operate_step(app, drv, photon_folder, tmp_path)
            assert not app.tour.awaiting, f"{app.tour.steps[app.tour.step_idx]['title']}: the step did not release"
        index = app.tour.step_idx
        drv.click_text("Finish ✓" if index == len(app.tour.steps) - 1 else "Next ►", last=True)
        if app.tour.active:
            assert app.tour.step_idx == index + 1, f"the Next button of step {index} was dead"
    assert not app.tour.active
    assert app.model.current_file and app.model.rating_of(app.model.current_file) == 2


def test_every_guide_target_is_a_drawn_control_and_the_card_does_not_cover_it(app, drv, shown):
    from chisurf.emtk.help_guide import place_tour_card

    seen = set()
    for index, step in enumerate(app.tour.steps):
        target = step.get("target") or {}
        if not target:
            continue
        app.tour.start(index)
        key = app.tour._target_key(target)
        drv.draw(3)
        rect = app.tour.get_target_rect(key)
        if rect is None and key == "tab_setup":
            rect = app.item_rects.get("tab_setup")
        assert rect and rect[2] > 0 and rect[3] > 0, f"{step['title']}: nothing drawn for {key!r}"
        card_w = min(480.0, drv.size[0] - 40.0)
        W, H = float(drv.size[0]), float(drv.size[1])
        x, y = place_tour_card(rect, W, H, card_w, 150.0)
        clear = x + card_w <= rect[0] or x >= rect[0] + rect[2] or y + 150.0 <= rect[1] or y >= rect[1] + rect[3]
        # a target that fills most of the window (the mosaic) leaves no free side for a card; the user drags it away
        free_side = (
            rect[0] + rect[2] + card_w + 16 <= W or rect[0] - card_w - 16 >= 0 or rect[1] + rect[3] + 150 + 16 <= H or rect[1] - 150 - 16 >= 0
        )
        assert clear or not free_side, f"{step['title']}: the card would cover its target although room was free"
        seen.add(key)
    app.tour.stop()
    assert {"choose_folder", "rows", "image", "levels", "current_rating", "multi_select", "export_tiff"} <= seen


def test_the_tour_card_can_be_dragged_away(app, drv):
    drv.click("start_guide")
    drv.draw(3)
    handle = drv.text_rect("drag here to move")
    before = app.tour.card_offset
    drv.drag((handle[0] + 20, handle[1] + 5), (handle[0] - 60, handle[1] + 80))
    assert app.tour.card_offset != before


# ---------------------------------------------------------------------------------------------------- pages
def test_the_tabs_switch_pages_and_use_setup_returns(app, drv, opened):
    assert app.page == "browser"
    drv.click("tab_setup")
    drv.draw(3)
    assert app.page == "setup" and "Use setup and continue" in strings(drv)
    assert "Open folder" not in strings(drv)  # the browser's toolbar is not drawn on the setup page
    drv.click("use_setup")
    drv.draw(3)
    assert app.page == "browser" and "Open folder" in strings(drv)
    assert app.model.setup_settings is not None
    drv.click("tab_setup")
    drv.draw(3)
    drv.click("tab_browser")
    drv.draw(3)
    assert app.page == "browser"


def test_a_setup_chosen_on_the_setup_page_filters_the_list_and_the_tiles(app, drv, photon_folder):
    """The shared editor's TTTR format combo: HT3 reads no .ptu file, so the list empties; PTU brings them back."""
    assert drv.drop(str(photon_folder))
    drv.settle()
    assert [e["label"] for e in app.model.file_entries()] == ["corrupt.ptu", SP8]  # auto: every supported type
    drv.click("tab_setup")
    drv.draw(3)
    combo = [t for t in drv.draw(1).texts if t[5] == "Auto"][0][:4]       # the File Type combo of the one-page editor
    drv.click_at(combo[0] + 10, combo[1] + combo[3] / 2)
    drv.draw(2)
    drv.click_text("HT3", last=True)
    drv.draw(2)
    drv.click("use_setup")
    drv.settle()
    assert app.model.setup_settings["tttr_reading"]["file_type"] == "HT3"
    assert app.model.file_entries() == [] and app.page == "browser"
    assert "none" not in app.model.setup_text()


# ---------------------------------------------------------------------------------------------------- drops
def test_dropping_a_folder_opens_it_and_a_file_is_refused(app, drv, photon_folder):
    drv.drop(str(photon_folder / SP8))
    assert "not a single file" in app.model.status_line and app.model.current_folder is None
    assert "not a single file" in " ".join(strings(drv))
    drv.drop(str(photon_folder))
    drv.settle()
    assert app.model.current_folder == str(photon_folder) and SP8 in strings(drv)
    status = app.model.status_line
    drv.drop()  # nothing dropped
    assert app.model.status_line == status and app.model.current_folder == str(photon_folder)


def test_a_drop_on_the_setup_page_opens_the_browser_page(app, drv, photon_folder):
    drv.click("tab_setup")
    drv.draw(3)
    assert drv.drop(str(photon_folder))
    drv.settle()
    assert app.page == "browser" and app.model.current_folder == str(photon_folder)


def test_the_qt_host_hook_is_the_same_verb(app):
    assert app.on_files_dropped == app.files_dropped


# ---------------------------------------------------------------------------------------------------- file list
def test_a_click_on_a_row_selects_it_and_draws_its_mosaic(app, drv, opened):
    assert "Select a file in the list" in " ".join(strings(drv))
    drv.click_text(SP8)
    drv.settle()
    assert app.model.current_file == str(opened / SP8)
    drv.draw(2)
    assert app.item_rects["image"][2] > 100 and "Leica_SP8.ptu: 2 tile(s), mosaic 512 x 256 px" in strings(drv)
    assert any(t.startswith("green") for t in strings(drv)) and any(t.startswith("red") for t in strings(drv))  # tile labels


def test_the_mosaic_is_drawn_on_the_screen(app, drv, shown):
    px = pixels(app)
    x, y, w, h = (int(v) for v in app.item_rects["image"])
    region = px[y : y + h, x : x + w]
    assert len({tuple(p) for p in region.reshape(-1, region.shape[-1])[::97]}) > 40  # an image, not a flat field


def test_a_file_without_an_image_says_so_in_the_image_area(app, drv, opened):
    drv.click_text("corrupt.ptu")
    drv.settle()
    text = " ".join(strings(drv))
    assert "corrupt.ptu: no image could be reconstructed" in text and app.model.current_image() is None
    drv.click_text(SP8)
    drv.settle()
    assert app.model.current_image() is not None


def test_a_slow_load_does_not_freeze_the_selection(app, drv, opened):
    """Pick another row while a mosaic is loading: the last pick wins, the first mosaic is kept in the cache."""
    drv.click_text("corrupt.ptu")
    drv.click_text(SP8)
    drv.settle()
    assert app.model.current_file == str(opened / SP8) and app.model.current_image() is not None


def header(drv, title):
    """The drawn header text of the column *title* (a sorted column carries an arrow after its title)."""
    hits = [t for t in drv.draw(1).texts if t[5] in (title, title + " \u25b4", title + " \u25be")]
    return min(hits, key=lambda t: t[1])  # the column header is above the label of the same word below the list


def listed(drv):
    return [t[5] for t in drv.draw(1).texts if t[5] in ("corrupt.ptu", SP8, "sub/Leica_SP5.ptu")]


def test_the_header_sorts_by_name_and_by_rating(app, drv, shown):
    drv.click_at(*[header(drv, "File")[0] + 10, header(drv, "File")[1] + 6])
    ascending = listed(drv)
    drv.click_at(*[header(drv, "File")[0] + 10, header(drv, "File")[1] + 6])
    descending = listed(drv)
    assert ascending == list(reversed(descending)) and len(ascending) == 2
    app.model.select_file(str(shown / SP8))
    drv.click("current_rating.3")
    h = header(drv, "Rating")
    drv.click_at(h[0] + 10, h[1] + 6)
    by_rating = listed(drv)
    drv.click_at(h[0] + 10, h[1] + 6)
    assert listed(drv) == list(reversed(by_rating))
    h = header(drv, "MB")
    drv.click_at(h[0] + 10, h[1] + 6)
    assert listed(drv)[0] == "corrupt.ptu"  # 0.0 MB sorts before 12.0 MB: by value, not by text


def test_the_filter_box_narrows_the_rows_by_any_text(app, drv, opened):
    app.model.set_recursive(True)
    drv.draw(2)
    drv.settle()
    box = [t for t in drv.draw(1).texts if t[5] == "filter"][0][:4]
    drv.click_at(box[0] + 20, box[1] + box[3] / 2)
    drv.type_text("sp5")
    shown_rows = [s for s in strings(drv) if s.endswith(".ptu")]
    assert shown_rows == ["sub/Leica_SP5.ptu"]


def test_select_all_selects_every_row_and_multiple_selection_toggles_rows(app, drv, opened):
    drv.click("multi_select")
    assert app.model.multi_select is True
    drv.click_text(SP8)
    drv.settle()
    drv.click_text("corrupt.ptu")
    drv.settle()
    assert sorted(pathlib.Path(p).name for p in app.model.selected_files) == ["Leica_SP8.ptu", "corrupt.ptu"]
    assert "2 image(s) in imgs, 2 selected" in strings(drv)
    drv.click_text("corrupt.ptu")  # toggled off
    drv.settle()
    assert [pathlib.Path(p).name for p in app.model.selected_files] == ["Leica_SP8.ptu"]
    drv.click("select_all_files")
    drv.settle()
    assert len(app.model.selected_files) == 2
    drv.click("multi_select")  # off: one file stays
    drv.settle()
    assert len(app.model.selected_files) == 1


def test_copy_acts_on_every_selected_row(app, drv, opened, tmp_path):
    (tmp_path / "all").mkdir()
    drv.click("select_all_files")
    drv.settle()
    drv.click("copy_files")
    choose_in_dialog(drv, app, tmp_path, "all", "Choose")
    drv.settle()
    assert sorted(p.name for p in (tmp_path / "all").iterdir()) == ["Leica_SP8.ptu", "corrupt.ptu"]


def test_the_rating_filter_choice_lists_the_five_filters_and_applies_one(app, drv, shown):
    drv.click("current_rating.2")
    drv.draw(2)
    assert app.model.rating_of(str(shown / SP8)) == 2
    drv.click("rating_filter")
    drv.draw(2)
    for label in ("All", "≥ 1  ★", "≥ 2  ★★", "≥ 3  ★★★", "Only 0  ★"):
        assert label in strings(drv), label  # a gap before the stars: they are drawn wider than they measure
    drv.click_text("≥ 2  ★★", last=True)
    drv.settle()
    assert app.model.rating_filter == "≥ 2★★"
    assert [e["label"] for e in app.model.file_entries()] == [SP8] and "corrupt.ptu" not in strings(drv)


def test_the_rating_choice_writes_the_stars_and_the_file(app, drv, shown):
    for stars in (1, 3, 0):
        drv.click(f"current_rating.{stars}")
        drv.draw(2)
        assert app.model.rating_of(str(shown / SP8)) == stars
        saved = json.loads((shown / ".image_browser_meta.json").read_text())
        assert saved[SP8]["rating"] == stars
    drv.click("current_rating.3")
    drv.draw(2)
    assert "★★★" in strings(drv)  # the list shows the stars


def test_the_rating_choice_is_greyed_without_a_file(app, drv, opened):
    drv.click("current_rating.2")
    assert app.model.current_file is None and not app.model.enabled("current_rating")
    assert not (opened / ".image_browser_meta.json").exists()


def test_the_annotation_is_typed_saved_and_follows_the_file(app, drv, shown):
    box = drv.rect("annotation")
    drv.click_at(box[0] + 20, box[1] + 15)
    drv.type_text("bleached")
    drv.draw(2)
    assert app.model.note_of(str(shown / SP8)) == "bleached"
    assert json.loads((shown / ".image_browser_meta.json").read_text())[SP8]["annotation"] == "bleached"
    drv.click_text("corrupt.ptu")
    drv.settle()
    assert app.note_text == ""  # another file: its own (empty) note
    drv.click_text(SP8)
    drv.settle()
    assert app.note_text == "bleached"


# ---------------------------------------------------------------------------------------------------- image
def mosaic_center(app):
    x, y, w, h = app.item_rects["image"]
    return x + w / 2, y + h / 2


def span(app):
    x0, x1, y0, y1 = app.view_limits
    return x1 - x0, y1 - y0


def notches(drv, x, y, n):
    """*n* wheel events of one notch each (implot zooms one step per event), away from the user for n > 0."""
    for _ in range(abs(n)):
        drv.wheel(x, y, 1 if n > 0 else -1)


def test_the_wheel_over_the_image_zooms_in_and_out_about_the_pointer(app, drv, shown):
    cx, cy = mosaic_center(app)
    full = span(app)
    notches(drv, cx, cy, 5)
    zoomed = span(app)
    assert zoomed[0] < full[0] * 0.75 and zoomed[1] < full[1] * 0.75
    assert abs(zoomed[0] / zoomed[1] - full[0] / full[1]) < 0.02  # equal aspect: square pixels stay square
    notches(drv, cx, cy, -3)
    assert span(app)[0] > zoomed[0] * 1.1
    # zooming about the pointer: the image pixel under it keeps its place
    rx, ry, rw, rh = app.item_rects["image"]
    under = lambda: app.view_limits[0] + (cx - rx) / rw * span(app)[0]
    before = under()
    notches(drv, cx, cy, 3)
    assert under() == pytest.approx(before, abs=2.0)


def test_each_notch_zooms_further(app, drv, shown):
    cx, cy = mosaic_center(app)
    widths = [span(app)[0]]
    for _ in range(4):
        notches(drv, cx, cy, 1)
        widths.append(span(app)[0])
    assert all(a > b for a, b in zip(widths, widths[1:]))


def test_a_drag_pans_the_image_and_reset_view_restores_it(app, drv, shown):
    cx, cy = mosaic_center(app)
    home = app.view_limits
    notches(drv, cx, cy, 6)  # zoomed in, so that a pan has room
    zoomed = app.view_limits
    drv.drag((cx, cy), (cx - 90, cy - 50))
    panned = app.view_limits
    assert span(app)[0] == pytest.approx(zoomed[1] - zoomed[0], rel=0.02)  # a pan does not change the scale
    assert panned[0] > zoomed[0] + 10 and panned[2] > zoomed[2] + 5  # dragged left / up: the view moved right / down in the image
    drv.click("reset_view")
    drv.draw(2)
    assert app.view_limits == pytest.approx(home)


def test_selecting_another_file_resets_the_view(app, drv, shown):
    cx, cy = mosaic_center(app)
    home = app.view_limits
    notches(drv, cx, cy, 5)
    assert app.view_limits != home
    drv.click_text("corrupt.ptu")
    drv.settle()
    drv.click_text(SP8)
    drv.settle()
    assert app.view_limits == pytest.approx(home)


def test_a_wheel_used_for_zooming_does_not_step_the_next_field_the_pointer_reaches(app, drv, shown):
    cx, cy = mosaic_center(app)
    notches(drv, cx, cy, 4)
    drv.click("auto_levels")  # Min becomes editable ...
    low = app.model.level_low
    drv.hover(*[v + 5 for v in drv.rect("level_low")[:2]])
    drv.draw(6)  # ... and the pointer rests on it: nothing steps it
    assert app.model.level_low == low


def test_the_colormap_combo_lists_the_qt_colormaps_and_recolours_the_image(app, drv, shown):
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import COLORMAPS

    before = pixels(app)
    drv.click("colormap")
    drv.draw(2)
    for name in COLORMAPS:
        assert name in strings(drv), name
    drv.click_text("viridis", last=True)
    drv.draw(3)
    assert app.model.colormap == "viridis" and app.canvas.colormap == "viridis"
    after = pixels(app)
    x, y, w, h = (int(v) for v in app.item_rects["image"])
    assert not np.array_equal(before[y : y + h, x : x + w], after[y : y + h, x : x + w])
    drv.click("colormap")
    drv.escape()
    assert app.model.colormap == "viridis"


def test_every_colormap_can_be_picked(app, drv, shown):
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import COLORMAPS

    for name in COLORMAPS:
        drv.click("colormap")
        drv.draw(2)
        drv.click_text(name, last=True)
        drv.draw(2)
        assert app.model.colormap == name, name


def test_gamma_is_typed_and_clamped(app, drv, shown):
    drv.type_into("gamma", "2.5")
    drv.draw(2)
    assert app.model.gamma == pytest.approx(2.5)
    drv.type_into("gamma", "99")
    drv.draw(2)
    assert app.model.gamma == pytest.approx(5.0)
    drv.type_into("gamma", "0")
    drv.draw(2)
    assert app.model.gamma == pytest.approx(0.1)


def test_gamma_arrows_and_wheel_step_it(app, drv, shown):
    x, y, w, h = drv.rect("gamma.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.gamma == pytest.approx(1.1)
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    assert app.model.gamma == pytest.approx(0.9)
    gx, gy, gw, gh = drv.rect("gamma")
    drv.wheel(gx + 10, gy + gh / 2, 2)
    assert app.model.gamma > 0.9


def test_a_gamma_change_recolours_the_image(app, drv, shown):
    before = pixels(app)
    drv.type_into("gamma", "3")
    drv.draw(3)
    after = pixels(app)
    x, y, w, h = (int(v) for v in app.item_rects["image"])
    assert not np.array_equal(before[y : y + h, x : x + w], after[y : y + h, x : x + w])


def test_levels_are_greyed_while_auto_levels_is_on_and_typed_when_it_is_off(app, drv, shown):
    drv.click("level_low", fx=0.3)
    assert not app.io.want_capture_keyboard  # greyed: the click did not take the keyboard
    drv.type_text("50")
    drv.enter()
    assert app.model.level_low == 0.0
    drv.click("auto_levels")
    assert app.model.auto_levels is False
    drv.type_into("level_low", "40")
    drv.type_into("level_high", "120")
    drv.draw(2)
    assert (app.model.level_low, app.model.level_high) == (40.0, 120.0)
    assert app.canvas.low == 40.0 and app.canvas.high == 120.0
    drv.type_into("level_high", "20")  # below Min: clamped above it
    assert app.model.level_high > app.model.level_low
    drv.click("auto_levels")
    assert app.model.auto_levels is True and app.model.level_range() == (0.0, 212.0)


def test_the_level_lines_are_dragged_in_the_histogram(app, drv, shown):
    drv.draw(3)
    x, y, w, h = app.item_rects["levels"]
    assert app.model.auto_levels
    # the high line sits at the top of the data range; the plot's y axis spans -1 .. 256
    drv.draw(2)
    start = (x + w / 2, y + h * (1.0 - 213.0 / 257.0))
    drv.drag(start, (start[0], start[1] + 120), steps=8)
    drv.draw(3)
    assert app.model.auto_levels is False
    assert app.model.level_high < 212.0 and app.model.level_low < app.model.level_high


def test_tile_labels_can_be_switched_off(app, drv, shown):
    before = pixels(app)
    drv.click("show_labels")
    drv.draw(3)
    assert app.model.show_labels is False and app.model.tile_labels() == []
    after = pixels(app)
    assert not np.array_equal(before, after)
    drv.click("show_labels")
    assert app.model.show_labels is True


def test_display_controls_are_greyed_without_an_image(app, drv, opened):
    for name in ("colormap", "gamma", "auto_levels", "show_labels", "reset_view"):
        assert not app.model.enabled(name), name
    drv.click("auto_levels")
    assert app.model.auto_levels is True
    drv.click("show_labels")
    assert app.model.show_labels is True


# ---------------------------------------------------------------------------------------------------- idle state and persistence
def test_the_idle_state_offers_only_what_can_act_and_says_what_to_do(app, drv):
    text = " ".join(strings(drv))
    assert "Open a folder with photon files" in text
    for name in ("clear", "clear_caches", "copy_files", "export_tiff", "export_docx", "next_step", "select_all_files", "colormap", "gamma"):
        assert not app.model.enabled(name), name
    assert app.model.enabled("choose_folder")
    assert app.item_rects.get("image") is None or app.model.current_image() is None


def test_settings_survive_a_restart_through_the_host_hooks(app, drv, shown):
    drv.click("recursive")
    drv.settle()
    drv.click("colormap")
    drv.draw(2)
    drv.click_text("plasma", last=True)
    drv.draw(2)
    drv.click("current_rating.1")
    saved = json.loads(json.dumps(app.export_settings()))
    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

    other = make_app()
    other.restore_settings(saved)
    d2 = BrowserDriver(other, (1000, 700))
    d2.settle()
    assert other.model.colormap == "plasma" and other.model.recursive is True
    assert other.model.current_folder == str(shown) and other.model.current_file == str(shown / SP8)
    assert other.model.current_image() is not None  # loaded by drawn frames alone
    other.close()


def test_the_imaging_hub_contract(app, drv, photon_folder):
    """The hub hands the shared setup (``apply_setup_settings``), the current source (``apply_pipeline_context``) and
    itself (the ``_coordinator`` attribute, as it does for every child)."""
    calls = []

    class Hub:
        def set_pipeline(self, **kw):
            calls.append(pathlib.Path(kw["source"]).name)

    app.apply_setup_settings(two_detector_setup())
    assert set(app.model.setup_settings["detectors"]) == {"green", "red"} and "2 detector(s)" in app.model.status_line
    app._coordinator = Hub()
    app.model.can_next = True
    app.apply_pipeline_context({"file": str(photon_folder / SP8)})
    drv.settle()
    assert app.model.current_folder == str(photon_folder) and app.model.current_file == str(photon_folder / SP8)
    assert app.model.current_image() is not None and calls == [SP8]
    drv.click("tab_setup")
    drv.draw(3)
    drv.click_text("Detectors")
    drv.draw(3)
    assert "green" in strings(drv) and "red" in strings(drv)  # the shared editor holds the hub's setup
    app.apply_pipeline_context({})  # nothing to open: ignored
    assert app.model.current_file == str(photon_folder / SP8)


def test_resizing_the_window_shows_the_whole_mosaic_again(app, drv, shown):
    cx, cy = mosaic_center(app)
    notches(drv, cx, cy, 6)
    zoomed = app.view_limits
    drv.draw(2, size=(800, 600))
    small = app.view_limits
    assert small != zoomed
    x0, x1, y0, y1 = small
    assert x0 < 0 and x1 > 511 and y0 < 0 and y1 > 255  # the whole 512 x 256 mosaic is in view


def test_the_window_draws_at_both_sizes_populated(app, drv, shown):
    for size in ((1200, 800), (800, 600)):
        painter = drv.draw(2, size=size)
        assert "Open folder" in painter.strings and SP8 in painter.strings and "Colormap" in painter.strings
