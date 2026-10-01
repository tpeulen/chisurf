"""The native LUT Tools app against the Qt tool: numbers, plots, every control, no Qt.

Hermetic: every file is a temporary copy of the repository's BH SPC-130 sample, settings and
MMFDB point into a temporary folder, and nothing touches the user's ``~/.chisurf``. The Qt half
is the real ``TTRLutToolsWidget`` constructed offscreen; its plot curves, spin boxes, info label
and bridge result are the reference the native model is compared with.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import i18n, implot
from emtk.testing import PixelPainter, RecordingPainter

ROOT = Path(__file__).resolve().parents[5]
SPC = ROOT / "test/data/tttr/BH/132/BH_SPC132.spc"
GUI = Path(__file__).resolve().parents[1] / "gui"
SIZES = ((1200, 800), (800, 600))

pytestmark = pytest.mark.skipif(not SPC.is_file(), reason="sample SPC not available")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
@pytest.fixture
def env(tmp_path, monkeypatch):
    """Temporary settings, MMFDB and a private copy of the sample file."""
    for name, sub in (("CHISURF_SETTINGS_DIR", "settings"), ("MMFDB_SETTINGS_DIR", "mmfdb")):
        (tmp_path / sub).mkdir()
        monkeypatch.setenv(name, str(tmp_path / sub))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb" / "db.sqlite"))
    sample = tmp_path / "uniform.spc"
    shutil.copy(SPC, sample)
    i18n.set_locale("en")
    return {"dir": tmp_path, "spc": sample}


def make(env, **kwargs):
    from chisurf.plugins.tttr.tttr_lut_tools.gui.app import create_app

    return create_app(preferences_path=env["dir"] / "prefs.json", **kwargs)


def frames(app, size=SIZES[0], count=3):
    painter = None
    for _ in range(count):
        painter = RecordingPainter()
        app.draw(painter, 0.0, 0.0, float(size[0]), float(size[1]))
    return painter


def settle(app, size=SIZES[0]):
    """Draw until the model's jobs are finished (the way the real frame loop does)."""
    for _ in range(600):
        app.draw(RecordingPainter(), 0.0, 0.0, float(size[0]), float(size[1]))
        if not app.job.busy and not app.model.job_request and not app.model.dialog_request:
            return
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def load(app, env):
    app.model.add_files([str(env["spc"])])
    settle(app)
    return app.model


def click(app, name, size=SIZES[0]):
    """Press the control *name* the way a user does (hover, press, release)."""
    frames(app, size)
    x0, y0, w, h = app.form.rects[name]
    x, y = x0 + w / 2, y0 + h / 2
    app.hover(x, y)
    frames(app, size, 1)
    app.press(x, y)
    frames(app, size, 1)
    app.release()
    frames(app, size, 2)
    app.hover(size[0] - 5, size[1] / 2)
    frames(app, size, 1)


class FakeDialog:
    """Stands in for ``FileDialog``: it 'chooses' the next path as soon as it is drawn."""

    chosen: list = []
    made: list = []

    def __init__(self, title="", mode="open", filters=(), multiselect=False, **kwargs):
        self.mode, self.filters, self.multiselect = mode, filters, multiselect
        FakeDialog.made.append(self)

    def draw(self):
        return list(FakeDialog.chosen)


@pytest.fixture
def chooser(monkeypatch):
    from chisurf.plugins.tttr.tttr_lut_tools.gui import app as app_module

    FakeDialog.chosen, FakeDialog.made = [], []
    monkeypatch.setattr(app_module, "FileDialog", FakeDialog)
    return FakeDialog


@pytest.fixture(scope="module")
def qapp():
    qtpy = pytest.importorskip("qtpy")
    from qtpy.QtWidgets import QApplication

    _ = qtpy
    return QApplication.instance() or QApplication([])


@pytest.fixture
def qt_tool(qapp, env):
    """The real Qt tool with the sample loaded in tab 1."""
    from chisurf.plugins.tttr.tttr_lut_tools.gui import sections
    from chisurf.plugins.tttr.tttr_lut_tools.gui.tool import TTRLutToolsWidget

    widget = TTRLutToolsWidget()
    widget.tac_panel.model.load_files([str(env["spc"])])
    plots = widget.tac_panel.findChildren(sections._ComputePlotSection)[0]
    yield widget, plots
    widget.close()


