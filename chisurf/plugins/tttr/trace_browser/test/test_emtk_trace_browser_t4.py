"""The native Trace Browser, card T4: Export, CSV, DOCX, Delete, hand-offs, Help and Guide, manifest entry.

Everything runs on temporary COPIES of ``test/data/tttr/BH/132/BH_SPC132.spc``. Export, CSV and Delete write only
inside the pytest temp folders. The reference for the ALEX setup on that file is the one the legacy engine
gave (``test_binning_trace_browser.py``): 6233 bins of 10 ms, per-detector sums ``[22443, 56257, 0]`` for
``green``, ``red``, ``yellow`` (62329 bins at 1 ms). ``python-docx`` is not installed in every environment, so
the DOCX tests inject a stand-in module that records what the report would hold; the button's disabled state
without the package is tested by making the import fail.
"""

import csv
import json
import pathlib
import shutil

import pytest
from emtk import im_widgets
from emtk.keys import KEY_DELETE

from chisurf.plugins.tttr.trace_browser.test.conftest import ALEX
from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t2 import (
    BH132,
    ENTRY,
    GUI,
    META,
    SPEC,
    all_sections,
    commit,
    frames,
    pressing,
    table,
)
from chisurf.plugins.tttr.trace_browser.test.test_emtk_trace_browser_t3b import (
    BINS_1MS,
    BINS_10MS,
    LABELS,
    SUMS,
    settle_all,
)

REPO = next(p for p in pathlib.Path(__file__).parents if (p / "pyproject.toml").exists())
BUTTONS = ["Select all", "Export", "CSV", "DOCX", "Delete", "HMM", "TW", "NDX"]


# ---- helpers ---------------------------------------------------------------------------------
@pytest.fixture
def work(tmp_path):
    """``work/data`` with three real measurements (``m000``, ``m001``, ``sub/m002``) and companions.

    ``m000.set`` shares the stem of ``m000.spc`` (a companion file the delete moves along), ``notes.txt`` is
    a file the browser does not list and the delete must not touch. ``outside/keep.spc`` is a real
    measurement beside the data folder: no action may ever touch it.
    """
    if not BH132.exists():
        pytest.skip("sample TTTR data missing")
    data = tmp_path / "work" / "data"
    (data / "sub").mkdir(parents=True)
    shutil.copy(BH132, data / "m000.spc")
    shutil.copy(BH132, data / "m001.spc")
    shutil.copy(BH132, data / "sub" / "m002.spc")
    (data / "m000.set").write_bytes(b"companion of m000")
    (data / "notes.txt").write_bytes(b"not a measurement")
    outside = tmp_path / "work" / "outside"
    outside.mkdir()
    shutil.copy(BH132, outside / "keep.spc")
    return data


def make_app(on_request=None):
    """The app on its Browser page with the real ALEX setup accepted (precompute off)."""
    from chisurf.plugins.tttr.trace_browser.gui.app import TraceBrowserApp

    app = TraceBrowserApp(on_request=on_request)
    app.model.accept_setup(json.loads(json.dumps(ALEX)))
    app.model.precompute_after_scan = False
    return app


def open_folder(app, folder, subfolders=False):
    """Open *folder* through the model's request path and draw until everything is idle."""
    if subfolders:
        commit(app, "include_subfolders", True)
    app.model.request("open_folder", folder)
    settle_all(app)


def snapshot(folder):
    """``{relative path: bytes}`` of every file under *folder* (the cache folder excluded)."""
    return {
        str(p.relative_to(folder)): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and ".tttr_trace_cache" not in p.parts
    }


def button_states(app, size=(1200, 800)):
    """Draw a frame and return ``{button label: disabled}`` of every button the spec drew."""
    from emtk.im_core import get_current_context

    states = {}
    real = im_widgets.button

    def spy(label, *args, **kwargs):
        result = real(label, *args, **kwargs)
        states[str(label).split("##")[0]] = bool(get_current_context()._last_item_disabled)
        return result

    im_widgets.button = spy
    try:
        frames(app, size, 1)
    finally:
        im_widgets.button = real
    return states


def select(app, *names):
    """Select the rows *names* the way the table keeps a multi-row selection (``also_selected``)."""
    control = table(app)
    paths = [str(app.model.current_folder / n) for n in names]
    position = next(i for i, index in enumerate(control.order()) if control.key_of(index) == paths[0])
    control._select_position(position)                       # a click: the model's selection follows
    control.also_selected = set(paths[1:])                   # the other rows, as Select all leaves them
    frames(app, n=2)


def press(app, monkeypatch, label, n=3):
    """Press the real button *label* once and draw a few frames."""
    with pressing(monkeypatch, label):
        frames(app, n=1)
    frames(app, n=n)


