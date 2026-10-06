"""The native FRC tool against the Qt tool it replaces: numbers, every action and every error path.

Hermetic: settings in a temporary folder, files in ``tmp_path``, no network (the database picker gets a stub client). References:
(a) what the Qt window showed on a Poisson-noise TIFF stack, a second stack and the real photon stream
(``okf/plugins/emtk-ports/img_frc/qt_values.json``, captured by ``scripts/capture_qt_populated.py`` before the port), (b) the Qt tool itself,
constructed offscreen and run on the same files, and (c) a written-out numpy split of the stack fed to the core's ring correlation, which does
not go through the shared view model.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fio.image import imwrite
from chisurf.core.fluorescence.imaging import frc as frc_mod
from chisurf.plugins.microscopy.imaging_emtk.testing import (
    Driver,
    dialog_open,
    hermetic_env,
    numeric_ticks,
    walk,
)
from chisurf.plugins.microscopy.img_frc import core
from chisurf.plugins.microscopy.img_frc.gui.app import ImgFrcApp, make_app

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
EVIDENCE = REPO / "okf/plugins/emtk-ports/img_frc"
QT_VALUES = json.loads((EVIDENCE / "qt_values.json").read_text(encoding="utf-8"))
QT_CSV = (EVIDENCE / "qt_frc.csv").read_text(encoding="utf-8")
QT_SPEC = json.loads((PLUGIN / "gui" / "frc.view.json").read_text(encoding="utf-8"))
EMTK_SPEC = json.loads((PLUGIN / "gui" / "frc_emtk.view.json").read_text(encoding="utf-8"))
HT3 = REPO / "test/data/clsm/PQ_Olympus_MFIS.ht3"
BIG = (1200, 800)

_make = importlib.util.spec_from_file_location(
    "frc_make_data", EVIDENCE / "scripts" / "make_data.py"
)
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
def stack_a(tmp_path):
    path = tmp_path / "a.tif"
    imwrite(path, _data.noisy_stack(seed=0))
    return path


@pytest.fixture
def stack_b(tmp_path):
    path = tmp_path / "b.tif"
    imwrite(path, _data.noisy_stack(seed=1))
    return path


def loaded(app, drv, path):
    """Choose *path* the way a person does (type it, Enter) and wait for the worker that reads its channels."""
    drv.type_into("filename", str(path))
    drv.settle()
    return app.model


def measure(app, drv, **settings):
    for k, v in settings.items():
        setattr(app.model, k, v)
    drv.click("measure")
    drv.settle()
    return app.model


def pick(drv, field, label):
    drv.click(field)
    assert label in drv.draw(1).strings, (field, label, drv.painter.strings[:80])
    drv.click_text(label, last=True)


def curve_of(model):
    r = model.result
    return (
        np.asarray(r.frequency),
        np.nan_to_num(np.asarray(r.correlation)),
        np.asarray(r.threshold),
    )


# ── 1. the numbers ──────────────────────────────────────────────────────────────────────────────────────────── #


def check(model, key):
    """The model's result equals what the Qt window showed in scenario *key*."""
    qt = QT_VALUES[key]
    assert model.status_line == qt["model_status"], key
    r = model.result
    assert (
        r.resolution == pytest.approx(qt["resolution"], rel=1e-12)
        and bool(r.crossed) == qt["crossed"]
        and r.unit == qt["unit"]
    )
    assert (
        r.criterion == qt["criterion_used"]
        and r.kind == qt["kind"]
        and r.n_frames == qt["n_frames"]
    )
    np.testing.assert_allclose(r.frequency, qt["frequency"], rtol=1e-12)
    np.testing.assert_allclose(
        np.nan_to_num(r.correlation), qt["correlation"], rtol=1e-12, atol=1e-12
    )
    np.testing.assert_allclose(r.threshold, qt["threshold"], rtol=1e-12)
    assert [int(c) for c in r.counts] == qt["counts"]
    assert model.summary_html() == qt["summary"]


def test_measure_gives_the_numbers_the_qt_window_showed_for_even_odd_frames_in_pixels(
    app, drv, stack_a
):
    m = loaded(app, drv, stack_a)
    assert (
        m.status_line
        == QT_VALUES["tiff_loaded"]["model_status"]
        == "40 frames, 1 channel(s), 96x96 px (image)."
    )
    measure(app, drv)
    check(m, "tiff_even_odd")
    assert m.status_line == "Resolution 4.292 px (fixed_1/7)."


def test_the_calibrated_and_the_other_criteria_give_the_qt_numbers(app, drv, stack_a):
    loaded(app, drv, stack_a)
    check(measure(app, drv, pixel_size_nm=25.0), "tiff_25nm")
    for crit in ("half_bit", "two_sigma"):
        check(measure(app, drv, criterion=crit), f"criterion_{crit}")
    app.model.criterion = "fixed_1/7"
    check(measure(app, drv, split="halves"), "tiff_halves")
    app.model.split = "even_odd"
    check(measure(app, drv, bin_width=0.02, smooth=5), "tiff_binwidth_smooth")


def test_two_files_give_the_qt_numbers(app, drv, stack_a, stack_b):
    loaded(app, drv, stack_a)
    app.model.pixel_size_nm = 25.0
    drv.type_into("second_filename", str(stack_b))
    assert Path(app.model.second_filename) == stack_b
    check(measure(app, drv, split="two_files"), "two_files")


