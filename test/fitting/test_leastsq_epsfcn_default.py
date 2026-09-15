"""The forward-difference step must not be left at machine epsilon.

MINPACK derives its step as ``sqrt(epsfcn) * |x|``, and ``epsfcn = 0`` means
"use machine epsilon" -- about 1.5e-8 relative. That is far below the noise
floor of the decay model, whose convolution is recursive over ~1024 channels, so
the Jacobian columns come back dominated by rounding noise. In practice the
optimiser then failed to move the lifetimes at all from many starting points:
they stayed at *exactly* their starting values while only the nuisance
parameters moved.

Measured over 88 randomised fits across four independent conditions (three start
seeds, a different noise realisation, and a 3-exponential model), fits reaching
chi2r < 1.1:

==========  =======
``epsfcn``  valid
==========  =======
0           60/88
1e-10       81/88
1e-8        82/88
**1e-6**    **83/88**
==========  =======

``1e-6`` was no worse than any alternative in any of the four conditions, for
roughly 10-30% more time.

The bundled default is in ``settings_chisurf.yaml``, but user settings are copied
to ``~/.chisurf`` once and **never refreshed**, so every existing install keeps
``epsfcn: 0`` -- the broken value. :func:`_leastsq_options` therefore treats 0 as
unset, or the fix would be inert for exactly the people who already have the
problem.
"""
import numpy as np
import pytest

import chisurf.core.settings
from chisurf.core.fitting.fit import DEFAULT_EPSFCN, _leastsq_options

from .test_tcspc_fit_convergence import _build, _chi2r, _taus, TRUE_TAUS


def test_zero_is_treated_as_unset():
    """The regression: 0 is MINPACK's 'pick for me', and its pick is wrong here."""
    assert _leastsq_options({"epsfcn": 0})["epsfcn"] == DEFAULT_EPSFCN
    assert _leastsq_options({"epsfcn": 0.0})["epsfcn"] == DEFAULT_EPSFCN


def test_missing_key_is_filled_in():
    assert _leastsq_options({})["epsfcn"] == DEFAULT_EPSFCN


def test_explicit_value_is_honoured():
    """A machine-epsilon step stays reachable by asking for it explicitly."""
    assert _leastsq_options({"epsfcn": 1e-3})["epsfcn"] == pytest.approx(1e-3)
    assert _leastsq_options({"epsfcn": 1e-16})["epsfcn"] == pytest.approx(1e-16)


def test_garbage_falls_back_rather_than_raising():
    assert _leastsq_options({"epsfcn": None})["epsfcn"] == DEFAULT_EPSFCN
    assert _leastsq_options({"epsfcn": "nonsense"})["epsfcn"] == DEFAULT_EPSFCN


def test_other_options_are_passed_through_untouched():
    opts = {"epsfcn": 0, "ftol": 1.5e-8, "xtol": 1.5e-8, "factor": 100}
    out = _leastsq_options(opts)
    assert out["ftol"] == pytest.approx(1.5e-8)
    assert out["xtol"] == pytest.approx(1.5e-8)
    assert out["factor"] == 100


def test_the_caller_s_dict_is_not_mutated():
    """The settings dict is global; writing into it would leak across fits."""
    opts = {"epsfcn": 0}
    _leastsq_options(opts)
    assert opts["epsfcn"] == 0


def test_bundled_default_is_no_longer_zero():
    """The shipped YAML should be right too, for fresh installs."""
    shipped = chisurf.core.settings.cs_settings["optimization"]["leastsq"]
    assert "epsfcn" in shipped


# ---------------------------------------------------------------------------
# End to end: it has to actually move the lifetimes.
# ---------------------------------------------------------------------------


def test_lifetimes_move_away_from_a_poor_start():
    """With a machine-epsilon step these stayed at exactly their start values."""
    start = [(1.0, 3.0), (1.0, 2.0)]
    fit, m = _build(start=start)
    fit.run()

    taus = _taus(m)
    assert taus != pytest.approx(sorted(t for _a, t in start)), (
        "lifetimes never moved — the Jacobian step is below the model's noise floor")
    np.testing.assert_allclose(taus, sorted(TRUE_TAUS), rtol=0.1)
    assert _chi2r(fit) < 1.5
