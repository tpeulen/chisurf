"""GUI-reachable PDA diagnostics: the consistency check and the light-path link.

Both had headless APIs and no way to reach them from a model editor. They are
model methods so a ``button_row`` in the view spec is the whole user interface --
which means the button and the scripted call are the same code path, and these
tests cover both.
"""

from __future__ import annotations

import json

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


PDA_MODELS = [
    "chisurf.core.models.pda.simple.PdaSimpleModel",
    "chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel",
    "chisurf.core.models.pda.dynamic.PdaDynamicTwoStateModel",
    "chisurf.core.models.pda.dynamic_mc.PdaDynamicNStateModel",
    "chisurf.core.models.pda.anisotropy.PdaAnisotropyModel",
]


def _fit(path):
    import importlib

    from test.gui.test_pda_model_editor import _make_pda_fit  # noqa: PLC0415

    module, _, name = path.rpartition(".")
    return _make_pda_fit(getattr(importlib.import_module(module), name))


@pytest.mark.parametrize("model_path", PDA_MODELS)
def test_every_pda_model_offers_both_diagnostics(qapp, model_path):
    model = _fit(model_path).model
    assert callable(model.run_consistency_check)
    assert callable(model.apply_light_path)
    # Before anything runs, the info boxes explain rather than mislead.
    assert "Not run" in model.consistency_html()
    assert "Not applied" in model.lightpath_html()


@pytest.mark.parametrize("model_path", PDA_MODELS)
def test_the_diagnostics_panel_is_wired_to_real_methods(qapp, model_path):
    """Every button action names a method that exists, and every info a property."""
    model = _fit(model_path).model
    spec = model.view_spec()
    panels = [s for s in spec.flat_sections()
              if getattr(s, "buttons", None) or getattr(s, "source", None)]
    actions = [b["action"] for s in panels for b in getattr(s, "buttons", ())]
    sources = [s.source for s in panels if getattr(s, "source", None)]
    assert "run_consistency_check" in actions
    assert "apply_light_path" in actions
    for name in actions + sources:
        assert hasattr(model, name), f"{model_path} view spec references {name!r}"


# --- the consistency check ----------------------------------------------------------


def test_the_check_runs_and_reports_a_p_value(qapp):
    model = _fit("chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel").model
    model.consistency_resamples = 30
    result = model.run_consistency_check()

    assert set(result) >= {"p_value", "consistent", "chi2_measured", "hist_measured"}
    assert 0.0 < result["p_value"] <= 1.0
    assert "p = " in model.consistency_html()
    assert ("consistent" in model.consistency_html())


def test_data_the_model_did_not_generate_is_reported_inconsistent(qapp):
    """The check has to be able to say no, or it is not a check."""
    import chisurf.core.fluorescence.tcspc as tcspc

    fit = _fit("chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel")
    model = fit.model
    model.consistency_resamples = 30

    # Data from one distance, model left at a very different one.
    model.distances._means[0].value = 40.0
    model.update()
    s1s2 = np.asarray(model.pda.get_S1S2_matrix(), dtype=float)
    ny, nx = fit.data.pda["shape"]
    s1s2 = s1s2[:ny, :nx]
    s1s2 = s1s2 / max(s1s2.sum(), 1e-12) * 2e5
    fit.data.pda["s1s2"] = np.random.default_rng(1).poisson(s1s2).astype(float)
    fit.data.y = fit.data.pda["s1s2"].ravel(order="C")
    fit.data.ey = tcspc.counting_noise(fit.data.y)

    model.distances._means[0].value = 70.0          # nowhere near the data
    result = model.run_consistency_check()
    assert result["consistent"] is False
    assert "inconsistent" in model.consistency_html()


