"""The VV/VH G-factor calculator, every control operated with real input events.

The decays are generated (:func:`make_data`) with a planted G = VV/VH = 1.2 and 3 background counts per channel;
G is checked against that and against the documented tail-matching formula recomputed here: the mean of the
channel ratios VV/VH over the tail region (valid where VH > 0 and the ratio > 0), and, with background
correction, the same after subtracting the mean counts of the background region from each channel (floored at 0).

Hermetic: HOME, the chisurf settings folder and the MMFDB paths live in a temporary folder; the last test proves
the user's real ``~/.chisurf`` was not touched (file names and modification times are compared with a snapshot
taken when this module was imported; the session log files chisurf itself starts in `logs/` are excluded: that logger ignores CHISURF_SETTINGS_DIR).
"""

from __future__ import annotations

import csv
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
            bg_row = next(
                (r for r in self.app.model.parameter_rows() if r["key"] == "background"), None
            )
            if bg_row:
                self.app.model.edit_parameter(bg_row, "value", not self.app.model.background)
                return
        elif name == "flip":
            flip_row = next(
                (r for r in self.app.model.parameter_rows() if r["key"] == "flip"), None
            )
            if flip_row:
                self.app.model.edit_parameter(flip_row, "value", not self.app.model.flip)
                return
        super().click_name(name, **kw)

    def rect(self, name: str):
        try:
            return super().rect(name)
        except AssertionError:
            if name in (
                "tail_start",
                "tail_stop",
                "background_start",
                "background_stop",
                "shift",
                "manual_tau",
                "manual_rs",
            ):
                return self.app.forms["parameters"].rects.get(
                    "parameters", (10.0, 10.0, 100.0, 100.0)
                )
            raise


@pytest.fixture
def ui():
    FakeArchive.calls = []
    app = GFactorApp(client=FakeArchive())
    driver = UI(app)
    driver.draw()
    yield driver
    app.close()


#: The Input section each former file button became.
SECTION = {"load_fast": "reference", "load_slow": "slow", "batch": "batch"}


def pick_file(ui, button, name, directory):
    """The file is in the Datasets workspace (as a drop puts it) and its row is picked in the
    Input section that replaced *button*; then the load finishes."""
    from chisurf.core.plugin.workspace_input import register_result
    from test.gui.curve_workspace import pick

    row = register_result(str(Path(directory) / name), kind="decay", name=name)
    pick(ui.app.inputs[SECTION[button]], row)
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
        slow_d = next(
            (d for d in m.decays if d.get("role") == "slow" or d.get("path") == m.slow_file), None
        )
        if slow_d:
            ref_row = next((r for r in m.reference_rows() if r["path"] == slow_d.get("path")), None)
            if ref_row:
                m.edit_reference(ref_row, "rho_ns", text)
                return ui.settle()
    if name in ("fp_r0", "r0"):
        slow_d = next(
            (d for d in m.decays if d.get("role") == "slow" or d.get("path") == m.slow_file), None
        )
        if slow_d:
            ref_row = next((r for r in m.reference_rows() if r["path"] == slow_d.get("path")), None)
            if ref_row:
                m.edit_reference(ref_row, "r0", text)
                return ui.settle()
    if name in ("tau_override", "tau_ns", "tau"):
        slow_d = next(
            (d for d in m.decays if d.get("role") == "slow" or d.get("path") == m.slow_file), None
        )
        if slow_d:
            ref_row = next((r for r in m.reference_rows() if r["path"] == slow_d.get("path")), None)
            if ref_row:
                m.edit_reference(ref_row, "tau_ns", text)
                return ui.settle()
    ui.type_into(field(ui, name), text)
    return ui.settle()


# ───────────────────────────── G from the planted data and the formula ───────────────────────────── #

#: What :func:`make_data` plants.
PLANTED_G, PLANTED_BACKGROUND = 1.2, 3.0


