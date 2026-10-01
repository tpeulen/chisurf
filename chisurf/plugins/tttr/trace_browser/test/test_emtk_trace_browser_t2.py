"""The native Trace Browser, card T2: the Browser page (folder, file table, filter, selection).

Everything runs on temporary COPIES of repository sample data: the browser writes the metadata
``.trace_browser_meta.json`` and a trace cache beside the data files, so repo data is never opened
in place. The hermetic autouse fixture in ``conftest.py`` redirects the settings folder, the MMFDB
and the setups file. The trace plot and annotation are card T3b (test_emtk_trace_browser_t3b.py).
"""

import contextlib
import json
import pathlib
import shutil
import time

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.tttr.trace_browser.test.conftest import ALEX

HERE = pathlib.Path(__file__).parent
GUI = HERE.parent / "gui"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
BH132 = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
BH630 = REPO / "test" / "data" / "tttr" / "BH" / "630_256" / "BH_SPC630_256.spc"
ENTRY = "chisurf.plugins.tttr.trace_browser.gui.app:make_app"
SPEC = GUI / "trace_browser_emtk.view.json"
META = ".trace_browser_meta.json"


# ---- helpers ---------------------------------------------------------------------------------
@pytest.fixture
def data_dir(tmp_path):
    """A temp folder with the real ``.spc`` sample copied three times: m000, m001 and sub/m002."""
    if not BH132.exists() or not BH630.exists():
        pytest.skip("sample TTTR data missing")
    folder = tmp_path / "data"
    (folder / "sub").mkdir(parents=True)
    shutil.copy(BH132, folder / "m000.spc")
    shutil.copy(BH132, folder / "m001.spc")
    shutil.copy(BH630, folder / "sub" / "m002.spc")
    return folder


@pytest.fixture
def fake_dir(tmp_path):
    """A temp folder of unreadable stand-in files (listed as non-image) plus metadata."""
    folder = tmp_path / "fake"
    for rel in ["a.ptu", "b.PTU", "c.spc", "d.txt", "sub/e.ht3", "sub/.trash/f.ptu", ".trash/g.ptu"]:
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"not a real tttr file")
    (folder / META).write_text(
        json.dumps(
            {
                "a.ptu": {"rating": 3, "annotation": "hello"},
                "sub/e.ht3": {"rating": 1},
                "c.spc": {"rating": 0},
                "b.PTU": {"rating": 2},
            }
        )
    )
    return folder


def make_app(setups_file=None):
    """The app, on its Browser page with an empty setup (channels are auto-detected)."""
    from chisurf.plugins.tttr.trace_browser.gui.app import TraceBrowserApp

    app = TraceBrowserApp(setups_file=setups_file)
    app.continue_to_browser()
    app.model.precompute_after_scan = False         # the T2 tests are about the page, not the precompute
    return app


def frames(app, size=(1200, 800), n=3):
    """Draw *n* frames; return the strings of the last one."""
    painter = RecordingPainter()
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter.strings


def settle(app, size=(1200, 800), timeout=30.0):
    """Draw frames until the app's worker and its queue are idle; return the last frame's strings."""
    deadline = time.time() + timeout
    strings = frames(app, size, 1)
    while (app.job.busy or app._queue or app.load_job.busy or app.pre_job.busy) and time.time() < deadline:
        time.sleep(0.02)
        strings = frames(app, size, 1)
    assert not app.job.busy and not app._queue, "the worker did not finish"
    return frames(app, size, 2) or strings


def table(app):
    """The file table's control (it is bound on the first frame that draws the form)."""
    return app.form.tables["rows"].control


def edit_cell(app, row_name, key, text):
    """Type *text* into a cell of the file table the way the table does (open, type, Enter)."""
    control = table(app)
    index = next(i for i in range(control.row_count()) if control.value(i, "name") == row_name)
    control.begin_edit(index, key)
    control.editor.set_text(text)
    control.commit_edit()


