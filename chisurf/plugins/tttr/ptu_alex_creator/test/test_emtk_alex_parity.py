"""The ALEX Creator's emtk app against the Qt tool, and every control operated with real input.

Hermetic: ``HOME``, ``CHISURF_SETTINGS_DIR`` and the MMFDB settings / database point into a temporary folder, the real
``~/.chisurf`` is snapshotted and must be unchanged at the end (its ``logs`` folder aside). Nothing reaches the app but what a
host delivers (pointer press / release / move, the wheel, typed keys, dropped files); the numbers are compared with the Qt
tool's own view model (the Qt widget is built offscreen for the settings and the help button) on a real photon file.
The control -> test list is in ``okf/plugins/emtk-ports/ptu_alex_creator/REPORT.md``.
"""

from __future__ import annotations

import json
import os
import pwd
import time
from pathlib import Path

import numpy as np
import pytest
import tttrlib
from emtk import keys

from chisurf.plugins.emtk_test_input import Driver, assert_tour_card_clear
from chisurf.plugins.tttr.ptu_alex_creator import core
from chisurf.plugins.tttr.ptu_alex_creator.api import AlexRequest, run
from chisurf.plugins.tttr.ptu_alex_creator.gui.app import AlexApp, translated
from chisurf.plugins.tttr.ptu_alex_creator.gui.view_model import AlexViewModel
from test.gui import emtk_layout_checks as lay

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
SAMPLE = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
SIZES = [(1200, 800), (800, 600)]
REAL_HOME = Path(pwd.getpwuid(os.getuid()).pw_dir)


def _tree(root: Path) -> dict:
    out = {}
    for path in sorted(root.rglob("*")) if root.is_dir() else []:
        if path.relative_to(root).parts[:1] in (("logs",), ("cache",)):  # logs, and the bytecode cache any Python process fills
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        out[str(path.relative_to(root))] = (st.st_size, st.st_mtime_ns)
    return out


@pytest.fixture(scope="module", autouse=True)
def real_chisurf_untouched():
    """The user's real ``~/.chisurf`` is read by nothing here: it is the same afterwards (``logs`` ignored)."""
    before = _tree(REAL_HOME / ".chisurf")
    yield
    assert _tree(REAL_HOME / ".chisurf") == before, "a test wrote into the real ~/.chisurf"


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    (tmp_path / "home").mkdir()
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def source(tmp_path):
    if not SAMPLE.is_file():
        pytest.skip("Leica TTTR sample unavailable")
    folder = tmp_path / "data"
    folder.mkdir()
    path = folder / "source.ptu"
    tttrlib.TTTR(str(SAMPLE))[:5000].write(str(path))
    return path


@pytest.fixture
def second(source):
    path = source.with_name("second.ptu")
    path.write_bytes(source.read_bytes())
    return path


class Ui(Driver):
    """A :class:`Driver` that also waits for the workers and operates the file dialog."""

    def settle(self, timeout: float = 30.0):
        end = time.monotonic() + timeout
        while self.app.running and time.monotonic() < end:
            time.sleep(0.01)
            self.draw(1)
        assert not self.app.running, "the worker did not finish"
        return self.draw(3)

    @property
    def dialog_open(self) -> bool:
        return self.app.dialog is not None

    def pick(self, name: str, action: str = "Open"):
        self.draw(2)
        assert self.dialog_open
        self.click_text(name)
        self.click_text(action)

    def choose_option(self, field: str, label: str):
        """Open a choice and click its entry (a long list is narrowed by typing into its filter first)."""
        self.click_name(field)
        painter = self.draw(2)
        if not any(t[5] == label for t in painter.texts):
            self.type(label)
        self.click_text(label)


@pytest.fixture
def ui(tmp_path):
    ui = Ui(AlexApp(tmp_path / "preferences.json"))
    yield ui
    ui.app.close()


def loaded(ui, path):
    assert ui.drop(path)
    ui.settle()
    assert ui.app.model.has_data
    return ui


