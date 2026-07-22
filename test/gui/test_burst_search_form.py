"""The registry-driven burst-search parameter form widget.

:class:`~chisurf.gui.widgets.burst_search_form.BurstSearchForm` builds its
algorithm chooser and parameter form from tttrlib's registry, so there is no
per-algorithm widget code to test — only that the widget reflects the registry,
switches cleanly, restores saved state, and degrades when no registry is
published. The registry itself and the Qt-free view layer are covered by
``test_tttrlib_search.py``.
"""

import pytest

pytest.importorskip("qtpy.QtWidgets", reason="no Qt binding installed")

from chisurf.core.fluorescence.burst import tttrlib_search  # noqa: E402
from chisurf.gui.widgets.burst_search_form import BurstSearchForm  # noqa: E402


def test_combobox_offers_every_registry_algorithm(qapp):
    form = BurstSearchForm()
    offered = {
        form.combo_algorithm.itemData(i)
        for i in range(form.combo_algorithm.count())
    }
    assert offered == set(tttrlib_search.algorithms())
    assert form.combo_algorithm.isEnabled()


def test_parameters_default_to_the_registry_values(qapp):
    form = BurstSearchForm(algorithm="maxtree")
    assert form.algorithm == "maxtree"
    assert form.parameters == tttrlib_search.defaults("maxtree")


def test_initial_values_override_the_defaults(qapp):
    form = BurstSearchForm(algorithm="maxtree", values={"L": 123})
    assert form.parameters["L"] == 123


def test_switching_algorithm_rebuilds_with_its_own_defaults(qapp):
    form = BurstSearchForm(algorithm="maxtree", values={"L": 999})
    index = form.combo_algorithm.findData("sliding_window")
    assert index >= 0
    form.combo_algorithm.setCurrentIndex(index)
    assert form.algorithm == "sliding_window"
    # The old algorithm's edited value does not carry over; parameters are the
    # new algorithm's own defaults.
    assert form.parameters == tttrlib_search.defaults("sliding_window")


def test_switching_algorithm_emits_parameters_changed(qapp):
    form = BurstSearchForm(algorithm="maxtree")
    seen = []
    form.parametersChanged.connect(lambda: seen.append(True))
    form.combo_algorithm.setCurrentIndex(
        form.combo_algorithm.findData("sliding_window")
    )
    assert seen, "changing the algorithm should notify listeners"


def test_set_state_selects_and_loads(qapp):
    form = BurstSearchForm(algorithm="maxtree")
    form.set_state("sliding_window", {"L": 77})
    assert form.algorithm == "sliding_window"
    assert form.parameters["L"] == 77


def test_set_state_rejects_an_unknown_algorithm(qapp):
    form = BurstSearchForm()
    with pytest.raises(ValueError, match="unknown burst search"):
        form.set_state("not_an_algorithm")


def test_composite_search_renders_a_nested_panel(qapp):
    # The coincident search delegates its per-group parameters to another search;
    # the widget must render those as a nested panel (via entry_form_view_auto),
    # not as a raw JSON box, and expose them under "parameters".
    from chisurf.core import tttrlib_registry

    if "coincident" not in tttrlib_search.algorithms():
        pytest.skip("this tttrlib has no composite burst search")
    form = BurstSearchForm(algorithm="coincident")
    params = form.parameters
    assert "parameters" in params, "the delegated inner parameters must be present"
    assert params["parameters"] == tttrlib_registry.defaults(
        "burst_search", "maxtree"
    )


def test_composite_parameters_are_foldable_not_a_json_box(qapp):
    from chisurf.core.dataspec.rpc import RpcMethodView  # noqa: F401

    if "coincident" not in tttrlib_search.algorithms():
        pytest.skip("this tttrlib has no composite burst search")
    form = BurstSearchForm(algorithm="coincident")
    panels = form._view.view_spec().sections
    assert len(panels) >= 2, "expected the entry's own panel plus a nested one"


def test_no_registry_disables_the_widget_and_explains(qapp, monkeypatch):
    # An older tttrlib publishes no registry; the widget stays usable-looking but
    # inert, and says why, instead of raising on construction.
    monkeypatch.setattr(tttrlib_search, "algorithms", lambda: {})
    form = BurstSearchForm()
    assert not form.combo_algorithm.isEnabled()
    assert form.parameters == {}
    assert "tttrlib" in form.label_summary.text()