def test_the_plot_accessor_is_empty_until_the_check_has_run(qapp):
    from chisurf.core.models.pda.common import get_pda_consistency

    fit = _fit("chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel")
    assert get_pda_consistency(fit) == []

    fit.model.consistency_resamples = 20
    fit.model.run_consistency_check()
    curves = get_pda_consistency(fit)
    assert len(curves) == 2
    assert {c["label"] for c in curves} == {"measured", "expected (fitted scheme)"}
    assert all(np.all(np.isfinite(c["y"])) for c in curves)


def test_a_model_without_a_pda_engine_reports_instead_of_raising(qapp):
    """The button must not propagate an exception into the editor."""
    fit = _fit("chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel")
    fit.data.pda["s1s2"] = None
    assert fit.model.run_consistency_check() == {}
    assert "failed" in fit.model.consistency_html()


# --- the light-path link ------------------------------------------------------------


def test_a_missing_light_path_is_reported_not_raised(qapp, tmp_path):
    model = _fit("chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel").model
    model.lightpath_graph = str(tmp_path / "nope.json")
    assert model.apply_light_path() == {}
    assert "No light path found" in model.lightpath_html()


def test_an_unreadable_light_path_is_reported_not_raised(qapp, tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    model = _fit("chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel").model
    model.lightpath_graph = str(path)
    assert model.apply_light_path() == {}
    assert "failed" in model.lightpath_html()


def test_a_setup_that_is_not_two_by_two_is_refused_with_its_labels(qapp, tmp_path,
                                                                  monkeypatch):
    """Guessing the donor/acceptor pair would silently rescale every correction."""
    from chisurf.core.models.pda import common

    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({"nodes": [], "edges": []}))
    matrices = {
        "crosstalk_matrices": {
            "excitation": {"rows": ["488"],
                           "columns": ["D", "A", "A2"], "values": []},
            "emission": {"rows": ["D", "A", "A2"],
                         "columns": ["green", "red"], "values": []},
        }
    }
    monkeypatch.setattr(
        "chisurf.plugins.core.lightpath_simulator.core.workflow.simulate_lightpath",
        lambda payload: matrices,
    )
    model = _fit("chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel").model
    model.lightpath_graph = str(graph)
    assert model.apply_light_path() == {}
    assert "Ambiguous setup" in model.lightpath_html()
    assert "3 dyes" in model.lightpath_html()
    assert "A2" in model.lightpath_html()          # says which, so it can be fixed
    assert common is not None


def test_a_two_by_two_setup_is_applied_and_summarised(qapp, tmp_path, monkeypatch):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({"nodes": [], "edges": []}))
    matrices = {
        "crosstalk_matrices": {
            "excitation": {"rows": ["488", "640"],
                           "columns": ["Alexa488", "Alexa647"],
                           "values": [[1.0, 0.05], [0.0, 1.0]]},
            "emission": {"rows": ["Alexa488", "Alexa647"],
                         "columns": ["green", "red"],
                         "values": [[0.92, 0.08], [0.02, 0.98]]},
        }
    }
    monkeypatch.setattr(
        "chisurf.plugins.core.lightpath_simulator.core.workflow.simulate_lightpath",
        lambda payload: matrices,
    )
    model = _fit("chisurf.core.models.pda.pdagauss.PdaGaussianDistanceModel").model
    model.lightpath_graph = str(graph)
    result = model.apply_light_path()

    assert result is matrices
    # The crosstalk really landed on the nuisance group, and on the right terms:
    # cGA is the acceptor leaking into the green channel, cRD the donor into red.
    assert float(model.nuisance.cGD) == pytest.approx(0.92)
    assert float(model.nuisance.cRD) == pytest.approx(0.08)
    assert float(model.nuisance.cGA) == pytest.approx(0.02)
    assert float(model.nuisance.cRA) == pytest.approx(0.98)
    assert float(model.nuisance.ExDG) == pytest.approx(1.0)
    assert float(model.nuisance.ExAG) == pytest.approx(0.05)
    assert "Alexa488" in model.lightpath_html() and "green" in model.lightpath_html()
    assert "&gamma;" in model.lightpath_html()
