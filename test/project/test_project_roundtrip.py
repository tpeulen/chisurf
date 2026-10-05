from __future__ import annotations

# Consolidated test file: test_project_roundtrip.py
# --- FROM test_project_fits_roundtrip.py ---
import json

import numpy as np
import pytest

pytest.importorskip("chinet")

from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.fitting.parameter import FittingParameter
from chisurf.core.models.model import ModelCurve
from chisurf.core.project import (
    Project,
    ProjectArchive,
    capture_session,
    load_project,
    restore_session,
    save_project,
)


class DummyLinearModel(ModelCurve):
    """Small concrete model used for Project.fits round-trip tests.

    Uses two fitting parameters ``p0`` and ``p1`` to describe
    ``y = p0 + p1 * x``. This mirrors the setup in ``test_fit_state``
    without depending on any GUI components.
    """

    name = "DummyLinearModelForProject"

    def __init__(self, fit: Fit, **kwargs):  # type: ignore[override]
        super().__init__(fit, **kwargs)
        self.p0 = FittingParameter(name="p0", value=0.5)
        self.p1 = FittingParameter(name="p1", value=1.5)
        self.find_parameters()

    def _update_model(self, **kwargs):  # type: ignore[override]
        x = self.fit.data.x
        if x is None:
            x = np.arange(self.fit.data.y.size, dtype=float)
        self.x = x
        self.y = float(self.p0.value) + float(self.p1.value) * x

    def update(self, **kwargs) -> None:  # type: ignore[override]
        super().update(**kwargs)


def _make_dummy_fit() -> Fit:
    x = np.arange(4, dtype=float)
    y = np.ones_like(x)
    data = DataCurve(x=x, y=y)
    return Fit(model_class=DummyLinearModel, data=data)


def test_project_fits_roundtrip_with_single_fit(tmp_path):
    fit = _make_dummy_fit()
    fit.unique_identifier = "fit-uid-1"
    fit.fit_range = (1, 3)
    params = fit.model.parameters_all_dict
    params["p0"].value = 2.0
    params["p0"].bounds = (0.0, 5.0)
    params["p0"].bounds_on = True

    params["p1"].value = -0.5
    params["p1"].fixed = True

    project = capture_session([fit.data], [fit], name="proj_with_fit")
    archive_path = save_project(project, tmp_path / "proj1")
    assert archive_path.is_file()

    # Inspect raw JSON to ensure fits structure is present
    archive = ProjectArchive.open(archive_path)
    raw = json.loads(archive.read_text("project.json"))
    archive.close()

    assert "fits" in raw
    assert len(raw["fits"]) == 1
    raw_fit = raw["fits"][0]
    assert raw_fit["uid"] == "fit-uid-1"
    assert raw_fit["members"][0]["dataset_uid"] == fit.data.unique_identifier
    assert raw_fit["members"][0]["fit_range"] == [1, 3]
    assert raw_fit["members"][0]["model"]["model_class"] == "DummyLinearModel"

    loaded_project = load_project(archive_path)
    assert isinstance(loaded_project, Project)
    assert len(loaded_project.fits) == 1

    restored = restore_session(loaded_project)
    assert len(restored.fits) == 1
    fit2 = restored.fits[0]
    params2 = fit2.model.parameters_all_dict

    # After applying the record, the parameter state should match
    assert np.isclose(params2["p0"].value, 2.0)
    assert params2["p0"].bounds_on is True
    assert np.allclose(params2["p0"].bounds, [0.0, 5.0])

    assert np.isclose(params2["p1"].value, -0.5)
    assert params2["p1"].fixed is True
    assert fit2.fit_range == (1, 3)


# --- FROM test_project_json_roundtrip.py ---


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
    assert archive_path.suffix == ".pto"

    # Sanity-check the raw JSON structure
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


# --- FROM test_project_v3.py ---
import os
import tempfile
import unittest


class TestProjectFormat(unittest.TestCase):
    def test_v5_format_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_v5_project")

            p = _representative_project("v5_test_project")
            second = DataCurve(
                x=np.array([0.0, 1.0, 2.0]), y=np.array([12.0, 8.0, 4.0]), unique_identifier="ds2"
            )
            second_project = capture_session([second], [])
            p.datasets.update(second_project.datasets)
            p.ui_state["dataset_layout"].extend(second_project.ui_state["dataset_layout"])
            p.metadata["checkpoint_interval"] = 50

            archive_path = save_project(p, project_dir)
            assert archive_path.is_file()

            archive = ProjectArchive.open(archive_path)
            raw = json.loads(archive.read_text("project.json"))
            archive.close()

            self.assertEqual(raw["project_format_version"], 5)
            self.assertIn("meta", raw)
            self.assertEqual(raw["meta"]["name"], "v5_test_project")
            self.assertIn("ds1", raw["datasets"])

            loaded = load_project(project_dir)
            self.assertEqual(loaded.project_format_version, 5)
            self.assertEqual(loaded.name, "v5_test_project")
            self.assertEqual(len(loaded.datasets), 2)
            self.assertEqual(len(loaded.fits), 1)
            self.assertEqual(loaded.fits[0]["uid"], "fit1")

    def test_v5_deterministic_ordering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_ordering")

            curves = [
                DataCurve(x=np.array([0.0, 1.0]), y=np.array([2.0, 1.0]), unique_identifier=uid)
                for uid in ("z_dataset", "a_dataset", "m_dataset")
            ]
            p = capture_session(curves, [], name="ordering_test")

            archive_path = save_project(p, project_dir)

            archive = ProjectArchive.open(archive_path)
            raw = json.loads(archive.read_text("project.json"))
            archive.close()

            dataset_keys = list(raw["datasets"].keys())
            self.assertEqual(dataset_keys, sorted(dataset_keys))

    def test_v5_outputs_canonical_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_v1")

            p = _representative_project("v5_project")

            archive_path = save_project(p, project_dir)

            archive = ProjectArchive.open(archive_path)
            raw = json.loads(archive.read_text("project.json"))
            archive.close()

            self.assertEqual(raw["project_format_version"], 5)
            self.assertIn("meta", raw)

            loaded = load_project(project_dir)
            self.assertEqual(loaded.project_format_version, 5)
            self.assertEqual(loaded.name, "v5_project")

    def test_get_dataset_by_uid(self):
        p = Project(name="test", project_format_version=5)
        p.datasets["uid1"] = {"name": "dataset1"}
        p.datasets["uid2"] = {"name": "dataset2"}

        self.assertEqual(p.get_dataset("uid1")["name"], "dataset1")
        self.assertIsNone(p.get_dataset("nonexistent"))

    def test_get_fit_by_uid(self):
        p = Project(name="test", project_format_version=5)
        p.fits.append({"uid": "fit1", "name": "Fit 1"})
        p.fits.append({"uid": "fit2", "name": "Fit 2"})

        self.assertEqual(p.get_fit("fit1")["name"], "Fit 1")
        self.assertIsNone(p.get_fit("nonexistent"))

    def test_list_uids(self):
        p = Project(name="test", project_format_version=5)
        p.datasets["z"] = {"uid": "z"}
        p.datasets["a"] = {"uid": "a"}
        p.datasets["m"] = {"uid": "m"}
        p.fits.append({"uid": "fit3"})
        p.fits.append({"uid": "fit1"})
        p.fits.append({"uid": "fit2"})

        self.assertEqual(p.list_dataset_uids(), ["a", "m", "z"])
        self.assertEqual(p.list_fit_uids(), ["fit1", "fit2", "fit3"])
