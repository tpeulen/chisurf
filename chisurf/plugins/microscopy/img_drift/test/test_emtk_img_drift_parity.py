"""The native drift-correction tool against the Qt tool it replaces: numbers, every action and every error path.

Hermetic: settings in a temporary folder, files in ``tmp_path``, no network (the database picker gets a stub client). References:
(a) what the Qt window showed on its drifting TIFF and on the real photon stream (``okf/plugins/emtk-ports/img_drift/qt_values.json``,
captured by ``scripts/capture_qt_populated.py`` before the port), (b) the Qt tool itself, constructed offscreen and run on the same files,
and (c) the drift written into the test stack, which is known exactly.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fio.image import imread, imwrite
from chisurf.plugins.microscopy.img_drift import core
from chisurf.plugins.microscopy.img_drift.gui.app import ImgDriftApp, make_app
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, dialog_open, hermetic_env, numeric_ticks, walk

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
EVIDENCE = REPO / "okf/plugins/emtk-ports/img_drift"
QT_VALUES = json.loads((EVIDENCE / "qt_values.json").read_text(encoding="utf-8"))
QT_SHIFTS_CSV = (EVIDENCE / "qt_shifts.csv").read_text(encoding="utf-8")
QT_SPEC = json.loads((PLUGIN / "gui" / "drift.view.json").read_text(encoding="utf-8"))
EMTK_SPEC = json.loads((PLUGIN / "gui" / "drift_emtk.view.json").read_text(encoding="utf-8"))
HT3 = REPO / "test/data/clsm/PQ_Olympus_MFIS.ht3"
BIG = (1200, 800)

_make = importlib.util.spec_from_file_location("drift_make_data", EVIDENCE / "scripts" / "make_data.py")
_data = importlib.util.module_from_spec(_make)
_make.loader.exec_module(_data)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def drv(app):
    return Driver(app, (1000, 700))


@pytest.fixture
def tiff(tmp_path):
    path = tmp_path / "drift.tif"
    imwrite(path, _data.drifting_stack())
    return path


def measured(app, drv, path):
    """Choose *path* the way a person does (type it, Enter) and wait for the automatic measurement."""
    drv.type_into("filename", str(path))
    drv.settle()
    return app.model


def shifts_of(model):
    return np.asarray(model.result.shifts, dtype=float)


# ── 1. the numbers ──────────────────────────────────────────────────────────────────────────────────────────── #


def test_choosing_a_drifting_stack_measures_exactly_the_injected_drift_and_the_qt_numbers(app, drv, tiff):
    m = measured(app, drv, tiff)
    qt = QT_VALUES["tiff_default"]
    assert m.status_line == qt["status"] == "Max drift 24.6 px over 12 frames."
    np.testing.assert_allclose(shifts_of(m), qt["shifts"], atol=0)
    truth = np.array([[2 * k, -k] for k in range(12)], dtype=float)  # the drift written into the stack, (dy, dx) per frame
    np.testing.assert_allclose(shifts_of(m), truth)
    assert m.result.total_drift == pytest.approx(qt["total_drift"], rel=1e-12)
    assert float(np.asarray(m.before_image()).sum()) == pytest.approx(qt["before_sum"], rel=1e-9)
    assert float(np.asarray(m.after_image()).std()) == pytest.approx(qt["after_std"], rel=1e-9)
    assert np.asarray(m.after_image()).std() > 2 * np.asarray(m.before_image()).std() / 2  # sharper: the correction worked
    assert m.channel == "ch0" and m.channel_names == ["ch0"]


def test_the_options_give_the_numbers_the_qt_window_showed(app, drv, tiff):
    m = measured(app, drv, tiff)
    m.reference, m.mode, m.smooth, m.subpixel = "previous", "constant", 0.0, True
    drv.click("measure")
    drv.settle()
    qt = QT_VALUES["tiff_previous_constant_subpixel"]
    assert m.status_line == qt["status"]
    np.testing.assert_allclose(shifts_of(m), qt["shifts"], atol=1e-12)
    m.reference, m.mode, m.smooth, m.subpixel = "mean", "wrap", 2.0, False
    drv.click("measure")
    drv.settle()
    assert m.status_line == QT_VALUES["tiff_mean"]["status"] == "Max drift 13.4 px over 12 frames."
    np.testing.assert_allclose(shifts_of(m), QT_VALUES["tiff_mean"]["shifts"], atol=1e-12)


@pytest.mark.skipif(not HT3.exists(), reason="CLSM test data not present")
def test_the_real_photon_stream_has_no_measurable_drift_as_in_the_qt_window(app, drv):
    m = measured(app, drv, HT3)
    qt = QT_VALUES["photon_stream"]
    assert m.status_line == qt["status"] == "Max drift below one pixel — correction changes nothing over 40 frames."
    assert m.result.kind == "tttr" and m.result.n_frames == 40 and not shifts_of(m).any()
    assert m.channel_names == qt["channel_names"] == ["ch0", "ch1", "ch4", "ch5"]
    assert "No image loaded." not in drv.strings()


def test_the_shift_table_shows_what_the_qt_table_showed(app, drv, tiff):
    m = measured(app, drv, tiff)
    qt_rows = QT_VALUES["tiff_default"]["shift_rows"]
    shown = [{"frame": r["frame"], "dx": f"{r['dx']:+.2f}", "dy": f"{r['dy']:+.2f}", "magnitude": f"{r['magnitude']:.2f}"}
             for r in m.shift_table_rows()]
    assert shown == qt_rows
    drv.click_text("Shifts")
    assert {"Frame", "dx / px", "dy / px", "|d| / px"} <= set(drv.draw(2).strings)


# ── 2. the live Qt tool on the same files ──────────────────────────────────────────────────────────────────── #


@pytest.fixture(scope="module")
def qt_tool():
    """The legacy Qt tool, offscreen, on temporary settings. Skipped only when Qt is not installed."""
    if importlib.util.find_spec("qtpy") is None:
        pytest.skip("Qt is not installed")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy import QtWidgets

    from chisurf.plugins.microscopy.img_drift.gui.tool import ImgDriftTool

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tool = ImgDriftTool()
    tool._qapp = qapp
    yield tool
    tool.close()


def qt_measure(tool, path, **settings):
    """What the Qt window computes for *path* (the file event starts the measurement; here it runs inline)."""
    m = tool.model
    m.reference, m.mode, m.smooth, m.subpixel = "first", "wrap", 2.0, False
    for k, v in settings.items():
        setattr(m, k, v)
    assert m.set_filename(str(path))
    assert m.compute()
    tool._on_finished(True)
    tool._refresh()
    return m


def qt_table_cells(tool):
    from qtpy import QtWidgets

    table = next(t for t in tool.findChildren(QtWidgets.QTableWidget) if t.columnCount() == 4)
    return [[table.item(r, c).text() for c in range(4)] for r in range(table.rowCount())]


SCENARIOS = {"defaults": {}, "previous frame": {"reference": "previous"}, "stack mean": {"reference": "mean"},
             "blanking": {"mode": "constant"}, "no smoothing, subpixel": {"smooth": 0.0, "subpixel": True},
             "heavy smoothing": {"smooth": 6.0}}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_the_qt_tool_and_the_emtk_app_agree_on_every_result(app, drv, qt_tool, tiff, scenario):
    settings = SCENARIOS[scenario]
    qt = qt_measure(qt_tool, tiff, **settings)
    m = measured(app, drv, tiff)
    for k, v in settings.items():
        setattr(m, k, v)
    drv.click("measure")
    drv.settle()
    assert m.status_line == qt_tool.statusBar().currentMessage() == qt.status
    np.testing.assert_array_equal(shifts_of(m), shifts_of(qt))
    np.testing.assert_array_equal(np.asarray(m.before_image()), np.asarray(qt.before_image()))
    np.testing.assert_array_equal(np.asarray(m.after_image()), np.asarray(qt.after_image()))
    assert [{k: v for k, v in s.items()} for s in m.drift_series()] and len(m.drift_series()) == len(qt.drift_series())
    for a, b in zip(m.drift_series(), qt.drift_series()):
        np.testing.assert_array_equal(a["y"], b["y"])
        assert a["name"] == b["name"] and a["color"] == b["color"]
    cells = [[str(r["frame"]), f"{r['dx']:+.2f}", f"{r['dy']:+.2f}", f"{r['magnitude']:.2f}"] for r in m.shift_table_rows()]
    assert cells == qt_table_cells(qt_tool)


@pytest.mark.skipif(not HT3.exists(), reason="CLSM test data not present")
def test_the_qt_tool_and_the_emtk_app_agree_on_the_photon_stream(app, drv, qt_tool):
    qt = qt_measure(qt_tool, HT3)
    m = measured(app, drv, HT3)
    assert m.status_line == qt.status and m.channel_names == qt.channel_names
    np.testing.assert_array_equal(shifts_of(m), shifts_of(qt))
    np.testing.assert_array_equal(np.asarray(m.before_image()), np.asarray(qt.before_image()))


@pytest.mark.parametrize("attr", ["smooth"])
def test_typed_extremes_are_clamped_to_the_range_the_qt_spin_box_enforced(app, drv, qt_tool, attr):
    from chisurf.gui.autoform.sections.builtin import ValueWidget

    editor = {vw._section.attr: vw.editor for vw in qt_tool.findChildren(ValueWidget) if getattr(vw, "_section", None)}[attr]
    drv.click("Estimator.fold")
    for qt_value in (1e9, -5.0):
        editor.setValue(qt_value)
        drv.type_into(attr, str(qt_value))
        assert getattr(app.model, attr) == pytest.approx(editor.value()), (attr, qt_value)


def test_the_qt_choice_lists_equal_the_emtk_choice_lists(app, qt_tool):
    """The stream's thin app offered 'middle', 'nearest' and 'reflect', which the core refuses, and no 'previous' / 'constant'."""
    from chisurf.gui.autoform.sections.builtin import ChoiceWidget

    qt_options = {}
    for cw in qt_tool.findChildren(ChoiceWidget):
        section = getattr(cw, "_section", None)
        if section is not None and section.attr in ("reference", "mode"):
            qt_options[section.attr] = [cw.combo.itemText(i) for i in range(cw.combo.count())] if hasattr(cw, "combo") else None
    spec = {s["attr"]: s for s in walk(EMTK_SPEC["sections"]) if s.get("type") == "choice"}
    for attr, labels in (("reference", ["First frame", "Previous frame", "Stack mean"]),
                         ("mode", ["Wrapping (keep all signal)", "Blanking (drop what leaves)"])):
        assert spec[attr]["labels"] == labels
        assert spec[attr]["options"] == (["first", "previous", "mean"] if attr == "reference" else ["wrap", "constant"])
        if qt_options.get(attr):
            assert qt_options[attr] == labels


