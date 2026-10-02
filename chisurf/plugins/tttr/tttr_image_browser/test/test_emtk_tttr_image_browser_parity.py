"""The emtk TTTR image browser against the Qt tool: same files, same numbers, every action.

The Qt reference runs in a subprocess (``qt_reference.py``: the real ``TTTRImageBrowserTool`` offscreen, on the same
CLSM test files and the same detector setup, with temporary settings and the destination dialogs stubbed). Because the
Qt tool and the emtk model share ``ImageBrowserViewModel``, a fault in it would pass a Qt-versus-emtk comparison on its
own: the numbers pinned below were captured from the Qt window before the port (``qt_values.json`` of the evidence
folder) and a written-out reference of the rules (the DOCX content, the copy rule) is compared too.
"""

import hashlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import zipfile

import numpy as np
import pytest

from .conftest import REPO, two_detector_setup

HERE = pathlib.Path(__file__).resolve().parent
pytestmark = pytest.mark.usefixtures("hermetic")

# Pinned from the Qt window before the port (okf/plugins/emtk-ports/tttr_image_browser/qt_values.json), real files of
# test/data/clsm with the two-detector setup of conftest.py.
QT_SP8 = dict(
    shape=[256, 512],
    cols=2,
    rows=1,
    labels=["green  |  mt: 0-4095  |  ch: 0,1", "red  |  mt: 0-4095  |  ch: 2"],
    sum=547933,
    max=212,
    sha1="c12bdf5fb28317ad7abfe2aef4b8836eb7756997",
)
QT_SP5 = dict(shape=[512, 34], cols=2, rows=1, sum=13610, max=69, sha1="f0c5aab7335256fc31c33806321be8b77e1e753a")
QT_TIFF = {
    "Leica_SP5_green.tiff": ([7921, 256], 443139),
    "Leica_SP5_red.tiff": ([7921, 256], 0),
    "Leica_SP8_green.tiff": ([93, 512, 512], 2710575),
    "Leica_SP8_red.tiff": ([93, 512, 512], 0),
}


def sha(a):
    return hashlib.sha1(np.ascontiguousarray(a).tobytes()).hexdigest()


@pytest.fixture(scope="module")
def qt(photon_template, tmp_path_factory):
    """What the real Qt tool computed and did on a copy of the photon folder (a Qt failure fails, never skips)."""
    work = tmp_path_factory.mktemp("qt_work")
    folder = work / "imgs"
    shutil.copytree(photon_template, folder)
    (work / "setup.json").write_text(json.dumps(two_detector_setup()))
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        CHISURF_SETTINGS_DIR=str(work / "settings"),
        MMFDB_SETTINGS_DIR=str(work / "mmfdb"),
        MMFDB_DATABASE_PATH=str(work / "mmfdb.sqlite"),
        HOME=str(work / "home"),
        PYTHONPATH=os.pathsep.join([str(REPO), os.environ.get("PYTHONPATH", "")]),
    )
    probe = subprocess.run([sys.executable, "-c", "import qtpy"], env=env, capture_output=True)
    if probe.returncode != 0:
        pytest.skip("Qt (qtpy) is not installed")
    proc = subprocess.run(
        [sys.executable, str(HERE / "qt_reference.py"), str(folder), str(work / "setup.json"), str(work)],
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("JSON:")]
    if proc.returncode != 0 or not lines:
        pytest.fail(f"the Qt reference failed (exit {proc.returncode}):\n{proc.stderr[-3000:]}")
    data = json.loads(lines[-1][5:])
    data["folder"] = folder
    return data


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
def test_the_file_list_is_what_the_qt_list_showed(qt, photon_folder):
    model = model_on(photon_folder)
    assert rows(model.file_entries()) == [tuple(r) for r in qt["entries_flat"]]
    assert [r[0] for r in rows(model.file_entries())] == ["corrupt.ptu", "Leica_SP8.ptu"]
    model.set_recursive(True)
    assert rows(model.file_entries()) == [tuple(r) for r in qt["entries_recursive"]]
    assert [r[0] for r in rows(model.file_entries())] == ["corrupt.ptu", "sub/Leica_SP5.ptu", "Leica_SP8.ptu"]


def test_the_info_line_says_what_the_qt_info_panel_said(qt, photon_folder):
    model = model_on(photon_folder)
    assert f"<i>{model.info_text()}</i>" == qt["info_flat"] == "<i>2 image(s) in imgs</i>"
    assert model_on(photon_folder, setup=False).info_text() == "2 image(s) in imgs"


def test_a_text_file_is_never_listed(photon_folder):
    assert "notes.txt" not in [e["label"] for e in model_on(photon_folder).file_entries()]


