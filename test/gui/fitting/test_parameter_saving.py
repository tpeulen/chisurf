"""Every control on the photon-filter page must reach ``get_burst_selection_parameters``.

Two of these values moved: ``photon_threshold`` and ``max_gap`` are now read
from the Qt-free :class:`FilterSettings` model, and the old Designer spin boxes
(``spinBox`` / ``spinBox_7``) are a *mirror* the page writes to and never reads
back. Setting the spin box therefore no longer configures anything -- this test
was asserting 100 and getting the default 60 -- so the migrated values are set
on the model here, and the rest stay on the widgets that still own them.
"""

from chisurf.gui.widgets.wizard.tttr_photonfilter import WizardTTTRPhotonFilter


def test_parameter_collection(qtbot):
    windows = {}
    detectors = {}

    widget = WizardTTTRPhotonFilter(windows=windows, detectors=detectors)
    qtbot.addWidget(widget)

    widget.filter_settings.min_photons = 100
    widget.filter_settings.merge_gap = 5
    widget.doubleSpinBox.setValue(2.0)
    widget.checkBox.setChecked(True)
    widget.checkBox_4.setChecked(True)
    widget.checkBox_5.setChecked(True)
    widget.doubleSpinBox_4.setValue(1.5)
    widget.spinBox_6.setValue(50)
    widget.lineEdit_4.setText("1,2,3")
    widget.spinBox_5.setValue(8)

    params = widget.get_burst_selection_parameters()

    assert params["photon_threshold"] == 100
    assert params["count_rate_window_ms"] == 2.0
    assert params["invert_filter"]
    assert params["filter_active"]
    assert params["use_gap_fill"]
    assert params["max_gap"] == 5
    assert params["trace_bin_width"] == 1.5
    assert params["number_of_burst_bins"] == 50
    assert params["channels"] == [1, 2, 3]
    assert params["decay_coarse"] == 8