@pytest.mark.skipif(not HT3.exists(), reason="CLSM test data not present")
def test_the_real_photon_stream_gives_the_qt_numbers_for_both_splits(app, drv):
    m = loaded(app, drv, HT3)
    assert m.channel_names == ["ch0", "ch1", "ch4", "ch5"]
    check(
        measure(app, drv, pixel_size_nm=25.0), "photon_even_odd"
    )  # the Qt capture ran with the 25 nm calibration still set
    m.channel, m.channel_2 = "ch0", "ch1"
    check(measure(app, drv, split="channels"), "photon_channels")


def test_the_result_equals_a_written_out_split_fed_to_the_core_ring_correlation(app, drv, stack_a):
    """No view model, no ``core.halves``: numpy sums of the even and odd frames and the core's ring correlation."""
    frames = np.asarray(_data.noisy_stack(seed=0), dtype=np.float64)
    curve = frc_mod.frc_curve(
        frames[0::2].sum(0), frames[1::2].sum(0), bin_width=None, pixel_size=None
    )
    expected = frc_mod.resolve(curve, "fixed_1/7", smooth=3)
    m = loaded(app, drv, stack_a)
    measure(app, drv)
    assert m.result.resolution == pytest.approx(expected.resolution, rel=1e-9)
    np.testing.assert_allclose(
        np.nan_to_num(m.result.correlation), np.nan_to_num(curve.correlation), rtol=1e-12
    )
    assert m.result.counts.tolist() == np.asarray(curve.counts).tolist()


def test_the_halves_shown_are_the_two_independent_images(app, drv, stack_a):
    m = loaded(app, drv, stack_a)
    measure(app, drv)
    frames = np.asarray(_data.noisy_stack(seed=0), dtype=np.float64)
    np.testing.assert_allclose(m.half_1_image(), frames[0::2].sum(0))
    np.testing.assert_allclose(m.half_2_image(), frames[1::2].sum(0))
    assert not np.array_equal(m.half_1_image(), m.half_2_image())


def test_the_ring_table_shows_what_the_qt_table_showed(app, drv, stack_a):
    m = loaded(app, drv, stack_a)
    measure(app, drv)
    qt_rows = QT_VALUES["tiff_even_odd"]["ring_rows"]
    shown = [
        {
            "frequency": f"{r['frequency']:.5g}",
            "period": f"{r['period']:.4g}",
            "correlation": f"{r['correlation']:.4f}",
            "threshold": f"{r['threshold']:.4f}",
            "pixels": r["pixels"],
        }
        for r in m.ring_table_rows()
    ]
    assert shown == [{k: v for k, v in row.items() if k != "_unit"} for row in qt_rows]
    drv.click_text("Rings")
    assert {"Period", "FRC", "Threshold"} <= {s for s in drv.draw(2).strings}


# ── 2. the live Qt tool on the same files ──────────────────────────────────────────────────────────────────── #


@pytest.fixture(scope="module")
def qt_tool():
    """The legacy Qt tool, offscreen, on temporary settings. Skipped only when Qt is not installed."""
    if importlib.util.find_spec("qtpy") is None:
        pytest.skip("Qt is not installed")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy import QtWidgets

    from chisurf.plugins.microscopy.img_frc.gui.tool import ImgFrcTool

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tool = ImgFrcTool()
    tool._qapp = qapp
    yield tool
    tool.close()


def qt_measure(tool, path, second=None, **settings):
    """What the Qt window computes for *path* (the compute runs inline here)."""
    m = tool.model
    m.split, m.criterion, m.pixel_size_nm, m.bin_width, m.smooth, m.axis_order = (
        "even_odd",
        "fixed_1/7",
        0.0,
        0.0,
        3,
        "auto",
    )
    m.channel, m.channel_2, m.second_filename = 0, "", ""
    assert m.set_filename(str(path))
    if second:
        m.set_second_filename(str(second))
    for k, v in settings.items():
        setattr(m, k, v)
    ok = m.compute()
    tool._on_finished(ok)
    tool._refresh()
    return m


def qt_table_cells(tool):
    from qtpy import QtWidgets

    table = next(t for t in tool.findChildren(QtWidgets.QTableWidget) if t.columnCount() == 5)
    return [[table.item(r, c).text() for c in range(5)] for r in range(table.rowCount())]


