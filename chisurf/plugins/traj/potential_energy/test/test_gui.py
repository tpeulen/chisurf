"""GUI/widget tests for the AutoForm-backed Potential-Energy calculator."""

import pytest
from qtpy import QtCore, QtWidgets


def test_potential_energy_creation(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.potential_energy.widget import PotentialEnergyWidget

    widget = PotentialEnergyWidget()
    qtbot.addWidget(widget)
    assert isinstance(widget, QtWidgets.QWidget)
    # AutoForm-backed: a Qt-free view-model drives a single AutoForm.
    assert hasattr(widget, "model")
    assert hasattr(widget, "auto_form")


def test_widget_properties_delegate_to_model(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.potential_energy.widget import PotentialEnergyWidget

    widget = PotentialEnergyWidget()
    qtbot.addWidget(widget)
    widget.trajectory_file = "/data/example.h5"
    widget.model.stride = 5
    widget.model.selected_potential_index = 0
    assert widget.trajectory_file == "/data/example.h5"
    assert widget.stride == 5
    assert widget.potential_number == 0
    assert widget.potential_name  # a non-empty name from potentialDict


def test_form_renders_with_live_log(qapp, qtbot):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.potential_energy.widget import PotentialEnergyWidget

    widget = PotentialEnergyWidget()
    qtbot.addWidget(widget)
    widget.resize(520, 460)
    widget.show()
    qapp.processEvents()

    # The AutoForm built a non-trivial section tree...
    assert widget.auto_form.findChildren(QtWidgets.QWidget)
    # ...including the custom setup section's combo, weight and buttons...
    assert widget.auto_form.findChildren(QtWidgets.QComboBox)
    assert widget.auto_form.findChildren(QtWidgets.QToolButton)
    # ...the potentials table...
    assert widget.auto_form.findChildren(QtWidgets.QTableWidget)
    # ...and the live log (info section bound to log_html) shows the initial entry.
    browsers = widget.auto_form.findChildren(QtWidgets.QTextBrowser)
    assert browsers
    assert any("Ready" in b.toPlainText() for b in browsers)

    # The whole widget paints headlessly without Qt errors.
    pixmap = widget.grab()
    assert not pixmap.isNull()
    assert pixmap.width() > 0 and pixmap.height() > 0


def test_add_button_appends_potential(qapp, qtbot):
    """Functional GUI-interaction test: drive the real combo + Add button.

    Exercises the actual Qt section (not the model directly): select a potential
    in the combo, click the Add tool button, and assert the model's universe /
    table grew and the table row count increased.
    """
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.potential_energy.widget import PotentialEnergyWidget

    widget = PotentialEnergyWidget()
    qtbot.addWidget(widget)
    widget.show()
    qapp.processEvents()

    combos = widget.auto_form.findChildren(QtWidgets.QComboBox)
    assert combos
    combo = combos[0]
    tables = widget.auto_form.findChildren(QtWidgets.QTableWidget)
    assert tables
    table = tables[0]

    # Pick "Radius of Gyration" (a simple, dependency-free potential).
    names = widget.model.potential_names()
    target = "Radius of Gyration"
    assert target in names
    combo.setCurrentIndex(names.index(target))
    qapp.processEvents()

    # Locate the real "Add" tool button and click it.
    add_buttons = [
        b for b in widget.auto_form.findChildren(QtWidgets.QToolButton) if "Add" in b.text()
    ]
    assert add_buttons, "the setup section must expose an Add button"

    rows_before = table.rowCount()
    n_before = len(widget.model.universe.potentials)

    qtbot.mouseClick(add_buttons[0], QtCore.Qt.LeftButton)
    qapp.processEvents()

    # The model's universe and table records gained an entry...
    assert len(widget.model.universe.potentials) == n_before + 1
    added = widget.model.added_potentials()
    assert added[-1]["name"] == target
    # ...and the rendered table row count increased.
    assert table.rowCount() == rows_before + 1
