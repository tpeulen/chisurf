"""PDA fit-histogram settings: axis selection, binning, and counting statistic.

Covers :class:`chisurf.core.models.pda.common.PdaFitSettings` and
:func:`~chisurf.core.models.pda.common.pda_weighted_residuals` — the choice of
*which* 1D projection of the S1S2 count matrix a PDA model is fitted against,
and *how* its bins are weighted. The bias test is the reason the default is the
Poisson deviance rather than a chi-square: see PRD-50.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest
from scipy import stats

PDA_VIEW_SPECS = [
    "simple.view.json",
    "pdagauss.view.json",
    "saw_nu.view.json",
    "dynamic.view.json",
    "dynamic_mc.view.json",
    "anisotropy.view.json",
]


def _make_pda_data(nmax: int = 60, nmin: int = 5):
    """Return a DataCurve carrying synthetic, valid ``.pda`` metadata."""
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
    pda = {
        "maximum_number_of_photons": nmax,
        "minimum_number_of_photons": nmin,
        "minimum_time_window_length": 2e-3,
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
        x=np.arange(y.size),
        ey=tcspc.counting_noise(y),
    )


def _gaussian_fit():
    """Return a fit on the Gaussian-distance PDA model over synthetic data."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.pda.pdagauss import PdaGaussianDistanceModel

    return fit_mod.Fit(model_class=PdaGaussianDistanceModel, data=_make_pda_data())


# ── settings object ────────────────────────────────────────────────────────


def test_axis_selection_resets_the_binning_range():
    from chisurf.core.models.pda.common import PdaFitSettings

    s = PdaFitSettings()
    assert s.axis == "S1/(S0+S1)"
    assert s.kw_hist["x_min"] == 0.0 and s.kw_hist["x_max"] == 1.0
    assert s.kw_hist["log_x"] is False

    # A proximity-ratio range is meaningless on a distance axis, so selecting an
    # axis adopts that axis' defaults.
    s.axis = "R"
    assert (s.x_min, s.x_max, s.log_x) == (20.0, 100.0, False)
    s.axis = "S0/S1"
    assert s.log_x is True and s.x_max == 500.0

    # ... but re-selecting the same axis must not clobber a hand-set range.
    s.x_max = 42.0
    s.axis = "S0/S1"
    assert s.x_max == 42.0

    # Unknown names fall back rather than raise (view specs are user-editable).
    s.axis = "not-an-axis"
    assert s.axis == "S1/(S0+S1)"


def test_every_pda_model_carries_editable_fit_settings():
    from chisurf.core.models.pda.common import PdaFitSettings

    fit = _gaussian_fit()
    assert isinstance(fit.model.fit_settings, PdaFitSettings)
    assert fit.model.fit_settings.statistic == "poisson"


# ── the statistics themselves ──────────────────────────────────────────────


def test_statistics_rescale_the_model_to_the_data_counts():
    """The engine returns probabilities; the residual must compare counts."""
    from chisurf.core.models.pda.common import pda_weighted_residuals

    data = np.array([10.0, 20.0, 30.0, 40.0])
    model = data / data.sum()  # same shape, normalised to 1
    for statistic in ("poisson", "neyman", "pearson"):
        w = pda_weighted_residuals(data, model, statistic=statistic)
        assert np.allclose(w, 0.0, atol=1e-9), statistic


def test_poisson_deviance_matches_its_closed_form():
    from chisurf.core.models.pda.common import pda_weighted_residuals

    data = np.array([0.0, 1.0, 5.0, 50.0])
    model = np.array([2.0, 1.0, 4.0, 49.0])
    model = model * (data.sum() / model.sum())

    w = pda_weighted_residuals(data, model, statistic="poisson")
    expected = np.empty_like(data)
    for i, (d, m) in enumerate(zip(data, model)):
        term = m - d + (d * np.log(d / m) if d > 0 else 0.0)
        expected[i] = np.sign(d - m) * np.sqrt(max(2.0 * term, 0.0))
    assert np.allclose(w, expected)
    # Empty bins still constrain the fit: they contribute 2m, not nothing.
    assert abs(w[0]) == pytest.approx(np.sqrt(2.0 * model[0]))


def test_mismatched_shapes_return_empty_rather_than_raising():
    from chisurf.core.models.pda.common import pda_weighted_residuals

    assert pda_weighted_residuals(np.zeros(4), np.zeros(3)).size == 0


# ── axis wiring through the model ──────────────────────────────────────────


@pytest.mark.parametrize("axis", ["S1/(S0+S1)", "E", "S0/S1", "R"])
def test_fitting_on_every_axis_produces_finite_residuals(axis):
    fit = _gaussian_fit()
    m = fit.model
    m.fit_settings.axis = axis
    m.update()
    w = np.asarray(m.get_wres(fit), dtype=float)
    assert w.size > 0, f"axis {axis!r} produced no residuals"
    assert np.all(np.isfinite(w)), f"axis {axis!r} produced non-finite residuals"


def test_the_axis_actually_changes_the_fitted_histogram():
    """A different projection must give a different residual, not a silent no-op.

    Before the axis was wired through, the model stored a ``kw_hist`` that the
    residual ignored — every model fitted the proximity ratio regardless.
    """
    fit = _gaussian_fit()
    m = fit.model
    m.update()
    w_pr = np.asarray(m.get_wres(fit), dtype=float).copy()
    m.fit_settings.axis = "S0/S1"
    w_ratio = np.asarray(m.get_wres(fit), dtype=float)
    assert w_pr.shape == w_ratio.shape
    assert not np.allclose(w_pr, w_ratio)