def choose_destination(app, monkeypatch, destination):
    """Drive the open folder dialog: go to *destination* and press Choose."""
    assert app.dialog is not None and app.dialog.mode == "folder"
    app.dialog.directory = str(destination)
    app.dialog.selection = []
    with pressing(monkeypatch, "Choose"):
        frames(app, n=1)
    assert app.dialog is None
    settle_all(app)


def rows_of(path):
    """The rows of a CSV file."""
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.reader(handle))


class FakeDocx:
    """A stand-in for ``python-docx``: the module, a recording ``Document`` and ``Inches``."""

    documents: list = []

    class Document:
        def __init__(self):
            self.ops = []
            FakeDocx.documents.append(self)

        def add_heading(self, text, level=1):
            self.ops.append(("heading", level, text))

        def add_paragraph(self, text=""):
            self.ops.append(("paragraph", text))

        def add_picture(self, path, width=None):
            data = pathlib.Path(path).read_bytes()          # the picture must exist while it is added
            self.ops.append(("picture", pathlib.Path(path).name, data[:8] == b"\x89PNG\r\n\x1a\n", len(data), width))

        def save(self, path):
            pathlib.Path(path).write_text(json.dumps(self.ops, default=str))

    @staticmethod
    def Inches(value):
        return ("inches", value)


@pytest.fixture
def with_docx(monkeypatch):
    """Make ``python-docx`` importable (the stand-in) for the model."""
    from chisurf.plugins.tttr.trace_browser.gui import model as model_module

    FakeDocx.documents = []
    monkeypatch.setattr(model_module, "_docx_modules", lambda: (FakeDocx.Document, FakeDocx.Inches))
    return FakeDocx


@pytest.fixture
def without_docx(monkeypatch):
    """Make the ``python-docx`` import fail for the model."""
    from chisurf.plugins.tttr.trace_browser.gui import model as model_module

    monkeypatch.setattr(model_module, "_docx_modules", lambda: None)


# ---- multi-row selection through the real table -----------------------------------------------
def test_select_all_selects_every_row_in_the_real_table_state(work, monkeypatch):
    app = make_app()
    try:
        open_folder(app, work, subfolders=True)
        control = table(app)
        assert control.selected_indices() == [0]                    # the first row, selected by the scan
        assert [p.name for p in app.model.selection_paths()] == ["m000.spc"]
        press(app, monkeypatch, "Select all")
        assert len(control.selected_indices()) == 3 and len(control.also_selected) == 3
        assert [p.name for p in app.model.selection_paths()] == ["m000.spc", "m001.spc", "m002.spc"]
        assert app.model.multi_selection == [r["path"] for r in app.model.rows]
        assert "3 file(s) selected" in app.model.status_text
        # a click on one row goes back to that file alone
        control._select_position(1)
        frames(app, n=2)
        assert [p.name for p in app.model.selection_paths()] == ["m001.spc"]
        assert control.selected_indices() == [1]
    finally:
        app.close()


def test_a_subset_in_the_table_state_is_the_selection(work):
    app = make_app()
    try:
        open_folder(app, work)
        select(app, "m000.spc", "m001.spc")
        assert [p.name for p in app.model.selection_paths()] == ["m000.spc", "m001.spc"]
        assert app.model.enabled("export_selected") and app.model.enabled("delete_selected")
    finally:
        app.close()


def test_the_new_buttons_are_in_the_spec_in_order():
    spec = json.loads(SPEC.read_text())
    labels = [b["label"] for s in all_sections(spec) for b in s.get("buttons", [])]
    assert labels[4:12] == BUTTONS                                   # after the first row of four
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    for section in all_sections(spec):
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        options = section.get("options") or {}
        if options.get("delete_call"):
            assert callable(getattr(model, options["delete_call"]))


# ---- Export ---------------------------------------------------------------------------------------
def test_export_copies_exactly_the_selected_files_with_equal_bytes(work, tmp_path, monkeypatch):
    dest = tmp_path / "exported"
    dest.mkdir()
    before = snapshot(work.parent)
    app = make_app()
    try:
        open_folder(app, work, subfolders=True)
        select(app, "m000.spc", "sub/m002.spc")
        press(app, monkeypatch, "Export")
        assert app.dialog.title == "Select destination folder for the exported files"
        choose_destination(app, monkeypatch, dest)
        assert sorted(p.name for p in dest.iterdir()) == ["m000.spc", "m002.spc"]
        assert (dest / "m000.spc").read_bytes() == (work / "m000.spc").read_bytes()
        assert (dest / "m002.spc").read_bytes() == (work / "sub" / "m002.spc").read_bytes()
        assert "Exported 2/2 file(s)" in app.model.status_text and app.model.actions_done == 1
        for rel, data in before.items():                          # no source file changed or disappeared
            assert (work.parent / rel).read_bytes() == data
    finally:
        app.close()


