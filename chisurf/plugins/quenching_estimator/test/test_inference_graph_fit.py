"""The graph fit's arithmetic and the stage plumbing, fast (no site tables).

A small analytic stand-in for the site model (:class:`FakeSite`: contacts, residue counts,
exposure, the same parameter names) makes every step checkable in seconds: the search finds a
known truth, an injected outlier is flagged by the search and by leave one out, the Laplace
interval holds the truth, propagation equals the analytic error, the profile likelihood has its
minimum at the best fit, the factor graph of the MalE layout has the stored structure, and the
stages build every declared table, report progress and stop on cancel. The real-table numbers
are in ``test_male_reproduction.py`` (slow).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.inference import columns
from chisurf.plugins.quenching_estimator.core.inference import graph_fit as gf
from chisurf.plugins.quenching_estimator.core.inference import stages as st
from chisurf.plugins.quenching_estimator.core.tasks import CancelledError

GROUPS = ["aromatic", "hydrophobic", "basic", "acidic", "polar"]


class FakeSite:
    """An analytic site: quenching rate from contacts, stickiness and exposure."""

    def __init__(self, seed):
        rng = np.random.default_rng(seed)
        self.c = rng.uniform(0.0, 0.6, (5, 2))
        self.n = rng.integers(0, 4, 5).astype(float)
        self.e = float(rng.uniform(0.3, 1.0))
        self.a = float(rng.uniform(0.5, 1.5))
        self.exposure = np.array([self.e])

    def _rate(self, th):
        c = (1 - th["lam"]) * self.c[:, 0] + th["lam"] * self.c[:, 1]
        stick = np.exp(-0.3 * sum(n * th[f"ln_s_{g}"] for n, g in zip(self.n, GROUPS)))
        return np.exp(th["ln_scale"]) * (c @ np.asarray(th["kq"])) * stick * np.exp(
            -0.3 * self.a * th["delta"]), c

    def lifetime(self, th, tau0, water=0.0):
        k, c = self._rate(th)
        t0 = tau0 + th.get("dtau_shield", 0.0) * (1 - self.e)
        tau = 1 / (1 / t0 + k + water * self.e)
        dark = 1 - np.exp(-np.exp(th["ln_static"]) * (c @ np.asarray(th["kq"])))
        return float(tau), float(dark), self.e

    def exposure_profile(self, th, tau0, water=0.0):
        return dict(exposure=self.exposure, weight=np.ones(1), visible=self.e,
                    reachable=self.e, dark_fraction=self.lifetime(th, tau0, water)[1])


class FakeLibrary:
    """``.site(state, site, linker)`` -> a FakeSite fixed by its key."""

    def __init__(self):
        self.sites = {}

    def site(self, state, site, linker_length):
        key = (state, int(site), float(linker_length))
        if key not in self.sites:
            self.sites[key] = FakeSite(10 * int(site) + (state == "HOLO"))
        return self.sites[key]


ROW = np.dtype([("site", "i8"), ("state", "U4"), ("solvent", "U3"), ("tau_x", "f8"),
                ("sigma_meas", "f8")])

TRUTH = {"ln_s_common": -1.0, "ln_s_aromatic": -0.5, "ln_s_hydrophobic": -1.0,
         "ln_s_basic": -2.0, "ln_s_acidic": -0.3, "ln_s_polar": -1.5,
         "ln_scale": np.log(0.5), "delta": 0.5, "dtau_shield": 0.8}


@pytest.fixture(scope="module")
def data():
    return st.load_analysis_data(library=FakeLibrary())


@pytest.fixture(scope="module")
def fit_settings():
    return gf.settings("quick", dict(n_starts=8, search_maxiter=200, joint_max_nfev=200))


def _block(data, fit_settings, outlier_row=3, n=30, label="Cy3B synthetic"):
    sites = [FakeSite(1000 + k) for k in range(n)]
    probe = gf.Block(label, "Cy3B", np.zeros(n, ROW), [(s, 0.0) for s in sites], 2.39,
                     data.context, fit_settings, GROUPS)
    th = dict(probe.fixed, **TRUTH, ln_tau0=np.log(2.39), kq=data.context.kq("Cy3B"))
    rows = np.zeros(n, ROW)
    rows["site"] = np.arange(n) + 1
    rows["state"] = "APO"
    rows["solvent"] = "H2O"
    rows["tau_x"] = [s.lifetime(th, 2.39)[0] for s in sites]
    rows["sigma_meas"] = 0.01
    if outlier_row is not None:
        rows["tau_x"][outlier_row] += 0.8
    return gf.Block(label, "Cy3B", rows, [(s, 0.0) for s in sites], 2.39, data.context,
                    fit_settings, GROUPS)


def test_parameters_follow_the_declaration():
    fs = gf.settings()
    assert [p.name for p in gf.parameter_specs(fs)][:7] == [
        "ln_s_common", "ln_s_aromatic", "ln_s_hydrophobic", "ln_s_basic", "ln_s_acidic",
        "ln_s_polar", "ln_scale"]
    assert gf.fixed_values("AF488", fs) == {"ln_static": np.log(1e-3), "delta_static": 0.0}
    counts = {d: len(gf.free_names(d, gf.fixed_values(d, fs), fs))
              for d in ("AF488", "Cy3B", "Atto655")}
    assert counts == {"AF488": 10, "Cy3B": 10, "Atto655": 12}
    assert "dtau_shield" not in gf.free_names("AF488", (), fs)
    quick = gf.settings("quick")
    assert (quick["n_starts"], quick["search_maxiter"]) == (8, 60) and fs["n_starts"] == 64
    with pytest.raises(KeyError):
        gf.settings(overrides={"no_such_setting": 1})


def test_model_error_criterion_and_floor():
    fs = gf.settings()
    sigma = np.full(40, 0.02)
    assert gf.model_error(np.full(40, 1e-3), sigma, fs) == fs["model_error_floor"]
    r = np.random.default_rng(0).normal(0, 0.3, 40)
    s = gf.model_error(r, sigma, fs)
    assert s > 0.1
    assert abs(np.median(r**2 / (sigma**2 + s**2)) - fs["model_error_median_chi2"]) < 1e-9


def test_clipped_inverse_caps_flat_directions():
    H = np.diag([100.0, 2.0, 1e-9])
    cov = gf.clipped_inverse(H, 0.25)
    assert np.allclose(np.diag(cov), [0.01, 0.25, 0.25])


def test_search_joint_fit_and_laplace_recover_the_truth(data, fit_settings):
    block = gf.search(_block(data, fit_settings), 7, fit_settings, workers=1)
    assert block.s == fit_settings["model_error_floor"]
    assert not block.use[3] and block.use.sum() == 29
    graph = gf.Graph([block], fit_settings)
    assert graph.n_parameters == 9 + 8 and len(graph.k_keys) == 8
    gf.joint_fit(graph, workers=1)
    (view,) = gf.block_views(graph, "synthetic")
    for label, truth, log in (("scale", 0.5, True), ("delta", 0.5, False),
                              ("dtau_shield", 0.8, False), ("s_basic", np.exp(-2.0), True)):
        e = view.estimate(label)
        f = np.log if log else (lambda x: x)
        assert e["low"] < e["value"] < e["high"], (label, e)
        # the truth lies within three Laplace sds of the best fit
        sd = (f(e["high"]) - f(e["low"])) / 2
        assert abs(f(e["value"]) - f(truth)) < 3 * sd, (label, e)
    assert view.stats["outliers"] == [4]          # row 3 is site 4
    assert view.worst[0][0] == 4 and view.worst[0][1] > 10
    assert view.table["outlier"].sum() == 1 and not view.table["used"][3]
    assert view.estimate("lam")["note"].startswith("fixed")
    assert set(view.table.dtype.names) == {c["column"] for c in
                                           columns.columns("fit_predictions", gf.RESULT_COLUMNS)}
    # propagation: d scale = scale * d ln_scale
    value, sd = gf.propagate(view, lambda th: [np.exp(th["ln_scale"])])
    j = gf._layout_index(view, "ln_scale")
    expected = value[0] * np.sqrt(graph.cov[j, j]) * (graph.hi[j] - graph.lo[j])
    assert abs(sd[0] - expected) < 1e-3 * expected
    lap = gf.sample_summary(gf.laplace_samples(view))
    assert abs(lap["median"] - view.estimate("scale")["value"]) < 0.01
    # the profile likelihood: minimum at the best fit, deviance 1 brackets an interval of the
    # same size as Laplace's (this posterior is close to Gaussian in ln scale)
    prof = gf.profile_likelihood(view, max_nfev=50)
    e = view.estimate("scale")
    assert 0.0 <= prof["deviance"].min() < 0.05
    assert prof["deviance"][0] > 1 and prof["deviance"][-1] > 1
    assert prof["low"] < e["value"] < prof["high"]
    width = np.log(prof["high"] / prof["low"]) / np.log(e["high"] / e["low"])
    assert 0.5 < width < 2.0, width


def test_worker_processes_give_the_same_searches(data, fit_settings):
    fs = dict(fit_settings, n_starts=3, search_maxiter=20)
    one = gf.search(_block(data, fs), 11, fs, workers=1)
    two = gf.search(_block(data, fs), 11, fs, workers=2)
    assert [lp for _, lp in one.searches] == [lp for _, lp in two.searches]
    assert np.array_equal(one.best_x, two.best_x)


def test_one_pool_for_many_jacobians_and_the_polished_profile(data, fit_settings):
    """The quick preset's path: Jacobians on running workers, profile points by the polish."""
    assert fit_settings["joint_minpack"] is False
    assert fit_settings["profile_likelihood"]["method"] == "polish"
    assert gf.settings()["joint_minpack"] is True
    block = gf.search(_block(data, fit_settings), 7, fit_settings, workers=1)
    graph = gf.Graph([block], fit_settings)
    gf.joint_fit(graph, workers=1)
    one = graph.jacobian(graph.u, workers=1)[0]
    with gf.WorkerPool(dict(graph=graph.lean()), 2) as pool:
        first = graph.jacobian(graph.u, pool=pool)[0]
        executor = pool.executor()
        second = graph.jacobian(graph.u, pool=pool)[0]
        assert pool.executor() is executor          # the same processes
    assert pool._pool is None
    assert np.array_equal(one, first) and np.array_equal(first, second)
    # a held coordinate stays where it is
    j = gf._layout_index(gf.block_views(graph)[0], "ln_scale")
    u = graph.u.copy()
    u[j] = 0.3
    held = gf.polish(graph, u, 5, 1e-12, workers=1, hold=[j])
    assert held["u"][j] == 0.3 and held["cost"] <= 0.5 * float(graph.evaluate(u)[0] @
                                                              graph.evaluate(u)[0])
    # the polished profile agrees with MINPACK's on this near-Gaussian posterior
    (view,) = gf.block_views(graph, "synthetic")
    polished = gf.profile_likelihood(view, workers=2)
    graph.settings = dict(fit_settings, profile_likelihood=dict(
        fit_settings["profile_likelihood"], method="minpack"))
    minpack = gf.profile_likelihood(view, max_nfev=50)
    assert 0.0 <= polished["deviance"].min() < 0.05
    for key in ("low", "high"):
        assert abs(np.log(polished[key] / minpack[key])) < 0.1, (key, polished, minpack)