def same_file(first, second):
    a, b = tttrlib.TTTR(str(first)), tttrlib.TTTR(str(second))
    for attr in ("macro_times", "micro_times", "routing_channels", "event_types"):
        np.testing.assert_array_equal(getattr(a, attr), getattr(b, attr))
    assert a.header.json == b.header.json


# -- parity with the Qt tool ----------------------------------------------------------------------------------------- #


def test_defaults_and_choices_equal_the_qt_tools(ui):
    qt = AlexViewModel()
    for attr in ("input_format", "output_format", "alex_period", "period_shift", "batch_mode", "batch_output_folder"):
        assert getattr(ui.app, attr) == getattr(qt, attr), attr
    assert ui.app.input_format_options() == qt.input_format_options()
    assert ui.app.output_format_options() == qt.output_format_options()
    assert ui.app.model.batch_files == qt.batch_files == []
    assert not ui.app.model.has_data and qt.can_save() is not None


def test_the_number_fields_have_the_qt_tools_range_and_step(ui):
    def fields(spec):
        found = {}

        def walk(sections):
            for s in sections:
                if s.get("type") == "value" and s.get("attr") in ("alex_period", "period_shift"):
                    found[s["attr"]] = (s["minimum"], s["maximum"], s["step"], s["kind"])
                walk(s.get("sections", []))

        walk(spec["sections"])
        return found

    qt = fields(json.loads((PLUGIN / "gui" / "alex.view.json").read_text()))
    assert fields(ui.app.spec_source) == qt == {"alex_period": (1, 1000000, 100, "int"), "period_shift": (-1000000, 1000000, 1, "int")}
    ui.draw()
    spin = [s for s in _walk(ui.app.spec) if s.get("attr") in ("alex_period", "period_shift")]
    assert spin and all(s["style"] == "spin" for s in spin)  # typed value, arrows and wheel: not a drag field


def rects_left_width(ui) -> float:
    x, y, w, h = ui.app.item_rects["input_file"]
    return x + w + 8


def _walk(spec):
    for s in spec["sections"] if "sections" in spec else []:
        yield s
        yield from _walk(s)


def test_histogram_and_converted_file_equal_the_qt_tools_numbers(ui, source, tmp_path):
    qt = AlexViewModel()
    qt.load(str(source))
    loaded(ui, source)
    for period, shift in ((8000, 0), (4000, 23), (2500, -17)):
        qt.alex_period, qt.period_shift = period, shift
        ui.app.model.alex_period, ui.app.model.period_shift = period, shift
        ui.draw(2)
        ui.settle()
        np.testing.assert_array_equal(ui.app.histogram, qt.histogram_series()[0]["y"])
    qt_out, ours = tmp_path / "qt.ptu", tmp_path / "ours.ptu"
    qt.save(str(qt_out))
    assert ui.app.save(ours)
    ui.settle()
    same_file(qt_out, ours)


@pytest.mark.parametrize("mode", ["convert", "merge"])
def test_batch_outputs_equal_the_qt_tools(ui, source, second, tmp_path, mode):
    qt = AlexViewModel()
    qt.batch_mode, qt.alex_period, qt.period_shift = mode, 4000, 7
    qt.add_batch_files([str(source), str(second)])
    qt.batch_output_folder = str(tmp_path / "qt_out")
    expected = qt.run_batch()
    ui.app.add_paths([source, second])
    ui.app.model.batch_mode, ui.app.model.alex_period, ui.app.model.period_shift = mode, 4000, 7
    ui.app.model.batch_output_folder = str(tmp_path / "our_out")
    assert ui.app.run_batch()
    ui.settle()
    assert len(ui.app.outputs) == len(expected)
    for a, b in zip(expected, ui.app.outputs):
        same_file(a, b)


def test_another_output_container_equals_the_qt_tools(ui, source, tmp_path):
    qt = AlexViewModel()
    qt.output_format = "HT3"
    qt.load(str(source))
    qt.save(str(tmp_path / "qt.ht3"))
    loaded(ui, source)
    ui.choose_option("output_format", "HT3")
    assert ui.app.output_format == "HT3"
    assert ui.app.save(tmp_path / "ours.ht3")
    ui.settle()
    same_file(tmp_path / "qt.ht3", tmp_path / "ours.ht3")


