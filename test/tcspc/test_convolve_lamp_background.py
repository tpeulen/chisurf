"""Pin the lamp-background handling of :meth:`Convolve._process_irf` (RF-195).

The loaded-IRF branch used to subtract ``lamp_background`` twice — once inside
the branch and once again in the shared tail below the ``if``/``else`` — while
the synthetic-IRF branch subtracted it exactly once. Both branches must remove
the background exactly once.
"""

import numpy as np
import pytest

from chisurf.core.curve import Curve
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.tcspc.lifetime import LifetimeModel

IRF_Y = np.array([0.0, 4.0, 10.0, 6.0, 3.0, 1.0, 0.0, 0.0])
IRF_X = np.arange(len(IRF_Y), dtype=float)


def _convolve(lamp_background: float):
    """Build a `Convolve` on a unit-spaced 8-channel decay with a full IRF window.

    Parameters
    ----------
    lamp_background : float
        Value of the lamp-background nuisance parameter.

    Returns
    -------
    chisurf.core.models.tcspc.nusiance.Convolve
        The convolve object of a fresh :class:`LifetimeModel` fit.
    """
    fit = Fit(model_class=LifetimeModel, data=DataCurve(x=IRF_X, y=IRF_Y.copy()))
    convolve = fit.model.convolve
    # The IRF window is expressed in time units; dt is 1.0 here, so this is the
    # whole axis and no truncation takes place.
    convolve._irf_start.value = 0.0
    convolve._irf_stop.value = float(len(IRF_Y))
    convolve.lamp_background = lamp_background
    return convolve


def test_lamp_background_subtracted_once_from_loaded_irf():
    """A loaded IRF loses the lamp background exactly once, not twice."""
    convolve = _convolve(lamp_background=1.0)
    convolve._irf = Curve(x=IRF_X, y=IRF_Y.copy())

    processed = convolve._process_irf(normalize=False)

    expected = np.clip(IRF_Y - 1.0, 0, None)
    np.testing.assert_allclose(processed.y, expected)


def test_process_irf_does_not_mutate_the_stored_irf():
    """Processing is non-destructive: the stored IRF keeps its raw counts."""
    convolve = _convolve(lamp_background=1.0)
    convolve._irf = Curve(x=IRF_X, y=IRF_Y.copy())

    convolve._process_irf(normalize=False)
    convolve._process_irf(normalize=False)

    np.testing.assert_allclose(convolve._irf.y, IRF_Y)


@pytest.mark.parametrize("lamp_background", [0.0, 0.25, 0.5, 1.0])
def test_lamp_background_is_a_single_offset(lamp_background):
    """The processed IRF is the raw IRF minus one background, clipped at zero."""
    convolve = _convolve(lamp_background=lamp_background)
    convolve._irf = Curve(x=IRF_X, y=IRF_Y.copy())

    processed = convolve._process_irf(normalize=False)

    expected = np.clip(IRF_Y - convolve.lamp_background, 0, None)
    np.testing.assert_allclose(processed.y, expected)
