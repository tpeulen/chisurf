"""Nondefault scientific state, using explicitly simulated stopped-flow traces."""

import numpy as np
import pytest

from chisurf.core.data import DataCurve
from chisurf.core.experiments.core.experiment import Experiment
from chisurf.core.experiments.tcspc.reader import TCSPCReader
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.model import ModelCurve
from chisurf.core.models.stopped_flow.reaction import ReactionModel
from chisurf.core.project.session import SessionCodecError, capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file


class _DroppedControlModel(ModelCurve):
    """Deliberately lossy adapter used to verify the capture integrity boundary."""

    def __init__(self, fit, **kwargs):
        """Start with a nonnumeric editor control that leaves predictions unchanged."""
        super().__init__(fit, **kwargs)
        self.algorithm = "default"

    def get_state(self):
        """Declare the scientific control the broken setter drops."""
        return {"algorithm": self.algorithm}

    def set_state(self, state):
        """Deliberately drop state to test rejection without comparing only y."""

    def _update_model(self, **kwargs):
        """Produce the same curve for both controls."""
        self.y = np.ones_like(self.fit.data.x)


def test_capture_rejects_dropped_declared_state_even_with_identical_predictions():
    """An unchanged y is insufficient evidence for a complete scientific snapshot."""
    data = DataCurve(x=np.arange(6.0), y=np.ones(6), load_filename_on_init=False)
    fit = Fit(data=data, model_class=_DroppedControlModel)
    fit.model.algorithm = "edited"
    with pytest.raises(SessionCodecError, match="state changed"):
        capture_session([data], [fit])


def test_description_mixture_restores_forward_sources_by_exact_fit_identity(tmp_path):
    """Duplicate source names cannot replace the two actual model dependencies."""
    from test.fitting.test_description_model import _lifetime_view, _mixture_view

    fast_fit, fast = _lifetime_view([0.5], [1.0])
    slow_fit, slow = _lifetime_view([3.0], [1.0])
    fast_fit.name = slow_fit.name = "same source name"
    mix_fit, mixture = _mixture_view([fast, slow])
    for fit in (mix_fit, fast_fit, slow_fit):
        response = fit.model._sources["response"]
        fit.model.set_dataset(
            "response", DataCurve(x=response.x, y=response.y, load_filename_on_init=False)
        )
    mixture._fractions[1].value = 3.0
    # Put the consumer first: this requires forward model references, not a
    # by-name lookup or a restore-order coincidence.
    fits = [mix_fit, fast_fit, slow_fit]
    for iteration in range(2):
        for fit in fits:
            fit.model.update()
        expected = fits[0].model.y.copy()
        path = save_file(
            capture_session([f.data for f in fits], fits), tmp_path / f"mixture-{iteration}.cs.pto"
        )
        fits = restore_session(load_file(path)).fits
        actual = fits[0].model
        assert actual.source_models == [fits[1].model, fits[2].model]
        assert actual.model_names == ["species 0", "species 1"]
        np.testing.assert_allclose(actual.y, expected, rtol=1e-12, atol=1e-12)
        target = fits[2].model.problem.get_parameter("lifetime.tau.0")
        target.fixed = False
        target.value *= 1.2
        fits[2].model.update()
        actual.update()
        assert not np.allclose(actual.y, expected)


@pytest.mark.parametrize("invalid", ["dangling", "cycle", "malformed"])
def test_model_input_graph_rejects_invalid_descriptors_before_fit_construction(
    monkeypatch, invalid
):
    """Graph validation fails before any scientific constructor receives state."""
    from test.project.test_session_codec import _TwoParameterModel

    data = DataCurve(x=np.arange(6.0), y=np.ones(6), load_filename_on_init=False)
    fits = [Fit(data=data, model_class=_TwoParameterModel) for _ in range(2)]
    project = capture_session([data], fits)
    states = [r["members"][0]["model"] for r in project.fits]
    refs = [{"fit_uid": r["uid"], "member_uid": r["members"][0]["uid"]} for r in project.fits]
    if invalid == "dangling":
        states[0]["model_dependencies"] = {"sources": [{**refs[1], "fit_uid": "missing"}]}
    elif invalid == "cycle":
        states[0]["model_dependencies"] = {"sources": [refs[1]]}
        states[1]["model_dependencies"] = {"sources": [refs[0]]}
    else:
        states[0]["model_dependencies"] = {"sources": ["by-name"]}

    def forbidden(*args, **kwargs):
        """Any attempted construction means preflight validation did not work."""
        raise AssertionError("fit constructed before descriptor rejection")

    monkeypatch.setattr(Fit, "__init__", forbidden)
    with pytest.raises(SessionCodecError, match="model (input|dependency)"):
        restore_session(project)


