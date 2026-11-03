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
from emtk.testing import RecordingPainter  # noqa: E402

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
    loaded.type_into("dt", "99")  # above the maximum of 10
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
def test_each_parameter_is_typed_clamped_to_its_range(loaded, key, typed, expected, low, high):
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
    reason="emtk gap: implot's drag_rect moves only by its edges and corners; the range "
    "region should also move as a whole when its body is dragged",
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


def test_importing_and_drawing_the_app_pulls_in_no_qt():
    result = qt_free("irf_estimator")
    assert result["ok"], result["output"]


# -- the app driven through its entry points (the workspace hand-off, the form, the model) -------------- #


def _draw(app, size=SIZE, n=2):
    out = None
    for _ in range(n):
        out = RecordingPainter()
        app.draw(out, 0, 0, *size)
    return out


def _click(app, key, size=SIZE):
    """Press and release the centre of the control drawn under *key*, as a pointer does."""
    _draw(app, size)
    x, y, w, h = app.item_rects[key]
    app.pointer_move(x + w / 2, y + h / 2)
    app.press(x + w / 2, y + h / 2)
    _draw(app, size, n=1)
    app.release()
    _draw(app, size, n=1)


def _wait(app, timeout=120.0):
    end = time.monotonic() + timeout
    while app.future is not None and time.monotonic() < end:
        _draw(app, n=1)
        time.sleep(0.01)
    assert app.future is None
    _draw(app, n=1)


def _states(app):
    form = app.form_model
    return [form.enabled(name) for name in ("request_estimate", "request_save", "request_transfer")]


def _receive(app, address):
    """What a pick in the Input section does: the workspace hands the decay's address over."""
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import receive_decay

    receive_decay(app, {"decay": str(address)})


def _loaded(**kwargs):
    app = IRFEstimatorApp(**kwargs)
    _receive(app, DECAY)
    return app


@pytest.fixture(scope="module")
def tail_file(tmp_path_factory):
    """A VV/VH decay whose last tenth is a 7-9 count floor, so a file's background estimate shows."""
    from chisurf.core.fio import write_vv_vh

    t = np.arange(512.0)
    counts = np.round(
        2000.0 * np.exp(-(((t - 40.0) / 6.0) ** 2))
        + 900.0 * np.exp(-np.clip(t - 40.0, 0, None) / 60.0) * (t > 40)
        + 7.0
        + (t % 3)
    )
    path = tmp_path_factory.mktemp("tail") / "tail.dat"
    write_vv_vh(str(path), vv=counts, vh=counts)
    return str(path)


def test_a_handed_over_file_sets_label_time_axis_and_the_enabled_actions():
    app = IRFEstimatorApp()
    try:
        assert _states(app) == [False, False, False]
        assert app.model.time_axis_text() == "Time axis: Not available"
        assert app.model.source_text == "No data loaded"
        _receive(app, DECAY)
        assert _states(app) == [True, False, False]
        assert app.model.source_text == str(DECAY)
        n = len(app.model.decay_data_original)
        assert f"dt = {app.model.dt:.4f} ns" in app.model.time_axis_text()
        assert f"{n} pts" in app.model.time_axis_text()
        app.form_model.rl_iterations = 100
        app.form_model.use_range_selection = True
        _click(app, "request_estimate")
        assert app.future is not None
        _wait(app)
        assert _states(app) == [True, True, True]
        assert app.model.status == "IRF estimation completed"
        rows = [text for _, text in app.model.result_rows()]
        strings = _draw(app).strings
        assert all(text in strings for text in rows)
        assert app.model.time_axis_text() in " ".join(strings)
    finally:
        app.close()


def test_a_file_sets_the_background_from_its_tail_floor(tail_file):
    app = IRFEstimatorApp()
    try:
        _receive(app, tail_file)
        assert 7.0 <= app.model.manual_background <= 10.0  # the floor the file was written with
    finally:
        app.close()