def test_factor_graph_of_the_male_layout(data):
    a = st.Analysis(data, preset="quick", workers=1)
    blocks = a.blocks("joint")
    assert [b.label for b in blocks] == ["AF488 in H2O", "Cy3B in H2O", "Atto655 in D2O and H2O"]
    assert [len(b.rows) for b in blocks] == [18, 10, 36]
    assert blocks[2].points[18][1] == data.errors.kqw_free and blocks[2].points[0][1] == 0.0
    graph = gf.Graph(blocks, a.fit_settings)
    assert graph.n_parameters == 41 and len(graph.k_keys) == 12
    s = gf.describe_graph(graph, data.titrated)
    assert (s["variables"], s["likelihoods"], s["priors"], s["treewidth"]) == (48, 20, 3, 18)
    assert sorted((c["dyes"], c["slopes"]) for c in s["components"]) == [
        (["AF488"], 0), (["Atto655", "Cy3B"], 17)]
    assert gf.Graph(a.blocks("heavy_water"), a.fit_settings).n_parameters == 19


def test_stages_build_every_declared_table(data, tmp_path):
    a = st.Analysis(data, preset="quick", workers=1, fit_overrides=dict(
        n_starts=2, search_maxiter=4, joint_max_nfev=2,
        profile_likelihood=dict(points=3, span_sd=1.0, max_nfev=2)))
    seen = []
    result = a.run("all", progress=lambda p, m: seen.append(p))
    assert list(result.stages) == st.stage_names() == ["A", "B", "naive_h2o", "C", "summary"]
    assert seen[-1] == 100 and seen == sorted(seen)
    c = result.stages["C"]
    assert len(c.tables["water_access"]) == 18 and len(c.tables["exposure"]) == 2
    assert {"r_all", "r_without"} <= set(c.numbers["water_access"])
    assert "compare_scale" in c.numbers and "profile" in c.numbers["compare_scale"]
    assert result.stages["naive_h2o"].numbers["n"] == 18
    assert len(result.stages["summary"].tables["dyes"]) == 3
    assert {"parity:AF488 in H2O", "loo:Cy3B in H2O", "profile:AF488 in H2O",
            "k_graph"} <= set(result.stages["A"].plots)
    json.dumps(result.to_dict())
    files = result.write(tmp_path)
    assert (tmp_path / "A.estimates.csv").exists() and (tmp_path / "report.md").exists()
    assert len(files) == len(result.tables()) + 2
    # a continued analysis reuses the solved graphs
    again = st.run_stage("C", analysis=a)
    assert again.graphs["joint"] is result.graphs["joint"]


