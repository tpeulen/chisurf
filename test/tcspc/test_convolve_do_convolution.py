"""Pin that ``Convolve.do_convolution`` reaches the model decay (RF-194).

The flag is written from the settings key ``tcspc.convolution_on_by_default``,
the checkbox of the Convolve panel and ``Convolve.set_state`` on project load —
but it used to be read by nobody, so unticking the box left the model convolved
with the IRF. With the convolution switched off the model is the ideal
multi-exponential decay (periodic tail in the ``per`` mode) instead.
"""

import numpy as np
import pytest
import scipy.stats

from chisurf.core.curve import Curve
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.tcspc.lifetime import LifetimeModel

X = np.arange(64, dtype=float)
LIFETIME_SPECTRUM = np.array([1.0, 4.0])
PERIOD = 32.0


def _convolve():
    """Build a `Convolve` on a 64-channel decay carrying a wide, shifted IRF.

    Returns
    -------
    chisurf.core.models.tcspc.nusiance.Convolve
        The convolve object of a fresh :class:`LifetimeModel` fit.
    """
    data = DataCurve(x=X, y=1000.0 * np.exp(-X / 4.0))
    fit = Fit(model_class=LifetimeModel, data=data)
    convolve = fit.model.convolve
    convolve._irf = Curve(x=X, y=scipy.stats.norm.pdf(X, loc=5.0, scale=1.0))
    # Window bounds are expressed in time units; dt is 1.0 here, so these cover
    # the whole axis (a synthetic DataCurve carries no reader, so `Convolve`
    # falls back to a single-channel convolution window).
    convolve._irf_start.value = 0.0
    convolve._irf_stop.value = float(len(X))
    convolve._stop.value = float(len(X))
    return convolve


def _ideal_decay():
    """Return the ideal single-exponential decay on the data time axis."""
    return np.exp(-(X - X[0]) / LIFETIME_SPECTRUM[1]) * LIFETIME_SPECTRUM[0]


def test_switching_the_convolution_off_gives_the_ideal_decay():
    """In ``exp`` mode the unconvolved model is the bare exponential decay."""
    convolve = _convolve()

    convolved = convolve.convolve(LIFETIME_SPECTRUM, mode="exp").copy()
    convolve.do_convolution = False
    unconvolved = convolve.convolve(LIFETIME_SPECTRUM, mode="exp").copy()

    np.testing.assert_allclose(unconvolved, _ideal_decay())
    assert not np.allclose(convolved, unconvolved)


def test_the_periodic_mode_keeps_the_inter_pulse_tail():
    """Without an IRF the ``per`` mode still folds the preceding pulses in."""
    convolve = _convolve()
    convolve.do_convolution = False

    unconvolved = convolve.convolve(LIFETIME_SPECTRUM, mode="per", rep_rate=1000.0 / PERIOD)

    tail = 1.0 / (1.0 - np.exp(-PERIOD / LIFETIME_SPECTRUM[1]))
    np.testing.assert_allclose(unconvolved, _ideal_decay() * tail)


def test_the_full_mode_returns_the_decay_it_was_given():
    """``full`` convolves a ready decay, so switching off returns it unchanged."""
    convolve = _convolve()
    convolve.do_convolution = False
    given = np.exp(-X / 2.0)

    unconvolved = convolve.convolve(given, mode="full")

    np.testing.assert_allclose(unconvolved, given)
    np.testing.assert_allclose(given, np.exp(-X / 2.0))


@pytest.mark.parametrize("mode", ["per", "exp"])
def test_the_flag_reaches_the_model_decay(mode):
    """Toggling the flag changes what ``LifetimeModel.update_model`` computes."""
    convolve = _convolve()
    model = convolve.fit.model
    convolve.mode = mode

    model.update_model(lifetime_spectrum=LIFETIME_SPECTRUM)
    convolved = np.array(model.y, dtype=float)
    convolve.do_convolution = False
    model.update_model(lifetime_spectrum=LIFETIME_SPECTRUM)
    unconvolved = np.array(model.y, dtype=float)

    assert not np.allclose(convolved, unconvolved)
    # The IRF only delays and broadens: the unconvolved decay peaks in the
    # first channel, the convolved one at the position of the IRF.
    assert unconvolved.argmax() == 0
    assert convolved.argmax() > 0
