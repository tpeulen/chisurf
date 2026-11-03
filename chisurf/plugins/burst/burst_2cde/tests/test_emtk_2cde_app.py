"""The native 2CDE tool: its run, states, errors, guide, drawing and tooltips.

The answer is the one planted in the demo folder (``demo_folder.build``): static bursts read
FRET-2CDE near 10, the dynamic ones (every fourth) well above it.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(REPO))
from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.plugins.burst.burst_2cde.core import computation as core  # noqa: E402
from chisurf.plugins.burst.burst_2cde.gui.app import create_app  # noqa: E402
from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build  # noqa: E402
from test.gui.emtk_port_parity import (  # noqa: E402  (before tttrlib's `test`)
    build_emtk_app,
    emtk_inventory,
    qt_free,
)


@pytest.fixture
def folder(tmp_path):
    return build(tmp_path / "measurement")


def _app(folder=None):
    app = create_app()
    app.model.donor_channels_text, app.model.acceptor_channels_text = "0", "1"
    if folder is not None:
        app.model.set_folder(folder)
    return app


def _draw(app, size=(1200, 800), n=2):
    painter = RecordingPainter()
    for _ in range(n):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def _settle(app, timeout=60.0):
    """Frames until the worker is done (the host would draw them on request)."""
    end = time.monotonic() + timeout
    while app.controller.running:
        assert time.monotonic() < end, "2CDE did not finish"
        time.sleep(0.02)
        _draw(app, n=1)
    _draw(app, n=1)


def _values(df):
    return np.asarray(df[core.COLUMN_FRET_2CDE], float)


# 1. the planted answer, and the companion written beside the measurement
def test_a_run_finds_the_dynamic_bursts_and_writes_one_companion(folder, tmp_path):
    app = _app(folder)
    try:
        app.controller.run()
        _settle(app)
        ours = _values(app.model.df)
        assert ours.shape == (60,) and np.isfinite(ours).all()
        dynamic = np.arange(len(ours)) % 4 == 3
        assert np.median(ours[~dynamic]) == pytest.approx(10.0, abs=2.5)
        assert ours[~dynamic].max() < 20 < 30 < ours[dynamic].min()
        params = json.loads(json.dumps(app.model.fingerprint_params()))
        assert params.get("micro_time_resolution_ps") is None
        assert {k: params[k] for k in ("variant", "kernel", "tau_us", "donor_channels", "acceptor_channels")} == {
            "variant": "fret",
            "kernel": "laplace",
            "tau_us": 100.0,
            "donor_channels": [0],
            "acceptor_channels": [1],
        }
        assert sorted(p.name for p in folder.parent.glob("*.pto")) == ["m000.pto"]
        assert not (folder / "2c4").exists()
        assert app.model.status_text == "FRET-2CDE: 60 / 60 bursts valid"
        assert not app.model.is_running and not app.model.is_locked
    finally:
        app.close()


# 2. the run's states
def test_an_unchanged_run_is_kept_and_points_at_restart(folder, monkeypatch):
    app = _app(folder)
    try:
        app.controller.run()
        _settle(app)
        calls = []
        original = core.compute_2cde
        monkeypatch.setattr(
            core, "compute_2cde", lambda *a, **k: calls.append(1) or original(*a, **k)
        )
        app.controller.run()
        assert (
            app.model.status_text
            == "Unchanged — kept the previous 2CDE result (Restart recomputes it)"
        )
        assert app.model.restart_attention and not calls and not app.controller.running
        app.controller.restart()
        _settle(app)
        assert calls == [1] and not app.model.restart_attention
    finally:
        app.close()


def test_stop_abandons_the_run_and_only_an_explicit_run_restarts_it(folder, monkeypatch):
    import threading

    from chisurf.plugins.burst.burst_bva.core import computation as bva

    release = threading.Event()
    real = bva.read_burst_analysis

    def slow(*a, **k):
        assert release.wait(10)
        return real(*a, **k)

    monkeypatch.setattr(core, "read_burst_analysis", slow)
    app = _app(folder)
    try:
        app.controller.run()
        assert app.model.is_locked
        app.controller.stop()
        release.set()
        _settle(app)
        assert app.model.df is None and "cancelled" in app.model.status_text
        assert not (folder / "2c4").exists()  # nothing written
        app.controller.auto_run()  # shown again: not by itself
        assert not app.controller.running
        assert app.model.status_text == "Stopped earlier — press Run to compute 2CDE"
        app.controller.run()  # an explicit Run
        _settle(app)
        assert app.model.df is not None
    finally:
        release.set()
        app.close()


def test_the_first_frame_runs_a_folder_that_is_already_set(folder):
    app = _app(folder)
    try:
        _draw(app, n=1)
        assert app.controller.running or app.model.df is not None
        _settle(app)
        assert app.model.df is not None
    finally:
        app.close()


def test_a_burst_run_handed_over_runs_and_no_input_dialog_or_drop_exists(folder):
    """The Input section / Open in… hands a burst run over (no file dialog, no drop hook)."""
    import pytest

    from chisurf.plugins.burst.burst_2cde.gui.app import receive_bursts

    app = _app()
    try:
        assert not hasattr(app, "files_dropped")
        with pytest.raises(ValueError, match="not a burst run"):
            receive_bursts(app, {"folder": str(folder / "bi4_bur" / "m000.bur"), "datasets": ["x"]})
        receive_bursts(app, {"folder": str(folder), "datasets": ["run-uid"]})
        assert app.model.folder == str(folder)
        _settle(app)
        assert app.model.df is not None
    finally:
        app.close()


def test_progress_is_shown_while_running(folder, monkeypatch):
    import threading

    gate = threading.Event()
    seen = []
    original = core.compute_2cde

    def compute(*a, progress_window=None, **k):
        progress_window.set_value(30)
        seen.append((app.model.progress_text, app.model.progress))
        assert gate.wait(10)
        return original(*a, progress_window=progress_window, **k)

    monkeypatch.setattr(core, "compute_2cde", compute)
    app = _app(folder)
    try:
        app.controller.run()
        end = time.monotonic() + 30
        while not seen:
            assert time.monotonic() < end
            time.sleep(0.02)
        assert seen == [("Computing 2CDE …", pytest.approx(0.5))]
        painter = _draw(app)
        assert "Computing 2CDE …" in painter.strings
        assert app.next_frame_in() is not None  # looks again soon while running
        gate.set()
        _settle(app)
        assert app.model.progress_text == "" and not app.controller.running
    finally:
        gate.set()
        app.close()


# 2. errors
def test_errors_reach_the_window(folder, tmp_path, monkeypatch):
    app = _app(tmp_path / "missing")
    try:
        app.controller.run()
        assert app.model.status_text == "Pick a burst run in the Input section first."
        app.model.set_folder(folder)
        monkeypatch.setattr(
            core,
            "write_2cde_container",
            lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")),
        )
        app.controller.run()
        _settle(app)
        assert app.model.df is not None  # a failed write keeps the result
        assert "could not write the 2CDE result: disk full" in app.model.status_text
        monkeypatch.setattr(
            core,
            "read_burst_analysis",
            lambda *a, **k: (_ for _ in ()).throw(ValueError("bad table")),
        )
        app.controller.restart()
        _settle(app)
        assert app.model.df is None and app.model.status_text == "Error: bad table"
        assert "Error: bad table" in _draw(app).strings
    finally:
        app.close()


# 3. every guide step points at something drawn
def test_every_guide_target_is_drawn():
    app = _app()
    try:
        _draw(app)
        steps = json.loads((HERE.parent / "gui" / "guide.json").read_text())["steps"]
        keys = {app.two_cde_gui.tour._target_key(s.get("target")) for s in steps if s.get("target")}
        keys.discard(None)
        keys.discard("")
        assert keys and keys <= set(app.item_rects), keys - set(app.item_rects)
    finally:
        app.close()


# 4. draws, empty and populated, at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws_empty_and_populated(folder, size):
    app = _app()
    try:
        assert {"Input", "2CDE Parameters"} <= set(_draw(app, size).strings)
        pane_right = app.item_rects["controls"][0] + app.item_rects["controls"][2]
        for name in (
            "run",
            "restart",
            "stop",
            "guide",
            "help",
        ):  # the row wraps, nothing is cut
            x, _y, w, _h = app.item_rects[name]
            assert x + w <= pane_right, name
        app.model.set_folder(folder)
        app.controller.run()
        _settle(app)
        strings = _draw(app, size).strings
        assert "FRET-2CDE: 60 / 60 bursts valid" in strings
        assert "Threshold: 10.0" in strings
    finally:
        app.close()


def _y_ranges(monkeypatch):
    """The y range each plot ends its frame with, by title (what is drawn, not what was asked)."""
    from emtk import implot
    from emtk import implot_internal as I

    seen = {}
    original = implot.end_plot

    def end_plot():
        plot = I.gp.current_plot
        if plot is not None:
            axis = plot.axes[I.AXIS_Y1]
            seen[plot.title] = (float(axis.range_min), float(axis.range_max))
        return original()

    monkeypatch.setattr(implot, "end_plot", end_plot)
    return seen


def test_the_2cde_axis_fits_every_burst_of_a_new_result(folder, monkeypatch):
    """Measured on a plot already drawn empty, as in the app: the result arrives later."""
    seen = _y_ranges(monkeypatch)
    app = _app()
    try:
        _draw(app)  # the empty plot exists
        app.model.set_folder(folder)
        app.controller.run()
        _settle(app)
        _draw(app, n=2)
        y = _values(app.model.df)
        lo, hi = seen["FRET-2CDE / ALEX-2CDE"]
        assert lo < np.nanmin(y) and hi > np.nanmax(y), (lo, hi)  # no burst on (or past) the edge
    finally:
        app.close()


# 6. no Qt
def test_port_is_qt_free():
    result = qt_free("burst_2cde")
    assert result["ok"], result["output"]


# 7. tooltips
def test_every_control_has_a_tooltip():
    app = build_emtk_app("burst_2cde")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