def test_corrected_axis_rebins_when_gamma_changes():
    """E/R bin through gamma, so the cached data histogram must invalidate."""
    fit = _gaussian_fit()
    m = fit.model
    m.fit_settings.axis = "E"
    m.update()
    w_a = np.asarray(m.get_wres(fit), dtype=float).copy()

    # gamma is a read-only *output* of the detection description, so move one of
    # its inputs (the acceptor quantum yield) the way a user would.
    m.nuisance.QYA = float(m.nuisance.QYA) * 3.0
    m.nuisance.update_correction_factors()
    w_b = np.asarray(m.get_wres(fit), dtype=float)
    assert not np.allclose(w_a, w_b), "gamma change did not re-bin the E axis"


# ── why "poisson" is the default ───────────────────────────────────────────


def _recover_mean(statistic, seed, total=800.0, true_mean=52.0, start=44.0):
    """Fit a Poisson realisation of the model and return the recovered mean."""
    import chisurf.core.fluorescence.tcspc as tcspc

    fit = _gaussian_fit()
    m = fit.model
    m.fit_settings.statistic = statistic
    m.distances._means[0].value = true_mean
    m.distances._sigmas[0].value = 6.0
    m.update()
    _ = m.get_wres(fit)  # installs the histogram function on m.pda

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
    mean_p.bounds = (20.0, 90.0)
    mean_p.bounds_on = True
    mean_p.fixed = False
    mean_p.value = start
    m.find_parameters()
    fit.run()
    return float(mean_p.value)


def test_poisson_deviance_is_less_biased_than_chi_square_at_low_counts():
    """The default statistic earns its place: it is the unbiased one.

    Twenty independent Poisson realisations of the same 800-count histogram are
    fitted for the mean distance with each statistic. The scatter is ~0.27 A, so
    the standard error on the mean of twenty is ~0.06 A: Neyman's offset is many
    standard errors wide and in the direction its low-count weighting predicts
    (bins that fluctuated low get the largest weight), while the deviance sits
    on the truth. Seeds are fixed, so this is deterministic.
    """
    true_mean = 52.0
    seeds = range(1, 21)
    bias = {
        statistic: float(
            np.mean([_recover_mean(statistic, s) for s in seeds]) - true_mean
        )
        for statistic in ("poisson", "neyman")
    }
    assert abs(bias["poisson"]) < 0.1, bias
    assert bias["neyman"] > 0.2, bias
    assert abs(bias["poisson"]) < abs(bias["neyman"]) / 3.0, bias


# ── the editor exposes all of it ───────────────────────────────────────────


@pytest.mark.parametrize("spec_name", PDA_VIEW_SPECS)
def test_view_specs_expose_the_fit_histogram_panel(spec_name):
    spec = json.loads(
        (pathlib.Path("chisurf/core/models/pda") / spec_name).read_text()
    )
    panels = [s for s in spec["sections"] if s.get("title") == "Fit histogram / statistic"]
    assert panels, f"{spec_name} has no fit-histogram panel"
    inner = panels[0]["sections"]

    axis = [s for s in inner if s.get("attr") == "axis"]
    statistic = [s for s in inner if s.get("attr") == "statistic"]
    binning = [s for s in inner if s.get("key") == "scalar_table"]
    assert axis and statistic and binning, spec_name
    assert axis[0]["target"] == "fit_settings"
    # The offered axes must be ones the residual can actually build.
    from chisurf.core.models.pda.common import PDA_AXES, PDA_STATISTICS

    assert set(axis[0]["options"]) <= set(PDA_AXES)
    assert set(statistic[0]["options"]) == set(PDA_STATISTICS)
    assert len(axis[0]["labels"]) == len(axis[0]["options"])


@pytest.mark.parametrize("spec_name", PDA_VIEW_SPECS)
def test_component_groups_render_as_tables(spec_name):
    """Species/component groups use the paired table, not a spin-box grid."""
    spec = json.loads(
        (pathlib.Path("chisurf/core/models/pda") / spec_name).read_text()
    )

    def walk(sections):
        for s in sections:
            if s.get("type") == "dynamic_group":
                yield s
            yield from walk(s.get("sections", []))

    for section in walk(spec["sections"]):
        assert section.get("style") == "table", f"{spec_name}: {section['target']}"


def test_fit_settings_panel_builds_real_widgets(qtbot):
    """The declarative panel must resolve to live, bound controls."""
    from chisurf.gui.autoform.sections.builtin import ChoiceWidget
    from chisurf.gui.autoform.sections.scalar_table_section import ScalarTableWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit = _gaussian_fit()
    editor = build_model_editor(fit.model)
    qtbot.addWidget(editor)

    labels = {c._section.label for c in editor.findChildren(ChoiceWidget)}
    assert {"Axis", "Statistic"} <= labels
    assert editor.findChildren(ScalarTableWidget), "binning table did not render"

    # The combo commits through to the model (the binding, not just the layout).
    axis_combo = [
        c for c in editor.findChildren(ChoiceWidget) if c._section.label == "Axis"
    ][0]
    axis_combo.combo.setCurrentIndex(axis_combo._options.index("R"))
    assert fit.model.fit_settings.axis == "R"
    assert fit.model.fit_settings.x_max == 100.0