@contextlib.contextmanager
def pressing(monkeypatch, label):
    """Make the next button *label* report a click (the real button path of a spec or a dialog)."""
    from emtk import im, im_widgets

    fired = []

    def wrap(real):
        def button(text, *args, **kwargs):
            result = real(text, *args, **kwargs)
            if str(text).split("##")[0] == label and not fired:
                fired.append(text)
                return True
            return result

        return button

    originals = (im.button, im_widgets.button)
    monkeypatch.setattr(im, "button", wrap(originals[0]))
    monkeypatch.setattr(im_widgets, "button", wrap(originals[1]))
    yield fired
    monkeypatch.setattr(im, "button", originals[0])
    monkeypatch.setattr(im_widgets, "button", originals[1])
    assert fired, f"no button {label!r} was drawn"


def commit(app, attr, value):
    """Write *value* into the spec section of *attr* exactly as the drawn control does."""
    from emtk.view_form import _commit

    section = next(s for s in all_sections(json.loads(SPEC.read_text())) if s.get("attr") == attr)
    _commit(app.model, section, value, app.form)


def all_sections(spec):
    """Every section dict of a spec, depth first."""
    out = []

    def walk(sections):
        for section in sections:
            out.append(section)
            walk(section.get("sections", []))

    walk(spec.get("sections", []))
    return out


def names(rows):
    return sorted((r["name"], r["rating"]) for r in rows)


# 1. the spec and the model agree
def test_every_spec_key_exists_on_the_model():
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    spec = json.loads(SPEC.read_text())
    seen = {"attr": 0, "call": 0, "action": 0, "table": 0}
    for section in all_sections(spec):
        for key in ("attr", "source"):
            if section.get(key):
                assert hasattr(model, section[key]), section[key]
                seen["attr"] += 1
        for key in ("call", "options_source"):
            if section.get(key):
                assert callable(getattr(model, section[key])), section[key]
                seen["call"] += 1
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
            seen["action"] += 1
        if section.get("key") == "data_table":
            options = section["options"]
            assert isinstance(getattr(model, options["source"]), list)
            for call in ("selected_call", "edited_call"):
                assert callable(getattr(model, options[call])), options[call]
            seen["table"] += 1
    assert seen == {"attr": 8, "call": 3, "action": 6, "table": 1}, seen   # T3b: Precompute, Stop, the toggle
    assert callable(model.enabled) and model.enabled("clear") is True
    model.busy = True
    assert model.enabled("clear") is False


# 2. the Browser page draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_browser_page_draws_empty_and_populated(size, data_dir):
    app = make_app()
    try:
        text = " | ".join(frames(app, size))
        assert app.model.page == "browser"
        for label in ("Select setup", "Open", "Clear caches", "Include subfolders", "Bin window [ms]",
                      "Y min", "Y max", "No folder selected", "Select a file to write an annotation"):
            assert label in text, label
        for header in ("File", "Rating", "Size (MB)", "Notes"):
            assert header in text, header
        assert "m000.spc" not in text and not app.model.rows       # an empty state, nothing invented
        app.model.request("open_folder", data_dir)
        text = " | ".join(settle(app, size))
        assert "m000.spc" in text and "m001.spc" in text
        assert "1.144" in text                                     # the real size in MB
        assert "sub/m002.spc" not in text                          # subfolders are off
        assert str(data_dir) in text or data_dir.name in text
    finally:
        app.close()


# 3. open a folder through the model and through the app (real .spc, the real image probe)
def test_open_folder_lists_the_real_spc_files(data_dir):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    assert model.image_probe is None                               # the default probe, not a stand-in
    assert model.open_folder(data_dir)
    assert [r["name"] for r in model.rows] == ["m000.spc", "m001.spc"]
    assert model.rows[0]["size"] == BH132.stat().st_size
    assert model.folder_text == str(data_dir) and model.status_text.startswith("2 of 2")
    assert model.open_folder(data_dir / "m000.spc") is False       # a file is not a folder
    assert "Not a folder" in model.error_text and model.status_line == model.error_text


