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


def test_the_grid_agrees_with_the_shared_rate_convention(qapp):
    """Typing into row i, column j must move ``k_ij`` and nothing else.

    The grid, the fitting parameters and the burst likelihood each read a rate
    matrix, and a divergence between them is invisible: a permuted scheme is
    still a valid scheme. This drives the real widget against a real
    ``RateMatrixParameters`` and checks the whole chain — cell -> parameter ->
    ``K[target, source]`` -> the shared flat order.
    """
    import numpy as np

    from chisurf.core.fitting.kinetics import RateMatrixParameters
    from chisurf.core.fluorescence.kinetics import rates_from_rate_matrix
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget

    class _Host:
        """Minimal model exposing a scheme the way a fitting model does."""

        def __init__(self):
            self.kinetics = RateMatrixParameters(name="k", n_states=3, default_rate=0.0)

        @property
        def n_states(self):
            return self.kinetics.n_states

        @property
        def rate_values(self):
            return self.kinetics.rate_values

        @rate_values.setter
        def rate_values(self, values):
            self.kinetics.rate_values = values

        def view_spec(self):
            from chisurf.core.dataspec import load_view_spec

            return load_view_spec({
                "sections": [
                    {"type": "custom", "key": "rate_matrix", "target": "rate_values",
                     "options": {"size_attr": "n_states", "minimum": 0.0,
                                 "decimals": 2, "diagonal": False}},
                ]
            })

    host = _Host()
    form = AutoForm(host)
    grid = form.findChildren(RateMatrixWidget)[0]

    # Row 1, column 2 of the grid is k_12: the rate from state 1 to state 2.
    grid.table.cellWidget(0, 1).setValue(250.0)
    grid.table.cellWidget(2, 1).setValue(70.0)      # k_32

    rates = host.kinetics.rates_by_name()
    assert rates["k1_2"].value == pytest.approx(250.0)
    assert rates["k3_2"].value == pytest.approx(70.0)
    assert sum(1 for p in rates.values() if p.value) == 2

    # ... and the matrix the compute layer receives is K[target, source].
    K = host.kinetics.rate_matrix()
    assert K[1, 0] == pytest.approx(250.0)
    assert K[1, 2] == pytest.approx(70.0)
    assert np.array_equal(rates_from_rate_matrix(K), host.kinetics.flat_rates)
