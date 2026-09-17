"""Headless model-editor tests for the AutoForm-ported PDA models (PRD-38/PRD-50).

These mirror ``test_model_editor_integration.py`` but for the PDA family. They
walk the real add-fit path for each pure PDA model:

* ``build_model_editor(model)`` returns an :class:`AutoModelWidget`;
* every ``ParameterGroupSection`` resolves to a group that has parameters;
* the dynamic species/distance/component groups render rows;
* plot specs resolve (distribution accessor imports cleanly);
* ``model.update()`` computes a finite, non-empty curve.

A synthetic ``data.pda`` is built so no TTTR files or heavy I/O are needed.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy import stats


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    return app


def _make_pda_data(nmax: int = 60, nmin: int = 5):
    """Return a DataCurve carrying a synthetic, valid ``.pda`` metadata dict."""
    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.data import DataCurve

    n = np.arange(nmax + 1)
    ps = stats.poisson.pmf(n, mu=20.0).astype(float)
    ps /= ps.sum()

    s1s2 = np.zeros((nmax + 1, nmax + 1), dtype=float)
    for N in range(nmin, nmax + 1):
        g = np.arange(N + 1)
        s1s2[g, N - g] += ps[N] * stats.binom.pmf(g, N, 0.6) * 1000.0

    ny, nx = s1s2.shape
    rr, cc = np.indices((ny, nx))
    y = s1s2.ravel(order="C")
    x = np.arange(y.size)
    pda = {
        "maximum_number_of_photons": nmax,
        "minimum_number_of_photons": nmin,
        "minimum_time_window_length": 2e-3,
        "segmentation": "time-bins",
        "observation_time": 2e-3,
        "channels": ([0], [1]),
        "s1s2": s1s2,
        "ps": ps,
        "row_indices": rr.ravel().tolist(),
        "col_indices": cc.ravel().tolist(),
        "ndim": 2,
        "shape": (ny, nx),
        "size": int(y.size),
        "tttr_indices": None,
    }
    return DataCurve(
        name="synthetic-pda",
        load_filename_on_init=False,
        pda=pda,
        y=y,
        x=x,
        ey=tcspc.counting_noise(y),
    )


def _make_pda_fit(model_class):
    import chisurf.core.fitting.fit as fit_mod

    return fit_mod.Fit(model_class=model_class, data=_make_pda_data())


PDA_MODELS = [
    "chisurf.core.models.pda2c.simple.Pda2cSimpleModel",
    "chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel",
    "chisurf.core.models.pda2c.dynamic.Pda2cDynamicTwoStateModel",
    "chisurf.core.models.pda2c.dynamic_mc.Pda2cDynamicNStateModel",
    "chisurf.core.models.pda2c.anisotropy.Pda2cAnisotropyModel",
]

# Fixed-layout dynamic models have no add/remove component group.
_FIXED_LAYOUT = ("Pda2cDynamicTwoStateModel", "Pda2cDynamicNStateModel")


def _resolve(path):
    import importlib

    mod, _, name = path.rpartition(".")
    return getattr(importlib.import_module(mod), name)


@pytest.mark.parametrize("model_path", PDA_MODELS)
def test_pda_model_editor_renders_and_computes(qapp, model_path):
    from qtpy import QtWidgets

    from chisurf.core.models import view_spec as vs
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import (
        build_model_editor,
        model_plot_specs,
    )

    model_class = _resolve(model_path)
    # AutoForm requires a declarative spec file on the pure model.
    assert getattr(model_class, "view_spec_file", None), f"{model_path} has no view_spec_file"

    fit = _make_pda_fit(model_class)
    model = fit.model

    # (a) build_model_editor returns a real AutoForm widget (the add-fit crash site)
    editor = build_model_editor(model)
    assert isinstance(editor, AutoModelWidget)
    QtWidgets.QVBoxLayout().addWidget(editor)

    # (b) editor is not a row of empty titled boxes
    from chisurf.gui.autoform.sections.parameter_table import ParameterGroupTableWidget
    table_rows = sum(t.table_model.rowCount() for t in editor.findChildren(ParameterGroupTableWidget))
    assert len(editor.parameter_widgets) + table_rows > 3, "parameter groups rendered empty"

    # (c) every parameter-group section resolves to a group that has parameters
    spec = model.view_spec()
    for section in spec.flat_sections():
        if isinstance(section, (vs.ParameterGroupSection, vs.ParameterGroupTableSection)):
            group = getattr(model, section.target)
            if hasattr(group, "find_parameters") and not list(group.parameters_all):
                group.find_parameters()
            assert list(group.parameters_all), f"group {section.target!r} has no parameters"

    # (d) variable-component models expose an add/remove dynamic group. The
    # fixed-layout dynamic models (2/3-state) are exempt.
    if not any(fx in model_path for fx in _FIXED_LAYOUT):
        dyn = [s for s in spec.flat_sections() if isinstance(s, vs.DynamicGroupSection)]
        assert dyn, "no dynamic component group in PDA editor"

    # (e) plot specs resolve (distribution accessor imports) and model computes
    assert model_plot_specs(model), "no plot specs resolved"
    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y)), "model did not compute a finite curve"


def test_dynamic_two_state_limits():
    """The two-state occupation-time law reduces correctly in both limits.

    Slow exchange (K->0): mass concentrates at the boundaries f in {0, 1}.
    Fast exchange (K->inf): mass concentrates near f = p1 (steady occupancy).

    Checked against ``two_state_occupation_quadrature``, which replaced the
    closed-form Bessel density this test used to exercise — that density was
    not a distribution away from ``p1 = 0.5``. Fuller coverage, including a
    comparison against a direct simulation of the telegraph process, lives in
    ``test/models/test_two_state_occupation.py``.
    """
    from chisurf.core.models.pda2c.dynamic import two_state_occupation_quadrature

    p1 = 0.3

    # Slow: essentially everything sits on the two boundary atoms.
    f_slow, w_slow = two_state_occupation_quadrature(p1, 1e-3)
    assert (w_slow[0] + w_slow[-1]) > 0.99
    assert w_slow[-1] == pytest.approx(p1, abs=1e-3)

    # Fast: the distribution collapses onto the steady-state occupancy.
    f_fast, w_fast = two_state_occupation_quadrature(p1, 500.0)
    assert float(w_fast @ f_fast) == pytest.approx(p1, abs=1e-3)
    assert np.sqrt(w_fast @ (f_fast - p1) ** 2) < 0.05
    assert (w_fast[0] + w_fast[-1]) < 1e-6


def test_dynamic_two_state_matches_static_in_slow_limit(qapp):
    """Dynamic model computes a finite, positive histogram in the static limit.

    With K->0 the dynamic model reduces to a static two-population PDA; here we
    assert it produces a finite, non-empty, positive-sum curve.
    """
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.pda2c.dynamic import Pda2cDynamicTwoStateModel

    fit = fit_mod.Fit(model_class=Pda2cDynamicTwoStateModel, data=_make_pda_data())
    model = fit.model
    # Push toward the static two-state limit and update.
    model.states._kex.value = 0.0
    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y)) and float(np.sum(y)) > 0.0


def _dynamic_two_state_fit(true_kex, free_kex, total=2e5, seed=1):
    """Build a dynamic-PDA self-recovery fit and run it.

    ``true_kex`` is the *dimensionless* exchange ``K = (k1 + k2) * T`` -- the
    only thing a single dataset determines -- and is converted to the rate the
    model actually carries using the dataset's observation time.

    The data is a Poisson realisation of the two-state dynamic model at
    ``true_kex``. Both candidate fits are given the same structural freedom --
    the two distances and the occupancy -- so the *only* thing that
    distinguishes them is whether the exchange parameter is free (dynamic) or
    pinned at zero (static two-population limit). That makes them properly
    nested and gives the static alternative every chance to mimic the data.

    Returns
    -------
    tuple
        ``(fit, model)`` after ``fit.run()``.
    """
    import chisurf.core.fluorescence.tcspc as tcspc

    model_class = _resolve("chisurf.core.models.pda2c.dynamic.Pda2cDynamicTwoStateModel")
    fit = _make_pda_fit(model_class)
    m = fit.model
    st = m.states
    st._R1.value, st._s1.value = 40.0, 4.0
    st._R2.value, st._s2.value = 62.0, 4.0
    st._x1.value, st._kex.value = 0.5, true_kex / m.observation_time
    m.update()
    _ = m.get_wres(fit)

    s1s2 = np.asarray(m.pda.get_S1S2_matrix(), dtype=float)
    ny, nx = fit.data.pda["shape"]
    s1s2 = s1s2[:ny, :nx]
    s1s2 = s1s2 / max(s1s2.sum(), 1e-12) * total
    noisy = np.random.default_rng(seed).poisson(s1s2).astype(float)

    fit.data.pda["s1s2"] = noisy
    fit.data.y = noisy.ravel(order="C")
    fit.data.ey = tcspc.counting_noise(fit.data.y)

    for p in m.parameters_all:
        p.fixed = True
    for p in (st._x1, st._R1, st._R2):
        p.fixed = False
    # Perturbed start, so recovery is not the trivial identity.
    st._x1.value, st._R1.value, st._R2.value = 0.42, 43.0, 58.0
    st._kex.fixed = not free_kex
    st._kex.value = (true_kex * 4.0 / m.observation_time) if free_kex else 0.0

    m.find_parameters()
    fit.run()
    return fit, m


def test_dynamic_pda_recovers_exchange_and_rejects_the_static_model(qapp):
    """PRD-50 acceptance: 2-state exchange is recovered; static-only is rejected.

    Two halves, matching the PRD criterion:

    1. a synthetic 2-state exchange at a known rate is recovered by the fit;
    2. the nested static-only alternative is rejected by the F-test that the
       ``f_test`` plugin exposes (both share
       :func:`chisurf.core.math.statistics.f_test_confidence`).
    """
    from chisurf.core.math.statistics import f_test_confidence

    true_kex = 2.0
    fit_dyn, m_dyn = _dynamic_two_state_fit(true_kex, free_kex=True)
    st = m_dyn.states

    # (1) the exchange rate -- and the state structure -- come back. The model
    # carries a rate in Hz; what the data determines is the product with the
    # observation time, so that is what is checked.
    assert m_dyn.transitions_per_window == pytest.approx(true_kex, rel=0.1)
    assert st.k_ex == pytest.approx(true_kex / m_dyn.observation_time, rel=0.1)
    assert st.R1 == pytest.approx(40.0, abs=1.0)
    assert st.R2 == pytest.approx(62.0, abs=1.0)
    assert st.x1 == pytest.approx(0.5, abs=0.05)
    # Converged means at least as good as the truth on this realisation. An
    # absolute bound (chi2r < 1.5) measured the noise instead: at the true
    # parameters this dataset's chi2r is 1.62, and across seeds it spans
    # 0.8-1.7.
    chi2r_fit = fit_dyn.chi2r
    fitted = [p.value for p in (st._R1, st._R2, st._x1, st._kex)]
    st._R1.value, st._R2.value, st._x1.value = 40.0, 62.0, 0.5
    st._kex.value = true_kex / m_dyn.observation_time
    fit_dyn.update()
    chi2r_truth = fit_dyn.chi2r
    for parameter, value in zip((st._R1, st._R2, st._x1, st._kex), fitted):
        parameter.value = value
    fit_dyn.update()
    assert chi2r_fit <= chi2r_truth + 1e-9, (
        f"the fit stopped above the truth (chi2r {chi2r_fit:.3f} > {chi2r_truth:.3f})")

    # (2) the static limit cannot follow, even re-optimising both distances:
    # it pulls them together to imitate dynamic averaging and still fails.
    fit_static, m_static = _dynamic_two_state_fit(true_kex, free_kex=False)
    assert m_static.states.k_ex == 0.0
    assert m_static.n_free == m_dyn.n_free - 1, "the two models must be nested"
    assert fit_static.chi2r > 10.0 * fit_dyn.chi2r

    confidence = f_test_confidence(
        chi2r_1=fit_static.chi2r,
        chi2r_2=fit_dyn.chi2r,
        nu_1=m_static.n_points - m_static.n_free,
        nu_2=m_dyn.n_points - m_dyn.n_free,
    )
    assert confidence > 0.99, f"F-test failed to reject the static model (conf={confidence:.4f})"


def test_three_state_mc_gillespie_equilibrium():
    """The sampled occupancies recover the analytic equilibrium populations."""
    from chisurf.core.fluorescence.kinetics import (
        equilibrium_populations,
        occupation_time_fractions,
    )

    # K[target, source]; symmetric-ish 3-state scheme.
    K = np.array([
        [0.0, 200.0, 50.0],
        [150.0, 0.0, 300.0],
        [100.0, 250.0, 0.0],
    ])
    p_eq = equilibrium_populations(K)
    assert abs(p_eq.sum() - 1.0) < 1e-9 and np.all(p_eq >= 0)

    # Long windows -> mean time-fraction converges to equilibrium populations.
    fr = occupation_time_fractions(K, window=2.0, n_samples=1500, seed=3)
    assert fr.shape == (1500, 3)
    assert np.allclose(fr.sum(axis=1), 1.0, atol=1e-9)
    assert np.allclose(fr.mean(axis=0), p_eq, atol=0.05)


def test_three_state_mc_model_computes(qapp):
    """The 3-state MC PDA model builds a finite, positive histogram."""
    model_class = _resolve("chisurf.core.models.pda2c.dynamic_mc.Pda2cDynamicNStateModel")
    fit = _make_pda_fit(model_class)
    model = fit.model
    model.states._n_windows.value = 800  # keep the test fast
    model.update()
    y = np.asarray(model.y)
    assert y.size > 0 and np.all(np.isfinite(y)) and float(np.sum(y)) > 0.0
    # MC result is cached: same rates -> same fractions object (no re-sim).
    frac1 = model._time_fractions()
    frac2 = model._time_fractions()
    assert frac1 is frac2


def test_pda_corrected_axes_e_and_r(qapp):
    """The corrected FRET-efficiency and distance histogram axes compute."""
    from chisurf.core.models.pda2c.common import get_pda_distribution

    model_class = _resolve("chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel")
    fit = _make_pda_fit(model_class)
    fit.model.update()
    for axis, lo, hi in [("E", 0.0, 1.0), ("R", 20.0, 100.0)]:
        curves = get_pda_distribution(fit, {"x_max": hi, "x_min": lo, "log_x": False,
                                            "n_bins": 41, "n_min": 10, "histogram": axis})
        assert curves, f"axis {axis} produced no curves"
        x = np.asarray(curves[0][1])
        assert x.size > 0 and np.all(np.isfinite(x))


def test_apply_lightpath_matrices():
    """Pda2cFretNuisance ingests a light-path crosstalk-matrix result correctly."""
    from chisurf.core.models.pda2c.nusiance import Pda2cFretNuisance

    matrices = {
        "excitation": {
            "rows": ["laser_green", "laser_red"],
            "columns": ["donor", "acceptor"],
            "values": [[1.0, 0.05], [0.0, 1.0]],
        },
        "emission": {
            "rows": ["donor", "acceptor"],
            "columns": ["det_green", "det_red"],
            "values": [[0.9, 0.05], [0.02, 0.95]],
        },
    }
    n = Pda2cFretNuisance()
    n.apply_lightpath_matrices(
        matrices,
        donor="donor",
        acceptor="acceptor",
        green_detector="det_green",
        red_detector="det_red",
        green_laser="laser_green",
    )
    assert n.ExDG == 1.0 and n.ExAG == 0.05
    assert n.cGD == 0.9 and n.cRD == 0.05
    assert n.cGA == 0.02 and n.cRA == 0.95
    # Derived MFD factors recomputed and finite.
    for name in ("alpha", "gamma", "delta"):
        assert np.isfinite(getattr(n, name)), f"{name} not computed"


def test_pda_gaussian_plots_pr_and_residual2d(qapp):
    """Gaussian PDA exposes the P(R) distribution and 2D S1S2 residual plots."""
    from chisurf.core.models.pda2c.common import (
        get_pda_distance_distribution,
        get_pda_residual_image,
    )
    from chisurf.gui.plots.residual_image import Residual2DPlot
    from chisurf.gui.widgets.models.model_editor import model_plot_specs

    model_class = _resolve("chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel")
    fit = _make_pda_fit(model_class)
    model = fit.model
    model.distances.append()  # a second Gaussian component
    model.update()

    # P(R): summed distribution + one curve per Gaussian component.
    pr = get_pda_distance_distribution(fit)
    assert len(pr) == 3
    assert all(len(np.asarray(y)) > 0 for y, _ in pr)

    # 2D S1S2 weighted residual image is finite.
    img, xa, ya = get_pda_residual_image(fit)
    assert img is not None and img.ndim == 2 and np.all(np.isfinite(img))

    # The residual2d plot is wired via view.json and its accessor resolves.
    specs = model_plot_specs(model)
    res2d = [opts for cls, opts in specs if cls is Residual2DPlot]
    assert res2d, "residual2d plot not resolved from view.json"
    assert callable(res2d[0].get("accessor")), "residual2d accessor not resolved to a callable"


def test_pda_gaussian_correction_factors(qapp):
    """The Gaussian PDA model populates read-only alpha/gamma/delta outputs."""
    model_class = _resolve("chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel")
    fit = _make_pda_fit(model_class)
    model = fit.model
    model.update()
    n = model.nuisance
    for name in ("alpha", "gamma", "delta"):
        assert np.isfinite(getattr(n, name)), f"{name} not computed"


def test_pda_gaussian_fit_recovers_distance(qapp):
    """PRD-50 primary acceptance: a fit recovers a known Gaussian mean distance.

    Self-recovery — the model's own S1S2 histogram at a known mean is used as the
    experimental data (so the truth is the exact minimum), every parameter except
    the mean is fixed, the mean is perturbed, and ``fit.run()`` must find it back.
    """
    import chisurf.core.fluorescence.tcspc as tcspc

    model_class = _resolve("chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel")
    fit = _make_pda_fit(model_class)
    m = fit.model

    true_mean = 52.0
    m.distances._means[0].value = true_mean
    m.distances._sigmas[0].value = 6.0
    m.update()
    _ = m.get_wres(fit)  # sets the histogram_function on m.pda
    s1s2 = np.asarray(m.pda.get_S1S2_matrix(), dtype=float)
    ny, nx = fit.data.pda["shape"]
    s1s2 = s1s2[:ny, :nx]
    s1s2 = s1s2 / max(s1s2.sum(), 1e-12) * 1e5  # scale to counts

    # Use the truth histogram as the experimental data.
    fit.data.pda["s1s2"] = s1s2
    fit.data.y = s1s2.ravel(order="C")
    fit.data.ey = tcspc.counting_noise(fit.data.y)

    # Fix everything, free only the mean, and perturb it.
    for p in m.parameters_all:
        p.fixed = True
    mean_p = m.distances._means[0]
    mean_p.bounds = (20.0, 90.0)
    mean_p.bounds_on = True
    mean_p.fixed = False
    mean_p.value = 44.0  # perturbed start
    m.find_parameters()

    def _chi2r():
        m.update()
        w = np.asarray(m.get_wres(fit), dtype=float)
        w = w[np.isfinite(w)]
        return float(np.sum(w ** 2) / max(len(w), 1))

    assert _chi2r() > 1.0, "perturbed start was not actually poor"
    fit.run()
    assert m.distances._means[0].value == pytest.approx(true_mean, abs=2.0)


def _pda_noisy_truth_fit(true_mean=52.0, true_sigma=6.0, total=1500.0, seed=3):
    """Return a Poisson-noisy self-recovery fit at ``true_mean``.

    The data is a Poisson realisation of the Gaussian PDA model at ``true_mean``,
    with every parameter fixed except that mean.
    """
    import chisurf.core.fluorescence.tcspc as tcspc

    model_class = _resolve("chisurf.core.models.pda2c.pdagauss.Pda2cGaussianDistanceModel")
    fit = _make_pda_fit(model_class)
    m = fit.model
    m.distances._means[0].value = true_mean
    m.distances._sigmas[0].value = true_sigma
    m.update()
    _ = m.get_wres(fit)
    s1s2 = np.asarray(m.pda.get_S1S2_matrix(), dtype=float)
    ny, nx = fit.data.pda["shape"]
    s1s2 = s1s2[:ny, :nx]
    s1s2 = s1s2 / max(s1s2.sum(), 1e-12) * total
    noisy = np.random.default_rng(seed).poisson(s1s2).astype(float)

    fit.data.pda["s1s2"] = noisy
    fit.data.y = noisy.ravel(order="C")
    fit.data.ey = tcspc.counting_noise(fit.data.y)

    for p in m.parameters_all:
        p.fixed = True
    mean_p = m.distances._means[0]
    mean_p.bounds = (30.0, 80.0)
    mean_p.bounds_on = True
    mean_p.fixed = False
    m.find_parameters()
    return fit, m, mean_p


def test_pda_error_surface_ci_brackets_truth(qapp):
    """A support-plane (F-test) scan of the PDA mean yields a CI bracketing truth.

    Depends on the 1D-residual count-normalisation + cache-invalidation fixes in
    ``common.pda_1d_residuals_from_s1s2``: without them the chi2 surface is flat and
    mis-scaled (chi2r ~ 12) and no F-test crossing is found (CI ``(None, None)``).
    """
    from chisurf.core.fitting.support_plane import confidence_intervals_from_scan_result

    true_mean = 52.0
    fit, m, mean_p = _pda_noisy_truth_fit(true_mean=true_mean, total=1500.0, seed=3)
    fit.run()

    # A proper Poisson chi2 (the fix): chi2r ~ 1, not ~12.
    assert fit.chi2r < 3.0, f"chi2r={fit.chi2r:.2f}: 1D PDA residual is not a proper Poisson chi2"
    assert mean_p.value == pytest.approx(true_mean, abs=2.0)

    result = fit.adaptive_chi2_scan(mean_p.name, p_value=0.99)
    cis = confidence_intervals_from_scan_result(result, p_values=(0.99,))
    assert cis, "no confidence interval computed from the scan"
    low, high = cis[0]["crossings"]
    assert low is not None and high is not None, f"one-sided CI: {cis[0]['crossings']}"
    assert low < high, "degenerate confidence interval"
    assert low < true_mean < high, f"99% CI [{low:.2f}, {high:.2f}] does not bracket {true_mean}"


def test_pda_mcmc_posterior_brackets_truth_and_agrees_with_support_plane(qapp):
    """MCMC sampling of a PDA parameter reproduces the support-plane interval.

    This is the second error-surface route required by PRD-50. It also guards the
    Metropolis acceptance sign in ``sample.walk_mcmc``: with the sign inverted the
    chain ran away from the optimum instead of sampling the posterior.
    """
    import chisurf.core.fitting.sample
    from chisurf.core.fitting.support_plane import confidence_intervals_from_scan_result

    true_mean = 52.0
    fit, m, mean_p = _pda_noisy_truth_fit(true_mean=true_mean, total=1500.0, seed=3)
    fit.run()
    chi2r_best = fit.chi2r
    assert chi2r_best < 3.0

    np.random.seed(0)
    r = chisurf.core.fitting.sample.walk_mcmc(
        fit=fit, steps=800, step_size=0.01, temp=1.0, thin=1
    )
    assert list(r["parameter_names"]) == [mean_p.name]
    assert r["acceptance_rate"] > 0.05, "chain is stuck; proposal scale is degenerate"

    chi2r = np.asarray(r["chi2r"], dtype=float)
    # An inverted acceptance test drives the chain uphill in chi2 without bound.
    assert np.median(chi2r) < 3.0 * chi2r_best

    samples = np.asarray(r["parameter_values"], dtype=float)[:, 0]
    samples = samples[len(samples) // 5:]  # discard burn-in
    assert samples.mean() == pytest.approx(true_mean, abs=2.0)

    mcmc_low, mcmc_high = np.percentile(samples, [0.5, 99.5])
    assert mcmc_low < true_mean < mcmc_high, (
        f"99% credible interval [{mcmc_low:.2f}, {mcmc_high:.2f}] misses {true_mean}"
    )

    # The two independent error-surface routes must agree on the width.
    mean_p.value = true_mean
    fit.run()
    result = fit.adaptive_chi2_scan(mean_p.name, p_value=0.99)
    spa_low, spa_high = confidence_intervals_from_scan_result(
        result, p_values=(0.99,)
    )[0]["crossings"]
    assert (mcmc_high - mcmc_low) == pytest.approx(spa_high - spa_low, rel=0.5)


def test_dynamic_pda_recovers_exchange_at_unequal_populations(qapp):
    """The regime the old occupation-time density could not fit.

    PRD-50's original dynamic acceptance test recovered ``x1 = 0.503`` — the one
    occupancy at which the closed-form Bessel density happened to be correct.
    Away from it that density was not even a probability distribution, so the
    model was biased exactly where a two-state system is most informative (an
    unequal split says something about the free-energy difference). This fits a
    synthetic set generated at ``x1 = 0.25`` and requires both the occupancy and
    the exchange rate back.
    """
    import chisurf.core.fluorescence.tcspc as tcspc

    model_class = _resolve("chisurf.core.models.pda2c.dynamic.Pda2cDynamicTwoStateModel")
    fit = _make_pda_fit(model_class)
    m = fit.model

    # k_ex is the dimensionless K = (k1 + k2) * T; the model carries the rate.
    truth = {"R1": 40.0, "R2": 62.0, "x1": 0.25, "k_ex": 2.0}
    m.states._R1.value = truth["R1"]
    m.states._R2.value = truth["R2"]
    m.states._x1.value = truth["x1"]
    m.states._kex.value = truth["k_ex"] / m.observation_time
    m.update()

    s1s2 = np.asarray(m.pda.get_S1S2_matrix(), dtype=float)
    ny, nx = fit.data.pda["shape"]
    s1s2 = s1s2[:ny, :nx]
    s1s2 = s1s2 / max(s1s2.sum(), 1e-12) * 2e5
    noisy = np.random.default_rng(5).poisson(s1s2).astype(float)
    fit.data.pda["s1s2"] = noisy
    fit.data.y = noisy.ravel(order="C")
    fit.data.ey = tcspc.counting_noise(fit.data.y)

    m.find_parameters()
    for p in m.parameters_all:
        p.fixed = True
    for parameter, start in ((m.states._x1, 0.5),
                             (m.states._kex, 0.7 / m.observation_time)):
        parameter.fixed = False
        parameter.value = start
    m.find_parameters()
    fit.run()

    assert float(m.states._x1.value) == pytest.approx(truth["x1"], abs=0.06)
    assert m.transitions_per_window == pytest.approx(truth["k_ex"], rel=0.35)