def test_a_cancelled_export_dialog_copies_nothing(work, tmp_path, monkeypatch):
    dest = tmp_path / "exported"
    dest.mkdir()
    app = make_app()
    try:
        open_folder(app, work)
        press(app, monkeypatch, "Export")
        assert app.dialog is not None
        with pressing(monkeypatch, "Cancel"):
            frames(app, n=1)
        settle_all(app)
        assert app.dialog is None and list(dest.iterdir()) == [] and app.model.actions_done == 0
    finally:
        app.close()


def test_export_never_overwrites_one_selected_file_with_another_of_the_same_name(work, tmp_path):
    shutil.copy(BH132, work / "sub" / "m000.spc")             # same name in a sub-folder, other bytes below
    (work / "sub" / "m000.spc").write_bytes(b"x" + (work / "sub" / "m000.spc").read_bytes())
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.include_subfolders = True
    model.image_probe = lambda path: False
    model.open_folder(work)
    paths = [work / "m000.spc", work / "sub" / "m000.spc"]
    assert model.export_files(tmp_path / "flat", paths) == 2
    assert sorted(p.name for p in (tmp_path / "flat").iterdir()) == ["m000.spc", "m000__2.spc"]
    assert (tmp_path / "flat" / "m000.spc").read_bytes() == paths[0].read_bytes()
    assert (tmp_path / "flat" / "m000__2.spc").read_bytes() == paths[1].read_bytes()


def test_exporting_a_file_onto_itself_changes_nothing(work):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.image_probe = lambda path: False
    model.open_folder(work)
    original = (work / "m000.spc").read_bytes()
    assert model.export_files(work, [work / "m000.spc"]) == 0
    assert (work / "m000.spc").read_bytes() == original


def test_the_buttons_are_greyed_without_a_selection_or_a_host(work):
    app = make_app()
    try:
        states = button_states(app)                                   # no folder: nothing to act on
        assert [states[label] for label in BUTTONS[:5]] == [True] * 5
        open_folder(app, work)
        states = button_states(app)
        assert states["Select all"] is False and states["Export"] is False and states["CSV"] is False
        assert states["Delete"] is False
        assert states["HMM"] is True and states["TW"] is True and states["NDX"] is True   # no host
        app.model.set_selection([])
        app.model.multi_selection = []
        states = button_states(app)
        assert states["Export"] is True and states["Delete"] is True and states["CSV"] is True
    finally:
        app.close()


# ---- CSV ----------------------------------------------------------------------------------------
def test_csv_has_the_header_the_bins_and_the_series_columns(work, tmp_path, monkeypatch):
    dest = tmp_path / "csv"
    dest.mkdir()
    app = make_app()
    try:
        open_folder(app, work)
        select(app, "m001.spc")
        press(app, monkeypatch, "CSV")
        assert app.dialog.title == "Select destination folder for the CSV files"
        choose_destination(app, monkeypatch, dest)
        files = sorted(p.name for p in dest.glob("*.csv"))
        assert files == ["m001_trace.csv"]
        rows = rows_of(dest / files[0])
        assert rows[0] == ["time_ms"] + LABELS                       # the RPC export's header (see below)
        assert len(rows) - 1 == BINS_10MS
        columns = list(zip(*[[float(v) for v in row] for row in rows[1:]]))
        assert [int(sum(c)) for c in columns[1:]] == SUMS
        assert columns[0][0] == 0.0 and abs(columns[0][-1] - 62.32) < 1e-6
        # The first column is labelled time_ms by api/io.py but holds seconds (62.32 at the end of a
        # 62.3 s measurement): pinned here so the day the label is corrected this test says so.
        assert "Exported 1/1 CSV file(s)" in app.model.status_text
    finally:
        app.close()


def test_csv_of_a_selection_writes_one_file_per_file_and_follows_the_bin_window(work, tmp_path):
    dest = tmp_path / "csv1ms"
    app = make_app()
    try:
        open_folder(app, work)
        commit(app, "window_ms", 1.0)
        settle_all(app)
        written = app.model.export_csv_files(dest, [work / "m000.spc", work / "m001.spc"])
        assert sorted(pathlib.Path(w).name for w in written) == ["m000_trace.csv", "m001_trace.csv"]
        for w in written:
            assert len(rows_of(w)) - 1 == BINS_1MS
    finally:
        app.close()


