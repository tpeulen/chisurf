"""Click coverage of the native blind IRF estimator: every control operated with pointer, keys, wheel, drags and drops.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` reach the window, and the decay is
picked in its Input section from the Datasets workspace (where a drop on ChiSurf puts it);
assertions read what is drawn, the model and the files written.
"""

from __future__ import annotations

import os
import pwd
import sys
import time
from pathlib import Path

import numpy as np
import pytest

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
# isort: off
from test.gui.emtk_port_parity import qt_free  # noqa: E402,F401  (before the plugin import)
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui as _Ui  # noqa: E402
from emtk import keys  # noqa: E402
from emtk.app import LEFT_BUTTON  # noqa: E402

from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import IRFEstimatorApp  # noqa: E402
from chisurf.plugins.emtk_layout import help_close_caption
# isort: on

DECAY = REPO / "test" / "data" / "tcspc" / "Jordi_FRETsens" / "Donor" / "D0_14_TAC1024_DexDem.dat"
SIZE = (1200, 800)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


def decay_arrays(path=DECAY):
    """The time axis and counts of a VV/VH decay file, as the workspace holds the curve."""
    from chisurf.plugins.fluorescence_decay.irf_estimator.backend.services import load_decay_handler

    data = load_decay_handler(str(path))["result"]
    y = np.asarray(data["intensity"], float)
    return np.arange(len(y)) * float(data["dt"]), y


class Ui(_Ui):
    def pick_decay(self, path=DECAY, name=None):
        """The decay at *path* is in the workspace; its row is picked in the Input section."""
        from test.gui.curve_workspace import pick_curve

        x, y = decay_arrays(path)
        dataset = pick_curve(self.app.input, x, y, name=name or Path(path).stem)
        self.draw(3)
        return dataset

    def settle(self, timeout=120.0):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.future is not None:
            assert time.monotonic() < end, "the estimate did not finish"
            time.sleep(0.01)
            self.draw(1)
        return self.draw(4)

    def drag(self, start, end, steps=8):
        self.app.pointer_move(*start)
        self.draw(1)
        self.app.pointer_press(*start, LEFT_BUTTON, 0, 1)
        self.draw(1)
        for i in range(1, steps + 1):
            self.app.pointer_move(
                start[0] + (end[0] - start[0]) * i / steps,
                start[1] + (end[1] - start[1]) * i / steps,
                LEFT_BUTTON,
            )
            self.draw(1)
        self.app.pointer_release(*end, LEFT_BUTTON, 0)
        return self.draw(3)

    def type_into(self, key, text, enter=True, replace=True, fx=0.3):
        self.draw(1)
        self.click(key, fx=fx)
        assert self.app.io.want_capture_keyboard, f"{key} did not take the keyboard"
        self.type_text(text, replace)
        if enter:
            self.key(keys.KEY_RETURN, "\r")
        return self.draw(2)


@pytest.fixture
def ui():
    ui = Ui(IRFEstimatorApp(), SIZE)
    yield ui
    ui.app.close()


@pytest.fixture
def loaded(ui):
    ui.pick_decay()
    assert ui.app.model.decay_data_original is not None
    return ui


@pytest.fixture
def estimated(loaded):
    loaded.type_into("rl_iterations", "100")
    loaded.click("request_estimate")
    loaded.settle()
    assert loaded.app.model.result is not None
    return loaded


def test_the_idle_window_offers_only_what_can_act(ui):
    form = ui.app.form_model
    assert [
        form.enabled(n) for n in ("request_estimate", "request_save", "request_transfer", "dt")
    ] == [False] * 4
    ui.click("request_estimate")
    assert ui.app.future is None and ui.app.model.result is None  # greyed: the press does nothing
    ui.click("request_save")
    ui.click("request_transfer")
    assert not ui.dialog_open
    assert ui.shown("No data loaded") or ui.shown("Time axis: Not available")


def test_guide_and_help_buttons_are_pressed(ui):
    ui.click("request_guide")
    steps = len(ui.app.tour.steps)
    assert ui.app.tour.active and ui.shown(f"Step 1 of {steps}")
    ui.press_text("Next ►")
    assert ui.app.tour.step_idx == 1
    ui.app.tour.start(3)
    ui.draw(2)
    ui.press_text("◄ Prev")
    assert ui.app.tour.step_idx == 2
    ui.press_text("Close Tour")
    assert not ui.app.tour.active
    ui.click("request_help")
    assert ui.app.help_window.open
    ui.press_text(help_close_caption(), nth=-1)
    assert not ui.app.help_window.open


def test_no_tour_card_button_is_dead_on_any_step():
    from chisurf.plugins.traj.traj_save_topology.test.real_input import dead_tour_buttons

    assert dead_tour_buttons(IRFEstimatorApp, SIZE) == []


