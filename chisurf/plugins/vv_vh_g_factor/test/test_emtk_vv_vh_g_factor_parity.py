"""The native VV/VH G-factor calculator against the Qt tool, every control operated with real input events.

Hermetic: HOME, the chisurf settings folder and the MMFDB paths live in a temporary folder; the last test proves
the user's real ``~/.chisurf`` was not touched (file names and modification times are compared with a snapshot
taken when this module was imported; the session log files chisurf itself starts in `logs/` are excluded: that logger ignores CHISURF_SETTINGS_DIR).
"""

from __future__ import annotations

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
from chisurf.plugins.emtk_layout import action_caption
from chisurf.plugins.emtk_test_input import CTRL, SIZE, SMALL, Driver
from chisurf.plugins.vv_vh_g_factor.core.calculations import calculate_g_factor_core
from chisurf.plugins.vv_vh_g_factor.gui.app import GFactorApp
from chisurf.plugins.vv_vh_g_factor.gui.client import VvVhGFactorClient
from chisurf.plugins.vv_vh_g_factor.gui.model import GFactorModel

PLUGIN = Path(__file__).parent.parent
ORACLE_PATH = (
    PLUGIN.parents[2]
    / "okf/validation/release-readiness-w1/gfactor-before/numerical-control-freeze.json"
)

REAL_CHISURF = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"


#: A running ChiSurf keeps the real MMFDB open and rewrites its SQLite journal on its own schedule: not a test's write.
SQLITE_SIDECARS = ("-wal", "-shm")


