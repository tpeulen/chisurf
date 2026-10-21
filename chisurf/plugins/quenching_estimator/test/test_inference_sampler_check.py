"""The optional MCMC check of the Laplace error bars (prototype cell 40).

The prototype's ``sampler_check`` (male_quenching_analysis.ipynb, defined in cell 36, run in
cell 49 behind ``RUN_SAMPLER_CHECK``) explores one data set's posterior with an affine-invariant
stretch-move ensemble sampler -- slopes and model error held at the best fit, Gaussian
likelihood on the inliers, stickiness ridge prior -- and compares the 68 % intervals with the
Laplace approximation's. Here the same check runs on the analytic stand-in site model, where
the posterior is close to Gaussian and the two methods must agree: a 1-block graph fitted in
seconds, sampled with a small ensemble. The declared setting
(``settings/analysis/fit_parameters.yaml: sampler_check``) is off by default.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.inference import graph_fit as gf
from chisurf.plugins.quenching_estimator.core.inference import sampler_check as sc
from chisurf.plugins.quenching_estimator.core.inference import stages as st

from .test_inference_graph_fit import FakeLibrary, _block

#: A small ensemble: enough for the near-Gaussian stand-in posterior, seconds of work.
CHECK = dict(steps=300, runs=2, walkers=32)
#: The API-level fit overrides that make a stage run take seconds.
TINY_FIT = dict(n_starts=2, search_maxiter=4, joint_max_nfev=2)


@pytest.fixture(scope="module")
def data():
    return st.load_analysis_data(library=FakeLibrary())


@pytest.fixture(scope="module")
def fit_settings():
    return gf.settings("quick", dict(n_starts=8, search_maxiter=200, joint_max_nfev=200))


@pytest.fixture(scope="module")
def view(data, fit_settings):
    block = gf.search(_block(data, fit_settings), 7, fit_settings, workers=1)
    graph = gf.Graph([block], fit_settings)
    gf.joint_fit(graph, workers=1)
    return gf.block_views(graph, "synthetic")[0]


# --------------------------------------------------------------------------------------------
# the comparison itself


def test_sampler_and_laplace_agree_on_a_near_gaussian_posterior(view):
    result = sc.sampler_check(view, **CHECK)
    assert result["block"] == view.label and result["dye"] == view.dye
    assert result["n_samples"] == CHECK["runs"] * CHECK["walkers"] * (CHECK["steps"] // 2)
    assert 0.0 < result["acceptance"] <= 1.0
    rows = {r["parameter"]: r for r in result["parameters"]}
    # the well-determined, strictly interior parameters: both methods must see the same
    # 68 % interval (dtau_shield rides its declared upper bound here, so the check rightly
    # calls it a mismatch -- see test_a_boundary_parameter_is_called_a_mismatch)
    for label, log in (("scale", True), ("delta", False), ("s_basic", True),
                       ("s_common", True)):
        r = rows[label]
        assert r["verdict"] == "agree", (label, r)
        assert r["overlap"] >= 0.5, (label, r)
        bend = np.log if log else (lambda v: v)
        lap = bend([r["laplace_low_68"], r["laplace_high_68"]])
        sam = bend([r["sampler_low_68"], r["sampler_high_68"]])
        assert 0.5 < (sam[1] - sam[0]) / (lap[1] - lap[0]) < 2.0, (label, r)
        assert r["laplace_low_68"] < r["best_fit"] < r["laplace_high_68"]
    assert result["mismatches"] == ["dtau_shield"]      # the one boundary parameter
    assert result["verdict"] == "mismatch: dtau_shield"


def test_a_boundary_parameter_is_called_a_mismatch(view):
    """A parameter at the edge of its range is no smooth valley: the check says so."""
    result = sc.sampler_check(view, **CHECK)
    r = {row["parameter"]: row for row in result["parameters"]}["dtau_shield"]
    assert view.estimate("dtau_shield")["high"] == pytest.approx(2.0)   # the declared bound
    assert r["verdict"] == "mismatch" and r["overlap"] < sc.AGREE_ABOVE
    assert result["verdict"] == "mismatch: dtau_shield"


def test_every_free_block_parameter_is_compared(view):
    result = sc.sampler_check(view, **CHECK)
    rows = {r["parameter"] for r in result["parameters"]}
    block = view.block
    expected = {gf._spec_map(view.graph.settings)[n].label
                for n in block.free if n != "ln_model_error"}
    assert rows == expected
    assert "model_error" not in rows          # held at the best fit, like the prototype's
    assert "lam" not in rows                  # fixed for Cy3B, not a fit parameter there


def test_the_laplace_columns_are_the_view_estimates(view):
    result = sc.sampler_check(view, **CHECK)
    for r in result["parameters"]:
        e = view.estimate(r["parameter"])
        assert r["best_fit"] == e["value"]
        assert r["laplace_low_68"] == e["low"] and r["laplace_high_68"] == e["high"]


def test_the_check_is_reproducible(view):
    first = sc.sampler_check(view, **CHECK)
    second = sc.sampler_check(view, **CHECK)
    assert first["parameters"] == second["parameters"]
    assert first["n_samples"] == second["n_samples"]


def test_interval_overlap_and_verdict():
    assert sc.interval_overlap((0.0, 1.0), (0.5, 1.5)) == pytest.approx(0.5)
    assert sc.interval_overlap((0.0, 1.0), (2.0, 3.0)) == 0.0
    assert sc.interval_overlap((0.0, 1.0), (0.0, 1.0)) == pytest.approx(1.0)
    assert sc.interval_overlap((1.0, 1.0), (0.0, 1.0)) == 0.0   # an empty interval shares nothing
    assert sc.interval_verdict(0.5) == "agree" and sc.interval_verdict(0.49) == "mismatch"


def test_the_text_names_the_block_and_the_verdict(view):
    result = sc.sampler_check(view, **CHECK)
    t = sc.text(result)
    assert view.label in t and result["verdict"] in t
    assert str(result["n_samples"]) in t


# --------------------------------------------------------------------------------------------
# the setting and its wiring


def test_the_setting_is_declared_and_off_by_default():
    full = gf.settings()["sampler_check"]
    assert full["enabled"] is False
    assert (full["steps"], full["runs"], full["walkers"]) == (1500, 8, 40)
    assert full["start_spread"] == 0.002 and full["first_seed"] == 100
    quick = gf.settings("quick")["sampler_check"]
    assert quick["enabled"] is False and quick["steps"] == 200


def test_resolve_follows_the_flag():
    declared = gf.settings()["sampler_check"]
    assert sc.resolve(None, declared) is None              # the declaration is off
    assert sc.resolve(False, declared) is None
    on = sc.resolve(True, declared)
    assert on["enabled"] is True and on["steps"] == 1500
    small = sc.resolve(dict(steps=50, walkers=16), declared)
    assert small["enabled"] is True and small["steps"] == 50 and small["walkers"] == 16
    assert small["runs"] == declared["runs"]               # undeclared keys stay declared
    assert sc.resolve(dict(enabled=False), declared) is None
    assert sc.resolve(None, dict(declared, enabled=True))["enabled"] is True


def test_the_analysis_runs_the_check_only_when_enabled(data):
    off = st.Analysis(data, preset="quick", workers=1, profile=False,
                      fit_overrides=TINY_FIT)
    assert off.sampler_check is None
    on = st.Analysis(data, preset="quick", workers=1, profile=False,
                     sampler_check=dict(steps=100, runs=1, walkers=16),
                     fit_overrides=TINY_FIT)
    assert on.sampler_check["steps"] == 100 and on.sampler_check["enabled"] is True
    # enabled through the declared setting itself (the fit_overrides path, e.g. over the RPC)
    via_settings = st.Analysis(data, preset="quick", workers=1, profile=False,
                               fit_overrides=dict(TINY_FIT,
                                                  sampler_check=dict(enabled=True, steps=100)))
    assert via_settings.sampler_check["enabled"] is True


def test_a_stage_reports_the_check(data):
    a = st.Analysis(data, preset="quick", workers=1, profile=False,
                    sampler_check=dict(steps=100, runs=1, walkers=24),
                    fit_overrides=TINY_FIT)
    result = a.run("A")
    stage = result.stages["A"]
    check = stage.numbers["sampler_check"]["AF488 in H2O"]
    assert check["block"] == "AF488 in H2O"
    assert {"scale", "delta", "s_common"} <= {r["parameter"] for r in check["parameters"]}
    # every surface the results flow through carries it (numbers are JSON-able copies)
    assert stage.numbers["blocks"]["AF488 in H2O"]["sampler_check"] == check
    assert "sampler_check:AF488 in H2O" in stage.plots
    assert "MCMC" in stage.text or "sampler" in stage.text
    assert "sampler_check" not in stage.tables             # no declared table: numbers only
    json.dumps(result.to_dict())                           # the JSON summary stays JSON-able


def test_a_default_stage_has_no_check(data):
    a = st.Analysis(data, preset="quick", workers=1, profile=False, fit_overrides=TINY_FIT)
    result = a.run("B")
    assert "sampler_check" not in result.stages["B"].numbers
    assert not any(k.startswith("sampler_check:") for k in result.stages["B"].plots)
