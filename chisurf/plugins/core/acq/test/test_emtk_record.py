"""The Record tool driven through its real controls: example, start, run, the run in the workspace."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from chisurf.plugins.core.acq.gui.record_app import HERE, RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1400, 900)


def _run_to_end(ui, model, timeout=120.0):
    end = time.monotonic() + timeout
    while model.running:
        assert time.monotonic() < end, "the run did not end"
        ui.draw(1)
        time.sleep(0.02)
    ui.draw(3)


@pytest.fixture
def app(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    app = RecordApp(model)
    yield app
    app.close()


def test_the_example_runs_and_lands_in_the_workspace(app):
    from chisurf.core.api import dataset_objects

    model = app.model
    ui = Driver(app, SIZE)
    ui.draw(3)
    ui.click("load_example")
    model.duration_s = 5.0
    ui.draw(2)
    ui.click("start")
    _run_to_end(ui, model)
    result = model.session.result
    assert result.stop_reason == "duration reached" and result.bursts > 50
    assert Path(result.ptu).exists()
    assert "bursts" in model.status_text  # a few words; the details are in the tooltip
    assert "In Datasets" in model.status_detail and model.saved_path == Path(result.ptu)
    snap = model.snapshot
    assert snap["bursts"] == result.bursts
    assert snap["histograms"]["Proximity Ratio vs Stoichiometry"]["counts"].sum() > 0
    assert model.plot_choice == "Proximity Ratio vs Stoichiometry"
    rows = {str(getattr(d, "address", "")): d for d in dataset_objects()}
    assert str(result.ptu) in rows
    run = rows.get(result.run_address)
    assert run is not None and str(getattr(run, "data_kind", "")) == "bursts"
    assert "Bursts:" in " ".join(ui.strings())


def test_a_two_colour_run_shows_the_proximity_ratio_and_no_stoichiometry(app):
    model = app.model
    ui = Driver(app, SIZE)
    ui.draw(3)
    ui.click("load_example")
    model.sim_scheme, model.duration_s = "two_color", 8.0
    ui.draw(2)
    assert model.make_experiment(400).preset == "two_color"
    ui.click("start")
    _run_to_end(ui, model)
    snap = model.snapshot
    assert list(snap["histograms"]) == ["Proximity Ratio"]
    assert "Stoichiometry" not in model.session.result.table
    checks = {c["name"]: c for c in (snap["qc"] or {}).get("checks", [])}
    assert checks["donor-only / acceptor-only"]["value"] == "not applicable"


def test_without_a_connected_device_neither_connect_nor_start_is_offered(app, monkeypatch):
    from chisurf.plugins.core.acq.live import devices

    # never enumerate (let alone open) the owner's real MultiHarp in a test
    monkeypatch.setattr(devices, "attached_devices", lambda: [])
    app.model._found_at = -1e9
    app.model.source_kind = "device"
    assert not app.model.enabled("connect_device")
    assert not app.model.enabled("start")
    assert app.model.start() is False
    assert app.model.device is None


def test_every_guide_step_points_at_a_drawn_control(app):
    ui = Driver(app, SIZE)
    ui.draw(3)
    steps = json.loads((HERE / "record_guide.json").read_text(encoding="utf-8"))["steps"]
    for step in steps:
        target = (step.get("target") or {}).get("name")
        if target:
            assert target in app.form.rects, target
