"""The MFD experiment, its models, and the plot — driven headlessly end to end.

Construction tests only prove nothing crashed. What these add is the seam checks
that a screenshot cannot automate: that the experiment registers *additively*, that
the models appear only where they apply, that nothing falls through the chiplot
seam to pyqtgraph, and that the model refuses to report uncertainties its own
scoring source cannot support.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
ANALYSIS = (
    REPO
    / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
    / "burstwise_All 0.1000#15"
)

pytestmark = pytest.mark.skipif(
    not ANALYSIS.is_dir(), reason="the bh_spc132_sm_dna burst folder is not present"
)


@pytest.fixture(scope="module")
def experiments():
    """Register every experiment once, without Qt widget readers."""
    import chisurf as cs
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    ensure_experiments_registered(allow_widgets=False, force=True)
    return cs.experiment


@pytest.fixture(scope="module")
def dataset(experiments):
    """Return the burst folder loaded through the MFD reader."""
    reader = experiments["MFD"].readers[0]
    group = reader.get_data(filename=str(ANALYSIS))
    return group[0]


@pytest.fixture(scope="module")
def fit(dataset):
    """Return a fit of the static model at the milestone-1a optimum."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.mfd import Mfd2DModel

    fit = Fit(
        model_class=Mfd2DModel,
        data=dataset,
        xmin=0,
        xmax=int(dataset.y.size),
        noise_model="poisson",
    )
    model = fit.model
    model.calibration._tau_d0.value = 1.569
    model.calibration._alpha.value = 0.0296
    model.state_group._distances[0].value = 54.42
    model.state_group._donor_only.value = 0.394
    model.update_model()
    return fit


# ──────────────────────────────────────────────────────────────────────────────
# Registration is additive
# ──────────────────────────────────────────────────────────────────────────────
def test_the_mfd_experiment_appears_with_its_reader_and_models(experiments):
    """A new experiment, registered without disturbing anything."""
    assert "MFD" in experiments
    mfd = experiments["MFD"]
    assert [type(r).__name__ for r in mfd.readers] == ["MfdReader"]
    assert [c.__name__ for c in mfd.get_model_classes()] == [
        "Mfd2DModel",
        "Mfd2DKineticModel",
    ]


def test_every_other_experiment_still_lists_its_own(experiments):
    """The one acceptance a purely additive change must still be checked against.

    Merging a user's experiment config *replaces* lists rather than extending them,
    so an addition that went in the wrong place would empty someone else's readers
    rather than fail.
    """
    for name, minimum_readers in (
        ("TCSPC", 3), ("PDA", 3), ("FCS", 8), ("DEER", 1), ("PCH", 1)
    ):
        assert len(experiments[name].readers) >= minimum_readers, name
    assert experiments["PDA"].get_model_names()
    assert experiments["FCS"].get_model_names()


def test_models_are_filtered_by_the_dataset_not_by_a_parallel_list(dataset, experiments):
    """``supports_data`` is the mechanism, so a non-MFD dataset gets nothing."""
    from chisurf.core.models.mfd import Mfd2DKineticModel, Mfd2DModel

    assert Mfd2DModel.supports_data(dataset)
    assert Mfd2DKineticModel.supports_data(dataset)
    # No payload, no MFD model. A plain curve is exactly that case.
    import chisurf.core.data

    plain = chisurf.core.data.DataCurve(
        x=np.arange(10.0), y=np.ones(10), load_filename_on_init=False
    )
    assert not Mfd2DModel.supports_data(plain)
    # `None` means "list everything", which is what an empty model combobox needs.
    assert Mfd2DModel.supports_data(None)


# ──────────────────────────────────────────────────────────────────────────────
# The dataset
# ──────────────────────────────────────────────────────────────────────────────
def test_the_dataset_carries_its_grid_and_its_exclusions(dataset):
    """A flattened 2D histogram, with the shape recorded for the generic machinery."""
    grid = dataset.meta_data["grid"]
    assert grid["ndim"] == 2
    assert grid["shape"] == (41, 41)
    assert int(dataset.y.size) == grid["size"] == 41 * 41
    meta = dataset.meta_data["mfd"]
    assert meta["n_bursts"] == 2980
    assert 0.0 < meta["excluded_fraction"] < 1.0
    assert set(meta["background_rates"]) == {"green", "red"}
    # Empty bins carry unit error rather than zero: a bin the data left empty is
    # information, and a zero error is either infinite weight or a silent drop.
    assert np.all(dataset.ey > 0)


def test_a_missing_folder_yields_an_empty_group(experiments, tmp_path):
    """A path that is not there is not a crash and not a fabricated dataset."""
    reader = experiments["MFD"].readers[0]
    assert len(reader.read(filename=str(tmp_path / "nope"))) == 0
    assert len(reader.read(filename=None)) == 0


