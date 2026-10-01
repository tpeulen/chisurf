"""The native Photon Table against the Qt tool: rows, summary, actions, errors, drawing, no Qt.

Hermetic: the settings folder is a temporary one, the data is a private copy of
``test/data/tttr/BH/132/BH_SPC132.spc`` (183,657 photons on routing channels 0, 1, 8 and 9).
The reference numbers are read straight from tttrlib for the same file, and the Qt tool
(constructed offscreen) is the second source: its drawn cells and its status messages.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.tttr.photon_table.gui.app import PhotonTableApp, make_app
from chisurf.plugins.tttr.photon_table.gui.model import PhotonTableViewModel

HERE = Path(__file__).parent
GUI = HERE.parent / "gui"
SPEC_FILE = GUI / "photon_table_emtk.view.json"
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
SAMPLE = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"
TABLE = "rows"

needs_sample = pytest.mark.skipif(not SAMPLE.exists(), reason="test data not available")


# ── helpers ─────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    """Settings in a temporary folder: nothing reads or writes ``~/.chisurf``."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))


@pytest.fixture
def sample(tmp_path):
    """A private copy of the BH sample (with its companion files)."""
    for src in SAMPLE.parent.glob("BH_SPC132*"):
        shutil.copy(src, tmp_path / src.name)
    return tmp_path / "BH_SPC132.spc"


@pytest.fixture(scope="module")
def reference():
    """The photons of the sample as tttrlib reads them: the independent source of truth."""
    import tttrlib

    t = tttrlib.TTTR(str(SAMPLE))
    return {
        "micro": np.asarray(t.micro_times),
        "macro": np.asarray(t.macro_times),
        "routing": np.asarray(t.routing_channels),
        "res": float(t.header.macro_time_resolution),
    }