def test_the_input_section_lists_workspace_decays_and_a_pick_loads_one(ui):
    from test.gui.curve_workspace import add_curve

    t = np.arange(50) * 0.1
    add_curve(t, np.exp(-t), name="a correlation", kind="correlation")
    ui.draw(2)
    assert not ui.app.input.workspace_input_rows()  # only decays are offered
    dataset = ui.pick_decay()
    assert ui.app.model.decay_data_original is not None
    assert ui.app.source_uid == str(dataset.unique_identifier)
    assert ui.shown(DECAY.stem)


def test_time_per_channel_is_typed_and_rescales_the_axis(loaded):
    loaded.type_into("dt", "2")
    assert loaded.app.model.dt == pytest.approx(2.0)
    assert loaded.app.model.channel_axis[1] == pytest.approx(2.0)
    assert loaded.shown("2.0000")
    loaded.type_into("dt", "99")  # above the Qt maximum of 10
    assert loaded.app.model.dt <= 10.0


@pytest.mark.parametrize(
    "key,typed,expected,low,high",
    [
        ("window_length", "21", 21, 5, 500),
        ("polyorder", "4", 4, 1, 10),
        ("rl_iterations", "300", 300, 5, 2000),
        ("regularization", "7", 7, 1, 51),
        ("manual_background", "12.5", 12.5, 0.0, 100000.0),
    ],
)
def test_each_parameter_is_typed_clamped_to_the_qt_range(loaded, key, typed, expected, low, high):
    loaded.type_into(key, typed)
    assert getattr(loaded.app.model, key) == expected
    loaded.type_into(key, str(high * 10))
    assert getattr(loaded.app.model, key) <= high
    loaded.type_into(key, "-5")
    assert getattr(loaded.app.model, key) >= low


@pytest.mark.parametrize(
    "key,step",
    [("window_length", 2), ("polyorder", 1), ("rl_iterations", 10), ("regularization", 2)],
)
def test_the_spin_arrows_step_each_parameter(loaded, key, step):
    start = getattr(loaded.app.model, key)
    loaded.arrow(key, +1)
    assert getattr(loaded.app.model, key) == start + step
    loaded.arrow(key, -1)
    assert getattr(loaded.app.model, key) == start


def test_the_wheel_steps_a_parameter(loaded):
    x, y, w, h = loaded.app.item_rects["rl_iterations"]
    loaded.app.pointer_move(x + w / 2, y + h / 2)
    loaded.draw(2)
    before = loaded.app.model.rl_iterations
    loaded.wheel_over("rl_iterations", 1)
    assert loaded.app.model.rl_iterations != before


def test_range_selection_toggle_shows_and_hides_the_channel_fields(loaded):
    assert not loaded.app.model.use_range_selection and not loaded.shown("First channel")
    loaded.click("use_range_selection")
    assert (
        loaded.app.model.use_range_selection
        and loaded.shown("First channel")
        and loaded.shown("Last channel")
    )
    loaded.click("use_range_selection")
    assert not loaded.app.model.use_range_selection and not loaded.shown("First channel")


def test_the_range_channels_are_typed_and_bounded(loaded):
    loaded.click("use_range_selection")
    loaded.type_into("first_channel", "100")
    loaded.type_into("last_channel", "600")
    assert [int(v) for v in loaded.app.model.range_bounds] == [100, 600]
    loaded.type_into("last_channel", "999999")
    assert int(loaded.app.model.range_bounds[1]) <= len(loaded.app.model.channel_axis) - 1


def _region(ui):
    """Left, right, top and bottom of the green range region as drawn (its translucent fill)."""
    fill = next(f for f in ui.last.fills if f[4][:3] == (70, 200, 90) and f[4][3] < 100)
    return fill[0], fill[0] + fill[2], fill[1], fill[1] + fill[3]


def _ranged(loaded):
    loaded.click("use_range_selection")
    loaded.type_into("first_channel", "50")
    loaded.type_into("last_channel", "500")
    return _region(loaded)


def test_dragging_the_regions_edges_in_the_plot_moves_the_range_and_the_fields(loaded):
    left, right, top, bottom = _ranged(loaded)
    mid = (top + bottom) / 2
    loaded.drag((right + 0.5, mid), (right - 100, mid))
    assert (
        int(loaded.app.model.range_bounds[1]) < 500 and int(loaded.app.model.range_bounds[0]) == 50
    )
    assert loaded.shown(str(int(loaded.app.model.range_bounds[1])))
    left, right, top, bottom = _region(loaded)
    loaded.drag((left + 0.5, mid), (left + 60, mid))
    assert int(loaded.app.model.range_bounds[0]) > 50


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: implot's drag_rect moves only by its edges and corners; the Qt "
    "LinearRegionItem also moves as a whole when its body is dragged",
)
def test_dragging_the_body_of_the_region_moves_it_as_a_whole(loaded):
    left, right, top, bottom = _ranged(loaded)
    loaded.drag(
        ((left + right) / 2, (top + bottom) / 2), ((left + right) / 2 + 60, (top + bottom) / 2)
    )
    first, last = (int(v) for v in loaded.app.model.range_bounds)
    assert first > 50 and last > 500 and last - first == 450


