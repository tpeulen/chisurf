"""Restore order of the project-load path (RF-926).

``_apply_state_to_model`` must restore ``bounds``/``bounds_on`` *before*
``value``: :class:`chisurf.core.parameter.Parameter` clamps a value against the
currently enforced bounds and writes the clamped number back, so a value
assigned while the freshly constructed model still carries its default bounds is
truncated irrecoverably.
"""

from __future__ import annotations

import pytest

pytest.importorskip("chinet")

from chisurf.core.fitting.parameter import FittingParameter  # noqa: E402
from chisurf.core.project.fit_state import _apply_state_to_model  # noqa: E402


class _ParameterHolder:
    """Minimal stand-in for a model exposing a single fitting parameter.

    Parameters
    ----------
    parameter : FittingParameter
        The parameter reachable through ``parameters_all`` /
        ``parameters_all_dict``, i.e. the two lookups the restore path uses.
    """

    def __init__(self, parameter: FittingParameter):
        self.parameters_all = [parameter]
        self.parameters_all_dict = {parameter.name: parameter}


def _state_for(parameter: FittingParameter, **fields) -> dict:
    """Build an ``_apply_state_to_model`` state dict for one parameter.

    Parameters
    ----------
    parameter : FittingParameter
        Parameter whose UID keys the returned ``parameters`` mapping.
    **fields
        Scalar entries (``value``, ``bounds``, ``bounds_on``, ``fixed``).

    Returns
    -------
    dict
        A state dictionary in the shape written by ``_model_to_state``.
    """
    entry = {"name": parameter.name}
    entry.update(fields)
    return {"parameters": {str(parameter.unique_identifier): entry}}


def test_value_outside_default_bounds_survives_restore():
    """A saved value beyond the model's *default* ceiling is not clamped."""
    p = FittingParameter(name="x", value=1.0, lb=0.0, ub=10.0, bounds_on=True)
    state = _state_for(p, value=50.0, bounds=[0.0, 100.0], bounds_on=True, fixed=False)

    _apply_state_to_model(_ParameterHolder(p), state)

    assert p.bounds == (0.0, 100.0)
    assert p.value == pytest.approx(50.0)


def test_value_below_default_bounds_survives_restore():
    """The same holds for a saved value below the default floor."""
    p = FittingParameter(name="x", value=1.0, lb=0.0, ub=10.0, bounds_on=True)
    state = _state_for(p, value=-5.0, bounds=[-10.0, 10.0], bounds_on=True, fixed=False)

    _apply_state_to_model(_ParameterHolder(p), state)

    assert p.bounds == (-10.0, 10.0)
    assert p.value == pytest.approx(-5.0)


def test_restored_bounds_still_clamp_a_value_outside_them():
    """Restoring in the right order does not disable clamping altogether."""
    p = FittingParameter(name="x", value=1.0, lb=0.0, ub=100.0, bounds_on=True)
    state = _state_for(p, value=50.0, bounds=[0.0, 10.0], bounds_on=True, fixed=False)

    _apply_state_to_model(_ParameterHolder(p), state)

    assert p.bounds == (0.0, 10.0)
    assert p.value == pytest.approx(10.0)


def test_bounds_off_in_state_leaves_the_value_untouched():
    """A state that turns bounds off restores the raw value verbatim."""
    p = FittingParameter(name="x", value=1.0, lb=0.0, ub=10.0, bounds_on=True)
    state = _state_for(p, value=50.0, bounds=[0.0, 10.0], bounds_on=False, fixed=False)

    _apply_state_to_model(_ParameterHolder(p), state)

    assert p.bounds_on is False
    assert p.value == pytest.approx(50.0)
