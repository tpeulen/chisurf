"""Smoke tests for the molecule-wise MLE AutoForm GUI."""

import pytest


def test_view_model_is_qt_free_and_binds_settings():
    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    vm = MoleculeMleViewModel()
    # Scalar bindings proxy the core settings.
    vm.tau = 3.0
    assert vm.settings.tau == 3.0
    vm.detector_chs_text = "2 0"
    assert vm.settings.detector_chs == [2, 0]
    vm.mtr_start, vm.mtr_stop = 5, 200
    assert vm.settings.micro_time_range == (5, 200)
    # No results yet → empty accessors.
    assert vm.segmentation_image() is None
    assert vm.molecule_entries() == []
    assert vm.current_molecule_marker() == []
    ok, reason = vm.can_run()
    assert not ok and reason


def test_view_spec_loads():
    from chisurf.plugins.microscopy.sm_image_mle.gui.view_model import MoleculeMleViewModel

    spec = MoleculeMleViewModel().view_spec()
    assert spec is not None
    assert spec.sections


def test_tool_creation(qapp, qtbot):
    pytest.importorskip("pyqtgraph")
    from chisurf.plugins.microscopy.sm_image_mle.gui.tool import SmImageMleTool

    widget = SmImageMleTool()
    qtbot.addWidget(widget)
    assert widget.windowTitle() == "Molecule-wise MLE"
    assert hasattr(widget, "auto_form")
    assert hasattr(widget, "model")