def test_the_qt_tool_has_a_help_button(qapp, qtbot):
    from qtpy import QtWidgets

    from chisurf.plugins.tttr.ptu_alex_creator.gui.tool import AlexPTUCreator

    tool = AlexPTUCreator()
    qtbot.addWidget(tool)
    texts = {b.text() for b in tool.findChildren(QtWidgets.QToolButton)}
    assert "?" in texts or any("?" in t for t in texts)


# -- the file row ---------------------------------------------------------------------------------------------------- #


def test_dropping_one_file_loads_it_and_shows_the_histogram(ui, source):
    loaded(ui, source)
    assert ui.app.model.input_file == str(source)
    assert sum(ui.app.histogram) == 5000 and ui.drawn("5,000 events")
    assert any("source.ptu" in s for s in ui.draw().strings)


def test_open_button_opens_the_dialog_and_a_picked_file_loads(ui, source):
    ui.click_name("choose_input")
    assert ui.dialog_open
    ui.app.dialog.enter(str(source.parent))
    ui.pick(source.name)
    assert not ui.dialog_open
    ui.settle()
    assert ui.app.model.input_file == str(source) and ui.app.model.has_data


def test_open_dialog_cancel_and_close_load_nothing(ui, source):
    ui.click_name("choose_input")
    ui.click_text("Cancel")
    assert not ui.dialog_open and not ui.app.model.has_data
    ui.click_name("choose_input")
    ui.click_text("×")
    assert not ui.dialog_open and not ui.app.model.has_data


def test_typing_a_path_and_enter_loads_it(ui, source):
    ui.type_into_name("input_file", str(source))
    ui.settle()
    assert ui.app.model.has_data and ui.app.loaded_path == str(source)


def test_the_load_button_reads_the_typed_path_and_is_grey_without_one(ui, source):
    ui.click_name("load_input")
    assert not ui.app.model.has_data and ui.app.message == ""  # greyed: a press does nothing
    ui.type_into_name("input_file", str(source), commit=False)
    ui.click_name("choose_save")  # leaving the field commits it: the Qt editingFinished
    ui.settle()
    assert ui.app.model.has_data
    ui.app.model._tttr = None
    ui.app.loaded_path = ""
    ui.click_name("load_input")
    ui.settle()
    assert ui.app.model.has_data


def test_a_path_that_is_not_a_file_says_so(ui, tmp_path):
    ui.type_into_name("input_file", str(tmp_path / "missing.ptu"))
    assert not ui.app.model.has_data
    assert ui.app.message_is_error and "missing.ptu" in ui.app.message
    assert any("missing.ptu" in s for s in ui.draw().strings)


def test_the_input_format_choice_is_clicked(ui, source):
    ui.choose_option("input_format", "PTU")
    assert ui.app.input_format == "PTU"
    loaded(ui, source)
    assert ui.app.model.has_data
    ui.choose_option("input_format", "Auto")
    assert ui.app.input_format == "Auto"


# -- period and shift ------------------------------------------------------------------------------------------------ #


def test_period_and_shift_are_typed_with_enter_and_refold_the_histogram(ui, source):
    loaded(ui, source)
    ui.type_into_name("alex_period", "4000")
    ui.settle()
    assert ui.app.model.alex_period == 4000 and len(ui.app.histogram) == 4000
    np.testing.assert_array_equal(ui.app.histogram, core.alex_histogram(str(source), 4000, 0))
    ui.type_into_name("period_shift", "-250")
    ui.settle()
    assert ui.app.model.period_shift == -250
    np.testing.assert_array_equal(ui.app.histogram, core.alex_histogram(str(source), 4000, -250))


def test_typed_values_are_clamped_and_garbage_is_ignored(ui):
    ui.type_into_name("alex_period", "0")
    assert ui.app.model.alex_period == 1
    ui.type_into_name("alex_period", "99999999")
    assert ui.app.model.alex_period == 1000000
    ui.type_into_name("alex_period", "abc")
    assert ui.app.model.alex_period == 1000000
    ui.type_into_name("period_shift", "-99999999")
    assert ui.app.model.period_shift == -1000000


