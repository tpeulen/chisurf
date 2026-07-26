"""Regression tests for the ``setup.params.set`` action (RF-090).

The action used to dereference ``chisurf.cs.current_setup`` unguarded. Without a
main window — a plugin started standalone, e.g. ``python -m
chisurf.plugins.tttr.microtime_histogram --auto-transfer`` — that raises
``AttributeError`` from inside a Qt slot, so the "Transfer to ChiSurf" hand-off
(``experiment.set`` → ``setup.params.set`` → ``dataset.add``) dies halfway with
no dialog and no dataset. ``Main.current_setup`` is a property that itself
raises ``AttributeError`` when no experiment is selected, which Python reports
as "``Main`` object has no attribute ``current_setup``" and hides the cause, so
that case is pinned here too.
"""

from __future__ import annotations

import pytest

import chisurf as cs
from chisurf.core.actions import dispatch


class _Sub:
    """Nested attribute holder for the dotted-key case."""

    def __init__(self):
        self.gain = 0.0


class _Setup:
    """Stand-in for an experiment reader."""

    def __init__(self):
        self.dt = 0.0
        self.detector = _Sub()


class _Gui:
    """Main-window stand-in exposing a single setup."""

    def __init__(self, setup):
        self.current_setup = setup


class _GuiWithoutExperiment:
    """Main-window stand-in whose ``current_setup`` property raises.

    This is what ``Main`` does while no experiment is selected: the getter
    dereferences ``self.current_experiment``, which is ``None``.
    """

    @property
    def current_setup(self):
        experiment = None
        return experiment.readers[0]


@pytest.fixture
def restore_cs():
    """Restore the process-global ``chisurf.cs`` after the test."""
    previous = getattr(cs, "cs", None)
    yield
    cs.cs = previous


def test_params_are_applied_to_the_current_setup(restore_cs):
    """Plain and dotted keys are written to the active setup."""
    setup = _Setup()
    cs.cs = _Gui(setup)

    result = dispatch(
        name="setup.params.set",
        payload={"params": {"dt": 0.032, "detector.gain": 2.5}},
    )

    assert setup.dt == 0.032
    assert setup.detector.gain == 2.5
    assert sorted(result["applied"]) == ["detector.gain", "dt"]


def test_no_main_window_does_not_raise(restore_cs):
    """Standalone plugins dispatch the action with no main window present."""
    cs.cs = None

    result = dispatch(name="setup.params.set", payload={"params": {"dt": 0.032}})

    assert result["applied"] == []


def test_unselected_experiment_does_not_raise(restore_cs):
    """A ``current_setup`` getter that raises must not abort the hand-off."""
    cs.cs = _GuiWithoutExperiment()

    result = dispatch(name="setup.params.set", payload={"params": {"dt": 0.032}})

    assert result["applied"] == []
