"""The native VV/VH G-factor calculator against the Qt tool, every control operated with real input events.

Hermetic: HOME, the chisurf settings folder and the MMFDB paths live in a temporary folder; the last test proves
the user's real ``~/.chisurf`` was not touched (file names and modification times are compared with a snapshot
taken when this module was imported; the session log files chisurf itself starts in `logs/` are excluded: that logger ignores CHISURF_SETTINGS_DIR).
"""

from __future__ import annotations

from chisurf.plugins.emtk_layout import action_caption

import csv
import hashlib
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
ORACLE_PATH = PLUGIN.parents[2] / "okf/validation/release-readiness-w1/gfactor-before/numerical-control-freeze.json"

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
        ui.settle()  # The dt change schedules recalculation; its busy state disables the picker.
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


@pytest.fixture(scope="module")
def legacy_oracle():
    """Committed controls/numerics captured before the old calculator was retired."""
    return json.loads(ORACLE_PATH.read_text())


def test_seeded_physical_files_equal_the_immutable_capture(files, legacy_oracle):
    """Regenerated physical data must match the source the frozen answers belong to."""
    for name, path in files.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == legacy_oracle["files"][name]["sha256"]


@pytest.mark.parametrize("state", ["defaults", "existing_reference", "no-background", "background"])
def test_g_factor_mixing_defaults_and_reference_equal_frozen_qt(state, files, legacy_oracle):
    record = legacy_oracle["records"][state]
    frozen = record.get("legacy", record.get("state"))
    native = GFactorModel()
    if state == "existing_reference":
        path = PLUGIN / "test_vv_vh_data.dat"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["source_sha256"]
        native.load(path)
    elif state != "defaults":
        native.fp_dt_ns = 0.05
        native.load(files["fast"])
        native.load(files["slow"], slow=True)
        native.background = state == "background"
        native.compute()
    assert native.region == list(map(float, frozen["region_bounds"]))
    assert native.background_region == list(map(float, frozen["bg_region_bounds"]))
    assert native.shift == frozen["decay_shift"] and native.flip == frozen["flip"]
    assert native.background == frozen["use_background_correction"]
    if state == "defaults":
        assert native.g_factor is None and native.result == {} and native.fp_result == {}
        controls = {c["name"]: c for c in record["controls"]}
        assert native.fp_dt_ns == controls["fp_dt_spinbox"]["value"]
        assert native.fp_rho_ns == controls["fp_rho_spinbox"]["value"]
        return
    assert native.result["g_factor_uncorrected"] == pytest.approx(frozen["g_factor_uncorrected"])
    assert native.g_factor == pytest.approx(frozen["g_factor"])
    if state == "existing_reference":
        assert native.result["g_factor_stddev_uncorrected"] > 0
        return
    before_native = record["native"]["result"]
    # The old UI never wired SD to its scalar; captured owner output preserves the real uncertainty.
    assert frozen["g_factor_stddev"] is None
    assert native.result["g_factor_stddev_uncorrected"] == pytest.approx(before_native["g_factor_stddev_uncorrected"])
    if state == "background":
        assert native.result["g_factor_corrected"] == pytest.approx(frozen["g_factor_corrected"])
        assert native.result["g_factor_stddev_corrected"] == pytest.approx(before_native["g_factor_stddev_corrected"])
        for key, display in (("bg_parallel_avg", "bg_parallel_text"), ("bg_perpendicular_avg", "bg_perpendicular_text")):
            assert native.result[key] == pytest.approx(float(frozen[display]), abs=1e-3)
    assert native.fp_result["tau_estimate_ns"] == pytest.approx(frozen["fp_tau_estimate_ns"])
    assert native.fp_result["r_expected"] == pytest.approx(frozen["fp_rs_expected"])
    assert native.fp_result["l1"] is frozen["l1_estimate"] is None
    assert native.fp_result["l2"] is frozen["l2_estimate"] is None
    assert "not applied" in native.fp_result["warning"]
    assert "will not be auto-applied" in frozen["fp_warning"]


