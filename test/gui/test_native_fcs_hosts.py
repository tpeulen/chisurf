"""Existing FCS Qt entry points host the real native workflow and navigation."""

from chisurf.plugins.emtk_layout import action_caption
import pytest


@pytest.mark.parametrize("full", [False, True])
def test_fcs_host_uses_one_native_surface_and_closes_it(qtbot, monkeypatch, full):
    """Both public Qt names retain the actual app and its scientific context."""
    from chisurf.plugins.fcs.fcs_correlator.gui.app import FcsHubApp
    from chisurf.plugins.fcs.fcs_correlator.tool import FcsCorrelatorTool
    from chisurf.plugins.fcs.fcs_toolbox.tool import FcsTool, FcsToolboxTool

    tool = FcsTool() if full else FcsCorrelatorTool()
    qtbot.addWidget(tool)
    assert isinstance(tool.app, FcsHubApp)
    assert tool.host.control is tool.app and tool.centralWidget() is tool.host
    assert tool.workflow is tool.app.workflow
    assert tool.workflow_context is tool.app.workflow.context
    assert FcsToolboxTool is FcsTool
    roles = {panel["role"] for panel in tool.app.tools}
    assert {"channel_def", "files", "filter", "correlator", "merger"} <= roles
    if full:
        assert {"flc_2d", "lfcs_sim", "burst_fcs", "diffusion_calc", "filter_calc"} <= roles
        assert tool.show_panel_by_role("filter_calc")
        assert tool.app.selected == "filter_calc"
    assert not tool.show_panel_by_role("unknown")
    calls = []
    close = tool.app.close
    monkeypatch.setattr(tool.app, "close", lambda: (calls.append("close"), close()))
    tool.close()
    tool.close()
    tool.host.close()
    assert calls == ["close"]
    assert tool.host._control_closed
    assert tool.app.children == {}



def test_burst_host_parent_closure_cancels_real_queued_work_once(qtbot, monkeypatch):
    """The existing live burst host closes its owned executor once, even on repeated close."""
    from concurrent.futures import CancelledError
    from threading import Event

    from chisurf.plugins.burst.burst_fcs_correlator.gui.tool import BurstFcsTool

    tool = BurstFcsTool(embedded=True)
    qtbot.addWidget(tool)
    started, release = Event(), Event()
    ctrl = tool.controller

    def in_flight():
        started.set()
        release.wait(timeout=5)
        ctrl.check_cancel()

    running = ctrl._executor.submit(in_flight)
    assert started.wait(timeout=2)
    queued = ctrl._executor.submit(lambda: "must never run")
    ctrl._future, ctrl.running = queued, True
    calls = []
    close = tool.app.close
    monkeypatch.setattr(tool.app, "close", lambda: (calls.append("close"), close()))
    try:
        tool.close()
        tool.close()
        tool.host.close()
        assert calls == ["close"] and tool.host._control_closed
        assert queued.cancelled() and ctrl._cancel.is_set()
    finally:
        release.set()
    with pytest.raises(CancelledError):
        running.result(timeout=5)



def test_native_correlator_host_matches_frozen_real_measurement(qtbot, tmp_path):
    """Retiring the Qt wizard keeps the actual two-chunk measurements and channel counts."""
    import json
    import shutil
    from pathlib import Path

    import numpy as np

    from chisurf.plugins.fcs.fcs_toolbox.tool import FcsTool

    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "BH_SPC132.spc"
    shutil.copy2(root / "test/data/tttr/BH/132/BH_SPC132.spc", source)
    tool = FcsTool()
    qtbot.addWidget(tool)
    try:
        tool.app.files_step.add_paths([str(source)])
        assert tool.show_panel_by_role("correlator")
        model = tool.app.correlator_model
        model.channel_a, model.channel_b, model.n_splits = "0,1", "8,9", 2
        assert len(model._tttr) == 183657
        model.correlate_data()
        facts = json.loads((root / "okf/validation/release-readiness-w1/fcs-before/correlator-facts.json").read_text())
        assert len(model._correlations) == len(facts["correlations"]) == 2
        for measured, frozen in zip(model._correlations, facts["correlations"]):
            for quantity in ("x", "y"):
                np.testing.assert_array_equal(measured[quantity], frozen[quantity])
            assert measured["channel_a"] == frozen["channel_a"]
            assert measured["channel_b"] == frozen["channel_b"]
            assert measured["correlation_settings"] == frozen["correlation_settings"]
            assert measured["duration"] == frozen["duration"]
    finally:
        tool.close()


@pytest.mark.parametrize("width", [800, 1200])
def test_burst_resize_keeps_actual_radio_and_distribution_inside_canvas(width):
    """Live resizing retires clipped radios and plot axes without painting hidden controls."""
    from emtk import implot
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app

    app = create_app()
    try:
        driver = Driver(app, size=(1200, 800))
        app.select_tab("Settings")
        driver.draw(2)
        driver.draw(2, size=(width, 600))
        x, y, w, h = driver.rect("fit_mode.2")
        assert x >= 0 and x + w <= width and 0 <= y < y + h <= 600
        plot = implot.gp.last_plot
        assert plot.title is None
        assert 0 <= plot.frame_rect[0] < plot.frame_rect[2] <= width
        assert 0 <= plot.frame_rect[1] < plot.frame_rect[3] <= 600
        driver.click("fit_mode.2")
        assert app.controller._model.fit_mode == "maxent"
    finally:
        app.close()


@pytest.mark.parametrize("full", [False, True], ids=["correlator", "toolbox"])
def test_actual_native_fcs_factory_help_and_guide_buttons_are_bound(tmp_path, monkeypatch, full):
    """Visible native hub actions open real help and advance a tour through its real Example target."""
    from emtk.testing import Driver

    from chisurf.plugins.fcs.fcs_correlator.gui.app import make_app as correlator
    from chisurf.plugins.fcs.fcs_toolbox.gui.app import make_app as toolbox

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("MMFDB_OBJECT_STORE_ROOT", str(tmp_path / "objects"))
    app = (toolbox if full else correlator)()
    driver = Driver(app, size=(1200, 800))
    try:
        driver.draw(3)
        assert {"help", "guide"} <= set(driver.ids())
        driver.click("help")
        painter = driver.draw(3)
        visible = {call[6] for call in painter.calls if call[0] == "text"}
        assert app.help.open and action_caption("close") in visible
        assert any("correl" in text.casefold() for text in visible)
        driver.click(action_caption("close"))
        assert not app.help.open
        driver.click("guide")
        painter = driver.draw(3)
        visible = {call[6] for call in painter.calls if call[0] == "text"}
        assert app.tour.active
        assert any(app.tour.steps[0]["title"] in text for text in visible)
        driver.click("Next ►")
        assert app.tour.step_idx == 1 and app.tour.awaiting
        driver.draw(3)
        target = app._target_rect("example")
        assert target is not None
        driver.click(target)
        assert app.files_step.checked_files
        assert not app.tour.awaiting
    finally:
        app.close()