# ── 3. choosing a file: typed, Browse, Database, drop ─────────────────────────────────────────────────────── #


def test_a_typed_path_is_measured_on_enter(app, drv, tiff):
    drv.type_into("filename", str(tiff), enter=False)
    assert app.model.filename == ""
    drv.enter()
    drv.settle()
    assert Path(app.model.filename) == tiff and app.model.result is not None


def test_a_path_typed_and_clicked_away_is_taken(app, drv, tiff):
    drv.type_into("filename", str(tiff), enter=False)
    drv.click("smooth", fx=0.3) if "smooth" in app.form.rects else drv.click("Estimator.fold")
    drv.settle()
    assert Path(app.model.filename) == tiff and app.model.result is not None


def test_browse_opens_the_dialog_and_a_chosen_file_is_measured(app, drv, tiff):
    app.model.folder = str(tiff.parent)
    drv.click("open_file")
    assert dialog_open(drv) and app.dialog.title == "Open image"
    drv.click_text("drift.tif")
    drv.click_text("Open", last=True)
    drv.settle()
    assert Path(app.model.filename) == tiff and app.model.status_line == QT_VALUES["tiff_default"]["status"]
    assert not dialog_open(drv) and app.model.folder == str(tiff.parent)


def test_browse_cancel_changes_nothing(app, drv, tiff):
    app.model.folder = str(tiff.parent)
    drv.click("open_file")
    drv.click_text("Cancel")
    assert app.model.filename == "" and not dialog_open(drv) and not app.job.busy


