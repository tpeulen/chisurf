"""``Parameter.lb`` / ``Parameter.ub`` accessors.

``Parameter.__init__`` has always accepted ``lb``/``ub`` — 158 call sites across
the tree pass them — but there were no matching properties. So ``p.lb`` raised
``AttributeError``, and ``p.lb = 0.01`` silently created a dead instance
attribute while the bound was never applied. That bit a real fixture: lifetime
bounds looked set and were not.
"""
import numpy as np
import pytest

from chisurf.core.parameter import Parameter


def test_constructor_bounds_are_readable():
    p = Parameter(value=5.0, lb=1.0, ub=10.0, bounds_on=True)
    assert p.lb == pytest.approx(1.0)
    assert p.ub == pytest.approx(10.0)


def test_bounds_round_trip():
    """Assignment must actually stick — this is the regression."""
    p = Parameter(value=5.0, lb=1.0, ub=10.0, bounds_on=True)
    p.lb = 2.0
    p.ub = 8.0
    assert p.lb == pytest.approx(2.0)
    assert p.ub == pytest.approx(8.0)
    assert tuple(p.bounds) == pytest.approx((2.0, 8.0))


def test_setting_one_bound_leaves_the_other():
    p = Parameter(value=5.0, lb=1.0, ub=10.0, bounds_on=True)
    p.lb = 3.0
    assert p.ub == pytest.approx(10.0)
    p.ub = 20.0
    assert p.lb == pytest.approx(3.0)


def test_bounds_are_enforced_on_read():
    p = Parameter(value=5.0, lb=1.0, ub=10.0, bounds_on=True)
    p.value = 99.0
    assert p.value == pytest.approx(10.0)
    p.value = -99.0
    assert p.value == pytest.approx(1.0)


def test_unbounded_parameter_reports_infinities():
    """An absent bound reads back the way __init__ spells it."""
    q = Parameter(value=1.0)
    assert q.lb == float("-inf")
    assert q.ub == float("inf")


def test_bounds_set_while_disabled_are_stored_then_enforced():
    """Setting a bound must stick even when enforcement is off.

    ``Port.bounds`` reports ``(None, None)`` while ``bounds_on`` is False even
    though the values are stored, which made lb/ub a lossy round-trip.
    """
    q = Parameter(value=1.0)
    q.lb, q.ub = 0.0, 3.0
    assert q.lb == pytest.approx(0.0)
    assert q.ub == pytest.approx(3.0)

    q.value = 99.0
    assert q.value == pytest.approx(99.0), "bounds must not apply while off"

    q.bounds_on = True
    assert q.value == pytest.approx(3.0), "bounds must apply once enabled"


def test_reading_value_is_side_effect_free():
    """Repeated reads must be stable and must not mutate the parameter."""
    p = Parameter(value=2.5)
    first = p.value
    for _ in range(5):
        assert p.value == first
