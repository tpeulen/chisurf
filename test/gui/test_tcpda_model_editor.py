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