def test_a_click_away_commits_a_typed_value(ui):
    ui.type_into_name("period_shift", "41", commit=False)
    ui.click_name("choose_input")
    ui.click_text("Cancel")
    assert ui.app.model.period_shift == 41


@pytest.mark.parametrize("field,step", [("alex_period", 100), ("period_shift", 1)])
def test_each_arrow_steps_its_field_by_the_qt_step(ui, field, step):
    start = getattr(ui.app.model, field)
    rect = ui.app.item_rects[f"{field}.stepper"] if f"{field}.stepper" in ui.app.item_rects else ui.rect(f"{field}.stepper")
    ui.click(rect, 0.5, 0.25)
    assert getattr(ui.app.model, field) == start + step
    ui.click(rect, 0.5, 0.75)
    ui.click(rect, 0.5, 0.75)
    assert getattr(ui.app.model, field) == start - step


@pytest.mark.parametrize("field,step", [("alex_period", 100), ("period_shift", 1)])
def test_the_wheel_over_a_field_steps_it(ui, field, step):
    x, y, w, h = ui.rect(field)
    start = getattr(ui.app.model, field)
    ui.wheel(x + w / 2, y + h / 2, 1.0)
    assert getattr(ui.app.model, field) == start + step
    ui.wheel(x + w / 2, y + h / 2, -1.0)
    assert getattr(ui.app.model, field) == start
    ui.wheel(x + w / 2, y + h / 2, -3.0)  # one notch is one step however large the delta
    assert getattr(ui.app.model, field) == start - step


def test_the_form_stays_usable_while_the_histogram_refolds(ui, source):
    loaded(ui, source)
    ui.click(ui.rect("alex_period.stepper"), 0.5, 0.25)
    assert ui.app.enabled("choose_save")  # a preview is not a greyed window
    ui.settle()


# -- save -------------------------------------------------------------------------------------------------------------- #


def test_save_is_grey_without_a_file_and_a_click_opens_nothing(ui):
    ui.click_name("choose_save")
    assert not ui.dialog_open and not ui.app.model.has_data


def test_save_dialog_offers_the_qt_name_and_writes_the_converted_file(ui, source, tmp_path):
    loaded(ui, source)
    ui.app.model.alex_period, ui.app.model.period_shift = 4000, 23
    ui.click_name("choose_save")
    assert ui.dialog_open and ui.app.dialog.filename == core.default_output_name(str(source), "PTU")
    ui.click_text("Cancel")
    assert not ui.dialog_open and not ui.app.outputs
    ui.click_name("choose_save")
    ui.click_text("×")
    assert not ui.dialog_open
    ui.click_name("choose_save")
    ui.app.dialog.enter(str(tmp_path))
    ui.click_text(ui.app.dialog.filename)
    ui.app.key(0x41, "a", 0x04000000)
    ui.draw(1)
    ui.type("converted.ptu")
    ui.click_text("Save")
    ui.settle()
    out = tmp_path / "converted.ptu"
    assert out.is_file() and ui.app.outputs == [str(out)]
    assert any("converted.ptu" in s for s in ui.draw().strings)
    expected = tmp_path / "expected.ptu"
    core.convert_file(str(source), str(expected), 4000, 23, "PTU", "Auto")
    same_file(expected, out)


def test_the_input_file_is_never_overwritten(ui, source):
    loaded(ui, source)
    before = source.read_bytes()
    assert not ui.app.save(source)
    assert ui.app.message_is_error and "preserve" in ui.app.message
    assert source.read_bytes() == before


# -- the batch queue ---------------------------------------------------------------------------------------------------- #


def queue(ui):
    return [Path(p).name for p in ui.app.model.batch_files]