SCENARIOS = {
    "defaults": {},
    "calibrated": {"pixel_size_nm": 25.0},
    "half-bit": {"criterion": "half_bit"},
    "2 sigma": {"criterion": "two_sigma", "pixel_size_nm": 40.0},
    "first / second half": {"split": "halves"},
    "ring width and smoothing": {"bin_width": 0.03, "smooth": 7},
    "no smoothing": {"smooth": 1},
    "two files": {"split": "two_files", "pixel_size_nm": 25.0},
}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_the_qt_tool_and_the_emtk_app_agree_on_every_result(
    app, drv, qt_tool, stack_a, stack_b, scenario
):
    settings = SCENARIOS[scenario]
    qt = qt_measure(
        qt_tool, stack_a, stack_b if settings.get("split") == "two_files" else None, **settings
    )
    m = loaded(app, drv, stack_a)
    if settings.get("split") == "two_files":
        drv.type_into("second_filename", str(stack_b))
    measure(app, drv, **settings)
    assert m.status_line == qt_tool.statusBar().currentMessage() == qt.status
    for a, b in zip(curve_of(m), curve_of(qt)):
        np.testing.assert_array_equal(a, b)
    assert m.result.resolution == qt.result.resolution and m.result.crossed == qt.result.crossed
    np.testing.assert_array_equal(m.half_1_image(), qt.half_1_image())
    np.testing.assert_array_equal(m.half_2_image(), qt.half_2_image())
    assert m.summary_html() == qt.summary_html()
    assert [s["name"] for s in m.frc_series()] == [s["name"] for s in qt.frc_series()]
    for a, b in zip(m.frc_series(), qt.frc_series()):
        np.testing.assert_array_equal(a["y"], b["y"])
    cells = [
        [
            f"{r['frequency']:.5g}",
            f"{r['period']:.4g}",
            f"{r['correlation']:.4f}",
            f"{r['threshold']:.4f}",
            str(r["pixels"]),
        ]
        for r in m.ring_table_rows()
    ]
    assert cells == qt_table_cells(qt_tool)


@pytest.mark.skipif(not HT3.exists(), reason="CLSM test data not present")
def test_the_qt_tool_and_the_emtk_app_agree_on_the_photon_stream_and_the_channel_split(
    app, drv, qt_tool
):
    qt = qt_measure(qt_tool, HT3)
    m = loaded(app, drv, HT3)
    measure(app, drv)
    np.testing.assert_array_equal(curve_of(m)[1], curve_of(qt)[1])
    assert m.status_line == qt.status and m.channel_names == qt.channel_names
    qt = qt_measure(qt_tool, HT3, split="channels", channel="ch0", channel_2="ch1")
    measure(app, drv, split="channels", channel="ch0", channel_2="ch1")
    np.testing.assert_array_equal(curve_of(m)[1], curve_of(qt)[1])
    assert m.status_line == qt.status


@pytest.mark.skipif(not HT3.exists(), reason="CLSM test data not present")
def test_the_hub_setup_payload_names_the_detector_windows_as_the_qt_tool_did(app, drv, qt_tool):
    payload = {"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}}
    qt = qt_tool.model
    qt.detectors = {}
    qt.set_filename(str(HT3))
    qt.apply_setup_settings(payload)
    loaded(app, drv, HT3)
    app.apply_setup_settings(payload)
    drv.settle()
    assert app.model.channel_names == qt.channel_names and set(app.model.channel_names) >= {
        "green",
        "red",
    }
    qt.detectors = {}


@pytest.mark.parametrize("attr", ["pixel_size_nm", "bin_width", "smooth"])
def test_typed_extremes_are_clamped_to_the_range_the_qt_spin_box_enforced(app, drv, qt_tool, attr):
    from qtpy import QtWidgets

    from chisurf.gui.autoform.sections.builtin import ValueWidget

    editor = {
        vw._section.attr: vw.editor
        for vw in qt_tool.findChildren(ValueWidget)
        if getattr(vw, "_section", None)
    }[attr]
    drv.click("Estimator.fold") if attr != "pixel_size_nm" else None
    whole = isinstance(editor, QtWidgets.QSpinBox)
    for qt_value in (1_000_000, -5):
        editor.setValue(qt_value if whole else float(qt_value))
        drv.type_into(attr, str(qt_value))
        assert getattr(app.model, attr) == pytest.approx(editor.value()), (attr, qt_value)


# ── 3. choosing files: typed, Browse, Database, drops ──────────────────────────────────────────────────────── #


def test_choosing_a_file_reads_its_channels_and_does_not_measure(app, drv, stack_a):
    m = loaded(app, drv, stack_a)
    assert (
        Path(m.filename) == stack_a
        and m.channel_names == ["ch0"]
        and m.channel == "ch0"
        and m.result is None
    )
    assert m.status_line == QT_VALUES["tiff_loaded"]["model_status"]


def test_a_typed_path_is_taken_on_enter_and_on_click_away_but_not_before(app, drv, stack_a):
    drv.type_into("filename", str(stack_a), enter=False)
    assert app.model.filename == ""
    drv.click("pixel_size_nm", fx=0.3)
    drv.settle()
    assert Path(app.model.filename) == stack_a and app.model.channel_names == ["ch0"]


def test_browse_opens_the_dialog_and_a_chosen_file_is_loaded(app, drv, stack_a):
    app.model.folder = str(stack_a.parent)
    drv.click("open_file")
    assert (
        dialog_open(drv)
        and app.dialog.title == "Open image"
        and "Open image" in drv.draw(1).strings
    )
    drv.click_text("a.tif")
    drv.click_text("Open", last=True)
    drv.settle()
    assert (
        Path(app.model.filename) == stack_a
        and app.model.folder == str(stack_a.parent)
        and not dialog_open(drv)
    )


def test_browse_cancel_the_window_close_button_and_escape_change_nothing(app, drv, stack_a):
    app.model.folder = str(stack_a.parent)
    drv.click("open_file")
    drv.click_text("Cancel")
    assert not dialog_open(drv) and app.model.filename == ""
    drv.click("open_file")
    drv.click_text("×")
    assert not dialog_open(drv)
    drv.click("open_file")
    drv.hover(500, 350)
    drv.escape()
    assert not dialog_open(drv) and app.model.filename == "" and not app.job.busy


def test_the_second_file_is_typed_browsed_and_clicked_away(app, drv, stack_a, stack_b):
    drv.type_into("second_filename", str(stack_b), enter=False)
    assert app.model.second_filename == ""
    drv.click("pixel_size_nm", fx=0.3)
    assert (
        Path(app.model.second_filename) == stack_b and app.model.status_line == "Second file: b.tif"
    )
    app.model.second_filename = ""
    app.model.folder = str(stack_b.parent)
    drv.click("open_second_file")
    assert dialog_open(drv) and app.dialog.title == "Open second image"
    drv.click_text("b.tif")
    drv.click_text("Open", last=True)
    assert Path(app.model.second_filename) == stack_b and not dialog_open(drv)


class FakeClient:
    """A database client that lists one dataset and resolves it to a local file."""

    def __init__(self, path):
        self.path = str(path)

    def call(self, method, params=None):
        if method == "mmfdb.datasets.browse":
            return {
                "datasets": [
                    {
                        "artifact_id": "a1",
                        "artifact_kind": "raw_data",
                        "data_format": "tif",
                        "original_filename": "stored.tif",
                    }
                ],
                "total": 1,
            }
        if method == "mmfdb.datasets.open":
            return {"local_path": self.path}
        raise AssertionError(method)


def open_picker(app, drv, button, path):
    import time

    app.picker.client = FakeClient(path)
    drv.click(button)
    drv.draw(2)
    assert app.picker.is_open
    end = time.monotonic() + 10
    while "stored.tif [raw_data] (tif)" not in drv.draw(1).strings and time.monotonic() < end:
        time.sleep(0.02)
    drv.click_text("stored.tif [raw_data] (tif)")
    assert app.picker.selection is not None


def test_the_database_buttons_pick_the_first_and_the_second_acquisition(app, drv, stack_a, stack_b):
    open_picker(app, drv, "open_database", stack_a)
    assert (
        app.picker.accept()
    )  # the picker's own accept: what the "Open selected" button would call (see the xfail below)
    drv.settle()
    assert Path(app.model.filename) == stack_a and app.model.channel_names == ["ch0"]
    open_picker(app, drv, "open_second_database", stack_b)
    assert app.picker.accept()
    assert Path(app.model.second_filename) == stack_b and Path(app.model.filename) == stack_a


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the dataset picker's buttons share one id ('...##dataset') and its Open selected / Cancel "
    "never fire; see REPORT.md section 10",
)
def test_the_open_selected_button_of_the_database_picker_can_be_pressed(app, drv, stack_a):
    import time

    open_picker(app, drv, "open_database", stack_a)
    drv.click_text("Open selected")
    end = time.monotonic() + 5
    while app.picker.is_open and time.monotonic() < end:
        time.sleep(0.02)
        drv.draw(1)
    assert not app.picker.is_open


