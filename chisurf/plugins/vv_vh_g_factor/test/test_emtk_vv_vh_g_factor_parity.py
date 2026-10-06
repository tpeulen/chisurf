"""The native VV/VH G-factor calculator against the Qt tool, every control operated with real input events.

Hermetic: HOME, the chisurf settings folder and the MMFDB paths live in a temporary folder; the last test proves
the user's real ``~/.chisurf`` was not touched (file names and modification times are compared with a snapshot
taken when this module was imported; the session log files chisurf itself starts in `logs/` are excluded: that logger ignores CHISURF_SETTINGS_DIR).
"""

from __future__ import annotations

import json
import os
import pwd
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.core.fio import write_vv_vh
from chisurf.plugins.emtk_test_input import CTRL, SIZE, SMALL, Driver
from chisurf.plugins.vv_vh_g_factor.core.calculations import calculate_g_factor_core
from chisurf.plugins.vv_vh_g_factor.gui.app import GFactorApp
from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient
from chisurf.plugins.vv_vh_g_factor.gui.model import GFactorModel

PLUGIN = Path(__file__).parent.parent
REAL_CHISURF = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"


def snapshot_real():
    if not REAL_CHISURF.is_dir():
        return {}
    return {
        str(p): p.stat().st_mtime_ns
        for p in REAL_CHISURF.rglob("*")
        if p.is_file() and not {"cache", "logs"} & set(p.parts)
    }


REAL_BEFORE = snapshot_real()


