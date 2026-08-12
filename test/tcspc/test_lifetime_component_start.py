"""Lifetime components must start apart, and inside their declared bounds.

Two defects in :meth:`chisurf.core.models.tcspc.lifetime.Lifetime.append`:

* every component started at the same 4 ns, so a two-exponential model began as
  **two identical exponentials** -- a start whose two Jacobian columns are the
  same vector, leaving the optimiser nothing to separate them with. Measured on
  the 10k-photon FRET sub-ensemble decay of
  ``test/agent/test_burst_workflow.py``, the fitted efficiency moved between
  0.04 and 0.55 -- every one of them at a reduced chi2 between 0.79 and 0.95 --
  depending on nothing but the lifetime bounds. With the components spread, the
  same four bounds give 0.575, 0.579, 0.583 and 0.572.
* the lifetime bounds ``[0.001, 100]`` ns were declared in the signature and
  never switched on, so the optimiser could walk into lifetimes of hundreds of
  nanoseconds -- past the excitation period, where the decay is a constant and
  the fit is meaningless rather than merely poor.
"""

import numpy as np
import pytest

from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import Fit
from chisurf.core.models.tcspc.lifetime import Lifetime, LifetimeModel

X = np.arange(64, dtype=float)
Y = np.round(1000.0 * np.exp(-X / 8.0)) + 5.0


def _lifetime_group(n: int) -> Lifetime:
    """Return a :class:`Lifetime` group holding *n* components."""
    fit = Fit(model_class=LifetimeModel, data=DataCurve(x=X, y=Y.copy()))
    group = Lifetime(fit=fit, short="L")
    for _ in range(n):
        group.append()
    return group


def test_the_first_component_keeps_the_familiar_default():
    """A single-exponential model still starts at 4 ns."""
    group = _lifetime_group(1)

    assert group._lifetimes[0].value == pytest.approx(Lifetime.DEFAULT_LIFETIME)


def test_components_do_not_start_on_top_of_each_other():
    """The degenerate start: two components at the same value."""
    group = _lifetime_group(4)
    values = [p.value for p in group._lifetimes]

    assert len(set(values)) == len(values), values
    for faster, slower in zip(values[1:], values):
        assert faster == pytest.approx(slower / Lifetime.COMPONENT_SPACING)


def test_the_spread_stays_inside_the_bounds():
    """Even a long chain of components stays in the declared window."""
    group = _lifetime_group(12)

    for parameter in group._lifetimes:
        lower, upper = parameter.bounds
        assert lower <= parameter.value <= upper


def test_the_declared_lifetime_bounds_are_enforced():
    """Declaring bounds and leaving them off is the same as having none."""
    group = _lifetime_group(2)

    for parameter in group._lifetimes:
        assert parameter.bounds_on is True
        lower, upper = parameter.bounds
        assert lower > 0.0, "a lifetime is positive"
        assert np.isfinite(upper), "a lifetime past the time window is a constant, not a fit"


def test_an_explicit_starting_lifetime_is_still_honoured():
    """The spread is only the default; callers keep control."""
    group = _lifetime_group(1)
    group.append(lifetime=7.5)

    assert group._lifetimes[1].value == pytest.approx(7.5)


def test_the_amplitudes_are_left_unbounded():
    """A negative amplitude is a rise term, not an error."""
    group = _lifetime_group(2)

    for parameter in group._amplitudes:
        assert parameter.bounds_on is False
