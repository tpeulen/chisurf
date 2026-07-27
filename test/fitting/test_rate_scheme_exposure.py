"""A kinetic scheme must report the rates it currently has.

A parameter group only lists its parameters after ``find_parameters`` has run,
which the fitting machinery does when it builds a model. A scheme inspected on
its own — from a script, a test, or the assistant — therefore looked **empty**,
which reads as "this model has nothing to fit" rather than "ask again later".

Worse, ``find_parameters`` snapshots the rate objects, and resizing a scheme
replaces every one of them. Without invalidation the group keeps reporting the
*old* rates: an optimiser handed those would move parameters that no longer
belong to the scheme while the ones that do sit untouched — and the fit would
report success.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fitting.kinetics import RateMatrixParameters


def names(group) -> list[str]:
    """Return the parameter names a group reports."""
    return list(group.parameters_all_dict)


def rate_names(group) -> list[str]:
    """Return only the rate parameters a group reports."""
    return [name for name in names(group) if name.startswith("k")]


# ── exposure without being asked ──────────────────────────────────────


def test_a_fresh_scheme_reports_its_rates():
    """The regression: this used to be empty until find_parameters was called."""
    scheme = RateMatrixParameters(name="kinetics", n_states=3)

    assert rate_names(scheme) == ["k1_2", "k1_3", "k2_1", "k2_3", "k3_1", "k3_2"]


def test_two_states_give_two_rates():
    assert rate_names(RateMatrixParameters(name="k", n_states=2)) == ["k1_2", "k2_1"]


def test_the_reported_parameters_are_the_live_rate_objects():
    """Reporting copies would let a caller set a value that changes nothing."""
    scheme = RateMatrixParameters(name="kinetics", n_states=2)
    scheme.parameters_all_dict["k1_2"].value = 250.0

    assert scheme.rates_by_name()["k1_2"].value == pytest.approx(250.0)
    # The matrix is K[target, source], so 1 -> 2 sits at row 2, column 1.
    assert scheme.rate_matrix()[1, 0] == pytest.approx(250.0)


def test_the_matrix_is_indexed_target_then_source():
    """An easy one to get backwards, and it silently transposes a scheme."""
    scheme = RateMatrixParameters(name="kinetics", n_states=2, default_rate=0.0)
    scheme.rates_by_name()["k1_2"].value = 7.0

    matrix = np.asarray(scheme.rate_matrix())
    assert matrix[1, 0] == pytest.approx(7.0), "K[target, source]"
    assert matrix[0, 1] == pytest.approx(0.0), "the reverse rate is still zero"


# ── the cache follows the scheme ──────────────────────────────────────


def test_growing_the_scheme_reports_the_new_rates():
    scheme = RateMatrixParameters(name="kinetics", n_states=2)
    assert len(rate_names(scheme)) == 2

    scheme.n_states = 4
    assert len(rate_names(scheme)) == 12
    assert "k3_4" in rate_names(scheme)


def test_shrinking_the_scheme_drops_the_vanished_rates():
    scheme = RateMatrixParameters(name="kinetics", n_states=3)
    assert "k1_3" in rate_names(scheme)

    scheme.n_states = 2
    assert rate_names(scheme) == ["k1_2", "k2_1"]


def test_no_stale_object_survives_a_resize():
    """The dangerous case: an optimiser holding rates that are no longer used."""
    scheme = RateMatrixParameters(name="kinetics", n_states=3)
    before = list(scheme.parameters_all)

    scheme.n_states = 2
    after = scheme.parameters_all

    assert all(parameter in scheme._rates for parameter in after)
    assert not any(parameter in after for parameter in before if parameter not in scheme._rates)


def test_values_survive_a_resize_by_label():
    """Growing a scheme must not reset the rates it already had."""
    scheme = RateMatrixParameters(name="kinetics", n_states=2)
    scheme.rates_by_name()["k1_2"].value = 42.0

    scheme.n_states = 3
    assert scheme.rates_by_name()["k1_2"].value == pytest.approx(42.0)


# ── a group that holds more than rates ────────────────────────────────


def test_a_mixin_group_reports_its_other_parameters_too():
    """``PdaDynamicNStates`` carries a distance and a width per state."""
    from chisurf.core.models.pda.dynamic_mc import PdaDynamicNStates

    group = PdaDynamicNStates(name="states", n_states=2)
    reported = names(group)

    assert {"k1_2", "k2_1"} <= set(reported)
    assert {"R1", "R2", "s1", "s2"} <= set(reported)


def test_resizing_a_mixin_group_grows_both_kinds():
    from chisurf.core.models.pda.dynamic_mc import PdaDynamicNStates

    group = PdaDynamicNStates(name="states", n_states=2)
    group.n_states = 3
    reported = set(names(group))

    assert {"k1_3", "k3_1"} <= reported, "the new rates are missing"
    assert {"R3", "s3"} <= reported, "the new state's own parameters are missing"


# ── the scheme is still a scheme ──────────────────────────────────────


def test_topology_is_data_not_code():
    """Zeroing the long-range rates turns a triangle into a chain."""
    scheme = RateMatrixParameters(name="kinetics", n_states=3, default_rate=100.0)
    rates = scheme.rates_by_name()
    rates["k1_3"].value = 0.0
    rates["k3_1"].value = 0.0

    matrix = np.asarray(scheme.rate_matrix())
    assert matrix[0, 2] == 0.0 and matrix[2, 0] == 0.0
    assert matrix[0, 1] == pytest.approx(100.0)
    assert np.allclose(np.diag(matrix), 0.0)


def test_the_rates_are_linkable_like_any_parameter():
    """Detailed balance is a link between two rates, so they must support it."""
    scheme = RateMatrixParameters(name="kinetics", n_states=2)
    forward = scheme.parameters_all_dict["k1_2"]

    assert hasattr(forward, "link")
    assert hasattr(forward, "fixed")
    assert hasattr(forward, "bounds")
