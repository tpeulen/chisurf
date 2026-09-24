"""The Qt parameter table creates vectors: Make vector…, Populations…, Make scalar.

ChiSurf's ``ParameterGroupTableWidget`` edits nDXplorer's parameters through
their mirrors; each mirror carries ``population_vector``
(``ndxplorer.core.chisurf_binding.PopulationVectorActions``), so the row's menu
offers what the emtk table's menu does, through the same model calls
(``Parameter.set_populations``, ``Parameter.to_scalar``). Driven here in the ndX
Qt window's constants editor: right-click menu, the dialog, OK.

``CHISURF_TABLE_SHOTS=<dir>`` saves the menu, the dialog and the table there.
"""

from __future__ import annotations

import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")

from qtpy import QtWidgets  # noqa: E402


@pytest.fixture
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def editor(qapp, tmp_path):
    import json

    from ndxplorer.ui.parameter_editor import ParameterEditor

    path = tmp_path / "constants.json"
    path.write_text(json.dumps({"gamma": 0.8, "gG/gR": 0.6, "alpha": 0.05}))
    widget = ParameterEditor(json_file=str(path))
    widget.resize(420, 320)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()


def _names(table):
    model = table.table_model
    return [str(model.index(r, 0).data()).strip() for r in range(model.rowCount())]


def _row(table, text):
    return next(i for i, n in enumerate(_names(table)) if n.endswith(text))


def _action(menu, text):
    return next(a for a in menu.actions() if a.text() == text)


def _settle(qapp):
    import time

    for _ in range(5):
        qapp.processEvents()
        time.sleep(0.02)


def _shot(widget, name):
    folder = os.environ.get("CHISURF_TABLE_SHOTS")
    if folder:
        pathlib.Path(folder).mkdir(parents=True, exist_ok=True)
        widget.grab().save(str(pathlib.Path(folder) / f"{name}.png"))


def test_make_vector_populations_and_make_scalar_from_the_menu(qapp, editor):
    table = editor._table
    group = editor._group
    menu = table.context_menu(_row(table, "gamma"))
    texts = [a.text() for a in menu.actions()]
    assert "Make vector…" in texts and "Make scalar" not in texts
    menu.popup(table.table_view.viewport().mapToGlobal(table.table_view.rect().center()))
    qapp.processEvents()
    _shot(menu, "qt_menu_make_vector")
    menu.hide()

    _action(menu, "Make vector…").trigger()
    dialog = table._populations_dialog
    assert dialog.isVisible() and dialog.populations.text() == "2"
    dialog.populations.setText("HF, LF")
    dialog.column.setCurrentText("Population")
    _shot(dialog, "qt_populations_dialog")
    dialog.accept()
    qapp.processEvents()
    gamma = group.get("gamma")
    assert gamma.is_vector and gamma.populations == ["HF", "LF"]
    assert [e.value for e in gamma.elements] == pytest.approx([0.8, 0.8])
    assert gamma.vector_state()["column"] == "Population"
    names = _names(table)
    assert any(n.endswith("gamma [2]") for n in names)       # the table follows, opened
    assert any(n.endswith("HF") for n in names) and any(n.endswith("LF") for n in names)
    _settle(qapp)
    # sized to every row once the dialog is gone (no row cut off)
    view = table.table_view
    assert view.height() >= sum(view.rowHeight(r) for r in range(len(names)))
    _shot(editor, "qt_table_after_make_vector")

    # a vector's own menu: Populations… (three now) and Make scalar
    vector_menu = table.context_menu(_row(table, "gamma [2]"))
    assert {"Populations…", "Make scalar"} <= {a.text() for a in vector_menu.actions()}
    assert "Make vector…" not in {a.text() for a in vector_menu.actions()}
    _action(vector_menu, "Populations…").trigger()
    table._populations_dialog.populations.setText("HF, LF, MF")
    table._populations_dialog.accept()
    assert gamma.populations == ["HF", "LF", "MF"]

    element_menu = table.context_menu(_row(table, "MF"))
    _action(element_menu, "Make scalar").trigger()
    qapp.processEvents()
    assert not gamma.is_vector
    assert not any("[" in n for n in _names(table))


def test_a_bad_population_text_keeps_the_dialog_open(qapp, editor, monkeypatch):
    table = editor._table
    warnings = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning",
                        lambda *a, **k: warnings.append(a[2]))
    _action(table.context_menu(_row(table, "alpha")), "Make vector…").trigger()
    dialog = table._populations_dialog
    dialog.populations.setText(" , ")
    dialog.accept()
    assert warnings and dialog.isVisible()
    assert not editor._group.get("alpha").is_vector
    dialog.reject()
