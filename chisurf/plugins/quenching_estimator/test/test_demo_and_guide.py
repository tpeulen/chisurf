"""The demo the guided tour starts from computes a quenched result, and every tour step points at a drawn control."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

GUIDE = Path(__file__).resolve().parents[1] / "gui" / "guide.json"


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    from chisurf.plugins.microscopy.imaging_emtk.testing import hermetic_env

    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.setenv("QUEST_RUNS_DIR", str(tmp_path / "jobs"))


def test_the_demo_ships_its_structure_and_is_quenched():
    from chisurf.plugins.quenching_estimator.api.local import simulate_project
    from chisurf.plugins.quenching_estimator.demo import DEMO_STRUCTURE, apply_demo
    from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

    assert DEMO_STRUCTURE.is_file()
    model = ProjectFormModel(locale="en")
    apply_demo(model)
    assert model.validate() == []
    project = json.loads(json.dumps(model.to_project_dict()))
    assert project["fret"]["enabled"] is False
    result = simulate_project(project, save_outputs=False)
    # E36 at IMP.bff's default AV: labelable, and quenched (0.864 at seed 7 on 2026-10-12 with
    # FPS's every-node link search; 0.913 with the seed-only search before it).
    assert 0.5 < result.quantum_yield_donor < 0.99


def test_every_tour_step_points_at_a_control_the_window_draws():
    from chisurf.plugins.quenching_estimator.gui.app import make_app
    from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

    app = make_app()
    try:
        ui = Ui(app, (800, 600))
        ui.draw(3)
        steps = json.loads(GUIDE.read_text(encoding="utf-8"))["steps"]
        unresolved = [
            step["title"]
            for step in steps
            if app.tour._target_key(step.get("target"))
            and app.item_rects.get(app.tour._target_key(step.get("target"))) is None
        ]
        assert unresolved == []
    finally:
        app.close()


def test_load_example_then_simulate_by_clicks_ends_in_a_quantum_yield():
    from chisurf.plugins.quenching_estimator.gui.app import make_app
    from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

    app = make_app()
    try:
        ui = Ui(app, (800, 600))
        ui.draw(3)
        ui.click("load_example")
        assert app.session.model.project["attachment"]["residue"] == 36
        ui.click("simulate")
        end = time.monotonic() + 300
        while app.session.running and time.monotonic() < end:
            time.sleep(0.05)
            ui.draw(1)
        ui.draw(2)
        assert app.session.model.status.startswith("QY"), app.session.model.status
    finally:
        app.close()


def test_make_demo_writes_a_stamped_project_once_and_load_example_reads_it(tmp_path):
    """The demo contract: ``make_demo`` caches structure + project, ``load_example`` reads that project."""
    from chisurf.plugins.quenching_estimator.demo import DEMO, demo_folder, make_demo
    from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

    path = make_demo()
    assert path.parent == demo_folder() and path.is_file()
    project = json.loads(path.read_text(encoding="utf-8"))
    assert Path(project["pdb"]).parent == demo_folder() and Path(project["pdb"]).is_file()
    assert project["attachment"] == {"chain": "E", "residue": 36, "atom": "CB"}
    assert project["random_seed"] == DEMO["random_seed"]
    stamp = path.stat().st_mtime_ns
    assert make_demo() == path and path.stat().st_mtime_ns == stamp  # reused, not rewritten
    elsewhere = make_demo(tmp_path / "own", overwrite=True)
    assert elsewhere.parent == tmp_path / "own"

    model = ProjectFormModel(locale="en")
    assert model.load_example() == path
    assert model.attachment_residue == 36 and model.fret_enabled is False
