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
    # The milestone-1a optimum, re-derived after the instrument response stopped
    # being taken as the raw non-burst histogram. ``tau_d0`` was 1.569 ns while
    # that histogram's fluorescent tail sat in the response; it is the one
    # parameter degenerate with the response's first moment, so it had absorbed
    # the error. Kept in step with ``test_mfd_milestone.FITTED``.
    model.calibration._tau_d0.value = 2.757
    model.calibration._alpha.value = 0.02793
    model.state_group._distances[0].value = 54.55
    model.state_group._donor_only.value = 0.3956
    model.update()
    return fit


# ──────────────────────────────────────────────────────────────────────────────
# Registration is additive
# ──────────────────────────────────────────────────────────────────────────────
def test_the_mfd_experiment_appears_with_its_reader_and_models(experiments):
    """A new experiment, registered without disturbing anything."""
    assert "MFD" in experiments
    mfd = experiments["MFD"]
    assert [type(r).__name__ for r in mfd.readers] == ["MfdReader"]
    # One model, not two: a static analysis is the special case of a kinetic one
    # with no exchange, so splitting them would make the user choose before the
    # data has told them which it is.
    assert [c.__name__ for c in mfd.get_model_classes()] == ["Mfd2DModel"]


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
    from chisurf.core.models.mfd import Mfd2DModel

    assert Mfd2DModel.supports_data(dataset)
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


def test_one_model_covers_static_and_kinetic(dataset):
    """A fresh model is static, and the same model becomes kinetic when asked.

    The shared rate-matrix group defaults its rates to 100 Hz, which would mean
    every MFD fit began with exchange nobody asked for — at a rate that is neither
    slow nor fast for a typical burst, so it would visibly move the answer. An
    empty scheme means *no exchange*, and is mapped to ``None`` rather than handed
    to the occupation-time law, whose all-zero generator has no well-defined
    equilibrium and would return uniform populations over the fitted ones.
    """
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
    assert model.exchange_rate_matrix() is None, "a fresh model must be static"

    # Distinct states, or exchange between two identical ones would correctly
    # change nothing and the test would pass for the wrong reason.
    model.state_group._distances[0].value = 40.0
    model.state_group._distances[1].value = 70.0
    model.update()
    static = np.array(model.y, copy=True)

    rates = list(model.rate_values)
    n = model.n_states
    rates[0 * n + 1] = 800.0
    rates[1 * n + 0] = 800.0
    model.rate_values = rates
    assert model.exchange_rate_matrix() is not None
    model.update()
    assert not np.allclose(static, model.y), "exchange did not change the model"


def test_states_and_rates_resize_together(dataset):
    """A rate matrix that disagrees with the state count is a latent broadcast bug."""
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
    assert model.n_states == 2
    assert np.asarray(model.kinetics.rate_matrix()).shape == (2, 2)
    model.n_states = 3
    assert model.state_group.n_states == 3
    assert np.asarray(model.kinetics.rate_matrix()).shape == (3, 3)
    assert len(model.state_names) == 3
    # A new state must not arrive already exchanging.
    assert model.exchange_rate_matrix() is None
    model.update()
    assert np.all(np.isfinite(model.y))


def test_the_summary_lives_in_the_info_plot_not_the_analysis_dock(fit, qapp):
    """It is reference text, and the dock is for the controls being edited.

    Seven rows of burst bookkeeping and a three-line caveat took the top of a
    panel whose actual job is the parameter tables underneath them.
    """
    from chisurf.gui.plots.fitinfo import FitInfo

    spec = fit.model.view_spec()
    kinds = [type(s).__name__ for s in spec.sections]
    assert "InfoSection" not in kinds, "the summary is back in the analysis dock"

    info = FitInfo(fit)
    info.update()
    # Merged into the one report, not floated above it in a widget of its own.
    text = info.textedit.toPlainText()
    assert "Bursts in the folder" in text
    assert "covariance are not valid" in text
    assert not hasattr(info, "model_summary")


