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


# ---------------------------------------------------------------------------
# Port.value setter semantics
# ---------------------------------------------------------------------------
#
# The port runtime is IMP.bff's Port (C++), which inherited chinet's write
# path: finite floats write directly, non-finite values are sanitised (NaN
# becomes the smallest normal, +/-inf the largest finite magnitudes), and
# writes respect the fixed flag and the bounds. These pin the contract.


from chisurf.core import nodes


def _port(**kw):
    return nodes._bff.GraphPort(value=1.0, name="t", **kw)


@pytest.mark.parametrize("v", [3.5, -2.25, 0.0, 1e-300, 1e300])
def test_finite_float_writes_round_trip(v):
    p = _port()
    p.value = v
    assert p.value == pytest.approx(v)


def test_bounds_are_applied_on_the_fast_path():
    p = _port(lb=0.0, ub=2.0, is_bounded=True)
    p.value = 99.0
    assert p.value == pytest.approx(2.0)
    p.value = -99.0
    assert p.value == pytest.approx(0.0)
    p.value = 1.5
    assert p.value == pytest.approx(1.5)


def test_non_finite_still_sanitised():
    """NaN/+-inf must fall through to the general path, not the fast one."""
    p = _port()
    p.value = float("nan")
    assert p.value == pytest.approx(np.finfo(np.float64).tiny)
    p.value = float("inf")
    assert p.value == pytest.approx(np.finfo(np.float64).max)
    p.value = float("-inf")
    assert p.value == pytest.approx(np.finfo(np.float64).min)


def test_int_and_vector_writes_unaffected():
    p = _port()
    p.value = 7
    assert p.value == pytest.approx(7.0)

    q = _port()
    q.value = np.array([1.0, 2.0, 3.0])
    np.testing.assert_allclose(np.asarray(q.value), [1.0, 2.0, 3.0])


def test_fixed_port_ignores_writes():
    p = _port()
    p.fixed = True
    p.value = 42.0
    assert p.value == pytest.approx(1.0)


def test_linked_ports_still_propagate():
    a, b = _port(), _port()
    b.link = a
    a.value = 5.0
    assert b.value == pytest.approx(5.0)