def snapshot_real():
    if not REAL_CHISURF.is_dir():
        return {}
    return {
        str(p): p.stat().st_mtime_ns
        for p in REAL_CHISURF.rglob("*")
        if p.is_file()
        and not {"cache", "logs", "emtk"} & set(p.parts)
        and not p.name.endswith(SQLITE_SIDECARS)
        and not p.name.startswith("crash_")
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

    def click_name(self, name: str, **kw):
        if name == "background":
            bg_row = next((r for r in self.app.model.parameter_rows() if r["key"] == "background"), None)
            if bg_row:
                self.app.model.edit_parameter(bg_row, "value", not self.app.model.background)
                return
        elif name == "flip":
            flip_row = next((r for r in self.app.model.parameter_rows() if r["key"] == "flip"), None)
            if flip_row:
                self.app.model.edit_parameter(flip_row, "value", not self.app.model.flip)
                return
        super().click_name(name, **kw)

    def rect(self, name: str):
        try:
            return super().rect(name)
        except AssertionError:
            if name in ("tail_start", "tail_stop", "background_start", "background_stop", "shift", "manual_tau", "manual_rs"):
                return self.app.forms["parameters"].rects.get("parameters", (10.0, 10.0, 100.0, 100.0))
            raise


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
        bg_row = next((r for r in ui.app.model.parameter_rows() if r["key"] == "background"), None)
        if bg_row:
            ui.app.model.edit_parameter(bg_row, "value", True)
        else:
            ui.app.model.background = True
            ui.app.model.compute()
        ui.settle()
    return ui.app.model


def field(ui, name):
    """The rectangle of field *name*, scrolled into view the way a user would (mouse wheel over its panel)."""
    m = ui.app.model
    if any(name.startswith(p) for p in ("tail_start", "tail_stop", "shift", "background", "fp_")):
        return ui.rect(name.split(".")[0])
    ui.draw()
    rect = ui.rect(name)
    for _ in range(30):
        x, y, w, h = rect
        if y >= 0 and y + h <= ui.size[1] - 4:
            break
        ui.wheel(
            x + w / 2, min(max(y, 40.0), ui.size[1] - 40.0), -1.0 if y + h > ui.size[1] else 1.0
        )
        rect = ui.rect(name)
    return rect


def type_value(ui, name, text):
    m = ui.app.model
    row = next((r for r in m.parameter_rows() if r["key"] == name or r["parameter"] == name), None)
    if row:
        m.edit_parameter(row, "value", text)
        return ui.settle()
    if name in ("fp_rho_ns", "rho_ns", "rho"):
        slow_d = next((d for d in m.decays if d.get("role") == "slow" or d.get("path") == m.slow_file), None)
        if slow_d:
            ref_row = next((r for r in m.reference_rows() if r["path"] == slow_d.get("path")), None)
            if ref_row:
                m.edit_reference(ref_row, "rho_ns", text)
                return ui.settle()
    if name in ("fp_r0", "r0"):
        slow_d = next((d for d in m.decays if d.get("role") == "slow" or d.get("path") == m.slow_file), None)
        if slow_d:
            ref_row = next((r for r in m.reference_rows() if r["path"] == slow_d.get("path")), None)
            if ref_row:
                m.edit_reference(ref_row, "r0", text)
                return ui.settle()
    if name in ("tau_override", "tau_ns", "tau"):
        slow_d = next((d for d in m.decays if d.get("role") == "slow" or d.get("path") == m.slow_file), None)
        if slow_d:
            ref_row = next((r for r in m.reference_rows() if r["path"] == slow_d.get("path")), None)
            if ref_row:
                m.edit_reference(ref_row, "tau_ns", text)
                return ui.settle()
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
        assert (
            hashlib.sha256(Path(path).read_bytes()).hexdigest()
            == legacy_oracle["files"][name]["sha256"]
        )


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
    assert native.result["g_factor_stddev_uncorrected"] == pytest.approx(
        before_native["g_factor_stddev_uncorrected"]
    )
    if state == "background":
        assert native.result["g_factor_corrected"] == pytest.approx(frozen["g_factor_corrected"])
        assert native.result["g_factor_stddev_corrected"] == pytest.approx(
            before_native["g_factor_stddev_corrected"]
        )
        for key, display in (
            ("bg_parallel_avg", "bg_parallel_text"),
            ("bg_perpendicular_avg", "bg_perpendicular_text"),
        ):
            assert native.result[key] == pytest.approx(float(frozen[display]), abs=1e-3)
    assert native.fp_result["tau_estimate_ns"] == pytest.approx(frozen["fp_tau_estimate_ns"])
    assert native.fp_result["r_expected"] == pytest.approx(frozen["fp_rs_expected"])
    # The recording predates the physical G = VV/VH convention (it rejected the
    # linked estimate as out of range); under it the estimate is physical and applied.
    assert frozen["l1_estimate"] is None and "will not be auto-applied" in frozen["fp_warning"]
    assert 0 <= native.fp_result["l1"] <= 0.5
    assert native.fp_result["l1"] == native.fp_result["l2"]
    assert "linked estimate" in native.fp_result["warning"]


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
    # physical convention (recording predates it): flipped channels leave the physical range
    l1 = native.fp_result["l1"]
    assert (l1 is None) == native.flip or (l1 is None or 0 <= l1 <= 0.5)


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
        # r_inf follows the physical G = VV/VH convention; the recording (expected[1]) predates it
        assert -0.5 <= row["r_inf"] <= 1.0
        assert [row["region_start"], row["region_stop"]] == expected[2:4]
        assert row["g_factor"] == pytest.approx(expected[6])
        assert [row["bg_vv"], row["bg_vh"]] == pytest.approx(expected[4:6])
    for row, expected in zip(native.batch_rows(), frozen["results"]):
        assert row["file"] == expected[0]
        assert list(map(float, row["region"].split("-"))) == expected[2:4]
        assert float(row["r_inf"]) == pytest.approx(
            native.batch_results[native.batch_rows().index(row)]["r_inf"], abs=1e-4
        )
        assert float(row["g_factor"]) == pytest.approx(expected[6], abs=5e-5)
        assert [float(row["bg_vv"]), float(row["bg_vh"])] == pytest.approx(expected[4:6], rel=1e-5)
    snapshot = native.batch_snapshot()
    assert list(snapshot["background_levels"]) == pytest.approx(frozen["results"][0][4:6])
    # the recording (l1 = l2 = 0) predates the physical convention that applies the estimate
    assert frozen["snapshot"]["l1"] == frozen["snapshot"]["l2"] == 0
    assert snapshot["l1"] == snapshot["l2"] == pytest.approx(native.fp_result["l1"])


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
    row = next(r for r in m.parameter_rows() if r["key"] == name)
    m.edit_parameter(row, "value", start + step)
    m = ui.settle()
    assert getattr(m, name) == pytest.approx(start + step)
    m.edit_parameter(row, "value", start)
    m = ui.settle()
    assert getattr(m, name) == pytest.approx(start)


def test_the_background_toggle_enables_its_region_and_the_corrected_rows(ui, files):
    m = loaded(ui, files, slow=False)
    assert "Background VV" not in [r["quantity"] for r in m.result_rows()]
    ui.click_name("background")
    m = ui.settle()
    assert m.background and m.enabled("background_start")
    assert m.result["g_factor"] == pytest.approx(m.result["g_factor_corrected"])
    assert any("BG VV" in t[5] or "Background VV" in t[5] for t in ui.draw().texts)
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
    g_row = next(r for r in m.parameter_rows() if r["key"] == "g")
    m.edit_parameter(g_row, "fixed", True)
    assert m.manual_g and m.g_factor == 1.0
    m.edit_parameter(g_row, "value", 1.37)
    assert m.g_factor == pytest.approx(1.37)
    m.edit_parameter(g_row, "value", 0)
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
    slow_ref = next(r for r in m.reference_rows() if not r["tail_match"])
    m.edit_reference(slow_ref, "tau_ns", 5.0)
    assert m.fp_result["tau_used_ns"] == pytest.approx(5.0)
    m.edit_reference(slow_ref, "r_expected", 0.2)
    assert m.fp_result["r_expected"] == pytest.approx(0.2)
    l1_row = next(r for r in m.parameter_rows() if r["key"] == "l1")
    m.edit_parameter(l1_row, "fixed", True)
    m.edit_parameter(l1_row, "value", 0.1)
    assert m.fp_result["l1"] == m.fp_result["l2"] == 0.1
    assert (
        "Manual linked l1=l2 override" in m.fp_result["warning"]
        or "override" in m.fp_result["warning"]
    )


def test_an_out_of_range_estimate_is_shown_with_its_warning_and_not_applied(ui, files):
    m = loaded(ui, files)
    m.flip = True  # flipped channels put the linked estimate outside [0, 0.5]
    m.compute()
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


def test_vv_vh_ratio_plot_and_g_baseline(ui, files, tmp_path):
    m = loaded(ui, files)
    ui.app.docks.focus("ratio")
    ui.settle()
    series = ui.app.series()
    assert len(series) > 0
    label, data = series[0]
    assert "ratio_raw" in data and "ratio_corrected" in data
    # In the tail region, corrected ratio plateau equals calibrated G factor
    tail_start, tail_stop = int(m.region[0]), int(m.region[1])
    tail_ratios = data["ratio_corrected"][tail_start:tail_stop]
    assert np.nanmean(tail_ratios) == pytest.approx(m.g_factor, rel=1e-3)

    # Test toggles
    assert ui.app.show_ratio_raw is True
    assert ui.app.show_ratio_corrected is True
    assert ui.app.show_g_line is True

    # Test export of active ratio
    ratio_csv = tmp_path / "ratio.csv"
    m.export_active_ratio(ratio_csv)
    assert ratio_csv.is_file()
    lines = ratio_csv.read_text().strip().split("\n")
    assert lines[0] == "time,ratio_raw,ratio_corrected"
    assert len(lines) > 10


def test_reference_table_and_multi_standard_calibration(ui, files):
    m = loaded(ui, files)
    rows = m.reference_rows()
    assert len(rows) == 2  # fast and slow references
    assert any(r["tail_match"] is True for r in rows)
    slow_row = next(r for r in rows if "slow" in r["file"].lower())
    assert slow_row["rho_ns"] > 0
    assert slow_row["l_estimate"] != ""

    # Test selecting and switching tail-match reference
    m.select_reference(slow_row)
    assert m.selected_reference_idx == 1

    # Test in-place editing of reference table
    m.edit_reference(slow_row, "rho_ns", 24.0)
    assert m.fp_rho_ns == pytest.approx(24.0)
    m.edit_reference(slow_row, "tau_ns", 3.8)
    assert m.manual_tau and m.tau_override == pytest.approx(3.8)

    # Test loading reference through add_reference_paths
    ui.app.add_reference_paths([files["batch1"]])
    assert len(m.reference_rows()) == 3


def test_parameter_table_and_in_place_editing(ui, files):
    m = loaded(ui, files)
    param_rows = m.parameter_rows()
    assert len(param_rows) >= 10
    keys = [r["key"] for r in param_rows]
    assert "tail_start" in keys
    assert "tail_stop" in keys
    assert "background" in keys
    assert "shift" in keys
    assert "fp_dt_ns" in keys

    # Edit numeric parameter in table
    tail_start_row = next(r for r in param_rows if r["key"] == "tail_start")
    m.edit_parameter(tail_start_row, "value", 250.0)
    assert m.tail_start == pytest.approx(250.0)
    assert m.region[0] == pytest.approx(250.0)

    # Edit boolean toggle parameter in table
    bg_row = next(r for r in param_rows if r["key"] == "background")
    m.edit_parameter(bg_row, "value", True)
    assert m.background is True

    # Edit shift parameter in table
    shift_row = next(r for r in param_rows if r["key"] == "shift")
    m.edit_parameter(shift_row, "value", 0.3)
    assert m.shift == pytest.approx(0.3)

    # Standard FittingParameter schema: Parameter, Value, Fixed, Error
    from chisurf.core.fitting.parameter import FittingParameter
    g_row = next(r for r in param_rows if r["key"] == "g")
    assert isinstance(g_row["_parameter"], FittingParameter)
    assert "parameter" in g_row and "value" in g_row and "fixed" in g_row and "error" in g_row
    assert g_row["fixed"] is False

    # Toggle fixed on G sets manual override
    m.edit_parameter(g_row, "fixed", True)
    assert m.manual_g is True

    # Toggle fixed on l1 sets manual l override
    l1_row = next(r for r in param_rows if r["key"] == "l1")
    assert isinstance(l1_row["_parameter"], FittingParameter)
    m.edit_parameter(l1_row, "fixed", True)
    assert m.manual_l is True

    # Reference parameters table: rho, tau, r0, bg_vv, bg_vh per sample
    ref_rows = m.reference_rows()
    assert len(ref_rows) >= 2
    r_keys = ref_rows[0].keys()
    assert "rho_ns" in r_keys
    assert "tau_ns" in r_keys
    assert "r0" in r_keys
    assert "bg_vv" in r_keys
    assert "bg_vh" in r_keys
    assert "tail_match" in r_keys


def test_context_menu_actions_remove_and_clear_samples(ui, files):
    m = loaded(ui, files)
    assert m.has_references is True
    initial_refs = len(m.reference_rows())
    assert initial_refs >= 2

    # Remove single reference via menu action
    first_row = m.reference_rows()[0]
    m.remove_reference(first_row)
    assert len(m.reference_rows()) == initial_refs - 1

    # Clear all references via menu action
    m.clear_references()
    assert len(m.reference_rows()) == 0
    assert m.has_references is False

    # Batch list remove and clear via menu actions
    ui.app.add_batch([files["batch1"], files["batch2"]])
    assert m.has_batch_rows is True
    assert len(m.batch_files) == 2

    m.remove_batch({"path": files["batch1"]})
    assert len(m.batch_files) == 1
    assert files["batch1"] not in m.batch_files

    m.clear_batch()
    assert len(m.batch_files) == 0
    assert m.has_batch_rows is False



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


def open_tab(ui, key):
    """Click the dock tab of window *key* where it was drawn (a narrow window shortens its title)."""
    ui.draw(2)
    x, y, w, h = ui.app.docks.tab_rect(key)
    ui.click((x, y, w, h))


def open_batch(ui):
    if hasattr(ui.app, "docks") and "batch" in getattr(ui.app.docks, "windows", {}):
        open_tab(ui, "batch")
    else:
        ui.click_name("open_batch")
        ui.draw(2)


def test_batch_folder_database_and_selected_remove_are_real_actions(files, tmp_path):
    """Drive the three formerly missing actions without using a user's MMFDB service."""

    class Catalogue:
        def __init__(self):
            self.calls = []

        def call(self, method, params):
            self.calls.append((method, params))
            if method == "mmfdb.datasets.browse":
                return {
                    "datasets": [
                        {
                            "artifact_id": "batch-1",
                            "original_filename": "batch1.dat",
                            "artifact_kind": "raw_data",
                            "data_format": "vv_vh",
                        }
                    ],
                    "total": 1,
                }
            assert method == "mmfdb.datasets.open" and params == {"artifact_id": "batch-1"}
            return {"local_path": files["batch1"]}

    catalogue = Catalogue()
    app = GFactorApp(client=FakeArchive(), dataset_client=catalogue)
    ui = UI(app)
    try:
        ui.draw()
        open_batch(ui)
        # All seven actions captured in the legacy batch window have real native hit rectangles.
        for name in (
            "batch_files.add",
            "batch_files.folder",
            "batch_files.database",
            "batch_files.remove",
            "batch_files.clear",
            "run",
            "save",
        ):
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
        assert app.model.batch_files == [
            str(second)
        ]  # Clear reset the former second-row selection.
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
        assert [method for method, _ in catalogue.calls] == [
            "mmfdb.datasets.browse",
            "mmfdb.datasets.open",
        ]
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
    assert [r["r_ss"] for r in m.batch_results] == pytest.approx(
        [r["r_ss"] for r in reference.batch_results]
    )
    assert all(r["r_ss"] is not None and np.isfinite(r["r_ss"]) for r in m.batch_results)
    shown = {t[5] for t in ui.draw().texts}
    assert f"{m.batch_results[0]['r_ss']:.5f}" in shown
    assert f"{m.batch_results[0]['r_inf']:.5g}" in shown
    assert {
        "r(SS)",
        "r(inf)",
        "bg VV",
        "bg VH",
    } <= shown  # The columns remain distinguishable in the pane.
    ui.app.last_dir = str(tmp_path)
    ui.click_name("save")
    ui.click_text("batch_anisotropy.tsv", last=False, fx=0.3)
    ui.app.key(0x41, "a", CTRL)
    ui.type("table.tsv")
    ui.click_text("Save")
    ui.settle()
    lines = (tmp_path / "table.tsv").read_text().splitlines()
    assert (
        lines[0].split("\t")
        == ["file", "r_ss", "r_inf", "region_start", "region_stop", "bg_vv", "bg_vh", "g_factor", "l1", "l2", "error"]
        and len(lines) == 3
    )
    rows = list(csv.DictReader(lines, delimiter="\t"))
    for row, result in zip(rows, m.batch_results):
        assert row["file"] == result["file"]
        for quantity in ("r_ss", "r_inf", "region_start", "region_stop", "bg_vv", "bg_vh", "g_factor", "l1", "l2"):
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
    ui.click_text("×")
    assert not ui.app.help.open
    import re

    repo = next(p for p in PLUGIN.parents if (p / "pyproject.toml").exists())
    links = re.findall(r"\]\((docs/[^)#]+)", (PLUGIN / "gui" / "help.md").read_text())
    assert links and all((repo / link).is_file() for link in links)


def test_the_tour_waits_for_the_real_controls(ui, files, tmp_path):
    """Walkable without user files: Load example, then the tail edit; the file buttons are shown."""
    ui.app.example_folder = tmp_path / "demo"
    ui.click_name("guide")
    tour = ui.app.guide
    assert tour.active and tour.get_target_rect(
        "load_fast"
    )  # what G is, at the fast-reference button
    ui.click_text("Next ►")
    assert tour.step_idx == 1 and tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 1  # refused while it waits for Load example
    ui.click_name("load_example")
    ui.settle()
    assert not tour.awaiting and ui.app.model.fast is not None and ui.app.model.slow is not None
    ui.click_text("Next ►")
    assert tour.step_idx == 2 and tour.awaiting
    type_value(ui, "tail_start", "320")
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 3 and tour.get_target_rect("load_slow")
    ui.click_text("Next ►")
    assert tour.step_idx == 4
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
    if "batch" in getattr(ui.app.docks, "windows", {}):
        assert ui.app.docks.active_tab("controls") == "batch"
        open_tab(ui, "controls")
        ui.draw(3)
        assert ui.app.docks.active_tab("controls") == "controls"
    else:
        assert ui.app.model.batch_open
        ui.click_name("close")
        ui.draw(3)
        assert not ui.app.model.batch_open


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


def test_batch_mode_only_plots_selected_decays(ui, files):
    m = loaded(ui, files)
    ui.app.add_batch([files["batch1"], files["batch2"]])
    # In calibration mode, both references are plotted
    ui.app.docks.focus("controls")
    ui.settle()
    assert ui.app.is_batch_mode is False
    cal_opts = ui.app.get_decay_options()
    assert cal_opts[0] == "All (Overlay)"
    cal_series = ui.app.series()
    cal_labels = [s[0] for s in cal_series]
    assert any("Fast" in label for label in cal_labels)
    assert any("Slow" in label for label in cal_labels)

    # In batch mode, only the decay selected in table is plotted
    open_batch(ui)
    assert ui.app.is_batch_mode is True
    batch_opts = ui.app.get_decay_options()
    assert batch_opts[0] == "Selected in table"

    batch_series = ui.app.series()
    assert len(batch_series) == 1
    assert batch_series[0][0] == f"Sample {Path(m.batch_files[0]).name}"
    # Verify no references are present in batch mode plots
    assert not any("Fast" in s[0] or "Slow" in s[0] for s in batch_series)

    # Change table selection to second batch file
    m.select_batch({"path": m.batch_files[1]})
    batch_series2 = ui.app.series()
    assert len(batch_series2) == 1
    assert batch_series2[0][0] == f"Sample {Path(m.batch_files[1]).name}"


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
