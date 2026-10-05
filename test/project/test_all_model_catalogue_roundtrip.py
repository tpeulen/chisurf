"""Configured scientific catalogue, with measured or labelled simulated inputs.

The complete matrix deliberately exposes unsupported scientific paths as failures.
Passing class resolution is recorded separately from scientific file roundtrips.
"""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import yaml

from chisurf.core.data import DataCurve
from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.fitting.fit import Fit
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file

HERE = Path(__file__).parent
CATALOGUE = json.loads((HERE / "fixtures/scientific_model_catalogue.json").read_text())
IDS = [entry["configured_path"] for entry in CATALOGUE]


def _resolve(path):
    """Resolve an independently checked-in shipped catalogue path."""
    module, name = path.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)


def test_shipped_catalogue_has_exactly_the_independent_42_entries():
    """New configured entries cannot silently fall outside the scientific matrix."""
    config = yaml.safe_load(Path("chisurf/core/settings/experiment_configs.yaml").read_text())
    configured = [
        (family, path)
        for family, settings in config.items()
        if isinstance(settings, dict)
        for path in settings.get("models", [])
    ]
    assert configured == [(entry["experiment"], entry["configured_path"]) for entry in CATALOGUE]
    assert len(configured) == 42


@pytest.mark.parametrize("entry", CATALOGUE, ids=IDS)
def test_catalogue_resolves_actual_class(entry):
    """Report configuration resolution separately from the scientific acceptance."""
    cls = _resolve(entry["configured_path"])
    assert f"{cls.__module__}.{cls.__name__}" == entry["identity"]


def _data(entry, cls):
    """Return a legitimate reader output or a labelled deterministic simulation."""
    family = entry["experiment"]
    experiment = Experiment(name=family)
    experiment.add_model_class(cls)
    if family == "tcspc":
        from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup

        reader = TCSPCSimulatorSetup(
            experiment=experiment,
            n_tac=128,
            dt=0.1,
            lifetime_spectrum=[1.0, 3.5],
            add_noise=False,
            seed=47,
            record_provenance=False,
        )
        return reader.get_data()[0]
    if family == "fcs":
        from chisurf.core.experiments.fcs.reader import FCS

        reader = FCS(experiment=experiment, experiment_reader="kristine", record_provenance=False)
        return reader.get_data(filename="test/data/fcs/kristine/Kristine_with_error.cor")[0]
    if family == "deer":
        from chisurf.core.experiments.deer.reader import DeerReader

        reader = DeerReader(experiment=experiment, record_provenance=False)
        return reader.get_data(filename="test/data/deer/deer_twostate.DSC")[0]
    if family == "ics":
        from chisurf.core.experiments.ics import ICSReader
        from test.gui.test_ics_model_editor import _make_ics_data

        data = _make_ics_data(n_lags=3)
        data.data_reader = ICSReader(experiment=experiment, record_provenance=False)
    elif family == "pda" and cls.__name__ == "Pda3cModel":
        from chisurf.core.experiments.pda3c.reader import Pda3cSimulatorReader

        reader = Pda3cSimulatorReader(
            experiment=experiment, n_bursts=24, seed=47, record_provenance=False
        )
        data = reader.get_data()[0]
    elif family == "pda":
        from chisurf.core.experiments.pda2c.reader import Pda2cReader
        from test.gui.test_pda2c_model_editor import _make_pda_data

        data = _make_pda_data(nmax=24, nmin=5)
        data.meta_data["grid"] = {
            "ndim": 2,
            "shape": data.pda["shape"],
            "size": len(data.y),
            "order": "C",
        }
        data.data_reader = Pda2cReader(
            experiment=experiment,
            record_provenance=False,
            channels=[[0], [1]],
            micro_time_ranges=[[0, 16000]] * 2,
        )
    elif family == "mfd":
        from chisurf.core.experiments.mfd.reader import MfdReader

        reader = MfdReader(
            experiment=experiment, n_ratio_bins=12, n_micro_time_bins=12, record_provenance=False
        )
        # Bundled measured bursts, as used by the shipped MFD scientific suite.
        folder = (
            "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/"
            "burstwise_All 0.1000#15"
        )
        data = reader.get_data(filename=folder)[0]
    elif family == "structure":
        from chisurf.core.experiments.modelling.reader import StructureReader

        reader = StructureReader(experiment=experiment, record_provenance=False)
        data = reader.get_data(filename="test/data/atomic_coordinates/pdb_files/148l.pdb")[0]
        data.data_reader = reader
    elif family == "global":
        from chisurf.core.experiments.globalfit.reader import GlobalFitSetup

        reader = GlobalFitSetup(experiment=experiment)
        data = reader.read()
        data.data_reader = reader
    elif family == "pch":
        from chisurf.core.experiments.pch.reader import PCHReader
        from chisurf.core.models.pch.fida import fida_pch

        y = 10000 * fida_pch(30, [(2.0, 1.5), (4.0, 0.5)])
        data = DataCurve(
            x=np.arange(len(y)),
            y=y,
            ey=np.sqrt(np.maximum(y, 1)),
            name="deterministic FIDA count distribution",
            load_filename_on_init=False,
        )
        data.data_reader = PCHReader(experiment=experiment, record_provenance=False)
    elif family == "pcf":
        from chisurf.core.experiments.fcs.reader import FCS

        x = np.linspace(0.05, 4, 65)
        data = DataCurve(
            x=x,
            y=np.exp(-x),
            ey=np.ones_like(x),
            name="deterministic simulated transit",
            load_filename_on_init=False,
        )
        data.data_reader = FCS(
            experiment=experiment, experiment_reader="csv", name="PCF-CSV", record_provenance=False
        )
    else:
        from chisurf.core.experiments.tcspc.reader import TCSPCReader

        x = np.linspace(0.05, 4, 65)
        data = DataCurve(
            x=x,
            y=np.exp(-x),
            ey=np.ones_like(x),
            name="deterministic simulated relaxation/transit",
            load_filename_on_init=False,
        )
        data.data_reader = TCSPCReader(experiment=experiment, record_provenance=False)
    data.experiment = experiment
    return data


