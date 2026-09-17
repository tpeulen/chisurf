"""The evaluation budget a fitting progress bar reports against.

Two failures, in order of discovery.

The bar was first scaled by MINPACK's ``200 * (n + 1)`` — its *give-up limit*,
not an expectation. A four-parameter fit converges in tens of evaluations, so the
bar crept to five percent and then jumped to done.

Scaling it by an *estimate* instead moved the failure rather than removing it:
nobody can know how many evaluations a fit needs, and dividing by a guess
saturates the moment the guess is passed. A real MFD fit takes 450 evaluations
against an estimate of 42, and the bar sat at 98–99% for **91% of its runtime** —
reporting 450 times, 410 of them the same number. The fraction is therefore
asymptotic: always moving, always increasing, never arriving.
"""

from __future__ import annotations

import pytest

import chisurf.core.fitting.minimizer as _minimizer

pytestmark = pytest.mark.skipif(
    not _minimizer.have_minimizer(), reason="IMP.bff carries no Minimizer"
)

import IMP.bff as _bff  # noqa: E402

#: `MAX_RUNNING_RATIO` in `Minimizer.cpp` -- a full bar is reserved for the
#: completion report. Spelled out here because it is a file-local constant in
#: C++ and not worth an export; if it moves there, this line is what fails.
_MAX_RUNNING_RATIO = 0.99

# The arithmetic moved into `IMP::bff::Minimizer` with the optimiser itself on
# 2026-09-01, when ChiSurf's second copy of the bounded Levenberg-Marquardt was
# deleted. The names are the C++ ones; the behaviour is the same and so is
# every assertion below.
_expected_evaluations = _bff.minimizer_expected_evaluations
_reported_total = _bff.minimizer_reported_total


def _fraction(nfev: int, expected: int) -> float:
    return nfev / _reported_total(nfev, expected)


def test_the_budget_scales_with_the_number_of_free_parameters():
    """One Jacobian plus one trial step per iteration, so it grows with ``n``."""
    for n in (2, 4, 10):
        assert _expected_evaluations(n, 0) > _expected_evaluations(n - 1, 0)
    # And far below MINPACK's give-up limit, which is what made the bar useless.
    for n in (1, 4, 10):
        assert _expected_evaluations(n, 0) < 200 * (n + 1) / 4


def test_the_budget_never_exceeds_the_hard_limit():
    """An estimate larger than the optimiser's own limit could never be reached."""
    assert _expected_evaluations(4, 20) == 20
    assert _expected_evaluations(100, 5) == 5


def test_the_reported_fraction_only_ever_increases():
    """A bar that retreats reads as a bug; the mapping makes it impossible."""
    expected = _expected_evaluations(6, 0)
    # The guarantee is about what is *displayed*. The reported total is a whole
    # number of evaluations, so deep in the tail -- past evaluation 950, where
    # the curve is flattening against its ceiling -- rounding can move the raw
    # fraction by about 0.001. At the one-percent resolution a bar actually has,
    # none of that is visible, and the displayed value never goes backwards.
    shown = [round(100 * _fraction(nfev, expected)) for nfev in range(1, 100000)]
    assert all(b >= a for a, b in zip(shown, shown[1:]))
    # Over any stretch worth watching it genuinely climbs.
    fractions = [_fraction(nfev, expected) for nfev in range(1, 500)]
    assert all(fractions[k + 20] > fractions[k] for k in range(0, 400, 20))


def test_a_running_fit_never_reports_a_full_bar():
    """100% is reserved for the completion report.

    A bar that says "done" while the fit runs on is one the user learns to
    ignore, so "converged" stays distinguishable from "still going".
    """
    expected = _expected_evaluations(6, 0)
    for nfev in (1, 42, 450, 5000, 100000):
        assert _fraction(nfev, expected) <= _MAX_RUNNING_RATIO + 1e-9
        assert _reported_total(nfev, expected) > nfev


def test_a_fit_that_runs_ten_times_the_estimate_still_moves():
    """The regression this mapping exists for.

    The MFD fit: 450 evaluations against an estimate of 42. Under a linear bar it
    reached 98% by evaluation 42 — ten seconds into a hundred-second fit — and
    then never moved again.
    """
    expected = _expected_evaluations(6, 0)
    assert expected == 42

    stuck_near_the_top = sum(1 for nfev in range(1, 451) if _fraction(nfev, expected) >= 0.97)
    assert stuck_near_the_top < 45, (
        f"{stuck_near_the_top} of 450 evaluations spent above 97%; the linear bar spent 410"
    )
    # And it is still visibly climbing over the second half of the fit.
    assert _fraction(450, expected) - _fraction(225, expected) > 0.05


def test_the_estimate_is_worth_a_meaningful_part_of_the_bar():
    """It must still *mean* something, or it is not an estimate at all."""
    expected = _expected_evaluations(6, 0)
    assert 0.2 < _fraction(expected, expected) < 0.45


def test_a_fit_that_beats_the_estimate_ends_low_and_that_is_fine():
    """The deliberate trade.

    Ending low costs a jump to 100% on a fit too fast to watch; saturating costs
    a dead bar on exactly the fits worth watching. Only one of those is visible.
    """
    expected = _expected_evaluations(2, 0)
    assert _fraction(8, expected) < 0.5
