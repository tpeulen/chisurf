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
    grid._spins[(0, 1)].setValue(250.0)
    grid._spins[(2, 1)].setValue(70.0)      # k_32

    rates = host.kinetics.rates_by_name()
    assert rates["k1_2"].value == pytest.approx(250.0)
    assert rates["k3_2"].value == pytest.approx(70.0)
    assert sum(1 for p in rates.values() if p.value) == 2

    # ... and the matrix the compute layer receives is K[target, source].
    K = host.kinetics.rate_matrix()
    assert K[1, 0] == pytest.approx(250.0)
    assert K[1, 2] == pytest.approx(70.0)
    assert np.array_equal(rates_from_rate_matrix(K), host.kinetics.flat_rates)


def test_building_the_grid_never_moves_a_rate_it_cannot_display(qapp):
    """Opening a panel is not an edit, and a spin box is not the model.

    A ``QDoubleSpinBox`` clamps to its range and rounds to its ``decimals``, so
    a grid that writes back what it displays destroys every rate outside the
    configured range — merely rendering the editor moved a 5 MHz rate to the
    1 MHz maximum. Values the grid cannot show survive both the build and a
    later edit of another cell; only the cell the user touched is committed.
    """
    from chisurf.core.dataspec import load_view_spec
    from chisurf.core.fitting.kinetics import RateMatrixParameters
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget

    class _Host:
        """A three-state scheme rendered with the shipped PDA grid options."""

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
            return load_view_spec({
                "sections": [
                    {"type": "custom", "key": "rate_matrix", "target": "rate_values",
                     "options": {"size_attr": "n_states", "minimum": 0.0,
                                 "maximum": 1e6, "decimals": 2, "diagonal": False}},
                ]
            })

    host = _Host()
    rates = host.kinetics.rates_by_name()
    rates["k1_2"].value = 5.0e6         # above the grid's maximum
    rates["k2_1"].value = 2.5e6
    rates["k1_3"].value = 123.456       # finer than the grid's decimals
    before = list(host.rate_values)

    form = AutoForm(host)
    grid = form.findChildren(RateMatrixWidget)[0]
    assert list(host.rate_values) == pytest.approx(before)
    assert host.kinetics.rates_by_name()["k1_2"].value == pytest.approx(5.0e6)
    # The clamped cell still says what it can, and says that it is clamped.
    assert grid._spins[(0, 1)].value() == pytest.approx(1.0e6)
    assert "outside the range" in grid._spins[(0, 1)].toolTip()
    # A cell that merely rounds is not flagged — that is what a grid does.
    assert "outside the range" not in grid._spins[(0, 2)].toolTip()

    # Editing one cell commits that cell only.
    grid._spins[(2, 1)].setValue(70.0)      # k_32
    after = host.kinetics.rates_by_name()
    assert after["k3_2"].value == pytest.approx(70.0)
    assert after["k1_2"].value == pytest.approx(5.0e6)
    assert after["k2_1"].value == pytest.approx(2.5e6)
    assert after["k1_3"].value == pytest.approx(123.456)

    # A refresh reloads the display; the values behind it are still intact
    # after the next edit.
    grid.refresh()
    grid._spins[(1, 2)].setValue(5.0)       # k_23
    after = host.kinetics.rates_by_name()
    assert after["k2_3"].value == pytest.approx(5.0)
    assert after["k1_2"].value == pytest.approx(5.0e6)
    assert after["k1_3"].value == pytest.approx(123.456)


def test_popup_mode_keeps_the_grid_behind_a_button(qapp):
    """``popup`` trades N rows of grid for one button that still says the state.

    A collapsed control that reports nothing about its contents makes the panel
    lie about the model, so the button carries a live summary — size and how
    many transitions are non-zero — and it has to track edits.
    """
    from qtpy import QtWidgets

    from chisurf.core.dataspec import load_view_spec
    from chisurf.gui.autoform import AutoForm
    from chisurf.gui.autoform.sections.rate_matrix_section import RateMatrixWidget

    class _Popup(_Model):
        def __init__(self):
            super().__init__()
            self.n = 3
            self.k = [0.0] * 9

        def view_spec(self):
            return load_view_spec({
                "sections": [
                    {"type": "custom", "key": "rate_matrix", "target": "k",
                     "options": {"size_attr": "n", "minimum": 0.0, "decimals": 2,
                                 "popup": True, "title": "Rates"}},
                ]
            })

    model = _Popup()
    form = AutoForm(model)
    grid = form.findChildren(RateMatrixWidget)[0]

    assert grid.button is not None
    assert "3×3" in grid.button.text()
    assert "0 set" in grid.button.text()
    # The grid must not be occupying the panel before it is asked for.
    assert grid.table.parent() is not grid or not grid.table.isVisibleTo(form)
    assert grid._dialog is None

    grid.button.click()
    assert isinstance(grid._dialog, QtWidgets.QDialog)
    assert grid.table.isVisibleTo(grid._dialog)

    # An edit in the popup reaches the model and updates the summary.
    grid._spins[(0, 1)].setValue(4.0)
    assert model.k[1] == pytest.approx(4.0)
    assert "1 set" in grid.button.text()

    # Reopening reuses the one dialog rather than stacking windows.
    dialog = grid._dialog
    grid.button.click()
    assert grid._dialog is dialog