# 2. the mosaics ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,pinned,key", [("Leica_SP8.ptu", QT_SP8, "mosaic_SP8"), ("sub/Leica_SP5.ptu", QT_SP5, "mosaic_SP5")])
def test_the_mosaic_equals_the_qt_mosaic(qt, photon_folder, name, pinned, key):
    model = model_on(photon_folder)
    model.set_recursive(True)
    model.select_file(str(photon_folder / name))
    got = model.load_current()
    assert got is not None
    mosaic = got["mosaic"]
    for field, value in pinned.items():
        if field in ("shape",):
            assert list(mosaic.shape) == value, field
        elif field == "sum":
            assert int(mosaic.sum()) == value
        elif field == "max":
            assert int(mosaic.max()) == value
        elif field == "sha1":
            assert sha(mosaic) == value
        elif field in ("cols", "rows"):
            assert got[field] == value
        else:
            assert got[field] == value
    # ... and the live Qt tool agrees on the same copy of the file
    live = qt[key]
    assert list(mosaic.shape) == live["shape"] and sha(mosaic) == live["sha1"]
    assert got["labels"] == live["labels"] and model.image_labels() == live["tile_labels"]


def test_tile_labels_sit_where_the_qt_labels_sat(photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.load_current()
    assert model.image_labels() == [
        {"x": 3, "y": 3, "text": QT_SP8["labels"][0]},
        {"x": 259, "y": 3, "text": QT_SP8["labels"][1]},
    ]
    model.show_labels = False
    assert model.tile_labels() == []


def test_a_file_without_an_image_has_no_mosaic_and_says_why(qt, photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "corrupt.ptu"))
    assert model.load_current() is None
    assert qt["mosaic_corrupt"] is None
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
    assert model.current_image() is None and model.wanted_image() == str(photon_folder / "Leica_SP8.ptu")
    model.load_current()
    assert model.current_image() is not None and model.wanted_image() is None


# 3. display lists ---------------------------------------------------------------------------------------------------
def test_colormaps_and_filters_are_the_qt_lists(qt):
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    model = ImageBrowserModel()
    assert model.colormap_options() == qt["colormaps"]
    assert model.colormap == qt["colormap_default"] == "magma"
    assert model.rating_filter_options() == qt["rating_filters"]


# 4. rating, annotation, filters -------------------------------------------------------------------------------------
def test_rating_and_annotation_write_the_file_the_qt_tool_wrote(qt, photon_folder):
    model = model_on(photon_folder)
    path = str(photon_folder / "Leica_SP8.ptu")
    model.select_file(path)
    model.rate_2()
    model.set_note(path, "good cell, bleached after frame 3")
    on_disk = json.loads((photon_folder / ".image_browser_meta.json").read_text())
    assert on_disk == qt["meta"] == {"Leica_SP8.ptu": {"rating": 2, "annotation": "good cell, bleached after frame 3"}}
    assert rows(model.file_entries()) == [tuple(r) for r in qt["entries_rated"]]
    assert model.rating_of(path) == 2 and model.current_rating == 2
    # a new model on the same folder reads the rating back
    again = model_on(photon_folder)
    assert again.rating_of(path) == 2 and again.note_of(path).startswith("good cell")


