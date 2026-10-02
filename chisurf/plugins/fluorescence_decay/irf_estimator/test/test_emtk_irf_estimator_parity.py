"""The native IRF estimator at parity with the Qt IRFEstimatorTool.

The Qt facts (the results group, the status bar's time axis, the data label, the
background a file sets, the estimated IRF and when each action is enabled) come
from the Qt widget in a subprocess on a measured donor decay; this process stays
Qt-free. The native app is driven through its real controls: pointer presses on
the spec's buttons, the file dialog's callback, the dataset combo.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import PixelPainter, RecordingPainter

from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as app_module
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.app import IRFEstimatorApp, _spec

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
DECAY = str(REPO / "test" / "data" / "tcspc" / "Jordi_FRETsens" / "Donor" / "D0_14_TAC1024_DexDem.dat")
ITERATIONS = 100

_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.tool import IRFEstimatorTool
w = IRFEstimatorTool()
def states():
    return [w.estimate_button.isEnabled(), w.save_action.isEnabled(), w.transfer_action.isEnabled()]
facts = {"states": [states()], "time_empty": w.status_time_label.text(), "label_empty": w.data_info_label.text()}
w.load_decay_file(sys.argv[1])
facts["states"].append(states())
facts["background"] = w.background_spinbox.value()
facts["label"] = w.data_info_label.text()
facts["time"] = w.status_time_label.text()
w.rl_iterations_spinbox.setValue(int(sys.argv[2]))
w.range_selection_checkbox.setChecked(True)
w.estimate_irf()
facts["states"].append(states())
facts["results"] = [w.lifetime_value.text(), w.decay_rate_value.text(), w.amplitude_value.text(), w.offset_value.text()]
facts["irf"] = [float(v) for v in w.irf_data]
facts["status"] = w._status_bar.currentMessage()
w.load_decay_file(sys.argv[3])
facts["tail_background"] = w.background_spinbox.value()
print("FACTS" + json.dumps(facts))
"""


@pytest.fixture(scope="module")
def tail_file(tmp_path_factory):
    """A VV/VH decay whose last tenth is not empty, so a file's background estimate shows."""
    from chisurf.core.fio import write_vv_vh

    t = np.arange(512.)
    counts = np.round(2000. * np.exp(-((t - 40.) / 6.) ** 2) + 900. * np.exp(-np.clip(t - 40., 0, None) / 60.)
                      * (t > 40) + 7. + (t % 3))
    path = tmp_path_factory.mktemp("tail") / "tail.dat"
    write_vv_vh(str(path), vv=counts, vh=counts)
    return str(path)


@pytest.fixture(scope="module")
def qt(tail_file):
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, DECAY, str(ITERATIONS), tail_file], capture_output=True, text=True,
                          timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt widget's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS"):])


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _click(app, key, size=(1200, 800), painter=RecordingPainter):
    """Press and release the centre of the control drawn under *key*, as a pointer does."""
    _draw(app, size, painter=painter)
    x, y, w, h = app.item_rects[key]
    app.pointer_move(x + w / 2, y + h / 2)
    app.press(x + w / 2, y + h / 2)
    _draw(app, size, n=1, painter=painter)
    app.release()
    _draw(app, size, n=1, painter=painter)


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


def _loaded(**kwargs):
    app = IRFEstimatorApp(**kwargs)
    app.choose_file()
    app.dialog = None
    app.file_chosen(DECAY)
    return app


# 1. the Qt tool's numbers, texts and control states, reached through the real buttons
def test_load_and_estimate_match_the_qt_tool(qt):
    app = IRFEstimatorApp()
    try:
        assert _states(app) == qt["states"][0] == [False, False, False]
        assert app.model.time_axis_text() == qt["time_empty"]
        assert app.model.source_text == qt["label_empty"]
        _click(app, "request_load")
        assert app.dialog is not None and app.dialog.mode == "open" and app.file_action == "load"
        app.dialog = None
        app.file_chosen(DECAY)                                     # what the dialog's result does
        assert _states(app) == qt["states"][1]
        assert app.model.manual_background == pytest.approx(qt["background"])
        assert app.model.source_text == qt["label"]
        assert app.model.time_axis_text() == qt["time"]
        app.form_model.rl_iterations = ITERATIONS
        app.form_model.use_range_selection = True
        _click(app, "request_estimate")
        assert app.future is not None
        _wait(app)
        assert _states(app) == qt["states"][2] == [True, True, True]
        assert [text for _, text in app.model.result_rows()] == qt["results"]
        np.testing.assert_allclose(app.model.irf_data, qt["irf"], rtol=1e-6, atol=1e-9)
        assert app.model.status == qt["status"]
        strings = _draw(app).strings
        assert all(text in strings for text in qt["results"]) and qt["time"] in " ".join(strings)
    finally:
        app.close()