def test_csv_falls_back_to_the_local_export_when_the_rpc_gives_nothing(work, tmp_path, monkeypatch):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.accept_setup(json.loads(json.dumps(ALEX)))
    model.open_folder(work)
    monkeypatch.setattr(model.client, "export_csv", lambda *a, **k: [])
    written = model.export_csv_files(tmp_path / "local", [work / "m000.spc"])
    assert [pathlib.Path(w).name for w in written] == ["m000_bin10ms.csv"]
    rows = rows_of(written[0])
    assert rows[0] == ["time_s"] + LABELS and len(rows) - 1 == BINS_10MS
    assert [int(sum(float(r[i]) for r in rows[1:])) for i in (1, 2, 3)] == SUMS


def test_the_qt_widget_and_the_emtk_app_export_the_same_csv(qapp, qtbot, work, tmp_path, monkeypatch):
    """The Qt tool's *CSV* handler and the app write the same bytes for the same file."""
    pytest.importorskip("pyqtgraph")
    from qtpy.QtWidgets import QFileDialog

    from chisurf.plugins.tttr.trace_browser import widget as widget_module

    only = tmp_path / "only"
    only.mkdir()
    shutil.copy(work / "m000.spc", only / "m000.spc")
    qt_out, app_out = tmp_path / "qt_out", tmp_path / "app_out"
    qt_out.mkdir()
    app_out.mkdir()

    widget = widget_module.TraceBrowser()
    qtbot.addWidget(widget)
    widget.detector_page._load_data(json.loads(json.dumps(ALEX)))
    widget._on_continue()
    monkeypatch.setattr(widget, "_plot_file", lambda *a, **k: None)
    monkeypatch.setattr(widget, "_precompute_all_traces", lambda *a, **k: None)
    widget._open_folder(only)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(qt_out))
    monkeypatch.setattr(widget_module.dialogs, "information", lambda *a, **k: None)
    widget._on_export_csv()
    qt_files = sorted(p.name for p in qt_out.glob("*.csv"))
    assert qt_files == ["m000_trace.csv"]

    app = make_app()
    try:
        open_folder(app, only)
        written = app.model.export_csv_files(app_out, [only / "m000.spc"])
    finally:
        app.close()
    assert [pathlib.Path(w).name for w in written] == qt_files
    assert (app_out / qt_files[0]).read_bytes() == (qt_out / qt_files[0]).read_bytes()
    assert len(rows_of(app_out / qt_files[0])) - 1 == BINS_10MS


# ---- DOCX -----------------------------------------------------------------------------------------
def test_docx_report_holds_every_selected_file_with_rating_note_and_picture(work, with_docx, monkeypatch):
    app = make_app()
    try:
        open_folder(app, work)
        app.model.set_rating(work / "m000.spc", 3)
        app.model.set_notes(work / "m000.spc", "good burst")
        select(app, "m000.spc", "m001.spc")
        states = button_states(app)
        assert states["DOCX"] is False                                  # python-docx "installed"
        press(app, monkeypatch, "DOCX")
        settle_all(app)
        saved = work / "data.docx"
        assert saved.exists() and "Saved: " in app.model.status_text and app.model.actions_done == 1
        ops = json.loads(saved.read_text())
        assert ops[0] == ["heading", 1, "Trace Browser Export"]
        headings = [o[2] for o in ops if o[0] == "heading" and o[1] == 2]
        assert headings == ["m000.spc", "m001.spc"]
        texts = [o[1] for o in ops if o[0] == "paragraph"]
        assert f"Folder: {work}" in texts and "Rating: 3" in texts and "Rating: 0" in texts
        assert "Annotation: good burst" in texts and sum(t.startswith("Annotation") for t in texts) == 1
        pictures = [o for o in ops if o[0] == "picture"]
        assert [p[1] for p in pictures] == ["m000.png", "m001.png"]
        assert all(p[2] is True for p in pictures)                      # a PNG header
        assert all(p[3] > 1000 for p in pictures)                       # a real picture, not an empty file
        assert all(p[4] == ["inches", 6] for p in pictures)             # six inches wide, as in Qt
    finally:
        app.close()


def test_docx_is_disabled_with_a_reason_when_python_docx_is_missing(work, without_docx, monkeypatch):
    app = make_app()
    try:
        open_folder(app, work)
        select(app, "m000.spc")
        assert app.model.docx_available is False
        assert button_states(app)["DOCX"] is True                       # greyed
        assert app.model.enabled("export_docx") is False
        description = next(
            b["description"] for s in all_sections(json.loads(SPEC.read_text())) for b in s.get("buttons", [])
            if b["label"] == "DOCX"
        )
        assert "python-docx" in description and "greyed" in description   # the tooltip says why
        app.model.export_docx()                                         # called anyway (a script): no crash
        assert "python-docx is not installed" in app.model.error_text
        assert not list(work.glob("*.docx")) and app.model.actions_done == 0
        assert app.model.write_docx() is None
    finally:
        app.close()