# ──────────────────────────────────────────────────────────────────────────────
# The model
# ──────────────────────────────────────────────────────────────────────────────
def test_the_model_computes_and_matches_the_data_total(fit, dataset):
    """The model produces a histogram of the right shape, scaled to the data."""
    model = fit.model
    assert model.y.shape == dataset.y.shape
    assert float(model.y.sum()) == pytest.approx(float(dataset.y.sum()), rel=1e-9)
    assert np.all(np.isfinite(model.y))
    assert 0.5 < fit.chi2r < 5.0


def test_uncertainties_are_refused_rather_than_quietly_reported(fit):
    """The M-estimator rule, enforced in code instead of in a footnote."""
    with pytest.raises(RuntimeError, match="M-estimator"):
        fit.model.parameter_uncertainties()


def test_the_kinetic_model_resizes_its_states_and_rates_together(dataset):
    """A rate matrix that disagrees with the state count is a latent broadcast bug."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.mfd import Mfd2DKineticModel

    fit = Fit(
        model_class=Mfd2DKineticModel,
        data=dataset,
        xmin=0,
        xmax=int(dataset.y.size),
        noise_model="poisson",
    )
    model = fit.model
    assert model.n_states == 2
    assert np.asarray(model.kinetics.rate_matrix()).shape == (2, 2)
    model.n_states = 3
    assert model.state_group.n_states == 3
    assert np.asarray(model.kinetics.rate_matrix()).shape == (3, 3)
    assert len(model.state_names) == 3
    model.update_model()
    assert np.all(np.isfinite(model.y))


def test_view_specs_load(fit, dataset):
    """Both view specs parse, and name plot keys that are actually registered."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.mfd import Mfd2DKineticModel
    from chisurf.gui.autoform.sections.registry import get_plot_class

    kinetic = Fit(
        model_class=Mfd2DKineticModel, data=dataset, xmin=0, xmax=int(dataset.y.size)
    ).model
    for model in (fit.model, kinetic):
        spec = model.view_spec()
        assert spec is not None
        keys = [p.key if hasattr(p, "key") else p["key"] for p in spec.plots]
        assert "mfd_2d" in keys
        for key in keys:
            assert get_plot_class(key) is not None, key


# ──────────────────────────────────────────────────────────────────────────────
# The plot
# ──────────────────────────────────────────────────────────────────────────────
def test_the_plot_draws_with_nothing_falling_through_the_chiplot_seam(fit, qapp):
    """Pyqtgraph is a backend behind chiplot, and a passthrough is a silent bug.

    Anything chiplot lacks falls *through* to pyqtgraph with a warning rather than
    failing, so the migration only finishes if new code is held to producing none.
    """
    from chisurf.gui import chiplot as cp
    from chisurf.gui.plots.mfd_2d import Mfd2DPlot

    cp.reset_gaps()
    plot = Mfd2DPlot(fit)
    plot.resize(1100, 700)
    plot.update_all()
    qapp.processEvents()
    assert sorted(cp.passthrough_gaps()) == []


def test_the_plot_shows_the_axes_the_histogram_was_binned_on(fit, qapp):
    """The panels must span the whole proximity-ratio range, not the model's own.

    Every ``set_data`` re-triggers the renderer's auto-range, so a range set before
    the curves are drawn is silently replaced by whichever curve is drawn last —
    which once left the proximity axis stopping at 0.43.
    """
    from chisurf.gui.plots.mfd_2d import Mfd2DPlot

    plot = Mfd2DPlot(fit)
    plot.resize(1100, 700)
    plot.update_all()
    qapp.processEvents()

    for panel in (plot.data_plot, plot.model_plot, plot.marginal_plot):
        x_range = panel.get_range()[0]
        assert x_range[0] == pytest.approx(0.0, abs=1e-6)
        assert x_range[1] == pytest.approx(1.0, abs=1e-6)


def test_the_plot_reports_what_the_histogram_excluded(fit, qapp):
    """The status line must not let a 45%-excluded histogram look complete."""
    from chisurf.gui.plots.mfd_2d import Mfd2DPlot

    plot = Mfd2DPlot(fit)
    plot.update_all()
    text = plot.status.text()
    assert "2980" in text and "excluded" in text
    assert "population fractions" in text


def test_no_module_here_imports_pyqtgraph_directly():
    """The seam guard, applied to the modules this change added."""
    for relative in (
        "chisurf/gui/plots/mfd_2d.py",
        "chisurf/core/experiments/mfd/reader.py",
        "chisurf/core/models/mfd/two_dimensional.py",
    ):
        source = (REPO / relative).read_text(encoding="utf-8")
        assert "import" + " pyqtgraph" not in source, relative
