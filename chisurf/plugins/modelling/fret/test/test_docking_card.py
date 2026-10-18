"""The FRET docking card: request parity with the form model, project round trip, a real run. Hermetic: temp
settings, no network, real example files."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from chisurf.plugins.modelling.fret.gui.docking_card import make_app as make_dock
from chisurf.plugins.modelling.fret.gui.docking_session import DockingSession
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
EXAMPLE = REPO / "chisurf/plugins/modelling/fret/examples/fps_hiv_rt"
SIZES = [(1200, 800), (800, 600)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture()
def inputs(tmp_path):
    for name in ("protein_1R0A.pdb", "dna.pdb"):
        shutil.copy(EXAMPLE / name, tmp_path / name)
    payload = json.loads((EXAMPLE / "hiv_rt.fps.json").read_text())
    for pos in payload["Positions"].values():
        pos["pdb_path"] = str(
            tmp_path / ("dna.pdb" if pos["chain_identifier"] == "P" else "protein_1R0A.pdb")
        )
    names = list(payload["Distances"])
    payload["χ²"] = {"all": {"distances": names}}
    fps = tmp_path / "x.fps.json"
    fps.write_text(json.dumps(payload))
    return fps


# ---- docking ----------------------------------------------------------------------------------------------------


def test_docking_request_equals_the_form_model(inputs, tmp_path):
    from chisurf.plugins.modelling.fret.gui.docking_model import DockingModel as _DockingModel

    s, q = DockingSession(), _DockingModel()
    pdbs = [str(tmp_path / "protein_1R0A.pdb"), str(tmp_path / "dna.pdb")]
    for m in (s, q):
        m.fps_json, m.output_dir, m.n_frames, m.sigma_da = str(inputs), str(tmp_path / "o"), 77, 4.5
    s.add_pdbs(pdbs)
    q.pdb_paths = ", ".join(pdbs)
    for op in ("dock", "refine", "screen", "score"):
        s.operation = q.operation = op
        assert s.build_params() == q.build_params()
    s.operation = q.operation = "dock"
    s.n_repeats = q.n_repeats = 3
    assert s.build_params() == q.build_params()


@pytest.mark.parametrize(
    ("attribute", "value"),
    [
        ("n_frames", 77),
        ("mc_steps", 8),
        ("n_best", 4),
        ("n_repeats", 3),
        ("refine_av_cycles", 1),
        ("fixed_body", 1),
        ("sigma_da", 4.5),
        ("simulated_annealing", True),
        ("ev_weight", 2.5),
        ("save_distributions", True),
        ("av_backend", "imp-bff"),
        ("save_trajectory", True),
    ],
)
def test_docking_project_round_trip_preserves_control_settings(inputs, tmp_path, attribute, value):
    session = DockingSession()
    session.add_pdbs([str(tmp_path / "protein_1R0A.pdb"), str(tmp_path / "dna.pdb")])
    session.fps_json = str(inputs)
    session.output_dir = str(tmp_path / "out")
    setattr(session, attribute, value)
    project = tmp_path / "docking-project.json"
    assert session.save_project(str(project))

    restored = DockingSession()
    assert restored.load_project(str(project))
    assert getattr(restored, attribute) == value


def _needs_docking_engine():
    """Skip where this IMP.bff has no docking engine (the IMP-free ``core`` wheel)."""
    import IMP.bff as bff

    if not hasattr(bff, "dock"):
        pytest.skip(
            f"this IMP.bff (build {bff.get_build()}) has no docking engine; docking needs a "
            "build that links IMP (see the imp-bff note in pixi.toml)"
        )


def test_docking_runs_and_lists_the_result(inputs, tmp_path):
    _needs_docking_engine()
    app = make_dock()
    s = app.session
    s.add_pdbs([str(tmp_path / "protein_1R0A.pdb"), str(tmp_path / "dna.pdb")])
    s.fps_json, s.output_dir, s.n_frames = str(inputs), str(tmp_path / "out"), 30
    ui = Ui(app, (1200, 800))
    ui.click("run")
    assert s.running
    assert s.poll_wait(120)
    ui.draw(3)
    assert (
        len(s.rows) == 1 and s.rows[0]["score"] > 0 and (tmp_path / "out" / "docked.pdb").exists()
    )
    app.close()


def test_docking_repeats_give_one_row_per_trial(inputs, tmp_path):
    _needs_docking_engine()
    s = DockingSession()
    s.add_pdbs([str(tmp_path / "protein_1R0A.pdb"), str(tmp_path / "dna.pdb")])
    s.fps_json, s.output_dir, s.n_frames, s.n_repeats = str(inputs), str(tmp_path / "out"), 20, 2
    assert s.start() and s.poll_wait(120)
    assert len(s.rows) == 2 and "2 trials" in s.status
    s.close()


def test_docking_missing_input_and_drop(inputs, tmp_path):
    app = make_dock()
    ui = Ui(app, (800, 600))
    ui.click("run")
    assert ui.shown("Add at least one PDB file")
    assert (
        ui.drop(tmp_path / "dna.pdb", inputs)
        and app.session.pdb_files
        and app.session.fps_json == str(inputs)
    )
    app.close()


def test_load_example_copies_the_hiv_rt_project_and_fills_the_inputs(tmp_path, monkeypatch):
    """The tour's Load example works on a copy in the settings folder, never on the package's files."""
    from chisurf.plugins.modelling.fret import demo

    monkeypatch.setattr(demo, "demo_folder", lambda: tmp_path / "demo")
    app = make_dock()
    ui = Ui(app, (1100, 720))
    ui.click("load_example")
    s = app.session
    assert [Path(p).name for p in s.pdb_files] == ["protein_1R0A.pdb", "dna.pdb"]
    assert Path(s.fps_json) == tmp_path / "demo" / "hiv_rt.fps.json"
    assert demo.make_demo(tmp_path / "demo") == tmp_path / "demo" / "docking_project.json"
    app.close()