def test_a_model_without_a_summary_leaves_the_panel_hidden(qapp):
    """The hook is optional: most models publish nothing and must show nothing."""
    import chisurf.core.data
    import chisurf.core.models.parse
    from chisurf.core.fitting.fit import Fit
    from chisurf.gui.plots.fitinfo import FitInfo

    x = np.linspace(0.0, 5.0, 32)
    plain = Fit(
        model_class=chisurf.core.models.parse.ParseModel,
        data=chisurf.core.data.DataCurve(x=x, y=x ** 2, ey=np.ones_like(x)),
    )
    info = FitInfo(plain)
    info.update()
    text = info.textedit.toPlainText()
    assert "--- Model ---" not in text


def test_the_panel_offers_a_way_back_out_of_a_bad_minimum(fit):
    """Six free parameters over a multi-modal objective can settle anywhere."""
    spec = fit.model.view_spec()
    actions = [
        button.get("action")
        for section in spec.sections
        for button in (getattr(section, "buttons", None) or [])
    ]
    assert "seed_from_data" in actions
    assert callable(getattr(fit.model, "seed_from_data"))


def test_seeding_only_touches_free_parameters(dataset):
    """A value the user fixed is a decision, not a starting point."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.mfd import Mfd2DModel

    fit = Fit(
        model_class=Mfd2DModel, data=dataset, xmin=0, xmax=int(dataset.y.size),
        noise_model="poisson",
    )
    model = fit.model
    model.calibration._alpha.fixed = True
    model.calibration._alpha.value = 0.42
    model.state_group._distances[0].value = 11.0
    model.seed_from_data()
    assert model.calibration._alpha.value == pytest.approx(0.42)
    assert model.state_group._distances[0].value != pytest.approx(11.0)


def test_the_exchange_scheme_is_drawn_like_any_other(fit, qapp):
    """The same diagram the FCS kinetics model gets, on the MFD rate matrix.

    The canvas was written against the FCS saturation model, which nests its
    generator under ``.dark``; a bare ``RateMatrixParameters`` -- the shared,
    fittable kind -- is adapted onto that shape rather than the drawing code
    learning two.
    """
    from chisurf.gui.autoform.sections.registry import get_plot_class
    from chisurf.gui.autoform.sections.state_scheme_section import StateSchemePlot

    spec = fit.model.view_spec()
    keys = [p.key if hasattr(p, "key") else p["key"] for p in spec.plots]
    assert "state_scheme" in keys
    assert get_plot_class("state_scheme") is StateSchemePlot

    model = fit.model
    n = model.n_states
    rates = list(model.rate_values)
    rates[0 * n + 1] = 1500.0   # R1 -> R2
    rates[1 * n + 0] = 900.0    # R2 -> R1
    model.rate_values = rates

    plot = StateSchemePlot(fit, target="kinetics", labels_attr="state_names")
    scheme = plot.scheme_widget._get_saturation()
    assert scheme.n_states == n
    assert list(scheme.state_labels) == list(model.state_names)
    drawn = np.asarray(scheme.dark.rate_matrix())
    # The editor is row -> column ("from i to j" at ``rate_values[i * n + j]``);
    # the generator is K[target, source]. Those are transposes of each other, and
    # a diagram that drew one while the model integrated the other would put
    # every arrow the wrong way round without changing a single number.
    assert drawn[1, 0] == pytest.approx(1500.0), "R1 -> R2 lost its direction"
    assert drawn[0, 1] == pytest.approx(900.0)
    plot.update()


def test_a_plain_rate_scheme_has_no_pumped_transition(fit, qapp):
    """The hardcoded ``0 -> 1`` was the bug the user saw.

    It drew every scheme as though state 0 were a ground state being pumped, so
    a two-state FRET exchange came out with a phantom ``k_exc`` arrow out of R1
    and its real backward rate missing. There is no laser in a rate matrix.
    """
    from chisurf.gui.autoform.sections.state_scheme_section import StateSchemePlot

    plot = StateSchemePlot(fit, target="kinetics", labels_attr="state_names")
    assert plot.scheme_widget._excitation() is None
    assert plot.scheme_widget._get_saturation().excitation_edge is None


def test_a_declared_pumped_transition_is_still_honoured(qapp):
    """The photophysics models rely on it: their laser is not a fitted rate."""
    from chisurf.gui.autoform.sections.state_scheme_section import StateSchemeWidget

    class _Model:
        saturation = None

    widget = StateSchemeWidget(_Model(), target="saturation", excitation_edge=[0, 1])
    assert widget._excitation_edge == (0, 1)


def test_the_preset_toolbar_is_hidden_when_it_would_do_nothing(fit, qapp):
    """A model with no presets got a combo reading "Custom" and two dead buttons."""
    from chisurf.gui.autoform.sections.state_scheme_section import StateSchemePlot

    plot = StateSchemePlot(fit, target="kinetics", labels_attr="state_names")
    combo = plot.scheme_widget.combo_preset
    assert combo.count() == 1
    assert combo.parent().isHidden()


def test_the_scheme_zooms_about_the_pointer(fit, qapp):
    """And hit-testing follows it, or a zoomed node cannot be clicked."""
    from qtpy import QtCore, QtGui

    from chisurf.gui.autoform.sections.state_scheme_section import StateSchemePlot

    plot = StateSchemePlot(fit, target="kinetics", labels_attr="state_names")
    widget = plot.scheme_widget
    assert widget._view.zoom == pytest.approx(1.0)

    anchor = QtCore.QPointF(260.0, 120.0)
    before = widget._scene_pos(anchor)
    event = QtGui.QWheelEvent(
        anchor, anchor, QtCore.QPoint(0, 0), QtCore.QPoint(0, 480),
        QtCore.Qt.NoButton, QtCore.Qt.NoModifier, QtCore.Qt.NoScrollPhase, False,
    )
    widget._on_canvas_wheel(event)
    assert widget._view.zoom > 1.5
    # What was under the pointer is still under the pointer.
    after = widget._scene_pos(anchor)
    assert after.x() == pytest.approx(before.x(), abs=1e-6)
    assert after.y() == pytest.approx(before.y(), abs=1e-6)

    # A scene point maps to canvas and back exactly, so clicks still land.
    widget._init_coords(widget._get_saturation().n_states)
    node = widget._node_coords[0]
    assert widget._scene_pos(widget._transform().map(node)).x() == pytest.approx(node.x())

    low, high = widget.ZOOM_RANGE
    for _ in range(40):
        widget._on_canvas_wheel(event)
    assert widget._view.zoom <= high


def test_the_node_palette_does_not_run_out(qapp):
    """It stopped at four, so every state past the third came out the same orange."""
    from chisurf.gui.autoform.sections.state_scheme_section import _NODE_COLOURS

    assert len(_NODE_COLOURS) >= 6
    assert len(set(_NODE_COLOURS)) == len(_NODE_COLOURS)


def test_the_scheme_adapter_leaves_the_fcs_shape_alone(qapp):
    """A model that already nests its generator must not be wrapped twice."""
    from chisurf.gui.autoform.sections.state_scheme_section import StateSchemeWidget

    class _Dark:
        n_states = 3

        def rate_matrix(self):
            return np.zeros((3, 3))

    class _Saturation:
        dark = _Dark()
        n_states = 3
        state_labels = ["S0", "S1", "T1"]

    class _Model:
        saturation = _Saturation()

    widget = StateSchemeWidget(_Model(), target="saturation")
    assert widget._get_saturation() is _Model.saturation


def test_view_specs_load(fit, dataset):
    """Both view specs parse, and name plot keys that are actually registered."""
    from chisurf.gui.autoform.sections.registry import get_plot_class

    for model in (fit.model,):
        spec = model.view_spec()
        assert spec is not None
        keys = [p.key if hasattr(p, "key") else p["key"] for p in spec.plots]
        assert "mfd_marginals" in keys
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


def test_the_marginal_plot_spans_the_axes_the_histogram_was_binned_on(fit, qapp):
    """Each marginal must span its own whole axis, not the model's support.

    Every ``set_data`` re-triggers the renderer's auto-range, so a range set before
    the curves are drawn is silently replaced by whichever curve is drawn last —
    which once left the proximity axis stopping at 0.43.
    """
    from chisurf.gui.plots.mfd_2d import MfdMarginalPlot

    plot = MfdMarginalPlot(fit)
    plot.resize(900, 620)
    plot.update_all()
    qapp.processEvents()

    ratio_range = plot.ratio_plot.get_range()[0]
    assert ratio_range[0] == pytest.approx(0.0, abs=1e-6)
    assert ratio_range[1] == pytest.approx(1.0, abs=1e-6)
    micro_range = plot.micro_plot.get_range()[0]
    assert micro_range[1] > micro_range[0]


def test_the_2d_residual_is_placed_in_axis_coordinates(fit, qapp):
    """The panel used to be blank, and for two separate reasons.

    A view spec names its accessor as a string, and nothing turned that into a
    callable — so it was called, the ``TypeError`` was swallowed, and the panel
    stayed empty. With that fixed the image was drawn at *pixel* indices while the
    view was ranged to the real axes, so a 41x41 image landed entirely off the side
    of a view showing 0 to 1. Both broke every model supplying axis vectors, not
    just this one.
    """
    from chisurf.gui.autoform.sections.registry import resolve_plot_specs
    from chisurf.gui.plots.residual_image import _resolve_accessor

    assert callable(
        _resolve_accessor(
            "chisurf.core.models.mfd.two_dimensional:get_mfd_residual_image"
        )
    )
    for plot_class, options in resolve_plot_specs(fit.model.view_spec()):
        if plot_class.__name__ != "Residual2DPlot":
            continue
        plot = plot_class(fit, **options)
        plot.resize(700, 500)
        plot.update()
        qapp.processEvents()
        assert plot._image is not None, "the accessor produced no image"
        assert plot._image.shape == (41, 41)
        # Placed where the axes are, so it is actually inside the view.
        view_x = plot._plot_widget.get_range()[0]
        assert view_x[0] < 0.5 < view_x[1]
        return
    raise AssertionError("no Residual2DPlot in the view spec")


def test_what_the_histogram_excluded_is_reported_once(fit, qapp):
    """A 45%-excluded histogram must not look complete -- but say so in one place.

    It was under the marginals *and* in the Info tab. It is fixed for the
    dataset and does not change as the fit runs, so a three-line paragraph under
    the axes only costs the curves the room they were given the tab for.
    """
    from chisurf.gui.plots.fitinfo import FitInfo
    from chisurf.gui.plots.mfd_2d import Mfd2DPlot

    plot = Mfd2DPlot(fit)
    plot.update_all()
    assert not hasattr(plot, "status"), "the summary is back under the curves"

    info = FitInfo(fit)
    info.update()
    text = info.textedit.toPlainText()
    assert "2980" in text and "Excluded" in text


def test_no_module_here_imports_pyqtgraph_directly():
    """The seam guard, applied to the modules this change added."""
    for relative in (
        "chisurf/gui/plots/mfd_2d.py",
        "chisurf/core/experiments/mfd/reader.py",
        "chisurf/core/models/mfd/two_dimensional.py",
    ):
        source = (REPO / relative).read_text(encoding="utf-8")
        assert "import" + " pyqtgraph" not in source, relative


# ──────────────────────────────────────────────────────────────────────────────
# The reader control, and the startup crash it caused
# ──────────────────────────────────────────────────────────────────────────────
def test_every_shipped_reader_can_show_something(qapp):
    """A reader with no controller must not be able to abort the startup.

    Registering an MFD reader without a ``controller_class`` took the *entire*
    splash startup down: ``_refresh_setup_ui`` reached ``None.show()``, the
    ``load_tools`` stage raised, and every later stage — including the QtConsole —
    never ran. The visible symptom was "the console does not show", which points
    nowhere near the cause.

    ``controller_class: null`` is a legitimate configuration that a couple of
    readers already ship, so the fix is both: MFD declares a controller, *and* a
    reader without one is reported and skipped rather than raising.
    """
    import yaml

    config = yaml.safe_load(
        (REPO / "chisurf/core/settings/experiment_configs.yaml").read_text()
    )
    mfd = config["mfd"]["readers"][0]
    assert mfd["controller_class"].endswith("mfd.MFDController")


def test_the_mfd_controller_builds_and_picks_a_folder(qapp):
    """An MFD dataset is a *folder*, so the control must ask for one."""
    from chisurf.core.experiments.mfd import MfdReader
    from chisurf.gui.widgets.experiments.mfd import MFDController

    controller = MFDController(experiment_reader=MfdReader())
    assert controller is not None
    # The one thing it cannot inherit: a directory chooser rather than a file one.
    assert callable(controller.get_filename)
    assert "filename" in dir(controller)
    controller.updateUI()


def test_a_controllerless_reader_is_skipped_not_fatal(qapp, monkeypatch):
    """The guard itself, exercised through the real refresh path."""
    from qtpy import QtWidgets

    from chisurf.gui import main_helper

    class _Bare:
        """A reader that never got a controller."""

        name = "bare reader"
        controller = None

    class _Fake:
        current_experiment = type("E", (), {"readers": [_Bare()]})()
        current_setup = _Bare()
        layout_experiment_reader = QtWidgets.QVBoxLayout()
        comboBox_setupSelect = QtWidgets.QComboBox()
        _current_setup_idx = 0

    fake = _Fake()
    # Must return quietly rather than raising AttributeError on None.show().
    main_helper.SetupMixin._refresh_setup_ui(fake)


def test_the_map_is_a_plot_not_a_form_section(fit, qapp):
    """The map belongs with the plots; the analysis dock is for controls.

    It is still the shared AutoForm image widget — that is what brings the
    colormap and channel selectors, the real-world axes and the rectangle gate —
    just hosted in a plot tab rather than in the model editor.
    """
    from chisurf.gui.autoform.sections.registry import resolve_plot_specs

    spec = fit.model.view_spec()
    keys = [p.key if hasattr(p, "key") else p["key"] for p in spec.plots]
    assert "mfd_map" in keys
    # And *not* among the form sections.
    for section in spec.sections:
        key = getattr(section, "key", None) or getattr(section, "kind", None)
        assert key != "image", "the map should not be in the analysis dock"

    for plot_class, options in resolve_plot_specs(spec):
        if plot_class.__name__ != "MfdMapPlot":
            continue
        plot = plot_class(fit, **options)
        plot.resize(760, 560)
        plot.update()
        qapp.processEvents()
        assert plot.image_widget is not None
        return
    raise AssertionError("no MfdMapPlot in the view spec")


def test_every_map_channel_stays_on_the_real_axes(fit, qapp):
    """Switching channel must not drop the view back to pixel coordinates.

    ``setImage`` resets the view to the image's pixel box, and the extent was
    re-applied only when the *span* changed — so swapping a measured map for a
    residual left the axes reading 0 to 41 with the image a speck in the corner.
    """
    from chisurf.gui.autoform.sections.registry import resolve_plot_specs

    for plot_class, options in resolve_plot_specs(fit.model.view_spec()):
        if plot_class.__name__ != "MfdMapPlot":
            continue
        plot = plot_class(fit, **options)
        plot.resize(760, 560)
        plot.show()
        plot.update()
        qapp.processEvents()
        for channel in fit.model.mfd_image_channels():
            fit.model.set_mfd_image_channel(channel)
            plot.update()
            qapp.processEvents()
            image = fit.model.mfd_image()
            # Row-major for this dock: (⟨t⟩, proximity ratio).
            assert image.shape == (41, 41)
            (x0, x1), (y0, y1) = plot.image_widget._image.getView().viewRange()
            assert x1 - x0 < 2.0, f"{channel}: view fell back to pixel coordinates"
            assert y1 - y0 < 20.0, f"{channel}: view fell back to pixel coordinates"
        return
    raise AssertionError("no MfdMapPlot in the view spec")