def test_the_open_button_opens_a_folder_dialog_that_opens_the_folder(data_dir, monkeypatch):
    app = make_app()
    try:
        frames(app)
        assert app.dialog is None
        with pressing(monkeypatch, "Open"):
            frames(app, n=1)
        frames(app, n=1)
        assert app.dialog is not None and app.dialog.mode == "folder"
        assert app.dialog.title == "Select folder with PTU/TTTR files"
        shown = " | ".join(frames(app, n=1))
        assert "Choose" in shown and "Cancel" in shown and "[..]" in shown   # the folder chooser
        app.dialog.directory = str(data_dir)
        app.dialog.selection = []
        with pressing(monkeypatch, "Choose"):
            frames(app, n=1)
        assert app.dialog is None
        text = " | ".join(settle(app))
        assert app.model.current_folder == data_dir and "m000.spc" in text
        # Cancel leaves the folder alone
        with pressing(monkeypatch, "Open"):
            frames(app, n=1)
        frames(app, n=2)
        assert app.dialog is not None
        with pressing(monkeypatch, "Cancel"):
            frames(app, n=1)
        assert app.dialog is None and app.model.current_folder == data_dir
    finally:
        app.close()


# 4. rating and notes: edited in the table, persisted through the metadata, shown after a rescan
def test_rating_and_notes_edits_persist_and_show_after_a_rescan(data_dir):
    app = make_app()
    try:
        app.model.request("open_folder", data_dir)
        settle(app)
        edit_cell(app, "m001.spc", "rating", "2")
        edit_cell(app, "m001.spc", "notes", "good burst, dim acceptor")
        edit_cell(app, "m000.spc", "rating", "1")
        saved = json.loads((data_dir / META).read_text())
        assert saved["m001.spc"] == {"rating": 2, "annotation": "good burst, dim acceptor"}
        assert saved["m000.spc"]["rating"] == 1
        assert app.model.get_rating(data_dir / "m001.spc") == 2
        assert names(app.model.rows) == [("m000.spc", 1), ("m001.spc", 2)]
        assert {r["name"]: r["notes"] for r in app.model.rows}["m001.spc"] == "good burst, dim acceptor"
        # a rescan of the same folder (the toggle) and a brand-new app read it back from the disk
        app.model.request("scan")
        text = " | ".join(settle(app))
        assert "good burst, dim acceptor" in text and names(app.model.rows) == [("m000.spc", 1), ("m001.spc", 2)]
    finally:
        app.close()
    other = make_app()
    try:
        other.model.request("open_folder", data_dir)
        text = " | ".join(settle(other))
        assert names(other.model.rows) == [("m000.spc", 1), ("m001.spc", 2)]
        assert "good burst, dim acceptor" in text
    finally:
        other.close()


def test_an_invalid_rating_is_refused_and_the_stored_value_stays(data_dir):
    app = make_app()
    try:
        app.model.request("open_folder", data_dir)
        settle(app)
        edit_cell(app, "m000.spc", "rating", "3")
        edit_cell(app, "m000.spc", "rating", "4")                  # above the maximum
        edit_cell(app, "m000.spc", "rating", "9")                  # above the maximum
        assert app.model.get_rating(data_dir / "m000.spc") == 3
        assert next(r for r in app.model.rows if r["name"] == "m000.spc")["rating"] == 3
        assert "whole number from 0 to 3" in app.model.error_text
        edit_cell(app, "m000.spc", "rating", "2.5")                # not a whole number
        assert app.model.get_rating(data_dir / "m000.spc") == 3
        edit_cell(app, "m000.spc", "rating", "abc")                # a typo: the table keeps the cell
        assert app.model.get_rating(data_dir / "m000.spc") == 3
        edit_cell(app, "m000.spc", "rating", "0")
        assert app.model.get_rating(data_dir / "m000.spc") == 0 and app.model.error_text == ""
        assert json.loads((data_dir / META).read_text())["m000.spc"]["rating"] == 0
    finally:
        app.close()