# --------------------------------------------------------------------------- #
# 1. numbers equal the Qt widget's for the same file
# --------------------------------------------------------------------------- #
def qt_spins(widget):
    from qtpy import QtWidgets

    return sorted(
        float(w.value()) for w in widget.tac_panel.findChildren(QtWidgets.QAbstractSpinBox)
    )


def native_spins(model):
    return sorted(
        float(getattr(model, k))
        for k in (
            "linear_start",
            "linear_stop",
            "ntac_required",
            "noffset",
            "preview_photons",
            "seed",
            "threshold",
            "eps",
        )
    )


def test_loaded_state_equals_the_qt_widget(env, qt_tool):
    widget, plots = qt_tool
    app = make(env)
    model = load(app, env)
    qx, qy = plots._raw_curve.get_data()
    x, y, label = model.raw_plot()
    np.testing.assert_array_equal(x, qx)
    np.testing.assert_array_equal(y, qy)
    assert label == "Counts"
    after_x, after_y = plots._after_curve.get_data()
    native_x, native_y = model.corrected_plot()
    np.testing.assert_array_equal(native_x, after_x)
    np.testing.assert_array_equal(native_y, after_y)
    assert native_spins(model) == qt_spins(widget)
    assert model.info_text == widget.tac_panel.model.info_text()
    assert model.ws.compute.available_channels == widget.tac_panel.model.available_channels == [
        0,
        1,
        8,
        9,
    ]
    assert model.channel == widget.tac_panel.model.channel == "0"
    np.testing.assert_array_equal(
        model.ws.compute.current_table["NTAC_fract"],
        widget.tac_panel.model.current_table["NTAC_fract"],
    )


def test_hand_tuned_region_normalize_threshold_and_wrap_equal_the_qt_widget(env, qt_tool):
    widget, plots = qt_tool
    qt_model = widget.tac_panel.model
    app = make(env)
    model = load(app, env)
    for target in (qt_model, model):
        target.linear_start, target.linear_stop = 1200, 1900
        target.normalize = True
        target.threshold = 1.0
        target.mitigate_wrap = True
        target.ntac_required = 2048
    qt_model.compute()
    qt_model.notify("plot")
    model.param_changed()
    qx, qy = plots._raw_curve.get_data()
    x, y, label = model.raw_plot()
    np.testing.assert_array_equal(x, qx)
    np.testing.assert_allclose(y, qy)
    assert label == "Counts / ⟨region⟩"
    after = plots._after_curve.get_data()[1]
    np.testing.assert_array_equal(model.corrected_plot()[1], after)
    assert len(after) == 2048
    assert model.info_text == qt_model.info_text()
    np.testing.assert_array_equal(
        model.ws.compute.current_table["NTAC_fract"], qt_model.current_table["NTAC_fract"]
    )


def test_every_channel_selected_gives_the_qt_lut(env, qt_tool):
    widget, _ = qt_tool
    qt_model = widget.tac_panel.model
    app = make(env)
    model = load(app, env)
    for channel in model.ws.compute.available_channels:
        qt_model.channel = str(channel)
        qt_model.update()
        model.channel = str(channel)
        model.channel_changed()
        np.testing.assert_array_equal(
            model.ws.compute.current_table["NTAC_fract"], qt_model.current_table["NTAC_fract"]
        )
        assert model.info_text == qt_model.info_text()
        assert (model.linear_start, model.linear_stop) == (
            qt_model.linear_start,
            qt_model.linear_stop,
        )


def test_add_all_channels_gives_the_luts_the_qt_bridge_assigns(env, qt_tool):
    widget, _ = qt_tool
    widget._bridge_compute_to_assign()
    qt_luts = widget.settings_panel.channel_luts
    app = make(env)
    model = load(app, env)
    click(app, "add_all")
    settle(app)
    assert sorted(qt_luts) == sorted(model.ws.channel_luts) == [0, 1, 8, 9]
    for channel, lut in qt_luts.items():
        np.testing.assert_array_equal(model.ws.channel_luts[channel], lut)
    assert "channel(s) 0, 1, 8, 9" in model.message
    assert model.ws.selected_lut == "ch9_lut"
    assert sorted(model.ws.loaded_luts) == ["ch0_lut", "ch1_lut", "ch8_lut", "ch9_lut"]