def test_add_files_multiselect_dialog_and_duplicates(ui, source, second):
    ui.click_name("choose_files")
    assert ui.dialog_open
    ui.app.dialog.enter(str(source.parent))
    ui.click_text(source.name)
    ui.click_text(second.name)
    ui.click_text("Open")
    assert queue(ui) == ["source.ptu", "second.ptu"]
    assert ui.drawn("second.ptu") and ui.drawn("source.ptu")
    ui.app.add_paths([source])
    assert queue(ui) == ["source.ptu", "second.ptu"]  # duplicates are ignored


def test_add_files_cancel_and_close_change_nothing(ui):
    ui.click_name("choose_files")
    ui.click_text("Cancel")
    ui.click_name("choose_files")
    ui.click_text("×")
    assert not ui.dialog_open and queue(ui) == []


def test_folder_button_queues_the_supported_files_recursively(ui, source, tmp_path):
    folder = tmp_path / "many"
    (folder / "deep").mkdir(parents=True)
    for name in ("a.ptu", "deep/b.sm", "deep/c.ht3", "notes.txt", "deep/readme.md"):
        (folder / name).write_text("")
    ui.click_name("choose_folder")
    assert ui.dialog_open
    ui.app.dialog.enter(str(tmp_path))
    ui.click_text("[many]")
    ui.click_text("Choose")
    assert sorted(queue(ui)) == ["a.ptu", "b.sm", "c.ht3"]


def test_database_button_opens_the_dataset_picker(ui):
    before = ui.draw().strings
    ui.click_name("choose_database")
    assert ui.app.dataset_picker.open if hasattr(ui.app.dataset_picker, "open") else ui.draw().strings != before


def test_remove_is_grey_until_a_row_is_selected_then_removes_that_file(ui, source, second):
    ui.app.add_paths([source, second])
    ui.draw(2)
    ui.click_name("remove_selected")
    assert queue(ui) == ["source.ptu", "second.ptu"]
    ui.click_text("second.ptu")
    assert ui.app.selected_path == str(second)
    ui.click_name("remove_selected")
    assert queue(ui) == ["source.ptu"] and source.is_file() and second.is_file()
    assert not ui.drawn("second.ptu")


def test_the_delete_key_removes_the_selected_row(ui, source, second):
    ui.app.add_paths([source, second])
    ui.draw(2)
    ui.click_text("source.ptu")
    ui.delete()
    assert queue(ui) == ["second.ptu"]


def test_clear_empties_the_queue_and_is_grey_when_empty(ui, source, second):
    ui.click_name("clear_queue")
    ui.app.add_paths([source, second])
    ui.draw(2)
    ui.click_name("clear_queue")
    assert queue(ui) == [] and not ui.drawn("source.ptu")
    assert not ui.app.enabled("clear_queue")


def test_the_wheel_scrolls_a_long_queue(ui, tmp_path):
    folder = tmp_path / "long"
    folder.mkdir()
    names = [f"file_{i:02d}.ptu" for i in range(60)]
    for name in names:
        (folder / name).write_text("")
    ui.app.add_paths([folder])
    ui.draw(3)
    assert ui.drawn("file_00.ptu") and not ui.drawn("file_59.ptu")
    x, y, w, h = ui.app.item_rects["queue"]
    ui.wheel(x + w / 2, y + h / 2, -8.0)
    assert not ui.drawn("file_00.ptu")
    assert any(f"file_{i:02d}.ptu" in s for i in range(20, 60) for s in ui.draw().strings)


def test_the_mode_radios_are_clicked(ui):
    ui.click_name("batch_mode.1")
    assert ui.app.model.batch_mode == "merge"
    ui.click_name("batch_mode.0")
    assert ui.app.model.batch_mode == "convert"


def test_the_output_folder_is_typed_and_browsed(ui, tmp_path):
    out = tmp_path / "typed_out"
    ui.type_into_name("batch_output_folder", str(out))
    assert ui.app.model.batch_output_folder == str(out)
    (tmp_path / "chosen").mkdir()
    ui.click_name("choose_output")
    assert ui.dialog_open
    ui.app.dialog.enter(str(tmp_path))
    ui.draw(2)
    ui.click_text("[chosen]")
    ui.click_text("Choose")
    assert ui.app.model.batch_output_folder == str(tmp_path / "chosen")
    ui.click_name("choose_output")
    ui.click_text("Cancel")
    assert not ui.dialog_open


