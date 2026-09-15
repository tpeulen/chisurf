"""The fit controller's controls come from a view spec, and still behave.

They were a Qt Designer file whose widgets were called ``spinBox_2`` …
``spinBox_6``. The layout is now ``fitting_controls.view.json``, which is only
an improvement if the controls it renders are the same controls: the same
values reach the fit, the same groups show and hide, and the sampling panel now
also carries the choice between a text chain and an HDF5 one.
"""
import numpy as np
import pytest

import chisurf
import chisurf.core.data
import chisurf.core.fitting.fit as fit_module
import chisurf.core.models.parse

pytest.importorskip("qtpy")


@pytest.fixture
def controller(qtbot):
    """A controller on a small real fit."""
    from chisurf.gui.widgets.fitting import FittingControllerWidget

    rng = np.random.default_rng(0)
    x = np.linspace(0, 10, 512)
    y = 2.0 + 0.5 * x ** 2 + rng.normal(0, 0.5, x.size)
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y))
    data.name = "decay.txt"
    fit = fit_module.FitGroup(
        data=chisurf.core.data.DataGroup([data]),
        model_class=chisurf.core.models.parse.ParseModel,
    )
    fit.fit_range = 0, len(fit.model.y)
    fit.model.func = 'c+a*x**2'
    fit.model.find_parameters()

    widget = FittingControllerWidget(fit=fit)
    qtbot.addWidget(widget)
    return widget


def test_every_control_of_the_designer_file_is_still_there(controller):
    """The names the controller was written against must all resolve.

    They are bound to the widgets AutoForm builds; a spec that renames or drops
    a field would leave one of these ``None`` and the failure would surface
    somewhere else entirely.
    """
    from qtpy import QtWidgets

    expected = {
        'comboBox': QtWidgets.QComboBox,
        'spinBox': QtWidgets.QSpinBox,        # xmax
        'spinBox_2': QtWidgets.QSpinBox,      # xmin
        'spinBox_3': QtWidgets.QSpinBox,      # result index
        'spinBox_4': QtWidgets.QSpinBox,      # xmin2
        'spinBox_6': QtWidgets.QSpinBox,      # xmax2
        'checkBox': QtWidgets.QCheckBox,
    }
    for name, kind in expected.items():
        assert isinstance(getattr(controller, name), kind), name
    for name in ('button_fit', 'button_sample', 'button_auto_fit_range',
                 'button_dataset_select'):
        assert isinstance(getattr(controller, name), QtWidgets.QAbstractButton), name
    assert controller.groupBox is not None


def test_steps_and_runs_come_from_the_settings_not_from_the_panel(controller, monkeypatch):
    """They configure a *run*, not a fit, so they live with the run settings.

    One place to set them, and the same value whether the run is started from
    the panel, a macro or the server.
    """
    settings = chisurf.core.settings.cs_settings['optimization']['sampling']
    monkeypatch.setitem(settings, 'steps', 4321)
    monkeypatch.setitem(settings, 'n_runs', 7)
    assert controller.n_steps == 4321
    assert controller.n_runs == 7


def test_each_sampler_keeps_its_own_settings(controller):
    """Switching sampler must not lose what was set, nor mix the two up.

    They do not take the same knobs: handing one another's to it would be a
    TypeError at the start of a long run.
    """
    from chisurf.gui.widgets.fitting.fitting_controls import OptimizationSettingsModel

    model = OptimizationSettingsModel()
    model.method = 'blocked'
    model.sampler_changed()
    model.step_size = 0.25
    model._remember_sampler_settings()

    model.method = 'slice'
    model.sampler_changed()
    model.std = 0.05

    saved = model.sampling_settings()['samplers']
    assert saved['blocked']['step_size'] == 0.25
    assert saved['slice']['std'] == 0.05
    assert 'std' not in saved['blocked']
    assert 'step_size' not in saved['slice']


def test_the_values_the_fit_reads_round_trip(controller):
    """Setting a control must be visible through the property the fit uses."""
    controller.xmin, controller.xmax = 10, 480
    assert (controller.xmin, controller.xmax) == (10, 480)

    controller.checkBox.setChecked(False)
    assert controller.local_first is False


def test_initial_fit_range_is_loaded_before_the_first_plot(controller):
    """The controls must start from the fit, not from zero-valued placeholders."""
    assert (controller.xmin, controller.xmax) == controller.fit.fit_range
    assert controller.xmax > controller.xmin