def test_saved_lut_and_exported_corrected_files_equal_the_qt_ones(env, qt_tool, chooser):
    widget, _ = qt_tool
    qt_lut, qt_corr = env["dir"] / "qt_lut.npy", env["dir"] / "qt_corr.npy"
    widget.tac_panel.model.save_lut(str(qt_lut))
    widget.tac_panel.model.export_corrected(str(qt_corr))
    app = make(env)
    load(app, env)
    lut, corr = env["dir"] / "lut.npy", env["dir"] / "corr.npy"
    chooser.chosen = [str(lut)]
    click(app, "request_save_lut")
    assert "LUT saved to" in app.model.message
    chooser.chosen = [str(corr)]
    click(app, "request_export_corrected")
    settle(app)
    assert "Exported corrected micro-times" in app.model.message
    np.testing.assert_array_equal(np.load(lut), np.load(qt_lut))
    np.testing.assert_array_equal(np.load(corr), np.load(qt_corr))
    assert np.load(corr).size == 56499


def test_autodetect_equals_qt_on_a_channel_with_a_plateau_and_reports_failure(env, qt_tool):
    widget, _ = qt_tool
    qt_model = widget.tac_panel.model
    app = make(env)
    model = load(app, env)
    # Channel 0 of this decay file has no flat plateau: the Qt tool swallows the error, the
    # native tool keeps the region and says so.
    model.linear_start, model.linear_stop = 1200, 1900
    click(app, "autodetect")
    assert (model.linear_start, model.linear_stop) == (1200, 1900)
    assert model.message.startswith("Auto-detect failed")
    # Channel 8 has one.
    for target in (qt_model, model):
        target.channel = "8"
    qt_model.update()
    model.channel_changed()
    for target in (qt_model, model):
        target.linear_start, target.linear_stop = 1200, 1900
    qt_model.autodetect()
    click(app, "autodetect")
    assert (model.linear_start, model.linear_stop) == (788, 828) == (
        qt_model.linear_start,
        qt_model.linear_stop,
    )
    assert model.message == "Auto-detected region [788, 828)."


def test_tab_two_corrected_histograms_equal_the_production_reader(env):
    from chisurf.core.fio.staging import open_tttr

    app = make(env)
    model = load(app, env)
    model.add_all()
    settle(app)
    model.stage = 1
    model.add_files([str(env["spc"])])
    settle(app)
    ws = model.ws
    ws.active_channel = 0
    model.shift = 3
    tttr = open_tttr(
        env["spc"],
        channel_luts=ws.channel_luts,
        channel_shifts=ws.channel_shifts,
        apply_lut=True,
    )
    mask = np.asarray(tttr.routing_channels) == 0
    expected = np.bincount(
        np.asarray(tttr.micro_times)[mask].astype(int), minlength=len(ws.corrected[0])
    )
    np.testing.assert_array_equal(ws.corrected[0], expected)
    assert ws.raw[0].sum() == ws.corrected[0].sum()
    assert model.channel_rows[0] == {
        "channel": 0,
        "show": True,
        "photons": 56499,
        "lut": "yes",
        "shift": 3,
    }


# --------------------------------------------------------------------------- #
# 2. the two plots: empty state, populated, draggable region
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("size", SIZES)
def test_empty_state_draws_both_plots_with_the_qt_axes_and_no_data(env, size, monkeypatch):
    drawn = []
    real = implot.plot_line
    monkeypatch.setattr(implot, "plot_line", lambda *a, **k: (drawn.append(a), real(*a, **k)))
    app = make(env)
    painter = frames(app, size)
    text = "\n".join(painter.strings)
    for shown in (
        "Raw TAC histogram (drag the orange region)",
        "After linearization (corrected preview)",
        "TAC bin",
        "Equal-width NTAC bin",
        "Counts",
    ):
        assert shown in text, shown
    assert drawn == [], "an empty state must not draw a curve"
    assert app.model.raw_plot() is None and app.model.corrected_plot() is None
    assert "No LUT" in text