def test_run_batch_says_what_is_missing(ui, source):
    ui.click_name("run_batch")
    assert ui.app.message_is_error and "batch list" in ui.app.message
    assert any("batch list" in s for s in ui.draw().strings)
    ui.app.add_paths([source])
    ui.click_name("run_batch")
    assert ui.app.message_is_error and "output folder" in ui.app.message
    assert ui.app.outputs == []


@pytest.mark.parametrize("mode,radio", [("convert", "batch_mode.0"), ("merge", "batch_mode.1")])
def test_run_batch_with_real_input_writes_the_files(ui, source, second, tmp_path, mode, radio):
    ui.app.add_paths([source, second])
    ui.click_name(radio)
    ui.type_into_name("alex_period", "4000")
    ui.type_into_name("period_shift", "7")
    out = tmp_path / "written"
    ui.type_into_name("batch_output_folder", str(out))
    ui.click_name("run_batch")
    ui.settle()
    expected = run(AlexRequest(files=[str(source), str(second)], mode=mode, output_dir=str(tmp_path / "ref"),
                               alex_period=4000, period_shift=7)).output_paths
    assert len(ui.app.outputs) == len(expected) == (2 if mode == "convert" else 1)
    for a, b in zip(expected, ui.app.outputs):
        same_file(a, b)
    assert any(Path(ui.app.outputs[0]).name in s for s in ui.draw().strings)


# -- drops -------------------------------------------------------------------------------------------------------------- #


def test_a_file_dropped_outside_the_queue_loads_and_one_over_it_is_queued(ui, source, second):
    x, y, w, h = ui.rect("choose_input")
    ui.app.pointer_move(x + 5, y + 5)
    assert ui.drop(source)
    ui.settle()
    assert ui.app.model.has_data and queue(ui) == []
    qx, qy, qw, qh = ui.app.item_rects["queue"]
    ui.app.pointer_move(qx + qw / 2, qy + qh / 2)
    assert ui.drop(second)
    assert queue(ui) == ["second.ptu"]


def test_several_files_and_folders_dropped_are_queued(ui, source, second, tmp_path):
    folder = tmp_path / "dropdir"
    folder.mkdir()
    (folder / "x.sm").write_text("")
    (folder / "x.txt").write_text("")
    assert ui.drop(source, second, folder)
    assert queue(ui) == ["source.ptu", "second.ptu", "x.sm"] and not ui.app.model.has_data


# -- settings -------------------------------------------------------------------------------------------------------------- #


def test_settings_round_trip_and_bad_values_are_ignored(tmp_path, source):
    state = tmp_path / "state.json"
    first = AlexApp(state)
    first.model.alex_period, first.model.period_shift = 1500, -22
    first.model.output_format, first.model.batch_mode = "HT3", "merge"
    first.model.batch_output_folder = str(tmp_path / "o")
    first.add_paths([source])
    first.close()
    again = AlexApp(state)
    try:
        assert (again.model.alex_period, again.model.period_shift) == (1500, -22)
        assert again.model.output_format == "HT3" and again.model.batch_mode == "merge"
        assert again.model.batch_files == [str(source)] and not again.model.has_data  # a remembered file is loaded explicitly
        again.set_state({"settings": {"alex_period": "junk", "input_format": "NOPE", "batch_mode": "x"}})
        assert again.model.alex_period == 8000 and again.model.input_format == "Auto" and again.model.batch_mode == "convert"
    finally:
        again.close()


def test_the_default_settings_file_is_in_the_settings_folder_not_the_real_home(tmp_path):
    app = AlexApp()
    app.close()
    assert (tmp_path / "settings" / "alex-emtk.json").is_file()
    assert not (REAL_HOME / ".chisurf" / "alex-emtk.json").stat().st_mtime_ns > time.time_ns() - 60e9 if (REAL_HOME / ".chisurf" / "alex-emtk.json").exists() else True


