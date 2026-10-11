"""Format derivation from step, and the log/linear range choice."""

import math

import pytest

from chisurf.plugins.calculator.inputs import _fmt_for, _wants_log


@pytest.mark.parametrize(
    "step,decimals",
    [
        (0.1, 1),
        (0.01, 2),
        (0.05, 2),
        (0.005, 3),
        (0.5, 1),
        (1.0, 0),
        (5.0, 0),
    ],
)
def test_step_implies_its_decimals(step, decimals):
    assert _fmt_for(step) == f"%.{decimals}f"


def test_no_step_defaults_to_three():
    assert _fmt_for(None) == "%.3f"


@pytest.mark.parametrize(
    "minimum,maximum,log",
    [
        (0.001, 9999.0, True),  # seven decades: lifetimes
        (0.1, 999.0, True),  # four decades: R0
        (0.0, 1.0, False),  # includes zero: E
        (0.0, 9999.0, False),  # zero bound: never log
        (0.001, 1.0, True),  # three decades: log by the threshold
        (-1.0, 1.0, False),  # signed
    ],
)
def test_which_ranges_go_logarithmic(minimum, maximum, log):
    assert _wants_log(minimum, maximum) is log


def test_two_decades_is_the_threshold():
    assert _wants_log(1.0, 99.0) is False
    assert _wants_log(1.0, 100.0) is True