def test_estimate_runs_on_the_worker_and_fills_results_plot_and_buttons(loaded):
    loaded.type_into("rl_iterations", "100")
    loaded.click("request_estimate")
    assert loaded.app.future is not None and loaded.shown("Estimating IRF...")
    assert not loaded.app.form_model.enabled(
        "rl_iterations"
    )  # the parameters are greyed while it runs
    loaded.settle()
    m = loaded.app.model
    assert m.status == "IRF estimation completed" and m.result is not None
    assert loaded.shown("Estimated IRF (scaled)") and loaded.shown("IRF ⊗ Exp (Forward Model)")
    for label, text in m.result_rows():
        assert loaded.shown(text), label
    assert loaded.app.form_model.enabled("request_save") and loaded.app.form_model.enabled(
        "request_transfer"
    )


def test_auto_update_re_estimates_when_a_parameter_changes(estimated):
    estimated.click("auto_update_enabled")
    assert estimated.app.model.auto_update_enabled
    before = estimated.app.model.irf_data.copy()
    estimated.type_into("regularization", "9")
    assert estimated.app.future is not None or not np.array_equal(
        estimated.app.model.irf_data, before
    )
    estimated.settle()
    assert not np.array_equal(estimated.app.model.irf_data, before)


def test_save_irf_writes_a_vv_vh_file_and_every_way_out_works(estimated, tmp_path):
    estimated.click("request_save")
    assert estimated.dialog_open and estimated.shown("Save IRF")
    estimated.press_text("Cancel")
    assert not estimated.dialog_open
    estimated.click("request_save")
    estimated.press_text("×")
    assert not estimated.dialog_open
    target = tmp_path / "irf_out.dat"
    estimated.click("request_save")
    estimated.draw(2)
    estimated.click(estimated.text_rect(estimated.app.dialog.filename), fx=0.3)
    estimated.type_text(str(target))
    estimated.press_text("Save")
    assert (
        target.exists()
        and estimated.shown("IRF saved to")
        or "IRF saved to" in estimated.app.model.status
    )
    from chisurf.core.fio import read_vv_vh

    channels = read_vv_vh(str(target), split=True)
    vv = channels["VV"] if isinstance(channels, dict) else channels[0]
    np.testing.assert_allclose(vv, estimated.app.model.irf_data, rtol=1e-5, atol=1e-6)


def test_transfer_hands_the_irf_to_chisurf(estimated):
    got = []
    estimated.app.dataset_sink = got.append
    estimated.click("request_transfer")
    assert len(got) == 1 and len(got[0]) == 2 and estimated.shown("registered as a ChiSurf dataset")


def test_a_second_decay_picked_in_the_workspace_replaces_the_first(ui):
    from test.gui.curve_workspace import add_curve, pick

    t = np.arange(200) * 0.05
    donor = add_curve(t, np.exp(-t / 2.0) * 1000 + 3, name="donor decay")
    acceptor = add_curve(t, np.exp(-t / 4.0) * 1000 + 3, name="acceptor decay")
    ui.draw(2)
    assert ui.shown("donor decay") and ui.shown("acceptor decay")
    pick(ui.app.input, donor)
    pick(ui.app.input, acceptor)
    ui.draw(2)
    assert ui.app.model.source_text.endswith("acceptor decay")
    assert ui.app.source_uid == str(acceptor.unique_identifier)


def test_the_plot_has_axes_a_crosshair_and_zooms_with_the_wheel(estimated):
    assert estimated.shown("Time (ns)") and estimated.shown("Intensity (counts/channel)")
    x, y, w, h = estimated.app.item_rects["plot"]
    estimated.app.pointer_move(x + w * 0.4, y + h * 0.5)
    estimated.draw(3)
    assert estimated.app.pointer_text.startswith("Time: ") and estimated.shown(
        estimated.app.pointer_text
    )
    before = [s for s in estimated.last.strings if s.replace(".", "", 1).isdigit()]
    for _ in range(3):
        estimated.app.wheel(x + w * 0.4, y + h * 0.5, 1)
        estimated.draw(2)
    assert [s for s in estimated.last.strings if s.replace(".", "", 1).isdigit()] != before


def _real_chisurf_state():
    root = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"
    return {str(p): p.stat().st_mtime_ns for p in root.rglob("*")} if root.exists() else {}


def test_a_full_session_leaves_the_real_chisurf_folder_untouched(estimated, tmp_path):
    before = _real_chisurf_state()
    estimated.app.model.save(str(tmp_path / "x.dat"))
    assert _real_chisurf_state() == before


def test_qt_free():
    assert qt_free("irf_estimator")