def test_docx_without_a_picture_backend_still_writes_the_report(work, with_docx, monkeypatch):
    app = make_app()
    try:
        open_folder(app, work)
        monkeypatch.setattr(app.model, "_render_trace_png", lambda path, png: None)
        saved = app.model.write_docx([work / "m000.spc"])
        ops = json.loads(saved.read_text())
        assert not [o for o in ops if o[0] == "picture"] and ["heading", 2, "m000.spc"] in ops
    finally:
        app.close()


# ---- Delete ---------------------------------------------------------------------------------------
def test_delete_asks_first_then_moves_the_files_and_their_companions_to_trash(work, monkeypatch):
    before = snapshot(work.parent)
    app = make_app()
    try:
        open_folder(app, work)
        app.model.set_notes(work / "m000.spc", "to be removed")
        select(app, "m000.spc")
        press(app, monkeypatch, "Delete", n=1)
        confirm = app.model.confirm
        assert confirm is not None and confirm["kind"] == "delete"
        assert sorted(pathlib.Path(p).name for p in confirm["paths"]) == ["m000.set", "m000.spc"]
        text = " | ".join(frames(app, n=2))
        assert "Move to .trash?" in text and "Move to .trash" in text and "Cancel" in text
        assert "m000.set" in confirm["message"] and "m000.spc" in confirm["message"]
        assert (work / "m000.spc").exists()                         # nothing moved before the answer
        assert button_states(app)["Export"] is True                   # the window is modal: others greyed
        with pressing(monkeypatch, "Move to .trash"):
            frames(app, n=1)
        settle_all(app)
        trash = work / ".trash"
        assert sorted(p.name for p in trash.iterdir()) == ["m000.set", "m000.spc"]
        assert (trash / "m000.spc").read_bytes() == before["data/m000.spc"]
        assert not (work / "m000.spc").exists() and not (work / "m000.set").exists()
        assert [r["name"] for r in app.model.rows] == ["m001.spc"]
        assert "m000.spc" not in " | ".join(frames(app, n=2))      # the table dropped it
        assert app.model.confirm is None and "Moved 2 file(s)" in app.model.status_text
        # untouched: the other measurements, the unlisted file, the file outside the folder
        for rel in ("data/m001.spc", "data/sub/m002.spc", "data/notes.txt", "outside/keep.spc"):
            assert (work.parent / rel).read_bytes() == before[rel], rel
        meta = json.loads((work / META).read_text())
        assert "m000.spc" not in meta                                 # its rating and note went with it
        # the selection moved to the row nearest the removed one
        assert app.model.current_file == work / "m001.spc"
    finally:
        app.close()


def test_a_declined_delete_confirmation_changes_nothing(work, monkeypatch):
    before = snapshot(work.parent)
    app = make_app()
    try:
        open_folder(app, work)
        select(app, "m000.spc", "m001.spc")
        press(app, monkeypatch, "Delete", n=1)
        assert app.model.confirm is not None
        with pressing(monkeypatch, "Cancel"):
            frames(app, n=1)
        settle_all(app)
        assert app.model.confirm is None and "no file was moved" in app.model.status_text
        assert not (work / ".trash").exists() or not list((work / ".trash").iterdir())
        after = snapshot(work.parent)
        assert {k: v for k, v in after.items() if not k.endswith(META)} == {
            k: v for k, v in before.items() if not k.endswith(META)
        }
        assert [r["name"] for r in app.model.rows] == ["m000.spc", "m001.spc"]
        assert app.model.actions_done == 0
    finally:
        app.close()


def test_the_delete_key_in_the_table_opens_the_confirmation(work):
    app = make_app()
    try:
        open_folder(app, work)
        select(app, "m001.spc")
        assert table(app).key(KEY_DELETE) is True
        assert app.model.confirm is not None and "m001.spc" in app.model.confirm["message"]
        assert (work / "m001.spc").exists()
    finally:
        app.close()


def test_delete_moves_a_whole_selection_keeps_subfolders_and_never_overwrites(work):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.include_subfolders = True
    model.image_probe = lambda path: False
    model.open_folder(work)
    (work / ".trash").mkdir()
    (work / ".trash" / "m001.spc").write_bytes(b"older copy")      # the name is taken in .trash
    targets = [work / "m001.spc", work / "sub" / "m002.spc"]
    assert model.delete_files([str(p) for p in targets]) == 2
    assert (work / ".trash" / "m001.spc").read_bytes() == b"older copy"
    stamped = [p.name for p in (work / ".trash").iterdir() if p.name.startswith("m001__")]
    assert len(stamped) == 1 and stamped[0].endswith(".spc")
    assert (work / ".trash" / "sub" / "m002.spc").exists()          # the sub-folder is kept
    assert [r["name"] for r in model.rows] == ["m000.spc"]


