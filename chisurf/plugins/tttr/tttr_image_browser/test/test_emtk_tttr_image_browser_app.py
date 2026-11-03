"""The emtk TTTR image browser: real CLSM files, their numbers, every action.

The numbers are checked against the files: the image of a detector is the photon file
reconstructed by tttrlib's ``CLSMImage`` over that detector's routing channels (frames,
lines, pixels); a mosaic tile is its frame sum min-max scaled to 0..255 and shrunk by
nearest neighbour until the mosaic's longer side is 512; a copied file has the source's
bytes. The detector setup is the two-detector one of ``conftest.py`` (green: channels 0
and 1, red: channel 2, which neither Leica file uses).
"""

import hashlib
import io
import json
import pathlib
import shutil
import zipfile

import numpy as np
import pytest

from chisurf.plugins.emtk_layout import action_caption

from .conftest import REPO, two_detector_setup

HERE = pathlib.Path(__file__).resolve().parent
pytestmark = pytest.mark.usefixtures("hermetic")

GREEN, RED = [0, 1], [2]


def clsm_stack(name, channels):
    """The (frames, lines, pixels) image of *channels* as tttrlib reconstructs it from the file."""
    import tttrlib

    data = tttrlib.TTTR(str(REPO / "test" / "data" / "clsm" / name))
    return np.asarray(tttrlib.CLSMImage(tttr_data=data, channels=channels, fill=True).intensity)


def scaled_tile(image):
    """A frame sum min-max scaled to uint8 (all zero when the image is flat)."""
    a = image.astype(float)
    lo, hi = a.min(), a.max()
    if hi <= lo:
        return np.zeros(a.shape, np.uint8)
    return ((a - lo) / (hi - lo) * 255.0).clip(0, 255).astype(np.uint8)