@pytest.mark.parametrize("size", SIZES)
def test_populated_state_draws_both_curves(env, size, monkeypatch):
    drawn = []
    real = implot.plot_line
    monkeypatch.setattr(implot, "plot_line", lambda *a, **k: (drawn.append(a[0]), real(*a, **k)))
    app = make(env)
    load(app, env)
    drawn.clear()
    painter = frames(app, size)
    assert {"Raw TAC", "Corrected"} <= set(drawn)
    text = "\n".join(painter.strings)
    assert "ch 0 | Range [1749, 2387)" in text
    assert "uniform.spc" in text
    PixelPainter(*size)


def _edge_pixels(app, monkeypatch):
    seen = {}
    real = implot.drag_rect

    def wrapped(n, x0, y0, x1, y1, *args, **kwargs):
        mid = (y0 + y1) / 2
        seen["left"] = implot.plot_to_pixels(x0, mid)
        seen["right"] = implot.plot_to_pixels(x1, mid)
        return real(n, x0, y0, x1, y1, *args, **kwargs)

    monkeypatch.setattr(implot, "drag_rect", wrapped)
    frames(app, count=3)
    return seen


def test_the_plateau_region_is_dragged_with_the_pointer_and_the_lut_follows(
    env, monkeypatch
):
    app = make(env)
    model = load(app, env)
    seen = _edge_pixels(app, monkeypatch)
    f_before = model.ws.compute.current_table["f"]
    lx, ly = seen["left"]
    app.hover(lx, ly)
    frames(app, count=2)
    app.press(lx, ly)
    frames(app, count=1)
    for dx in (20, 40, 60, 80):
        app.drag(lx + dx, ly)
        frames(app, count=1)
    app.release()
    frames(app, count=2)
    assert model.linear_start > 1749 + 300  # the left edge moved right by about 430 bins
    assert model.linear_stop == 2387
    assert "Range [%d, 2387)" % model.linear_start in model.info_text
    # the region sets the scale f of the table (the corrected histogram itself does not depend
    # on it, as in the Qt tool)
    assert model.ws.compute.current_table["f"] != f_before
    # the spec fields show the dragged value
    assert str(model.linear_start) in "\n".join(frames(app).strings)


def test_a_dragged_region_is_ordered_clamped_and_leaves_the_data_alone(env, monkeypatch):
    app = make(env)
    model = load(app, env)
    counts = np.array(model.ws.compute.counts)

    class Dragged:
        modified, x_min, y_min, x_max, y_max = True, 3000.0, 0.0, 99999.0, 1.0
        clicked = hovered = held = False

    monkeypatch.setattr(implot, "drag_rect", lambda *a, **k: Dragged())
    frames(app, count=1)
    assert model.linear_start == 3000
    assert model.linear_stop == model.ws.compute.n_bins == 3664
    Dragged.x_min, Dragged.x_max = 2500.0, 1000.0  # dragged past each other
    frames(app, count=1)
    assert (model.linear_start, model.linear_stop) == (1000, 2500)
    np.testing.assert_array_equal(model.ws.compute.counts, counts)


def test_offset_and_threshold_lines_are_dragged(env, monkeypatch):
    app = make(env)
    model = load(app, env)

    class Line:
        def __init__(self, value):
            self.modified, self.value = True, value
            self.clicked = self.hovered = self.held = False

    monkeypatch.setattr(
        implot, "drag_line_x", lambda n, x, *a, **k: Line(321.6)
    )
    monkeypatch.setattr(implot, "drag_line_y", lambda n, y, *a, **k: Line(-4.0))
    frames(app, count=1)
    assert model.noffset == 322
    assert model.threshold == 0.0  # clamped at zero
    assert model.ws.compute.current_table["noffset"] == 322


def test_the_corrected_preview_is_cached_until_an_input_changes(env, monkeypatch):
    app = make(env)
    model = load(app, env)
    calls = []
    real = type(model.ws.compute).corrected_after_hist
    monkeypatch.setattr(
        type(model.ws.compute), "corrected_after_hist", lambda self: (calls.append(1), real(self))[1]
    )
    frames(app, count=5)
    first = len(calls)
    frames(app, count=5)
    assert len(calls) == first, "drawing again must not rebin 500k photons"
    model.noffset = 600
    model.param_changed()
    frames(app, count=2)
    assert len(calls) == first + 1


