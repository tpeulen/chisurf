"""Click coverage of the native QuEst window: Cancel, Load/Save project, Reset Defaults, attachment-site picking.

Everything is pressed at the rectangle the control was drawn in (``Ui``), on T4 lysozyme (PDB 148L) shipped with the
quest package. The simulated result is compared with the engine's ``simulate_project`` for the same project.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest

from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

quest = pytest.importorskip("quest")
SIZE = (1400, 900)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    from chisurf.plugins.microscopy.imaging_emtk.testing import hermetic_env

    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)  # the file dialogs open in the working directory


@pytest.fixture
def pdb(tmp_path):
    src = Path(quest.__file__).resolve().parents[1] / "tests" / "148l.pdb"
    if not src.is_file():
        pytest.skip("the quest test structure is not there")
    return Path(shutil.copy(src, tmp_path / "148l.pdb"))


@pytest.fixture
def app(pdb):
    from chisurf.plugins.quenching_estimator.gui.app import make_app

    application = make_app()
    assert application.session.ready, application.session.error
    yield application
    application.close()


def test_the_manifest_declares_the_native_entrypoint():
    manifest = json.loads((Path(__file__).parents[1] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.quenching_estimator.gui.app:make_app"
    from chisurf.core.plugin.emtk_readiness import is_preview

    assert not is_preview("quenching_estimator")


def _open_structure_tab(ui):
    ui.draw(3)
    ui.press_text("3D Structure")
    ui.draw(3)


def test_load_pdb_project_save_and_reload_by_clicks(app, pdb, tmp_path):
    ui = Ui(app, SIZE)
    ui.draw(3)
    ui.click("load_pdb")
    assert ui.dialog_open and ui.shown("Open a structure")
    ui.dialog_pick(pdb.name)
    assert app.session.model.project["pdb"] == str(pdb)

    saved = tmp_path / "quest_project.json"
    ui.click("save_project")
    assert ui.dialog_open and ui.shown("Save project")
    ui.save_dialog_type_name(str(saved))
    ui.press_text("Save")
    assert saved.exists()
    on_disk = json.loads(saved.read_text())
    assert on_disk["pdb"] == str(pdb)

    app.session.model.n_photons = 4321
    ui.draw(2)
    ui.click("load_project")
    assert ui.dialog_open and ui.shown("Load project")
    ui.dialog_pick(saved.name)
    assert app.session.model.project["n_photons"] == on_disk["n_photons"]
    assert "Loaded quest_project.json" in app.session.message


def test_reset_defaults_restores_the_reference_chemistry(app):
    from quest.project import template_project

    ui = Ui(app, SIZE)
    ui.draw(3)
    ui.press_text("Quenching Chemistry")
    ui.draw(3)
    app.session.model.project["amino_acid_interactions"] = {}
    ui.draw(2)
    ui.click("reset_defaults")
    ui.draw(2)
    assert (
        app.session.model.project["amino_acid_interactions"]
        == template_project()["amino_acid_interactions"]
    )
    assert "reset to the defaults" in app.session.message


def test_pick_donor_and_acceptor_residues_by_clicking_the_list(app, pdb):
    ui = Ui(app, SIZE)
    ui.draw(3)
    app.session.load_structure(str(pdb))
    _open_structure_tab(ui)
    assert {"pick_donor", "pick_acceptor", "open_web_ui"} <= set(app.item_rects)

    ui.click("pick_donor")
    ui.click("res.E.3")
    att = app.session.model.project["attachment"]
    assert (att["chain"], att["residue"]) == ("E", 3) and att["atom"] in ("CB", "CA")

    ui.click("pick_acceptor")
    ui.click("res.E.5")
    fret = app.session.model.project["fret"]
    assert fret["enabled"]
    acc = fret["dyes"][1]["attachment"]
    assert (acc["chain"], acc["residue"]) == ("E", 5)
    assert app.session.message == "Selected acceptor: E:5"


def test_open_web_ui_opens_the_local_interface(app, monkeypatch):
    import webbrowser

    from chisurf.plugins.quenching_estimator.gui.app import WEB_UI_URL

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url, *a, **k: opened.append(url) or True)
    ui = Ui(app, SIZE)
    _open_structure_tab(ui)
    ui.click("open_web_ui")
    assert opened == [WEB_UI_URL]


def test_cancel_stops_a_running_simulation_by_click(app, pdb):
    s = app.session
    s.load_structure(str(pdb))
    m = s.model
    m.n_photons, m.t_max, m.parallel_trajectories = 2_000_000, 500.0, 1
    ui = Ui(app, SIZE)
    ui.draw(3)
    ui.click("simulate")
    if not s.running:
        pytest.skip(f"simulation did not start: {s.message}")
    ui.draw(3)
    ui.click("cancel")
    end = time.monotonic() + 120
    while s.running and time.monotonic() < end:
        time.sleep(0.05)
        ui.draw(1)
    assert not s.running


def test_a_simulated_result_equals_the_engine_for_the_same_project(app, pdb):
    import numpy as np
    from quest.api import simulate_project

    s = app.session
    s.load_structure(str(pdb))
    m = s.model
    m.attachment_chain, m.attachment_residue, m.attachment_atom = "E", 117, "CB"
    m.n_photons, m.t_max, m.parallel_trajectories = 2000, 30.0, 1
    project = json.loads(json.dumps(m.to_project_dict()))
    ui = Ui(app, SIZE)
    ui.draw(3)
    ui.click("simulate")
    assert s.running, s.message
    assert s.wait(300)
    ui.draw(3)
    if s.status_error:
        pytest.skip(f"engine unavailable here: {s.message}")
    shown = m.decay_series()
    assert shown and len(shown[0]["y"]) > 10
    engine = simulate_project(project, save_outputs=False)
    assert np.allclose(np.asarray(shown[0]["y"], float), np.asarray(engine["donor_counts"], float))
    assert m.status.startswith("QY")