def _edit_topology(model):
    """Edit family-specific scientific controls, without altering formulas."""
    if hasattr(model, "structure_options") and type(model).__name__ != "FRETStructure":
        options = model.structure_options()
        if len(options) > 1:
            model.structure = options[1][0]
    if type(model).__name__ == "ReactionModel":
        model.add_reaction_row()
        model.autoscale = True
    if type(model).__name__ == "GeneralFCSModel":
        model.diffusion_mode = "species"
        model.species.append()
    if type(model).__name__ in {"FCSKineticsModel", "MaxEntFCSModel", "MaxEntRHModel"}:
        from test.project.test_fcs_snapshot_science_edits import configure_fcs_science

        configure_fcs_science(model)
    if hasattr(model, "prior_kind"):
        model.prior_kind = "lognormal"
    if hasattr(model, "background") and hasattr(model.background, "model"):
        model.background.model = "strexp"
    if hasattr(model, "regularization"):
        model.regularization.method = "lcurve"
    if type(model).__name__ in {"DescriptionModel_tcspc_fret_gaussian", "DeerGaussianModel"}:
        model.gaussians.append(mean=48, sigma=4, amplitude=0.4)
    if type(model).__name__ == "Pda2cGaussianDistanceModel":
        model.distances.append(mean=48, sigma=4, amplitude=0.4)
    if type(model).__name__ == "DeerRiceModel":
        model.rice._nu.value = 48.0
        model.rice._sigma.value = 4.0
    if hasattr(model, "fit_settings"):
        model.fit_settings.statistic = "pearson"
        model.fit_settings.n_bins = 31
        model.residual_mode = "2D"
    if type(model).__name__ == "Pda2cDynamicNStateModel":
        model.n_states = 4
        model.seed = 47
        model.method = "monte-carlo"
        model.n_hist = 21
        model.states._n_windows.value = 120
    if type(model).__name__ == "Pda2cDynamicTwoStateModel":
        model.n_grid = 27
    if type(model).__name__ == "Pda3cModel":
        model.species.append()
        model.n_nodes = 3
        model.brightness_correction = True
        model.dynamic_seed = 47
    if type(model).__name__ == "Mfd2DModel":
        model.n_states = 3
    if type(model).__name__ == "PchMultiComponentModel":
        model.add_component()
        model._eps[1].value = 4.0
        model._n[1].value = 0.6
    if type(model).__name__ == "FidaModel":
        model._q[1].value = 4.0
        model._n[1].value = 0.6
    model.find_parameters()