def draw(app, size=(1200, 800), frames=3):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def pump(app, seconds=30.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        draw(app, frames=1)
        if not app.job.busy:
            return
        time.sleep(0.01)
    raise AssertionError("the load did not finish")


def loaded(sample):
    app = make_app()
    assert app.load_file(str(sample))
    pump(app)
    assert app.model.loaded, app.model.notice
    return app


def table(app):
    return app.form.tables[TABLE].control


def press(app, action):
    """Press a spec button the way the form does: its model method, then a frame."""
    getattr(app.model, action)()
    draw(app, frames=1)


# ── 1. rows and summary equal tttrlib's and the Qt tool's ───────────────


@needs_sample
def test_rows_equal_tttrlib_for_the_same_file(sample, reference):
    app = loaded(sample)
    m = app.model
    assert m.table.n_photons == len(reference["micro"]) == 183_657
    for r in m.rows:
        i = r["idx"]
        assert r["photon"] == i  # no filter: Photon is the file index
        assert r["micro"] == int(reference["micro"][i])
        assert r["channel"] == int(reference["routing"][i])
        assert r["macro"] == pytest.approx(float(reference["macro"][i]) * reference["res"] * 1e3)
    assert len(m.rows) == 200
    assert m.table.used_channels == [0, 1, 8, 9]
    assert m.range_text == "photons 0–200"


@needs_sample
def test_filtered_rows_equal_tttrlib(sample, reference):
    app = loaded(sample)
    m = app.model
    m.set_channel(9)
    expected = np.flatnonzero(reference["routing"] == 9)
    assert m.count == len(expected) == 24_652
    assert [r["idx"] for r in m.rows] == [int(i) for i in expected[:200]]
    assert [r["photon"] for r in m.rows] == list(range(200))  # renumbered within the filter
    assert {r["channel"] for r in m.rows} == {9}
    m.set_first(1000)
    assert [r["idx"] for r in m.rows] == [int(i) for i in expected[1000:1200]]
    assert m.range_text == "photons 1,000–1,200"


@needs_sample
def test_summary_and_cells_equal_the_qt_tool(qapp, sample):
    """The Qt tool's drawn summary and first rows are the native app's."""
    from chisurf.plugins.tttr.photon_table.gui.tool import PhotonTableTool

    tool = PhotonTableTool()
    try:
        tool.load_file(str(sample))
        qt = RecordingPainter()
        tool.app.draw(qt, 0.0, 0.0, 1200.0, 800.0)
        qt_strings = set(qt.strings)
        app = loaded(sample)
        m = app.model
        assert str(sample) in qt_strings and m.file_name == str(sample)
        assert m.summary_text in qt_strings
        assert m.channels_text in qt_strings
        assert m.notice == tool.statusBar().currentMessage()
        # the first rows: the Qt table's cells (thousands separators) are the native values
        for r in m.rows[:25]:
            assert f"{r['photon']:,}" in qt_strings and f"{r['idx']:,}" in qt_strings
            assert f"{r['micro']}" in qt_strings and f"{r['macro']:.6f}" in qt_strings
        # the model behind both is the same rows
        assert [r["idx"] for r in m.rows] == [
            r["idx"] for r in tool._model.page(tool.first_index, tool.rows_per_page, tool.channel_filter)
        ]
    finally:
        tool.close()


@needs_sample
def test_the_native_table_binds_the_same_rows_and_columns(sample):
    app = loaded(sample)
    draw(app)
    control = table(app)
    assert control.row_count() == 200
    assert [c.title for c in control.visible_columns()] == [
        "Photon", "File idx", "Channel", "Micro time", "Macro time [ms]"
    ]


# ── 2. every action ─────────────────────────────────────────────────────


@needs_sample
def test_navigation_buttons_page_through_the_file(sample):
    app = loaded(sample)
    m = app.model
    press(app, "go_next")
    assert m.first_index == 200
    press(app, "go_next")
    assert m.first_index == 400
    press(app, "go_prev")
    assert m.first_index == 200
    press(app, "go_first")
    assert m.first_index == 0
    press(app, "go_prev")  # the first page has no page before it
    assert m.first_index == 0
    press(app, "go_last")
    assert m.first_index == 183_657 - 200
    press(app, "go_next")  # nor after the last
    assert m.first_index == 183_657 - 200
    assert m.rows[-1]["idx"] == 183_656


@needs_sample
def test_the_fields_clamp_like_the_qt_tool(sample):
    app = loaded(sample)
    m = app.model
    m.set_first(10**9)
    assert m.first_index == 183_657 - 200
    m.set_first(-5)
    assert m.first_index == 0
    m.set_first("not a number")
    assert m.first_index == 0
    m.set_rows(0)
    assert m.rows_per_page == 1 and len(m.rows) == 1
    m.set_rows(10**6)
    assert m.rows_per_page == 20_000 and len(m.rows) == 20_000
    m.set_first(183_000)  # a bigger page pulls the first row back so it stays full
    assert m.first_index == 183_657 - 20_000
    m.set_rows(50)
    assert m.rows_per_page == 50


@needs_sample
def test_the_channel_filter_resets_the_page_and_ignores_an_unknown_channel(sample):
    app = loaded(sample)
    m = app.model
    m.set_first(5000)
    m.set_channel(1)
    assert m.channel_filter == 1 and m.first_index == 0
    assert {r["channel"] for r in m.rows} == {1}
    assert [v for v, _ in m.channel_labels()] == [-1, 0, 1, 8, 9]
    assert m.channel_labels()[0][1] == "All channels"
    m.set_channel(7)  # not in the file
    assert m.channel_filter == -1
    assert m.count == 183_657


@needs_sample
def test_load_resets_the_view_and_remembers_the_file(sample, tmp_path):
    app = loaded(sample)
    m = app.model
    m.set_channel(9)
    m.set_first(300)
    other = tmp_path / "again.spc"
    for src in sample.parent.glob("BH_SPC132*"):
        shutil.copy(src, tmp_path / src.name.replace("BH_SPC132", "again"))
    assert app.load_file(str(other))
    pump(app)
    assert (m.first_index, m.channel_filter) == (0, -1)
    assert m.input_file == str(other)
    assert m.notice == f"183,657 photons from {other}"


@needs_sample
def test_a_second_load_is_refused_while_one_runs(sample, monkeypatch):
    import threading

    from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

    gate = threading.Event()
    real = PhotonTableModel.load_file

    def slow(self, path, tttr_type=None):
        gate.wait(10)
        real(self, path, tttr_type)

    monkeypatch.setattr(PhotonTableModel, "load_file", slow)
    app = make_app()
    assert app.load_file(str(sample))
    draw(app, frames=1)
    assert app.job.busy and app.model.busy
    assert app.load_file(str(sample)) is False
    assert app.files_dropped([str(sample)]) is False
    assert app.model.enabled("request_open") is False
    assert any("Loading the photons" in s for s in draw(app).strings)
    gate.set()
    pump(app)
    assert app.model.loaded and app.model.enabled("request_open")


@needs_sample
def test_copy_visible_puts_the_page_on_the_clipboard(sample, monkeypatch):
    import emtk.im as im

    copied = []
    monkeypatch.setattr(im, "set_clipboard_text", lambda s: copied.append(s))
    app = loaded(sample)
    app.model.set_rows(5)
    app.model.set_channel(9)
    press(app, "request_copy")
    assert len(copied) == 1
    lines = copied[0].splitlines()
    assert lines[0] == "photon\tidx\tchannel\tmicro\tmacro_ms"
    assert len(lines) == 6
    # identical to what the Qt tool's model would copy for the same page
    assert copied[0] == app.model.table.page_tsv(0, 5, 9)
    assert app.model.notice == "Copied 5 rows to the clipboard."
    assert lines[1].split("\t")[0] == "0" and lines[1].split("\t")[2] == "9"


def test_copy_with_nothing_loaded_does_nothing(monkeypatch):
    import emtk.im as im

    copied = []
    monkeypatch.setattr(im, "set_clipboard_text", lambda s: copied.append(s))
    app = make_app()
    assert app.model.enabled("request_copy") is False
    press(app, "request_copy")
    assert copied == [] and app.model.request == ""


def test_open_shows_the_file_dialog_and_loads_the_choice(sample, monkeypatch):
    from emtk.file_dialog import FileDialog

    app = make_app()
    app.model.input_file = str(sample)
    press(app, "request_open")
    assert app.dialog is not None
    assert app.dialog.title == "Open TTTR file"
    assert Path(app.dialog.directory) == sample.parent  # starts where the last file was
    monkeypatch.setattr(FileDialog, "draw", lambda self: [str(sample)])
    draw(app, frames=1)
    assert app.dialog is None
    pump(app)
    assert app.model.loaded
    # cancelling closes the dialog and changes nothing
    press(app, "request_open")
    monkeypatch.setattr(FileDialog, "draw", lambda self: False)
    draw(app, frames=1)
    assert app.dialog is None and app.model.loaded


@needs_sample
def test_a_dropped_file_is_opened(sample):
    app = make_app()
    assert app.files_dropped([]) is False
    assert app.on_files_dropped([str(sample)]) is True
    pump(app)
    assert app.model.table.n_photons == 183_657


# ── 3. error paths ──────────────────────────────────────────────────────


def test_a_missing_file_is_reported_and_nothing_loads(tmp_path):
    app = make_app()
    missing = tmp_path / "nope.ptu"
    assert app.load_file(str(missing))
    pump(app)
    assert app.model.notice == f"Could not open {missing}: file does not exist"
    assert not app.model.loaded and app.model.rows == []
    assert app.model.input_file == ""


@needs_sample
def test_an_unreadable_file_keeps_the_old_table_and_says_what_tttrlib_said(qapp, sample, tmp_path):
    """Same text as the Qt tool's status message, and the table that was shown stays."""
    from chisurf.plugins.tttr.photon_table.gui.tool import PhotonTableTool

    bad = tmp_path / "broken.ptu"
    bad.write_text("this is not a TTTR file")
    app = loaded(sample)
    app.model.set_first(400)
    assert app.load_file(str(bad))
    pump(app)
    assert app.model.table.n_photons == 183_657 and app.model.first_index == 400
    assert app.model.notice.startswith(f"Could not open {bad}: ")
    assert app.model.input_file == str(sample)
    tool = PhotonTableTool()
    try:
        tool.load_file(str(bad))
        assert app.model.notice == tool.statusBar().currentMessage()
    finally:
        tool.close()
    # the window still draws the old table after the error
    assert any("183,657 photons" in s for s in draw(app).strings)


def test_the_error_does_not_cover_the_window(tmp_path):
    """The earlier standalone app replaced the whole window by an undismissable error box."""
    app = make_app()
    app.load_file(str(tmp_path / "gone.ptu"))
    pump(app)
    strings = draw(app).strings
    assert any("Could not open" in s for s in strings)
    assert "Open TTTR..." in strings  # the controls are still there
    app.load_file(str(tmp_path / "gone2.ptu"))  # and a new try is possible
    pump(app)
    assert app.model.notice.endswith("gone2.ptu: file does not exist")


# ── 4. no invented data, drawing ────────────────────────────────────────


def test_the_empty_state_is_a_message_and_no_rows():
    app = make_app()
    painter = draw(app)
    assert app.model.rows == []
    assert any("Open a TTTR file, or drop one on this window" in s for s in painter.strings)
    assert not any("photons from" in s for s in painter.strings)
    assert app.model.range_text == "no photons"
    assert app.model.channel_labels() == [[-1, "All channels"]]
    assert app.model.enabled("go_next") is False


@needs_sample
@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (500, 500)])
def test_draws_empty_and_populated_at_both_sizes(sample, size):
    empty = draw(make_app(), size)
    assert len(empty.texts) > 5
    app = loaded(sample)
    painter = draw(app, size)
    assert len(painter.texts) > len(empty.texts)
    assert any("183,657 photons" in s for s in painter.strings)
    assert "0.768366" in painter.strings  # the first macro time in ms