def test_the_curves_carry_their_pens(monkeypatch):
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as app_module

    app = _loaded()
    try:
        app.model.manual_background = 5.0
        app.model.rl_iterations = 20
        app.model.estimate()
        styles = []
        monkeypatch.setattr(
            app_module.implot,
            "set_next_line_style",
            lambda colour=None, weight=None, dash=None: styles.append((colour, dash)),
        )
        _draw(app, n=1)
        assert styles == [
            app_module.PENS[name]
            for name in (
                "Measured Decay",
                "BG Corrected",
                "Estimated IRF (scaled)",
                "IRF ⊗ Exp (Forward Model)",
            )
        ]
        # the background-corrected decay and the forward model are dashed
        assert [dash is not None for _, dash in styles] == [False, True, False, True]
    finally:
        app.close()


def test_a_file_that_cannot_load_is_reported(tmp_path):
    bad = tmp_path / "bad.dat"
    bad.write_text("not a decay\n")
    app = IRFEstimatorApp()
    try:
        _receive(app, bad)
        assert app.error and app.model.source_text.startswith("Error: ")
        assert app.model.decay_data_original is None
        strings = _draw(app).strings
        assert any(app.error in s for s in strings)
        _receive(app, DECAY)
        assert not app.error and app.model.source_text == str(DECAY)
    finally:
        app.close()


def test_a_failed_estimate_is_reported(monkeypatch):
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as app_module

    def broken(*args, **kwargs):
        raise RuntimeError("tail fit did not converge")

    monkeypatch.setattr(app_module, "estimate_irf", broken)
    app = _loaded()
    try:
        assert app.start_estimate()
        _wait(app)
        assert (
            app.error == "tail fit did not converge" and app.model.status == "IRF estimation failed"
        )
        assert app.model.result is None and _states(app) == [True, False, False]
    finally:
        app.close()


def test_one_estimate_at_a_time_and_frames_only_while_running():
    app = _loaded()
    try:
        app.model.rl_iterations = 20
        _draw(app)
        assert not app.animating()
        assert app.start_estimate()
        assert not app.start_estimate()
        assert app.animating()
        assert not app.form_model.enabled("load_example") and app.form_model.enabled("request_help")
        _wait(app)
        assert not app.animating() and app.model.result is not None
    finally:
        app.close()


def test_auto_update_reestimates_quickly_with_50_iterations(monkeypatch):
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as app_module

    app = _loaded()
    try:
        app.model.rl_iterations = 20
        app.form_model.window_length = 15  # no IRF yet, auto-update off: nothing
        assert app.future is None
        app.start_estimate()
        _wait(app)
        seen = []
        real = app_module.estimate_irf
        monkeypatch.setattr(
            app_module, "estimate_irf", lambda *a: seen.append(a[2].rl_iterations) or real(*a)
        )
        app.form_model.window_length = 17  # auto-update off: nothing
        assert app.future is None
        _click(app, "auto_update_enabled")
        assert app.model.auto_update_enabled and app.future is None  # switching it on: no estimate
        app.form_model.manual_background = 1.0
        _wait(app)
        assert seen == [50]
    finally:
        app.close()


def test_range_fields_order_themselves_and_the_plot_series():
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as app_module

    app = _loaded()
    try:
        _click(app, "use_range_selection")
        assert app.model.use_range_selection
        _draw(app)
        assert {"first_channel", "last_channel"} <= set(app.item_rects)
        assert app.form_model.bounds("last_channel") == (0, 1023)
        app.form_model.last_channel = 10
        app.form_model.first_channel = 600
        assert app.model.range_bounds == [10.0, 600.0]
        app.model.rl_iterations = 20
        app.model.manual_background = 5.0
        app.model.estimate()
        names = [c["name"] for c in app.model.plot_series()]
        assert names == [
            "Measured Decay",
            "BG Corrected (BG=5.0)",
            "Estimated IRF (scaled)",
            "IRF ⊗ Exp (Forward Model)",
        ]
        irf = np.asarray(app.model.plot_series()[2]["y"])
        assert np.nanmin(irf) >= 1.0 and np.isnan(irf).any()  # cut below one count (log axis)
        assert all(name.split(" (BG=")[0] in app_module.PENS for name in names)
    finally:
        app.close()


