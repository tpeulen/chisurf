"""Count Rate and Time Windows declare geometry without changing measured workflows."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.emtk.state import attach_native_state
from chisurf.plugins.tttr.tttr_count_rate_analysis.gui.controller import create_app as rate_app
from chisurf.plugins.tttr.tttr_time_windows.gui.controller import create_app as time_app


@pytest.fixture
def tools(tmp_path, monkeypatch):
    """Keep all inputs, settings and outputs in private scratch storage."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    return {"tttr_count_rate_analysis": rate_app, "tttr_time_windows": time_app}


@pytest.mark.parametrize("plugin_id", ["tttr_count_rate_analysis", "tttr_time_windows"])
def test_base_and_standalone_share_the_primary_window_default(tools, plugin_id):
    """The actual baseapp owns the declaration, not only its standalonewrapper."""
    app = tools[plugin_id]()
    try:
        assert app.window_size == (1100, 720)
        base = type(app).__bases__[0](app.tool)
        assert base.window_size == (1100, 720)
        Driver(base, base.window_size).draw(3)
    finally:
        app.close()


@pytest.mark.parametrize("plugin_id", ["tttr_count_rate_analysis", "tttr_time_windows"])
def test_saved_custom_geometry_and_dock_placement_win(tools, plugin_id):
    """A realclose/reopen persistencecycle preserves resize and meaningfullayout."""
    app = attach_native_state(plugin_id, tools[plugin_id]())
    gui = app.count_rate_gui if plugin_id == "tttr_count_rate_analysis" else app.time_window_gui
    Driver(app, (1100, 720)).draw(3)
    gui.docks.undock("files", (40, 50, 440, 400))
    saved = gui.docks.state()
    app.window_resized(1390, 910)
    app.close()
    reopened = attach_native_state(plugin_id, tools[plugin_id]())
    try:
        gui = (
            reopened.count_rate_gui
            if plugin_id == "tttr_count_rate_analysis"
            else reopened.time_window_gui
        )
        assert reopened.window_size == (1390, 910)
        assert gui.docks.state()["layout"] == saved["layout"]
        assert gui.docks.state()["windows"] == saved["windows"]
        Driver(reopened, reopened.window_size).draw(3)
    finally:
        reopened.close()


@pytest.mark.parametrize("plugin_id", ["tttr_count_rate_analysis", "tttr_time_windows"])
def test_primary_spec_reaches_shared_reader(tools, monkeypatch, plugin_id):
    """Factories consume the existingprimaryspec through the sharedreader."""
    import chisurf.plugins.tttr.tttr_count_rate_analysis.gui.app as rate
    import chisurf.plugins.tttr.tttr_time_windows.gui.app as windows

    module = rate if plugin_id == "tttr_count_rate_analysis" else windows
    original = module.window_size
    seen = []

    def declared(spec, default):
        """Record exactprimarydeclaration and exercise a differentlogicalsize."""
        seen.append((spec["window"], default))
        return original({**spec, "window": {"width": 1234, "height": 789}}, default)

    monkeypatch.setattr(module, "window_size", declared)
    app = tools[plugin_id]()
    try:
        assert app.window_size == (1234, 789)
        assert seen == [({"width": 1100, "height": 720}, (1100, 720))]
    finally:
        app.close()


def test_real_calculate_process_and_resize_preserve_science_and_output(tools, tmp_path):
    """Actualworkerbutton workflows preserve6.7Mphotons and16ten-secondwindows."""
    from chisurf.core.fio.staging import open_tttr

    sample = tmp_path / "Leica_SP5.ptu"
    shutil.copyfile(Path(__file__).parents[1] / "data/clsm/Leica_SP5.ptu", sample)
    source_hash = hashlib.sha256(sample.read_bytes()).hexdigest()
    tttr = open_tttr(sample)
    assert len(tttr) == 6714549
    channels = [int(ch) for ch in tttr.get_used_routing_channels()]
    setup = {
        "detectors": {"all": {"chs": channels, "micro_time_ranges": []}},
        "windows": {"": None},
    }
    rate = rate_app(setups={"Leica all": setup})
    try:
        rate.tool.add_paths([sample])
        driver = Driver(rate, rate.window_size)
        driver.draw(3)
        driver.click("calculate")
        if rate.tool.job.future is not None:
            rate.tool.job.future.result(timeout=30)
        rate.tool.job.poll()
        rows = rate.tool._model.results_rows()
        assert rows == [
            {
                "channel": "all",
                "mean_khz": 44.72292671613037,
                "std_khz": 0.0,
                "photons": 6714549,
                "time_s": 150.13661879999998,
            }
        ]
        driver.draw(3, size=(1390, 910))
        assert rate.tool._model.results_rows() == rows
    finally:
        rate.close()
    windows = time_app()
    try:
        windows.tool.time_window_ms = 10000.0
        windows.tool.output_dir_text = str(tmp_path / "output")
        windows.tool.add_paths([sample])
        windows.tool.job.future.result(timeout=30)
        windows.tool.job.poll()
        driver = Driver(windows, windows.window_size)
        driver.draw(3)
        driver.click("process")
        if windows.tool.job.future is not None:
            windows.tool.job.future.result(timeout=30)
        windows.tool.job.poll()
        # the splitter's output is the container holding the time_window run:
        # sixteen inclusive windows, consecutive ones tiling without overlap
        import numpy as np

        from chisurf.core.datastore import row_count
        from chisurf.core.fio.fluorescence.burst_tree import read_burst_table

        container = next((tmp_path / "output").rglob("*.pto"))
        table = read_burst_table(container)
        assert table is not None and row_count(table) == 16
        rows = np.asarray(
            [tuple(r) for r in zip(table["first photon"], table["last photon"])],
            dtype=np.int64,
        ).reshape(-1, 2)
        assert (rows[1:, 0] == rows[:-1, 1] + 1).all()
        assert not list((tmp_path / "output").rglob("*.bst"))
        driver.draw(3, size=(1390, 910))
        again = read_burst_table(container)
        assert row_count(again) == 16 and (
            np.asarray(
                [tuple(r) for r in zip(again["first photon"], again["last photon"])],
                dtype=np.int64,
            ).reshape(-1, 2)
            == rows
        ).all()
        assert hashlib.sha256(sample.read_bytes()).hexdigest() == source_hash
    finally:
        windows.close()
