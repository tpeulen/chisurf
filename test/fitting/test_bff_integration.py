"""FittingParameter synchronises with its underlying port.

The backing port is an ``IMP.bff.Port`` (phase 3 of removing chinet from
chisurf); the contract itself is unchanged from the chinet era: writes
through the parameter reach the port, writes to the port reach the
parameter, links link ports, and the fixed flag freezes both.
"""

import numpy as np

from chisurf.core.fitting.parameter import FittingParameter


def test_fitting_parameter_port_sync():
    p = FittingParameter(name="test_p", value=10.0, lb=0.0, ub=20.0,
                         bounds_on=True)

    # Check initial sync
    assert p.value == 10.0
    assert float(np.atleast_1d(p._port.value)[0]) == 10.0
    assert p._port.bounded is True
    assert np.allclose(p._port.bounds, [0.0, 20.0])

    # Update via Parameter object
    p.value = 15.0
    assert float(np.atleast_1d(p._port.value)[0]) == 15.0

    # Update via the port directly
    p._port.value = np.array([5.0])
    assert p.value == 5.0

    # Test bounding: the port enforces on write, the parameter on read
    p.value = 25.0
    assert p.value == 20.0 or float(np.atleast_1d(p._port.value)[0]) == 20.0


def test_fitting_parameter_linking_sync():
    p1 = FittingParameter(name="p1", value=1.0)
    p2 = FittingParameter(name="p2", value=2.0)

    p2.link = p1
    assert p2.is_linked
    assert p2._port.is_linked()

    # Check value sync through link
    p1.value = 5.0
    assert p2.value == 5.0
    assert float(np.atleast_1d(p2._port.value)[0]) == 5.0


def test_fitting_parameter_fixed_sync():
    p = FittingParameter(name="p", value=1.0, fixed=False)
    assert not p._port.fixed

    p.fixed = True
    assert p._port.fixed

    p.fixed = False
    assert not p._port.fixed