def expected_mosaic(name):
    """Green and red tiles side by side, every tile shrunk so the mosaic is at most 512 wide."""
    tiles = [scaled_tile(clsm_stack(name, chs).sum(axis=0)) for chs in (GREEN, RED)]
    side = tiles[0].shape[1]
    step = max(1, (2 * side) // 512)  # 512 px tiles shrink by 2, 256 px tiles stay
    return np.hstack([t[::step, ::step] for t in tiles])


def sha(a):
    return hashlib.sha1(np.ascontiguousarray(a).tobytes()).hexdigest()


def model_on(folder, setup=True):
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    model = ImageBrowserModel()
    if setup:
        model.apply_setup_settings(two_detector_setup())
    model.open_folder(str(folder))
    return model


def rows(entries):
    return [(e["label"], e["badge"], e["rating"]) for e in entries]


# 1. the file list ---------------------------------------------------------------------------------------------------
def badge(path):
    """A row's size badge: the file size in MiB to one decimal."""
    return f"{path.stat().st_size / 2**20:.1f} MB"


def test_the_file_list_is_the_folders_photon_files(photon_folder):
    model = model_on(photon_folder)
    flat = ["corrupt.ptu", "Leica_SP8.ptu"]
    assert rows(model.file_entries()) == [(n, badge(photon_folder / n), 0) for n in flat]
    model.set_recursive(True)
    deep = ["corrupt.ptu", "sub/Leica_SP5.ptu", "Leica_SP8.ptu"]
    assert rows(model.file_entries()) == [(n, badge(photon_folder / n), 0) for n in deep]


def test_the_info_line_counts_the_listed_images(photon_folder):
    model = model_on(photon_folder)
    assert model.info_text() == "2 image(s) in imgs"
    assert model_on(photon_folder, setup=False).info_text() == "2 image(s) in imgs"


def test_a_text_file_is_never_listed(photon_folder):
    assert "notes.txt" not in [e["label"] for e in model_on(photon_folder).file_entries()]


# 2. the mosaics ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["Leica_SP8.ptu", "sub/Leica_SP5.ptu"])
def test_the_mosaic_is_the_files_scaled_detector_images(photon_folder, name):
    model = model_on(photon_folder)
    model.set_recursive(True)
    model.select_file(str(photon_folder / name))
    got = model.load_current()
    assert got is not None
    expected = expected_mosaic(pathlib.Path(name).name)
    assert got["mosaic"].shape == expected.shape == (256, 512)
    np.testing.assert_array_equal(got["mosaic"], expected)
    assert (got["cols"], got["rows"]) == (2, 1)
    # name | micro-time range (resolved against the file) | routing channels
    assert [(lab.split("  |  ")[0], lab.split("  |  ")[-1]) for lab in got["labels"]] == [
        ("G|G", "ch: 0,1"),
        ("R|G", "ch: 2"),
    ]
    assert got["mosaic"][:, 256:].max() == 0  # red: channel 2 holds no photons


def test_tile_labels_sit_in_the_corner_of_each_tile(photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    labels = model.load_current()["labels"]
    assert model.image_labels() == [  # 3 px into each 256 px tile
        {"x": 3, "y": 3, "text": labels[0]},
        {"x": 259, "y": 3, "text": labels[1]},
    ]
    model.show_labels = False
    assert model.tile_labels() == []


def test_a_file_without_an_image_has_no_mosaic_and_says_why(photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "corrupt.ptu"))
    assert model.load_current() is None
    assert model.current_image() is None
    assert "no image could be reconstructed" in model.image_error()
    assert "corrupt.ptu" in model.file_info()


def test_the_mosaic_without_a_setup_is_one_tile_with_all_channels(photon_folder):
    model = model_on(photon_folder, setup=False)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    got = model.load_current()
    assert got["labels"] == ["Image"] and got["mosaic"].shape == (512, 512)


def test_the_draw_loop_never_reads_a_photon_file(photon_folder):
    """``current_image`` answers from the cache only: a selection without a loaded mosaic shows nothing yet."""
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    assert model.current_image() is None and model.wanted_image() == str(
        photon_folder / "Leica_SP8.ptu"
    )
    model.load_current()
    assert model.current_image() is not None and model.wanted_image() is None


# 3. display lists ---------------------------------------------------------------------------------------------------
def test_the_default_colormap_is_one_of_the_choices():
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    model = ImageBrowserModel()
    assert model.colormap == "magma" and "magma" in model.colormap_options()
    assert model.rating_filter_options()[0] == "All"


# 4. rating, annotation, filters -------------------------------------------------------------------------------------
def test_rating_and_annotation_are_written_beside_the_files(photon_folder):
    model = model_on(photon_folder)
    path = str(photon_folder / "Leica_SP8.ptu")
    model.select_file(path)
    model.rate_2()
    model.set_note(path, "good cell, bleached after frame 3")
    on_disk = json.loads((photon_folder / ".image_browser_meta.json").read_text())
    assert on_disk == {
        "Leica_SP8.ptu": {"rating": 2, "annotation": "good cell, bleached after frame 3"}
    }
    sp8 = photon_folder / "Leica_SP8.ptu"
    assert rows(model.file_entries()) == [
        ("corrupt.ptu", badge(photon_folder / "corrupt.ptu"), 0),
        ("Leica_SP8.ptu", badge(sp8) + "  ★★", 2),
    ]
    assert model.rating_of(path) == 2 and model.current_rating == 2
    # a new model on the same folder reads the rating back
    again = model_on(photon_folder)
    assert again.rating_of(path) == 2 and again.note_of(path).startswith("good cell")


def test_the_rating_filters_list_the_files_with_those_stars(photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.rate_2()  # SP8 has two stars, corrupt.ptu none
    filters = {
        "All": ["corrupt.ptu", "Leica_SP8.ptu"],
        "≥ 1★": ["Leica_SP8.ptu"],
        "≥ 2★★": ["Leica_SP8.ptu"],
        "≥ 3★★★": [],
        "Only 0★": ["corrupt.ptu"],
    }
    assert model.rating_filter_options() == list(filters)
    for text, expected in filters.items():
        model.set_rating_filter(text)
        assert [e["label"] for e in model.file_entries()] == expected, text


def test_rows_carry_name_size_and_stars(photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.rate_3()
    table = {r["name"]: r for r in model.rows()}
    assert table["Leica_SP8.ptu"]["rating"] == "★★★"
    assert table["Leica_SP8.ptu"]["size_mb"] == pytest.approx(
        (photon_folder / "Leica_SP8.ptu").stat().st_size / 2**20
    )
    assert table["corrupt.ptu"]["rating"] == "" and table["corrupt.ptu"]["size_mb"] == 0.0


# 5. exports ---------------------------------------------------------------------------------------------------------
def test_copy_raw_files_copies_the_source_bytes(photon_folder, tmp_path):
    model = model_on(photon_folder)
    model.set_recursive(True)
    model.selected_files = [e["id"] for e in model.file_entries()]
    model.current_file = model.selected_files[0]
    model.do_copy_files(str(tmp_path / "copy"))
    got = {
        p.name: hashlib.md5(p.read_bytes()).hexdigest()
        for p in sorted((tmp_path / "copy").rglob("*.ptu"))
    }
    sources = {p.name: p for p in photon_folder.rglob("*.ptu")}
    assert got == {n: hashlib.md5(p.read_bytes()).hexdigest() for n, p in sorted(sources.items())}
    # the paths below the opened folder are kept: two files of one name do not collide
    assert (tmp_path / "copy" / "sub" / "Leica_SP5.ptu").is_file()
    assert "Copied 3 raw file(s)" in model.status_line


def test_tiff_stacks_are_the_files_detector_images(photon_folder, tmp_path):
    from chisurf.core.fio.image import imread

    model = model_on(photon_folder)
    model.set_recursive(True)
    model.selected_files = [
        str(photon_folder / "sub" / "Leica_SP5.ptu"),
        str(photon_folder / "Leica_SP8.ptu"),
    ]
    model.current_file = model.selected_files[0]
    model.do_export_tiff(str(tmp_path / "tiff"))
    got = {
        p.name: [list(imread(p).shape), int(imread(p).sum())]
        for p in sorted((tmp_path / "tiff").iterdir())
    }
    expected = {}
    for stem in ("Leica_SP5", "Leica_SP8"):
        for tag, chs in (("G-G", GREEN), ("R-G", RED)):
            stack = clsm_stack(stem + ".ptu", chs)
            expected[f"{stem}_{tag}.tiff"] = [list(stack.shape), int(stack.sum())]
    assert got == expected
    assert got["Leica_SP8_G-G.tiff"][0] == [93, 512, 512]  # 93 frames of 512 x 512
    assert "Wrote 4 TIFF stack(s)" in model.status_line


def docx_parts(path):
    """Paragraph texts and the embedded PNGs of a .docx in document order."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode()
        media = {n: z.read(n) for n in z.namelist() if n.startswith("word/media/")}
    import re

    items = []
    for m in re.finditer(r"<w:t[^>]*>(.*?)</w:t>|<a:blip r:embed=\"rId(\d+)\"", xml):
        items.append(("text", m.group(1)) if m.group(1) is not None else ("image", int(m.group(2))))
    return items, media


def test_the_magma_lut_exists_on_this_matplotlib():
    """``matplotlib.cm.get_cmap`` was removed in 3.9; the LUT silently became ``None`` (grey DOCX pictures)."""
    from chisurf.plugins.tttr.tttr_image_browser.core.image import get_magma_lut

    lut = get_magma_lut()
    assert lut is not None and lut.shape == (256, 3) and lut.dtype == np.uint8
    assert lut[0].max() < 10 and lut[255].min() > 180  # black to pale yellow


def test_the_docx_report_lists_rating_annotation_and_mosaic_per_file(photon_folder, tmp_path):
    """Heading, then per listed file: its name, ``Rating: n``, ``Annotation: text`` and the magma mosaic."""
    from chisurf.plugins.tttr.tttr_image_browser.core.image import get_magma_lut

    model = model_on(photon_folder)
    sp8 = str(photon_folder / "Leica_SP8.ptu")
    model.select_file(sp8)
    model.rate_2()
    model.set_note(sp8, "good cell")
    out = tmp_path / "report.docx"
    model.do_export_docx(str(out))
    items, media = docx_parts(out)
    texts = [v for k, v in items if k == "text"]
    assert texts == [
        "TTTR Image Browser Export",
        "corrupt.ptu",
        "Rating: 0",
        "Annotation: ",
        "Leica_SP8.ptu",
        "Rating: 2",
        "Annotation: good cell",
    ]
    assert [k for k, _ in items].count(
        "image"
    ) == 1  # the empty file has no picture
    from PIL import Image

    picture = np.asarray(Image.open(io.BytesIO(media["word/media/image1.png"])))
    model.select_file(sp8)
    mosaic = model.load_current()["mosaic"]
    assert np.array_equal(picture, get_magma_lut()[mosaic])
    assert "1 without an image" in model.status_line


# 6. toolbar, hand-off, caches, drop ---------------------------------------------------------------------------------
def test_next_hands_the_image_to_the_intensity_step(photon_folder):
    from chisurf.plugins.tttr.tttr_image_browser.gui.app import TTTRImageBrowserApp

    calls = []

    class Coordinator:
        def set_pipeline(self, **kw):
            calls.append(["set_pipeline", {k: pathlib.Path(v).name for k, v in kw.items()}])

        def goto_role(self, role):
            calls.append(["goto_role", role])

        def autorun_role(self, role):
            calls.append(["autorun_role", role])

    app = TTTRImageBrowserApp(coordinator=Coordinator())
    app.model.open_folder(str(photon_folder))
    app.model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    del calls[:]
    app.next_step()
    # picking already announced the selection; Next announces it once more, then moves on
    assert calls == [
        ["set_pipeline", {"source": "Leica_SP8.ptu"}],
        ["goto_role", "pixel_intensity"],
        ["autorun_role", "pixel_intensity"],
    ]


def test_clear_caches_removes_every_cache_folder(photon_folder):
    model = model_on(photon_folder)
    model.set_recursive(True)
    before = sorted(
        str(p.relative_to(photon_folder)) for p in photon_folder.rglob(".tttr_image_cache")
    )
    assert before == [".tttr_image_cache", "sub/.tttr_image_cache"]
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.load_current()
    model.clear_caches()
    assert sorted(photon_folder.rglob(".tttr_image_cache")) == []
    assert model.current_image() is None  # the in-memory mosaic went too
    assert model.status_line == "Image caches cleared."


def test_clear_empties_the_list_but_deletes_nothing(photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.rate_1()
    model.clear()
    assert model.file_entries() == [] and model.current_file is None
    assert (photon_folder / "Leica_SP8.ptu").is_file()
    assert (photon_folder / ".image_browser_meta.json").is_file()


def test_picked_images_open_their_folder_listing_exactly_them(photon_folder):
    """Images picked in the workspace open their folder, listing only them."""
    model = model_on(photon_folder)
    model.open_files([str(photon_folder / "sub" / "Leica_SP5.ptu")])
    assert [e["label"] for e in model.file_entries()] == ["Leica_SP5.ptu"]
    assert model.current_folder == str(photon_folder / "sub")
    assert model.current_file == str(photon_folder / "sub" / "Leica_SP5.ptu")
    assert not hasattr(model, "on_drop")


def test_every_toolbar_action_is_drawn():
    from emtk.testing import RecordingPainter

    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

    app = make_app()
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 800)
    strings = list(painter.strings)
    for caption in (
        "Use selected",  # the Input section of the workspace's images
        "Clear",
        "Clear caches",
        "Copy raw files",
        "TIFF",
        "DOCX",
        "Next → Intensity",
        action_caption("help"),
    ):
        assert caption in strings, caption
    assert "Include subfolders" in strings and action_caption("guide") in strings


# 7. enabled states --------------------------------------------------------------------------------------------------
def test_actions_are_greyed_until_they_can_act(photon_folder):
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    model = ImageBrowserModel()
    for name in (
        "copy_files",
        "export_tiff",
        "export_docx",
        "clear",
        "clear_caches",
        "select_all_files",
        "next_step",
        "rate_1",
        "current_rating",
        "colormap",
        "level_low",
    ):
        assert not model.enabled(name), name
    assert model.enabled("load_example")
    model.open_folder(str(photon_folder))
    assert (
        model.enabled("clear")
        and model.enabled("clear_caches")
        and model.enabled("export_docx")
        and model.enabled("select_all_files")
    )
    assert not model.enabled("copy_files") and not model.enabled("export_tiff")
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    assert model.enabled("copy_files") and model.enabled("export_tiff") and model.enabled("rate_1")
    assert not model.enabled("colormap")  # no mosaic yet
    model.load_current()
    assert (
        model.enabled("colormap") and model.enabled("reset_view") and not model.enabled("level_low")
    )
    model.auto_levels = False
    assert model.enabled("level_low") and model.enabled("level_high")


def test_actions_without_a_selection_say_so_and_ask_for_nothing(photon_folder):
    model = model_on(photon_folder)
    model.copy_files()
    model.export_tiff()
    assert model.dialog == "" and "Select image files first" in model.status_line
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    empty = ImageBrowserModel()
    empty.export_docx()
    assert empty.dialog == "" and "Open a folder" in empty.status_line


def test_an_action_asks_for_its_dialog(photon_folder):
    model = model_on(photon_folder)
    assert not hasattr(model, "choose_folder")  # the input is the workspace
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    for action, kind in (("copy_files", "copy"), ("export_tiff", "tiff"), ("export_docx", "docx")):
        getattr(model, action)()
        assert model.dialog == kind
        model.dialog = ""
    assert model.dialog_filename("docx") == "imgs.docx" and model.dialog_filename("copy") == ""


def test_opening_something_that_is_not_a_folder_says_so(tmp_path):
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    model = ImageBrowserModel()
    model.open_folder(str(tmp_path / "missing"))
    assert model.current_folder is None and "Not a folder" in model.status_line


# 8. selection -------------------------------------------------------------------------------------------------------
def test_multiple_selection_toggles_rows_and_switching_it_off_keeps_one(photon_folder):
    model = model_on(photon_folder)
    model.set_recursive(True)
    rows_ = {r["name"]: r for r in model.rows()}
    model.select_row(rows_["Leica_SP8.ptu"])
    assert model.selected_files == [str(photon_folder / "Leica_SP8.ptu")]
    model.set_multi_select(True)
    model.select_row(rows_["corrupt.ptu"])
    assert len(model.selected_files) == 2 and model.current_file.endswith("corrupt.ptu")
    model.select_row(rows_["corrupt.ptu"])  # toggled off
    assert model.selected_files == [
        str(photon_folder / "Leica_SP8.ptu")
    ] and model.current_file.endswith("Leica_SP8.ptu")
    model.select_row(rows_["sub/Leica_SP5.ptu"])
    model.set_multi_select(False)
    assert len(model.selected_files) == 1 and model.paths() == model.selected_files
    model.select_row(None)
    assert model.current_file is None and model.selected_files == []


# 9. persistence -----------------------------------------------------------------------------------------------------
def test_settings_round_trip_and_bad_values_are_ignored(photon_folder):
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    model = model_on(photon_folder)
    model.colormap, model.gamma, model.auto_levels = "viridis", 1.7, False
    model.show_labels, model.recursive, model.rating_filter = False, True, "≥ 1★"
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    state = json.loads(json.dumps(model.export_settings()))
    other = ImageBrowserModel()
    other.restore_settings(state)
    assert (other.colormap, other.gamma, other.auto_levels, other.show_labels) == (
        "viridis",
        1.7,
        False,
        False,
    )
    assert other.recursive is True and other.rating_filter == "≥ 1★"
    assert other.current_folder == str(photon_folder)
    assert (
        other.selected_files == [str(photon_folder / "Leica_SP8.ptu")]
        and other.setup_settings == model.setup_settings
    )
    third = ImageBrowserModel()
    third.restore_settings(
        {
            "colormap": "nope",
            "gamma": 99.0,
            "rating_filter": "x",
            "current_folder": str(photon_folder / "gone"),
            "recursive": "yes",
        }
    )
    assert third.colormap == "magma" and third.gamma == 1.0 and third.rating_filter == "All"
    assert third.current_folder is None and third.recursive is False
    third.restore_settings("not a dict")  # ignored


def test_the_app_remembers_through_the_host_hooks(photon_folder):
    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

    app = make_app()
    app.model.colormap = "gray"
    state = app.export_settings()
    other = make_app()
    other.restore_settings(state)
    assert other.model.colormap == "gray"


# 10. spec, tooltips, drawing, Qt-free -------------------------------------------------------------------------------
SPEC = HERE.parent / "gui" / "browser_emtk.view.json"


def spec_sections():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))

    def walk(sections):
        for section in sections:
            yield section
            yield from walk(section.get("sections", []))

    return list(walk(spec["sections"]))


def test_every_spec_key_exists_on_the_model():
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    model = ImageBrowserModel()
    for section in spec_sections():
        if section.get("attr"):
            assert hasattr(model, section["attr"]), section["attr"]
        for key in ("call", "options_source"):
            if section.get(key):
                assert callable(getattr(model, section[key])), section[key]
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        options = section.get("options") if isinstance(section.get("options"), dict) else {}
        for key in ("source", "selected_call"):
            if isinstance(options.get(key), str):
                assert callable(getattr(model, options[key])), options[key]
        if section.get("source"):
            assert callable(getattr(model, section["source"])) or hasattr(model, section["source"])
    # every window the app draws is in the spec
    assert {s["window"] for s in json.loads(SPEC.read_text())["sections"]} == {
        "toolbar",
        "files",
        "check",
        "display",
    }


def test_the_rating_filter_choice_carries_the_model_values_with_spaced_labels():
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    section = next(s for s in spec_sections() if s.get("attr") == "rating_filter")
    assert (
        section["options"] == ImageBrowserModel().rating_filter_options()
    )  # the values are the model's filter strings
    assert [l.replace(" ", "") for l in section["labels"]] == [
        o.replace(" ", "") for o in section["options"]
    ]  # same words, a gap before the stars
    assert len(section["labels"]) == 5


def test_every_spec_section_column_and_button_has_a_description():
    for section in spec_sections():
        assert section.get("description"), (
            section.get("attr") or section.get("title") or section.get("type")
        )
        options = section.get("options") if isinstance(section.get("options"), dict) else {}
        for column in options.get("columns", []):
            assert column.get("description"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_every_spec_field_is_declared_with_its_range():
    """Gamma and the 8-bit display levels have their ranges; the default colormap is one of the choices."""
    by_attr = {s["attr"]: s for s in spec_sections() if s.get("attr")}
    assert (by_attr["gamma"]["minimum"], by_attr["gamma"]["maximum"]) == (0.1, 5.0)
    assert (by_attr["level_low"]["minimum"], by_attr["level_high"]["maximum"]) == (0.0, 255.0)
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import COLORMAPS, ImageBrowserModel

    model = ImageBrowserModel()
    assert COLORMAPS[0:2] == ("viridis", "magma") and model.colormap in COLORMAPS


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("tttr_image_browser")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip_empty_and_populated(photon_folder):
    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app
    from test.gui.emtk_port_parity import emtk_inventory

    app = make_app()
    assert emtk_inventory(app)["controls_without_tooltip"] == []
    app.model.apply_setup_settings(two_detector_setup())
    app.model.open_folder(str(photon_folder))
    app.model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    app.model.load_current()
    assert emtk_inventory(app)["controls_without_tooltip"] == []
    app.pending_page = "setup"
    assert emtk_inventory(app)["controls_without_tooltip"] == []


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_the_app_draws_empty_and_populated_at_both_sizes(size, photon_folder):
    from emtk.testing import RecordingPainter

    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

    app = make_app()
    for _ in range(3):
        empty = RecordingPainter()
        app.draw(empty, 0, 0, *size)
    assert (
        "Open a folder with photon files (or drop one here) to see their detector-window mosaics."
        in empty.strings
        or any("Open a folder with photon files" in s for s in empty.strings)
    )
    app.model.apply_setup_settings(two_detector_setup())
    app.model.open_folder(str(photon_folder))
    app.model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    app.model.load_current()
    for _ in range(3):
        full = RecordingPainter()
        app.draw(full, 0, 0, *size)
    assert "Leica_SP8.ptu: 2 tile(s), mosaic 512 x 256 px" in full.strings
    assert any(s.startswith("G|G") for s in full.strings) and any(
        s.startswith("R|G") for s in full.strings
    )
    assert "x [px]" in full.strings and "level" in full.strings
    app.pending_page = "setup"
    for _ in range(3):
        setup = RecordingPainter()
        app.draw(setup, 0, 0, *size)
    assert "Use setup and continue" in setup.strings


# 11. the levels and the colours --------------------------------------------------------------------------------------
def test_the_level_range_and_histogram_describe_the_image(photon_folder):
    """Auto levels span 0 to the mosaic's maximum; the histogram counts every pixel."""
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.load_current()
    mosaic = model.current_image()
    top = int(mosaic.max())
    assert model.level_range() == (0.0, float(top))
    counts = model.histogram()
    np.testing.assert_array_equal(counts, np.bincount(mosaic.ravel(), minlength=256))
    assert len(counts) == 256 and int(counts.sum()) == mosaic.size and counts[top + 1 :].sum() == 0
    model.auto_levels, model.level_low, model.level_high = False, 20.0, 120.0
    assert model.level_range() == (20.0, 120.0)


@pytest.mark.parametrize("colormap", ["magma", "viridis", "gray"])
def test_the_drawn_colours_are_the_colormap_of_the_value_between_the_levels(
    photon_folder, colormap
):
    """A drawn pixel's colour: value -> (value - low) / (high - low) -> colormap (gamma 1, auto levels 0..max)."""
    from matplotlib import colormaps

    from chisurf.emtk.image_canvas import ImageCanvas

    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.load_current()
    mosaic = model.current_image()
    canvas = ImageCanvas("t")
    canvas.colormap, canvas.gamma, canvas.auto_levels = colormap, 1.0, True
    texture = canvas.texture(mosaic)
    low, high = float(mosaic.min()), float(mosaic.max())
    for y, x in ((10, 10), (100, 150), (200, 90), (255, 511), (130, 400)):
        # emtk's colormaps round to the nearest byte (matplotlib's bytes=True truncates).
        expected = tuple(
            np.round(
                np.asarray(colormaps[colormap]((mosaic[y, x] - low) / (high - low))) * 255
            ).astype(np.uint8)
        )
        assert tuple(texture.get_pixel(x, y)) == expected, (colormap, y, x)
    # gamma lifts a dim pixel; fixed levels clip
    canvas.gamma = 2.0
    _dim = np.argwhere((mosaic > 10) & (mosaic < 40))[0]
    assert texture is not canvas.texture(mosaic)
    canvas.auto_levels, canvas.low, canvas.high = False, 20.0, 120.0
    clipped = canvas.texture(mosaic)
    y, x = np.argwhere(mosaic == 0)[0]
    assert tuple(clipped.get_pixel(int(x), int(y))) == tuple(
        np.round(np.asarray(colormaps[colormap](0.0)) * 255).astype(np.uint8)
    )