def test_the_database_picker_window_close_button_closes_it(app, drv, stack_a):
    open_picker(app, drv, "open_database", stack_a)
    drv.click_text("×")
    assert not app.picker.is_open and app.model.filename == ""


def test_a_drop_loads_the_first_file_and_with_the_two_file_split_the_second_one(
    app, drv, stack_a, stack_b
):
    assert drv.drop(stack_a) is True
    drv.settle()
    assert Path(app.model.filename) == stack_a and app.model.second_filename == ""
    app.model.split = "two_files"
    assert drv.drop(stack_b) is True
    assert (
        Path(app.model.second_filename) == stack_b and Path(app.model.filename) == stack_a
    )  # routed by what is missing
    app.model.filename, app.model.second_filename = "", ""
    assert drv.drop(stack_a, stack_b) is True
    drv.settle()
    assert Path(app.model.filename) == stack_a and Path(app.model.second_filename) == stack_b
    assert app.files_dropped([]) is False


def test_dropping_while_a_worker_runs_is_refused(app, drv, stack_a):
    app.model.open_path(str(stack_a))
    assert app.job.busy and app.files_dropped([str(stack_a)]) is False
    drv.settle()


def test_the_qt_host_delivers_a_dropped_file_to_the_app(app, stack_a):
    pytest.importorskip("qtpy")
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui, QtWidgets

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    host = ControlHost(app)
    host.resize(900, 600)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(stack_a))])
    enter = QtGui.QDragEnterEvent(
        QtCore.QPoint(10, 10),
        QtCore.Qt.CopyAction,
        mime,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    host.dragEnterEvent(enter)
    assert enter.isAccepted()
    host.dropEvent(
        QtGui.QDropEvent(
            QtCore.QPointF(10, 10),
            QtCore.Qt.CopyAction,
            mime,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
    )
    assert Path(app.model.filename) == stack_a and qapp is not None
    host.close()


# ── 4. errors ──────────────────────────────────────────────────────────────────────────────────────────────── #


def test_measure_with_nothing_loaded_says_why_where_the_qt_bar_said_only_measurement_failed(
    app, drv
):
    drv.click("measure")
    assert app.model.status_line == QT_VALUES["empty_measure"]["model_status"] == "No image loaded."
    assert QT_VALUES["empty_measure"]["status"] == "Measurement failed" and not app.job.busy
    assert "No image loaded." in drv.strings()


@pytest.mark.parametrize(
    "key,settings",
    [
        ("two_files_without_second", {"split": "two_files"}),
        ("channels_on_one_channel_tiff", {"split": "channels"}),
        ("tiff_axis_channels", {"axis_order": "channels"}),
    ],
)
def test_a_split_that_cannot_be_made_reports_the_qt_reason(app, drv, stack_a, key, settings):
    loaded(app, drv, stack_a)
    measure(app, drv, **settings)
    assert app.model.status_line == QT_VALUES[key]["model_status"] and app.model.result is None
    assert QT_VALUES[key]["model_status"] in " ".join(
        drv.strings()
    )  # the status line shows it, wrapped


def test_an_unknown_channel_name_reports_the_qt_reason(app, drv, stack_a):
    loaded(app, drv, stack_a)
    measure(app, drv, axis_order="frames", split="channels", channel_2="ch1")
    assert app.model.status_line == QT_VALUES["tiff_axis_frames_channel_split"]["model_status"]


def test_a_corrupt_a_one_frame_and_a_missing_file_report_the_qt_reasons(app, drv, tmp_path):
    bad = tmp_path / "bad.tif"
    bad.write_bytes(b"not a tiff")
    drv.type_into("filename", str(bad))
    drv.settle()
    assert app.model.status_line == "No image loaded." or app.model.status_line.startswith(
        "Could not read the image"
    )
    measure(app, drv)
    assert (
        app.model.status_line.startswith("FRC failed: could not read image")
        and app.model.result is None
    )
    one = tmp_path / "one.tif"
    imwrite(one, np.ones((32, 32), dtype=np.float32))
    drv.type_into("filename", str(one))
    drv.settle()
    measure(app, drv)
    assert app.model.status_line == QT_VALUES["one_frame"]["model_status"]
    app.model.filename = str(tmp_path / "missing.tif")
    measure(app, drv)
    assert app.model.status_line.startswith("FRC failed: no such file") and app.model.result is None


def test_a_new_file_clears_the_previous_result(app, drv, stack_a, stack_b):
    loaded(app, drv, stack_a)
    measure(app, drv)
    assert app.model.result is not None
    drv.type_into("filename", str(stack_b))
    drv.settle()
    assert (
        app.model.result is None
        and app.model.ring_table_rows() == []
        and app.model.frc_series() == []
    )


def test_the_actions_and_the_form_are_greyed_while_a_worker_runs(app, drv, stack_a):
    app.model.open_path(str(stack_a))
    assert app.job.busy
    runs = []
    app.model.measure = lambda: runs.append(1)
    drv.click("measure")
    assert runs == []
    drv.click("split")
    assert "Two files" not in drv.draw(1).strings
    drv.settle()


def test_a_worker_that_raises_is_reported_not_swallowed(app, drv, stack_a, monkeypatch):
    loaded(app, drv, stack_a)

    def boom(*a, **k):
        raise RuntimeError("fft exploded")

    monkeypatch.setattr(core, "analyse", boom)
    drv.click("measure")
    drv.settle()
    assert "fft exploded" in app.model.status_line and app.model.result is None


# ── 5. the settings ────────────────────────────────────────────────────────────────────────────────────────── #


def test_the_split_list_offers_the_four_qt_splits_and_each_is_picked(app, drv):
    for label, value in (
        ("First / second half", "halves"),
        ("Two channels", "channels"),
        ("Two files", "two_files"),
        ("Even / odd frames", "even_odd"),
    ):
        pick(drv, "split", label)
        assert app.model.split == value
        assert label in drv.draw(2).strings


def test_the_criterion_list_offers_the_three_criteria(app, drv):
    for label, value in (("½-bit", "half_bit"), ("2σ", "two_sigma"), ("Fixed 1/7", "fixed_1/7")):
        pick(drv, "criterion", label)
        assert app.model.criterion == value


def test_the_axis_order_list_offers_the_three_qt_readings(app, drv):
    drv.click("Estimator.fold")
    for label, value in (
        ("All planes are frames", "frames"),
        ("Leading axis is channels", "channels"),
        ("Auto", "auto"),
    ):
        pick(drv, "axis_order", label)
        assert app.model.axis_order == value


def test_the_channel_lists_name_the_channels_and_the_second_one_offers_the_next_channel(app, drv):
    if not HT3.exists():
        pytest.skip("CLSM test data not present")
    m = loaded(app, drv, HT3)
    drv.click("channel")
    assert {"ch0", "ch1", "ch4", "ch5"} <= set(drv.draw(1).strings)
    drv.click_text("ch1", last=True)
    assert m.channel == "ch1"
    drv.click("channel_2")
    shown = drv.draw(1).strings
    assert {"next channel", "ch4"} <= set(shown)
    drv.click_text("ch4", last=True)
    assert m.channel_2 == "ch4"
    drv.click("channel_2")
    drv.click_text("next channel", last=True)
    assert m.channel_2 == ""
    measure(app, drv, split="channels")  # ch1 against the next channel, ch4: the Qt default
    expected = core.analyse(str(HT3), split="channels", channel="ch1")
    assert m.result.resolution == expected.resolution


def test_escape_closes_an_open_list_without_choosing(app, drv):
    drv.click("split")
    assert "Two files" in drv.draw(1).strings
    drv.escape()
    assert app.model.split == "even_odd"


def test_the_numeric_fields_take_typed_values_and_their_arrows_step_by_the_qt_steps(app, drv):
    drv.click("Estimator.fold")
    x, y, w, h = drv.rect("pixel_size_nm.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.pixel_size_nm == pytest.approx(1.0)
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    assert app.model.pixel_size_nm == 0.0  # the Qt minimum
    x, y, w, h = drv.rect("smooth.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.smooth == 4
    for _ in range(5):
        drv.click_at(x + w / 2, y + h * 0.75)
    assert app.model.smooth == 1
    x, y, w, h = drv.rect("bin_width.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.bin_width == pytest.approx(
        0.5
    )  # a step of 1.0 clamps to the Qt maximum of 0.5
    drv.type_into("bin_width", "0.0125")
    assert app.model.bin_width == 0.0125
    drv.type_into("pixel_size_nm", "33.333")
    assert app.model.pixel_size_nm == 33.33  # two decimals, as the Qt box


def test_changing_a_setting_does_not_re_measure_by_itself_as_in_the_qt_tool(app, drv, stack_a):
    loaded(app, drv, stack_a)
    measure(app, drv)
    before = app.model.status_line
    pick(drv, "criterion", "½-bit")
    assert (
        not app.job.busy
        and app.model.status_line == before
        and app.model.result.criterion == "fixed_1/7"
    )
    drv.click("measure")
    drv.settle()
    assert app.model.result.criterion == "half_bit"


# ── 6. export ────────────────────────────────────────────────────────────────────────────────────────────── #


def test_export_without_a_result_says_so(app, drv):
    drv.click("request_export")
    assert app.model.status_line == QT_VALUES["empty_export"][
        "status"
    ] == "Nothing to export yet" and not dialog_open(drv)


def test_export_csv_writes_the_file_the_qt_tool_wrote(app, drv, stack_a, tmp_path):
    loaded(app, drv, stack_a)
    measure(app, drv, pixel_size_nm=25.0)
    drv.click("request_export")
    painter = drv.draw(2)
    assert (
        dialog_open(drv)
        and app.dialog.title == "Export FRC curve"
        and "frc_resolution.csv" in painter.strings
    )
    drv.click_text("Save", last=True)
    written = tmp_path / "frc_resolution.csv"
    assert written.read_text() == QT_CSV
    assert app.model.status_line == f"Wrote {written}" and not dialog_open(drv)


def test_export_to_a_typed_name_cancel_and_an_unwritable_place(app, drv, stack_a, tmp_path):
    loaded(app, drv, stack_a)
    measure(app, drv)
    drv.click("request_export")
    drv.draw(2)
    drv.click_text("Cancel")
    assert not list(tmp_path.glob("*.csv")) and not dialog_open(drv)
    drv.click("request_export")
    drv.draw(2)
    drv.click_at(*[v + o for v, o in zip(drv.text_rect("frc_resolution.csv")[:2], (30, 6))])
    assert app.io.want_capture_keyboard
    drv.select_all()
    drv.type_text("mine")
    drv.click_text("Save", last=True)
    assert (
        (tmp_path / "mine.csv")
        .read_text()
        .startswith("frequency_1/px,correlation,threshold,ring_pixels")
    )
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    app.model.write_export(str(blocker / "x.csv"))
    assert app.model.status_line.startswith("Could not write") and "Could not write" in " ".join(
        drv.strings()
    )


# ── 7. the views ─────────────────────────────────────────────────────────────────────────────────────────── #


def test_every_view_says_what_to_do_before_there_is_a_result(app, drv):
    assert any(s.startswith("Press Measure: the correlation") for s in drv.draw(2).strings)
    drv.click_text("Halves")
    assert any(s.startswith("Measure a file") for s in drv.draw(2).strings)
    drv.click_text("Rings")
    strings = drv.draw(2).strings
    assert (
        "Rings" in strings
        and app.model.ring_table_rows() == []
        and not {"Period", "Ring px"} - set(strings)
    )


def test_the_resolution_window_and_the_curve_are_drawn_after_a_measurement(app, drv, stack_a):
    loaded(app, drv, stack_a)
    measure(app, drv, pixel_size_nm=25.0)
    strings = set(drv.draw(3).strings)
    assert {
        "Resolution",
        "FRC",
        "correlation",
        "spatial frequency (1/nm or 1/px)",
        "threshold (fixed_1/7)",
        "resolution",
    } <= strings
    assert "107.3 nm" in strings and any(
        s.startswith("Criterion fixed_1/7, crossing at") for s in strings
    )
    for tab, expect in (
        ("Halves", {"Half 1", "Half 2", "Colormap", "Reset view"}),
        ("Rings", {"Rings", "Period", "FRC", "Threshold"}),
    ):
        drv.click_text(tab)
        assert expect <= set(drv.draw(2).strings), tab


def test_no_crossing_is_reported_as_an_answer_not_an_error(app, drv, tmp_path):
    flat = tmp_path / "flat.tif"
    imwrite(
        flat, np.stack([_data.object_image() * 100 + k * 0.0 for k in range(6)]).astype(np.float32)
    )
    loaded(app, drv, flat)
    measure(app, drv)
    assert app.model.result is not None and not app.model.result.crossed
    assert app.model.status_line == "The FRC never crosses its threshold — see the help."
    assert any("No crossing." in s for s in drv.draw(2).strings)


def test_the_two_halves_share_one_colormap_as_the_qt_docks_did(app, drv, stack_a):
    loaded(app, drv, stack_a)
    measure(app, drv)
    drv.click_text("Halves")
    drv.draw(2)
    combos = [t[:4] for t in drv.draw(1).texts if t[5] == "inferno"]
    assert len(combos) == 2
    x, y, w, h = combos[1]
    drv.click_at(x + 10, y + h / 2)
    drv.click_text("gray", last=True)
    assert app.model.colormap == "gray" and [t[5] for t in drv.draw(2).texts].count("gray") == 2


def test_a_drag_pans_the_curve_and_a_new_result_refits_the_view(app, drv, stack_a):
    loaded(app, drv, stack_a)
    measure(app, drv, pixel_size_nm=25.0)
    drv.draw(3)
    x, y, w, h = app.item_rects["FRC"]
    original = numeric_ticks(drv.draw(2))
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.4))
    assert numeric_ticks(drv.draw(2)) != original
    measure(
        app, drv, pixel_size_nm=50.0
    )  # a different calibration: the frequency axis changes, the panned view must not hide it
    drv.draw(3)
    ticks = numeric_ticks(drv.draw(2))
    assert (
        ticks != original
        and any(t in ticks for t in ("0.2", "0.4", "0.6", "0.8", "1", "0"))
        and "0.2" in ticks
    )


def test_a_drag_pans_a_half_image_and_reset_view_restores_it(app, drv, stack_a):
    loaded(app, drv, stack_a)
    measure(app, drv)
    drv.click_text("Halves")
    drv.draw(3)
    bx, by, bw, bh = app.item_rects["half_1.image"]
    original = numeric_ticks(drv.draw(2))
    drv.drag((bx + bw * 0.5, by + bh * 0.5), (bx + bw * 0.3, by + bh * 0.3))
    assert numeric_ticks(drv.draw(2)) != original
    drv.click_text("Reset view")
    assert numeric_ticks(drv.draw(3)) == original


def table_values(drv, expect):
    return [t[5] for t in drv.draw(2).texts if t[5] in expect]


def test_the_ring_table_header_sorts_by_value_and_a_row_click_changes_nothing(app, drv, stack_a):
    loaded(app, drv, stack_a)
    measure(app, drv)
    drv.click_text("Rings")
    checks = {f"{r['correlation']:.4f}" for r in app.model.ring_table_rows()}
    unsorted = table_values(drv, checks)
    assert len(unsorted) >= 10

    def header():
        return [t[:4] for t in drv.draw(1).texts if t[5].endswith("FRC")][
            -1
        ]  # the table header, drawn after the plot window's tab

    drv.click(header())
    ascending = table_values(drv, checks)
    assert ascending == sorted(ascending, key=float) and ascending != unsorted
    drv.click(header())
    descending = table_values(drv, checks)
    assert descending == sorted(descending, key=float, reverse=True)
    before = app.model.export_settings()
    drv.click_text(descending[3])
    assert app.model.export_settings() == before and app.model.result is not None


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the wheel never reaches an implot inside a DockManager window; see REPORT.md section 10",
)
def test_the_wheel_zooms_the_curve(app, drv, stack_a):
    loaded(app, drv, stack_a)
    measure(app, drv)
    drv.draw(3)
    before = numeric_ticks(drv.draw(2))
    x, y, w, h = app.item_rects["FRC"]
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert numeric_ticks(drv.draw(2)) != before


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the wheel does not reach a spin field inside a DockManager window; see REPORT.md section 10",
)
def test_the_wheel_over_the_pixel_size_field_steps_it(app, drv):
    x, y, w, h = drv.rect("pixel_size_nm")
    drv.wheel(x + w * 0.3, y + h / 2, 1)
    assert app.model.pixel_size_nm == pytest.approx(1.0)