@pytest.mark.parametrize(
    "model_name,structure",
    [
        ("ImageCorrelationModel", "Image correlation (2D membrane)"),
        ("IcsGaussian2DModel", "2D Gaussian (2 sigma + angle)"),
    ],
)
def test_ics_catalogue_modes_restore_without_process_registry(tmp_path, model_name, structure):
    """Both configured ICS modes keep their identity on a legitimate 3D carpet."""
    from chisurf.core.models.ics import ics
    from chisurf.core.project import session
    from test.gui.test_ics_model_editor import _make_ics_data

    # This source fixture uses image_correlation, not a measurement. Its axes
    # and three frame lags are exactly the flattened layout emitted by ICSReader.
    data = _make_ics_data(n_lags=3)
    experiment = Experiment(name="Image correlation")
    for cls in (ics.ImageCorrelationModel, ics.IcsGaussian2DModel):
        experiment.add_model_class(cls)
    data.experiment = experiment
    cls = getattr(ics, model_name)
    fit = Fit(data=data, model_class=cls, xmin=0, xmax=len(data.y))
    fit.model.structure = structure
    fit.model.update()
    expected = fit.model.y.copy()
    path = save_file(capture_session([data], [fit]), tmp_path / f"{model_name}.cs.pto")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(session, "_MODEL_REGISTRY", {})
        restored = restore_session(load_file(path))
    assert type(restored.fits[0].model) is cls
    assert restored.fits[0].model.structure == structure
    np.testing.assert_allclose(restored.fits[0].model.y, expected, rtol=1e-12, atol=1e-12)


def test_scientific_carpet_metadata_keeps_dtype_shape_and_tuple_axes(tmp_path):
    """Reader metadata must remain scientific arrays rather than JSON lists."""
    data = DataCurve(x=np.arange(6.0), y=np.ones(6), load_filename_on_init=False)
    data.meta_data["grid"] = {"shape": (2, 3), "ndim": 2}
    data.meta_data["ics"] = {
        "correlation": np.arange(6, dtype=np.float32).reshape(2, 3),
        "frame_lags": np.array([0, 2], dtype=np.int16),
        "pixel_size_nm": np.float32(47.5),
    }
    path = save_file(capture_session([data], []), tmp_path / "carpet.cs.pto")
    actual = restore_session(load_file(path)).datasets[0]
    assert actual.meta_data["grid"]["shape"] == (2, 3)
    for key in ("correlation", "frame_lags"):
        assert actual.meta_data["ics"][key].dtype == data.meta_data["ics"][key].dtype
        np.testing.assert_array_equal(actual.meta_data["ics"][key], data.meta_data["ics"][key])
    assert type(actual.meta_data["ics"]["pixel_size_nm"]) is np.float32


def test_pda_reader_auxiliary_payload_is_preserved(tmp_path):
    """PDA fits need the S1S2 count matrix in addition to the plotted curve."""
    data = DataCurve(x=np.arange(8.0), y=np.ones(8), load_filename_on_init=False)
    data.pda = {
        "s1s2": np.arange(16, dtype=np.uint32).reshape(4, 4),
        "ps": np.array([0.0, 0.1, 0.2, 0.7]),
        "minimum_number_of_photons": 2,
    }
    path = save_file(capture_session([data], []), tmp_path / "pda.cs.pto")
    actual = restore_session(load_file(path)).datasets[0]
    assert actual.pda["s1s2"].dtype == np.uint32
    np.testing.assert_array_equal(actual.pda["s1s2"], data.pda["s1s2"])
    np.testing.assert_array_equal(actual.pda["ps"], data.pda["ps"])


