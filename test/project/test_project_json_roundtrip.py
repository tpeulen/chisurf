from __future__ import annotations

import json

import numpy as np

from chisurf.core.project import Project, ProjectArchive, load_project, save_project


def _representative_project(name="unit_test_project"):
    """Capture a real reader/experiment, curve and shipped scientific model."""
    from chisurf.core.data import DataCurve
    from chisurf.core.experiments.core.experiment import Experiment
    from chisurf.core.experiments.tcspc.reader import TCSPCReader
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.description import tcspc_lifetime
    from chisurf.core.project import capture_session

    experiment = Experiment(name="TCSPC", unique_identifier="exp1")
    experiment.add_model_class(tcspc_lifetime)
    curve = DataCurve(
        x=np.array([0.0, 1.0, 2.0]), y=np.array([10.0, 6.0, 3.0]), unique_identifier="ds1"
    )
    curve.data_reader = TCSPCReader(experiment=experiment)
    fit = Fit(data=curve, model_class=tcspc_lifetime)
    fit.unique_identifier = "fit1"
    project = capture_session([curve], [fit], name=name)
    project.description = "Project JSON round-trip test"
    project.chisurf_version = "test-version"
    project.ui_state["current_experiment_id"] = "exp1"
    return project


def test_project_json_roundtrip(tmp_path):
    project_dir = tmp_path / "test_project"

    p = _representative_project()

    archive_path = save_project(p, project_dir)

    # Ensure the archive was created where we expect it
    assert archive_path.is_file()
    assert archive_path.name.endswith(".cs.pto")

    # Inspect the exact returned PTO path through the supported archive reader.
    archive = ProjectArchive.open(archive_path)
    raw = json.loads(archive.read_text("project.json"))
    archive.close()

    assert raw["meta"]["name"] == "unit_test_project"
    assert raw["project_format_version"] == 5
    assert "datasets" in raw and "ds1" in raw["datasets"]

    # Load back into a Project instance and compare key fields
    loaded = load_project(project_dir)

    assert isinstance(loaded, Project)
    assert loaded.name == p.name
    assert loaded.description == p.description
    assert loaded.chisurf_version == p.chisurf_version
    assert loaded.project_format_version == p.project_format_version
    assert loaded.datasets == p.datasets
    assert loaded.experiments == p.experiments
    assert loaded.fits == p.fits
    assert loaded.ui_state == p.ui_state