def test_delete_never_touches_a_file_outside_the_open_folder(work):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.image_probe = lambda path: False
    model.open_folder(work)
    outside = work.parent / "outside" / "keep.spc"
    original = outside.read_bytes()
    assert model.plan_delete([outside]) == []
    assert model.delete_files([str(outside)]) == 0
    assert outside.read_bytes() == original and not (work / ".trash" / "keep.spc").exists()
    model.set_selection([])
    model.delete_selected()
    assert model.confirm is None and "Select one or more files" in model.status_text


def test_the_files_inside_trash_are_never_listed_or_moved_again(work):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.image_probe = lambda path: False
    model.open_folder(work)
    model.delete_files([str(work / "m001.spc")])
    assert "m001.spc" not in [r["name"] for r in model.rows]
    model.scan()
    assert "m001.spc" not in [r["name"] for r in model.rows]
    assert model.plan_delete([work / ".trash" / "m001.spc"]) == []


# ---- hand-offs -------------------------------------------------------------------------------------
def test_each_hand_off_reaches_the_host_with_its_payload(work, monkeypatch):
    received = []
    app = make_app(on_request=lambda name, payload: received.append((name, payload)))
    try:
        app.model.ndx_available = lambda: True
        open_folder(app, work)
        select(app, "m001.spc")
        states = button_states(app)
        assert states["HMM"] is False and states["TW"] is False and states["NDX"] is False
        assert app.model.host_connected is True

        press(app, monkeypatch, "HMM")
        press(app, monkeypatch, "TW")
        assert [n for n, _ in received] == ["open_intensity_trace", "open_time_window"]
        hmm, tw = (p for _, p in received)
        assert hmm == {
            "file": str(work / "m001.spc"),
            "window_ms": 10.0,
            "setup_settings": json.loads(json.dumps(ALEX)),
            "selected_channels": [0, 1],
        }
        assert tw == {"files": [str(work / "m001.spc")], "window_ms": 10.0}
        assert [r["name"] for r in app.model.requests] == ["open_intensity_trace", "open_time_window"]
        assert app.model.requests[0]["payload"] == hmm

        press(app, monkeypatch, "NDX", n=1)
        settle_all(app)
        frames(app, n=3)
        name, payload = received[-1]
        assert name == "open_ndxplorer"
        folder = work / "m001_TW_10ms"
        assert payload == {"folder": str(folder), "file": str(work / "m001.spc"), "window_ms": 10.0}
        bur = folder / "bi4_bur" / "m001.bur"
        lines = bur.read_text().splitlines()
        assert lines[0].startswith("First Photon") and len(lines) > 6000
        assert (folder / "Info" / "m001.mti").exists()
        assert len(received) == 3 and len(app.model.requests) == 3
        frames(app, n=5)
        assert len(received) == 3                                  # each request is delivered once
        assert app.model.actions_done == 3
    finally:
        app.close()


def test_the_hand_offs_work_on_the_first_file_of_a_multi_selection(work, monkeypatch):
    received = []
    app = make_app(on_request=lambda name, payload: received.append((name, payload)))
    try:
        open_folder(app, work)
        press(app, monkeypatch, "Select all")
        press(app, monkeypatch, "TW")
        assert received == [("open_time_window", {"files": [str(work / "m000.spc")], "window_ms": 10.0})]
    finally:
        app.close()


def test_without_a_host_the_hand_off_buttons_are_greyed_and_record_nothing(work, monkeypatch):
    from chisurf.plugins.tttr.trace_browser.gui import app as app_module

    # a session that already runs a QApplication would host the app (card T5): this test is about no host
    monkeypatch.setattr(app_module, "default_request_handler", lambda: None)
    app = app_module.make_app()
    try:
        assert app.on_request is None and app.model.host_connected is False
        app.model.accept_setup(json.loads(json.dumps(ALEX)))
        open_folder(app, work)
        states = button_states(app)
        assert states["HMM"] is True and states["TW"] is True and states["NDX"] is True
        for action in ("open_intensity_trace", "open_time_window", "open_ndxplorer"):
            assert app.model.enabled(action) is False
        spec = json.loads(SPEC.read_text())
        for section in all_sections(spec):
            for button in section.get("buttons", []):
                if button["label"] in ("HMM", "TW", "NDX"):
                    assert "needs the chisurf main window" in button["description"].lower()
        assert app.model.requests == []
    finally:
        app.close()


def test_a_host_that_raises_is_reported_and_the_app_keeps_drawing(work):
    def broken(name, payload):
        raise RuntimeError("no such window")

    app = make_app(on_request=broken)
    try:
        open_folder(app, work)
        app.model.set_selection([str(work / "m000.spc")])
        app.model.open_time_window()
        frames(app, n=3)
        assert "could not open open_time_window: no such window" in app.model.error_text
    finally:
        app.close()