def test_the_wheel_scrolls_the_settings_window_when_the_form_is_taller_than_it(app):
    drv = Driver(app, (800, 300))
    drv.draw(3)
    top = app.form.rects["measure"][1]
    drv.click("Estimator.fold")
    drv.wheel(150, 200, -5)
    assert app.form.rects["measure"][1] < top
    drv.wheel(150, 200, 8)
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
    drv = Driver(app, BIG)
    drv.click("guide")
    assert app.tour.active
    drv.click_text("Close Tour")
    assert not app.tour.active


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(
    app, stack_a
):
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
                drv.type_into("filename", str(stack_a))
                drv.settle()
            elif target.get("name") == "computed":
                drv.click("measure")
                drv.settle()
            drv.draw(2)
            assert not app.tour.awaiting, (
                f"{step['title']}: operating the control did not release the step"
            )
        drv.click_text(
            "Finish ✓" if app.tour.step_idx == len(app.tour.steps) - 1 else "Next ►", last=True
        )
    assert not app.tour.active and app.model.result is not None


def test_a_file_chosen_in_the_dialog_releases_the_load_step(app, stack_a):
    drv = Driver(app, BIG)
    app.model.folder = str(stack_a.parent)
    drv.click("guide")
    app.tour.next()
    drv.draw(2)
    assert app.tour.awaiting
    drv.click("open_file")
    drv.click_text("a.tif")
    drv.click_text("Open", last=True)
    drv.settle()
    assert not app.tour.awaiting