def test_save_writes_the_irf_an_unwritable_path_is_reported_and_transfer_registers_it(tmp_path):
    app = _loaded()
    try:
        app.model.rl_iterations = 20
        app.start_estimate()
        _wait(app)
        _click(app, "request_save")
        assert app.dialog is not None and app.dialog.mode == "save" and app.file_action == "save"
        app.dialog = None
        app.file_chosen(str(tmp_path / "irf"))
        assert "IRF saved to" in app.model.status and not app.error
        from chisurf.core.fio import read_vv_vh

        channels = read_vv_vh(str(tmp_path / "irf.dat"), split=True)
        vv = channels["VV"] if isinstance(channels, dict) else channels[0]
        np.testing.assert_allclose(vv, app.model.irf_data, rtol=1e-5, atol=1e-6)  # 6 decimals
        app.file_chosen(str(tmp_path / "irf.dat" / "inside_a_file.dat"))
        assert app.error  # an unwritable path is reported
        received = []
        app.dataset_sink = received.append
        _click(app, "request_transfer")
        assert len(received) == 1 and len(received[0]) == 2 and not app.error
        assert received[0].data_reader.dt == pytest.approx(1.0)
    finally:
        app.close()


def test_a_decay_picked_in_the_workspace_input_section_sets_label_and_dt():
    from test.gui.curve_workspace import add_curve, pick

    t = np.arange(200) * 0.05
    y = np.exp(-t / 2.0) * 1000 + 3
    empty = IRFEstimatorApp()
    try:
        assert "donor decay" not in _draw(empty).strings
    finally:
        empty.close()
    curve = add_curve(t, y, name="donor decay")
    app = IRFEstimatorApp()
    try:
        assert "donor decay" in _draw(app).strings
        pick(app.input, curve)
        assert app.model.source_text == "Dataset: Uncategorized - donor decay"
        assert app.model.dt == pytest.approx(0.05)
        assert app.source_uid == str(curve.unique_identifier)
    finally:
        app.close()


def test_the_guide_points_at_real_controls_and_waits():
    app = IRFEstimatorApp()
    try:
        _draw(app)
        steps = app.tour.steps
        keys_ = {app.tour._target_key(s.get("target")) for s in steps} - {""}
        assert keys_ == {
            "load_example",
            "Load Decay",
            "irf_background",
            "irf_rl_iterations",
            "Estimate IRF",
        }
        assert keys_ <= set(app.item_rects)
        app.tour.start(1)  # the example step waits for its own button
        assert app.tour.awaiting
        _click(app, "load_example")
        assert not app.tour.awaiting
        load = next(
            i for i, s in enumerate(steps) if s.get("target", {}).get("action") == "Load Decay"
        )
        app.tour.start(load)
        assert not app.tour.awaiting  # the example already loaded a decay: your own is optional
        _receive(app, DECAY)
        estimate = next(
            i for i, s in enumerate(steps) if s.get("target", {}).get("action") == "Estimate IRF"
        )
        app.tour.start(estimate)
        assert app.tour.awaiting
        app.model.rl_iterations = 20
        _click(app, "Estimate IRF")
        assert not app.tour.awaiting
        _wait(app)
    finally:
        app.tour.active = False
        app.close()


@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated_with_every_control_inside_its_dock(size):
    app = IRFEstimatorApp()
    try:
        strings = _draw(app, size).strings
        assert {"🔮  Estimate IRF", "Time axis: Not available", "N/A"} <= set(strings)
        assert any("workspace" in s for s in strings)  # the Input section says how data gets in
        _receive(app, DECAY)
        app.model.rl_iterations = 20
        app.start_estimate()
        _wait(app)
        _draw(app, size)
        x0, y0, w0, h0 = app.item_rects["controls"]
        for name in (
            "workspace_input_rows",
            "request_save",
            "request_transfer",
            "request_guide",
            "request_help",
            "dt",
            "manual_background",
            "use_range_selection",
            "auto_update_enabled",
            "request_estimate",
        ):
            x, y, w, h = app.item_rects[name]
            assert x >= x0 - 0.5 and x + w <= x0 + w0 + 0.5 and y + h <= y0 + h0 + 0.5, name
    finally:
        app.close()


def test_every_control_has_a_tooltip():
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import _spec
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("irf_estimator")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()

    def walk(sections):
        for section in sections:
            yield section
            yield from walk(section.get("sections") or [])
            yield from section.get("buttons") or []

    assert all(s.get("description") for s in walk(_spec()["sections"]))