# --------------------------------------------------------------------------- #
# 3. every control and its error path
# --------------------------------------------------------------------------- #
def test_buttons_are_disabled_until_there_is_something_to_act_on(env):
    model = make(env).model
    for name in ("autodetect", "save_lut", "export_corrected", "add_all", "remove_file",
                 "clear_files", "remove_lut", "clear_luts", "assign_selected", "assign_all",
                 "save_json"):
        assert not model.enabled(name), name
    assert model.enabled("request_add_files") and model.enabled("show_help")
    assert not model.enabled("apply_setup")
    model.busy = True
    assert not model.enabled("request_add_files")


def test_file_buttons_open_the_right_dialogs(env, chooser):
    app = make(env)
    click(app, "request_add_files")
    dialog = chooser.made[-1]
    assert dialog.mode == "open" and dialog.multiselect and "*.spc" in dialog.filters
    chooser.chosen = []
    app.dialog = None
    click(app, "request_add_folder")
    assert chooser.made[-1].mode == "folder"
    app.dialog = None
    chooser.chosen = []
    opened = []
    app.dataset_picker.open = lambda: opened.append(True)  # the MMFDB picker itself is shared
    click(app, "request_database")
    assert opened == [True]
    app.model.stage = 1
    app.model.ws.receive_computed_lut("a", [0.0, 1.0], 0)  # Save JSON needs a LUT
    frames(app)
    for name, mode in (("request_load_lut", "open"), ("request_load_json", "open"),
                       ("request_save_json", "save")):
        app.dialog = None
        chooser.chosen = []
        click(app, name)
        assert chooser.made[-1].mode == mode, name


def test_add_files_folder_remove_clear_and_unsupported_files(env, chooser):
    app = make(env)
    folder = env["dir"] / "folder"
    folder.mkdir()
    shutil.copy(SPC, folder / "a.spc")
    (folder / "notes.txt").write_text("not a photon file")
    chooser.chosen = [str(folder)]
    click(app, "request_add_folder")
    settle(app)
    assert [r["name"] for r in app.model.file_rows] == ["a.spc"]
    chooser.chosen = [str(folder / "notes.txt")]
    app.model.finish_dialog("add_files", chooser.chosen)
    assert app.model.message == "No supported TTTR files."
    assert [r["name"] for r in app.model.file_rows] == ["a.spc"]
    app.model.select_file(app.model.file_rows[0])
    assert app.model.enabled("remove_file")
    click(app, "remove_file")
    settle(app)
    assert app.model.file_rows == [] and app.model.ws.compute.counts is None
    load(app, env)
    click(app, "clear_files")
    settle(app)
    assert app.model.file_rows == [] and app.model.raw_plot() is None


def test_an_unreadable_file_is_reported_not_raised(env):
    app = make(env)
    bad = env["dir"] / "broken.spc"
    bad.write_bytes(b"not a photon file")
    app.model.add_files([str(bad)])
    settle(app)
    assert app.model.message and app.model.ws.compute.counts is None
    frames(app)


def test_save_and_export_without_a_lut_report_instead_of_raising(env, chooser):
    app = make(env)
    model = app.model
    model.finish_dialog("save_lut", [str(env["dir"] / "x.npy")])
    assert model.message == "Compute a LUT first."
    model.finish_dialog("export_corrected", [str(env["dir"] / "x.npy")])
    settle(app)
    assert model.message == "Compute a LUT first."
    model.autodetect()
    assert model.message == "Load a uniform-illumination file first."
    model.finish_dialog("save_lut", [])  # a cancelled dialog changes nothing
    assert model.message == "Load a uniform-illumination file first."


def test_export_formats_follow_the_extension(env, chooser):
    app = make(env)
    model = load(app, env)
    for ext in (".npy", ".npz", ".csv", ".txt"):
        path = env["dir"] / f"corrected{ext}"
        model.finish_dialog("export_corrected", [str(path)])
        settle(app)
        assert path.is_file(), ext
        data = np.load(path)["corrected_ntac"] if ext == ".npz" else (
            np.load(path) if ext == ".npy" else np.loadtxt(path, delimiter="," if ext == ".csv" else None)
        )
        assert data.size == 56499, ext
    lut = env["dir"] / "lut.json"
    model.finish_dialog("save_lut", [str(lut)])
    assert lut.is_file()