def test_ndx_needs_the_ndx_components_and_a_readable_file(work, tmp_path):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.host_connected = True
    model.image_probe = lambda path: False
    model.open_folder(work)
    model.set_selection([str(work / "m000.spc")])
    model.ndx_available = lambda: False
    assert model.enabled("open_ndxplorer") is False
    assert model.prepare_ndx(work / "m000.spc") is None and "ndX components" in model.error_text
    model.ndx_available = lambda: True
    bad = work / "broken.spc"
    bad.write_bytes(b"not a photon stream")
    assert model.prepare_ndx(bad) is None and "One-click workflow failed" in model.error_text
    assert model.requests == []


# ---- Help and Guide ----------------------------------------------------------------------------------
def test_the_help_window_opens_from_the_button_and_shows_the_help_text(work, monkeypatch):
    app = make_app()
    try:
        open_folder(app, work)
        assert "The Trace Browser pages through" not in " | ".join(frames(app, n=1))
        press(app, monkeypatch, "Help", n=2)
        text = " | ".join(frames(app, n=2))
        assert "Trace Browser" in text and "Selecting files" in text
        assert (GUI / "help.md").read_text().startswith("# Trace Browser")
        app.help_window.hide()
        assert "Selecting files" not in " | ".join(frames(app, n=2))
    finally:
        app.close()


def _guide_steps():
    return json.loads((GUI / "guide.json").read_text())["steps"]


def test_every_guide_target_resolves_to_a_rectangle(work):
    """Each step's target is a rectangle in one of the two pages (setup, browser with data)."""
    app = make_app()
    try:
        app.model.back_to_setup()
        frames(app, n=3)
        setup_rects = {k: v for k, v in app.item_rects.items()}
        app.continue_to_browser()
        open_folder(app, work)
        select(app, "m000.spc", "m001.spc")
        frames(app, n=3)
        resolve = app.tour.get_target_rect
        steps = _guide_steps()
        assert len(steps) >= 12
        for step in steps:
            target = step.get("target") or {}
            if not target:
                continue
            key = app.tour._target_key(target)
            rect = resolve(key)
            if rect is None and key == "setup_accepted":              # the setup page's Continue button
                rect = setup_rects.get("continue")
            assert rect is not None and len(rect) == 4 and rect[2] > 0 and rect[3] > 0, (step["title"], key)
        # the spec-checked targets are attributes and actions of the spec
        spec = json.loads(SPEC.read_text())
        attrs = {s.get("attr") for s in all_sections(spec)}
        actions = {b["action"] for s in all_sections(spec) for b in s.get("buttons", [])}
        for step in steps:
            target = step.get("target") or {}
            assert target.get("attr", next(iter(attrs))) in attrs
            assert target.get("action", next(iter(actions))) in actions
    finally:
        app.close()


def test_the_awaiting_steps_are_released_by_their_outcome(work, tmp_path, monkeypatch):
    steps = _guide_steps()
    awaiting = [i for i, s in enumerate(steps) if s.get("await")]
    names = {i: steps[i]["target"]["name"] for i in awaiting}
    assert set(names.values()) == {"setup_accepted", "folder_opened", "several_selected", "exported"}
    app = make_app()
    try:
        # setup_accepted: pressing Continue on the setup page releases it
        app.model.back_to_setup()
        frames(app, n=3)
        app.tour.start(awaiting[0])
        frames(app, n=2)
        assert app.tour.awaiting
        with pressing(monkeypatch, "Continue"):
            frames(app, n=1)
        frames(app, n=2)
        assert app.model.page == "browser" and not app.tour.awaiting
        # folder_opened: waits until files are listed
        app.tour.start(awaiting[1])
        frames(app, n=2)
        assert app.tour.awaiting
        open_folder(app, work)
        frames(app, n=2)
        assert not app.tour.awaiting
        # several_selected: waits for more than one selected file
        app.tour.start(awaiting[2])
        frames(app, n=2)
        assert app.tour.awaiting
        press(app, monkeypatch, "Select all")
        assert not app.tour.awaiting
        # exported: waits until an export finished
        app.tour.start(awaiting[3])
        frames(app, n=2)
        assert app.tour.awaiting
        app.model.export_files(tmp_path / "out")
        frames(app, n=2)
        assert not app.tour.awaiting
        # nothing was exported by the tour itself: the copies are the ones this test asked for
        assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["m000.spc", "m001.spc"]
    finally:
        app.close()