def test_edits_are_refused_while_a_scan_runs(fake_dir):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.open_folder(fake_dir)
    row = next(r for r in model.rows if r["name"] == "a.ptu")
    row["rating"] = 1                                              # what the table does first
    model.busy = True
    model.edit_cell(row, "rating", 1)
    assert row["rating"] == 3 and model.get_rating(row["path"]) == 3
    model.busy = False
    model.edit_cell(row, "rating", 1)
    assert model.get_rating(row["path"]) == 1


# 5. the rating filter
def test_rating_filter_through_the_spec_choice(fake_dir):
    from chisurf.plugins.tttr.trace_browser.gui.model import FILTER_LABELS

    app = make_app()
    try:
        app.model.request("open_folder", fake_dir)
        settle(app)
        assert names(app.model.rows) == [("a.ptu", 3), ("b.PTU", 2), ("c.spc", 0)]
        expected = {
            "All": [("a.ptu", 3), ("b.PTU", 2), ("c.spc", 0)],
            FILTER_LABELS[1]: [("a.ptu", 3), ("b.PTU", 2)],
            FILTER_LABELS[2]: [("a.ptu", 3), ("b.PTU", 2)],
            FILTER_LABELS[3]: [("a.ptu", 3)],
            FILTER_LABELS[4]: [("c.spc", 0)],
        }
        for label, rows in expected.items():
            commit(app, "rating_filter", label)                    # setattr, then set_rating_filter
            text = " | ".join(frames(app))
            assert names(app.model.rows) == rows, label
            assert all(name in text for name, _ in rows)
            assert all(name not in text for name in {"a.ptu", "b.PTU", "c.spc"} - {n for n, _ in rows}), label
            assert label in text                                    # the drop-down shows the filter
        # the filter acts on the ratings as they are edited
        commit(app, "rating_filter", FILTER_LABELS[4])
        frames(app)
        edit_cell(app, "c.spc", "rating", "2")
        assert [r["name"] for r in app.model.rows] == []
        commit(app, "rating_filter", "All")
        assert names(app.model.rows) == [("a.ptu", 3), ("b.PTU", 2), ("c.spc", 2)]
    finally:
        app.close()


# 6. include subfolders: the toggle really rescans (the Qt toolbar checkbox did nothing)
def test_include_subfolders_really_rescans(data_dir):
    app = make_app()
    try:
        commit(app, "include_subfolders", True)                    # no folder yet: nothing to scan, no error
        assert app.model.include_subfolders is True and app.model.error_text == ""
        commit(app, "include_subfolders", False)
        app.model.request("open_folder", data_dir)
        settle(app)
        assert [r["name"] for r in app.model.rows] == ["m000.spc", "m001.spc"]
        commit(app, "include_subfolders", True)
        text = " | ".join(settle(app))
        assert [r["name"] for r in app.model.rows] == ["m000.spc", "m001.spc", "sub/m002.spc"]
        assert "sub/m002.spc" in text
        commit(app, "include_subfolders", False)
        settle(app)
        assert [r["name"] for r in app.model.rows] == ["m000.spc", "m001.spc"]
    finally:
        app.close()


# 7. selection sets the model's selection and current file (the trace it loads is card T3b's)
def test_selecting_a_row_sets_selection_and_current_file(data_dir):
    app = make_app()
    try:
        app.model.request("open_folder", data_dir)
        settle(app)
        control = table(app)
        model = app.model
        assert model.current_file == data_dir / "m000.spc"           # card T3b: a scan selects the first row
        control._select_position(1)                                # the table reports it: selected_call
        assert model.selected_files == [str(data_dir / "m001.spc")]
        assert model.current_file == data_dir / "m001.spc" and model.trace is None   # no trace until loaded
        text = " | ".join(frames(app))
        assert "m001.spc" in text
        control._select_position(0)
        assert model.selected_files == [str(data_dir / "m000.spc")]
        # a bin-window or y-range edit only stores the value
        commit(app, "window_ms", 1.0)
        commit(app, "y_max", 2500.0)
        assert model.window_ms == 1.0 and model.y_max == 2500.0 and model.y_range == (0.0, 2500.0)
        # selecting a row that a rescan removed does not leave a stale selection
        model.clear()
        assert model.selected_files == [] and model.current_file is None
    finally:
        app.close()