def test_fcs_kinetic_four_state_scheme_and_units_survive_file_restore(tmp_path):
    """Persist an active, edited photokinetic scheme rather than its defaults."""
    from chisurf.core.models.fcs.kinetics import FCSKineticsModel
    from test.fitting.test_graph_fit_fcs_kinetics import _arm_saturation, make_fit

    fit = make_fit(n=24, meta={"mean_count_rate_total": 35.2})
    model = fit.model
    model.saturation.n_states = 4
    _arm_saturation(model)
    model.saturation.dark_unit = "1/ms"
    model.saturation._custom_state_labels = ["a", "b", "c", "d"]
    model.saturation._custom_state_names = ["ground", "excited", "dark", "isomer"]
    model.saturation._dye_name = "recorded custom dye"
    model.saturation.dark.rates_by_name()["k4_1"].value = 0.4
    model.saturation.dark.rates_by_name()["k1_4"].value = 0.1
    model.saturation_mode = "fast"
    for iteration in range(2):
        expected = model.y.copy()
        uids = [(p.unique_identifier, p._port.get_uid()) for p in model.parameters_all]
        path = save_file(
            capture_session([fit.data], [fit]), tmp_path / f"kinetics-{iteration}.cs.pto"
        )
        fit = restore_session(load_file(path)).fits[0]
        model = fit.model
        assert type(model) is FCSKineticsModel
        assert model.saturation_mode == "fast"
        assert model.saturation.n_states == 4
        assert model.saturation.dark_unit == "1/ms"
        assert model.saturation.state_labels == ["a", "b", "c", "d"]
        assert model.saturation._dye_name == "recorded custom dye"
        assert [(p.unique_identifier, p._port.get_uid()) for p in model.parameters_all] == uids
        np.testing.assert_allclose(model.y, expected, rtol=1e-12, atol=1e-12)
        model.saturation._N.value *= 1.2
        model.update()
        assert not np.allclose(model.y, expected)


@pytest.mark.parametrize("class_name", ["MaxEntFCSModel", "MaxEntRHModel"])
def test_fcs_maxent_nonuniform_prior_survives_two_file_loops(tmp_path, class_name):
    """Use a deterministic analytical correlation, with an edited inversion prior."""
    from chisurf.core.models.fcs import maxent_models

    tau = np.logspace(-3, 1, 24)
    y = 1 + 1 / ((1 + tau / 0.05) * np.sqrt(1 + tau / (0.05 * 3.5**2)))
    data = DataCurve(x=tau, y=y, ey=np.full_like(tau, 0.01), load_filename_on_init=False)
    fit = Fit(data=data, model_class=getattr(maxent_models, class_name), xmin=0, xmax=len(tau))
    fit.model.prior_kind = "lognormal"
    fit.model._prior_width.value = 0.2
    for iteration in range(2):
        fit.model.update()
        expected = fit.model.y.copy()
        path = save_file(
            capture_session([fit.data], [fit]), tmp_path / f"{class_name}-{iteration}.cs.pto"
        )
        fit = restore_session(load_file(path)).fits[0]
        assert fit.model.prior_kind == "lognormal"
        np.testing.assert_allclose(fit.model.y, expected, rtol=1e-12, atol=1e-12)
        fit.model._prior_width.value *= 1.2


def test_dynamic_pda_multistate_configuration_survives_file_restore(tmp_path):
    """A deterministic S1S2 matrix keeps an edited, fixed-seed four-state MC model."""
    from chisurf.core.models.pda2c.dynamic_mc import Pda2cDynamicNStateModel
    from test.gui.test_pda2c_model_editor import _make_pda_data

    data = _make_pda_data(nmax=24, nmin=5)
    fit = Fit(data=data, model_class=Pda2cDynamicNStateModel, xmin=0, xmax=len(data.y))
    model = fit.model
    model.n_states = 4
    model.method = "monte-carlo"
    model.seed = 47
    model.n_hist = 21
    model.states._n_windows.value = 120
    model.fit_settings.statistic = "pearson"
    model.fit_settings.n_bins = 31
    model.residual_mode = "2D"
    for iteration in range(2):
        model.update()
        expected = model.y.copy()
        path = save_file(
            capture_session([fit.data], [fit]), tmp_path / f"dynamic-{iteration}.cs.pto"
        )
        fit = restore_session(load_file(path)).fits[0]
        model = fit.model
        assert model.n_states == 4
        assert (model.method, model.seed, model.n_hist) == ("monte-carlo", 47, 21)
        assert model.fit_settings.statistic == "pearson"
        assert model.fit_settings.n_bins == 31
        assert model.residual_mode == "2D"
        np.testing.assert_allclose(model.y, expected, rtol=1e-12, atol=1e-12)
        model.states._R[0].value += 2