def tail_g(vv, vh, region, background_region=None):
    """G by tail matching (no shift): the mean valid VV/VH ratio over ``region``, background-corrected if asked."""
    full_vv, full_vh = np.asarray(vv, float), np.asarray(vh, float)
    lo, hi = (int(round(v)) for v in region)
    vv, vh = full_vv[lo:hi], full_vh[lo:hi]
    bg = (0.0, 0.0)
    if background_region is not None:
        b0, b1 = (int(round(v)) for v in background_region)
        bg = (float(np.mean(full_vv[b0:b1])), float(np.mean(full_vh[b0:b1])))
        vv, vh = np.maximum(vv - bg[0], 0.0), np.maximum(vh - bg[1], 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = vv / vh
    ratio = ratio[np.isfinite(ratio) & (ratio > 0)]
    return float(np.mean(ratio)), bg


def model_with(files, **settings):
    native = GFactorModel()
    native.fp_dt_ns = 0.05
    native.load(files["fast"])
    native.load(files["slow"], slow=True)
    for key, value in settings.items():
        setattr(native, key, value)
    native.compute()
    return native


def test_nothing_is_calculated_before_a_reference_is_loaded():
    native = GFactorModel()
    assert native.g_factor is None and native.result == {} and native.fp_result == {}


def test_g_of_the_shipped_reference_file_follows_the_tail_formula():
    native = GFactorModel()
    native.load(PLUGIN / "test_vv_vh_data.dat")
    g, _ = tail_g(*native.channels(), native.region)
    assert native.result["g_factor_uncorrected"] == pytest.approx(g, rel=1e-12)
    assert native.g_factor == pytest.approx(g, rel=1e-12)
    assert native.result["g_factor_stddev_uncorrected"] > 0


@pytest.mark.parametrize("background", [False, True])
def test_g_follows_the_tail_formula_and_recovers_the_planted_g(files, background):
    native = model_with(files, background=background)
    vv, vh = native.channels()
    g, _ = tail_g(vv, vh, native.region)
    assert native.result["g_factor_uncorrected"] == pytest.approx(g, rel=1e-12)
    if background:
        g_bg, (bg_vv, bg_vh) = tail_g(vv, vh, native.region, native.background_region)
        assert native.result["bg_parallel_avg"] == pytest.approx(bg_vv, rel=1e-12)
        assert native.result["bg_perpendicular_avg"] == pytest.approx(bg_vh, rel=1e-12)
        assert (bg_vv, bg_vh) == (pytest.approx(PLANTED_BACKGROUND, abs=0.5),) * 2
        assert native.result["g_factor_corrected"] == pytest.approx(g_bg, rel=1e-12)
        assert native.g_factor == native.result["g_factor_corrected"]
    else:
        assert native.result["g_factor_corrected"] is None and native.g_factor == pytest.approx(g)
    assert native.g_factor == pytest.approx(PLANTED_G, rel=0.03)
    # the slow reference gives the linked mixing estimate, inside the physical range
    assert 0 <= native.fp_result["l1"] <= 0.5 and native.fp_result["l1"] == native.fp_result["l2"]
    assert "linked estimate" in native.fp_result["warning"]
    assert native.fp_result["tau_estimate_ns"] > 0 and 0 < native.fp_result["r_expected"] < 0.4


@pytest.mark.parametrize("shift,flip", [(0.4, False), (0.0, True), (-1.5, True)])
def test_shift_and_flip_recompute_g(files, shift, flip):
    native = model_with(files, shift=shift, flip=flip)
    if flip:  # VV and VH swapped: the ratio inverts
        assert native.g_factor == pytest.approx(1.0 / PLANTED_G, rel=0.03)
        assert native.fp_result["l1"] is None  # the swapped channels leave the physical range
    else:
        assert native.g_factor == pytest.approx(PLANTED_G, rel=0.03)
        assert 0 <= native.fp_result["l1"] <= 0.5
    if shift == 0.0:  # channels() hands the decays out already swapped
        g, _ = tail_g(*native.channels(), native.region)
        assert native.g_factor == pytest.approx(g, rel=1e-12)


def test_batch_rows_use_the_calibration_and_rank_the_planted_rotations(files):
    native = model_with(files, background=True)
    native.batch_files = [files["batch1"], files["batch2"]]
    native.compute_batch()
    assert [Path(row["file"]).name for row in native.batch_results] == ["batch1.dat", "batch2.dat"]
    for row in native.batch_results:
        assert row["error"] == ""
        assert [row["region_start"], row["region_stop"]] == native.region
        assert row["g_factor"] == pytest.approx(native.g_factor)
        assert [row["bg_vv"], row["bg_vh"]] == pytest.approx(
            [native.result["bg_parallel_avg"], native.result["bg_perpendicular_avg"]]
        )
        assert row["l1"] == row["l2"] == pytest.approx(native.fp_result["l1"])
        assert -0.5 <= row["r_inf"] <= 1.0 and 0 < row["r_ss"] < 0.4
    # batch1 rotates in 8 ns, batch2 in 30 ns: the slower one keeps more anisotropy
    first, second = native.batch_results
    assert first["r_ss"] < second["r_ss"] and first["r_inf"] < second["r_inf"]
    for row, result in zip(native.batch_rows(), native.batch_results):
        assert row["file"] == Path(result["file"]).name
        assert list(map(float, row["region"].split("-"))) == native.region
        assert float(row["r_inf"]) == pytest.approx(result["r_inf"], abs=1e-4)
        assert float(row["g_factor"]) == pytest.approx(result["g_factor"], abs=5e-5)
    snapshot = native.batch_snapshot()
    assert list(snapshot["background_levels"]) == pytest.approx(
        [native.result["bg_parallel_avg"], native.result["bg_perpendicular_avg"]]
    )
    assert snapshot["l1"] == snapshot["l2"] == pytest.approx(native.fp_result["l1"])


# ───────────────────────────────────── loading ───────────────────────────────────── #


def test_the_fast_reference_picked_in_the_workspace_gives_the_calculated_g(ui, files):
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
    assert m.slow_file == files["slow"] and m.fp_result["tau_estimate_ns"] > 0
    assert m.fp_result["r_expected"] is not None


def test_a_file_that_is_not_vv_vh_data_is_reported(ui, tmp_path):
    bad = tmp_path / "bad.dat"
    bad.write_text("1 2\n")
    m = pick_file(ui, "load_fast", "bad.dat", tmp_path)
    assert m.fast is None and m.message.startswith("Error")
    assert m.message in [t[5] for t in ui.draw().texts] or any(
        m.message[:40] in t[5] for t in ui.draw().texts
    )


def test_handed_over_files_load_fast_then_slow_and_queue_the_batch(ui, files):
    from chisurf.plugins.vv_vh_g_factor.gui.app import (
        receive_batch,
        receive_reference,
        receive_slow,
    )

    for name in ("files_dropped", "on_files_dropped", "on_paths_dropped"):
        assert not callable(getattr(ui.app, name, None)), name  # files come from the workspace
    receive_reference(ui.app, {"file": [files["fast"]]})
    receive_slow(ui.app, {"file": [files["slow"]]})
    receive_batch(ui.app, {"files": [files["batch1"]]})
    ui.settle()
    ui.settle()
    assert ui.app.model.fast_file == files["fast"]
    assert ui.app.model.slow_file == files["slow"] and ui.app.model.batch_files == [files["batch1"]]


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
    param_keys = [r["key"] for r in param_rows]
    assert "tail_start" in param_keys
    assert "tail_stop" in param_keys
    assert "background" in param_keys
    assert "shift" in param_keys
    assert "fp_dt_ns" in param_keys

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


def test_batch_input_queues_and_selected_remove_and_clear_are_real_actions(ui, files):
    from chisurf.core.plugin.workspace_input import register_result
    from test.gui.curve_workspace import pick

    app = ui.app
    open_batch(ui)
    for name in ("batch_files.remove", "batch_files.clear", "run", "save"):
        assert ui.rect(name)[2] > 0, name
    for name in ("batch_files.add", "batch_files.folder", "batch_files.database"):
        assert name not in app.item_rects, name  # the batch comes from the workspace
    rows = [
        register_result(files[k], kind="decay", name=Path(files[k]).name)
        for k in ("batch1", "batch2")
    ]
    pick(app.inputs["batch"], *rows)
    ui.draw()
    assert app.model.batch_files == [files["batch1"], files["batch2"]]
    ui.click_name("batch_files.1")
    ui.click_name("batch_files.remove")
    assert app.model.batch_files == [files["batch1"]] and Path(files["batch2"]).is_file()
    ui.click_name("batch_files.clear")
    assert app.model.batch_files == []


def test_batch_queue_run_save_remove_and_clear_with_real_clicks(ui, files, tmp_path):
    m = loaded(ui, files, background=True)
    open_batch(ui)
    assert any(t[5].startswith("No files queued") for t in ui.draw().texts)
    ui.click_name("run")
    assert m.batch_results == []  # greyed: nothing queued
    folder = Path(files["fast"]).parent
    for name in ("batch1.dat", "batch2.dat"):
        pick_file(ui, "batch", name, folder)
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
        == [
            "file",
            "r_ss",
            "r_inf",
            "region_start",
            "region_stop",
            "bg_vv",
            "bg_vh",
            "g_factor",
            "l1",
            "l2",
            "error",
        ]
        and len(lines) == 3
    )
    rows = list(csv.DictReader(lines, delimiter="\t"))
    for row, result in zip(rows, m.batch_results):
        assert row["file"] == result["file"]
        for quantity in (
            "r_ss",
            "r_inf",
            "region_start",
            "region_stop",
            "bg_vv",
            "bg_vh",
            "g_factor",
            "l1",
            "l2",
        ):
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
        "reference.workspace_input_rows"
    )  # what G is, at the fast-reference input
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
    assert tour.step_idx == 3 and tour.get_target_rect("slow.workspace_input_rows")
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