def test_the_file_dialog_window_has_a_title_and_a_close_button_and_escape_cancels(app, drv, tiff):
    app.model.folder = str(tiff.parent)
    drv.click("open_file")
    assert dialog_open(drv) and "Open image" in drv.draw(1).strings  # the window's title bar
    drv.click_text("\u00d7")
    assert not dialog_open(drv) and app.model.filename == ""
    drv.click("open_file")
    assert dialog_open(drv)
    drv.hover(500, 350)  # Escape closes the window under the pointer
    drv.escape()
    assert not dialog_open(drv) and app.model.filename == "" and not app.job.busy


class FakeClient:
    """A database client that lists one dataset and resolves it to a local file."""

    def __init__(self, path):
        self.path = str(path)

    def call(self, method, params=None):
        if method == "mmfdb.datasets.browse":
            return {"datasets": [{"artifact_id": "a1", "artifact_kind": "raw_data", "data_format": "tif",
                                  "original_filename": "stored_drift.tif"}], "total": 1}
        if method == "mmfdb.datasets.open":
            return {"local_path": self.path}
        raise AssertionError(method)


def open_picker(app, drv, tiff):
    import time

    app.picker.client = FakeClient(tiff)
    drv.click("open_database")
    drv.draw(2)
    assert app.picker.is_open
    end = time.monotonic() + 10
    while "stored_drift.tif [raw_data] (tif)" not in drv.draw(1).strings and time.monotonic() < end:
        time.sleep(0.02)