def test_pda3c_simulator_table_and_species_controls_survive_file_restore(tmp_path):
    """The reader's fixed-seed simulated burst table and species topology survive."""
    from chisurf.core.experiments.pda3c.reader import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.pda3c import Pda3cModel

    reader = Pda3cSimulatorReader(
        n_bursts=24, seed=47, record_provenance=False, experiment=Experiment(name="PDA")
    )
    data = reader.get_data()[0]
    fit = Fit(data=data, model_class=Pda3cModel, xmin=0, xmax=len(data.y))
    model = fit.model
    model.species.append()
    model.n_nodes = 3
    model.truncate = 1e-4
    model.stochastic_labeling = True
    model.brightness_correction = True
    model.dynamic_seed = 47
    model.dynamic_samples = 80
    model.dynamic_resolution = 12
    model.dynamic_max_nodes = 60
    model.find_parameters()
    model.update()
    expected = model.y.copy()
    path = save_file(capture_session([data], [fit]), tmp_path / "pda3c.cs.pto")
    restored = restore_session(load_file(path))
    actual = restored.fits[0].model
    assert len(actual.species) == 2
    for field in (
        "n_nodes",
        "truncate",
        "stochastic_labeling",
        "brightness_correction",
        "dynamic_seed",
        "dynamic_samples",
        "dynamic_resolution",
        "dynamic_max_nodes",
    ):
        assert getattr(actual, field) == getattr(model, field)
    assert restored.datasets[0].pda3c["blue"].dtype == data.pda3c["blue"].dtype
    np.testing.assert_array_equal(restored.datasets[0].pda3c["blue"], data.pda3c["blue"])
    np.testing.assert_allclose(actual.y, expected, rtol=1e-12, atol=1e-12)


def test_reaction_network_survives_two_file_loops_and_edits(tmp_path):
    """An edited three-species simulation retains topology, UIDs and predictions."""
    experiment = Experiment(name="Stopped flow")
    experiment.add_model_class(ReactionModel)
    reader = TCSPCReader(experiment=experiment, name="deterministic trace")
    x = np.linspace(0, 4, 65)
    data = DataCurve(
        x=x,
        y=np.ones_like(x),
        ey=np.ones_like(x),
        experiment=experiment,
        data_reader=reader,
        name="simulated sequential reaction",
        load_filename_on_init=False,
    )
    fit = Fit(data=data, model_class=ReactionModel, xmin=0, xmax=len(x))
    fit.model.set_scheme(
        {
            "species": [
                {"species": "substrate", "concentration": 2.0, "brightness": 1.2},
                {"species": "intermediate", "concentration": 0.2, "brightness": 3.0},
                {"species": "product", "concentration": 0.0, "brightness": 0.1},
            ],
            "reactions": [
                {
                    "educts": [0],
                    "products": [1],
                    "educt_stoichiometry": [1],
                    "product_stoichometry": [1],
                    "rate": 1.3,
                },
                {
                    "educts": [1],
                    "products": [2],
                    "educt_stoichiometry": [1],
                    "product_stoichometry": [1],
                    "rate": 0.7,
                },
            ],
        }
    )
    fit.model.autoscale = True
    fit.model.selected_reaction = fit.model.reaction_rows()[1]
    fit.model.find_parameters()
    fit.model.rates[0].error_estimate = 0.13
    fit.model.rates[0].bounds = (0, float("inf"))
    fit.model.rates[0].bounds_on = False
    fit.model.update()
    for iteration in range(2):
        expected = fit.model.y.copy()
        scheme = fit.model.scheme
        parameter_uids = [p.unique_identifier for p in fit.model.parameters_all]
        path = save_file(capture_session([data], [fit]), tmp_path / f"reaction-{iteration}.cs.pto")
        restored = restore_session(load_file(path))
        fit, data = restored.fits[0], restored.datasets[0]
        assert type(fit.model) is ReactionModel
        assert fit.model.scheme == scheme
        assert fit.model.autoscale is True
        assert fit.model.selected_reaction["index"] == 1
        assert [p.unique_identifier for p in fit.model.parameters_all] == parameter_uids
        assert fit.model.rates[0].error_estimate == 0.13
        assert (fit.model.rates[0].lb, fit.model.rates[0].ub) == (0, float("inf"))
        assert fit.model.rates[0].bounds_on is False
        np.testing.assert_allclose(fit.model.y, expected, rtol=1e-12, atol=1e-12)
        fit.model.rates[0].value *= 1.2
        fit.model.update()
        assert not np.allclose(expected, fit.model.y)