# 8. Clear and Clear caches
def test_clear_and_clear_caches_buttons(data_dir, monkeypatch):
    app = make_app()
    try:
        app.model.request("open_folder", data_dir)
        settle(app)
        cache = data_dir / ".tttr_trace_cache"
        cache.mkdir(exist_ok=True)      # selecting the first row has loaded its trace (card T3b)
        (cache / "x.npz").write_bytes(b"cached")
        edit_cell(app, "m000.spc", "rating", "2")
        table(app)._select_position(0)
        with pressing(monkeypatch, "Clear caches"):
            frames(app, n=1)
        assert not cache.exists() and "caches cleared" in app.model.status_text
        assert app.model.rows                                        # the list is untouched
        with pressing(monkeypatch, "Clear"):
            frames(app, n=1)
        text = " | ".join(frames(app))
        assert app.model.rows == [] and app.model.selected_files == [] and app.model.current_file is None
        assert "m000.spc" not in text
        # files and metadata are untouched: scanning again lists the rating
        assert (data_dir / "m000.spc").exists()
        app.model.request("scan")
        settle(app)
        assert names(app.model.rows) == [("m000.spc", 2), ("m001.spc", 0)]
    finally:
        app.close()


# 9. drops
def test_drop_of_a_folder_opens_it_and_a_file_is_ignored(data_dir, fake_dir):
    app = make_app()
    try:
        frames(app)
        assert app.files_dropped([str(data_dir / "m000.spc")]) is False        # a file: ignored, as in Qt
        assert app.model.current_folder is None and "Drop a folder" in app.model.status_text
        assert app.files_dropped([str(data_dir / "nothing_here")]) is False
        assert app.files_dropped([]) is False
        assert app.files_dropped([str(data_dir / "m000.spc"), str(data_dir)]) is True   # first folder wins
        text = " | ".join(settle(app))
        assert app.model.current_folder == data_dir and "m001.spc" in text
        app.on_paths_dropped([str(fake_dir)])
        settle(app)
        assert app.model.current_folder == fake_dir
        assert names(app.model.rows) == [("a.ptu", 3), ("b.PTU", 2), ("c.spc", 0)]
    finally:
        app.close()


# 10. Select setup and Continue keep the folder, the list and the selection
def test_back_and_setup_round_trip_keeps_the_folder(data_dir, monkeypatch):
    app = make_app()
    try:
        app.model.request("open_folder", data_dir)
        settle(app)
        edit_cell(app, "m000.spc", "notes", "kept")
        table(app)._select_position(0)
        rows = list(app.model.rows)
        with pressing(monkeypatch, "← Select setup"):
            frames(app, n=1)
        text = " | ".join(frames(app))
        assert app.model.page == "setup" and "Continue" in text
        assert app.model.current_folder == data_dir and app.model.rows == rows
        with pressing(monkeypatch, "Continue"):
            frames(app, n=1)
        text = " | ".join(settle(app))
        assert app.model.page == "browser" and app.model.current_folder == data_dir
        assert "m000.spc" in text and "kept" in text
        assert app.model.selected_files == [str(data_dir / "m000.spc")]
        assert not app._queue                                       # an unchanged setup: no rescan
    finally:
        app.close()