@needs_sample
def test_the_page_table_notices_a_new_page(sample):
    m = loaded(sample).model
    first = m.rows
    assert m.rows is first  # unchanged page: same object, no rebuild
    m.go_next()
    second = m.rows
    assert second is not first and second.revision != first.revision
    assert second[0]["photon"] == 200


# ── 5. tooltips, spec, guide, help ──────────────────────────────────────


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


def test_every_spec_key_exists_on_the_model():
    model = PhotonTableViewModel()
    spec = json.loads(SPEC_FILE.read_text())
    for section in _walk(spec["sections"]):
        for key in ("attr", "call", "source", "options_source"):
            if section.get(key):
                assert hasattr(model, section[key]), (key, section[key])
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        hidden = section.get("hidden_when")
        if hidden:
            assert hasattr(model, hidden["attr"]), hidden
        options = section.get("options") or {}
        if options.get("source"):
            assert hasattr(model, options["source"])
        for column in options.get("columns", []):
            assert column.get("tooltip"), column
    row_keys = {"photon", "idx", "channel", "micro", "macro"}
    columns = {c["key"] for s in _walk(spec["sections"]) for c in (s.get("options") or {}).get("columns", [])}
    assert columns == row_keys


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("photon_table"))
    assert inventory["controls_without_tooltip"] == []
    spec = json.loads(SPEC_FILE.read_text())
    for section in _walk(spec["sections"]):
        if section.get("type") in ("value", "choice", "toggle", "custom", "info", "button_row", "panel"):
            assert section.get("description"), section.get("attr") or section.get("key") or section
        for button in section.get("buttons", []):
            assert button.get("description"), button


