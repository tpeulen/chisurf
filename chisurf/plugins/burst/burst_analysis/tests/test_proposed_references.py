"""Data Selection is the one place the workflow's references come from: it proposes those beside a
measurement into their rows, and Burst MLE takes only what it declares.

Burst MLE used to pick Rh110 and Alexa647 from the measurement's folder by name on its own,
before Data Selection had them -- so it used Rh110 with no G computed, and Alexa647 for both red
detectors. Now the files found beside a measurement land in Data Selection's rows (shown as
found, removable, never proposed again once removed), G and the volume are computed from them,
and the pipeline's Burst MLE reads nothing by name.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from chisurf.plugins.burst.burst_analysis import demo
from chisurf.plugins.burst.burst_analysis.gui.data_selection_app import (
    BurstDataSelectionApp,
    BurstDataSelectionModel,
)


@pytest.fixture(autouse=True)
def _packaged_dye_database(monkeypatch):
    from chisurf.core.fluorescence import dyes

    monkeypatch.setattr(dyes, "_entries_from_database", lambda: None)
    dyes.reference_dyes(refresh=True)
    yield
    monkeypatch.undo()
    dyes.reference_dyes(refresh=True)


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    where = tmp_path_factory.mktemp("proposed")
    files = demo.make_demo(where)
    files["red"] = demo.make_red_reference(where)
    return files


def _app():
    from chisurf.emtk.i18n import install

    install()
    model = BurstDataSelectionModel(auto_import=False)
    setup = copy.deepcopy(demo.SETUP_PIE)
    return BurstDataSelectionApp(model, setup_provider=lambda: setup), model, setup


def test_the_references_beside_a_measurement_are_proposed_into_their_rows(folder):
    app, model, _setup = _app()
    model.add_paths([folder["measurement"]])
    rows = model.rows()
    assert rows[str(Path(folder["measurement"]).resolve())] == "measurement"
    assert rows[str(Path(folder["reference"]).resolve())] == "reference:G"  # Rh110: green
    assert rows[str(Path(folder["red"]).resolve())] == "reference:R"  # Alexa 647: red
    assert rows[str(Path(folder["irf"]).resolve())] == "irf:G"
    assert rows[str(Path(folder["buffer"]).resolve())] == "buffer"
    # shown as found, with where from
    entry = next(r for r in app.assignment_rows() if r.get("path") == str(Path(folder["red"]).resolve()))
    assert entry["info"] == "found" and "sample_dsDNA.ptu" in entry["tip"]

    # removed by the user: gone, and not proposed again
    model.remove_paths([Path(folder["red"]).resolve()])
    model.add_paths([folder["measurement"]])  # again: nothing new
    assert str(Path(folder["red"]).resolve()) not in model.rows()
    state = model.export_settings()
    assert str(Path(folder["red"]).resolve()) in state["declined"]
    again = BurstDataSelectionModel(auto_import=False)
    again.setup = copy.deepcopy(demo.SETUP_PIE)
    again.restore_settings(state)
    assert again.declined == model.declined and again.proposed == model.proposed


def test_the_pipeline_mle_reads_only_what_data_selection_declares(folder):
    """Without references declared, the pipeline's Burst MLE finds none by name beside the data:
    its IRF comes from the photons outside the bursts. Declared, a red dye never serves the green
    detector and a green dye never the red ones."""
    from chisurf.plugins.burst.burst_analysis.workflow_context import BurstWorkflowContext
    from chisurf.plugins.burst.burst_mle_analysis import engine
    from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel

    model = MleViewModel(engine.MleSession())
    model.set_setup(copy.deepcopy(demo.SETUP_PIE))
    model.prepare_patterns([str(folder["measurement"])], {"buffer": [], "irf": {}, "reference": {}})
    assert model.session.irf_files == {}  # nothing by name

    context = BurstWorkflowContext(channel_settings=copy.deepcopy(demo.SETUP_PIE))
    context.samples = {str(folder["measurement"]): "measurement", str(folder["reference"]): "reference:G"}
    model.prepare_patterns([str(folder["measurement"])], context.references())
    assert model.session.irf_files.get("G|G") == [Path(folder["reference"])]
    assert "R|G" not in model.session.irf_files and "R|R" not in model.session.irf_files

    # the standalone tool (no Data Selection) still looks beside the data
    standalone = MleViewModel(engine.MleSession())
    standalone.set_setup(copy.deepcopy(demo.SETUP_PIE))
    standalone.prepare_patterns([str(folder["measurement"])], None)
    assert standalone.session.irf_files