def test_every_guide_target_is_a_drawn_control_or_window(app, drv, stack_a):
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
            loaded(app, drv, stack_a)
            measure(app, drv)
            app.tour.start(index)
            drv.draw(3)
            rect = app.tour.get_target_rect(key)
        assert rect and rect[2] > 0 and rect[3] > 0, f"{step['title']}: nothing drawn for {key!r}"
        seen.add(key)
    app.tour.stop()
    assert {"filename", "split", "criterion", "computed", "FRC"} <= seen


def test_settings_round_trip_and_invalid_values_are_ignored(app, drv):
    m = app.model
    m.split, m.criterion, m.pixel_size_nm, m.bin_width, m.smooth, m.axis_order = (
        "two_files",
        "half_bit",
        12.5,
        0.02,
        9,
        "frames",
    )
    m.colormap, m.folder = "gray", "/tmp"
    saved = json.loads(json.dumps(app.export_settings()))
    other = make_app()
    other.restore_settings(saved)
    assert other.export_settings() == saved and other.model.split == "two_files"
    other.restore_settings(
        {
            "split": "thirds",
            "criterion": 1,
            "pixel_size_nm": "big",
            "smooth": 2.5,
            "axis_order": "x",
            "colormap": 4,
        }
    )
    assert other.export_settings() == saved
    other.restore_settings(None)
    assert not {"filename", "second_filename", "channel"} & set(saved)


