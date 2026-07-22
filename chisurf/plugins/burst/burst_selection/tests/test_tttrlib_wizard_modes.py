"""The wizard drives a host combobox through a single BurstSearchForm.

The photon-filter wizard keeps its own "Filter mode" combobox but delegates
populating it and generating the parameter form to one
:class:`~chisurf.gui.widgets.burst_search_form.BurstSearchForm`, the same widget
used standalone. These exercise that external-combobox seam against a minimal
host, so a failure points here rather than at unrelated wizard wiring. The
Qt-free half of the feature is covered by ``test_tttrlib_search.py``.
"""

import pytest

pytest.importorskip("qtpy.QtWidgets", reason="no Qt binding installed")

from qtpy import QtWidgets  # noqa: E402

from chisurf.core.fluorescence.burst import tttrlib_search  # noqa: E402
from chisurf.gui.widgets.burst_search_form import BurstSearchForm  # noqa: E402

BUILTIN_MODES = ["Count rate", "Burst", "BOCPD Burst", "Kalman Burst", "CUSUM Burst"]


@pytest.fixture
def combo(qapp):
    """A host combobox pre-seeded with the retired built-in modes."""
    box = QtWidgets.QComboBox()
    box.addItems(BUILTIN_MODES)
    return box


@pytest.fixture
def form(combo):
    """A BurstSearchForm driving the host combobox, as the wizard builds it."""
    return BurstSearchForm(combo=combo)


def test_host_combobox_is_repopulated_from_the_registry(form, combo):
    labels = [combo.itemText(i) for i in range(combo.count())]
    # Driving the host combobox clears the hand-written built-in modes entirely
    # (single source of truth), then fills it from tttrlib.
    for mode in BUILTIN_MODES:
        assert mode not in labels, "a built-in mode leaked through"

    algorithms = tttrlib_search.algorithms()
    found = {combo.itemData(i) for i in range(combo.count())}
    assert set(algorithms) <= found
    # The label shown comes from tttrlib, not from this repo.
    for i in range(combo.count()):
        name = combo.itemData(i)
        assert name and combo.itemText(i) == algorithms[name]["label"]


def test_the_host_combobox_becomes_the_forms_selector(form, combo):
    # The widget does not create a second combobox; it drives the host's.
    assert form.combo_algorithm is combo


def test_selecting_an_algorithm_generates_its_parameters(form):
    form.set_state("maxtree")
    assert form.algorithm == "maxtree"
    assert form.parameters == tttrlib_search.defaults("maxtree")


def test_switching_algorithm_rebuilds_with_that_algorithms_parameters(form):
    form.set_state("maxtree")
    assert "min_significance" in form.parameters

    form.set_state("sliding_window")
    params = form.parameters
    assert set(params) == set(tttrlib_search.defaults("sliding_window"))
    assert "min_significance" not in params


def test_restored_values_survive_the_selection(form):
    """A saved project's parameters must not be overwritten by the defaults."""
    form.set_state("maxtree", {"L": 77, "min_significance": 6.0})
    params = form.parameters
    assert params["L"] == 77
    assert params["min_significance"] == 6.0


def test_switching_via_the_combobox_resets_to_that_algorithms_defaults(form, combo):
    form.set_state("maxtree", {"L": 55})
    # A user changing the combobox directly rebuilds with fresh defaults.
    index = combo.findData("sliding_window")
    combo.setCurrentIndex(index)
    assert form.algorithm == "sliding_window"
    assert form.parameters == tttrlib_search.defaults("sliding_window")


def test_unknown_algorithm_is_rejected(form):
    with pytest.raises(ValueError, match="unknown burst search"):
        form.set_state("not_an_algorithm")


def test_parameters_track_the_current_combobox_selection(combo):
    """Reading settings after a plain combobox change yields that search's set."""
    form = BurstSearchForm(combo=combo)
    index = combo.findData("maxtree")
    combo.setCurrentIndex(index)
    assert form.parameters == tttrlib_search.defaults("maxtree")