def test_a_changed_setup_rescans_the_open_folder(data_dir, tmp_path):
    from chisurf.plugins.tttr.trace_browser.test.conftest import OVERLAP

    ptu_only = dict(ALEX, setup_name="PTU only", tttr_reading={"file_type": "PTU", "micro_time_binning": 1})
    setups = tmp_path / "setups.json"
    setups.write_text(json.dumps({"setups": {"PTU only": ptu_only, "Overlap": OVERLAP},
                                  "last_used": "PTU only"}))
    app = make_app(setups)
    try:
        assert app.model.setup_filetype == "PTU"                    # the saved setup was accepted
        app.model.request("open_folder", data_dir)
        settle(app)
        assert app.model.rows == []                                  # a PTU setup: no .spc file is listed
        app.back_to_setup()
        app.editor.select_setup("Overlap")                           # file type Auto: every extension
        app.continue_to_browser()
        assert app._queue                                            # the folder is scanned again
        settle(app)
        assert [r["name"] for r in app.model.rows] == ["m000.spc", "m001.spc"]
    finally:
        app.close()


# 11. the start page: the Qt constructor continues with the setup it has
def test_the_app_opens_on_the_browser_page_when_a_setup_is_available(tmp_path):
    from chisurf.plugins.tttr.trace_browser.gui.app import TraceBrowserApp

    nothing = TraceBrowserApp(setups_file=tmp_path / "none.json")
    try:
        assert nothing.model.page == "setup" and nothing.model.setup_settings is None
        assert "Continue" in " | ".join(frames(nothing))
    finally:
        nothing.close()
    setups = tmp_path / "setups.json"
    setups.write_text(json.dumps({"setups": {"ALEX Suite (auto)": ALEX}, "last_used": "ALEX Suite (auto)"}))
    app = TraceBrowserApp(setups_file=setups)
    try:
        assert app.model.page == "browser"                           # _on_continue() at start-up
        assert app.model.selected_channels == [0, 1] and app.model.setup_filetype == "PTO"
        assert "Select a file to write an annotation" in " | ".join(frames(app))
    finally:
        app.close()


# 12. persistence
def test_settings_round_trip(data_dir, tmp_path):
    from chisurf.plugins.tttr.trace_browser.gui.model import FILTER_LABELS

    app = make_app()
    try:
        app.model.request("open_folder", data_dir)
        settle(app)
        commit(app, "include_subfolders", True)
        settle(app)
        commit(app, "rating_filter", FILTER_LABELS[2])
        commit(app, "window_ms", 2.5)
        commit(app, "y_min", 5.0)
        commit(app, "y_max", 750.0)
        saved = json.loads(json.dumps(app.export_settings()))        # it must survive JSON
    finally:
        app.close()
    assert saved["folder"] == str(data_dir) and saved["include_subfolders"] is True
    assert saved["rating_filter"] == FILTER_LABELS[2] and saved["window_ms"] == 2.5
    assert (saved["y_min"], saved["y_max"]) == (5.0, 750.0)

    other = make_app()
    try:
        other.restore_settings(saved)
        assert other.model.page == "browser"                         # a remembered setup: the Browser page
        settle(other)
        model = other.model
        assert model.current_folder == data_dir and model.include_subfolders is True
        assert model.rating_filter == FILTER_LABELS[2] and model.window_ms == 2.5
        assert (model.y_min, model.y_max) == (5.0, 750.0)
        assert model.files and model.rows == []                       # >= 2 stars: nothing rated yet
        assert [r["name"] for r in model.files] == ["m000.spc", "m001.spc", "sub/m002.spc"]
        assert other.export_settings()["folder"] == str(data_dir)
        # a folder that has gone, and entries that are not valid, are ignored without an error
        saved["folder"] = str(tmp_path / "gone")
        saved["rating_filter"] = "no such filter"
        saved["window_ms"] = "not a number"
        other.restore_settings(saved)
        settle(other)
        assert other.model.error_text == ""
        assert other.model.rating_filter == FILTER_LABELS[2] and other.model.window_ms == 2.5
        other.restore_settings({})                                    # nothing remembered: no error
        assert other.model.page == "setup"
    finally:
        other.close()