def test_the_imaging_hub_adopts_its_source_as_the_qt_tool_did(app, drv, stack_a):
    app.apply_pipeline_context({"source": str(stack_a), "hdf5": "/x/y.h5"})
    drv.settle()
    assert (
        Path(app.model.filename) == stack_a
        and app.model.channel_names == ["ch0"]
        and app.model.pipeline_hdf5 == "/x/y.h5"
    )
    app.model.pipeline_sink = lambda *a, **k: None
    app.set_frame_request_callback(lambda: None)
    app.close()


def test_the_window_draws_empty_and_populated_at_both_sizes(app, drv, stack_a):
    for size in ((1200, 800), (800, 600)):
        assert {"Settings", "Measure", "Export CSV", "Browse", "Database", "Resolution"} <= set(
            drv.draw(3, size).strings
        )
    loaded(app, drv, stack_a)
    measure(app, drv)
    for size in ((1200, 800), (800, 600)):
        assert any(s.startswith("Criterion fixed_1/7") for s in drv.draw(3, size).strings)


def test_the_idle_window_does_not_ask_for_frames(app, drv):
    drv.draw(3)
    assert not app.job.busy and not app.picker.is_open


# ── 9. the spec, the tooltips, no Qt ───────────────────────────────────────────────────────────────────────── #


