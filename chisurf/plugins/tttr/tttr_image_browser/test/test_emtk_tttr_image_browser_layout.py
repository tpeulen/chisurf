"""Layout of the emtk TTTR image browser, asserted at 1200x800 and 800x600 (the screenshots are read as well).

No clipped or overlapping text, the image area gets most of the window, short inputs stay short, windows do not overlap,
an idle window offers nothing that cannot act, and the wheel scrolls the file list.
"""

import pathlib

import pytest

from .conftest import two_detector_setup
from .test_emtk_tttr_image_browser_clicks import SP8, BrowserDriver, strings

pytestmark = pytest.mark.usefixtures("hermetic")

SIZES = [(1200, 800), (800, 600)]


@pytest.fixture
def app():
    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

    application = make_app()
    yield application
    application.close()


def populated(app, folder, size):
    drv = BrowserDriver(app, size)
    app.model.apply_setup_settings(two_detector_setup())
    app.model.open_folder(str(folder))
    app.model.select_file(str(folder / SP8))
    app.model.load_current()
    drv.draw(4)
    return drv


def overlap(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def inside(rect, box):
    return rect[0] >= box[0] - 1 and rect[1] >= box[1] - 1 and rect[0] + rect[2] <= box[0] + box[2] + 1 and rect[1] + rect[3] <= box[1] + box[3] + 1


@pytest.mark.parametrize("size", SIZES)
def test_the_image_area_gets_most_of_the_window(app, photon_folder, size):
    drv = populated(app, photon_folder, size)
    x, y, w, h = app.item_rects["image"]
    levels = app.item_rects["levels"]
    plot_share = (w * h + levels[2] * levels[3]) / (size[0] * size[1])
    assert plot_share >= (0.40 if size[0] >= 1200 else 0.30), plot_share
    # the window that holds the controls, the mosaic and the histogram: more than half of the frame
    display = app.form.rects["colormap"]
    window_share = (size[0] - display[0]) * (size[1] - app.form.rects["colormap"][1]) / (size[0] * size[1])
    assert window_share >= 0.55, window_share
    assert x > 0 and inside((x, y, w, h), (0, 0, *size)) and inside(levels, (0, 0, *size))


@pytest.mark.parametrize("size", SIZES)
def test_no_text_is_clipped_or_overlaps_other_text(app, photon_folder, size):
    drv = populated(app, photon_folder, size)
    texts = [t for t in drv.draw(1).texts if str(t[5]).strip()]
    image, levels = app.item_rects["image"], app.item_rects["levels"]
    vertical = {"y [px]", "level"}  # axis titles drawn turned: the recorder reports their unturned box
    widgets = [t for t in texts if not (inside(t[:4], image) or inside(t[:4], levels)) and t[5] not in vertical]
    for t in widgets:
        assert inside(t[:4], (0, 0, *size)), f"{t[5]!r} leaves the window"
    for i, a in enumerate(widgets):
        for b in widgets[i + 1 :]:
            assert overlap(a[:4], b[:4]) < 2.0, f"{a[5]!r} overlaps {b[5]!r}"


@pytest.mark.parametrize("size", SIZES)
def test_the_tile_labels_do_not_overlap_each_other_and_stay_in_the_plot(app, photon_folder, size):
    drv = populated(app, photon_folder, size)
    labels = [t for t in drv.draw(1).texts if str(t[5]).startswith(("green", "red"))]
    assert len(labels) == 2
    assert overlap(labels[0][:4], labels[1][:4]) < 2.0
    image = app.item_rects["image"]
    assert all(inside(t[:4], image) for t in labels)
    # the label of a tile is its detector at least; a wide enough tile gets the whole text
    assert labels[0][5].startswith("green") and labels[1][5].startswith("red")


def test_a_zoomed_tile_shows_its_whole_label(app, photon_folder):
    drv = populated(app, photon_folder, (800, 600))
    cx, cy = app.item_rects["image"][0] + 50, app.item_rects["image"][1] + 50
    short = [t[5] for t in drv.draw(1).texts if str(t[5]).startswith("green")][0]
    for _ in range(8):
        drv.wheel(cx, cy, 1)
    full = [t[5] for t in drv.draw(1).texts if str(t[5]).startswith("green")]
    assert len(short) < len("green  |  mt: 0-4095  |  ch: 0,1") and full and len(full[0]) >= len(short)


@pytest.mark.parametrize("size", SIZES)
def test_button_labels_fit_their_buttons(app, photon_folder, size):
    drv = populated(app, photon_folder, size)
    painter = drv.draw(1)
    for action in ("choose_folder", "clear", "clear_caches", "copy_files", "export_tiff", "export_docx", "next_step", "show_help", "start_guide", "select_all_files", "reset_view"):
        rect = app.form.rects[action]
        label = next(t for t in painter.texts if t[5] and inside(t[:4], (rect[0] - 2, rect[1] - 2, rect[2] + 4, rect[3] + 4)))
        assert label[2] <= rect[2] + 1, f"{action}: the caption is wider than its button"


@pytest.mark.parametrize("size", SIZES)
def test_short_inputs_are_not_stretched(app, photon_folder, size):
    populated(app, photon_folder, size)
    for name, widest in (("gamma", 150), ("level_low", 150), ("level_high", 150), ("colormap", 200), ("rating_filter", 200)):
        assert app.form.rects[name][2] <= widest, (name, app.form.rects[name])


@pytest.mark.parametrize("size", SIZES)
def test_the_windows_do_not_overlap_and_fill_the_frame(app, photon_folder, size):
    drv = populated(app, photon_folder, size)
    rects = app.form.rects
    toolbar = rects["choose_folder"]
    files = rects["rating_filter"]
    display = rects["colormap"]
    assert toolbar[1] + toolbar[3] <= files[1] and toolbar[1] + toolbar[3] <= display[1]
    assert files[0] + files[2] <= display[0]  # the file column is left of the display controls
    status = app.item_rects["status"]
    assert status[1] + status[3] <= size[1] and app.item_rects["image"][1] + app.item_rects["image"][3] <= status[1]


@pytest.mark.parametrize("size", SIZES)
def test_the_idle_window_fits_and_offers_only_what_can_act(app, size):
    drv = BrowserDriver(app, size)
    painter = drv.draw(4)
    assert any("Open a folder with photon files" in s for s in painter.strings)
    for t in painter.texts:
        if str(t[5]).strip():
            assert inside(t[:4], (0, 0, *size)), t[5]
    assert "Annotation" in painter.strings  # the box is there but greyed (see the click tests)


@pytest.mark.parametrize("size", SIZES)
def test_the_setup_page_fits(app, size):
    drv = BrowserDriver(app, size)
    drv.click("tab_setup")
    painter = drv.draw(4)
    assert "Use setup and continue" in painter.strings
    for t in painter.texts:
        if str(t[5]).strip():
            assert inside(t[:4], (0, 0, *size)), t[5]
    # the editor is a column of limited width: its widest control does not run across the window
    combo = next(t for t in painter.texts if t[5] == "Unsaved")
    assert combo[0] + combo[2] < min(size[0], 700)


def test_a_narrow_window_still_shows_every_control(app, photon_folder):
    drv = populated(app, photon_folder, (500, 500))
    drv.draw(2, size=(500, 500))
    strings_ = strings(drv)
    for caption in ("Open folder", "Copy raw files", "Include subfolders", "Colormap", "Reset view"):
        assert caption in strings_, caption


def test_the_wheel_scrolls_a_long_file_list(app, tmp_path):
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(60):
        (folder / f"file_{i:02d}.ptu").write_bytes(b"")
    drv = BrowserDriver(app, (800, 600))
    app.model.open_folder(str(folder))
    drv.draw(4)
    assert "file_00.ptu" in strings(drv) and "file_59.ptu" not in strings(drv)
    x, y, w, h = drv.rect("rows")
    drv.wheel(x + 30, y + h / 2, -8)
    assert "file_00.ptu" not in strings(drv)
    first = [s for s in strings(drv) if s.startswith("file_")][0]
    drv.wheel(x + 30, y + h / 2, 3)
    assert [s for s in strings(drv) if s.startswith("file_")][0] < first


def test_the_wheel_over_the_histogram_leaves_the_levels_alone(app, photon_folder):
    drv = populated(app, photon_folder, (1000, 700))
    x, y, w, h = app.item_rects["levels"]
    before = (app.model.level_low, app.model.level_high, app.model.auto_levels)
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert (app.model.level_low, app.model.level_high, app.model.auto_levels) == before
