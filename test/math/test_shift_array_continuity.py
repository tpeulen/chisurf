"""``shift_array`` must be continuous in ``shift`` and equal ``v[k - shift]``.

Neither property was covered, and both were violated:

1. **Off-by-one for fractional negative shifts.** ``ts_i`` truncated toward zero
   while ``ts_f`` used ``floor()``, so the two disagreed below zero: ``-1.5``
   shifted by ``-0.5``, and ``-0.25`` produced a *right* shift with wrapped data
   at index 0. Integer shifts were correct, which is why it went unnoticed.

2. **A jump discontinuity at every integer shift.** The out-of-range region was
   blanked with ``ceil()``/``floor()``, so an infinitesimal shift zeroed a whole
   channel. The finite-difference slope therefore diverged as ``1/h`` (measured:
   1e9 at h=1e-9, 1e6 at h=1e-6).

(2) is why fits could not move ``timeshift``. It is a fit parameter starting at
0, and the fabricated slope made its Jacobian column ~1000x every other column;
LM proposed a huge step, the step did not help, and ``timeshift`` stayed pinned
at exactly 0. Fits that left it there plateaued at chi2r ~3 with otherwise
correct lifetimes. Over 24 randomised starts, fixing this took the number of
fits reaching chi2r < 1.1 from 11/24 to 15/24 at the shipped optimiser settings,
and removed the chi2r ~3 plateau entirely.
"""

import numpy as np
import pytest

from chisurf.core.math.signal import shift_array


def _reference(v, shift, outside_value=0.0):
    """Linear interpolation of ``v[k - shift]``, written the obvious slow way."""
    n = len(v)
    out = np.zeros(n)
    for k in range(n):
        pos = k - shift
        i = int(np.floor(pos))
        frac = pos - i
        lo = v[i] if 0 <= i < n else outside_value
        hi = v[i + 1] if 0 <= i + 1 < n else outside_value
        out[k] = lo * (1.0 - frac) + hi * frac
    return out


SHIFTS = [0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 3.75, -0.25, -0.5, -1.0, -1.5, -2.0, -3.75]


@pytest.mark.parametrize("shift", SHIFTS)
def test_matches_the_reference(shift):
    v = np.arange(1.0, 11.0)
    np.testing.assert_allclose(shift_array(v, shift), _reference(v, shift), atol=1e-12)


@pytest.mark.parametrize("shift", SHIFTS)
def test_matches_the_reference_with_nonzero_outside(shift):
    v = np.arange(1.0, 11.0)
    np.testing.assert_allclose(
        shift_array(v, shift, True, 33.0), _reference(v, shift, 33.0), atol=1e-12
    )


@pytest.mark.parametrize("centre", [0.0, 1.0, -1.0, 2.0, -2.0, 5.0, -5.0])
def test_continuous_across_integer_shifts(centre):
    """The regression: an infinitesimal shift must not blank a whole channel."""
    v = np.arange(1.0, 11.0)
    for h in (1e-9, 1e-7, 1e-5):
        jump = np.max(np.abs(shift_array(v, centre + h) - shift_array(v, centre - h)))
        # Bounded slope. Before the fix this was ~|v| regardless of h, so the
        # implied derivative diverged as 1/h.
        assert jump < 100.0 * h, (
            f"discontinuity at shift={centre}: |f(+h)-f(-h)|={jump:.3e} for h={h:g}"
        )


def test_a_tiny_shift_barely_changes_the_array():
    """Stated the other way round, because this is the property fits rely on."""
    v = np.arange(1.0, 11.0)
    np.testing.assert_allclose(shift_array(v, 1e-9), v, atol=1e-6)
    np.testing.assert_allclose(shift_array(v, -1e-9), v, atol=1e-6)


def test_integer_shifts_are_exact():
    v = np.arange(1.0, 11.0)
    np.testing.assert_allclose(shift_array(v, 2.0)[2:], v[:-2])
    np.testing.assert_allclose(shift_array(v, -2.0)[:-2], v[2:])
    assert shift_array(v, 2.0)[:2].tolist() == [0.0, 0.0]
    assert shift_array(v, -2.0)[-2:].tolist() == [0.0, 0.0]


def test_shifts_beyond_the_array_are_all_outside():
    v = np.arange(1.0, 4.0)
    assert shift_array(v, 10.0).tolist() == [0.0, 0.0, 0.0]
    assert shift_array(v, -10.0).tolist() == [0.0, 0.0, 0.0]


def test_empty_input():
    assert shift_array(np.array([]), 1.0).size == 0