def test_tab_two_assign_remove_clear_shift_and_selection_errors(env):
    app = make(env)
    model = load(app, env)
    model.add_all()
    settle(app)
    model.stage = 1
    model.add_files([str(env["spc"])])
    settle(app)
    ws = model.ws
    # the table sources
    assert [r["name"] for r in model.lut_rows] == ["ch0_lut", "ch1_lut", "ch8_lut", "ch9_lut"]
    assert model.lut_rows[0] == {"name": "ch0_lut", "entries": 3664, "channels": "0"}
    assert [r["channel"] for r in model.channel_rows] == [0, 1, 8, 9]
    # assign the selected LUT to the active channel, then to all
    model.select_lut({"name": "ch8_lut"})
    model.select_channel({"channel": 1})
    model.assign_selected()
    np.testing.assert_array_equal(ws.channel_luts[1], ws.loaded_luts["ch8_lut"])
    model.assign_all()
    assert all(np.array_equal(v, ws.loaded_luts["ch8_lut"]) for v in ws.channel_luts.values())
    assert model.lut_rows[2]["channels"] == "0, 1, 8, 9"
    # a shift changes the corrected histogram of the active channel only
    before = ws.corrected[1].copy()
    model.shift = 5
    assert model.shift == 5 and ws.channel_shifts[1] == 5
    assert not np.array_equal(ws.corrected[1], before)
    # Show column hides a channel's curves
    model.edit_channel({"channel": 8}, "show", False)
    assert 8 not in ws.visible
    # remove / clear
    model.select_lut({"name": "ch0_lut"})
    model.remove_lut()
    assert "ch0_lut" not in ws.loaded_luts and ws.channel_luts
    model.delete_lut({"name": "ch1_lut"})
    assert "ch1_lut" not in ws.loaded_luts
    model.clear_luts()
    assert not ws.loaded_luts and not ws.channel_luts and model.message == "Cleared all LUTs."
    model.assign_selected()
    assert model.message == "Select a loaded LUT first."


def test_load_lut_load_json_save_json_round_trip(env, chooser):
    app = make(env)
    model = load(app, env)
    model.add_all()
    settle(app)
    lut = env["dir"] / "ch8.npy"
    model.ws.compute.channel = "8"
    model.channel_changed()
    model.finish_dialog("save_lut", [str(lut)])
    model.stage = 1
    model.add_files([str(env["spc"])])
    settle(app)
    # Load LUT, Save JSON, Clear LUTs, Load JSON
    model.finish_dialog("load_lut", [str(lut)])
    assert model.message == "Loaded LUT 'ch8.npy'."
    assert "ch8.npy" in model.ws.loaded_luts
    saved = env["dir"] / "settings.tttr.json"
    model.shift = 2
    model.finish_dialog("save_json", [str(saved)])
    data = json.loads(saved.read_text())
    assert sorted(data["channel_luts"]) == ["0", "1", "8", "9"]
    assert data["channel_shifts"] == {"0": 2}
    expected = {int(k): np.array(v) for k, v in data["channel_luts"].items()}
    model.clear_luts()
    assert not model.enabled("save_json")
    model.finish_dialog("load_json", [str(saved)])
    settle(app)
    assert model.message == "Loaded settings from settings.tttr.json."
    for channel, lut_values in expected.items():
        np.testing.assert_allclose(model.ws.channel_luts[channel], lut_values)
    assert model.ws.channel_shifts == {0: 2}
    # a broken file is a message, never an exception
    broken = env["dir"] / "broken.json"
    broken.write_text("{not json")
    model.finish_dialog("load_json", [str(broken)])
    settle(app)
    assert model.message
    bad_lut = env["dir"] / "bad.npy"
    bad_lut.write_bytes(b"nope")
    model.finish_dialog("load_lut", [str(bad_lut)])
    assert model.message


