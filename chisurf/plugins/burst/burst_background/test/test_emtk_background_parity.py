"""The native burst background tool at parity with the Qt BurstBackgroundEstimator.

Both hosts draw the same ``BurstBackgroundApp``; the Qt widget estimates
synchronously with files pushed in by the workflow shell, the emtk app picks its
own files and estimates on the controller's worker. The Qt widget runs in a
subprocess on the same measurement (this process stays Qt-free) and the rates are
compared, and both against the background the demo measurement was made with.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
from emtk.testing import PixelPainter, RecordingPainter  # noqa: E402

from chisurf.plugins.burst.burst_background.gui.app import create_app  # noqa: E402
from chisurf.plugins.burst.burst_background.test.demo_data import (  # noqa: E402
    BACKGROUND_KHZ,
    build,
)
from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory, qt_free  # noqa: E402


@pytest.fixture(scope="module")
def measurement(tmp_path_factory):
    return build(tmp_path_factory.mktemp("bg") / "measurement")


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


def _frames_until(app, done, timeout=60.0, size=(1200, 800)):
    """Draw frames -- as the host would on request -- until *done*; no manual poll."""
    end = time.monotonic() + timeout
    while not done():
        assert time.monotonic() < end, "not reached by drawing frames"
        time.sleep(0.02)
        _draw(app, size, n=1)


def _estimated(app, path):
    app.controller.add_files([path])
    app.controller.run()
    _frames_until(app, lambda: not app.controller.running and app.model.backgrounds)
    return next(iter(app.model.backgrounds.values()))


_QT = r"""
import json, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.burst.burst_background import BurstBackgroundEstimator
w = BurstBackgroundEstimator()
w._add_tttr_files([sys.argv[1]])
w._estimate()
rates = next(iter(w.model.backgrounds.values()))
print("FACTS" + json.dumps({"rates": rates, "window": [w.model.fit_from_ms, w.model.fit_to_ms],
                            "api": [n for n in ("tttr_files", "_add_tttr_files", "detector_wizard_page") if hasattr(w, n)]}))