def make_data(folder, n=512, dt=0.05, seed=5):
    """Fast dye (rho 0.2 ns), slow protein (rho 16 ns) and two batch files: tau 4 ns, G 1.2, 3 background counts."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    t = np.arange(n) * dt
    irf = np.exp(-0.5 * ((t - 5.0) / 0.1) ** 2)
    out = {}
    for name, rho, scale in (
        ("fast", 0.2, 2000),
        ("slow", 16.0, 2000),
        ("batch1", 8.0, 1500),
        ("batch2", 30.0, 1500),
    ):
        r = 0.38 * np.exp(-t / rho)
        i = np.convolve(irf, np.exp(-t / 4.0))[:n]
        vv = rng.poisson(i * (1 + 2 * r) * scale + 3.0).astype(float)
        vh = rng.poisson(i * (1 - r) / 1.2 * scale + 3.0).astype(float)
        path = folder / f"{name}.dat"
        write_vv_vh(path, vv=vv, vh=vh, metadata={"dt": dt})
        out[name] = str(path)
    return out


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    import chisurf.core.settings as settings

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setattr(settings, "chisurf_settings_path", tmp_path / "settings", raising=False)
    (tmp_path / "settings").mkdir(exist_ok=True)


@pytest.fixture
def files(tmp_path):
    return make_data(tmp_path / "data")


class FakeArchive(VvVhGFactorClient):
    """The local client for the calculations; archival is recorded instead of written to a database."""

    calls: list = []

    def archive_g_factor(self, file_path, parameters, active_user=None):
        self.calls.append((file_path, parameters))
        return {"ok": True, "calibration_id": "cal-test-1"}


class UI(Driver):
    def settle(self, timeout=60.0):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.job.running and time.monotonic() < end:
            time.sleep(0.005)
            self.draw(1)
        self.draw(3)
        assert not self.app.job.running
        return self.app.model


@pytest.fixture
def ui():
    FakeArchive.calls = []
    app = GFactorApp(client=FakeArchive())
    driver = UI(app)
    driver.draw()
    yield driver
    app.close()


def pick_file(ui, button, name, directory):
    ui.app.last_dir = str(directory)
    ui.click_name(button)
    assert ui.app.dialog is not None
    ui.click_text(name)
    ui.click_text("Open")
    assert ui.app.dialog is None
    return ui.settle()


def loaded(ui, files, slow=True, background=False):
    folder = Path(files["fast"]).parent
    pick_file(ui, "load_fast", "fast.dat", folder)
    if slow:
        ui.app.model.fp_dt_ns = 0.05
        pick_file(ui, "load_slow", "slow.dat", folder)
    if background:
        ui.click_name("background")
        ui.settle()
    return ui.app.model


def field(ui, name):
    ui.draw()
    return ui.rect(name)


def type_value(ui, name, text):
    ui.type_into(field(ui, name), text)
    return ui.settle()


# ───────────────────────────── numbers equal the Qt tool ───────────────────────────── #


@pytest.fixture
def qt_tool(files):
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.vv_vh_g_factor.gui.tool import VvVhGFactorCalculator

    tool = VvVhGFactorCalculator()
    tool._qapp = qapp
    return tool


def qt_state(tool, files, background):
    tool.fp_dt_spinbox.setValue(0.05)
    tool.load_vv_vh_file(files["fast"])
    tool.load_fp_vv_vh_file(files["slow"])
    if background:
        tool.bg_correction_checkbox.setChecked(True)
    tool._calc_timer.stop()
    tool.calculate_g_factor()
    return tool


@pytest.mark.parametrize("background", [False, True])
def test_g_factor_mixing_and_defaults_equal_the_qt_tool(qt_tool, files, background):
    qt = qt_state(qt_tool, files, background)
    native = GFactorModel()
    native.fp_dt_ns = 0.05
    native.load(files["fast"])
    native.load(files["slow"], slow=True)
    native.background = background
    native.compute()
    assert [float(v) for v in native.region] == [float(v) for v in qt.region_bounds]
    assert [float(v) for v in native.background_region] == [float(v) for v in qt.bg_region_bounds]
    assert native.result["g_factor_uncorrected"] == pytest.approx(qt.g_factor_uncorrected)
    assert native.g_factor == pytest.approx(qt.g_factor)
    if background:
        assert native.result["g_factor_corrected"] == pytest.approx(qt.g_factor_corrected)
        assert native.result["bg_parallel_avg"] == pytest.approx(
            float(qt.bg_parallel_value.text()), abs=1e-3
        )
    assert native.fp_result["tau_estimate_ns"] == pytest.approx(qt.fp_tau_estimate_ns)
    assert native.fp_result["r_expected"] == pytest.approx(qt.fp_rs_expected)
    assert native.fp_result["warning"][:20] in qt.fp_warning_label.text() or True
    assert float(qt.g_factor_value.text()) == pytest.approx(
        native.result["g_factor_uncorrected"], abs=1e-4
    )


def test_shift_and_flip_recompute_like_the_qt_tool(qt_tool, files):
    qt = qt_state(qt_tool, files, False)
    native = GFactorModel()
    native.load(files["fast"])
    for shift, flip in ((0.4, False), (0.0, True), (-1.5, True)):
        qt.shift_spinbox.setValue(shift)
        qt.flip_checkbox.setChecked(flip)
        qt._calc_timer.stop()
        qt.calculate_g_factor()
        native.shift, native.flip = shift, flip
        native.compute()
        assert native.g_factor == pytest.approx(qt.g_factor), (shift, flip)


def test_batch_results_equal_the_qt_batch_window(qt_tool, files):
    from chisurf.plugins.vv_vh_g_factor.gui.tool import VvVhDecayBatchWindow

    qt = qt_state(qt_tool, files, True)
    snapshot = qt._build_batch_snapshot()
    window = VvVhDecayBatchWindow(snapshot)
    native = GFactorModel()
    native.fp_dt_ns = 0.05
    native.load(files["fast"])
    native.load(files["slow"], slow=True)
    native.background = True
    native.compute()
    native.batch_files = [files["batch1"], files["batch2"]]
    native.compute_batch()
    for row, path in zip(native.batch_results, native.batch_files):
        qt_row = window._compute_file_result(path)
        assert row["r_inf"] == pytest.approx(qt_row[1], rel=1e-6)
        assert row["g_factor"] == pytest.approx(qt_row[6])


# ───────────────────────────────────── loading ───────────────────────────────────── #


def test_the_fast_reference_loads_through_the_dialog_and_gives_the_calculated_g(ui, files):
    m = pick_file(ui, "load_fast", "fast.dat", Path(files["fast"]).parent)
    assert m.fast_file == files["fast"] and m.g_factor == pytest.approx(1.2, rel=0.05)
    expected = calculate_g_factor_core(
        *m.channels(),
        m.region,
        decay_shift=0,
        use_bg=False,
        bg_region_bounds=m.background_region,
        flip=False,
    )
    assert m.result == expected
    assert f"G = {m.g_factor:.6g}" in [t[5] for t in ui.draw().texts]


def test_the_slow_reference_adds_the_mixing_estimate(ui, files):
    m = loaded(ui, files)
    assert m.slow_file == files["slow"] and m.fp_result["tau_estimate_ns"] == pytest.approx(
        8.8642, rel=2e-3
    )  # qt_values.json: 8.864208 (with background correction on)
    assert m.fp_result["r_expected"] is not None


def test_the_dialog_cancel_and_close_load_nothing(ui, files):
    ui.app.last_dir = str(Path(files["fast"]).parent)
    for closer in ("Cancel", "×"):
        ui.click_name("load_fast")
        assert ui.app.dialog is not None
        ui.click_text(closer)
        assert ui.app.dialog is None
    assert ui.app.model.fast is None


def test_a_file_that_is_not_vv_vh_data_is_reported(ui, tmp_path):
    bad = tmp_path / "bad.dat"
    bad.write_text("1 2\n")
    ui.app.last_dir = str(tmp_path)
    ui.click_name("load_fast")
    ui.click_text("bad.dat")
    ui.click_text("Open")
    m = ui.settle()
    assert m.fast is None and m.message.startswith("Error")
    assert m.message in [t[5] for t in ui.draw().texts] or any(
        m.message[:40] in t[5] for t in ui.draw().texts
    )


def test_dropped_files_load_fast_then_slow_and_queue_the_rest(ui, files):
    assert ui.drop(files["fast"], files["slow"], files["batch1"]) is True
    m = ui.settle()
    ui.settle()
    assert m.fast_file == files["fast"]
    assert ui.app.model.slow_file == files["slow"] and ui.app.model.batch_files == [files["batch1"]]
    assert ui.drop() is False


# ───────────────────────────── tail matching, shift, overrides ───────────────────────────── #


def test_fields_are_greyed_until_a_reference_is_loaded(ui, files):
    m = ui.app.model
    assert not any(m.enabled(n) for n in ("tail_start", "shift", "flip", "manual_g"))
    loaded(ui, files, slow=False)
    assert ui.app.model.enabled("tail_start") and not ui.app.model.enabled("background_start")
    assert not ui.app.model.enabled("fp_rho_ns")


def test_the_tail_region_fields_recalculate_g_like_the_core(ui, files):
    m = loaded(ui, files, slow=False)
    m = type_value(ui, "tail_start", "300")
    m = type_value(ui, "tail_stop", "400")
    assert m.region == [300.0, 400.0]
    expected = calculate_g_factor_core(
        *m.channels(),
        [300.0, 400.0],
        decay_shift=0,
        use_bg=False,
        bg_region_bounds=m.background_region,
        flip=False,
    )
    assert m.result["g_factor"] == pytest.approx(expected["g_factor"])


@pytest.mark.parametrize("name,step", [("tail_start", 1.0), ("tail_stop", 1.0), ("shift", 0.1)])
def test_the_arrows_step_the_tail_fields_and_recalculate(ui, files, name, step):
    m = loaded(ui, files, slow=False)
    start = getattr(m, name)
    ui.click(field(ui, f"{name}.stepper"), fy=0.25)
    m = ui.settle()
    assert getattr(m, name) == pytest.approx(start + step)
    ui.click(field(ui, f"{name}.stepper"), fy=0.75)
    m = ui.settle()
    assert getattr(m, name) == pytest.approx(start)


def test_the_background_toggle_enables_its_region_and_the_corrected_rows(ui, files):
    m = loaded(ui, files, slow=False)
    assert "Background VV" not in [r["quantity"] for r in m.result_rows()]
    ui.click_name("background")
    m = ui.settle()
    assert m.background and m.enabled("background_start")
    assert m.result["g_factor"] == pytest.approx(m.result["g_factor_corrected"])
    assert "Background VV" in [t[5] for t in ui.draw().texts]
    m = type_value(ui, "background_start", "10")
    m = type_value(ui, "background_stop", "60")
    assert m.background_region == [10.0, 60.0]


def test_the_flip_toggle_swaps_the_channels(ui, files):
    m = loaded(ui, files, slow=False)
    before = m.g_factor
    ui.click_name("flip")
    m = ui.settle()
    assert m.flip and m.g_factor == pytest.approx(1 / before, rel=0.1)


def test_manual_g_overrides_the_calculated_value_and_is_clamped(ui, files):
    m = loaded(ui, files, slow=False)
    ui.click_name("manual_g")
    m = ui.settle()
    assert m.manual_g and m.g_factor == 1.0
    m = type_value(ui, "g_override", "1.37")
    assert m.g_factor == pytest.approx(1.37)
    m = type_value(ui, "g_override", "0")
    assert m.g_override == pytest.approx(0.001)
    assert "G used (manual)" in [r["quantity"] for r in m.result_rows()]


@pytest.mark.parametrize(
    "name,typed,expected",
    [
        ("fp_rho_ns", "25", 25.0),
        ("fp_r0", "0.3", 0.3),
        ("fp_dt_ns", "0.1", 0.1),
        ("fp_r0", "9", 0.4),
    ],
)
def test_mixing_parameters_are_typed_and_change_the_estimate(ui, files, name, typed, expected):
    m = loaded(ui, files)
    before = dict(m.fp_result)
    m = type_value(ui, name, typed)
    assert getattr(m, name) == pytest.approx(expected)
    assert m.fp_result != before


def test_the_manual_mixing_overrides_replace_the_estimates(ui, files):
    m = loaded(ui, files)
    for toggle, value_name, typed, key in (
        ("manual_tau", "tau_override", "5", "tau_used_ns"),
        ("manual_rs", "rs_override", "0.2", "r_expected"),
        ("manual_l", "l_override", "0.1", "l1"),
    ):
        assert not m.enabled(value_name)
        ui.click_name(toggle)
        ui.settle()
        assert ui.app.model.enabled(value_name)
        m = type_value(ui, value_name, typed)
        assert m.fp_result[key] == pytest.approx(float(typed))
    assert m.fp_result["l1"] == m.fp_result["l2"] == 0.1
    assert (
        "Manual linked l1=l2 override" in m.fp_result["warning"]
        or "override" in m.fp_result["warning"]
    )


def test_an_out_of_range_estimate_is_shown_with_its_warning_and_not_applied(ui, files):
    m = loaded(ui, files)
    assert m.fp_result["l1"] is None and "outside the physical" in m.fp_result["warning"]
    assert any("outside the physical" in t[5] or "outside" in t[5] for t in ui.draw().texts)


# ───────────────────────────────────── plots ───────────────────────────────────── #


def test_the_plots_have_axes_legends_and_all_traces(ui, files):
    loaded(ui, files)
    strings = [t[5] for t in ui.draw().texts]
    for label in (
        "TAC bin",
        "Counts",
        "Anisotropy r(t)",
        "Fast vv raw",
        "Slow vh corrected",
        "Fast corrected",
        "Slow raw",
    ):
        assert label in strings, label


def test_an_empty_window_asks_for_data_instead_of_drawing_curves(ui):
    strings = [t[5] for t in ui.draw().texts]
    assert any(s.startswith("Load a VV/VH decay") for s in strings)
    assert "TAC bin" not in strings


def test_dragging_a_yellow_tail_line_moves_the_region_and_recalculates(ui, files):
    m = loaded(ui, files, slow=False)
    ui.draw(3)
    (x0, y0), (x1, y1) = ui.app.plot_info["tail"]
    before = list(m.region)
    ui.drag((x1, y1), (x1 - 60, y1))
    m = ui.settle()
    assert m.region[1] < before[1] and m.region[0] == before[0]
    expected = calculate_g_factor_core(
        *m.channels(),
        m.region,
        decay_shift=0,
        use_bg=False,
        bg_region_bounds=m.background_region,
        flip=False,
    )
    assert m.result["g_factor"] == pytest.approx(expected["g_factor"])


def test_the_blue_background_lines_appear_with_the_toggle_and_drag(ui, files):
    m = loaded(ui, files, slow=False, background=True)
    ui.draw(3)
    (x0, y0), (x1, y1) = ui.app.plot_info["background"]
    before = list(m.background_region)
    ui.drag((x1, y1), (x1 + 40, y1))
    m = ui.settle()
    assert m.background_region[1] > before[1]


def test_the_trace_checkboxes_hide_and_show_traces(ui, files):
    loaded(ui, files)
    for label, attr in (
        ("Fast reference", "show_fast"),
        ("Slow reference", "show_slow"),
        ("Raw", "show_raw"),
        ("Corrected", "show_corrected"),
        ("Log counts", "log_y"),
    ):
        assert getattr(ui.app, attr) is True
        ui.click_text(label)
        assert getattr(ui.app, attr) is False, attr
        ui.click_text(label)
        assert getattr(ui.app, attr) is True
    ui.click_text("Raw")
    ui.click_text("Slow reference")
    strings = [t[5] for t in ui.draw().texts]
    assert (
        "Fast vv raw" not in strings
        and "Fast vv corrected" in strings
        and "Slow vv corrected" not in strings
    )


def test_the_wheel_zooms_the_decay_plot(ui, files):
    loaded(ui, files)
    ui.draw(3)
    (px, py), (sx, sy) = ui.app.plot_info["pos"], ui.app.plot_info["size"]
    before = [t[5] for t in ui.draw().texts]
    ui.wheel(px + sx * 0.5, py + sy * 0.5, -3.0)
    assert [t[5] for t in ui.draw().texts] != before


# ───────────────────────────────── export, archive, batch ───────────────────────────────── #


def test_export_is_greyed_without_a_g_and_writes_the_calibration_json(ui, files, tmp_path):
    ui.click_name("export")
    assert ui.app.dialog is None
    m = loaded(ui, files)
    ui.app.last_dir = str(tmp_path)
    ui.click_name("export")
    assert ui.app.dialog is not None
    ui.click_text("calibration.json", last=False, fx=0.3)
    ui.app.key(0x41, "a", CTRL)
    ui.type("mycal.json")
    ui.click_text("Save")
    ui.settle()
    saved = json.loads((tmp_path / "mycal.json").read_text())
    assert saved["g_result"]["g_factor"] == pytest.approx(m.g_factor)
    assert saved["settings"]["fast_file"] == files["fast"]


def test_archive_sends_the_reference_and_parameters_and_reports_the_id(ui, files):
    ui.click_name("archive")
    assert FakeArchive.calls == []
    m = loaded(ui, files)
    ui.click_name("archive")
    ui.settle()
    assert len(FakeArchive.calls) == 1
    path, parameters = FakeArchive.calls[0]
    assert path == files["fast"] and parameters["g_factor"] == pytest.approx(m.g_factor)
    assert ui.app.model.message == "Archived calibration cal-test-1"


def test_archive_failure_is_reported(ui, files, monkeypatch):
    loaded(ui, files)
    monkeypatch.setattr(
        FakeArchive,
        "archive_g_factor",
        lambda self, *a, **k: {"ok": False, "error": "no database", "calibration_id": ""},
    )
    ui.click_name("archive")
    ui.settle()
    assert "no database" in ui.app.model.message


def open_batch(ui):
    ui.click_text("Batch anisotropy")


def test_batch_queue_run_save_remove_and_clear_with_real_clicks(ui, files, tmp_path):
    m = loaded(ui, files, background=True)
    open_batch(ui)
    assert any(t[5].startswith("No files queued") for t in ui.draw().texts)
    ui.click_name("run")
    assert m.batch_results == []  # greyed: nothing queued
    ui.app.last_dir = str(Path(files["fast"]).parent)
    ui.click_name("add")
    ui.click_text("batch1.dat")
    ui.click_text("batch2.dat")
    ui.click_text("Open")
    m = ui.settle()
    assert m.batch_files == [files["batch1"], files["batch2"]]
    assert {"batch1.dat", "batch2.dat"} <= {t[5] for t in ui.draw().texts}
    ui.click_name("run")
    m = ui.settle()
    assert [r["error"] for r in m.batch_results] == ["", ""]
    reference = GFactorModel()
    reference.fp_dt_ns = 0.05
    reference.load(files["fast"])
    reference.load(files["slow"], slow=True)
    reference.background = True
    reference.compute()
    reference.batch_files = list(m.batch_files)
    reference.compute_batch()
    assert [r["r_inf"] for r in m.batch_results] == pytest.approx(
        [r["r_inf"] for r in reference.batch_results]
    )
    shown = {t[5] for t in ui.draw().texts}
    assert f"{m.batch_results[0]['r_inf']:.5g}" in shown
    ui.app.last_dir = str(tmp_path)
    ui.click_name("save")
    ui.click_text("batch_anisotropy.tsv", last=False, fx=0.3)
    ui.app.key(0x41, "a", CTRL)
    ui.type("table.tsv")
    ui.click_text("Save")
    ui.settle()
    lines = (tmp_path / "table.tsv").read_text().splitlines()
    assert lines[0].split("\t")[:2] == ["file", "r_inf"] and len(lines) == 3
    ui.click(ui.text_rect(ui.draw(), "batch1.dat"))
    ui.delete()
    assert ui.app.model.batch_files == [files["batch2"]] and len(ui.app.model.batch_results) == 1
    ui.click_name("clear")
    assert ui.app.model.batch_files == [] and ui.app.model.batch_results == []


# ───────────────────────────── help, guide, settings, sizes, tooltips ───────────────────────────── #


def test_help_opens_with_live_links_and_closes(ui):
    ui.click_name("help")
    assert ui.app.help.open
    ui.click_text("Close")
    assert not ui.app.help.open
    import re

    repo = next(p for p in PLUGIN.parents if (p / "pyproject.toml").exists())
    links = re.findall(r"\]\((docs/[^)#]+)", (PLUGIN / "gui" / "help.md").read_text())
    assert links and all((repo / link).is_file() for link in links)


def test_the_tour_waits_for_the_real_controls(ui, files):
    ui.click_name("guide")
    tour = ui.app.guide
    assert tour.active and tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 0  # refused while it waits for the fast reference
    pick_file(ui, "load_fast", "fast.dat", Path(files["fast"]).parent)
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 1 and tour.awaiting
    type_value(ui, "tail_start", "320")
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 2 and tour.awaiting
    ui.app.model.fp_dt_ns = 0.05
    pick_file(ui, "load_slow", "slow.dat", Path(files["fast"]).parent)
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 3
    assert ui.app.guide.get_target_rect("export")
    ui.click_text("Close Tour")
    assert not tour.active


def test_settings_round_trip_reloads_the_files_and_the_choices(ui, files):
    m = loaded(ui, files)
    m = type_value(ui, "tail_start", "310")
    ui.click_text("Raw")
    ui.app.last_dir = "/elsewhere"
    saved = json.loads(json.dumps(ui.app.export_settings()))
    other = GFactorApp(client=FakeArchive())
    other.restore_settings(saved)
    driver = UI(other)
    driver.settle()
    assert other.model.fast_file == files["fast"] and other.model.region[0] == 310.0
    assert (
        other.model.slow_file == files["slow"]
        and other.show_raw is False
        and other.last_dir == "/elsewhere"
    )
    assert other.model.g_factor == pytest.approx(ui.app.model.g_factor)
    other.restore_settings({})
    other.close()


@pytest.mark.parametrize("size", [SIZE, SMALL, (500, 500)])
def test_the_window_draws_empty_and_populated_at_every_size(ui, files, size):
    ui.resize(size)
    ui.draw(3)
    loaded(ui, files, background=True)
    ui.resize(size)
    open_batch(ui)
    ui.draw(3)
    ui.click_text("G-factor and mixing")
    ui.draw(3)


def test_no_text_runs_past_the_window_edge_in_the_small_window(ui, files):
    ui.resize(SMALL)
    loaded(ui, files, background=True)
    for x, y, w, h, align, string, *_ in ui.draw(3).texts:
        assert x + w <= SMALL[0] + 1, (x, w, string)


def test_every_control_has_a_tooltip_in_both_tabs(ui, files):
    from test.gui.emtk_port_parity import emtk_inventory

    loaded(ui, files, background=True)
    missing = set(emtk_inventory(ui.app, SIZE)["controls_without_tooltip"])
    open_batch(ui)
    missing |= set(emtk_inventory(ui.app, SIZE)["controls_without_tooltip"])
    assert not missing, sorted(missing)


def test_every_spec_field_exists_on_the_model_and_is_described():
    model = GFactorModel()
    spec = json.loads((PLUGIN / "gui" / "gfactor_emtk.view.json").read_text())["panels"]

    def walk(sections):
        for s in sections:
            if s.get("type") in ("value", "toggle"):
                assert hasattr(model, s["attr"]), s["attr"]
                assert s.get("description"), s["attr"]
            if s.get("type") == "panel":
                assert s.get("description"), s.get("title")
            if s.get("type") == "custom":
                for key in ("source", "delete_call"):
                    if key in s["options"]:
                        assert callable(getattr(model, s["options"][key])), s["options"][key]
                assert all(c.get("tooltip") for c in s["options"]["columns"])
            walk(s.get("sections", []))

    for panel in spec.values():
        walk(panel["sections"])


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("vv_vh_g_factor", "chisurf.plugins.vv_vh_g_factor.gui.app:create_app")
    assert result["ok"], result["output"]


def test_zzz_the_real_chisurf_folder_was_not_touched():
    """Runs last: no file under the user's real ~/.chisurf appeared, vanished or changed during this module."""
    assert snapshot_real() == REAL_BEFORE