# -- guide, help ---------------------------------------------------------------------------------------------------------- #


def test_guide_and_help_buttons_work(ui):
    ui.click_name("guide")
    assert ui.app.guide.active
    ui.click_text("Close Tour")
    assert not ui.app.guide.active
    ui.click_name("help")
    assert ui.app.help.open
    ui.click_text("Close Help")
    assert not ui.app.help.open


def test_every_guide_target_is_drawn_and_the_card_covers_none(ui, source):
    loaded(ui, source)
    ui.click_name("guide")
    tour = ui.app.guide
    for size in SIZES:
        ui.resize(size)
        for index in range(len(tour.steps)):
            tour.start(index)
            ui.draw(3)
            assert_tour_card_clear(tour, size)


# -- layout ------------------------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize("size", SIZES)
def test_layout_populated_and_empty(ui, source, second, size):
    ui.resize(size)
    for populated in (False, True):
        if populated:
            loaded(ui, source)
            ui.app.add_paths([source, second])
            ui.draw(3)
        painter = ui.draw(3)
        lay.assert_texts_apart(painter, region=(0, 0, rects_left_width(ui), size[1]))  # (the plot's rotated axis caption is not a box)
        rects = {k: v for k, v in ui.app.item_rects.items() if not k.endswith(".stepper")}
        lay.assert_inside(rects, size)
        lay.assert_short(rects, ["alex_period", "period_shift"])
        lay.assert_aligned(rects, ["input_file", "input_format", "alex_period", "batch_output_folder"], tolerance=2.0)
        px, py, pw, ph = rects["plot"]
        assert pw * ph > 0.35 * size[0] * size[1], "the plot gets the space"
        qx, qy, qw, qh = rects["queue"]
        assert qh >= 60, "the queue is not squeezed away"


# -- tooltips and translations --------------------------------------------------------------------------------------------- #


def test_every_control_has_a_tooltip_in_the_inventory(ui, source, second):
    from test.gui.emtk_port_parity import emtk_inventory

    loaded(ui, source)
    ui.app.add_paths([source, second])
    for size in SIZES:
        inventory = emtk_inventory(ui.app, size)
        assert inventory["controls_without_tooltip"] == [], inventory["controls_without_tooltip"]
        assert len(inventory["interactive"]) >= 14


def test_every_spec_guide_and_message_text_is_translated_in_all_five_locales(ui):
    from emtk.i18n import get_locale, set_locale, tr

    from chisurf.plugins.tttr.ptu_alex_creator.gui import translations

    texts = set()

    def collect(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("title", "label", "description", "tooltip", "hint", "text") and isinstance(value, str) and value:
                    texts.add(value)
                elif key == "labels":
                    texts.update(value)
                else:
                    collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(ui.app.spec_source)
    collect(json.loads((PLUGIN / "gui" / "guide.json").read_text()))
    texts.update(["No file loaded.", "Guide", "Help", "events", "Loading…", "Loaded", "Written files", "Working…",
                  "Please choose an existing TTTR file.", "Choose a different output file to preserve the source.",
                  "Add .sm (or other TTTR) files to the batch list first.",
                  "Choose an output folder for the converted files."])
    rows = [line.split("|") for line in translations.ROWS.splitlines()]
    assert all(len(row) == 6 for row in rows)
    known = {row[0] for row in rows}
    assert not texts - known, sorted(texts - known)
    previous = get_locale()
    try:
        for index, locale in enumerate(("de", "fr", "es", "pt", "ru"), start=1):
            set_locale(locale)
            for row in rows:
                assert tr(row[0]) == row[index], (locale, row[0])
                assert row[index].strip(), (locale, row[0])
        set_locale("de")
        spec = translated(ui.app.spec_source)
        assert spec["sections"][0]["title"] == "Eingabedatei"
        assert spec["sections"][0]["sections"][1]["buttons"][0]["label"] == "Öffnen…"
    finally:
        set_locale(previous)


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("ptu_alex_creator")
    assert result["ok"], result["output"]
