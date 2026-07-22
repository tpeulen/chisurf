"""The photon-filter wizard's burst-search combobox is populated from tttrlib.

These exercise the registry-to-widget layer against a minimal stand-in page
rather than the full wizard, so a failure points at this integration instead of
at unrelated wizard wiring. They need a Qt binding; where none is installed the
whole module skips, and the Qt-free half of the same feature is covered by
``test_tttrlib_search.py``.
"""

import pytest

pytest.importorskip("qtpy.QtWidgets", reason="no Qt binding installed")

from qtpy import QtWidgets  # noqa: E402

from chisurf.core.fluorescence.burst import tttrlib_search  # noqa: E402
from chisurf.gui.widgets.wizard.tttr_photonfilter import (  # noqa: E402
    tttr_photon_filter_tttrlib as tttrlib_modes,
)

BUILTIN_MODES = ["Count rate", "Burst", "BOCPD Burst", "Kalman Burst", "CUSUM Burst"]


class _Page(QtWidgets.QWidget):
    """A stand-in for the wizard page: the combobox plus a couple of built-ins."""

    def __init__(self):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        self.comboBox_burst_filter = QtWidgets.QComboBox()
        self.comboBox_burst_filter.addItems(BUILTIN_MODES)
        layout.addWidget(self.comboBox_burst_filter)
        # Two of the shared widgets the built-in modes reuse.
        self.spinBox = QtWidgets.QSpinBox()
        self.doubleSpinBox_5 = QtWidgets.QDoubleSpinBox()
        layout.addWidget(self.spinBox)
        layout.addWidget(self.doubleSpinBox_5)


@pytest.fixture
def page(qapp):
    widget = _Page()
    assert tttrlib_modes.install(widget) is True
    return widget


def test_combobox_gains_every_tttrlib_algorithm(page):
    combo = page.comboBox_burst_filter
    labels = [combo.itemText(i) for i in range(combo.count())]
    # install() replaces the hand-written built-in modes entirely with the
    # tttrlib registry (single source of truth), so the built-ins are cleared.
    for mode in BUILTIN_MODES:
        assert mode not in labels, "a built-in mode leaked through"

    algorithms = tttrlib_search.algorithms()
    found = {
        combo.itemData(i, tttrlib_modes.ALGORITHM_ROLE)
        for i in range(combo.count())
    }
    assert set(algorithms) <= found
    # The label shown comes from tttrlib, not from this repo.
    for i in range(combo.count()):
        name = combo.itemData(i, tttrlib_modes.ALGORITHM_ROLE)
        if name:
            assert combo.itemText(i) == algorithms[name]["label"]


def test_builtin_modes_are_not_registry_backed(page):
    combo = page.comboBox_burst_filter
    for mode in BUILTIN_MODES:
        combo.setCurrentIndex(combo.findText(mode))
        assert tttrlib_modes.selected_algorithm(page) is None
        assert tttrlib_modes.apply_visibility(page) is False


def test_selecting_an_algorithm_generates_its_parameters(page):
    assert tttrlib_modes.select(page, "maxtree") is True
    assert tttrlib_modes.selected_algorithm(page) == "maxtree"
    assert tttrlib_modes.apply_visibility(page) is True

    # Built-in parameter widgets step aside for the generated ones.
    assert not page.spinBox.isVisible()
    assert not page.doubleSpinBox_5.isVisible()

    assert tttrlib_modes.parameters(page) == tttrlib_search.defaults("maxtree")


def test_switching_algorithm_rebuilds_with_that_algorithms_parameters(page):
    tttrlib_modes.select(page, "maxtree")
    assert "min_significance" in tttrlib_modes.parameters(page)

    tttrlib_modes.select(page, "sliding_window")
    params = tttrlib_modes.parameters(page)
    assert set(params) == set(tttrlib_search.defaults("sliding_window"))
    assert "min_significance" not in params


def test_restored_values_survive_the_selection(page):
    """A saved project's parameters must not be overwritten by the defaults."""
    tttrlib_modes.select(page, "maxtree", {"L": 77, "min_significance": 6.0})
    params = tttrlib_modes.parameters(page)
    assert params["L"] == 77
    assert params["min_significance"] == 6.0


def test_reapplying_visibility_does_not_discard_edits(page):
    """apply_visibility runs on every mode change; it must be idempotent."""
    tttrlib_modes.select(page, "maxtree", {"L": 55})
    for _ in range(3):
        tttrlib_modes.apply_visibility(page)
    assert tttrlib_modes.parameters(page)["L"] == 55


def test_unknown_algorithm_is_reported_not_raised(page):
    assert tttrlib_modes.select(page, "not_an_algorithm") is False


def test_parameters_before_the_form_exists_fall_back_to_defaults(qapp):
    """Reading settings before the page is shown still yields a valid set."""
    widget = _Page()
    tttrlib_modes.install(widget)
    combo = widget.comboBox_burst_filter
    for i in range(combo.count()):
        if combo.itemData(i, tttrlib_modes.ALGORITHM_ROLE) == "maxtree":
            combo.setCurrentIndex(i)
            break
    assert tttrlib_modes.parameters(widget) == tttrlib_search.defaults("maxtree")