@pytest.mark.parametrize("shift,flip", [(0.4, False), (0.0, True), (-1.5, True)])
def test_shift_and_flip_recompute_like_frozen_qt(files, legacy_oracle, shift, flip):
    frozen = legacy_oracle["records"][f"shift={shift};flip={flip}"]
    native = GFactorModel()
    native.fp_dt_ns = 0.05
    native.load(files["fast"])
    native.load(files["slow"], slow=True)
    native.shift, native.flip = shift, flip
    native.compute()
    assert native.g_factor == pytest.approx(frozen["g_factor"])
    assert native.fp_result["tau_estimate_ns"] == pytest.approx(frozen["fp_tau_estimate_ns"])
    assert native.fp_result["r_expected"] == pytest.approx(frozen["fp_rs_expected"])
    assert native.fp_result["l1"] is None and native.fp_result["l2"] is None


def test_batch_results_equal_frozen_qt_batch_window(files, legacy_oracle):
    frozen = legacy_oracle["records"]["batch"]
    native = GFactorModel()
    native.fp_dt_ns = 0.05
    native.load(files["fast"])
    native.load(files["slow"], slow=True)
    native.background = True
    native.compute()
    native.batch_files = [files["batch1"], files["batch2"]]
    native.compute_batch()
    assert len(native.batch_results) == len(frozen["results"]) == 2
    for row, expected in zip(native.batch_results, frozen["results"]):
        assert Path(row["file"]).name == expected[0]
        assert row["r_inf"] == pytest.approx(expected[1], rel=1e-6)
        assert [row["region_start"], row["region_stop"]] == expected[2:4]
        assert row["g_factor"] == pytest.approx(expected[6])
        assert [row["bg_vv"], row["bg_vh"]] == pytest.approx(expected[4:6])
    for row, expected in zip(native.batch_rows(), frozen["results"]):
        assert row["file"] == expected[0]
        assert list(map(float, row["region"].split("-"))) == expected[2:4]
        assert float(row["r_inf"]) == pytest.approx(expected[1], rel=1e-4)
        assert float(row["g_factor"]) == pytest.approx(expected[6], abs=5e-5)
        assert [float(row["bg_vv"]), float(row["bg_vh"])] == pytest.approx(expected[4:6], rel=1e-5)
    snapshot = native.batch_snapshot()
    assert list(snapshot["background_levels"]) == pytest.approx(frozen["results"][0][4:6])
    assert snapshot["l1"] == frozen["snapshot"]["l1"] == 0
    assert snapshot["l2"] == frozen["snapshot"]["l2"] == 0


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


