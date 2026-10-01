"""Native workflow orchestration exercises the real backend boundaries."""

import threading

import pandas as pd
import pytest

from chisurf.plugins.burst.burst_2cde.core import computation as core
from chisurf.plugins.burst.burst_2cde.gui.app import BurstTwoCdeApp
from chisurf.plugins.burst.burst_2cde.gui.controller import TwoCdeController
from chisurf.plugins.burst.burst_2cde.gui.view_model import TwoCdeViewModel


def test_native_compute_snapshot_output_and_unlock(tmp_path, monkeypatch):
    model = TwoCdeViewModel()
    model.set_folder(tmp_path)
    ctrl = TwoCdeController(model)
    table = pd.DataFrame({"Proximity Ratio": [0.4], core.COLUMN_FRET_2CDE: [12.0]})
    monkeypatch.setattr(core, "read_burst_analysis", lambda *args, **kw: (table, {}))
    settings = []
    monkeypatch.setattr(core, "compute_2cde", lambda df, tttrs, **kw: settings.append(kw) or df)
    written = []
    monkeypatch.setattr(
        core, "write_2cde_analysis", lambda *args, **kw: written.append(kw["variant"])
    )
    try:
        ctrl.run()
        assert model.is_locked
        model.variant = "alex"
        ctrl._future.result(timeout=5)
        ctrl.poll()
        assert settings[0]["tau"] == pytest.approx(100e-6)
        assert settings[0]["variant"] == "fret"
        assert written == ["fret"]
        assert model.last_computed_variant == "fret"
        assert not model.is_locked and not model.is_running
    finally:
        ctrl.close()


def test_native_stop_discards_result_and_does_not_write(tmp_path, monkeypatch):
    model = TwoCdeViewModel()
    model.set_folder(tmp_path)
    ctrl = TwoCdeController(model)
    ready, release = threading.Event(), threading.Event()

    def read(*args, **kwargs):
        ready.set()
        assert release.wait(5)
        return pd.DataFrame(), {}

    monkeypatch.setattr(core, "read_burst_analysis", read)
    writes = []
    monkeypatch.setattr(core, "write_2cde_analysis", lambda *args, **kw: writes.append(True))
    try:
        ctrl.run()
        assert ready.wait(5)
        ctrl.stop()
        release.set()
        try:
            ctrl._future.result(timeout=5)
        except InterruptedError:
            pass
        ctrl.poll()
        assert model.df is None and not writes
        assert not model.is_running
        assert "cancelled" in model.status_text
    finally:
        release.set()
        ctrl.close()


def test_native_app_has_wired_workflow_and_folder_drop(tmp_path):
    app = BurstTwoCdeApp()
    try:
        assert app.two_cde_gui.on_run == app.controller.run
        stray = tmp_path / "run.ptu"
        app.controller.on_paths_dropped([stray])
        assert "is not one" in app.model.status_text
    finally:
        app.controller.close()
