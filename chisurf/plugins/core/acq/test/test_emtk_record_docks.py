"""The Record tool's windows: every dock opens and closes, the layout round-trips, the tour finds
its targets across docks, Image mode records a scan into Datasets that an imaging tool takes, and
the running trace is drawn mirrored."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.core.acq.gui.record_app import DOCKS, HERE, RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1500, 950)
SHOTS = Path(__file__).resolve().parents[5] / "test" / "native_emtk" / "screenshots"


@pytest.fixture
def app(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    application = RecordApp(model)
    yield application
    application.close()


def _run_to_end(ui, model, timeout=180.0):
    # a run measures until Stop: old tests set only duration_s, so ask for the
    # duration cap explicitly or the runs never end (stop_after defaults off)
    model.stop_after = True
    end = time.monotonic() + timeout
    while model.running:
        assert time.monotonic() < end, "the run did not end"
        ui.draw(1)
        time.sleep(0.02)
    ui.draw(3)


def test_every_dock_opens_and_closes(app):
    # Setup quality is intentionally available only in Advanced mode.
    app.model.ui_mode = 'advanced'
    app.model.ui_mode_changed()
    ui = Driver(app, SIZE)
    ui.draw(2)
    for key, title, _region in DOCKS:
        app.docks.hide(key)
        ui.draw(1)
        assert not app.docks.windows[key].visible
        app.focus_dock(key)
        ui.draw(2)
        assert app.docks.windows[key].visible, key
        assert title in " ".join(ui.strings()), title


def test_the_layout_round_trips(app):
    ui = Driver(app, SIZE)
    ui.draw(2)
    app.docks.undock("quality", box=(900.0, 120.0, 360.0, 400.0))
    app.docks.hide("plot_decays")
    ui.draw(2)
    state = json.loads(json.dumps(app.docks.state()))
    fresh = RecordApp(RecordModel(realtime=False))
    try:
        fresh.docks.restore(state)
        Driver(fresh, SIZE).draw(2)
        assert json.loads(json.dumps(fresh.docks.state())) == state
        assert not fresh.docks.windows["plot_decays"].visible
    finally:
        fresh.close()
    app.reset_layout()
    ui.draw(2)
    assert app.docks.windows["plot_decays"].visible


def test_every_tour_target_is_drawn_when_its_step_is_shown(app):
    steps = json.loads((HERE / "guide.json").read_text(encoding="utf-8"))["steps"]
    ui = Driver(app, SIZE)
    model = app.model
    ui.click("load_example")
    model.duration_s = 3.0
    model.stop_after = True  # the duration cap must be asked for; a run measures until Stop
    ui.click("start")  # plots and the quality panel have content
    _run_to_end(ui, model)
    app.tour.start()
    for k, step in enumerate(steps):
        app.tour.step_idx = k
        ui.draw(3)
        name = (step.get("target") or {}).get("name")
        if name:
            assert app.form.rects.get(name), f"step {k} ({step['title']}): {name!r} not drawn"
        if "Image (scan)" in (step.get("await") or {}).get("hint", ""):
            app.model.mode = "image"  # what the user does at this step
            app.model.mode_changed()
        if str((step.get("target") or {}).get("name", "")).endswith(".fold"):
            app.form.folds[step["target"]["name"][:-5]] = True  # the user opens it
    app.tour.stop()


def test_point_and_image_swap_the_plot_docks(app):
    ui = Driver(app, SIZE)
    ui.draw(2)
    assert app.docks.windows["plot_hist"].visible and not app.docks.windows["plot_image"].visible
    app.model.mode = "image"
    app.model.mode_changed()
    ui.draw(2)
    assert app.docks.windows["plot_image"].visible and not app.docks.windows["plot_hist"].visible


def test_the_running_trace_is_mirrored_and_keeps_its_window(app):
    ui = Driver(app, SIZE)
    model = app.model
    ui.click("load_example")
    model.duration_s = 4.0
    model.trace_window_s, model.trace_bin_ms = 0.5, 2.0
    model.stop_after = True  # the duration cap must be asked for; a run measures until Stop
    ui.click("start")
    _run_to_end(ui, model)
    trace = model.snapshot["live_trace"]
    assert trace["window_s"] == pytest.approx(0.5) and trace["bin_s"] == pytest.approx(2e-3)
    assert len(trace["t"]) == 250
    signs = {s["name"]: np.sign(np.asarray(s["counts"])) for s in trace["streams"]}
    assert all((v >= 0).all() for k, v in signs.items() if k.startswith("DD"))
    assert all((v <= 0).all() for k, v in signs.items() if not k.startswith("DD"))
    app.focus_dock("plot_trace")
    ui.draw(1)
    assert "Last 0.5 s" in " ".join(ui.strings())


def test_an_image_scan_lands_in_datasets_and_opens_in_an_imaging_tool(app, tmp_path):
    from chisurf.core.api import dataset_objects
    from chisurf.plugins.microscopy.imaging_emtk.testing import pick_from_workspace
    from chisurf.plugins.microscopy.img_pixel_intensity.gui.app import make_app

    ui = Driver(app, SIZE)
    model = app.model
    model.mode = "image"
    model.mode_changed()
    ui.click("load_example")
    model.scan_pixels_x = model.scan_pixels_y = 32
    model.scan_frames = 2
    ui.click("start")
    _run_to_end(ui, model)
    result = model.session.result
    assert result.ptu is not None and Path(result.ptu).exists()
    snap = model.snapshot
    assert snap["lines_done"] == 64 and snap["images"]["Intensity"].sum() == result.photons
    rows = {str(getattr(d, "address", "")): d for d in dataset_objects()}
    row = rows.get(str(result.ptu))
    assert row is not None and str(getattr(row, "data_kind", "")) == "image"
    assert getattr(row, "representation", "") == "photons"
    assert "image" in model.status_detail
    SHOTS.mkdir(parents=True, exist_ok=True)
    from emtk.export import save_png

    save_png(app, str(SHOTS / "record_image_done.png"), size=SIZE)
    tool = make_app()
    try:
        pick_from_workspace(tool, result.ptu)
        Driver(tool, (1200, 800)).draw(3)
    finally:
        tool.close()


def test_record_workspace_tabs_and_controls(app):
    """The central main region acts as an EMTK workspace dock containing workspace documents
    with tabs, tiling, cascading, mode-specific workspace documents, and dock-in-dock flexibility."""
    assert app.docks.workspace == "main"
    assert app.docks.region_of("plot_hist") == "main"
    ws_keys = (
        "plot_hist", "plot_correlation", "plot_polarization", "plot_image",
        "power_calibration", "plot_trace", "plot_decays", "rates", "video",
        "quality", "setup_quality", "points"
    )
    for key in ws_keys:
        assert app.docks.windows[key].workspace, f"{key} should be a workspace window"
        assert app.docks.region_of(key) == "main"

    setup_keys = ("acquisition", "laser", "analysis")
    for key in setup_keys:
        assert not app.docks.windows[key].workspace, f"{key} should not be a workspace window"
        assert app.docks.region_of(key) == "settings"

    # Settings joins the workspace documents (the operator asked for it there), yet it
    # stays an expert dock: outside Advanced mode it is hidden (see mode presets test).
    assert app.docks.windows["settings"].workspace
    assert app.docks.region_of("settings") == "main"

    # Dock-in-docks: any dock can dock into main or other docks
    assert app.docks.admits("plot_trace", "main")
    assert app.docks.target_admits("plot_trace", "main:center")
    assert app.docks.target_admits("plot_trace", "main:left")
    assert app.docks.admits("plot_hist", "settings")

    ui = Driver(app, SIZE)
    ui.draw(2)
    rendered_strings = " ".join(ui.strings())
    for ctrl in ("Tile", "Cascade", "Tabbed", "Windows"):
        assert ctrl in rendered_strings, f"Workspace control {ctrl} missing from header"

    # Workspace layout operations
    app.docks.tile_workspace()
    ui.draw(1)
    app.docks.cascade_workspace()
    ui.draw(1)
    app.docks.tab_workspace()
    ui.draw(1)

    # In point mode, Histogram tab is active in workspace
    assert app.docks.windows["plot_hist"].visible
    assert not app.docks.windows["plot_correlation"].visible

    # Switching to FCS mode activates FCS Correlation tab in workspace
    app.model.mode = "fcs"
    app.model.mode_changed()
    ui.draw(2)
    assert app.docks.windows["plot_correlation"].visible
    assert not app.docks.windows["plot_hist"].visible

    # Switching to Polarization mode activates Polarization tab in workspace
    app.model.mode = "pol"
    app.model.mode_changed()
    ui.draw(2)
    assert app.docks.windows["plot_polarization"].visible
    assert not app.docks.windows["plot_correlation"].visible

    # Switching to Image mode activates Image tab in workspace
    app.model.mode = "image"
    app.model.mode_changed()
    ui.draw(2)
    assert app.docks.windows["plot_image"].visible
    assert not app.docks.windows["plot_polarization"].visible