def options_of(section):
    return section["options"] if isinstance(section.get("options"), dict) else {}


def test_every_spec_key_exists_on_the_model():
    model = make_app().model
    for section in walk(EMTK_SPEC["sections"]):
        options = options_of(section)
        for name in (
            section.get("attr"),
            section.get("call"),
            section.get("options_source"),
            options.get("source"),
            section.get("source"),
        ):
            if name:
                assert hasattr(model, name), (section.get("title"), name)
        for name in (section.get("call"), options.get("source"), section.get("options_source")):
            if name and not isinstance(
                getattr(model, name), list
            ):  # channel_names is a property holding the list
                assert callable(getattr(model, name)), name
        for image in options.get("images", []):
            assert callable(getattr(model, image["source"]))
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        for column in options.get("columns", []):
            assert column["key"] in ("frequency", "period", "correlation", "threshold", "pixels")


def test_every_qt_setting_is_in_the_emtk_spec_with_the_same_range_and_choices():
    def values(sections):
        return {
            s["attr"]: s
            for s in walk(sections)
            if s.get("type") in ("value", "toggle", "choice") and s.get("attr")
        }

    qt, emtk = values(QT_SPEC["sections"]), values(EMTK_SPEC["sections"])
    assert set(qt) ^ set(emtk) == {
        "filename",
        "second_filename",
    }  # the Qt data-source sections are declared by options.attr
    for attr, spec in qt.items():
        if attr not in emtk:
            continue
        for key in ("minimum", "maximum", "decimals", "label", "options", "labels", "description"):
            if attr == "channel_2" and key == "options_source":
                continue
            assert spec.get(key) == emtk[attr].get(key), (attr, key)


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("img_frc"))
    assert inventory["controls_without_tooltip"] == []
    for section in walk(EMTK_SPEC["sections"]):
        if section.get("type") in (
            "value",
            "choice",
            "toggle",
            "custom",
            "panel",
            "button_row",
            "info",
        ):
            assert section.get("description"), section.get("attr") or section.get("title")
        for column in options_of(section).get("columns", []):
            assert column.get("description"), column
        for image in options_of(section).get("images", []):
            assert image.get("description"), image
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_the_populated_window_has_a_tooltip_on_every_control_too(app, drv, stack_a):
    from test.gui.emtk_port_parity import ControlRecorder

    loaded(app, drv, stack_a)
    measure(app, drv)
    missing = set()
    for tab in ("Halves", "Rings"):
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

    result = qt_free("img_frc")
    assert result["ok"], result["output"]
