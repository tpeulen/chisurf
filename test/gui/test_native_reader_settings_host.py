"""The current Qt shell can host complete native reader settings without new Qt controls."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from qtpy import QtWidgets

from chisurf.gui.main_helper import SetupMixin


def _main(qtbot, reader):
    """Use the production setup-display method with an isolated existing dock layout."""
    widget = QtWidgets.QWidget()
    qtbot.addWidget(widget)
    widget.resize(760, 480)
    widget.layout_experiment_reader = QtWidgets.QVBoxLayout(widget)
    widget.current_setup = reader
    widget.current_experiment = SimpleNamespace(readers=[reader])
    widget.comboBox_setupSelect = QtWidgets.QComboBox()
    widget.comboBox_setupSelect.addItem("Reader")
    widget.open_context_help_for_reader = lambda: None
    return widget


def _reader():
    """A null-controller reader declaring its own native settings."""
    return SimpleNamespace(
        name="Declared reader", controller=None, gain=3.25,
        view_spec=lambda: {"sections": [{"type": "value", "attr": "gain", "kind": "float",
                                          "label": "Gain", "description": "Acquisition gain."}]},
    )


def test_null_controller_declared_reader_gets_one_reused_native_host(qtbot):
    """Choosing a headless reader shows real controls rather than a blank settings dock."""
    reader = _reader()
    main = _main(qtbot, reader)
    SetupMixin._refresh_setup_ui(main)
    assert main.layout_experiment_reader.count() == 1
    host = main.layout_experiment_reader.itemAt(0).widget()
    assert host.control.model is reader
    assert reader.controller is None
    SetupMixin._refresh_setup_ui(main)
    assert main.layout_experiment_reader.count() == 1
    assert main.layout_experiment_reader.itemAt(0).widget() is host
    assert reader.gain == 3.25
    host.close()
    assert host.control.closed


def test_configured_legacy_controller_is_retained(qtbot):
    """Existing controller ports remain visible until their declared migrations land."""
    controller = QtWidgets.QLabel("Legacy reader controls")
    calls = []
    controller.updateUI = lambda: calls.append("refresh")
    reader = _reader()
    reader.controller = controller
    main = _main(qtbot, reader)
    SetupMixin._refresh_setup_ui(main)
    assert main.layout_experiment_reader.itemAt(0).widget() is controller
    assert calls == ["refresh"]


def test_unsupported_declared_reader_does_not_install_a_partial_host(qtbot):
    """The seam refuses the entire declaration before adding a misleading surface."""
    reader = _reader()
    reader.view_spec = lambda: {"sections": [{"type": "custom", "key": "unregistered"}]}
    main = _main(qtbot, reader)
    with pytest.raises(ValueError, match="unsupported"):
        SetupMixin._refresh_setup_ui(main)
    assert main.layout_experiment_reader.count() == 0


def test_reselecting_a_closed_native_host_replaces_it_without_duplicate_layout_entries(qtbot):
    """Closed hosts release callbacks and cannot leave another hidden settings row behind."""
    main = _main(qtbot, _reader())
    SetupMixin._refresh_setup_ui(main)
    before = main.layout_experiment_reader.itemAt(0).widget()
    before.close()
    SetupMixin._refresh_setup_ui(main)
    assert main.layout_experiment_reader.count() == 1
    after = main.layout_experiment_reader.itemAt(0).widget()
    assert after is not before and not after.control.closed