def test_the_database_button_opens_the_picker_and_a_dataset_is_selected_and_measured(app, drv, tiff):
    open_picker(app, drv, tiff)
    drv.click_text("stored_drift.tif [raw_data] (tif)")
    assert app.picker.selection is not None and app.picker.selection.artifact_id == "a1"
    assert app.picker.accept()  # the picker's own accept: what the "Open selected" button would call (see the xfail below)
    drv.settle()
    assert Path(app.model.filename) == tiff and app.model.result is not None and not app.picker.is_open


@pytest.mark.xfail(strict=True, reason="emtk gap: the dataset picker's Refresh / Previous / Next / Open selected buttons share one id "
                   "('...##dataset'), so the disabled Previous / Next swallow the release and 'Open selected' never fires; see REPORT.md section 10")
def test_the_open_selected_button_of_the_database_picker_can_be_pressed(app, drv, tiff):
    import time

    open_picker(app, drv, tiff)
    drv.click_text("stored_drift.tif [raw_data] (tif)")
    drv.click_text("Open selected")
    end = time.monotonic() + 5
    while app.picker.is_open and time.monotonic() < end:
        time.sleep(0.02)
        drv.draw(1)
    assert not app.picker.is_open


def test_the_database_picker_window_close_button_closes_it_and_loads_nothing(app, drv, tiff):
    open_picker(app, drv, tiff)
    drv.click_text("\u00d7")
    assert not app.picker.is_open and app.model.filename == ""


@pytest.mark.xfail(strict=True, reason="emtk gap: the picker's Cancel button shares the id '...##dataset' with Refresh / Previous / Next / "
                   "Open selected and never fires; see REPORT.md section 10")
def test_the_cancel_button_of_the_database_picker_can_be_pressed(app, drv, tiff):
    open_picker(app, drv, tiff)
    drv.click_text("Cancel")
    assert not app.picker.is_open


def test_dropping_a_file_on_the_window_loads_and_measures_it(app, drv, tiff):
    assert drv.drop(tiff) is True
    drv.settle()
    assert Path(app.model.filename) == tiff and app.model.result is not None
    assert app.files_dropped([]) is False


def test_dropping_while_a_measurement_runs_is_refused(app, drv, tiff):
    app.model.open_path(str(tiff))
    assert app.job.busy
    assert app.files_dropped([str(tiff)]) is False
    drv.settle()