@needs_sample
def test_the_populated_app_has_no_untooltipped_control_either(sample):
    from test.gui.emtk_port_parity import emtk_inventory

    inventory = emtk_inventory(loaded(sample))
    assert inventory["controls_without_tooltip"] == []
    labels = {row["label"] for row in inventory["interactive"]}
    assert {"Open TTTR...", "Copy visible", "First", "Prev", "Next", "Last", "Guide", "Help"} <= labels


@needs_sample
def test_guide_steps_point_at_controls_the_app_draws(sample):
    from chisurf.emtk.help_guide import EmTkGuidedTour

    app = loaded(sample)
    draw(app)
    steps = json.loads((GUI / "guide.json").read_text())["steps"]
    assert len(steps) == 6
    for step in steps:
        name = EmTkGuidedTour._target_key(step["target"])
        rect = app.item_rects.get(name) or app.form.rects.get(name)
        assert rect is not None, f"{step['title']}: nothing drawn for {name!r}"
    awaiting = [EmTkGuidedTour._target_key(s["target"]) for s in steps if s.get("await")]
    assert awaiting == ["request_open", "go_next", "channel_filter", "request_copy"]


@needs_sample
def test_the_tour_hears_the_buttons_and_the_channel(sample):
    from emtk.view_form import _commit

    app = loaded(sample)
    draw(app)
    heard = []
    app.tour.notify_used = heard.append
    app.form.on_used = app.tour.notify_used
    app.form.used("request_open")
    section = next(s for s in _walk(app.panels["photons"]["sections"]) if s.get("attr") == "channel_filter")
    _commit(app.model, section, 8, app.form)
    assert "channel_filter" in heard and "request_open" in heard
    assert app.model.channel_filter == 8


def test_help_exists_and_draws():
    text = (GUI / "help.md").read_text()
    for word in ("Open TTTR...", "Copy visible", "Channel", "Rows"):
        assert word in text
    app = make_app()
    app.help_window.show()
    assert draw(app).strings
    app.tour.start()
    assert draw(app).strings


# ── 6. persistence, no Qt ───────────────────────────────────────────────


def test_settings_round_trip(sample):
    app = make_app()
    app.model.rows_per_page = 77
    app.model.input_file = str(sample)
    saved = json.loads(json.dumps(app.export_settings()))
    assert saved == {"rows_per_page": 77, "input_file": str(sample)}
    other = make_app()
    other.restore_settings(saved)
    assert other.model.rows_per_page == 77 and other.model.input_file == str(sample)
    assert not other.model.loaded  # remembered, not reopened
    other.restore_settings({"rows_per_page": 10**9})
    assert other.model.rows_per_page == 20_000


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("photon_table")
    assert result["ok"], result["output"]


def test_the_manifest_opens_the_native_app():
    manifest = json.loads((HERE.parent / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.tttr.photon_table.gui.app:make_app"
    assert isinstance(make_app(), PhotonTableApp)