@pytest.mark.parametrize("entry", CATALOGUE, ids=IDS)
def test_all_configured_scientific_file_roundtrip(tmp_path, entry):
    """Compute, save, fresh-load, edit and repeat for each configured model entry."""
    # A native solver timeout must produce one failure, then allow the other
    # scientific entries to execute. Native resources also get process lifetime.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "test.project.scientific_catalogue_probe",
            "--case",
            str(CATALOGUE.index(entry)),
            str(tmp_path),
        ],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _file_roundtrip(tmp_path, entry):
    """Run a single scientific entry with deterministic, self-contained inputs."""
    cls = _resolve(entry["configured_path"])
    from test.project.scientific_catalogue_probe import original_sources, scientific_observables

    data = _data(entry, cls)
    deferred = entry["configured_path"].endswith(
        ("tcspc_maxent_lifetime", "tcspc_maxent_fret", "DeerMaxEntModel")
    )
    fit = Fit(
        data=data, model_class=type if deferred else cls, xmin=0, xmax=len(getattr(data, "y", []))
    )
    fits = [fit]
    source_files = []
    if deferred:
        from test.project.test_maxent_snapshot_contracts import _deer_fit, _description_fit

        configured = (
            _deer_fit() if cls.__name__ == "DeerMaxEntModel" else _description_fit(cls.family)
        )
        configured.data.experiment = data.experiment
        configured.data.data_reader.experiment = data.experiment
        fit = configured
        fits = [fit]
    if entry["configured_path"].endswith("tcspc_mixture"):
        from test.fitting.test_description_model import _lifetime_view, _mixture_view

        first, first_model = _lifetime_view([0.5], [1.0])
        second, second_model = _lifetime_view([3.0], [1.0])
        first.name = second.name = "duplicate-named source"
        fit, _ = _mixture_view([first_model, second_model])
        fits = [fit, first, second]
        for source_fit in fits:
            response = source_fit.model._sources["response"]
            source_fit.model.set_dataset(
                "response", DataCurve(x=response.x, y=response.y, load_filename_on_init=False)
            )
        fit.model._fractions[1].value = 3.0
    if cls.__name__ == "GlobalFitModel":
        from test.project.test_global_snapshot_contracts import _global

        fit, sources = _global()
        fits = [fit, *sources]
    if cls.__name__ == "ParameterTransformModel":
        from chisurf.core.models.pda2c.simple import Pda2cSimpleModel
        from test.project.test_transform_snapshot_contracts import _transform

        fit = _transform()
        consumer_entry = next(
            e for e in CATALOGUE if e["configured_path"].endswith("Pda2cSimpleModel")
        )
        consumer = Fit(data=_data(consumer_entry, Pda2cSimpleModel), model_class=Pda2cSimpleModel)
        consumer.model.pch0._pch0[0].link = fit.model.parameters_all_dict["p0"]
        fits = [fit, consumer]
    if cls.__name__ == "ProteinMCModel":
        from test.project.test_structure_snapshot_contracts import _configured_proteinmc

        model, pdb, labeling = _configured_proteinmc(tmp_path)
        fit = Fit(data=model.fit.data)
        fit.data.data_reader = data.data_reader
        fit.data.experiment = data.experiment
        fit._model = model
        model.fit = fit
        fits = [fit]
        source_files = [pdb, labeling]
    if cls.__name__ == "FRETStructure":
        resource = tmp_path / "148l.pdb"
        resource.write_bytes(Path("test/data/atomic_coordinates/pdb_files/148l.pdb").read_bytes())
        fit.model.res_1, fit.model.res_2 = 47, 86
        fit.model.load_structures([str(resource)])
        assert fit.model.names and fit.model.structure_files, (
            "actual structure load was silently ignored"
        )
        assert np.sum(fit.model.source_models[0]) > 0, "empty structural distance distribution"
    _edit_topology(fit.model)
    parameters = [p for p in fit.model.parameters_all if not p.is_output and p.link is None]
    if parameters:
        parameters[0].error_estimate = 0.125
        parameters[0].bounds = (float("-inf"), float(parameters[0].value) + 10.0)
        parameters[0].bounds_on = False
    if len(getattr(fit.data, "y", [])) > 2:
        fit.fit_range = (fit.xmin if deferred else 1, len(fit.data.y) - 1)
        mask = fit.mask.copy()
        mask[::13] = 0
        fit.mask = mask
    for iteration in range(2):
        for member in fits:
            member.model.update()
        predictions = [
            np.array(member.model.y, copy=True).tolist() if hasattr(member.model, "y") else None
            for member in fits
        ]
        observables = [scientific_observables(member) for member in fits]
        for member, observable in zip(fits, observables):
            if type(member.model).__name__ == "ParameterTransformModel":
                assert all(
                    np.isfinite(value) and value > 0
                    for value in observable["native_outputs"].values()
                )
            elif type(member.model).__name__ == "ProteinMCModel":
                assert observable["distances"]
                assert all(
                    np.isfinite(value) and value > 0 for value in observable["distances"].values()
                )
            else:
                prediction = np.asarray(observable["prediction"])
                assert np.isfinite(prediction).all() and np.any(prediction > 0), entry[
                    "configured_path"
                ]
        project = capture_session([member.data for member in fits], fits)
        path = save_file(project, tmp_path / f"science-{iteration}.cs.pto")
        if cls.__name__ == "FRETStructure" and resource.exists():
            resource.unlink()
        for source_file in source_files:
            if source_file.exists():
                source_file.unlink()
        expected = tmp_path / f"expected-{iteration}.json"
        expected.write_text(
            json.dumps(
                {
                    "predictions": predictions,
                    "observables": observables,
                    "source_paths": sorted(original_sources(project)),
                }
            )
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "test.project.scientific_catalogue_probe",
                str(path),
                str(expected),
            ],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        restored = restore_session(load_file(path))
        fits = restored.fits
        fit = fits[0]
        assert type(fit.model) is cls
        assert capture_session(restored.datasets, restored.fits).fits == project.fits
        # A scientific edit is followed by recomputation before the second save.
        before_edit = [scientific_observables(member) for member in fits]
        if cls.__name__ in {"FCSKineticsModel", "MaxEntFCSModel", "MaxEntRHModel"}:
            from test.project.test_fcs_snapshot_science_edits import edit_fcs_science

            edit_fcs_science(fit.model)
            fit.model.update()
        elif cls.__name__ == "ProteinMCModel":
            coordinates = fit.model.structure.xyz.copy()
            atoms = fit.model.structure.atoms
            selected = (atoms["res_id"] == 86) & (atoms["atom_name"] == "CA")
            coordinates[selected, 0] += 0.1
            fit.model.structure.xyz = coordinates
            fit.model.update()
        else:
            parameters = (
                fit.model.global_parameters_all
                if cls.__name__ == "GlobalFitModel"
                else [p for p in fit.model.parameters if not p.is_output and p.link is None]
            )
            assert parameters, (
                f"no configured editable scientific input: {entry['configured_path']}"
            )
            changed = False
            for parameter in parameters:
                old_value = float(parameter.value)
                parameter.value = old_value * 1.01 + 0.001
                for member in fits:
                    member.model.update()
                changed = [scientific_observables(member) for member in fits] != before_edit
                if changed:
                    break
                parameter.value = old_value
            assert changed, f"no input edit reached a scientific output: {entry['configured_path']}"
        assert [scientific_observables(member) for member in fits] != before_edit
