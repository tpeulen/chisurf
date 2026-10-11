"""The hub computes intensity, N&B, micro-time and phasor in the background and recomputes them on a setup change."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from chisurf.plugins.microscopy.imaging_emtk import pixel_testing as data
from chisurf.plugins.microscopy.imaging_emtk.testing import hermetic_env
from chisurf.plugins.microscopy.imaging_tools.gui.app import ImagingToolsApp

from .test_emtk_imaging_tools_clicks import HubDriver
from .test_emtk_imaging_tools_parity import BIG, Client

STEPS = ImagingToolsApp.ANALYSIS_ROLES


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


def settle(drv, seconds=240.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        drv.draw(1)
        app = drv.app
        if not app.precompute_pending() and not app._any_child_busy() and not app._precomputing:
            return
        time.sleep(0.02)
    raise AssertionError("the background compute did not finish")


def test_a_new_source_precomputes_every_step_and_a_setup_change_recomputes_them(tmp_path):
    (tmp_path / "scan").mkdir()
    source = Path(data.flim_ptu(tmp_path / "scan" / "flim.ptu"))
    app = ImagingToolsApp(client=Client())
    drv = HubDriver(app, BIG)
    drv.draw(3)
    try:
        assert not app.children.keys() & set(
            STEPS
        )  # nothing built yet: lazy until a source is known
        app.set_pipeline(source=str(source))
        assert app.precompute_pending() == list(STEPS)
        settle(drv)
        for role in STEPS:
            model = app.children[role].model
            assert model._columns, f"{role} was not precomputed"
            assert not model.needs_recompute()
        assert "ready" in app.status

        # switching to a tab shows the finished results without a Run press
        for role in STEPS:
            drv.click(drv.rect("entry:" + role))
            drv.draw(2)
            assert app.selected == role and app.children[role].model._columns
            assert not app.children[role].job.busy
        first = {r: dict(app.children[r].model._columns) for r in STEPS}

        # a setup change makes the maps stale and the hub recomputes them with the new windows
        setup = {
            "detectors": {
                "ch0": {"chs": [0], "micro_time_ranges": [[0, 1000]]},
                "late": {"chs": [0], "micro_time_ranges": [[1000, 4095]]},
            }
        }
        app.set_setup(setup)
        assert app.precompute_pending()
        assert any(app.children[r].model.needs_recompute() for r in STEPS)
        settle(drv)
        for role in STEPS:
            model = app.children[role].model
            assert not model.needs_recompute(), role
            assert set(model.detectors) == {"ch0", "late"}, role
            assert model._columns and set(model._columns) != set(first[role]), role
    finally:
        app.close()
