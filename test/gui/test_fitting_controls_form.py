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
        'spinBox_5': QtWidgets.QSpinBox,      # n_runs
        'spinBox_6': QtWidgets.QSpinBox,      # xmax2
        'doubleSpinBox': QtWidgets.QDoubleSpinBox,
        'checkBox': QtWidgets.QCheckBox,
    }
    for name, kind in expected.items():
        assert isinstance(getattr(controller, name), kind), name
    for name in ('button_fit', 'button_sample', 'button_auto_fit_range',
                 'button_dataset_select'):
        assert isinstance(getattr(controller, name), QtWidgets.QAbstractButton), name
    assert controller.groupBox is not None


def test_the_values_the_fit_reads_round_trip(controller):
    """Setting a control must be visible through the property the fit uses."""
    controller.xmin, controller.xmax = 10, 480
    assert (controller.xmin, controller.xmax) == (10, 480)

    controller.doubleSpinBox.setValue(2.5)
    assert controller.n_steps == 2500

    controller.spinBox_5.setValue(4)
    assert controller.n_runs == 4

    controller.checkBox.setChecked(False)
    assert controller.local_first is False


def test_the_sampling_panel_offers_both_chain_formats(controller):
    """The point of the new control: text or HDF5, chosen where sampling starts."""
    combo = controller.comboBox_chain_format
    assert combo is not None
    labels = [combo.itemText(i) for i in range(combo.count())]
    assert any("er4" in text for text in labels)
    assert any("h5" in text or "HDF5" in text for text in labels)


def test_choosing_hdf5_is_what_the_run_is_told(controller):
    """A control nobody reads is decoration."""
    combo = controller.comboBox_chain_format
    for index in range(combo.count()):
        if "h5" in combo.itemText(index) or "HDF5" in combo.itemText(index):
            combo.setCurrentIndex(index)
            break
    assert controller.chain_format == 'hdf5'
    assert controller.chain_format in fit_module.CHAIN_FORMATS


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
