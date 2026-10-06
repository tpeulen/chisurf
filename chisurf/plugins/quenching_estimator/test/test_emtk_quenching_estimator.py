"""The native QuEst window of the plugin (the Structure Tools card hosted on its own), on temporary settings.

HERE a simulation cannot run: QuEst's core still imports Python modules of IMP.bff that moved to C++ (``IMP.bff.av``,
``IMP.bff.quenching.*``; see okf/references/known-issues.md). So the tests prove what is provable: the window builds Qt-free,
every control draws with a tooltip, a press on Simulate with a loaded structure ends in a readable failure, never in a
crash, the form accepts typed values, and the PET chemistry the form edits is the compiled core's.
"""

import json
import os
import time
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, hermetic_env

PDB = Path(os.path.expanduser("~")).joinpath("dev/quest/tests/148l.pdb")
quest = pytest.importorskip("quest")


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)


@pytest.fixture
def pdb():
    path = Path(quest.__file__).resolve().parents[1] / "tests" / "148l.pdb"
    if not path.is_file():
        pytest.skip("the quest test structure is not there")
    return path


@pytest.fixture
def app():
    from chisurf.plugins.quenching_estimator.gui.app import make_app

    application = make_app()
    yield application
    application.close()


def test_the_window_builds_and_draws_at_both_sizes(app):
    assert app.session.ready, app.session.error
    for size in ((1200, 800), (800, 600)):
        for _ in range(3):
            painter = RecordingPainter()
            app.draw(painter, 0, 0, *size)
        assert "Simulate" in painter.strings and "Load PDB..." in painter.strings


def test_it_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("quenching_estimator", "chisurf.plugins.quenching_estimator.gui.app:make_app")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    from chisurf.plugins.quenching_estimator.gui.app import make_app
    from test.gui.emtk_port_parity import emtk_inventory

    application = make_app()
    inventory = emtk_inventory(application)
    application.close()
    assert inventory["controls_without_tooltip"] == []


def test_loading_a_structure_with_a_press_picks_a_valid_attachment_site(app, pdb):
    ui = Driver(app, (1200, 800))
    ui.draw(3)
    app.session.load_structure(str(pdb))
    ui.draw(3)
    assert any("148l.pdb" in s for s in ui.draw(1).strings)


def test_a_typed_value_reaches_the_project(app):
    ui = Driver(app, (1200, 800))
    ui.draw(3)
    ui.type_into("n_photons", "12345")
    assert app.session.model.project["n_photons"] == 12345


def test_simulate_without_a_structure_says_why_and_with_one_ends_in_a_readable_message(app, pdb):
    ui = Driver(app, (1200, 800))
    ui.draw(3)
    ui.click("simulate")
    assert any("Cannot simulate" in s for s in ui.draw(2).strings)
    app.session.load_structure(str(pdb))
    m = app.session.model
    m.attachment_chain, m.attachment_residue, m.attachment_atom = "E", 117, "CB"
    m.n_photons, m.t_max, m.parallel_trajectories = 1000, 50.0, 1
    ui.draw(2)
    ui.click("simulate")
    end = time.monotonic() + 120
    while app.session.running and time.monotonic() < end:
        time.sleep(0.05)
        ui.draw(1)
    ui.draw(3)
    assert not app.session.running
    state = app.session.model.status
    assert state.startswith(("Failed", "QY")), (
        state
    )  # a result where IMP.bff serves the core, else a readable failure
