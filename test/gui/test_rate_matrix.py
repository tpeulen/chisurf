"""Tests for the reusable AutoForm rate_matrix section + button_row menu mode."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class _Model:
    def __init__(self):
        self.n = 2
        self.k = [0.0, 0.0, 0.0, 0.0]
        self.labels = ["A", "B", "C"]

    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec({
            "sections": [
                {"type": "custom", "key": "rate_matrix", "target": "k",
                 "options": {"size_attr": "n", "labels_attr": "labels",
                             "minimum": 0.0, "decimals": 3, "unit": "1/ms"}},
                {"type": "button_row", "menu": "🛠 Tools",
                 "buttons": [{"label": "🧪 Go", "action": "go"},
                             {"label": "💾 Save", "action": "save"}]},
            ]
        })

    def go(self):
        self.went = True

    def save(self):
        self.saved = True


def test_rate_matrix_edits_and_resizes(qapp):
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget

    m = _Model()
    form = AutoForm(m)
    w = form.findChild(RateMatrixWidget)
    assert w is not None and w.table.rowCount() == 2
    # Off-diagonal edit flows to the flat row-major model list; diagonal fixed at 0.
    w._spins[(0, 1)].setValue(1.5)
    assert m.k[1] == 1.5
    assert not w._spins[(0, 0)].isEnabled()
    # Resizes when the size attribute grows.
    m.n = 3
    w.refresh()
    assert w.table.rowCount() == 3 and len(m.k) == 9


def test_button_row_menu_mode(qapp):
    from qtpy import QtWidgets

    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.builtin import ButtonRowWidget

    m = _Model()
    form = AutoForm(m)
    brw = form.findChild(ButtonRowWidget)
    tool = brw.findChild(QtWidgets.QToolButton)
    assert tool is not None and tool.menu() is not None
    labels = [a.text() for a in tool.menu().actions()]
    assert labels == ["🧪 Go", "💾 Save"]
    tool.menu().actions()[0].trigger()
    assert getattr(m, "went", False) is True