def test_cancel_stops_at_the_next_checkpoint(data):
    a = st.Analysis(data, preset="quick", workers=1, profile=False,
                    fit_overrides=dict(n_starts=3, search_maxiter=3))
    calls = []

    def cancel():
        calls.append(1)
        return len(calls) > 2

    with pytest.raises(CancelledError):
        a.run("A", cancel=cancel)
    assert "joint" not in a.result.graphs


UNGUARDED = """
from chisurf.plugins.quenching_estimator.core.inference import stages as st
from chisurf.plugins.quenching_estimator.test.test_inference_graph_fit import FakeLibrary
data = st.load_analysis_data(library=FakeLibrary())
a = st.Analysis(data, preset="quick", workers=2, profile=False,
                fit_overrides=dict(n_starts=3, search_maxiter=3, joint_max_nfev=2))
r = a.run("B")
print("OK", r.stages["B"].numbers["blocks"]["Atto655 in D2O"]["stats"]["n_rows"])
"""


def test_worker_processes_from_a_script_without_main_guard(tmp_path):
    import subprocess
    import sys

    script = tmp_path / "unguarded.py"
    script.write_text(UNGUARDED)
    out = subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                         timeout=600, cwd=str(tmp_path))
    assert out.returncode == 0, out.stderr[-3000:]
    assert "OK 18" in out.stdout
    assert out.stdout.count("OK") == 1          # the workers did not re-run the script