def test_the_guide_and_help_buttons_start_the_tour_and_the_help(work, monkeypatch):
    app = make_app()
    try:
        open_folder(app, work)
        assert not app.tour.active
        press(app, monkeypatch, "Guide", n=2)
        assert app.tour.active and app.tour.step_idx == 0
        text = " | ".join(frames(app, n=2))
        assert "Step 1 of" in text and "What this does" in text and "Close Tour" in text
        app.tour.stop()
        app.model.back_to_setup()
        frames(app, n=3)
        assert "help" in app.item_rects and "guide" in app.item_rects      # both pages have the buttons
    finally:
        app.close()


# ---- the whole window ----------------------------------------------------------------------------------
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_the_app_draws_populated_with_a_selection_and_a_confirmation(work, size):
    app = make_app()
    try:
        open_folder(app, work, subfolders=True)
        app.model.select_all_files()
        strings = frames(app, size, 3)
        joined = " | ".join(strings)
        for label in BUTTONS:
            assert label in joined, label
        app.model.delete_selected()
        joined = " | ".join(frames(app, size, 3))
        assert "Move to .trash?" in joined and "Cancel" in joined
        app.model.confirm_no()
        frames(app, size, 2)
    finally:
        app.close()


def test_every_control_has_a_tooltip_with_the_new_controls(work, tmp_path):
    from test.gui.emtk_port_parity import emtk_inventory

    app = make_app(on_request=lambda name, payload: None)
    try:
        open_folder(app, work, subfolders=True)
        app.model.select_all_files()
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == []
        labels = {row["label"] for row in inv["interactive"]}
        assert set(BUTTONS) | {"Help", "Guide"} <= labels
        app.model.delete_selected()                                   # the confirmation window's buttons
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == []
        assert {"Move to .trash", "Cancel"} <= {row["label"] for row in inv["interactive"]}
        app.model.confirm_no()
        app.model.back_to_setup()
        inv = emtk_inventory(app)                                      # Help and Guide on the setup page too
        assert inv["controls_without_tooltip"] == [] and {"Help", "Guide"} <= {r["label"] for r in inv["interactive"]}
    finally:
        app.close()
    for section in all_sections(json.loads(SPEC.read_text())):
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_settings_round_trip_has_no_selection_or_request_state(work):
    app = make_app()
    try:
        open_folder(app, work)
        app.model.select_all_files()
        app.model.hand_off("open_time_window", {"files": [], "window_ms": 1.0})
        saved = json.loads(json.dumps(app.export_settings()))          # JSON-safe
        assert saved["folder"] == str(work)
        assert not {"requests", "multi_selection", "confirm", "selected_files"} & set(saved)
    finally:
        app.close()
    other = make_app()
    try:
        other.restore_settings(saved)
        settle_all(other)
        assert other.model.current_folder == work and other.model.requests == []
        assert [p.name for p in other.model.selection_paths()] == ["m000.spc"]   # the first row, as after a scan
    finally:
        other.close()


# ---- manifest, Qt-free ----------------------------------------------------------------------------------
def test_the_manifest_declares_the_emtk_entry_and_keeps_the_qt_one():
    manifest = json.loads((GUI.parent / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == ENTRY
    assert manifest["entrypoints"]["gui"] == "chisurf.plugins.tttr.trace_browser.gui.tool:TraceBrowserTool"
    module, attribute = manifest["entrypoints"]["emtk"].split(":")
    import importlib

    assert callable(getattr(importlib.import_module(module), attribute))


def test_port_is_qt_free_by_the_entry_and_by_the_manifest():
    from test.gui.emtk_port_parity import qt_free

    first = qt_free("trace_browser", ENTRY)
    assert first["ok"], first["output"]
    second = qt_free("trace_browser")                                  # the manifest's entrypoints.emtk
    assert second["ok"], second["output"]


def test_no_qt_is_imported_by_the_app_or_the_model_sources():
    for name in ("app.py", "model.py"):
        source = (GUI / name).read_text()
        for needle in ("qtpy", "PyQt", "PySide", "chisurf.gui"):
            assert needle not in source, (name, needle)


def test_the_model_methods_run_headless_without_a_host(work, tmp_path):
    """Export, CSV and Delete are model methods: they need neither the app nor Qt."""
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.accept_setup(json.loads(json.dumps(ALEX)))
    model.open_folder(work)
    model.set_selection([str(work / "m000.spc")])
    assert model.export_selected() is None and model.dialog == "export"
    assert model.export_files(tmp_path / "e") == 1
    assert [pathlib.Path(p).name for p in model.export_csv_files(tmp_path / "c")] == ["m000_trace.csv"]
    model.delete_selected()
    assert model.confirm is not None
    model.confirm_yes()
    assert not (work / "m000.spc").exists() and (work / ".trash" / "m000.spc").exists()
