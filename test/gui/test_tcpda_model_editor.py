"""tcPDA reaches the GUI: reader, model, editor and fit (PRD-65).

Exercises the seam the ``test-model-editor`` skill covers — a model is only
usable if it is registered, its dataset loads, ``build_model_editor`` renders it
without empty groups, and ``fit.run()`` moves the right parameters. A model that
computes but cannot be opened is not a feature.
"""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _simulated_fit(correlation: float = 0.0, n_bursts: int = 1500, seed: int = 3):
    """Return a Fit over a simulated three-colour burst table."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.tcpda import TcPdaModel

    reader = Pda3cSimulatorReader(
        n_bursts=n_bursts, correlation=correlation, seed=seed,
        r_gr=52.0, r_bg=46.0, r_br=68.0, sigma=6.0,
    )
    data = reader.read()[0]
    return fit_mod.Fit(model_class=TcPdaModel, data=data)


# ── registration ───────────────────────────────────────────────────────────


def test_the_experiment_type_and_model_are_registered():
    """It has to be reachable from the add-fit flow, not just importable."""
    import pathlib

    import yaml

    config = yaml.safe_load(
        pathlib.Path("chisurf/core/settings/experiment_configs.yaml").read_text()
    )
    assert "pda3c" in config["experiment_types"]
    assert config["experiment_types"]["pda3c"]["hidden"] is False

    block = config["pda3c"]
    readers = [r["reader_class"] for r in block["readers"]]
    assert "chisurf.core.experiments.pda3c.Pda3cSimulatorReader" in readers
    assert "chisurf.core.experiments.pda3c.Pda3cBurstTableReader" in readers
    assert "chisurf.core.models.pda3c.tcpda.TcPdaModel" in block["models"]


# ── the reader ─────────────────────────────────────────────────────────────


def test_the_simulator_reader_produces_a_usable_dataset():
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader

    group = Pda3cSimulatorReader(n_bursts=500, seed=7).read()
    assert len(group) == 1
    curve = group[0]

    payload = curve.meta_data["pda3c"]
    assert payload["blue"].shape == (500, 3)
    assert payload["green"].shape == (500, 2)
    assert payload["n_bursts"] == 500
    # The plotted curve is the three measured ratio histograms.
    assert curve.y.size == 3 * 41
    assert np.all(np.isfinite(curve.y)) and curve.y.sum() > 0


def test_the_burst_table_reader_round_trips(tmp_path):
    from chisurf.core.experiments.pda3c import Pda3cBurstTableReader, Pda3cSimulatorReader

    original = Pda3cSimulatorReader(n_bursts=300, seed=11).read()[0].meta_data["pda3c"]
    path = tmp_path / "bursts.npz"
    np.savez(path, blue=original["blue"], green=original["green"])

    loaded = Pda3cBurstTableReader().read(str(path))[0].meta_data["pda3c"]
    assert np.array_equal(loaded["blue"], original["blue"])
    assert np.array_equal(loaded["green"], original["green"])


def test_a_text_burst_table_loads(tmp_path):
    from chisurf.core.experiments.pda3c import Pda3cBurstTableReader

    path = tmp_path / "bursts.txt"
    path.write_text("10 5 3 8 4\n12 4 2 9 3\n7 6 5 6 6\n")
    payload = Pda3cBurstTableReader().read(str(path))[0].meta_data["pda3c"]
    assert payload["blue"].shape == (3, 3)
    assert payload["green"].shape == (3, 2)
    assert payload["blue"][0].tolist() == [10.0, 5.0, 3.0]


# ── the editor ─────────────────────────────────────────────────────────────


def test_the_editor_renders_with_real_parameter_rows(qapp):
    from chisurf.core.models import view_spec as vs
    from chisurf.gui.autoform.sections.parameter_table import (
        PairedParameterTableWidget,
        ParameterGroupTableWidget,
    )
    from chisurf.gui.widgets.models.auto_model_widget import AutoModelWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor, model_plot_specs

    fit = _simulated_fit(n_bursts=400)
    model = fit.model

    editor = build_model_editor(model)
    assert isinstance(editor, AutoModelWidget)

    # Species tables: 7 columns of distance parameters, 3 of correlations.
    paired = editor.findChildren(PairedParameterTableWidget)
    widths = sorted(t.table_model.width for t in paired)
    assert widths == [3, 7], widths
    assert all(t.table_model.rowCount() == 1 for t in paired)

    # The instrument group must not render as an empty box.
    flat = editor.findChildren(ParameterGroupTableWidget)
    assert sum(t.table_model.rowCount() for t in flat) >= 16

    spec = model.view_spec()
    for section in spec.flat_sections():
        if isinstance(section, (vs.ParameterGroupSection, vs.ParameterGroupTableSection)):
            group = getattr(model, section.target)
            if hasattr(group, "find_parameters") and not list(group.parameters_all):
                group.find_parameters()
            assert list(group.parameters_all), f"group {section.target!r} is empty"

    assert model_plot_specs(model), "no plot specs resolved"


def test_adding_a_species_adds_one_row_to_both_tables(qapp):
    from chisurf.gui.autoform.sections.parameter_table import PairedParameterTableWidget
    from chisurf.gui.widgets.models.model_editor import build_model_editor

    fit = _simulated_fit(n_bursts=200)
    editor = build_model_editor(fit.model)

    fit.model.species.append()
    for table in editor.findChildren(PairedParameterTableWidget):
        table.set_params(
            fit.model.species._distance_parameter_rows()
            if table.table_model.width == 7
            else fit.model.species._correlation_parameter_rows()
        )
        assert table.table_model.rowCount() == 2


def test_the_model_computes_a_finite_curve(qapp):
    fit = _simulated_fit(n_bursts=400)
    fit.model.update()
    y = np.asarray(fit.model.y)
    assert y.size == 3 * 41
    assert np.all(np.isfinite(y)) and y.sum() > 0


# ── the objective ──────────────────────────────────────────────────────────


def test_the_residual_is_the_likelihood_in_disguise(qapp):
    """sum(wres**2) must track -2 log L, so least squares *is* MLE here."""
    fit = _simulated_fit(n_bursts=600)
    model = fit.model

    def objective_and_likelihood(r_gr):
        model.species.means_of(0)[0].value = r_gr
        model.update()
        wres = np.asarray(model.get_wres(fit), dtype=float)
        return float(np.sum(wres ** 2)), model.total_log_likelihood()

    reference_sum, reference_ll = objective_and_likelihood(52.0)
    moved_sum, moved_ll = objective_and_likelihood(58.0)

    # Constant offset (the saturated term) cancels in the difference.
    assert (moved_sum - reference_sum) == pytest.approx(
        -2.0 * (moved_ll - reference_ll), rel=1e-6
    )
    assert moved_sum > reference_sum, "the wrong distance must cost more"


def test_chi2r_is_finite_stable_and_discriminating(qapp):
    """What chi2r can and cannot be trusted to do for this model.

    It is *not* calibrated to one: the saturated reference has three free cells
    per burst and the per-cell counts are far too small for the usual deviance
    asymptotics, so it settles near 2.4 at the truth. What it must do is be
    finite, be independent of dataset size, and go up when the model is wrong —
    those are the properties that make it usable for comparing fits of the same
    data, and they are what this pins.
    """
    small = _simulated_fit(n_bursts=500, seed=5)
    large = _simulated_fit(n_bursts=2000, seed=5)
    for fit in (small, large):
        fit.model.update()
        fit.model.find_parameters()

    assert np.isfinite(small.chi2r) and small.chi2r > 0
    # Size-independent to within noise: it is a per-observation quantity.
    assert small.chi2r == pytest.approx(large.chi2r, rel=0.25)

    at_truth = large.chi2r
    large.model.species.means_of(0)[0].value = 62.0  # R_GR far from the truth
    large.model.update()
    assert large.chi2r > at_truth, (at_truth, large.chi2r)


# ── the fit ────────────────────────────────────────────────────────────────


@pytest.mark.slow
def test_a_fit_from_the_gui_stack_recovers_the_simulated_distances(qapp):
    """End to end: reader -> model -> fit.run() moves the means back to truth."""
    fit = _simulated_fit(n_bursts=3000, seed=9)
    model = fit.model

    # find_parameters() is what *populates* parameters_all, so fixing has to
    # come after it — doing it first silently fixes nothing.
    model.find_parameters()
    for parameter in model.parameters_all:
        parameter.fixed = True

    means = model.species.means_of(0)
    truth = [52.0, 46.0, 68.0]
    for parameter, start in zip(means, (47.0, 51.0, 62.0)):
        parameter.fixed = False
        parameter.value = start
    model.find_parameters()
    assert [p.name for p in model.parameters] == ["RGR(1)", "RBG(1)", "RBR(1)"]

    fit.run()
    recovered = [float(p.value) for p in means]
    assert np.allclose(recovered, truth, atol=2.5), recovered


# ── stochastic labelling ───────────────────────────────────────────────────


def test_swapped_labels_add_a_mirror_population(qapp):
    """PAM's stochastic-labelling correction is a permutation, not a dropout.

    When the two labelling sites are chemically equivalent, green and red land
    on either one, so a fraction of molecules carries the mirror geometry:
    R(BG) and R(BR) exchanged, R(GR) untouched — it is the distance *between*
    the two swapped dyes. The correlations with GR trade places with each
    other while the BG/BR correlation is unchanged, for the same reason.
    """
    fit = _simulated_fit(n_bursts=200)
    model = fit.model
    species = model.species
    species.means_of(0)[0].value = 55.0   # R_GR
    species.means_of(0)[1].value = 40.0   # R_BG
    species.means_of(0)[2].value = 70.0   # R_BR
    species.correlations_of(0)[0].value = 0.5   # rho(GR,BG)
    species.correlations_of(0)[1].value = -0.2  # rho(GR,BR)
    species.correlations_of(0)[2].value = 0.3   # rho(BG,BR)

    assert len(species.as_species(1.0)) == 1

    pair = species.as_species(0.7)
    assert len(pair) == 2
    normal, mirror = pair
    assert normal.amplitude == pytest.approx(0.7)
    assert mirror.amplitude == pytest.approx(0.3)

    assert normal.means.tolist() == [55.0, 40.0, 70.0]
    assert mirror.means.tolist() == [55.0, 70.0, 40.0]

    def correlation(component, i, j):
        c = component.covariance
        return c[i, j] / np.sqrt(c[i, i] * c[j, j])

    # rho(GR,BG) and rho(GR,BR) swap; rho(BG,BR) does not.
    assert correlation(mirror, 0, 1) == pytest.approx(correlation(normal, 0, 2))
    assert correlation(mirror, 0, 2) == pytest.approx(correlation(normal, 0, 1))
    assert correlation(mirror, 1, 2) == pytest.approx(correlation(normal, 1, 2))


def test_labelling_correction_is_off_by_default_and_free_to_enable(qapp):
    fit = _simulated_fit(n_bursts=200)
    model = fit.model
    assert model.stochastic_labeling is False
    assert model._labeling_weight() == 1.0

    model.stochastic_labeling = True
    model.setup._labeling_fraction.value = 0.6
    assert model._labeling_weight() == pytest.approx(0.6)
    model.update()
    assert np.all(np.isfinite(model.y))


def test_a_symmetric_swap_is_invisible(qapp):
    """With R(BG) == R(BR) the mirror population is the same population.

    A correction that changed the answer here would be changing something other
    than what it claims to.
    """
    fit = _simulated_fit(n_bursts=400)
    model = fit.model
    for parameter, value in zip(model.species.means_of(0), (55.0, 50.0, 50.0)):
        parameter.value = value

    model.update()
    without = np.array(model.y, copy=True)

    model.stochastic_labeling = True
    model.setup._labeling_fraction.value = 0.5
    model.update()
    assert np.allclose(without, model.y)


# ── brightness ─────────────────────────────────────────────────────────────


def test_relative_brightness_is_one_without_transfer():
    """The reference case has to be exactly neutral, or every species shifts."""
    from chisurf.core.fluorescence.pda3c import (
        ThreeColorSetup,
        distances_to_matrix,
        relative_brightness,
    )

    setup = ThreeColorSetup.from_scalars(gamma_bg=0.7, gamma_br=1.4, crosstalk_gr=0.2)
    far = distances_to_matrix([1e9, 1e9, 1e9])
    for laser in (0, 1):
        assert np.ravel(relative_brightness(far, setup, laser))[0] == pytest.approx(1.0)


def test_transfer_towards_a_better_detected_dye_brightens():
    """Brightness is a consequence of the detection matrix, not a free knob."""
    from chisurf.core.fluorescence.pda3c import (
        ThreeColorSetup,
        distances_to_matrix,
        relative_brightness,
    )

    bright_red = ThreeColorSetup.from_scalars(gamma_bg=1.0, gamma_br=2.0)
    dim_red = ThreeColorSetup.from_scalars(gamma_bg=1.0, gamma_br=0.5)
    close = distances_to_matrix([35.0, 35.0, 35.0])

    assert np.ravel(relative_brightness(close, bright_red, 0))[0] > 1.0
    assert np.ravel(relative_brightness(close, dim_red, 0))[0] < 1.0


def test_scaling_a_photon_number_distribution_moves_its_mean():
    from chisurf.core.models.pda3c.tcpda import scale_photon_number_pmf

    counts = np.arange(200.0)
    pmf = np.exp(-0.5 * ((counts - 60.0) / 12.0) ** 2)
    pmf /= pmf.sum()

    assert np.allclose(scale_photon_number_pmf(pmf, 1.0), pmf)
    for factor in (0.5, 1.5):
        scaled = scale_photon_number_pmf(pmf, factor)
        assert scaled.sum() == pytest.approx(1.0)
        assert (scaled @ counts) == pytest.approx(factor * (pmf @ counts), rel=0.02)


def test_brightness_correction_is_off_by_default_and_changes_the_fit(qapp):
    fit = _simulated_fit(n_bursts=600)
    model = fit.model
    assert model.brightness_correction is False

    baseline = model.total_log_likelihood()
    model.brightness_correction = True
    corrected = model.total_log_likelihood()
    assert np.isfinite(corrected)
    # It reweights the species, so it must actually do something.
    assert corrected != pytest.approx(baseline)