# 13. every control has a tooltip; the spec describes every section and column
def test_every_control_has_a_tooltip(data_dir):
    from test.gui.emtk_port_parity import emtk_inventory

    app = make_app()
    try:
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == []
        labels = {row["label"] for row in inv["interactive"]}
        assert {"← Select setup", "Open", "Clear", "Clear caches", "Include subfolders"} <= labels
        app.model.request("open_folder", data_dir)
        settle(app)
        inv = emtk_inventory(app)
        assert inv["controls_without_tooltip"] == []
        assert inv["interactive"], "the drawn controls were not recorded"
    finally:
        app.close()
    spec = json.loads(SPEC.read_text())
    count = 0
    for section in all_sections(spec):
        assert section.get("description"), section.get("attr") or section.get("title") or section
        for button in section.get("buttons", []):
            assert button.get("description"), button
        for column in (section.get("options") or {}).get("columns", []):
            assert column.get("description"), column
            count += 1
        count += 1
    assert count == 16, count     # 1 form + 10 sections, 1 table + 4 columns (T3b: a button row, a toggle)


# 14. no Qt, no chisurf.gui
def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("trace_browser", ENTRY)
    assert result["ok"], result["output"]


# 15. the Qt widget and the emtk app list the same rows for the same folder
@pytest.mark.parametrize("recursive", [False, True])
@pytest.mark.parametrize("idx", range(5))
def test_qt_widget_and_emtk_app_agree_on_the_rows(qapp, qtbot, fake_dir, recursive, idx, monkeypatch):
    pytest.importorskip("pyqtgraph")
    from chisurf.plugins.tttr.trace_browser import TraceBrowser
    from chisurf.plugins.tttr.trace_browser.gui.model import FILTER_LABELS
    from chisurf.plugins.tttr.trace_browser.test.conftest import OVERLAP

    widget = TraceBrowser()
    qtbot.addWidget(widget)
    # the Qt page starts on its built-in SPC-130 detectors; take a file type of Auto, as the app has
    widget.detector_page._load_data(json.loads(json.dumps(OVERLAP)))
    widget._on_continue()
    # the trace of the selected row is card T3's business: do not compute it in this comparison
    monkeypatch.setattr(widget, "_plot_file", lambda *a, **k: None)
    monkeypatch.setattr(widget, "_precompute_all_traces", lambda *a, **k: None)
    widget.chk_subfolders.setChecked(recursive)
    widget.filter_combo.setCurrentIndex(idx)
    widget._open_folder(fake_dir)
    visible = [
        (widget.table.item(r, 0).text(), widget.table.cellWidget(r, 1).rating())
        for r in range(widget.table.rowCount())
        if not widget.table.isRowHidden(r)
    ]
    app = make_app()
    try:
        commit(app, "include_subfolders", recursive)
        commit(app, "rating_filter", FILTER_LABELS[idx])
        app.model.request("open_folder", fake_dir)
        settle(app)
        assert names(app.model.rows) == sorted(visible)
    finally:
        app.close()


def test_the_scan_is_the_models_not_api_list_files(fake_dir):
    """``api.io.list_files`` is a different listing (fixed extensions, lists in .trash); not used."""
    source = (GUI / "app.py").read_text() + (GUI / "model.py").read_text()
    assert "list_files" not in source


def test_a_rescan_does_not_keep_stale_hidden_rows(fake_dir):
    """The Qt widget hid rows by row index across scans; the model has no such state."""
    from chisurf.plugins.tttr.trace_browser.gui.model import FILTER_LABELS, TraceBrowserModel

    model = TraceBrowserModel()
    model.include_subfolders = True
    model.open_folder(fake_dir)
    model.set_rating_filter(FILTER_LABELS[3])
    assert [r["name"] for r in model.rows] == ["a.ptu"]
    model.set_rating_filter(FILTER_LABELS[0])
    model.include_subfolders = False
    model.scan()
    assert [r["name"] for r in model.rows] == ["a.ptu", "b.PTU", "c.spc"]