def test_batch_folder_database_and_selected_remove_are_real_actions(files, tmp_path):
    """Drive the three formerly missing actions without using a user's MMFDB service."""
    class Catalogue:
        def __init__(self):
            self.calls = []

        def call(self, method, params):
            self.calls.append((method, params))
            if method == "mmfdb.datasets.browse":
                return {"datasets": [{"artifact_id": "batch-1", "original_filename": "batch1.dat",
                                       "artifact_kind": "raw_data", "data_format": "vv_vh"}], "total": 1}
            assert method == "mmfdb.datasets.open" and params == {"artifact_id": "batch-1"}
            return {"local_path": files["batch1"]}

    catalogue = Catalogue()
    app = GFactorApp(client=FakeArchive(), dataset_client=catalogue)
    ui = UI(app)
    try:
        ui.draw()
        open_batch(ui)
        # All seven actions captured in the legacy batch window have real native hit rectangles.
        for name in ("batch_files.add", "batch_files.folder", "batch_files.database",
                     "batch_files.remove", "batch_files.clear", "run", "save"):
            assert ui.rect(name)[2] > 0, name
        folder = tmp_path / "batch-folder"
        nested = folder / "nested"
        nested.mkdir(parents=True)
        first = folder / "batch1.dat"
        second = nested / "batch2.dat"
        first.write_bytes(Path(files["batch1"]).read_bytes())
        second.write_bytes(Path(files["batch2"]).read_bytes())
        (folder / "ignore.bin").write_bytes(b"not a VV/VH file")
        app.last_dir = str(folder)
        ui.click_name("batch_files.folder")
        assert app.dialog is not None and app.dialog.mode == "folder"
        ui.click_text("Choose")
        assert app.dialog is None
        assert app.model.batch_files == [str(first), str(second)]
        ui.click_name("batch_files.1")
        ui.click_name("batch_files.remove")
        assert app.model.batch_files == [str(first)] and second.is_file()
        app.last_dir = str(folder)
        ui.click_name("batch_files.folder")
        ui.click_text("Choose")
        assert app.model.batch_files == [str(first), str(second)]
        ui.click_name("batch_files.1")
        ui.click_name("batch_files.clear")
        assert app.model.batch_files == [] and first.is_file()
        app.last_dir = str(folder)
        ui.click_name("batch_files.folder")
        ui.click_text("Choose")
        assert app.model.batch_files == [str(first), str(second)]
        ui.click_name("batch_files.remove")
        assert app.model.batch_files == [str(second)]  # Clear reset the former second-row selection.
        ui.click_name("batch_files.clear")
        ui.click_name("batch_files.database")
        deadline = time.monotonic() + 5
        while app.dataset_picker._pending is not None and time.monotonic() < deadline:
            time.sleep(0.005)
            ui.draw()
        assert app.dataset_picker.is_open and not app.dataset_picker.error
        ui.click_text("batch1.dat [raw_data] (vv_vh)")
        ui.click_text("Open selected")
        while app.dataset_picker.is_open and time.monotonic() < deadline:
            time.sleep(0.005)
            ui.draw()
        assert not app.dataset_picker.is_open and not app.dataset_picker.error
        assert app.model.batch_files == [files["batch1"]]
        assert [method for method, _ in catalogue.calls] == ["mmfdb.datasets.browse", "mmfdb.datasets.open"]
    finally:
        app.close()


def test_batch_queue_run_save_remove_and_clear_with_real_clicks(ui, files, tmp_path):
    m = loaded(ui, files, background=True)
    open_batch(ui)
    assert any(t[5].startswith("No files queued") for t in ui.draw().texts)
    ui.click_name("run")
    assert m.batch_results == []  # greyed: nothing queued
    ui.app.last_dir = str(Path(files["fast"]).parent)
    ui.click_name("batch_files.add")
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
    assert {"bg VV", "bg VH"} <= shown  # The two backgrounds remain distinguishable in the narrow pane.
    ui.app.last_dir = str(tmp_path)
    ui.click_name("save")
    ui.click_text("batch_anisotropy.tsv", last=False, fx=0.3)
    ui.app.key(0x41, "a", CTRL)
    ui.type("table.tsv")
    ui.click_text("Save")
    ui.settle()
    lines = (tmp_path / "table.tsv").read_text().splitlines()
    assert lines[0].split("\t") == [
        "file", "r_inf", "region_start", "region_stop", "bg_vv", "bg_vh", "g_factor", "error"
    ] and len(lines) == 3
    rows = list(csv.DictReader(lines, delimiter="\t"))
    for row, result in zip(rows, m.batch_results):
        assert row["file"] == result["file"]
        for quantity in ("r_inf", "region_start", "region_stop", "bg_vv", "bg_vh", "g_factor"):
            assert float(row[quantity]) == pytest.approx(result[quantity])
    # The filename is elided in this narrow seven-column table; select its real numeric cell.
    ui.click_text(f"{m.batch_results[0]['r_inf']:.5g}")
    ui.delete()
    assert ui.app.model.batch_files == [files["batch2"]] and len(ui.app.model.batch_results) == 1
    ui.click_name("batch_files.clear")
    assert ui.app.model.batch_files == [] and ui.app.model.batch_results == []


# ───────────────────────────── help, guide, settings, sizes, tooltips ───────────────────────────── #


def test_help_opens_with_live_links_and_closes(ui):
    ui.click_name("help")
    assert ui.app.help.open
    ui.click_text(action_caption("close"))
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
    loaded(ui, files)
    type_value(ui, "tail_start", "310")
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
                if s["key"] == "data_table":
                    assert all(c.get("tooltip") for c in s["options"]["columns"])
                elif s["key"] == "path_list":
                    assert s.get("description")
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
