"""Tests for the reader-level ``read()`` path of the TCSPC simulator setup.

Pins RF-637: a curve produced by :meth:`TCSPCSimulatorSetup.read` — the path
behind the *Read data* header's **+ Data** button — must carry the
``data_reader`` back-reference, otherwise a fit created from it opens at range
(0, 0) and fitting is a silent no-op.
"""

import types

import numpy as np

from chisurf.core.agent.tools.fitting import apply_auto_fit_range
from chisurf.core.experiments.tcspc.simulator import TCSPCSimulatorSetup

SPECTRUM = [0.75, 4.0, 0.25, 1.0]


def make_setup(**kwargs) -> TCSPCSimulatorSetup:
    """Build a simulator setup without a GUI controller.

    Parameters
    ----------
    **kwargs
        Forwarded to :class:`TCSPCSimulatorSetup`.

    Returns
    -------
    TCSPCSimulatorSetup
        Setup configured with a two-component lifetime spectrum.
    """
    kwargs.setdefault("n_tac", 512)
    kwargs.setdefault("dt", 0.0141)
    kwargs.setdefault("lifetime_spectrum", SPECTRUM)
    return TCSPCSimulatorSetup(**kwargs)


def test_simulator_constructs_without_controller():
    """A lifetime spectrum may be passed headlessly, i.e. with no controller."""
    setup = make_setup()
    assert setup.controller is None
    np.testing.assert_allclose(setup.lifetime_spectrum, SPECTRUM)


def test_read_sets_data_reader_on_curve():
    """``read()`` annotates the curve with the reader that produced it."""
    setup = make_setup()
    group = setup.read()
    curve = group[0]
    assert curve.data_reader is setup
    assert group.data_reader is setup


def test_read_curve_auto_ranges():
    """The simulated curve auto-ranges through its own ``data_reader``."""
    setup = make_setup()
    curve = setup.read()[0]

    start, stop = curve.data_reader.autofitrange(curve)
    assert 0 <= start < stop <= curve.y.size - 1

    fit = types.SimpleNamespace(data=curve, fit_range=(0, 0))
    assert apply_auto_fit_range(fit) == [int(start), int(stop)]
    assert fit.fit_range != (0, 0)
