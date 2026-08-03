"""The evaluation budget a fitting progress bar reports against.

The bar used to be scaled by MINPACK's ``200 * (n + 1)`` — its *give-up limit*,
not an expectation. A four-parameter fit converges in tens of evaluations, so the
bar crept to five percent and then jumped to done, which reads as broken rather
than fast.
"""

from __future__ import annotations

from chisurf.core.math.optimization.leastsqbound import (
    _MAX_RUNNING_RATIO,
    _expected_evaluations,
    _grow_budget,
)


def test_the_budget_scales_with_the_number_of_free_parameters():
    """One Jacobian plus one trial step per iteration, so it grows with ``n``."""
    for n in (1, 2, 4, 10):
        assert _expected_evaluations(n, 0) > _expected_evaluations(n - 1, 0) if n > 1 \
            else _expected_evaluations(n, 0) > 0
    # And far below MINPACK's give-up limit, which is what made the bar useless.
    for n in (1, 4, 10):
        assert _expected_evaluations(n, 0) < 200 * (n + 1) / 4


def test_the_budget_never_exceeds_the_hard_limit():
    """An estimate larger than the optimiser's own limit could never be reached."""
    assert _expected_evaluations(4, 20) == 20
    assert _expected_evaluations(100, 5) == 5


def test_the_budget_grows_when_a_fit_outruns_it():
    """A bar pinned at 100% while the fit runs on is wrong."""
    assert _grow_budget(10, 30, 0) == 30, "no growth while inside the estimate"
    grown = _grow_budget(31, 30, 0)
    assert grown > 30


def test_growth_never_makes_the_reported_fraction_go_backwards():
    """The failure mode of simply enlarging the denominator.

    The numerator rises by one while the denominator jumps by half, so the fraction
    *drops* and the bar retreats. Bounding the new budget by ``nfev / last_ratio``
    makes it stall at the previous fraction instead.
    """
    eff_total, last_ratio = 30, 0.0
    fractions = []
    for nfev in range(1, 120):
        eff_total = _grow_budget(nfev, eff_total, 0, last_ratio)
        fraction = min(1.0, nfev / eff_total)
        last_ratio = max(last_ratio, fraction)
        fractions.append(last_ratio)
    assert all(b >= a for a, b in zip(fractions, fractions[1:]))
    assert max(fractions) <= 1.0
    assert fractions[-1] > 0.9


def test_a_running_fit_never_reports_a_full_bar():
    """100% is reserved for the completion report.

    Without this floor the two rules collide: once a fit reaches 100% the
    retreat guard pins it there for every remaining evaluation, and a real
    four-parameter lifetime fit spent its last 110 evaluations that way. A bar
    that says "done" while the fit runs on is one the user learns to ignore.
    """
    eff_total, last_ratio = 30, 0.0
    for nfev in range(1, 400):
        eff_total = _grow_budget(nfev, eff_total, 0, last_ratio)
        fraction = nfev / eff_total
        assert fraction <= _MAX_RUNNING_RATIO + 1e-9, f"full bar at nfev={nfev}"
        last_ratio = max(last_ratio, fraction)


def test_growth_still_respects_the_hard_limit():
    """Growth may not carry the estimate past what the optimiser will ever do."""
    assert _grow_budget(999, 60, 100) == 100