def test_reading_routine_choice_reloads_the_preview_files(env):
    app = make(env)
    model = load(app, env)
    model.stage = 1
    model.add_files([str(env["spc"])])
    settle(app)
    assert model.reading_name == "Auto" and model.ws.reading_routine is None
    model.reading_name = "SPC-130"
    assert model.ws.reading_routine == 2
    model.reading_changed()
    settle(app)
    assert sorted(model.ws.raw) == [0, 1, 8, 9]
    assert model.bundle_reading() == 2 if hasattr(model, "bundle_reading") else True
    assert model.ws.bundle()["reading_routine"] == 2


def test_apply_to_detector_setup_uses_the_callback_and_is_hidden_without_one(env):
    app = make(env)
    assert not app.model.has_apply
    app.model.apply_setup()
    assert "detector setup" in app.model.message
    applied = []
    app = make(env, apply_callback=applied.append)
    model = load(app, env)
    assert model.has_apply
    model.add_all()
    settle(app)
    assert model.enabled("apply_setup")
    frames(app)
    assert "apply_setup" in app.form.rects
    click(app, "apply_setup")
    assert sorted(applied[0]["channel_luts"]) == ["0", "1", "8", "9"] or sorted(
        applied[0]["channel_luts"]
    ) == [0, 1, 8, 9]
    assert "Applied" in model.message
    plain = make(env)
    frames(plain)
    assert "apply_setup" not in plain.form.rects


def test_drag_and_drop_adds_photon_files_and_imports_luts(env):
    app = make(env)
    model = app.model
    lut = env["dir"] / "dropped.npy"
    np.save(lut, np.linspace(0, 100, 50))
    assert app.on_files_dropped([str(env["spc"]), str(lut)])
    settle(app)
    assert [r["name"] for r in model.file_rows] == ["uniform.spc"]
    assert "dropped.npy" in model.ws.loaded_luts


def test_help_guide_and_json_buttons_open_their_windows(env):
    app = make(env)
    click(app, "show_help")
    assert app.help_window.open
    app.help_window.hide()
    click(app, "start_guide")
    assert app.tour.active
    app.tour.stop()
    model = app.model
    model.stage = 1
    model.ws.receive_computed_lut("a", [0.0, 1.0, 2.0], 0)
    click(app, "toggle_json")
    assert model.show_json
    painter = frames(app)
    assert any("settings" in s and "correction" in s for s in painter.strings)
    click(app, "close_json")
    assert not model.show_json


# --------------------------------------------------------------------------- #
# 4. the spec, tooltips, draws, guide, no Qt, settings
# --------------------------------------------------------------------------- #
def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


def _spec():
    return json.loads((GUI / "lut_tools_emtk.view.json").read_text(encoding="utf-8"))