def test_a_file_sets_the_qt_background_estimate(qt, tail_file):
    app = IRFEstimatorApp()
    try:
        app.file_chosen(tail_file)
        assert qt["tail_background"] > 0
        assert app.model.manual_background == pytest.approx(qt["tail_background"])
    finally:
        app.close()


def test_the_curves_carry_the_qt_pens(monkeypatch):
    app = _loaded()
    try:
        app.model.manual_background = 5.0
        app.model.rl_iterations = 20
        app.model.estimate()
        styles = []
        monkeypatch.setattr(app_module.implot, "set_next_line_style",
                            lambda colour=None, weight=None, dash=None: styles.append((colour, dash)))
        _draw(app, n=1)
        assert styles == [app_module.PENS[name] for name in ("Measured Decay", "BG Corrected", "Estimated IRF (scaled)",
                                                             "IRF \u2297 Exp (Forward Model)")]
        assert [dash is not None for _, dash in styles] == [False, True, False, True]   # Qt's dashed pens
    finally:
        app.close()


def test_disabled_buttons_do_nothing():
    app = IRFEstimatorApp()
    try:
        _click(app, "request_estimate")
        _click(app, "request_save")
        assert app.future is None and app.dialog is None
    finally:
        app.close()


# 2. error paths: shown in red, the data label says what failed
def test_a_file_that_cannot_load_is_reported(tmp_path):
    bad = tmp_path / "bad.dat"
    bad.write_text("not a decay\n")
    app = IRFEstimatorApp()
    try:
        app.files_dropped([str(bad)])
        assert app.error and app.model.source_text.startswith("Error: ")
        assert app.model.decay_data_original is None
        strings = _draw(app).strings
        assert any(app.error in s for s in strings)
        app.files_dropped([DECAY])                                  # a drop loads the first file
        assert not app.error and app.model.source_text == DECAY
    finally:
        app.close()