def test_action_buttons_have_one_height_and_mcts_is_baby_blue(controller):
    buttons = [
        controller._button(action)
        for action in ("fit", "mcts", "sample", "settings", "auto_range",
                       "select_dataset")
    ]
    assert all(button is not None for button in buttons)
    assert len({button.minimumHeight() for button in buttons}) == 1
    assert buttons[1].objectName() == "button_mcts"

    import pathlib
    qss = pathlib.Path(
        "chisurf/gui/styles/widgets/fitting_buttons.qss"
    ).read_text()
    assert "QToolButton#button_mcts" in qss
    assert "#89cff0" in qss.lower()


def test_the_settings_offer_every_sampler_and_format_that_exists(controller):
    """The selectors are populated by the samplers, not by a list in a file.

    Adding a sampler must make it selectable without anyone editing a combo
    box, so the options are compared against the registry itself.
    """
    from chisurf.core.fitting import sample as sample_module
    from chisurf.gui.widgets.fitting.fitting_controls import OptimizationSettingsModel

    model = OptimizationSettingsModel()
    assert [name for name, _ in model.sampler_options()] == list(sample_module.SAMPLERS)
    assert [name for name, _ in model.chain_format_options()] == list(
        fit_module.CHAIN_FORMATS
    )


def test_each_sampler_advertises_its_own_settings(controller):
    """Choosing a sampler shows what *it* takes, derived from its signature."""
    from chisurf.gui.widgets.fitting.fitting_controls import OptimizationSettingsModel

    model = OptimizationSettingsModel()
    model.method = 'blocked'
    model.sampler_changed()
    blocked = {s['attr'] for s in model._sampler_sections()}
    model.method = 'slice'
    model.sampler_changed()
    slice_ = {s['attr'] for s in model._sampler_sections()}

    assert 'step_size' in blocked and 'step_size' not in slice_
    assert 'tune' in slice_ and 'tune' not in blocked
    # ...and every one of them carries the docstring text as its tooltip.
    assert all(s['description'] for s in model._sampler_sections())


def test_the_settings_are_what_the_run_is_told(controller):
    """A dialog that changed nothing the run reads would be decoration."""
    from chisurf.gui.widgets.fitting.fitting_controls import OptimizationSettingsModel

    model = OptimizationSettingsModel()
    model.method = 'slice'
    model.chain_format = 'hdf5'
    model.sampler_changed()
    values = model.sampling_settings()
    assert values['method'] == 'slice'
    assert values['chain_format'] == 'hdf5'
    assert values['chain_format'] in fit_module.CHAIN_FORMATS


def test_a_second_range_row_hides_its_label_with_its_field(controller):
    """One-dimensional data has no second axis, and no label saying it does.

    Hiding only the editor is what leaves a label pointing at nothing.
    """
    field = controller._field('xmin2')
    assert field is not None
    label = getattr(field, '_autoform_label', None)
    assert label is not None
    assert field.isVisibleTo(controller) == label.isVisibleTo(controller)


def test_the_actions_the_buttons_route_through_still_exist(controller):
    """The buttons trigger actions, so a menu or shortcut can do the same."""
    for name in ('actionFit', 'actionAutoFitRange', 'actionFit_range_changed',
                 'actionChange_dataset', 'actionSelectionChanged',
                 'actionErrorEstimate'):
        assert getattr(controller, name) is not None

    fired = []
    controller.actionFit.triggered.connect(lambda *_a: fired.append(True))
    controller.controls.fit()
    assert fired == [True]


def test_visiting_two_samplers_does_not_poison_the_next_run(controller, tmp_path,
                                                            monkeypatch):
    """The S1 of the review (RF-779), end to end.

    Open the settings, pick one sampler, accept; open them again, pick another,
    accept; sample. The first sampler's knobs must not reach the second, which
    does not take them -- binding them raises ``TypeError`` and the run dies
    before its first step.
    """
    import chisurf.macros.core_fit
    from chisurf.gui.widgets.fitting.fitting_controls import OptimizationSettingsModel

    monkeypatch.setattr(
        chisurf.macros.core_fit, "save_project",
        lambda target_path, project_name="project", **kw: None,
    )

    for method in ('slice', 'ensemble'):
        model = OptimizationSettingsModel()
        model.method = method
        model.sampler_changed()
        settings = chisurf.core.settings.cs_settings['optimization']['sampling']
        monkeypatch.setitem(settings, 'method', method)
        monkeypatch.setitem(settings, 'samplers', model.sampling_settings()['samplers'])

    # Everything the GUI would forward, exactly as onErrorEstimate builds it.
    kw = dict(chisurf.core.settings.cs_settings['optimization']['sampling'])
    kw.pop('steps', None)
    kw.pop('n_runs', None)
    fit_module.sample_fit(
        fit=controller.fit, target_directory=str(tmp_path),
        steps=40, n_runs=1, **kw
    )
    runs = list(tmp_path.iterdir())
    assert len(runs) == 1
    assert list((runs[0] / "chains").iterdir())