def test_every_spec_key_exists_on_the_model():
    from chisurf.plugins.tttr.tttr_lut_tools.gui.model import LutToolModel

    model = LutToolModel()
    for section in _walk(_spec()["sections"]):
        for key in ("attr", "source", "options_source"):
            name = section.get(key)
            if name:
                assert hasattr(model, name), name
        if section.get("call"):
            assert callable(getattr(model, section["call"])), section["call"]
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        options = section.get("options")
        if isinstance(options, dict):
            for key in ("source", "selected_call", "delete_call", "edited_call"):
                if options.get(key):
                    assert hasattr(model, options[key]), options[key]


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("tttr_lut_tools")
    inventory = emtk_inventory(app)
    assert inventory["controls_without_tooltip"] == []
    assert len(inventory["interactive"]) >= 10
    for section in _walk(_spec()["sections"]):
        if section.get("type") in ("value", "choice", "toggle", "table", "custom", "panel", "info"):
            assert section.get("description"), section.get("attr") or section.get("title")
        options = section.get("options")
        for column in (options or {}).get("columns", []) if isinstance(options, dict) else []:
            assert column.get("tooltip"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_tab_two_controls_have_tooltips_too(env):
    from test.gui.emtk_port_parity import ControlRecorder

    app = make(env)
    app.model.stage = 1
    load_model = app.model
    load_model.ws.receive_computed_lut("a", [0.0, 1.0], 0)
    recorder = ControlRecorder()
    with recorder.installed():
        frames(app)
        recorder.rows.clear()
        frames(app, count=1)
    missing = sorted({r["label"] or r["id"] for r in recorder.rows if not r["tooltip"]})
    assert missing == []
    labels = {r["label"] for r in recorder.rows}
    assert {"Load LUT", "Clear LUTs", "Selected", "All", "Show JSON", "Load JSON"} <= labels


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("stage", (0, 1))
def test_app_draws_empty_and_populated_on_both_tabs(env, size, stage, caplog):
    app = make(env)
    app.model.stage = stage
    frames(app, size)
    model = load(app, env)
    if stage == 1:
        model.add_all()
        settle(app, size)
        model.add_files([str(env["spc"])])
        settle(app, size)
        model.show_lut = True
    painter = frames(app, size)
    assert painter.strings
    assert not [r for r in caplog.records if r.levelname == "ERROR"]
    pixels = None
    for _ in range(3):
        pixels = PixelPainter(*size)
        app.draw(pixels, 0.0, 0.0, float(size[0]), float(size[1]))


def test_the_guide_targets_are_real_controls_and_wait_for_the_user(env, chooser):
    app = make(env)
    steps = json.loads((GUI / "guide.json").read_text(encoding="utf-8"))["steps"]
    frames(app)
    load(app, env)
    frames(app)
    known = set(app.form.rects)
    for step in steps:
        assert step["target"]["name"] in known, step["title"]
    awaited = [s["target"]["name"] for s in steps if s.get("await")]
    assert awaited == ["request_add_files", "autodetect", "add_all"]
    app.model.ws.compute.clear()
    app.tour.start(1)
    frames(app)
    assert app.tour.awaiting
    app.tour.next()
    assert app.tour.step_idx == 1, "the tour does not press or skip for the user"
    chooser.chosen = [str(env["spc"])]
    click(app, "request_add_files")
    settle(app)
    assert not app.tour.awaiting
    app.tour.next()
    assert app.tour.step_idx == 2


def test_help_text_links_are_live_and_stage_labels_match_the_qt_tabs():
    help_text = (GUI / "help.md").read_text(encoding="utf-8")
    for target in __import__("re").findall(r"\]\((docs/[^)]+)\)", help_text):
        assert (ROOT / target).is_file(), target
    from chisurf.plugins.tttr.tttr_lut_tools.gui.model import STAGES

    assert STAGES == ("Compute LUT", "settings.tttr.json (optional)")


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("tttr_lut_tools")
    assert result["ok"], result["output"]


def test_settings_round_trip_keeps_the_session(env):
    app = make(env)
    model = load(app, env)
    model.linear_start, model.linear_stop = 1800, 2100
    model.channel = "1"
    model.channel_changed()
    model.linear_start, model.linear_stop = 1800, 2100
    model.param_changed()
    model.add_all()
    settle(app)
    model.stage = 1
    app.form.folds["Advanced"] = False
    state = app.export_settings()
    json.dumps(state)  # plain data
    app.close()
    assert (env["dir"] / "prefs.json").is_file()
    fresh = make(env)  # restores prefs.json
    settle(fresh)
    restored = fresh.model
    assert restored.stage == 1
    assert restored.channel == "1"
    assert (restored.linear_start, restored.linear_stop) == (1800, 2100)
    assert sorted(restored.ws.channel_luts) == [0, 1, 8, 9]
    np.testing.assert_array_equal(restored.ws.channel_luts[8], model.ws.channel_luts[8])
    assert fresh.form.folds.get("Advanced") is False
    # a corrupt preference file is reported, not fatal
    (env["dir"] / "prefs.json").write_text("{broken")
    again = make(env)
    assert "Could not restore" in again.model.message
    frames(again)


def test_an_old_preference_file_without_the_new_keys_still_restores(env):
    app = make(env)
    model = load(app, env)
    old = {"workspace": model.ws.get_state(), "stage": 0, "docks": app.docks.state()}
    fresh = make(env)
    fresh.restore_settings(old)
    assert fresh.model.ws.compute.counts is not None
    assert fresh.model.stage == 0


def test_translated_labels_and_descriptions_follow_the_locale(env):
    app = make(env)
    app._sync_spec()
    english = json.dumps(app.panels["compute"])
    i18n.set_locale("de")
    try:
        app._sync_spec()
        german = json.dumps(app.panels["compute"])
    finally:
        i18n.set_locale("en")
    assert english != german
    assert "Linearer Anfang" in german