def test_the_qt_host_delivers_a_dropped_file_to_the_app(app, tiff):
    pytest.importorskip("qtpy")
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui, QtWidgets

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    host = ControlHost(app)
    host.resize(900, 600)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(tiff))])
    enter = QtGui.QDragEnterEvent(QtCore.QPoint(10, 10), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    host.dragEnterEvent(enter)
    assert enter.isAccepted()
    host.dropEvent(QtGui.QDropEvent(QtCore.QPointF(10, 10), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier))
    assert Path(app.model.filename) == tiff and qapp is not None
    host.close()


# ── 4. errors ──────────────────────────────────────────────────────────────────────────────────────────────── #


def test_measure_with_nothing_loaded_says_so_where_the_qt_tool_stayed_silent(app, drv):
    drv.click("measure")
    assert app.model.status_line == QT_VALUES["empty_measure"]["model_status"] == "No image loaded."
    assert not app.job.busy and app.model.result is None
    assert "No image loaded." in drv.strings()


def test_a_corrupt_file_reports_the_reason(app, drv, tmp_path):
    bad = tmp_path / "bad.tif"
    bad.write_bytes(b"not a tiff")
    drv.type_into("filename", str(bad))
    drv.settle()
    assert app.model.status_line.startswith("Could not read the image:")
    assert app.model.status_line == app.model.status and app.model.result is None
    assert app.model.before_image() is None and "Could not read the image" in " ".join(drv.strings())


def test_a_single_frame_file_is_refused_with_the_qt_message(app, drv, tmp_path):
    one = tmp_path / "one.tif"
    imwrite(one, np.zeros((16, 16), dtype=np.float32))
    drv.type_into("filename", str(one))
    drv.settle()
    assert app.model.status_line == QT_VALUES["one_frame"]["model_status"] == "1 frame(s): drift correction needs at least two."
    assert app.model.result is None


def test_a_missing_file_leaves_no_image_loaded(app, drv, tmp_path):
    drv.type_into("filename", str(tmp_path / "missing.tif"))
    drv.settle()
    assert app.model.status_line == QT_VALUES["missing"]["model_status"] == "No image loaded." and app.model.result is None


def test_a_new_bad_file_clears_the_previous_result(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    assert app.model.result is not None
    bad = tmp_path / "bad.tif"
    bad.write_bytes(b"nope")
    drv.type_into("filename", str(bad))
    drv.settle()
    assert app.model.result is None and app.model.shift_table_rows() == [] and app.model.drift_series() == []


def test_the_actions_and_the_form_are_greyed_while_a_run_is_in_flight(app, drv, tiff):
    app.model.open_path(str(tiff))
    assert app.job.busy
    runs = []
    app.model.measure = lambda: runs.append(1)
    drv.click("measure")
    assert runs == []
    drv.click("reference")
    assert "Previous frame" not in drv.draw(1).strings  # the list did not open
    drv.settle()


def test_a_worker_that_raises_is_reported_not_swallowed(app, drv, tiff, monkeypatch):
    measured(app, drv, tiff)

    def boom(*a, **k):
        raise RuntimeError("correlation exploded")

    monkeypatch.setattr(core, "measure_drift", boom)
    drv.click("measure")
    drv.settle()
    assert "correlation exploded" in app.model.status_line and app.model.result is None


# ── 5. the settings: choices, estimator, toggles ─────────────────────────────────────────────────────────── #


def pick(drv, field, label):
    drv.click(field)
    assert label in drv.draw(1).strings, (field, label)
    drv.click_text(label, last=True)


def test_the_reference_list_offers_the_three_qt_references_and_each_is_picked(app, drv):
    for label, value in (("Previous frame", "previous"), ("Stack mean", "mean"), ("First frame", "first")):
        pick(drv, "reference", label)
        assert app.model.reference == value
        assert label in drv.draw(2).strings


def test_the_apply_by_list_offers_wrapping_and_blanking(app, drv):
    pick(drv, "mode", "Blanking (drop what leaves)")
    assert app.model.mode == "constant"
    pick(drv, "mode", "Wrapping (keep all signal)")
    assert app.model.mode == "wrap"


def test_escape_closes_an_open_list_without_choosing(app, drv):
    drv.click("reference")
    assert "Previous frame" in drv.draw(1).strings
    drv.escape()
    assert app.model.reference == "first"


def test_the_channel_list_names_the_channels_of_the_file_and_the_chosen_one_is_measured(app, drv):
    if not HT3.exists():
        pytest.skip("CLSM test data not present")
    measured(app, drv, HT3)
    drv.click("channel")
    shown = drv.draw(1).strings
    assert {"ch0", "ch1", "ch4", "ch5"} <= set(shown)
    drv.click_text("ch4", last=True)
    assert app.model.channel == "ch4"
    drv.click("measure")
    drv.settle()
    expected = core.measure_drift(str(HT3), "ch4")  # an independent call of the core on the chosen channel
    np.testing.assert_array_equal(shifts_of(app.model), np.asarray(expected.shifts, dtype=float))
    assert app.model.status_line.startswith("Max drift")


def test_the_estimator_panel_opens_and_smoothing_and_subpixel_give_the_qt_measurement(app, drv, qt_tool, tiff):
    drv.click("Estimator.fold")
    assert {"smooth", "subpixel"} <= set(app.form.rects)
    measured(app, drv, tiff)
    default = shifts_of(app.model).copy()
    drv.type_into("smooth", "0")
    drv.click("subpixel")
    assert app.model.smooth == 0.0 and app.model.subpixel is True
    drv.click("measure")
    drv.settle()
    qt = qt_measure(qt_tool, tiff, smooth=0.0, subpixel=True)
    np.testing.assert_array_equal(shifts_of(app.model), shifts_of(qt))
    assert not np.array_equal(shifts_of(app.model), default)  # sub-pixel refinement moved the answer off the whole pixels
    drv.click("subpixel")
    assert app.model.subpixel is False


def test_each_arrow_steps_smoothing_by_the_qt_step_and_stops_at_its_limits(app, drv):
    drv.click("Estimator.fold")
    x, y, w, h = drv.rect("smooth.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.smooth == pytest.approx(3.0)
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    assert app.model.smooth == pytest.approx(0.0)
    drv.type_into("smooth", "20")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.smooth == 20.0


def test_changing_a_setting_does_not_re_measure_by_itself_as_in_the_qt_tool(app, drv, tiff):
    measured(app, drv, tiff)
    before = app.model.status_line
    pick(drv, "reference", "Stack mean")
    assert not app.job.busy and app.model.status_line == before
    assert app.model.result.total_drift == pytest.approx(QT_VALUES["tiff_default"]["total_drift"])  # still the first-frame result


# ── 6. exports ────────────────────────────────────────────────────────────────────────────────────────────── #


def test_exports_without_a_result_say_so_where_the_qt_tool_stayed_silent(app, drv):
    drv.click("request_export_stack")
    assert app.model.status_line == "Measure the drift first." and not dialog_open(drv)
    drv.click("request_export_shifts")
    assert app.model.status_line == "Measure the drift first." and not dialog_open(drv)


def test_export_shifts_writes_the_csv_the_qt_tool_wrote(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    drv.click("request_export_shifts")
    painter = drv.draw(2)
    assert dialog_open(drv) and app.dialog.title == "Export drift shifts" and "drift.drift.csv" in painter.strings
    drv.click_text("Save", last=True)
    written = tmp_path / "drift.drift.csv"
    assert written.read_text() == QT_SHIFTS_CSV
    assert app.model.status_line == f"Wrote {written}" and not dialog_open(drv)


def test_export_stack_writes_the_corrected_tiff_the_qt_tool_wrote(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    drv.click("request_export_stack")
    painter = drv.draw(2)
    assert dialog_open(drv) and app.dialog.title == "Export corrected stack" and "drift.corrected.tif" in painter.strings
    drv.click_text("Save", last=True)
    drv.settle()
    written = tmp_path / "drift.corrected.tif"
    corrected = np.asarray(imread(str(written)))
    qt = QT_VALUES["export_stack"]
    assert list(corrected.shape) == qt["shape"] and float(corrected.sum()) == pytest.approx(qt["sum"], rel=1e-9)
    assert float(np.std(list(corrected), axis=0).mean()) == pytest.approx(qt["std_frame_to_frame"], rel=1e-6)
    assert app.model.status_line == f"Wrote {written}"
    # every corrected frame lies on the first one: the drift is gone
    raw = np.asarray(imread(str(tiff)))
    assert np.abs(corrected[5] - corrected[0]).mean() < 3.0 < np.abs(raw[5] - raw[0]).mean()  # 3.0: the noise floor of two frames


def test_export_dialog_cancel_writes_nothing(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    drv.click("request_export_stack")
    drv.draw(2)
    drv.click_text("Cancel")
    assert not list(tmp_path.glob("*.corrected.tif")) and not dialog_open(drv)


def test_export_to_an_unwritable_place_reports_instead_of_raising(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    blocker = tmp_path / "afile"
    blocker.write_text("not a folder")
    app.model.write_shifts(str(blocker / "s.csv"))
    assert app.model.status_line.startswith("Could not write")
    assert "Could not write" in " ".join(drv.strings())
    app.model.write_stack(str(blocker / "c.tif"))
    drv.settle()
    assert app.model.status_line.startswith("Could not write the corrected stack")


# ── 7. the views ─────────────────────────────────────────────────────────────────────────────────────────────── #


def test_every_view_says_what_to_do_before_there_is_a_result(app, drv):
    for tab, message in (("Drift trace", "Choose an image or press Measure"), ("Projection", "Measure a file")):
        drv.click_text(tab)
        assert any(s.startswith(message) for s in drv.draw(2).strings), tab


def test_every_view_is_drawn_after_a_measurement(app, drv, tiff):
    measured(app, drv, tiff)
    for tab, expect in (("Drift trace", {"frame", "displacement / px", "dx", "dy", "|d|"}),
                        ("Projection", {"Before", "After", "Colormap", "Reset view"}),
                        ("Shifts", {"Frame", "dx / px", "dy / px", "|d| / px"})):
        drv.click_text(tab)
        strings = set(drv.draw(2).strings)
        assert expect <= strings, (tab, expect - strings)


def test_the_two_projections_share_one_colormap_as_the_qt_docks_did(app, drv, tiff):
    measured(app, drv, tiff)
    drv.click_text("Projection")
    drv.draw(2)
    combos = [t[:4] for t in drv.draw(1).texts if t[5] == "inferno"]
    assert len(combos) == 2
    x, y, w, h = combos[0]
    drv.click_at(x + 10, y + h / 2)
    drv.click_text("viridis", last=True)
    assert app.model.colormap == "viridis"
    assert [t[5] for t in drv.draw(2).texts].count("viridis") == 2  # the second combo followed


def test_a_drag_pans_the_drift_trace_and_an_image(app, drv, tiff):
    measured(app, drv, tiff)
    drv.click_text("Drift trace")
    drv.draw(3)
    x, y, w, h = app.item_rects["Drift trace"]
    before = numeric_ticks(drv.draw(2))
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.4))
    assert numeric_ticks(drv.draw(2)) != before
    drv.click_text("Projection")
    drv.draw(3)
    bx, by, bw, bh = app.item_rects["before.image"]
    original = numeric_ticks(drv.draw(2))
    drv.drag((bx + bw * 0.5, by + bh * 0.5), (bx + bw * 0.3, by + bh * 0.3))
    assert numeric_ticks(drv.draw(2)) != original
    drv.click_text("Reset view")  # the first one belongs to the Before image
    assert numeric_ticks(drv.draw(3)) == original


def table_values(drv, expect):
    return [t[5] for t in drv.draw(2).texts if t[5] in expect]


def test_the_shift_table_header_sorts_by_value_and_a_row_click_changes_nothing(app, drv, tiff):
    measured(app, drv, tiff)
    drv.click_text("Shifts")
    magnitudes = {f"{r['magnitude']:.2f}" for r in app.model.shift_table_rows()}
    unsorted = table_values(drv, magnitudes)
    assert unsorted == [f"{r['magnitude']:.2f}" for r in app.model.shift_table_rows()]

    def header():
        return [t[:4] for t in drv.draw(1).texts if "|d| / px" in t[5]][0]

    drv.click(header())
    assert table_values(drv, magnitudes) == sorted(unsorted, key=float)
    drv.click(header())
    assert table_values(drv, magnitudes) == sorted(unsorted, key=float, reverse=True)
    before = app.model.export_settings()
    drv.click_text(unsorted[3])
    assert app.model.export_settings() == before and app.model.result is not None


@pytest.mark.xfail(strict=True, reason="emtk gap: the wheel never reaches an implot inside a DockManager window; see REPORT.md section 10")
def test_the_wheel_zooms_the_drift_trace(app, drv, tiff):
    measured(app, drv, tiff)
    drv.click_text("Drift trace")
    drv.draw(3)
    before = numeric_ticks(drv.draw(2))
    x, y, w, h = app.item_rects["Drift trace"]
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert numeric_ticks(drv.draw(2)) != before


@pytest.mark.xfail(strict=True, reason="emtk gap: the wheel does not reach a spin field inside a DockManager window; see REPORT.md section 10")
def test_the_wheel_over_the_smoothing_field_steps_it(app, drv):
    drv.click("Estimator.fold")
    x, y, w, h = drv.rect("smooth")
    drv.wheel(x + w * 0.3, y + h / 2, 1)
    assert app.model.smooth == pytest.approx(3.0)


def test_the_wheel_scrolls_the_settings_window_when_the_form_is_taller_than_it(app):
    drv = Driver(app, (800, 200))
    drv.draw(3)
    top = app.form.rects["measure"][1]
    drv.click("Estimator.fold")
    drv.wheel(150, 150, -5)
    assert app.form.rects["measure"][1] < top
    drv.wheel(150, 150, 8)
    assert app.form.rects["measure"][1] == top


# ── 8. guide, help, persistence, host ──────────────────────────────────────────────────────────────────────── #


def test_help_button_opens_the_help_and_its_buttons_work(app, drv):
    drv.click("help")
    assert app.help_window.open
    assert {"Start Guided Tour", "Close"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not app.help_window.open and app.tour.active
    app.tour.stop()
    drv.click("help")
    drv.escape()
    assert not app.help_window.open


def test_guide_button_starts_the_tour_and_close_tour_ends_it(app):
    drv = Driver(app, BIG)  # the card is clear of the form here; see the xfail below for the overlapping case
    drv.click("guide")
    assert app.tour.active
    drv.click_text("Close Tour")
    assert not app.tour.active


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(app, tiff):
    drv = Driver(app, BIG)
    drv.click("guide")
    guard = 0
    while app.tour.active and guard < 30:
        guard += 1
        drv.draw(2)
        step = app.tour.steps[app.tour.step_idx]
        target = step.get("target") or {}
        if app.tour.awaiting:
            if target.get("attr") == "filename":
                drv.type_into("filename", str(tiff))
                drv.settle()
            elif target.get("name") == "computed":
                drv.click("measure")
                drv.settle()
            drv.draw(2)
            assert not app.tour.awaiting, f"{step['title']}: operating the control did not release the step"
        drv.click_text("Finish ✓" if app.tour.step_idx == len(app.tour.steps) - 1 else "Next ►", last=True)
    assert not app.tour.active and app.model.result is not None


def test_a_file_chosen_in_the_dialog_also_releases_the_load_step(app, tiff):
    drv = Driver(app, BIG)
    app.model.folder = str(tiff.parent)
    drv.click("guide")
    app.tour.next()
    drv.draw(2)
    assert app.tour.awaiting
    drv.click("open_file")
    drv.click_text("drift.tif")
    drv.click_text("Open", last=True)
    drv.settle()
    assert not app.tour.awaiting


def test_every_guide_target_is_a_drawn_control_or_window(app, drv, tiff):
    seen = set()
    for index, step in enumerate(app.tour.steps):
        target = step.get("target") or {}
        if not target:
            continue
        app.tour.start(index)
        key = app.tour._target_key(target)
        drv.draw(3)
        rect = app.tour.get_target_rect(key)
        if rect is None:
            measured(app, drv, tiff)
            drv.draw(3)
            app.tour.start(index)
            drv.draw(3)
            rect = app.tour.get_target_rect(key)
        assert rect and rect[2] > 0 and rect[3] > 0, f"{step['title']}: nothing drawn for {key!r}"
        seen.add(key)
    app.tour.stop()
    assert {"filename", "reference", "channel", "computed", "Drift trace", "Projection"} <= seen


def test_settings_round_trip_and_invalid_values_are_ignored(app, drv):
    app.model.reference, app.model.mode, app.model.smooth, app.model.subpixel = "mean", "constant", 3.5, True
    app.model.colormap, app.model.folder = "viridis", "/tmp"
    saved = json.loads(json.dumps(app.export_settings()))
    other = make_app()
    other.restore_settings(saved)
    assert other.export_settings() == saved and other.model.reference == "mean" and other.model.mode == "constant"
    other.restore_settings({"reference": "middle", "mode": "reflect", "smooth": "high", "subpixel": 3, "colormap": 4, "folder": 4})
    assert other.export_settings() == saved
    other.restore_settings(None)
    assert "filename" not in saved and "channel" not in saved


def test_the_imaging_hub_contract(app):
    app.apply_setup_settings({"detectors": {"a": {}}})
    app.apply_pipeline_context({"source": "/x/y.tif"})
    assert app.model.filename == ""  # the Qt drift tool adopted neither
    app.model.pipeline_sink = lambda *a, **k: None
    app.set_frame_request_callback(lambda: None)
    app.close()


def test_the_window_draws_empty_and_populated_at_both_sizes(app, drv, tiff):
    for size in ((1200, 800), (800, 600)):
        assert {"Settings", "Measure", "Export stack", "Export shifts", "Browse", "Database"} <= set(drv.draw(3, size).strings)
    measured(app, drv, tiff)
    for size in ((1200, 800), (800, 600)):
        assert any("Max drift 24.6 px" in s for s in drv.draw(3, size).strings)


def test_the_idle_window_does_not_ask_for_frames(app, drv):
    drv.draw(3)
    assert not app.job.busy and not app.picker.is_open


# ── 9. the spec, the tooltips, no Qt ───────────────────────────────────────────────────────────────────────── #


def test_every_spec_key_exists_on_the_model():
    model = make_app().model
    for section in walk(EMTK_SPEC["sections"]):
        options = section.get("options") if isinstance(section.get("options"), dict) else {}
        for name in (section.get("attr"), section.get("call"), section.get("options_source"), options.get("source")):
            if name:
                assert hasattr(model, name), (section.get("title"), name)
        for name in (section.get("call"), options.get("source")):
            if name:
                assert callable(getattr(model, name)), name
        for image in options.get("images", []):
            assert callable(getattr(model, image["source"]))
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        for column in options.get("columns", []):
            assert column["key"] in ("frame", "dx", "dy", "magnitude")


def test_every_qt_setting_is_in_the_emtk_spec_with_the_same_range():
    def values(sections):
        return {s["attr"]: s for s in walk(sections) if s.get("type") in ("value", "toggle", "choice") and s.get("attr")}

    qt, emtk = values(QT_SPEC["sections"]), values(EMTK_SPEC["sections"])
    assert set(qt) - {"filename"} == set(emtk) - {"filename"}, set(qt) ^ set(emtk)
    for attr, spec in qt.items():
        for key in ("minimum", "maximum", "decimals", "label", "options", "labels", "description"):
            assert spec.get(key) == emtk[attr].get(key), (attr, key)


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("img_drift"))
    assert inventory["controls_without_tooltip"] == []
    for section in walk(EMTK_SPEC["sections"]):
        if section.get("type") in ("value", "choice", "toggle", "custom", "panel", "button_row"):
            assert section.get("description"), section.get("attr") or section.get("title")
        options = section.get("options") if isinstance(section.get("options"), dict) else {}
        for column in options.get("columns", []):
            assert column.get("description"), column
        for image in options.get("images", []):
            assert image.get("description"), image
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_the_populated_window_has_a_tooltip_on_every_control_too(app, drv, tiff):
    from test.gui.emtk_port_parity import ControlRecorder

    measured(app, drv, tiff)
    missing = set()
    for tab in ("Drift trace", "Projection", "Shifts"):
        app.docks.focus(tab)
        recorder = ControlRecorder()
        with recorder.installed():
            for _ in range(3):
                recorder.rows.clear()
                drv.draw(1)
        missing |= {f"{r['kind']}: {r['label']}" for r in recorder.rows if not r["tooltip"]}
    assert sorted(missing) == [], sorted(missing)


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("img_drift")
    assert result["ok"], result["output"]