"""


@pytest.fixture(scope="module")
def qt(measurement, tmp_path_factory):
    pytest.importorskip("qtpy")
    # The Qt widget opens the last used detector setup of the user's settings; the reference must not see it.
    private = tmp_path_factory.mktemp("qt_settings")
    env = dict(
        os.environ,
        QT_QPA_PLATFORM="offscreen",
        CHISURF_SETTINGS_DIR=str(private / "s"),
        MMFDB_SETTINGS_DIR=str(private / "m"),
        MMFDB_DATABASE_PATH=str(private / "m" / "db.sqlite"),
    )
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, str(measurement)],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and (
        "No module named" in proc.stderr or "could not connect to display" in proc.stderr
    ):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt widget's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS") :])


# 1. the Qt widget's rates, and the background the measurement was made with
def test_an_estimate_gives_the_qt_widgets_rates_and_the_known_background(qt, measurement):
    app = create_app()
    try:
        rates = _estimated(app, measurement)
        for detector in ("green", "red"):
            assert rates[detector] == pytest.approx(qt["rates"][detector])
            assert rates[detector] == pytest.approx(BACKGROUND_KHZ[detector], rel=0.1)
        assert [app.model.fit_from_ms, app.model.fit_to_ms] == pytest.approx(qt["window"])
        assert not app.controller.running
    finally:
        app.close()


# 5. end to end: the files dialog opened by a press, the Estimate button pressed, frames alone
def test_open_files_and_estimate_by_presses_and_frames(measurement):
    app = create_app()
    size = (800, 600)
    try:
        _draw(app, size, painter=PixelPainter)

        def press(key):
            x, y, w, h = app.item_rects[key]
            app.pointer_move(x + w / 2, y + h / 2)
            app.press(x + w / 2, y + h / 2)
            _draw(app, size, n=1, painter=PixelPainter)
            app.release()
            _draw(app, size, n=1, painter=PixelPainter)

        press("files")  # the drawn Open TTTR files button
        assert app.controller.dialog.title == "Select TTTR files"
        app.controller.dialog.draw = lambda: [str(measurement)]  # the user picks the measurement
        _frames_until(app, lambda: app.controller.dialog is None, size=size)
        assert app.model.files == [str(measurement)]
        # The pick lands at the end of a frame, after the layout: the file row it adds moves
        # Estimate down, which the next frame (a host draws one after any input) lays out.
        _draw(app, size, n=1, painter=PixelPainter)
        step = next(i for i, st in enumerate(app.bg_gui.tour.steps) if st.get("await"))
        app.bg_gui.tour.start(step)
        assert app.bg_gui.tour.awaiting  # "Run it" waits for Estimate
        press("bg_run")
        assert not app.bg_gui.tour.awaiting
        _frames_until(app, lambda: not app.controller.running and app.model.backgrounds, size=size)
        assert set(next(iter(app.model.backgrounds.values()))) >= {"green", "red"}
    finally:
        app.close()


def test_a_dropped_folder_adds_its_measurements_not_their_containers(measurement):
    measurement.with_suffix(".pto").write_bytes(b"")  # what an estimate writes beside the photons
    app = create_app()
    try:
        app.on_paths_dropped([str(measurement.parent)])
        assert app.model.files == [str(measurement)]
    finally:
        app.close()


def test_frames_are_requested_while_estimating(measurement, monkeypatch):
    import threading

    from chisurf.plugins.burst.burst_background import view_model

    gate = threading.Event()
    original = view_model.BackgroundViewModel.estimate
    monkeypatch.setattr(
        view_model.BackgroundViewModel,
        "estimate",
        lambda self, cancel_check=None: (gate.wait(10), original(self, cancel_check))[1],
    )
    app = create_app()
    try:
        app.controller.add_files([measurement])
        app.controller.run()
        _draw(app, n=1)
        assert app.controller.running and app.next_frame_in() is not None
        gate.set()
        _frames_until(app, lambda: not app.controller.running)
    finally:
        gate.set()
        app.close()


# 2. actions and errors
def test_each_action_opens_its_own_dialog():
    app = create_app()
    try:
        for action, (title, mode) in {
            "files": ("Select TTTR files", "open"),
            "folder": ("Add TTTR folder", "folder"),
            "load_setup": ("Load detector setup", "open"),
            "save_setup": ("Save detector setup", "save"),
        }.items():
            app.controller.browse(action)
            assert (app.controller.dialog.title, app.controller.dialog.mode) == (title, mode), (
                action
            )
    finally:
        app.close()


def test_stop_remove_clear_and_reasons(measurement, tmp_path):
    app = create_app()
    try:
        app.controller.run()
        assert app.controller.status == "Please load TTTR files first."
        app.controller.add_files([measurement])
        app.controller.remove_file(str(measurement))
        assert app.model.files == []
        assert not app.controller.apply_detectors('{"green": {"chs": []}}')
        assert "nonempty chs" in app.controller.status
        setup = tmp_path / "detectors.json"
        app.controller.save_setup(setup)
        assert app.controller.load_setup(setup)
        _estimated(app, measurement)
        app.controller.clear()
        assert app.model.files == [] and not app.model.backgrounds
    finally:
        app.close()


def test_an_unreadable_file_is_reported(tmp_path):
    bad = tmp_path / "broken.ptu"
    bad.write_bytes(b"not a measurement")
    app = create_app()
    try:
        app.controller.add_files([bad])
        app.controller.run()
        _frames_until(app, lambda: not app.controller.running)
        assert app.controller.status.startswith("Error:")
        assert any(s.startswith("Error:") for s in _draw(app).strings)
    finally:
        app.close()


# 3. every guide target is drawn
def test_every_guide_target_is_drawn(measurement):
    app = create_app()
    try:
        _estimated(app, measurement)
        _draw(app)
        keys = {app.bg_gui.tour._target_key(s.get("target")) for s in app.bg_gui.tour.steps} - {""}
        assert keys and keys <= set(app.item_rects), keys - set(app.item_rects)
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes; legend, window tag, bar labels, one status
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(measurement, size, monkeypatch):
    from emtk import implot

    app = create_app()
    try:
        strings = _draw(app, size).strings
        assert "Estimate Background" in strings
        _estimated(app, measurement)
        ticks = []
        original = implot.setup_axis_ticks
        monkeypatch.setattr(
            implot,
            "setup_axis_ticks",
            lambda axis, values, n_ticks=None, labels=None, *a, **k: (
                ticks.append(labels),
                original(axis, values, n_ticks, labels, *a, **k),
            )[1],
        )
        strings = _draw(app, size).strings
        assert "Series" not in strings  # a fitted tail is not a legend entry
        assert [s for s in strings if s.startswith("Fit ") and "–" in s] == ["Fit 1.96–3.31 ms"]
        assert ["green", "red"] in ticks  # the bars are named
        status = app.model.status
        assert " ".join(strings).count(status.split(";")[0]) == 1  # the status once, not twice
    finally:
        app.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    result = qt_free("burst_background")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    app = build_emtk_app("burst_background")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()


def test_the_workflow_api_is_on_the_qt_widget(qt):
    assert set(qt["api"]) == {"tttr_files", "_add_tttr_files", "detector_wizard_page"}