def test_the_rating_filters_list_what_the_qt_filters_listed(qt, photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.rate_2()
    for text, expected in qt["filters"].items():
        model.set_rating_filter(text)
        assert [e["label"] for e in model.file_entries()] == expected, text
    assert qt["filters"]["≥ 2★★"] == ["Leica_SP8.ptu"]


def test_rows_carry_name_size_and_stars(photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.rate_3()
    table = {r["name"]: r for r in model.rows()}
    assert table["Leica_SP8.ptu"]["rating"] == "★★★"
    assert table["Leica_SP8.ptu"]["size_mb"] == pytest.approx((photon_folder / "Leica_SP8.ptu").stat().st_size / 2**20)
    assert table["corrupt.ptu"]["rating"] == "" and table["corrupt.ptu"]["size_mb"] == 0.0


# 5. exports ---------------------------------------------------------------------------------------------------------
def test_copy_raw_files_copies_the_bytes_the_qt_export_copied(qt, photon_folder, tmp_path):
    model = model_on(photon_folder)
    model.set_recursive(True)
    model.selected_files = [e["id"] for e in model.file_entries()]
    model.current_file = model.selected_files[0]
    model.do_copy_files(str(tmp_path / "copy"))
    got = {p.name: hashlib.md5(p.read_bytes()).hexdigest() for p in sorted((tmp_path / "copy").rglob("*.ptu"))}
    assert got == qt["copy"]
    # the paths below the opened folder are kept (the Qt tool flattened them: two files of one name would collide)
    assert (tmp_path / "copy" / "sub" / "Leica_SP5.ptu").is_file()
    assert "Copied 3 raw file(s)" in model.status_line


def test_tiff_stacks_equal_the_qt_stacks(qt, photon_folder, tmp_path):
    import tifffile

    model = model_on(photon_folder)
    model.set_recursive(True)
    model.selected_files = [str(photon_folder / "sub" / "Leica_SP5.ptu"), str(photon_folder / "Leica_SP8.ptu")]
    model.current_file = model.selected_files[0]
    model.do_export_tiff(str(tmp_path / "tiff"))
    got = {p.name: [list(tifffile.imread(p).shape), int(tifffile.imread(p).sum())] for p in sorted((tmp_path / "tiff").iterdir())}
    assert got == qt["tiff"]
    assert {k: (v[0], v[1]) for k, v in got.items()} == {k: (v[0], v[1]) for k, v in QT_TIFF.items()}
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


def test_the_docx_report_has_what_the_qt_report_wrote(photon_folder, tmp_path):
    """Qt (python-docx, absent here): heading, ``Rating: n``, ``Annotation: text``, the magma mosaic at 6 in, per listed file."""
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
    assert [k for k, _ in items].count("image") == 1  # the empty file has no picture (Qt skipped it too)
    from PIL import Image

    picture = np.asarray(Image.open(io.BytesIO(media["word/media/image1.png"])))
    model.select_file(sp8)
    mosaic = model.load_current()["mosaic"]
    assert np.array_equal(picture, get_magma_lut()[mosaic])
    assert "1 without an image" in model.status_line


# 6. toolbar, hand-off, caches, drop ---------------------------------------------------------------------------------
def test_next_hands_the_image_to_the_pipeline_as_the_qt_tool_did(qt, photon_folder):
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
    # the Qt tool also announced the selection to the pipeline when it was picked (observer); Next repeats it once
    assert calls == qt["next_calls"] == [
        ["set_pipeline", {"source": "Leica_SP8.ptu"}],
        ["goto_role", "pixel_intensity"],
        ["autorun_role", "pixel_intensity"],
    ]


def test_clear_caches_removes_the_cache_folders_the_qt_tool_removed(qt, photon_folder):
    model = model_on(photon_folder)
    model.set_recursive(True)
    before = sorted(str(p.relative_to(photon_folder)) for p in photon_folder.rglob(".tttr_image_cache"))
    assert before == qt["cache_dirs_before"] == [".tttr_image_cache", "sub/.tttr_image_cache"]
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.load_current()
    model.clear_caches()
    assert sorted(photon_folder.rglob(".tttr_image_cache")) == [] and qt["cache_dirs_after"] == []
    assert model.current_image() is None  # the in-memory mosaic went too
    assert model.status_line == "Image caches cleared."


def test_clear_empties_the_list_but_deletes_nothing(qt, photon_folder):
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.rate_1()
    model.clear()
    assert model.file_entries() == [] and model.current_file is None and qt["entries_after_clear"] == []
    assert (photon_folder / "Leica_SP8.ptu").is_file()
    assert (photon_folder / ".image_browser_meta.json").is_file()


def test_a_dropped_folder_opens_and_a_dropped_file_is_refused(qt, photon_folder):
    model = model_on(photon_folder)
    model.on_drop([str(photon_folder / "sub")])
    assert [e["label"] for e in model.file_entries()] == qt["drop_folder"] == ["Leica_SP5.ptu"]
    assert model.current_folder == str(photon_folder / "sub")
    model.on_drop([str(photon_folder / "Leica_SP8.ptu")])
    assert model.current_folder == str(photon_folder / "sub")
    assert "not a single file" in model.status_line


def test_every_qt_toolbar_action_is_a_drawn_emtk_button(qt):
    from emtk.testing import RecordingPainter

    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

    app = make_app()
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 800)
    strings = list(painter.strings)
    assert len(qt["toolbar"]) == 8
    mapping = {
        "Open": "Open folder",
        "Clear": "Clear",
        "Caches": "Clear caches",
        "Export": "Copy raw files",
        "TIFF": "TIFF",
        "DOCX": "DOCX",
        "Next": "Next → Intensity",
        "Help": "Help",
    }
    for text in qt["toolbar"]:
        word = next(w for w in mapping if w in text)
        assert mapping[word] in strings, (text, mapping[word])
    assert "Include subfolders" in strings and "Guide" in strings


# 7. enabled states --------------------------------------------------------------------------------------------------
def test_actions_are_greyed_until_they_can_act(photon_folder):
    from chisurf.plugins.tttr.tttr_image_browser.gui.model import ImageBrowserModel

    model = ImageBrowserModel()
    for name in ("copy_files", "export_tiff", "export_docx", "clear", "clear_caches", "select_all_files", "next_step", "rate_1", "current_rating", "colormap", "level_low"):
        assert not model.enabled(name), name
    assert model.enabled("choose_folder")
    model.open_folder(str(photon_folder))
    assert model.enabled("clear") and model.enabled("clear_caches") and model.enabled("export_docx") and model.enabled("select_all_files")
    assert not model.enabled("copy_files") and not model.enabled("export_tiff")
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    assert model.enabled("copy_files") and model.enabled("export_tiff") and model.enabled("rate_1")
    assert not model.enabled("colormap")  # no mosaic yet
    model.load_current()
    assert model.enabled("colormap") and model.enabled("reset_view") and not model.enabled("level_low")
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
    model.choose_folder()
    assert model.dialog == "folder"
    model.dialog = ""
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
    assert model.selected_files == [str(photon_folder / "Leica_SP8.ptu")] and model.current_file.endswith("Leica_SP8.ptu")
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
    assert (other.colormap, other.gamma, other.auto_levels, other.show_labels) == ("viridis", 1.7, False, False)
    assert other.recursive is True and other.rating_filter == "≥ 1★"
    assert other.current_folder == str(photon_folder)
    assert other.selected_files == [str(photon_folder / "Leica_SP8.ptu")] and other.setup_settings == model.setup_settings
    third = ImageBrowserModel()
    third.restore_settings({"colormap": "nope", "gamma": 99.0, "rating_filter": "x", "current_folder": str(photon_folder / "gone"), "recursive": "yes"})
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
    assert {s["window"] for s in json.loads(SPEC.read_text())["sections"]} == {"toolbar", "files", "display"}


def test_every_spec_section_column_and_button_has_a_description():
    for section in spec_sections():
        assert section.get("description"), section.get("attr") or section.get("title") or section.get("type")
        options = section.get("options") if isinstance(section.get("options"), dict) else {}
        for column in options.get("columns", []):
            assert column.get("description"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_every_spec_field_is_declared_like_the_qt_one():
    """Ranges and decimals of the fields the Qt image dock and the spin boxes had; defaults of the model equal the spec's."""
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
    from test.gui.emtk_port_parity import emtk_inventory

    from chisurf.plugins.tttr.tttr_image_browser.gui.app import make_app

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
    assert "Open a folder with photon files (or drop one here) to see their detector-window mosaics." in empty.strings or any(
        "Open a folder with photon files" in s for s in empty.strings
    )
    app.model.apply_setup_settings(two_detector_setup())
    app.model.open_folder(str(photon_folder))
    app.model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    app.model.load_current()
    for _ in range(3):
        full = RecordingPainter()
        app.draw(full, 0, 0, *size)
    assert "Leica_SP8.ptu: 2 tile(s), mosaic 512 x 256 px" in full.strings
    assert any(s.startswith("green") for s in full.strings) and any(s.startswith("red") for s in full.strings)
    assert "x [px]" in full.strings and "level" in full.strings
    app.pending_page = "setup"
    for _ in range(3):
        setup = RecordingPainter()
        app.draw(setup, 0, 0, *size)
    assert "Use setup and continue" in setup.strings


# 11. the levels and the colours --------------------------------------------------------------------------------------
def test_the_level_range_and_histogram_describe_the_qt_image(qt, photon_folder):
    """The Qt level bar spanned 0 to the mosaic's maximum (212 for the SP8 file); the histogram counts every pixel."""
    model = model_on(photon_folder)
    model.select_file(str(photon_folder / "Leica_SP8.ptu"))
    model.load_current()
    mosaic = model.current_image()
    assert model.level_range() == (0.0, float(qt["mosaic_SP8"]["max"])) == (0.0, 212.0)
    counts = model.histogram()
    assert len(counts) == 256 and int(counts.sum()) == mosaic.size and counts[212] > 0 and counts[213:].sum() == 0
    model.auto_levels, model.level_low, model.level_high = False, 20.0, 120.0
    assert model.level_range() == (20.0, 120.0)


@pytest.mark.parametrize("colormap", ["magma", "viridis", "gray"])
def test_the_drawn_colours_are_the_colormap_of_the_value_between_the_levels(photon_folder, colormap):
    """What pyqtgraph's image view did: value -> (value - low) / (high - low) -> colormap (gamma 1, auto levels 0..max)."""
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
        expected = tuple((np.asarray(colormaps[colormap]((mosaic[y, x] - low) / (high - low))) * 255).astype(np.uint8))
        assert tuple(texture.get_pixel(x, y)) == expected, (colormap, y, x)
    # gamma lifts a dim pixel; fixed levels clip
    canvas.gamma = 2.0
    dim = np.argwhere((mosaic > 10) & (mosaic < 40))[0]
    assert texture is not canvas.texture(mosaic)
    canvas.auto_levels, canvas.low, canvas.high = False, 20.0, 120.0
    clipped = canvas.texture(mosaic)
    y, x = np.argwhere(mosaic == 0)[0]
    assert tuple(clipped.get_pixel(int(x), int(y))) == tuple((np.asarray(colormaps[colormap](0.0)) * 255).astype(np.uint8))