def test_a_failed_estimate_is_reported(monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("tail fit did not converge")

    monkeypatch.setattr(app_module, "estimate_irf", broken)
    app = _loaded()
    try:
        assert app.start_estimate()
        _wait(app)
        assert app.error == "tail fit did not converge" and app.model.status == "IRF estimation failed"
        assert app.model.result is None and _states(app) == [True, False, False]
    finally:
        app.close()


# 3. one estimate at a time; the controls are disabled while it runs; frames only then
def test_one_estimate_at_a_time_and_frames_only_while_running():
    app = _loaded()
    try:
        app.model.rl_iterations = 20
        _draw(app)
        assert not app.animating()
        assert app.start_estimate()
        assert not app.start_estimate()
        assert app.animating()
        assert not app.form_model.enabled("request_load") and app.form_model.enabled("request_help")
        _wait(app)
        assert not app.animating() and app.model.result is not None
    finally:
        app.close()


# 4. auto-update re-estimates with 50 iterations on a parameter change, once an IRF exists
def test_auto_update_reestimates_quickly(monkeypatch):
    app = _loaded()
    try:
        app.model.rl_iterations = 20
        app.form_model.window_length = 15                     # no IRF yet, auto-update off: nothing
        assert app.future is None
        app.start_estimate()
        _wait(app)
        seen = []
        real = app_module.estimate_irf
        monkeypatch.setattr(app_module, "estimate_irf", lambda *a: seen.append(a[2].rl_iterations) or real(*a))
        app.form_model.window_length = 17                     # auto-update off: nothing
        assert app.future is None
        _click(app, "auto_update_enabled")
        assert app.model.auto_update_enabled and app.future is None   # switching it on does not estimate
        app.form_model.manual_background = 1.0
        _wait(app)
        assert seen == [50]
    finally:
        app.close()


# 5. range selection: the channel fields order themselves; the plot follows the Qt plot
def test_range_fields_and_plot_series():
    app = _loaded()
    try:
        _click(app, "use_range_selection")
        assert app.model.use_range_selection
        _draw(app)
        assert {"first_channel", "last_channel"} <= set(app.item_rects)
        assert app.form_model.bounds("last_channel") == (0, 1023)
        app.form_model.last_channel = 10
        app.form_model.first_channel = 600
        assert app.model.range_bounds == [10., 600.]
        app.model.rl_iterations = 20
        app.model.manual_background = 5.0
        app.model.estimate()
        names = [c["name"] for c in app.model.plot_series()]
        assert names == ["Measured Decay", "BG Corrected (BG=5.0)", "Estimated IRF (scaled)",
                         "IRF ⊗ Exp (Forward Model)"]
        irf = np.asarray(app.model.plot_series()[2]["y"])
        assert np.nanmin(irf) >= 1.0 and np.isnan(irf).any()       # cut below one count, as the Qt plot
        assert all(name.split(" (BG=")[0] in app_module.PENS for name in names)
    finally:
        app.close()


# 6. save, transfer and the dataset combo
def test_save_writes_the_irf_and_transfer_registers_it(tmp_path):
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
        np.testing.assert_allclose(vv, app.model.irf_data, rtol=1e-5, atol=1e-6)   # written with 6 decimals
        app.file_chosen(str(tmp_path / "irf.dat" / "inside_a_file.dat"))
        assert app.error                                          # an unwritable path is reported
        received = []
        app.dataset_sink = received.append
        _click(app, "request_transfer")
        assert len(received) == 1 and len(received[0]) == 2 and not app.error
        assert received[0].data_reader.dt == pytest.approx(1.0)
    finally:
        app.close()


def test_load_from_dataset_through_the_combo():
    from chisurf.core.data import DataCurve

    t = np.arange(200) * 0.05
    y = np.exp(-t / 2.0) * 1000 + 3
    curve = DataCurve(x=t, y=y, name="donor decay", load_filename_on_init=False)
    empty = IRFEstimatorApp(dataset_provider=lambda: [])
    try:
        _click(empty, "request_dataset")
        assert empty.error and empty.model.decay_data_original is None
    finally:
        empty.close()
    app = IRFEstimatorApp(dataset_provider=lambda: [curve])
    try:
        _click(app, "request_dataset")
        assert app.show_datasets and "donor decay" in _draw(app).strings
        _click(app, "dataset_load")
        assert app.model.source_text == "Dataset: Uncategorized - donor decay"
        assert app.model.dt == pytest.approx(0.05) and not app.show_datasets
    finally:
        app.close()


# 7. guide: every target drawn; the load and estimate steps wait for those actions
def test_the_guide_points_at_real_controls_and_waits():
    app = IRFEstimatorApp()
    try:
        _draw(app)
        steps = app.tour.steps
        keys = {app.tour._target_key(s.get("target")) for s in steps} - {""}
        assert keys == {"Load Decay", "irf_background", "irf_rl_iterations", "Estimate IRF"}
        assert keys <= set(app.item_rects)
        load = next(i for i, s in enumerate(steps) if s.get("target", {}).get("action") == "Load Decay")
        app.tour.start(load)
        assert app.tour.awaiting
        _click(app, "request_load")
        assert app.tour.awaiting                                   # opening the dialog is not loading
        app.dialog = None
        app.file_chosen(DECAY)
        assert not app.tour.awaiting
        estimate = next(i for i, s in enumerate(steps) if s.get("target", {}).get("action") == "Estimate IRF")
        app.tour.start(estimate)
        assert app.tour.awaiting
        app.model.rl_iterations = 20
        _click(app, "Estimate IRF")
        assert not app.tour.awaiting
        _wait(app)
    finally:
        app.tour.active = False
        app.close()


# 8. draws, empty and populated, at both sizes; every control inside its dock
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_inside_the_docks(size):
    app = IRFEstimatorApp()
    try:
        strings = _draw(app, size).strings
        assert {"📂 Load Decay", "🔮 Estimate IRF", "Time axis: Not available", "N/A"} <= set(strings)
        app.file_chosen(DECAY)
        app.model.rl_iterations = 20
        app.start_estimate()
        _wait(app)
        _draw(app, size)
        x0, y0, w0, h0 = app.item_rects["controls"]
        for name in ("request_load", "request_dataset", "request_save", "request_transfer", "request_guide",
                     "request_help", "dt", "manual_background", "use_range_selection", "auto_update_enabled",
                     "request_estimate"):
            x, y, w, h = app.item_rects[name]
            assert x >= x0 - 0.5 and x + w <= x0 + w0 + 0.5 and y + h <= y0 + h0 + 0.5, name
    finally:
        app.close()


def test_help_opens_with_its_page():
    app = IRFEstimatorApp()
    try:
        _click(app, "request_help")
        assert app.help_window.open
    finally:
        app.close()


# 9. no Qt, tooltips (inventory and the spec)
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("irf_estimator")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
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
